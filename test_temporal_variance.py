from ingestion.gee_client import initialize_gee
initialize_gee()

import ee
from ingestion.temporal_variance import compute_temporal_variance

# A single AOI covering both test points, built from their bounding box
# plus a small margin -- not hardcoded to any specific place, just sized
# to whatever two points are given below. Swap these for any other pair
# to test elsewhere.
POINTS = {
    "road_NH48_pointA": (19.050611, 72.849049),
    "road_NH48_pointB": (19.051732, 72.848193),
    "mangrove_patch": (19.049166, 72.846579),
}

lats = [lat for lat, lon in POINTS.values()]
lons = [lon for lat, lon in POINTS.values()]
margin = 0.002  # ~200m padding so the AOI comfortably contains both points

aoi = ee.Geometry.Rectangle([
    min(lons) - margin, min(lats) - margin,
    max(lons) + margin, max(lats) + margin,
])

result = compute_temporal_variance(aoi, year=2025)

print("status:", result["status"])
print("composite_count per month:", result["composite_count"])
print("date_range:", result["date_range"])
print("error:", result["error"])
print()

if result["status"] == "available":
    for label, (lat, lon) in POINTS.items():
        point = ee.Geometry.Point([lon, lat])
        sample = result["variance_image"].reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=point,
            scale=10,
        ).getInfo()
        print(f"--- {label} ({lat}, {lon}) ---")
        print("  raw stddev (indices + 6 bands):")
        for band, value in sorted(sample.items()):
            if band.endswith("_stddev"):
                print(f"    {band}: {value}")
        print("  coefficient of variation (6 raw bands only):")
        for band, value in sorted(sample.items()):
            if band.endswith("_cv"):
                print(f"    {band}: {value}")
        print()