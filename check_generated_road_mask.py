"""
Overlays the OSM-generated road mask (from generate_osm_road_masks.py)
directly on top of the real tile image, so you can visually confirm the
roads actually line up with real roads in the imagery before trusting
this for training.

DO NOT skip this step. If the CRS/transform handling in
generate_osm_road_masks.py has any mistake, this is the only way you'd
catch it -- the numbers alone (pixel counts etc.) won't tell you.

USAGE (run from geowatch/ repo root):
    python check_generated_road_mask.py <city>

Saves a side-by-side comparison image to:
    data/pipeline_runs/<city>_.../osm_road_mask/verification_preview.png
"""

import os
import sys
import glob
import json

import numpy as np
from PIL import Image

PIPELINE_RUNS_DIR = "data/pipeline_runs"


def find_run_dir(city):
    matches = sorted(glob.glob(os.path.join(PIPELINE_RUNS_DIR, f"{city}_*")))
    return matches[-1] if matches else None


def main():
    if len(sys.argv) != 2:
        print("Usage: python check_generated_road_mask.py <city>")
        sys.exit(1)
    city = sys.argv[1]

    run_dir = find_run_dir(city)
    mask_path = os.path.join(run_dir, "osm_road_mask", "road_mask.npy")
    meta_path = os.path.join(run_dir, "osm_road_mask", "meta.json")
    tile_path = os.path.join(run_dir, "tiles", "tile_0_0.png")

    if not os.path.exists(mask_path):
        print(f"No generated mask found at {mask_path}. "
              f"Run generate_osm_road_masks.py {city} first.")
        sys.exit(1)

    with open(meta_path) as f:
        meta = json.load(f)
    print(json.dumps(meta, indent=2))

    road_mask = np.load(mask_path)
    tile_img = Image.open(tile_path).convert("RGB")
    tile_arr = np.array(tile_img)

    if tile_arr.shape[:2] != road_mask.shape:
        print(f"WARNING: shape mismatch -- tile is {tile_arr.shape[:2]}, "
              f"mask is {road_mask.shape}. This alone suggests something "
              "is misaligned, investigate before trusting the overlay below.")

    # overlay: original on left, road mask highlighted in bright cyan on right
    overlay = tile_arr.copy()
    overlay[road_mask] = [0, 255, 255]  # bright cyan, impossible to miss

    original_img = Image.fromarray(tile_arr)
    overlay_img = Image.fromarray(overlay)

    combined = Image.new("RGB", (tile_arr.shape[1] * 2 + 10, tile_arr.shape[0]),
                          (255, 255, 255))
    combined.paste(original_img, (0, 0))
    combined.paste(overlay_img, (tile_arr.shape[1] + 10, 0))

    out_path = os.path.join(run_dir, "osm_road_mask", "verification_preview.png")
    combined.save(out_path)
    print(f"\nSaved verification image to: {out_path}")
    print("Open it now. LEFT = original tile. RIGHT = same tile with the "
          "generated road mask in bright cyan.")
    print("\nWhat to check:")
    print("  - Does the cyan highlight sit ON TOP of visible roads/paths "
          "in the original image (left side)?")
    print("  - If cyan is offset from real roads by a consistent direction "
          "(e.g. always shifted a few pixels up-left), that's a transform/"
          "CRS bug -- tell me the offset direction and I'll fix it.")
    print("  - If cyan appears in totally unrelated locations (rooftops, "
          "vegetation, empty space) with no relationship to real roads at "
          "all, that's a bigger CRS/projection mismatch -- stop and tell me.")
    print("  - If it looks basically right (cyan tracks the real road "
          "shapes even if not pixel-perfect), this is good to use for "
          "training.")


if __name__ == "__main__":
    main()