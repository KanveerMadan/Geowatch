"""
Round 3: shared-tile caches for the Sentinel-1-route feature build (flash / waterlogging DEV units).

A profile of one unit (2026-11-23) found 96 % of its 17 min was network waiting:
- the three rainfall climatology layers: 3 Earth Engine computePixels calls, ~600 s;
- the OSM water mask: 4 Overpass queries, ~350 s.
Neighbouring units (the same plain-year, nearby flash episodes) repeat the same requests. This module caches
them on shared tiles. It is installed only in the `build_r3 --s1feat` subprocess; nothing else changes.

- **Rain layers (exact; CHIRPS annual and design-day only):** the IMERG intensity layer timed out at 4 deg tiles
  and is left per unit. `hydro_rasters._rain_layer` fetches each layer on its own deg-aligned native lon/lat
  grid and maps it nearest onto the unit grid. Here the native grid is fetched per TILE_DEG tile (aligned to
  multiples of the native cell), cached by (layer, ref_year, tile), and cut to the unit's native window.
  Same cells, same values.
- **OSM water (equivalent up to Overpass edge cases):** each water clause is fetched once per OSM_TILE_DEG tile
  (`out geom`, unclipped). A unit keeps the elements whose geometry (a way's, or any relation member's)
  intersects its own box, which is the selection Overpass makes for the unit's box. Recorded in DECISIONS R31.
"""
from __future__ import annotations

import hashlib
import json
import math
import os

import numpy as np

CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/tilecache")
TILE_DEG = 4.0
OSM_TILE_DEG = 0.25
_STATE = {"year": None}


def _rain_tile(img, name, year, tx, ty, deg):
    import ee
    from ee_timeout import call
    from rasterio.transform import from_origin
    from susceptibility import hydro_rasters as HR
    p = os.path.join(CACHE, "rain", f"{name}_{year}_{tx}_{ty}.npy")
    if os.path.exists(p):
        return np.load(p)
    x0, y1 = tx * TILE_DEG, (ty + 1) * TILE_DEG
    n = int(round(TILE_DEG / deg))

    def fetch(timeout, retries):
        return call(lambda: ee.data.computePixels({
            "expression": img.unmask(HR.NODATA).toFloat(), "fileFormat": "NUMPY_NDARRAY",
            "grid": HR.ee_grid(from_origin(x0, y1, deg, deg), (n, n), "EPSG:4326")}),
            timeout=timeout, retries=retries, label=f"{name} tile {tx},{ty}")

    if name == HR.IMERG_LAYER:
        with HR.request_deadline(HR.IMERG_DEADLINE_S * 1000):
            arr = fetch(HR.IMERG_DEADLINE_S, HR.IMERG_RETRIES)
    else:
        HR.ensure_deadline(HR.RAIN_TIMEOUT_S * 1000)
        arr = fetch(HR.RAIN_TIMEOUT_S, HR.EE_RETRIES)
    v = np.where(arr[name] == HR.NODATA, np.nan, arr[name]).astype(np.float64)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    np.save(p + ".tmp.npy", v)
    os.replace(p + ".tmp.npy", p)
    return v


def cached_rain_layer(img, name, bbox, transform, shape, crs):
    from susceptibility import hydro_rasters as HR
    if name == HR.IMERG_LAYER:
        # a 10-year half-hourly percentile per cell: a 4 deg tile timed out on Earth Engine (2026-11-23),
        # so this layer stays per unit, exactly as before
        return _ORIG["rain_layer"](img, name, bbox, transform, shape, crs)
    deg = HR.RAIN_NATIVE_DEG[name]
    x0, y1, cols, rows = HR.native_grid(HR.grid_lonlat_bounds(transform, shape, crs), deg)
    year = _STATE["year"]
    out = np.full((rows, cols), np.nan)
    c0 = int(round(x0 / deg))
    r0 = int(round(y1 / deg))                 # row index counts down from the north edge
    per = int(round(TILE_DEG / deg))
    for r in range(rows):
        for c in range(cols):
            gc, gr = c0 + c, r0 - r - 1          # global native col / row (south edge index of the cell)
            tx, ty = math.floor(gc / per), math.floor(gr / per)
            t = _rain_tile(img, name, year, tx, ty, deg)
            out[r, c] = t[(ty + 1) * per - 1 - gr, gc - tx * per]
    return HR.nearest_from_native(out, x0, y1, deg, transform, shape, crs)


def _elements_touching(els, bbox):
    from shapely.geometry import LineString, Point, box
    b = box(*bbox)
    keep = []
    for el in els:
        geoms = []
        if el.get("geometry"):
            geoms.append(el["geometry"])
        for m in el.get("members", []) or []:
            if m.get("geometry"):
                geoms.append(m["geometry"])
        for g in geoms:
            pts = [(p["lon"], p["lat"]) for p in g if p]
            if not pts:
                continue
            gg = LineString(pts) if len(pts) > 1 else Point(pts[0])
            if gg.intersects(b):
                keep.append(el)
                break
    return keep


def cached_fetch_clause(clause, bbox, cache_path, *, run=None):
    """vector.sources._fetch_clause replacement: per-tile Overpass fetch, then the unit's own selection."""
    from vector import sources as VS
    if os.path.exists(cache_path):
        return json.load(open(cache_path))
    w, s, e, n = bbox
    tiles = [(i, j) for i in range(math.floor(w / OSM_TILE_DEG), math.floor(e / OSM_TILE_DEG) + 1)
             for j in range(math.floor(s / OSM_TILE_DEG), math.floor(n / OSM_TILE_DEG) + 1)]
    seen = {}
    for i, j in tiles:
        tb = (i * OSM_TILE_DEG, j * OSM_TILE_DEG, (i + 1) * OSM_TILE_DEG, (j + 1) * OSM_TILE_DEG)
        key = hashlib.md5(clause.encode()).hexdigest()[:12]
        tp = os.path.join(CACHE, "osm", f"{key}_{i}_{j}.json")
        els = _ORIG["fetch_clause"](clause, tb, tp) if run is None else _ORIG["fetch_clause"](clause, tb, tp, run=run)
        if els is None:
            return None                         # unavailable: recorded upstream, never read as zero
        for el in els:
            seen[(el.get("type"), el.get("id"))] = el
    out = _elements_touching(list(seen.values()), bbox)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    json.dump(out, open(cache_path, "w"))
    return out


_ORIG = {}


def install():
    from experiments.flood_baselines import build as BUILD
    from susceptibility import hydro_rasters as HR
    from vector import sources as VS
    if _ORIG:
        return
    _ORIG["rain_layer"] = HR._rain_layer
    _ORIG["fetch_hydro"] = HR.fetch_hydro_rasters
    _ORIG["fetch_clause"] = VS._fetch_clause

    def fetch_hydro(bbox, transform, shape, crs, ref_year, *a, **k):
        _STATE["year"] = ref_year
        return _ORIG["fetch_hydro"](bbox, transform, shape, crs, ref_year, *a, **k)

    HR._rain_layer = cached_rain_layer
    HR.fetch_hydro_rasters = fetch_hydro
    BUILD_fetch = getattr(BUILD, "fetch_hydro_rasters", None)
    if BUILD_fetch is not None:
        BUILD.fetch_hydro_rasters = fetch_hydro
    VS._fetch_clause = cached_fetch_clause
