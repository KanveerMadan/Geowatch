"""
Load the site's strata layer (LABELLING_GUIDE.md §3) for tiles.build_frame,
and compare the rule's draft with the hand-corrected final.

    strata, report = load_strata(path, site, cfg)
    frame = tiles.build_frame(site, crs, bounds, strata, cfg, frame=...)
    diff = compare_draft_final(draft_path, final_path, site, cfg)

`path` is the site package's strata.gpkg (layer "strata", written by
labelling/strata_rule.py and corrected by hand in QGIS) -- or a GeoJSON with
the same content. Returns {stratum: shapely geometry} (each stratum's polygons
unioned; `unassigned` tiles are accepted but never returned, so never
sampled) and a report.

REJECTED (StrataError):
  - wrong CRS. A GeoPackage's layer CRS must be the site's; a GeoJSON must
    name it in a "crs" member -- one with none is RFC 7946 WGS84, which is
    what QGIS writes by default on "Save as GeoJSON", and is rejected
    rather than assumed.
  - a stratum value that is null, empty, or not one of the guide's four or
    `unassigned`
  - a null, non-polygon or invalid geometry
  - no features, or no feature in any of the four strata

WARNED (StrataOverlapWarning, and listed in the report): overlap between
polygons of DIFFERENT strata, with its area in m². tiles.assign_stratum gives
such ground to the plurality stratum, so it is not fatal, but it is almost
always a drawing slip.
"""

from __future__ import annotations

import json
import warnings
from collections import Counter
from itertools import combinations

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.validation import explain_validity

POLYGONAL = ("Polygon", "MultiPolygon")
UNASSIGNED = "unassigned"
LAYER = "strata"


class StrataError(ValueError):
    pass


class StrataOverlapWarning(UserWarning):
    pass


def _declared_crs(fc: dict) -> str | None:
    crs = fc.get("crs")
    if not crs:
        return None
    name = crs.get("properties", {}).get("name", "")
    # "urn:ogc:def:crs:EPSG::32631" or "EPSG:32631"
    if "EPSG" in name:
        return "EPSG:" + name.replace("::", ":").rsplit(":", 1)[-1]
    return name or None


def _read(path: str) -> tuple[str | None, list]:
    """-> (declared CRS as 'EPSG:nnnn' or None, [(props, geojson geometry)])."""
    if path.lower().endswith(".gpkg"):
        import geopandas as gpd
        try:
            gdf = gpd.read_file(path, layer=LAYER, engine="pyogrio")
        except Exception as e:  # noqa: BLE001 -- surface as a strata error
            raise StrataError(f"{path}: cannot read layer {LAYER!r}: {e}") from None
        epsg = gdf.crs.to_epsg() if gdf.crs is not None else None
        crs = f"EPSG:{epsg}" if epsg else None
        feats = json.loads(gdf.to_json(drop_id=True))["features"] if len(gdf) else []
        return crs, [(f.get("properties") or {}, f.get("geometry")) for f in feats]
    with open(path) as fh:
        fc = json.load(fh)
    if fc.get("type") != "FeatureCollection":
        raise StrataError(f"{path}: not a GeoJSON FeatureCollection")
    return _declared_crs(fc), [(f.get("properties") or {}, f.get("geometry"))
                               for f in fc.get("features") or []]


def load_strata(path: str, site: str, cfg: dict) -> tuple[dict, dict]:
    got, feats = _read(path)
    want = cfg["aois"][site]["crs"]
    if got != want:
        raise StrataError(
            f"{path}: CRS is {got or 'not declared (RFC 7946 WGS84)'}, expected {want}. "
            f"In QGIS, keep the layer in {want} (and for GeoJSON, untick RFC 7946).")

    allowed = list(cfg["tiles"]["strata"])
    if not feats:
        raise StrataError(f"{path}: no strata drawn")

    parts = {s: [] for s in allowed}
    n_unassigned = 0
    for i, (props, g) in enumerate(feats):
        value = props.get("stratum")
        if value is None or not str(value).strip():
            raise StrataError(f"{path}: feature {i} has no stratum value")
        if value not in allowed and value != UNASSIGNED:
            raise StrataError(f"{path}: feature {i} stratum {value!r} is not one of "
                              f"{allowed + [UNASSIGNED]}")
        if not g:
            raise StrataError(f"{path}: feature {i} ({value}) has no geometry")
        if g.get("type") not in POLYGONAL:
            raise StrataError(f"{path}: feature {i} ({value}) is a {g.get('type')}, not a polygon")
        geom = shape(g)
        if not geom.is_valid:
            raise StrataError(f"{path}: feature {i} ({value}) invalid geometry: {explain_validity(geom)}")
        if geom.is_empty:
            raise StrataError(f"{path}: feature {i} ({value}) has an empty geometry")
        if value == UNASSIGNED:
            n_unassigned += 1                        # accepted, never sampled
            continue
        parts[value].append(geom)

    strata = {s: unary_union(gs) for s, gs in parts.items() if gs}
    if not strata:
        raise StrataError(f"{path}: every feature is {UNASSIGNED}; nothing to sample")
    overlaps = []
    for a, b in combinations(sorted(strata), 2):
        area = strata[a].intersection(strata[b]).area
        if area > 0:
            overlaps.append({"strata": [a, b], "area_m2": round(area, 1)})
            warnings.warn(f"{path}: strata {a} and {b} overlap by {area:.1f} m2",
                          StrataOverlapWarning, stacklevel=2)
    report = {"crs": got, "features": len(feats), "unassigned_features": n_unassigned,
              "area_m2": {s: round(g.area, 1) for s, g in strata.items()},
              # Empty strata are skipped for the site; coverage is required
              # across the training set as a whole (decided 2026-09-25).
              "strata_missing": [s for s in allowed if s not in strata],
              "overlaps": overlaps}
    return strata, report


def compare_draft_final(draft_path: str, final_path: str, site: str, cfg: dict) -> dict:
    """Draft (the rule) vs final (hand-corrected): per tile_id, what changed.

    -> {"tiles": n, "changed": n, "transitions": {"from -> to": n},
        "changed_tiles": [{tile_id, from, to}], "added": [...], "removed": [...],
        "geometry_changed": [...]}"""
    load_strata(final_path, site, cfg)                   # the final must itself be valid
    _, d_feats = _read(draft_path)
    _, f_feats = _read(final_path)

    def index(feats, path):
        out = {}
        for props, g in feats:
            tid = props.get("tile_id")
            if not tid:
                raise StrataError(f"{path}: a feature has no tile_id; the draft-vs-final "
                                  f"comparison is per tile")
            out[tid] = (props.get("stratum"), shape(g) if g else None)
        return out

    d, f = index(d_feats, draft_path), index(f_feats, final_path)
    changed, geom_changed = [], []
    for tid in sorted(set(d) & set(f)):
        (ds, dg), (fs, fg) = d[tid], f[tid]
        if ds != fs:
            changed.append({"tile_id": tid, "from": ds, "to": fs})
        if dg is not None and fg is not None and not dg.equals_exact(fg, 1e-6):
            geom_changed.append(tid)
    trans = Counter(f"{c['from']} -> {c['to']}" for c in changed)
    return {"site": site, "tiles": len(d), "changed": len(changed),
            "transitions": dict(sorted(trans.items())), "changed_tiles": changed,
            "added": sorted(set(f) - set(d)), "removed": sorted(set(d) - set(f)),
            "geometry_changed": geom_changed}
