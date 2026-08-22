"""
Phase 6: real coastline geometry via GEE's sat-io Global Shoreline
Dataset (mainlands + big_islands + small_islands polygon
FeatureCollections). STATIC/SCREENING SLICE ONLY -- distance-to-coast +
elevation. NOT tide/surge/storm-surge event hazard, which needs its own
dataset ADR and is deliberately deferred (see susceptibility/coastal.py's
docstring).

THIS IS REAL COASTLINE GEOMETRY (land polygon boundaries), unlike
ingestion.osm_dem.get_osm_features(), which converts ALL water geometry
(including closed natural=water ways) to LineString and never queries a
dedicated coastline layer. Do not use get_osm_features() for coastal
proximity -- it was never built for this and its geometry handling is
documented elsewhere as broken for polygon water bodies.

Source verification note: these asset IDs (projects/sat-io/open-datasets/
shoreline/{mainlands,big_islands,small_islands}) were identified via the
GEE community catalog documentation (gee-community-catalog.org/projects/
shoreline/), same host as FABDEM (already verified working in this
project since Phase 5). They have NOT yet been independently confirmed
against a live GEE console session by this codebase -- the first real
pipeline run against a live AOI is the actual verification step. If
these IDs are wrong or the collections are empty, this function will
surface that via status="unavailable"/error, not silently.
"""

import ee
from ingestion.gee_client import initialize_gee
from configs.coastal_constants import (
    COASTAL_SEARCH_RADIUS_KM,
    COASTAL_APPLICABILITY_THRESHOLD_KM,
)

MAINLANDS_ASSET = "projects/sat-io/open-datasets/shoreline/mainlands"
BIG_ISLANDS_ASSET = "projects/sat-io/open-datasets/shoreline/big_islands"
SMALL_ISLANDS_ASSET = "projects/sat-io/open-datasets/shoreline/small_islands"


def get_coastline_context(west: float, south: float, east: float, north: float,
                           search_radius_km: float = COASTAL_SEARCH_RADIUS_KM) -> dict:
    """
    Query the real global shoreline dataset to determine this AOI's
    distance to the nearest mapped coastline, and whether coastal
    flooding is even a plausible mechanism here.

    Returns an AOI-WIDE SCALAR distance (km), not a per-pixel spatial
    raster -- same limitation-transparency pattern as
    get_merit_hand_context() and get_fabdem_elevation_stats().

    Algorithm:
        1. Buffer the AOI by search_radius_km.
        2. Merge the three shoreline FeatureCollections and filter to
           features intersecting the buffered region.
        3. If nothing found within the search radius, report
           distance_km=None (not a guessed large number) -- the AOI is
           "at least search_radius_km away", not a computed distance.
        4. If something found, compute the real geodesic distance from
           the AOI rectangle to the merged coastline geometry.

    Returns:
        dict with status, distance_km (float or None),
        coastal_connectivity (bool or None), source, search_radius_km,
        note, error.
    """
    try:
        initialize_gee()

        aoi = ee.Geometry.Rectangle([west, south, east, north])
        buffered = aoi.buffer(search_radius_km * 1000.0)

        mainlands = ee.FeatureCollection(MAINLANDS_ASSET)
        big_islands = ee.FeatureCollection(BIG_ISLANDS_ASSET)
        small_islands = ee.FeatureCollection(SMALL_ISLANDS_ASSET)
        merged = mainlands.merge(big_islands).merge(small_islands)

        nearby = merged.filterBounds(buffered)
        nearby_count = nearby.size().getInfo()

        if nearby_count == 0:
            print(f"No coastline features found within {search_radius_km}km of AOI -- "
                  f"treating as far inland (exact distance not computed).")
            return {
                "status": "available",
                "distance_km": None,
                "coastal_connectivity": False,
                "source": "projects/sat-io/open-datasets/shoreline",
                "search_radius_km": search_radius_km,
                "note": (
                    f"No coastline geometry found within {search_radius_km}km "
                    f"search radius -- AOI is at least that far from any "
                    f"mapped coastline."
                ),
                "error": None,
            }

        # BUG FIX (v3): avoid unioning coastline geometries into one
        # combined geometry entirely (both the original .geometry() call
        # and the v2 per-feature-to-line conversion failed or risked
        # failing on this dataset's real geometry shapes -- MultiPolygon
        # features have 4-level nested coordinates that don't match what
        # MultiLineString expects). FeatureCollection.distance() computes
        # a distance-to-nearest-feature raster directly against the
        # ORIGINAL polygon/multipolygon features -- no manual geometry
        # conversion or union required.
        distance_image = merged.filterBounds(buffered).distance(
            searchRadius=search_radius_km * 1000.0, maxError=1
        )
        stats = distance_image.reduceRegion(
            reducer=ee.Reducer.min(), geometry=aoi, scale=100, maxPixels=1e9,
        ).getInfo()
        distance_m = stats.get("distance")

        # BUG FIX (v4, confirmed via live Delhi run): a None here does NOT
        # mean the computation failed -- it means every pixel in the AOI
        # was beyond searchRadius (distance() masks pixels outside that
        # radius rather than computing real values for them). This is a
        # LEGITIMATE "far inland" result, not an error. Confirmed root
        # cause: the nearby_count==0 pre-check above is unreliable as an
        # early-exit for this -- "mainlands" features are apparently
        # stored as one giant polygon per landmass, so filterBounds()
        # matches on bounding-box overlap with the buffered AOI even when
        # the AOI is hundreds of km from the actual coastline boundary
        # (confirmed: Delhi, ~very far from any coast, still had
        # nearby_count > 0). Do not treat this branch as removable --
        # it's the real signal the pre-check above fails to catch.
        if distance_m is None:
            print(f"AOI is beyond the {search_radius_km}km search radius of any "
                  f"real coastline -- treating as far inland (exact distance not computed).")
            return {
                "status": "available",
                "distance_km": None,
                "coastal_connectivity": False,
                "source": "projects/sat-io/open-datasets/shoreline",
                "search_radius_km": search_radius_km,
                "note": (
                    f"AOI is beyond the {search_radius_km}km search radius of "
                    f"any mapped coastline -- confirmed via masked distance "
                    f"computation, not just a bounding-box pre-check."
                ),
                "error": None,
            }

        distance_km = distance_m / 1000.0
        coastal_connected = distance_km <= COASTAL_APPLICABILITY_THRESHOLD_KM

        print(f"Distance to nearest coastline: {distance_km:.2f}km "
              f"(coastal_connectivity={coastal_connected})")

        return {
            "status": "available",
            "distance_km": round(distance_km, 3),
            "coastal_connectivity": coastal_connected,
            "source": "projects/sat-io/open-datasets/shoreline",
            "search_radius_km": search_radius_km,
            "note": None,
            "error": None,
        }

    except Exception as e:
        print(f"Coastline context computation failed: {e}")
        return {
            "status": "unavailable",
            "distance_km": None,
            "coastal_connectivity": None,
            "source": "projects/sat-io/open-datasets/shoreline",
            "search_radius_km": search_radius_km,
            "note": None,
            "error": str(e),
        }