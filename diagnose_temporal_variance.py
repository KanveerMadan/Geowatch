from ingestion.gee_client import initialize_gee
initialize_gee()

import ee
from ingestion.temporal_variance import compute_temporal_variance

# Same AOI-building approach as the main test script.
POINTS = {
    "road_NH48_pointA": (19.050611, 72.849049),
    "mangrove_patch": (19.049166, 72.846579),
}

lats = [lat for lat, lon in POINTS.values()]
lons = [lon for lat, lon in POINTS.values()]
margin = 0.002

aoi = ee.Geometry.Rectangle([
    min(lons) - margin, min(lats) - margin,
    max(lons) + margin, max(lats) + margin,
])

result = compute_temporal_variance(aoi, year=2025)

print("composite_count per month:", result["composite_count"])
print()

monthly_list = result["monthly_collection"].toList(result["monthly_collection"].size())
n_months = monthly_list.size().getInfo()

for label, (lat, lon) in POINTS.items():
    print(f"=== {label} ({lat}, {lon}) ===")
    point = ee.Geometry.Point([lon, lat])
    for i in range(n_months):
        img = ee.Image(monthly_list.get(i))
        sample = img.select(["Blue", "Green", "NDVI"]).reduceRegion(
            reducer=ee.Reducer.first(),
            geometry=point,
            scale=10,
        ).getInfo()
        print(f"  month index {i}: {sample}")
    print()
