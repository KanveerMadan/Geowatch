"""
Visually verifies that a generated standing_water mask (from
generate_osm_water_masks.py) actually lines up with real water features
in the tile image, before it gets merged into training data via
merge_osm_water_masks.py.

Mirrors check_generated_road_mask.py's exact approach: overlay the
boolean mask on top of the real tile PNG in a distinct, semi-transparent
color, and save the result as a single PNG you can open and eyeball.
This is the cheapest possible sanity check against a silent CRS/transform
bug -- if the mask is offset, rotated, or empty where you can see real
water, it will be immediately obvious visually in a way that pixel counts
alone can hide.

USAGE (run from geowatch/ repo root):
    python check_generated_water_mask.py <city>
    python check_generated_water_mask.py accra

Output:
    data/pipeline_runs/<city>_.../osm_water_mask/water_mask_overlay.png

Requires: numpy, Pillow
"""

import os
import sys
import glob
import json

import numpy as np
from PIL import Image

PIPELINE_RUNS_DIR = "data/pipeline_runs"

# Semi-transparent cyan/blue overlay -- distinct from typical tile colors
# (roads/roofing tend to be gray/brown/red, vegetation green, so blue
# reads unambiguously as "this is what the script thinks is water")
OVERLAY_COLOR = (0, 140, 255)   # RGB
OVERLAY_ALPHA = 0.5             # 0 = invisible, 1 = fully opaque


def find_run_dir(city):
    matches = sorted(glob.glob(os.path.join(PIPELINE_RUNS_DIR, f"{city}_*")))
    return matches[-1] if matches else None


def main():
    if len(sys.argv) != 2:
        print("Usage: python check_generated_water_mask.py <city>")
        sys.exit(1)
    city = sys.argv[1]

    run_dir = find_run_dir(city)
    if run_dir is None:
        print(f"No run dir found for {city}")
        sys.exit(1)

    mask_path = os.path.join(run_dir, "osm_water_mask", "water_mask.npy")
    meta_path = os.path.join(run_dir, "osm_water_mask", "meta.json")
    tile_path = os.path.join(run_dir, "tiles", "tile_0_0.png")

    if not os.path.exists(mask_path):
        print(f"No water_mask.npy found for {city}. "
              f"Run 'python generate_osm_water_masks.py {city}' first.")
        sys.exit(1)
    if not os.path.exists(tile_path):
        print(f"No tile image found at {tile_path}")
        sys.exit(1)

    water_mask = np.load(mask_path)
    print(f"Loaded water_mask.npy: shape={water_mask.shape}, "
          f"dtype={water_mask.dtype}, true_pixels={water_mask.sum()}")

    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        print(f"meta.json: {json.dumps(meta, indent=2)}")
    else:
        print("WARNING: no meta.json found alongside water_mask.npy -- "
              "unusual, but continuing.")

    tile_img = Image.open(tile_path).convert("RGB")
    tile_w, tile_h = tile_img.size
    print(f"tile_0_0.png actual size: {tile_w}x{tile_h}")

    # Hard shape check -- if these don't match, everything downstream is
    # meaningless and it's better to fail loudly here than produce a
    # silently misaligned overlay image that looks plausible at a glance.
    if water_mask.shape != (tile_h, tile_w):
        print(f"\n*** SHAPE MISMATCH ***")
        print(f"water_mask.shape = {water_mask.shape} (h, w)")
        print(f"tile image size  = ({tile_h}, {tile_w}) (h, w)")
        print("This means the mask was NOT rasterized onto this tile's "
              "actual pixel grid -- do not trust this mask, re-check "
              "generate_osm_water_masks.py's tile_h/tile_w handling "
              "before proceeding.")
        sys.exit(1)

    if water_mask.sum() == 0:
        print("\nWARNING: mask is completely empty (0 water pixels). "
              "Nothing to visually overlay. This could mean:")
        print("  - genuinely no waterways in this tile (check meta.json's "
              "num_osm_ways_used)")
        print("  - a CRS/transform bug silently rasterized outside the "
              "tile's real extent")
        print("Overlay image will just be the plain tile -- inspect "
              "meta.json's 'num_osm_ways_used' to tell these apart.")

    # Build the overlay: blend OVERLAY_COLOR into the tile wherever
    # water_mask is True, leave everything else untouched.
    tile_arr = np.array(tile_img).astype(np.float32)
    overlay_arr = tile_arr.copy()
    color = np.array(OVERLAY_COLOR, dtype=np.float32)

    mask_3d = water_mask[:, :, None]  # broadcast over RGB channels
    overlay_arr = np.where(
        mask_3d,
        tile_arr * (1 - OVERLAY_ALPHA) + color * OVERLAY_ALPHA,
        tile_arr,
    )

    overlay_img = Image.fromarray(overlay_arr.astype(np.uint8), mode="RGB")

    out_dir = os.path.join(run_dir, "osm_water_mask")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "water_mask_overlay.png")
    overlay_img.save(out_path)

    # Also save a side-by-side comparison (original | overlay) since
    # that's often more useful for judging "does this actually look like
    # water where the blue is" than the overlay alone.
    side_by_side = Image.new("RGB", (tile_w * 2 + 10, tile_h), (255, 255, 255))
    side_by_side.paste(tile_img, (0, 0))
    side_by_side.paste(overlay_img, (tile_w + 10, 0))
    side_by_side_path = os.path.join(out_dir, "water_mask_side_by_side.png")
    side_by_side.save(side_by_side_path)

    print(f"\nSaved overlay to: {out_path}")
    print(f"Saved side-by-side (original | overlay) to: {side_by_side_path}")
    print("\nNEXT STEP -- open both PNGs and visually confirm the blue")
    print("overlay actually lines up with real water/canals/drainage")
    print("features you can see in the tile image (rivers often show up")
    print("as darker, smoother, linear features in Sentinel-2 RGB).")
    print("\nDo NOT proceed to merge_osm_water_masks.py if:")
    print("  - the blue overlay is offset from anything that looks like water")
    print("  - the blue overlay covers rooftops/roads/vegetation instead")
    print("  - the mask is empty but you can visually see water in the tile")
    print("\nIf it looks right, move on to the next city, then eventually")
    print("run merge_osm_water_masks.py once all cities are generated and")
    print("spot-checked.")


if __name__ == "__main__":
    main()