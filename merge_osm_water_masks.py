import os
import sys
import json
import glob
from datetime import datetime, timezone

import numpy as np
from scipy import ndimage

PIPELINE_RUNS_DIR = "data/pipeline_runs"
MIN_COMPONENT_AREA = 15  # drop tiny fragment components (likely noise from
                          # buffering artifacts / polygon rasterization
                          # edge effects) -- same threshold as road script


def find_run_dir(city):
    matches = sorted(glob.glob(os.path.join(PIPELINE_RUNS_DIR, f"{city}_*")))
    return matches[-1] if matches else None


def encode_rle(mask_bool):
    """Encode a 2D boolean mask into the same COCO-style RLE format used
    elsewhere in this project ({'size': [h, w], 'counts': [...]}),
    column-major (Fortran order), matching decode_rle's expectations."""
    h, w = mask_bool.shape
    flat = mask_bool.T.flatten()  # column-major flatten, matches decode_rle
    counts = []
    prev_val = False
    run_len = 0
    for val in flat:
        if val == prev_val:
            run_len += 1
        else:
            counts.append(run_len)
            run_len = 1
            prev_val = val
    counts.append(run_len)
    return {"size": [h, w], "counts": counts}


def get_next_segment_id(masks_json_path, extra_json_paths=None):
    """Find the max existing segment_id across masks.json AND any other
    already-generated annotation files (e.g. the road version's output),
    so new water-derived segment_ids never collide with real SAM
    segment_ids OR with the road script's OSM-generated segment_ids.
    This is a small, deliberate improvement over the road script's
    original version, which only checked masks.json -- if you run the
    road merge first and then this one, checking only masks.json could
    produce a collision with the road script's own generated IDs."""
    max_id = 0
    if os.path.exists(masks_json_path):
        with open(masks_json_path) as f:
            masks = json.load(f)
        if masks:
            max_id = max(max_id, max(m.get("segment_id", 0) for m in masks))

    for extra_path in (extra_json_paths or []):
        if os.path.exists(extra_path):
            with open(extra_path) as f:
                data = json.load(f)
            anns = data.get("annotations", [])
            if anns:
                max_id = max(max_id, max(a.get("segment_id", 0) for a in anns))

    return max(max_id + 1, 1000)  # same arbitrary safe floor as road script


def main():
    if len(sys.argv) != 2:
        print("Usage: python merge_osm_water_masks.py <city>")
        sys.exit(1)
    city = sys.argv[1]

    run_dir = find_run_dir(city)
    if run_dir is None:
        print(f"No run dir found for {city}")
        sys.exit(1)

    mask_path = os.path.join(run_dir, "osm_water_mask", "water_mask.npy")
    if not os.path.exists(mask_path):
        print(f"No water_mask.npy found for {city}. "
              f"Run generate_osm_water_masks.py {city} first, then "
              f"check_generated_water_mask.py {city} to verify it, before "
              f"running this.")
        sys.exit(1)

    water_mask = np.load(mask_path)
    masks_json_path = os.path.join(run_dir, "masks.json")
    road_annotations_path = os.path.join(run_dir, "osm_generated_annotations.json")
    next_id = get_next_segment_id(
        masks_json_path, extra_json_paths=[road_annotations_path]
    )

    # connected component labeling -- 8-connectivity so diagonal water
    # pixels count as connected (same rationale as road script: water
    # bodies/canals are often diagonal in these tiles)
    structure = np.ones((3, 3), dtype=int)
    labeled, num_components = ndimage.label(water_mask, structure=structure)
    print(f"{city}: found {num_components} connected water components "
          f"before area filtering.")

    entries = []
    kept = 0
    dropped_small = 0
    for comp_id in range(1, num_components + 1):
        comp_mask = labeled == comp_id
        area = int(comp_mask.sum())
        if area < MIN_COMPONENT_AREA:
            dropped_small += 1
            continue

        ys, xs = np.where(comp_mask)
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        bbox = [x0, y0, x1 - x0 + 1, y1 - y0 + 1]

        seg_id = next_id
        next_id += 1

        rle = encode_rle(comp_mask)

        entries.append({
            "segment_id": seg_id,
            "bbox": bbox,
            "area": area,
            "mask_rle": rle,
            "human_label": "standing_water",
            "skipped": False,
            "annotated_at": datetime.now(timezone.utc).isoformat(),
            "annotation_priority": "osm_water_generated",
            "annotation_source": "osm_water_vector",
            "crop_confidence": None,
            "crop_top_category": None,
            "tile_confidence": None,
            "tile_suggested_label": None,
        })
        kept += 1

    print(f"Kept {kept} components as segments (dropped {dropped_small} "
          f"below {MIN_COMPONENT_AREA}px as noise).")

    out_path = os.path.join(run_dir, "osm_generated_annotations_water.json")
    with open(out_path, "w") as f:
        json.dump({"annotations": entries, "source": "osm_water_vector",
                   "city": city}, f, indent=2)

    print(f"Wrote {len(entries)} new standing_water annotations to: {out_path}")
    print("\nThis file is SEPARATE from annotations.json AND from")
    print("osm_generated_annotations.json (the road version's output) --")
    print("your dataset build step needs to be updated to also read from")
    print("osm_generated_annotations_water.json when constructing")
    print("training patches, or these won't be used yet.")


if __name__ == "__main__":
    main()