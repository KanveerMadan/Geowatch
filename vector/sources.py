"""
Raw inputs to the vector layer (item 19): OSM highways, and building
footprints from Open Buildings or OSM.

OSM is fetched through the shared C44 client (`ingestion.overpass.run_query`),
following generate_osm_road_masks.py's `way["highway"]` query. The fetch is
split into disjoint per-tag clauses and cached per clause, the pattern
diagnose_pure_pixels_paved.py established: a combined multi-clause query 504s
on overpass-api.de, and a per-clause cache lets a throttled run resume rather
than restart. That script fetches clauses sequentially; here a small thread
pool (OVERPASS_WORKERS = 2, deliberately low for a shared public endpoint)
runs them concurrently.

A clause that cannot be retrieved is recorded as unavailable and is NEVER
treated as zero ways. "Not retrieved" and "none exist" are different claims.
"""
from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor

from ingestion.overpass import (
    OverpassError, OverpassQueryError, OverpassQueryTooHeavy, run_query,
)

CACHE_DIR = os.path.join("cache", "vector")
OVERPASS_WORKERS = 2

_ARTERIAL_RE = "motorway|trunk|primary|secondary|tertiary"
_NAMED = ("motorway|trunk|primary|secondary|tertiary|motorway_link|trunk_link|"
          "primary_link|secondary_link|tertiary_link|residential|service|"
          "footway|path|pedestrian|steps")

# A partition of highway=*: every highway way matches exactly one clause.
# tests/test_vector_roads.py checks the partition is exhaustive and disjoint.
HIGHWAY_CLAUSES = {
    "arterial": f'way["highway"~"^({_ARTERIAL_RE})(_link)?$"]',
    "residential": 'way["highway"="residential"]',
    "service": 'way["highway"="service"]',
    "narrow_pedestrian": 'way["highway"~"^(footway|path|pedestrian|steps)$"]',
    "other": f'way["highway"]["highway"!~"^({_NAMED})$"]',
}

BUILDING_CLAUSE = 'way["building"]'


def bbox_key(name: str, bbox) -> str:
    """Cache key bound to the exact box, so a changed AOI cannot reuse a
    stale cache under the same name."""
    digest = hashlib.sha1(json.dumps([round(v, 6) for v in bbox]).encode()).hexdigest()[:10]
    return f"{name}_{digest}"


def _overpass_bbox(bbox) -> str:
    w, s, e, n = bbox
    return f"({s},{w},{n},{e})"


# A clause that hits Overpass's own query limit is retried on the four
# quarters of its box, down to this depth (a 121 km^2 AOI -> ~1.9 km^2 at 3).
MAX_SPLIT_DEPTH = 3


def _query_split(clause: str, bbox, run, depth: int = 0) -> list:
    query = f"[out:json][timeout:120];{clause}{_overpass_bbox(bbox)};out geom;"
    try:
        return run(query)
    except OverpassQueryTooHeavy:
        # The one failure a smaller box actually fixes (ingestion/overpass.py).
        if depth >= MAX_SPLIT_DEPTH:
            raise
        w, s, e, n = bbox
        mx, my = (w + e) / 2, (s + n) / 2
        seen = {}
        for q in ((w, s, mx, my), (mx, s, e, my), (w, my, mx, n), (mx, my, e, n)):
            for el in _query_split(clause, q, run, depth + 1):
                seen[(el.get("type"), el.get("id"))] = el   # ways crossing quarters
        return list(seen.values())


def _fetch_clause(clause: str, bbox, cache_path: str, *, run=run_query):
    """One clause, cached. Returns the element list, or None when every
    endpoint failed (recorded, never read as zero)."""
    if os.path.exists(cache_path):
        with open(cache_path) as fh:
            return json.load(fh)
    try:
        elements = _query_split(clause, bbox, run)
    except (OverpassQueryError, OverpassQueryTooHeavy):
        # The query is at fault, not the network: fail loudly.
        raise
    except OverpassError as e:
        print(f"    {clause}: UNAVAILABLE -- {e}")
        return None
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as fh:
        json.dump(elements, fh)
    return elements


def fetch_osm_highways(name: str, bbox, *, run=run_query) -> dict:
    """All highway=* ways intersecting `bbox`.

    Returns {"ways": [...deduped by id...], "clauses": {group: n or None},
    "unavailable": [group, ...]}. Ways carry `nodes` (OSM node ids) and
    `geometry`, because `out geom` includes both, and the network
    representation needs real shared-node topology.
    """
    key = bbox_key(name, bbox)

    def one(item):
        group, clause = item
        path = os.path.join(CACHE_DIR, "osm", f"{key}__highway_{group}.json")
        return group, _fetch_clause(clause, bbox, path, run=run)

    with ThreadPoolExecutor(max_workers=OVERPASS_WORKERS) as pool:
        results = list(pool.map(one, HIGHWAY_CLAUSES.items()))

    seen, counts, unavailable = {}, {}, []
    for group, elements in results:
        if elements is None:
            counts[group] = None
            unavailable.append(group)
            continue
        counts[group] = len(elements)
        for el in elements:
            if el.get("type") == "way" and el.get("geometry"):
                seen[el["id"]] = el
    return {"ways": list(seen.values()), "clauses": counts, "unavailable": unavailable}


def fetch_osm_buildings(name: str, bbox, *, run=run_query) -> dict:
    """OSM building ways (closed rings). Multipolygon relations are NOT
    fetched, so courtyard blocks mapped as relations are missed; this is a
    stated limitation, used only where Open Buildings has no coverage."""
    key = bbox_key(name, bbox)
    path = os.path.join(CACHE_DIR, "osm", f"{key}__building.json")
    elements = _fetch_clause(BUILDING_CLAUSE, bbox, path, run=run)
    if elements is None:
        return {"buildings": None, "unavailable": True}
    rings = []
    for el in elements:
        geom = el.get("geometry") or []
        coords = [(p["lon"], p["lat"]) for p in geom]
        if len(coords) >= 4 and coords[0] == coords[-1]:
            rings.append({"id": el["id"], "coords": coords})
    return {"buildings": rings, "unavailable": False}


OPEN_BUILDINGS_ASSET = "GOOGLE/Research/open-buildings/v3/polygons"


def fetch_open_buildings(name: str, bbox):
    """Open Buildings v3 polygons intersecting `bbox`, as a GeoDataFrame in
    EPSG:4326 (columns: geometry, confidence, area_in_meters). Cached as
    GeoJSON. Raises on any Earth Engine error (items 54/55 convention)."""
    import geopandas as gpd

    key = bbox_key(name, bbox)
    path = os.path.join(CACHE_DIR, "open_buildings", f"{key}.geojson")
    if os.path.exists(path):
        return gpd.read_file(path)

    import ee
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    fc = (ee.FeatureCollection(OPEN_BUILDINGS_ASSET)
          .filterBounds(ee.Geometry.Rectangle(list(bbox)))
          .select(["confidence", "area_in_meters"]))
    gdf = ee.data.computeFeatures({"expression": fc,
                                   "fileFormat": "GEOPANDAS_GEODATAFRAME"})
    gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    gdf.to_file(path, driver="GeoJSON")
    return gdf


def count_open_buildings(bbox) -> int:
    """Server-side polygon count. Used to choose the footprint source and,
    for item 20, where only the count is needed and downloading 100k
    polygons would be waste."""
    import ee
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    return (ee.FeatureCollection(OPEN_BUILDINGS_ASSET)
            .filterBounds(ee.Geometry.Rectangle(list(bbox))).size().getInfo())
