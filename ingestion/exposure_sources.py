"""
Phase 10A: raw exposure data sources -- population (WorldPop), built-up
reference (GHSL, fallback/cross-check only), and OSM road-length /
facility fetch.

This module ONLY fetches and prepares raw evidence. It does NOT
intersect anything with a hazard mask, and it does NOT compute
exposure -- that's exposure/compute.py's job (per Document 1's file-
structure simplification). Keeping ingestion and computation separate
avoids the confusion this project already fixed once (Sentinel-2
median-composite fetch vs. tiling vs. inference, all deliberately split
across separate files).

CRITICAL SEMANTIC NOTE (WorldPop): each pixel is a MODELED ESTIMATED
POPULATION COUNT for that ~93m cell, NOT a density. Exposure computation
must therefore SUM population values over intersecting pixels, never
average-then-multiply-by-area. See exposure/compute.py.
"""

import ee
from ingestion.gee_client import initialize_gee
from configs.exposure_constants import (
    WORLDPOP_COLLECTION_ID, WORLDPOP_COUNTRY_PROPERTY, WORLDPOP_BAND,
    WORLDPOP_NOMINAL_SCALE_M, GHSL_BUILTUP_ASSET, GHSL_RESOLUTION_M,
)


def get_population_context(west: float, south: float, east: float, north: float,
                            country_iso3: str = None) -> dict:
    """
    Fetch the most recent available WorldPop image for the AOI's country
    (or globally if country_iso3 is not supplied -- see note below), and
    return it as a GEE image reference plus metadata. Does NOT sum
    population yet -- callers do that via reduceRegion against their own
    hazard/evidence mask geometry (exposure/compute.py).

    IMPORTANT: WorldPop's collection is organized per-country per-year,
    not as one global mosaic. If country_iso3 is not supplied, this
    function will attempt to filter by bounds only, which may return
    multiple overlapping country images near borders -- always pass
    country_iso3 when known (e.g. "IND" for all current test AOIs) to
    get an unambiguous single image.

    Confirmed live 2026-07-31: country property key is `country` (not
    ISO3/iso3/country_code -- those all returned empty). Years available:
    2000-2020. NO DATA EXISTS PAST 2020 -- population_year will reflect
    this real gap, not a guess.

    Returns:
        dict with status, image (ee.Image or None), population_year,
        source, band, native_resolution_m, error, limitations.
    """
    limitations = [
        "Population is a MODELED ESTIMATE, not a household census.",
        "Population data caps at year 2020 -- no fresher WorldPop release "
        "exists as of this verification. Any exposure figure computed from "
        "this source describes an estimated 2020 population overlaid on "
        "current imagery/hazard evidence, not a current population count.",
        f"Native resolution is ~{WORLDPOP_NOMINAL_SCALE_M:.1f}m, not the "
        "10m of the land-cover model -- population estimates are "
        "necessarily coarser than the classified land-cover map.",
    ]
    try:
        initialize_gee()
        aoi = ee.Geometry.Rectangle([west, south, east, north])
        collection = ee.ImageCollection(WORLDPOP_COLLECTION_ID).filterBounds(aoi)

        if country_iso3:
            collection = collection.filter(ee.Filter.eq(WORLDPOP_COUNTRY_PROPERTY, country_iso3))

        count = collection.size().getInfo()
        if count == 0:
            return {
                "status": "unavailable",
                "image": None,
                "population_year": None,
                "source": WORLDPOP_COLLECTION_ID,
                "band": WORLDPOP_BAND,
                "native_resolution_m": WORLDPOP_NOMINAL_SCALE_M,
                "country_iso3_used": country_iso3,
                "limitations": limitations,
                "error": (
                    f"No WorldPop images found for this AOI"
                    + (f" and country={country_iso3}" if country_iso3 else "")
                    + "."
                ),
            }

        latest_year = ee.Number(collection.aggregate_max("year")).getInfo()
        latest_image = ee.Image(
            collection.filter(ee.Filter.eq("year", latest_year)).first()
        ).select(WORLDPOP_BAND)

        print(f"WorldPop: using year={latest_year}"
              + (f", country={country_iso3}" if country_iso3 else " (bounds-filtered only)"))

        return {
            "status": "available",
            "image": latest_image,
            "population_year": int(latest_year),
            "source": WORLDPOP_COLLECTION_ID,
            "band": WORLDPOP_BAND,
            "native_resolution_m": WORLDPOP_NOMINAL_SCALE_M,
            "country_iso3_used": country_iso3,
            "limitations": limitations,
            "error": None,
        }

    except Exception as e:
        print(f"WorldPop population context fetch failed: {e}")
        return {
            "status": "unavailable",
            "image": None,
            "population_year": None,
            "source": WORLDPOP_COLLECTION_ID,
            "band": WORLDPOP_BAND,
            "native_resolution_m": WORLDPOP_NOMINAL_SCALE_M,
            "country_iso3_used": country_iso3,
            "limitations": limitations,
            "error": str(e),
        }


