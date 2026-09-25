"""
Load a hand-drawn strata layer (LABELLING_GUIDE.md §3) for tiles.build_frame.

    strata, report = load_strata(path, site, cfg)
    frame = tiles.build_frame(site, crs, bounds, strata, cfg, frame=...)

The file is the site package's strata.geojson (data/strata_packages/<site>/),
drawn in QGIS in the site's UTM CRS. Returns {stratum: shapely geometry}
(each stratum's polygons unioned) and a report.

REJECTED (StrataError):
  - wrong CRS: the file must name the site's CRS in a GeoJSON "crs" member.
    A file with none is RFC 7946 WGS84 -- which is what QGIS writes by
    default on "Save as GeoJSON" -- and is rejected rather than assumed.
  - a stratum value that is null, empty, or not one of the guide's four
  - a null, non-polygon or invalid geometry
  - no features at all (nothing to stratify by)

WARNED (StrataOverlapWarning, and listed in the report): overlap between
polygons of DIFFERENT strata, with its area in m². tiles.assign_stratum
gives such ground to the plurality stratum, so an overlap is not fatal, but
it is almost always a drawing slip.
"""

from __future__ import annotations

import json
import warnings
from itertools import combinations

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.validation import explain_validity

POLYGONAL = ("Polygon", "MultiPolygon")


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


def load_strata(path: str, site: str, cfg: dict) -> tuple[dict, dict]:
    with open(path) as fh:
        fc = json.load(fh)
    if fc.get("type") != "FeatureCollection":
        raise StrataError(f"{path}: not a GeoJSON FeatureCollection")

    want = cfg["aois"][site]["crs"]
    got = _declared_crs(fc)
    if got != want:
        raise StrataError(
            f"{path}: CRS is {got or 'not declared (RFC 7946 WGS84)'}, expected {want}. "
            f"In QGIS, save with CRS {want} and RFC 7946 unchecked.")

    allowed = list(cfg["tiles"]["strata"])
    feats = fc.get("features") or []
    if not feats:
        raise StrataError(f"{path}: no strata drawn")

    parts = {s: [] for s in allowed}
    for i, f in enumerate(feats):
        value = (f.get("properties") or {}).get("stratum")
        if value is None or not str(value).strip():
            raise StrataError(f"{path}: feature {i} has no stratum value")
        if value not in allowed:
            raise StrataError(f"{path}: feature {i} stratum {value!r} is not one of {allowed}")
        g = f.get("geometry")
        if not g:
            raise StrataError(f"{path}: feature {i} ({value}) has no geometry")
        if g.get("type") not in POLYGONAL:
            raise StrataError(f"{path}: feature {i} ({value}) is a {g.get('type')}, not a polygon")
        geom = shape(g)
        if not geom.is_valid:
            raise StrataError(f"{path}: feature {i} ({value}) invalid geometry: {explain_validity(geom)}")
        if geom.is_empty:
            raise StrataError(f"{path}: feature {i} ({value}) has an empty geometry")
        parts[value].append(geom)

    strata = {s: unary_union(gs) for s, gs in parts.items() if gs}
    overlaps = []
    for a, b in combinations(sorted(strata), 2):
        area = strata[a].intersection(strata[b]).area
        if area > 0:
            overlaps.append({"strata": [a, b], "area_m2": round(area, 1)})
            warnings.warn(f"{path}: strata {a} and {b} overlap by {area:.1f} m2",
                          StrataOverlapWarning, stacklevel=2)
    report = {"crs": got, "features": len(feats),
              "area_m2": {s: round(g.area, 1) for s, g in strata.items()},
              "strata_missing": [s for s in allowed if s not in strata],
              "overlaps": overlaps}
    return strata, report
