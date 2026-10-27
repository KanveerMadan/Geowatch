"""
Item 19 — the vector road layer. One source, many representations.

A RoadLayer is built once per AOI from OSM highway=* (primary) plus
building-footprint negative space where OSM's pedestrian layer is thin. Every
road-derived output is a method of the layer -- `lengths_km`, `road_space`,
`rasterize`, `graph`, `surface_coverage`, `paved_status` -- and every result
dict carries the layer's `layer_id`. Consumers (items 20, 22-24) take a layer
and call these. They never re-fetch or rebuild roads, which is what makes all
road outputs degrade together when coverage is thin (02_ARCHITECTURE.md §4).

All geometry is held in the AOI's local UTM zone, so lengths, areas and
buffers are in metres.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import numpy as np
import pyproj
from shapely import STRtree
from shapely.geometry import LineString, Polygon, box, mapping
from shapely.ops import transform as shp_transform, unary_union

# ── Road widths ──────────────────────────────────────────────────────────
#
# DEFAULTS, NOT MEASUREMENTS. One assumed carriageway width per OSM highway
# class, carried over unchanged from generate_osm_road_masks.py. OSM `width`
# tags are rare and were not used. Every polygon built from these is an
# assumed footprint around a measured centreline, and anything reading road
# AREA (rasterize, road_space) inherits that assumption. Road LENGTH does not
# depend on these at all.
HIGHWAY_WIDTH_M_DEFAULT = {
    "motorway": 12, "trunk": 10, "primary": 9, "secondary": 8,
    "tertiary": 7, "residential": 5, "unclassified": 5,
    "living_street": 5, "service": 4, "track": 3,
    "path": 1.5, "footway": 1.5, "pedestrian": 3,
    "cycleway": 2,
}
WIDTH_M_DEFAULT_UNLISTED = 5   # DEFAULT for any class not listed above

# ── Groupings. Narrow and broad are kept SEPARATE and never merged. ─────────
#
# 03_EVIDENCE.md Part B: only footway/path/pedestrian/steps stand in for
# alleys. service/residential/track are vehicular-capable. HCMC ranks 2nd on
# the broad grouping and 3rd-lowest on the narrow one, so merging them
# changes the answer.
ARTERIAL_CLASSES = frozenset({
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link",
})
NARROW_PEDESTRIAN_CLASSES = frozenset({"footway", "path", "pedestrian", "steps"})
BROAD_PEDESTRIAN_CLASSES = NARROW_PEDESTRIAN_CLASSES | {"service", "residential", "track"}

# ── surface=* ─────────────────────────────────────────────────────────────
# Standard OSM values (wiki Key:surface). Anything else tagged counts as
# "other", and untagged ways count as "untagged". The two are kept apart.
PAVED_SURFACES = frozenset({
    "paved", "asphalt", "concrete", "concrete:plates", "concrete:lanes",
    "paving_stones", "sett", "cobblestone", "unhewn_cobblestone", "chipseal",
    "brick", "bricks", "metal", "wood",
})
UNPAVED_SURFACES = frozenset({
    "unpaved", "compacted", "fine_gravel", "gravel", "pebblestone", "rock",
    "dirt", "earth", "ground", "grass", "mud", "sand", "woodchips", "clay",
})
# Where surface is untagged, paved access is ASSUMED for these classes.
# A default, not a measurement: paved_status() reports which basis was used.
PAVED_BY_CLASS_DEFAULT = ARTERIAL_CLASSES | {"residential", "living_street"}

# ── Footprint negative space ──────────────────────────────────────────────
#
# Fixed before any real-data run (2026-10-27). PROVISIONAL, not calibrated.
#
# Trigger: negative space is derived only where narrow pedestrian density is
# below this. 03_EVIDENCE.md Part B's under-mapped cases sit below it (Lagos
# 0.19, Jakarta 0.39, HCMC 0.90); Accra (1.29) and every better-mapped
# baseline city sit above it.
NEGATIVE_SPACE_TRIGGER_KM_PER_KM2 = 1.0
# Gaps between footprints at most this wide count as candidate road space
# (a morphological closing of radius half this). DEFAULT, not a measurement.
NEGATIVE_SPACE_MAX_GAP_M = 6.0
# Slivers smaller than this are dropped as digitisation noise.
NEGATIVE_SPACE_MIN_AREA_M2 = 20.0


def utm_crs_for(bbox) -> pyproj.CRS:
    w, s, e, n = bbox
    lon, lat = (w + e) / 2, (s + n) / 2
    zone = int((lon + 180) / 6) + 1
    return pyproj.CRS.from_epsg((32600 if lat >= 0 else 32700) + zone)


def surface_class(surface) -> str:
    if surface is None or surface == "":
        return "untagged"
    if surface in PAVED_SURFACES:
        return "paved"
    if surface in UNPAVED_SURFACES:
        return "unpaved"
    return "other"


@dataclass
class Way:
    id: int
    highway: str
    surface: str | None
    nodes: list
    line: LineString            # UTM, NOT clipped (topology needs the whole way)
    clipped: object             # UTM, clipped to the AOI (LineString/MultiLineString/empty)

    @property
    def length_m(self) -> float:
        return float(self.clipped.length)

    @property
    def width_m_default(self) -> float:
        return float(HIGHWAY_WIDTH_M_DEFAULT.get(self.highway, WIDTH_M_DEFAULT_UNLISTED))


@dataclass
class RoadLayer:
    name: str
    bbox: tuple
    crs: pyproj.CRS
    aoi: Polygon                         # UTM
    ways: list
    footprints: list                     # UTM polygons
    footprint_source: str                # "open_buildings_v3" | "osm_building" | "none"
    negative_space: object               # UTM geometry (possibly empty)
    negative_space_triggered: bool
    fetch: dict = field(default_factory=dict)
    layer_id: str = ""

    # ── provenance ──
    def stamp(self, out: dict) -> dict:
        """Every representation's output carries the layer it came from."""
        out["source_layer_id"] = self.layer_id
        return out

    @property
    def area_km2(self) -> float:
        return self.aoi.area / 1e6

    # ── representation: aggregated length ──
    def lengths_km(self, region=None) -> dict:
        """Road length by grouping, clipped to `region` (default: the AOI).
        Narrow and broad are reported separately, never summed together."""
        region = self.aoi if region is None else region
        out = {"all": 0.0, "arterial": 0.0, "narrow_pedestrian": 0.0,
               "broad_pedestrian": 0.0}
        for w in self.ways:
            L = w.clipped.intersection(region).length if region is not self.aoi else w.length_m
            if not L:
                continue
            out["all"] += L
            if w.highway in ARTERIAL_CLASSES:
                out["arterial"] += L
            if w.highway in NARROW_PEDESTRIAN_CLASSES:
                out["narrow_pedestrian"] += L
            if w.highway in BROAD_PEDESTRIAN_CLASSES:
                out["broad_pedestrian"] += L
        return self.stamp({k: v / 1000.0 for k, v in out.items()})

    def densities_km_per_km2(self) -> dict:
        L = self.lengths_km()
        return self.stamp({k: L[k] / self.area_km2 for k in
                           ("all", "arterial", "narrow_pedestrian", "broad_pedestrian")})

    # ── measurement: surface tag coverage ──
    def surface_coverage(self) -> dict:
        """Share of clipped road LENGTH carrying each surface class, per
        grouping. Measured from the tags, so it is never assumed."""
        groups = {"all": lambda h: True,
                  "arterial": lambda h: h in ARTERIAL_CLASSES,
                  "narrow_pedestrian": lambda h: h in NARROW_PEDESTRIAN_CLASSES,
                  "broad_pedestrian": lambda h: h in BROAD_PEDESTRIAN_CLASSES}
        out = {}
        for g, member in groups.items():
            tot = {"paved": 0.0, "unpaved": 0.0, "other": 0.0, "untagged": 0.0}
            for w in self.ways:
                if member(w.highway):
                    tot[surface_class(w.surface)] += w.length_m
            total = sum(tot.values())
            out[g] = {
                "length_km": total / 1000.0,
                "tagged_share": (1.0 - tot["untagged"] / total) if total else 0.0,
                **{f"{k}_share": (v / total if total else 0.0) for k, v in tot.items()},
            }
        return self.stamp(out)

    # ── classification shared by access (item 24) ──
    def paved_status(self, way: Way) -> tuple:
        """(is_paved, basis). basis is "surface_tag" or "class_default"."""
        sc = surface_class(way.surface)
        if sc == "paved":
            return True, "surface_tag"
        if sc in ("unpaved", "other"):
            return False, "surface_tag"
        return way.highway in PAVED_BY_CLASS_DEFAULT, "class_default"

    # ── representation: road space (area) ──
    def road_space(self, include_negative_space: bool = True):
        """Union of OSM centrelines buffered by their DEFAULT widths, plus
        footprint negative space. Clipped to the AOI."""
        polys = [w.clipped.buffer(w.width_m_default / 2.0, cap_style="flat")
                 for w in self.ways if w.length_m > 0]
        geom = unary_union(polys) if polys else Polygon()
        if include_negative_space and not self.negative_space.is_empty:
            geom = unary_union([geom, self.negative_space])
        return geom.intersection(self.aoi)

    # ── representation: raster ──
    def rasterize(self, transform, shape, *, supersample: int = 5,
                  include_negative_space: bool = True) -> dict:
        """Road-space area fraction per pixel on a grid in this layer's CRS.
        Supersampled `supersample`x per axis, so a 4.5 m road contributes a
        proportional share of a 10 m pixel rather than a false binary."""
        from rasterio.features import rasterize as rio_rasterize
        from rasterio.transform import Affine

        geom = self.road_space(include_negative_space)
        H, W = shape
        fine = transform * Affine.scale(1.0 / supersample)
        if geom.is_empty:
            frac = np.zeros(shape, dtype=np.float32)
        else:
            hit = rio_rasterize([(mapping(geom), 1)], out_shape=(H * supersample, W * supersample),
                                transform=fine, fill=0, dtype="uint8")
            frac = hit.reshape(H, supersample, W, supersample).mean(axis=(1, 3)).astype(np.float32)
        return self.stamp({"fraction": frac, "transform": transform, "crs": self.crs.to_string(),
                           "width_basis": "HIGHWAY_WIDTH_M_DEFAULT (defaults, not measurements)"})

    # ── representation: blocks (path-delineated polygons) ──
    BLOCK_CUT_WIDTH_M = 0.02   # centrelines cut the AOI as 2 cm strips

    def blocks(self, min_area_m2: float = 1.0) -> list:
        """The AOI partitioned by the road network. Used by item 22
        (path-delineated units) and item 24 (per-block access), so both read
        the same partition.

        Computed as the AOI minus every centreline buffered by
        BLOCK_CUT_WIDTH_M / 2, not by polygonize(): a way clipped at the AOI
        edge ends a float's width inside or outside the boundary and never
        nodes with it, so polygonize silently merges blocks. The cut costs
        2 cm x road length of area (about 1e-4 of a typical AOI). Slivers
        under `min_area_m2` are dropped. Negative space has no centrelines
        and delineates nothing."""
        cut = unary_union([w.line.buffer(self.BLOCK_CUT_WIDTH_M / 2.0)
                           for w in self.ways if w.length_m > 0])
        pieces = self.aoi.difference(cut) if not cut.is_empty else self.aoi
        parts = getattr(pieces, "geoms", [pieces])
        return [p for p in parts if p.geom_type == "Polygon" and p.area >= min_area_m2]

    # ── representation: network ──
    def graph(self):
        """networkx Graph on real OSM node ids. An edge is one consecutive
        node pair of a way, kept when its segment touches the AOI. Negative
        space is area-only and has no topology, so it never enters here."""
        import networkx as nx
        G = nx.Graph(source_layer_id=self.layer_id, crs=self.crs.to_string())
        for w in self.ways:
            coords = list(w.line.coords)
            if len(coords) != len(w.nodes):
                continue
            for i in range(len(coords) - 1):
                seg = LineString([coords[i], coords[i + 1]])
                if not seg.intersects(self.aoi):
                    continue
                a, b = w.nodes[i], w.nodes[i + 1]
                G.add_node(a, xy=coords[i])
                G.add_node(b, xy=coords[i + 1])
                G.add_edge(a, b, length_m=seg.length, highway=w.highway,
                           surface=w.surface, way_id=w.id)
        return G


