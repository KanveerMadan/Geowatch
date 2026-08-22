from ingestion.tiler import generate_tiles

tiles = generate_tiles(
    image_path="data/pipeline_runs/dharavi_20260620_150817/raw.tif",
    output_dir="data/pipeline_runs/dharavi_20260620_150817/tiles_fixed"
)
print(tiles)
