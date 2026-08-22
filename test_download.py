from ingestion.gee_client import initialize_gee
from ingestion.sentinel2 import aoi_from_bbox, get_best_image
from ingestion.tiler import export_image_local, generate_tiles

initialize_gee()

# Dharavi AOI
aoi = aoi_from_bbox(72.836, 19.037, 72.862, 19.060)

# Get image
image = get_best_image(aoi, "2024-01-01", "2024-03-31")

# Download locally
export_image_local(
    image=image,
    aoi=aoi,
    output_path="data/raw/dharavi_test.tif",
    scale=10
)

# Generate tiles
tiles = generate_tiles(
    image_path="data/raw/dharavi_test.tif",
    output_dir="data/tiles/dharavi_test"
)

print(f"Total tiles generated: {len(tiles)}")
print(f"First tile: {tiles[0]}")