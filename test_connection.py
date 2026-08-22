import ee
from ingestion.gee_client import initialize_gee
from ingestion.sentinel2 import aoi_from_bbox, get_best_image

# Initialize
initialize_gee()

# Test AOI — Dharavi, Mumbai
aoi = aoi_from_bbox(72.836, 19.037, 72.862, 19.060)

# Fetch image
image = get_best_image(aoi, "2024-01-01", "2024-03-31")

# Print band names to confirm it worked
print("Band names:", image.bandNames().getInfo())
print("✅ Sentinel-2 ingestion pipeline working.")