# ── construction ─────────────────────────────────────────────────────────

def _layer_id(name, bbox, ways, footprint_source, footprints, negative_space) -> str:
    h = hashlib.sha256()
    h.update(json.dumps([name, [round(v, 6) for v in bbox], footprint_source]).encode())
    for w in sorted(ways, key=lambda w: w.id):
        h.update(f"{w.id}:{w.highway}:{w.surface};".encode())
    h.update(f"fp:{len(footprints)}:{round(sum(p.area for p in footprints), 1)}".encode())
    h.update(f"ns:{round(negative_space.area, 1)}".encode())
    return h.hexdigest()[:16]


def derive_negative_space(footprints, aoi, road_space):
    """Candidate road space from footprint gaps: a morphological closing of
    the footprint union (radius NEGATIVE_SPACE_MAX_GAP_M / 2) minus the
    footprints themselves and minus space OSM already maps. Gaps up to
    NEGATIVE_SPACE_MAX_GAP_M wide survive; open ground does not."""
    if not footprints:
        return Polygon()
    r = NEGATIVE_SPACE_MAX_GAP_M / 2.0
    fp = unary_union(footprints)
    closed = fp.buffer(r, join_style="mitre").buffer(-r, join_style="mitre")
    gaps = closed.difference(fp).difference(road_space).intersection(aoi)
    parts = getattr(gaps, "geoms", [gaps])
    keep = [g for g in parts if g.geom_type == "Polygon" and g.area >= NEGATIVE_SPACE_MIN_AREA_M2]
    return unary_union(keep) if keep else Polygon()


