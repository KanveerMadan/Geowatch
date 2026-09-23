import json
from PIL import Image

with open("data/pipeline_runs/dharavi_20260620_150817/result.json") as f:
    result = json.load(f)

print("First 5 segment bboxes and areas:")
for s in result["segments"][:5]:
    x, y, w, h = s["bbox"]
    print(f"  bbox=({x},{y},{w},{h})  area={s['area']}")

# Save a crop to visually inspect
# `primary_tile` was removed by item 46 (C13); resolve from the run dir.
tile_path = "data/pipeline_runs/dharavi_20260620_150817/tiles/tile_0_0.png"
img = Image.open(tile_path)
print(f"\nFull tile size: {img.size}")

x, y, w, h = result["segments"][0]["bbox"]
crop = img.crop((x, y, x + w, y + h))
crop.save("debug_crop_0.png")
print(f"Saved debug_crop_0.png — size {crop.size}")
