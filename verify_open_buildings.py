"""
Verification script for Google Open Buildings, following the same
discipline as verify_ghsl.py and the WorldPop scale-bug investigation
in configs/exposure_constants.py -- confirm live, record exact findings,
do not trust assumptions from prior documentation until checked against
the real asset.

Per 03_EVIDENCE.md Part C.2: Open Buildings has NO road layer (confirmed
there). This script checks the BUILDING data specifically, which is
what Decision 13 actually needs -- footprint polygons to constrain the
`built` endmember extraction pixel pool.

Known from evidence base, to be CONFIRMED not assumed:
  - Dual licensed CC BY 4.0 / ODbL v1.0
  - 1.8B detections, 58M km2
  - Temporal v1: 4m effective resolution, annual 2016-2023, DERIVED FROM
    SENTINEL-2 (a real caveat -- using it to constrain a Sentinel-2
    unmixing solve adds a strong inductive prior, not independent info)
  - GOOGLE/Research/open-buildings namespace has v1/v2/v3, each with
    `polygons` and `polygons_FeatureView` -- FEATURE COLLECTIONS, not
    images, per prior listAssets enumeration in the evidence base.
    CONFIRM this is still true rather than assuming it hasn't changed.
"""

from ingestion.gee_client import initialize_gee
initialize_gee()

import ee

# Dharavi AOI, same test point used throughout item 18 -- convenient to
# reuse a known-good AOI rather than introducing a new unverified one.
DHARAVI_AOI = ee.Geometry.Rectangle([72.85, 19.03, 72.87, 19.05])

# Candidate asset paths -- v3 is likely the newest/best but confirm
# what's actually queryable before assuming.
CANDIDATE_ASSETS = [
    "GOOGLE/Research/open-buildings/v3/polygons",
    "GOOGLE/Research/open-buildings/v2/polygons",
    "GOOGLE/Research/open-buildings/v1/polygons",
]

for asset_id in CANDIDATE_ASSETS:
    print(f"\n=== {asset_id} ===")
    try:
        fc = ee.FeatureCollection(asset_id).filterBounds(DHARAVI_AOI)
        count = fc.size().getInfo()
        print(f"  status: LOADS OK")
        print(f"  building count in Dharavi AOI: {count}")

        if count > 0:
            first = fc.first()
            props = first.propertyNames().getInfo()
            print(f"  property names: {props}")

            first_info = first.getInfo()
            print(f"  sample feature properties: {first_info.get('properties')}")
            geom_type = first_info.get("geometry", {}).get("type")
            print(f"  geometry type: {geom_type}")

    except Exception as e:
        print(f"  status: FAILED")
        print(f"  error: {e}")
