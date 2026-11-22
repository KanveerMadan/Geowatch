"""Bounded public vector queries for a previously authorized 200 m training tile."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import tempfile
import time

import requests

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform

from generate_osm_road_masks import HIGHWAY_WIDTH_M
from ingestion.overpass import run_query
from surface_fractions.config import load_config
from surface_fractions.osm_layers import _relation_geometry, _way_geometry, build_query


def check_disk(path):
    if shutil.disk_usage(path).free < 15_000_000_000:
        raise OSError("at least 15 GB free is needed before source downloads")


def _snapshot(cache, key, fetch):
    token = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
    path = cache / (token + ".json")
    if path.exists():
        return json.loads(path.read_text())
    check_disk(cache)
    payload = fetch()
    record = {"fetched_utc": datetime.now(timezone.utc).isoformat(), **payload}
    with tempfile.NamedTemporaryFile("w", dir=cache, delete=False) as tmp:
        json.dump(record, tmp, allow_nan=False, separators=(",", ":"))
    Path(tmp.name).replace(path)
    return record


def _ee_query(bounds, kind):
    import ee
    from surface_fractions.inputs import microsoft_asset_for, microsoft_fc

    ee.Initialize(project=os.getenv("GEE_PROJECT_ID") or None)
    ee.data.setDeadline(75_000)
    geom = ee.Geometry.Rectangle(list(bounds), proj="EPSG:4326", geodesic=False)
    cfg = load_config()
    if kind == "open_buildings":
        settings = cfg["footprints"]["open_buildings"]
        asset = settings["asset"]
        col = ee.FeatureCollection(asset).filter(ee.Filter.gte("confidence", settings["min_confidence"]))
    else:
        asset, country, error = microsoft_asset_for(geom, cfg)
        if error:
            raise RuntimeError(f"Microsoft source lookup for {country or 'tile'}: {error}")
        col = microsoft_fc(asset)
    # The cap is a transport limit. A truncated source never passes as complete.
    features = col.filterBounds(geom).limit(2501).getInfo()["features"]
    if len(features) > 2500:
        raise ValueError("too many upstream footprints for this tile")
    info = ee.data.getAsset(asset)
    version = asset + ("@" + info["updateTime"] if info.get("updateTime") else "")
    return {"asset": asset, "version": version, "features": features}


def _footprint_query(bounds, name):
    # A shared OS lock serializes local Item 21 EE requests even across overlapping invocations.
    with (Path(tempfile.gettempdir()) / "geowatch-change-round2-ee.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for attempt in range(3):
            try:
                return _ee_query(bounds, name)
            except Exception as err:
                if attempt == 2 or not any(s in str(err).lower() for s in ("429", "quota", "rate limit", "503", "unavailable", "timeout", "timed out")):
                    raise
                time.sleep(4 * 2 ** attempt)


def _map_elements(raw):
    nodes = {e["id"]:{"lon":e["lon"], "lat":e["lat"]} for e in raw if e["type"] == "node"}
    ways = {e["id"]:{**e, "geometry":[nodes[n] for n in e["nodes"]]} for e in raw
            if e["type"] == "way" and all(n in nodes for n in e["nodes"])}
    elements = list(ways.values())
    skipped_relations = 0
    for e in raw:
        if e["type"] != "relation" or e.get("tags", {}).get("type") != "multipolygon":
            continue
        members = [m for m in e["members"] if m.get("role") in ("", "inner", "outer")]
        if not members or any(m["type"] != "way" or m["ref"] not in ways for m in members):
            skipped_relations += 1
            continue
        elements.append({**e, "members":[{**m, "geometry":ways[m["ref"]]["geometry"]} for m in members]})
    return elements, skipped_relations


def _osm_query(bounds):
    # OSM's small-area API serves full ways touching a bbox. Incomplete relations are never closed by guesswork.
    url = "https://api.openstreetmap.org/api/0.6/map.json"
    try:
        res = requests.get(url, params={"bbox":",".join(map(str, bounds))}, timeout=20,
                           headers={"User-Agent":"GeoWatch/1.0 (https://github.com/KanveerMadan/Geowatch)"})
        res.raise_for_status()
        elements, skipped = _map_elements(res.json()["elements"])
        return {"version":"OSM v0.6 bbox map", "elements":elements, "incomplete_relations":skipped}
    except (requests.RequestException, ValueError, KeyError):
        pass
    west, south, east, north = bounds
    filters = ['["highway"]', '["area:highway"]', '["building"]', '["amenity"="parking"]',
               '["natural"~"^(water|wood|scrub|grassland)$"]', '["waterway"="riverbank"]',
               '["landuse"~"^(reservoir|basin|grass|forest|meadow|orchard|vineyard|farmland|village_green|parking)$"]',
               '["leisure"~"^(pitch|garden|park)$"]', '["aeroway"~"^(apron|taxiway|runway)$"]']
    query = build_query(filters, dict(west=west, south=south, east=east, north=north), timeout=20)
    query = query.replace("out geom;", "out meta geom;")
    elements = run_query(query, timeout=25, max_rounds=1)
    return {"version": "OSM ways and relations", "elements": elements}


def _suggest(layer, label, source, source_id, version, geom, note, confidence=None):
    return dict(layer=layer, **{"class": label}, source=source, source_id=str(source_id),
                source_version=version, geometry=geom, note=note, confidence=confidence,
                hint_only=int(layer.startswith("hint_")), needs_check=1)


def _footprints(features, source, version, project):
    output = []
    for f in features:
        props = f.get("properties", {})
        if not f.get("geometry"):
            continue
        geom = transform(project, shape(f["geometry"]))
        ident = f.get("id") or props.get("system:index") or hashlib.sha256(geom.wkb).hexdigest()
        confidence = props.get("confidence")
        if source == "open_buildings" and (confidence is None or confidence < .7):
            continue
        output.append(_suggest("built_" + source, "built", source, ident, version, geom,
                               "Check footprint, roof displacement and acquisition date against the tile.",
                               confidence if source == "open_buildings" else None))
    return output


UNSEALED = {"dirt", "earth", "sand", "gravel", "fine_gravel", "unpaved", "ground", "compacted",
            "grass", "mud", "pebblestone", "woodchips", "clay"}
SEALED = {"asphalt", "paved", "concrete", "concrete:plates", "concrete:lanes", "paving_stones",
          "sett", "cobblestone", "metal", "unhewn_cobblestone"}


def _road_width(tags):
    text = str(tags.get("width", "")).strip().lower()
    width = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(m|ft|')?", text)
    if width:
        metres = float(width[1]) * (.3048 if width[2] in ("ft", "'") else 1)
        if 0 < metres <= 75:
            return metres, "tagged width"
    highway = tags.get("highway", "").removesuffix("_link")
    return HIGHWAY_WIDTH_M.get(highway, 5), "estimated width for " + highway


def _osm_features(elements, project):
    out = []
    for e in elements:
        tags = e.get("tags", {})
        geometry = _relation_geometry(e) if e["type"] == "relation" else _way_geometry(e, "area_or_line")
        if not geometry:
            continue
        kind, geo = geometry
        g = transform(project, geo)
        highway = tags.get("highway", "")
        area = kind == "area"
        surface = tags.get("surface", "")
        osm_id = f"{e['type']}/{e['id']}"
        version = "OSM v{} {}".format(e.get("version", "?"), e.get("timestamp", "snapshot"))
        def add(layer, label, geom, note):
            out.append(_suggest(layer, label, "osm", osm_id, version, geom, note))
        if area and tags.get("building") not in (None, "no", "demolished", "destroyed", "construction"):
            add("built_osm", "built", g, "Mapped building; check roof and date against imagery.")
        if area and (tags.get("natural") == "water" or tags.get("waterway") == "riverbank" or
                     tags.get("landuse") == "reservoir"):
            add("water_osm", "water", g, "Water boundary can change seasonally; inspect imagery.")
        if area and (tags.get("natural") in {"wood", "scrub", "grassland"} or
                     tags.get("landuse") in {"grass", "forest", "meadow", "orchard", "vineyard", "farmland", "village_green"} or
                     tags.get("leisure") in {"park", "garden"}):
            add("hint_vegetation_osm", "vegetation", g, "Land use only; inspect actual cover.")
        if surface in UNSEALED or tags.get("tunnel") not in (None, "no") or tags.get("covered") == "yes":
            continue
        if tags.get("parking") in {"underground", "multi-storey", "rooftop"}:
            continue
        if area and (tags.get("area:highway") not in (None, "no") or tags.get("amenity") == "parking" or
                     tags.get("landuse") == "parking" or tags.get("aeroway") == "apron" or
                     (highway and tags.get("area") == "yes") or (tags.get("leisure") == "pitch" and surface in SEALED)):
            add("paved_osm", "paved", g, "Area outline only. Check for dirt, roof cover, trees and vehicles.")
        elif highway and highway.removesuffix("_link") in HIGHWAY_WIDTH_M and tags.get("area") != "yes":
            if highway in {"path", "footway", "track", "bridleway"} and surface not in SEALED:
                continue
            if area and e["type"] == "relation":
                continue
            line = g.boundary if area else g  # a closed centreline can be a roundabout
            width, basis = _road_width(tags)
            add("paved_osm", "paved", line.buffer(width / 2, cap_style="flat"),
                f"Check sealing and edges against image; {basis}: {width:g} m.")
    return out


def vector_sources(bounds, crs, cache):
    """Query footprints and OSM serially. Receipts distinguish empty coverage from source errors."""
    project = Transformer.from_crs(4326, crs, always_xy=True).transform
    output, receipts = [], {}
    for source in ("open_buildings", "microsoft", "osm"):
        key = ["tile-vector-v1" if source != "osm" else "tile-map-v2", list(bounds), source]
        try:
            snapshot = _snapshot(cache, key, lambda: _osm_query(bounds) if source == "osm" else _footprint_query(bounds, source))
            if source == "osm":
                features = _osm_features(snapshot["elements"], project)
                raw_count = len(snapshot["elements"])
            else:
                features = _footprints(snapshot["features"], source, snapshot["version"], project)
                raw_count = len(snapshot["features"])
            output.extend(features)
            receipts[source] = dict(status="available" if raw_count else "empty_in_query",
                                    source_objects=raw_count, version=snapshot["version"], fetched_utc=snapshot["fetched_utc"])
            if source == "osm":
                receipts[source]["incomplete_relations"] = snapshot.get("incomplete_relations",0)
        except OSError as err:
            if "15 GB" in str(err):
                raise
            receipts[source] = dict(status="unavailable", error=f"{type(err).__name__}: {err}"[:800])
        except Exception as err:
            receipts[source] = dict(status="unavailable", error=f"{type(err).__name__}: {err}"[:800])
    return output, receipts