def build_road_layer(name: str, bbox, *, highways: dict, footprints_4326: list,
                     footprint_source: str) -> RoadLayer:
    """Assemble a layer from already-fetched inputs (see load_road_layer for
    the fetching wrapper). `highways` is sources.fetch_osm_highways' output.
    `footprints_4326` is a list of shapely polygons in EPSG:4326."""
    crs = utm_crs_for(bbox)
    to_utm = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    aoi = shp_transform(to_utm, box(*bbox))

    ways = []
    for el in highways["ways"]:
        coords = [(p["lon"], p["lat"]) for p in el["geometry"] if p]
        if len(coords) < 2:
            continue
        line = shp_transform(to_utm, LineString(coords))
        tags = el.get("tags", {})
        ways.append(Way(id=el["id"], highway=tags.get("highway", ""),
                        surface=tags.get("surface"), nodes=list(el.get("nodes", [])),
                        line=line, clipped=line.intersection(aoi)))

    fps = []
    for p in footprints_4326:
        q = shp_transform(to_utm, p)
        if not q.is_valid:
            q = q.buffer(0)
        if not q.is_empty:
            fps.append(q)
    # Footprints are kept whole but must touch the AOI.
    if fps:
        tree = STRtree(fps)
        fps = [fps[i] for i in tree.query(aoi, predicate="intersects")]

    layer = RoadLayer(name=name, bbox=tuple(bbox), crs=crs, aoi=aoi, ways=ways,
                      footprints=fps, footprint_source=footprint_source,
                      negative_space=Polygon(), negative_space_triggered=False,
                      fetch={"clauses": highways.get("clauses", {}),
                             "unavailable": list(highways.get("unavailable", []))})
    narrow = layer.lengths_km()["narrow_pedestrian"] / layer.area_km2
    if narrow < NEGATIVE_SPACE_TRIGGER_KM_PER_KM2:
        layer.negative_space_triggered = True
        layer.negative_space = derive_negative_space(
            fps, aoi, layer.road_space(include_negative_space=False))
    layer.layer_id = _layer_id(name, bbox, ways, footprint_source, fps, layer.negative_space)
    return layer


def load_footprints(name: str, bbox) -> tuple:
    """(polygons_4326, source). Open Buildings where it has coverage, OSM
    buildings otherwise. Which one was used is always recorded."""
    from vector import sources
    if sources.count_open_buildings(bbox) > 0:
        gdf = sources.fetch_open_buildings(name, bbox)
        return list(gdf.geometry), "open_buildings_v3"
    osm = sources.fetch_osm_buildings(name, bbox)
    if osm["unavailable"]:
        raise RuntimeError(f"{name}: no Open Buildings coverage and OSM buildings "
                           f"could not be retrieved")
    return [Polygon(r["coords"]) for r in osm["buildings"]], "osm_building"


def load_road_layer(name: str, bbox) -> RoadLayer:
    """Fetch (cached) and build the layer for one AOI."""
    from vector import sources
    highways = sources.fetch_osm_highways(name, bbox)
    fps, src = load_footprints(name, bbox)
    return build_road_layer(name, bbox, highways=highways,
                            footprints_4326=fps, footprint_source=src)
