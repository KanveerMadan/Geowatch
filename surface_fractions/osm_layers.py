"""
OSM context layers for item 21 Phase A, fetched ONLY through
ingestion/overpass.py (C44: the project's single Overpass client).

A layer is a named group of Overpass tag filters (configs/fractions.yaml
`osm_layers`). Each is rasterised onto the native Sentinel-2 grid:

  area  -> per-pixel covered fraction, via grid.polygon_coverage
  line  -> per-pixel 0/1 "touched", via grid.line_touch. OSM lines carry no
           width, so no area is claimed for them.

A group with no usable OSM tag is status "no_producer" and has no array --
never an all-zero array, which would read as "measured, none present" (C33).
"""

from __future__ import annotations

import hashlib
import json
import os

import numpy as np

from ingestion.overpass import OverpassError, run_query
from surface_fractions.config import REPO_ROOT
from surface_fractions.grid import Grid, line_touch, polygon_coverage, to_grid_crs

GEOMETRY_MODES = ("area", "line", "area_or_line")
CACHE_DIR = os.path.join(REPO_ROOT, "cache", "surface_fractions", "osm")


def build_query(filters: list, bbox: dict, timeout: int = 90) -> str:
    """One Overpass QL query for all `filters` (ORed), ways and relations,
    returned with inline geometry."""
    b = f"({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']})"
    parts = []
    for f in filters:
        parts.append(f"way{f}{b};")
        parts.append(f"relation{f}{b};")
    return f"[out:json][timeout:{timeout}];(" + "".join(parts) + ");out geom;"


def _ring(points) -> list:
    return [(p["lon"], p["lat"]) for p in points]


def _way_geometry(el: dict, mode: str):
    """A way -> ('area'|'line', shapely geometry) or None."""
    from shapely.geometry import LineString, Polygon
    pts = _ring(el.get("geometry") or [])
    if len(pts) < 2:
        return None
    closed = len(pts) >= 4 and pts[0] == pts[-1]
    if mode == "line" or (mode == "area_or_line" and not closed):
        return "line", LineString(pts)
    if not closed:
        # An area tag on an open way is a mapping error; it encloses nothing.
        return None
    poly = Polygon(pts)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return ("area", poly) if not poly.is_empty else None


def _relation_geometry(el: dict):
    """A type=multipolygon relation -> ('area', geometry) or None. Outer
    member ways are polygonised together (they may be split into several
    ways), inner rings are subtracted."""
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    if el.get("tags", {}).get("type") not in ("multipolygon", "boundary"):
        return None
    outer, inner = [], []
    for m in el.get("members", []):
        if m.get("type") != "way" or not m.get("geometry"):
            continue
        pts = _ring(m["geometry"])
        if len(pts) < 2:
            continue
        (inner if m.get("role") == "inner" else outer).append(LineString(pts))
    if not outer:
        return None
    shape = unary_union(list(polygonize(unary_union(outer))))
    if inner:
        shape = shape.difference(unary_union(list(polygonize(unary_union(inner)))))
    return ("area", shape) if not shape.is_empty else None


def elements_to_geometries(elements: list, mode: str) -> tuple[list, list]:
    """Overpass elements -> (area geometries, line geometries), in WGS84."""
    if mode not in GEOMETRY_MODES:
        raise ValueError(f"geometry mode {mode!r} not in {GEOMETRY_MODES}")
    areas, lines = [], []
    for el in elements:
        if el.get("type") == "way":
            got = _way_geometry(el, mode)
        elif el.get("type") == "relation" and mode != "line":
            got = _relation_geometry(el)
        else:
            got = None
        if got is None:
            continue
        kind, geom = got
        (areas if kind == "area" else lines).append(geom)
    return areas, lines


def fetch_layer(name: str, spec: dict, bbox: dict, cache_dir: str = CACHE_DIR,
                query_fn=run_query) -> dict:
    """Fetch one layer's elements, cached on disk by query text."""
    if spec.get("status") == "no_producer" or not spec.get("filters"):
        return {"name": name, "status": "no_producer", "elements": None}
    query = build_query(spec["filters"], bbox)
    key = hashlib.sha1(query.encode()).hexdigest()[:16]
    path = os.path.join(cache_dir, f"{name}__{key}.json")
    if os.path.exists(path):
        with open(path) as fh:
            return {"name": name, "status": "available", "elements": json.load(fh),
                    "query": query, "cached": True}
    try:
        elements = query_fn(query)
    except OverpassError as e:
        # Not cached, so a later run retries. Reported, never read as zero.
        return {"name": name, "status": "unavailable", "elements": None,
                "query": query, "error": f"{type(e).__name__}: {e}"}
    os.makedirs(cache_dir, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(elements, fh)
    return {"name": name, "status": "available", "elements": elements,
            "query": query, "cached": False}


def rasterise_layer(fetched: dict, spec: dict, grid: Grid) -> dict:
    """A fetched layer -> per-pixel arrays on `grid`.

    Returns {"status", "area_fraction", "line_touch", "n_features"}; arrays
    are None when there is no producer, and present-but-zero when the layer
    was queried and OSM has nothing here.
    """
    if fetched["status"] != "available":
        return {"status": fetched["status"], "area_fraction": None,
                "line_touch": None, "n_features": None,
                "error": fetched.get("error")}
    areas, lines = elements_to_geometries(fetched["elements"], spec["geometry"])
    area = polygon_coverage(to_grid_crs(areas, grid), grid) if spec["geometry"] != "line" else None
    touch = line_touch(to_grid_crs(lines, grid), grid) if spec["geometry"] != "area" else None
    return {"status": "available",
            "area_fraction": None if area is None else area.astype(np.float32),
            "line_touch": touch,
            "n_features": {"areas": len(areas), "lines": len(lines)}}


def assemble_osm_layers(cfg: dict, bbox: dict, grid: Grid,
                        query_fn=run_query, cache_dir: str = CACHE_DIR) -> dict:
    out = {}
    for name, spec in cfg["osm_layers"].items():
        fetched = fetch_layer(name, spec, bbox, cache_dir, query_fn)
        out[name] = rasterise_layer(fetched, spec, grid)
        out[name]["geometry"] = spec["geometry"]
    return out