def get_builtup_reference(west: float, south: float, east: float, north: float) -> dict:
    """
    GHSL built-up reference -- a global fallback/cross-check for built-up
    area, independent of GeoWatch's own 7-class land-cover model (per
    Document 1's correction: do not rely solely on a model with a known
    unresolved paved_road/roofing confusion and no training exposure to
    many global scene types).

    WARNING: GHSL_BUILTUP_ASSET has NOT been live-verified against a real
    GEE session -- unlike WorldPop, MERIT Hydro, FABDEM, and the
    shoreline dataset, which were each checked before trusting them. This
    function will surface any asset-ID/band-mismatch error via
    status=unavailable, not silently. VERIFY THIS ASSET LIVE before
    relying on its output in any real exposure computation -- treat a
    successful call as provisional confirmation only, not full trust.

    Returns:
        dict with status, image (or None), source, resolution_m,
        error, limitations.
    """
    limitations = [
        "UNVERIFIED DATASET -- this asset ID has not yet been confirmed "
        "live against a real GEE session the way MERIT Hydro/FABDEM/"
        "shoreline data were. Treat any successful result with caution "
        "until independently re-checked.",
        "This is a GLOBAL REFERENCE product, independent of GeoWatch's "
        "own classifier -- used for cross-check/fallback, not as the "
        "sole source of built-up area truth.",
        f"Native resolution ~{GHSL_RESOLUTION_M}m -- coarser than the "
        "10m land-cover model.",
    ]
    try:
        initialize_gee()
        aoi = ee.Geometry.Rectangle([west, south, east, north])

        image = ee.Image(GHSL_BUILTUP_ASSET).clip(aoi)

        return {
            "status": "available",
            "image": image,
            "source": GHSL_BUILTUP_ASSET,
            "resolution_m": GHSL_RESOLUTION_M,
            "limitations": limitations,
            "error": None,
        }

    except Exception as e:
        print(f"GHSL built-up reference fetch failed: {e}")
        return {
            "status": "unavailable",
            "image": None,
            "source": GHSL_BUILTUP_ASSET,
            "resolution_m": GHSL_RESOLUTION_M,
            "limitations": limitations,
            "error": str(e),
        }


def get_osm_road_length(roads_gdf) -> dict:
    """
    Compute total OSM road length (km) from an already-fetched roads
    GeoDataFrame (the same object returned by
    ingestion.osm_dem.get_osm_features()["roads"] -- NOT a new Overpass
    query, reuses what the main pipeline already fetched).

    Per Document 1's correction: use real OSM vector geometry for road
    exposure, NOT the model's paved_road classification (which has a
    known, unresolved confusion with roofing).

    Returns:
        dict with status, total_length_km, segment_count, by_highway_type,
        osm_completeness (always "unknown" -- OSM coverage is never
        assumed complete), error.
    """
    if roads_gdf is None or (hasattr(roads_gdf, "empty") and roads_gdf.empty):
        return {
            "status": "unavailable",
            "total_length_km": None,
            "segment_count": 0,
            "by_highway_type": {},
            "osm_completeness": "unknown",
            "error": "No OSM road data available for this AOI (Overpass fetch "
                     "failed or returned zero roads).",
        }

    try:
        # Reproject to a metric CRS for real length calculation --
        # EPSG:4326 degrees are not directly usable as length. Use an
        # equal-area-ish approximation via GeoPandas' built-in geodesic
        # length support (to_crs to a local UTM-like metric CRS via
        # estimate_utm_crs(), same general idea as the rest of this
        # project using pyproj.Geod for geodesic calculations in api.py).
        metric_gdf = roads_gdf.to_crs(roads_gdf.estimate_utm_crs())
        lengths_km = metric_gdf.geometry.length / 1000.0
        total_length_km = float(lengths_km.sum())

        by_type = {}
        if "highway" in roads_gdf.columns:
            for highway_type, group_lengths in lengths_km.groupby(roads_gdf["highway"]):
                by_type[str(highway_type)] = round(float(group_lengths.sum()), 3)

        print(f"OSM road length: {total_length_km:.2f}km total across "
              f"{len(roads_gdf)} segments")

        return {
            "status": "available",
            "total_length_km": round(total_length_km, 3),
            "segment_count": len(roads_gdf),
            "by_highway_type": by_type,
            "osm_completeness": "unknown",
            "error": None,
        }

    except Exception as e:
        print(f"OSM road length computation failed: {e}")
        return {
            "status": "unavailable",
            "total_length_km": None,
            "segment_count": 0,
            "by_highway_type": {},
            "osm_completeness": "unknown",
            "error": str(e),
        }


