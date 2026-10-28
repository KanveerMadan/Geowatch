"""
Pluvial's drainage-distance input: distance to the nearest OSM waterway, on
the hydrology grid (UTM), normalised to [0, 1] by its maximum -- the same
semantics as ingestion.osm_dem.compute_waterway_distance_map, which works on
the legacy EPSG:4326 bbox grid.

Fetched through the shared C44 Overpass client and vector.sources' per-clause
cache, so an unretrievable clause is recorded, never read as "no waterways".
"""
from __future__ import annotations

import os

import numpy as np

WATERWAY_CLAUSES = {"waterway": 'way["waterway"]', "natural_water": 'way["natural"="water"]'}


def fetch_waterways(name: str, bbox) -> dict:
    """{"ways": [...], "unavailable": [clause, ...]}"""
    from vector.sources import CACHE_DIR, _fetch_clause, bbox_key
    key = bbox_key(name, bbox)
    ways, unavailable = {}, []
    for group, clause in WATERWAY_CLAUSES.items():
        path = os.path.join(CACHE_DIR, "osm", f"{key}__water_{group}.json")
        els = _fetch_clause(clause, bbox, path)
        if els is None:
            unavailable.append(group)
            continue
        for el in els:
            if el.get("type") == "way" and el.get("geometry"):
                ways[el["id"]] = el
    return {"ways": list(ways.values()), "unavailable": unavailable}


def distance_map(ways: list, crs, transform, shape):
    """Normalised distance to the nearest waterway cell, or None when no
    waterway touches the grid (no drainage input, not "far from drainage")."""
    import pyproj
    from rasterio.features import rasterize
    from scipy.ndimage import distance_transform_edt
    from shapely.geometry import LineString, mapping
    from shapely.ops import transform as shp_transform
    to_utm = pyproj.Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    lines = []
    for el in ways:
        coords = [(p["lon"], p["lat"]) for p in el["geometry"] if p]
        if len(coords) >= 2:
            lines.append(shp_transform(to_utm, LineString(coords)))
    if not lines:
        return None
    mask = rasterize(((mapping(g), 1) for g in lines), out_shape=shape, transform=transform,
                     fill=0, all_touched=True, dtype="uint8")
    if not mask.any():
        return None
    d = distance_transform_edt(1 - mask).astype(np.float32)
    m = d.max()
    return d / m if m > 0 else d