def get_osm_facilities(west: float, south: float, east: float, north: float,
                        output_dir: str = "data/raw") -> dict:
    """
    Fetch OSM point/polygon facilities (hospitals, clinics, schools) via
    a SEPARATE Overpass query from get_osm_features() in osm_dem.py --
    that function only fetches roads/waterways as LineStrings, has no
    concept of point/polygon amenity features, and is deliberately NOT
    modified here to avoid touching working, already-tested code.

    Per Document 1's guidance: start small (hospitals, clinics, schools
    only) for the first version -- do not claim these facilities are
    "non-functional" or "disrupted" from mere intersection with a hazard
    layer; that is exposure context, not service-disruption proof.

    RELIABILITY FIX (2026-08-01): this originally made a single Overpass
    request with no retry/fallback, unlike get_osm_features() in
    osm_dem.py. Confirmed live: this exact query failed with a 504
    Gateway Timeout on 2 of 3 real runs against the same AOI (roads/
    waterways succeeded via retry both times). Now mirrors
    get_osm_features()'s proven multi-endpoint + exponential-backoff
    pattern instead of inventing new retry logic.

    Returns:
        dict with status, facilities (list of dicts: name, type, lon,
        lat), osm_completeness ("unknown"), error.
    """
    import requests
    import time
    import os as _os
    import json as _json

    _os.makedirs(output_dir, exist_ok=True)

    query = (
        "[out:json][timeout:60];"
        "("
        "node[\"amenity\"~\"^(hospital|clinic|school)$\"]({s},{w},{n},{e});"
        "way[\"amenity\"~\"^(hospital|clinic|school)$\"]({s},{w},{n},{e});"
        ");out center;"
    ).format(s=south, w=west, n=north, e=east)

    ENDPOINTS = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]

    from ingestion.contact import contact_user_agent

    # Resolved BEFORE the retry loop, whose `except Exception` would swallow it.
    user_agent = contact_user_agent()
    data = None
    for endpoint in ENDPOINTS:
        for attempt in range(3):
            try:
                wait = 2 ** attempt
                if attempt > 0:
                    print(f"Retrying facilities query in {wait}s (attempt {attempt + 1}/3)...")
                    time.sleep(wait)
                print(f"Querying Overpass API for facilities ({endpoint})...")
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    headers={
                        "User-Agent": user_agent,
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    timeout=60,
                )
                response.raise_for_status()
                data = response.json()
                print(f"Facilities query succeeded via {endpoint}.")
                break
            except Exception as e:
                print(f"Facilities attempt {attempt + 1} failed ({endpoint}): {e}")

        if data is not None:
            break
        print(f"All attempts failed for {endpoint}, trying next endpoint...")
        time.sleep(5)

    if data is None:
        print("All Overpass endpoints failed for facilities query. Facilities unavailable for this run.")
        return {
            "status": "unavailable",
            "facilities": [],
            "osm_completeness": "unknown",
            "error": "All Overpass endpoints failed after retries.",
        }

    facilities = []
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        if "lat" in element and "lon" in element:
            lat, lon = element["lat"], element["lon"]
        elif "center" in element:
            lat, lon = element["center"]["lat"], element["center"]["lon"]
        else:
            continue
        facilities.append({
            "type": tags.get("amenity"),
            "name": tags.get("name", "unnamed"),
            "lat": lat,
            "lon": lon,
            "source": "OpenStreetMap",
        })

    output_path = _os.path.join(output_dir, "facilities.json")
    with open(output_path, "w") as f:
        _json.dump(facilities, f, indent=2)
    print(f"OSM facilities: {len(facilities)} found (hospitals/clinics/schools). "
          f"Saved: {output_path}")

    return {
        "status": "available",
        "facilities": facilities,
        "osm_completeness": "unknown",
        "error": None,
    }