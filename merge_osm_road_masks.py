"""
Converts the OSM-generated road_mask.npy (from generate_osm_road_masks.py,
verified via check_generated_road_mask.py) into individual segment
annotations matching your existing mask_rle/human_label schema, then
writes them to a NEW, SEPARATE file:

    data/pipeline_runs/<city>_.../osm_generated_annotations.json

This is deliberately kept separate from the real annotations.json (which
holds human-reviewed SAM-segment labels) rather than merged in directly,
so you can always tell OSM-vector-derived labels apart from
human-reviewed ones later -- matching the project's own standard of never
hiding data provenance. Every entry here is tagged
"annotation_source": "osm_road_vector" for exactly this reason.

The single road mask is split into separate CONNECTED COMPONENTS (each
disconnected blob of road pixels becomes its own segment with its own
bbox/area/mask_rle) rather than one giant mask for the whole tile --
this matches how your existing per-segment schema expects one mask per
entry, and gives you multiple real training examples per city instead of
one monolithic one.

USAGE (run from geowatch/ repo root):
    python merge_osm_road_masks.py <city>
    python merge_osm_road_masks.py dharavi

IMPORTANT -- this does NOT touch annotations.json or masks.json. It's a
new, additive file. You (or a later dataset-build step) need to
explicitly include osm_generated_annotations.json alongside
annotations.json when building training patches -- this script does not
do that wiring for you, since that touches your existing
run_all_cities.py-style dataset code which isn't in front of me.

Requires: scipy (for connected-component labeling), numpy
Install if missing:
    pip install scipy --break-system-packages
"""

import os
import sys
import json
import glob
from datetime import datetime, timezone

import numpy as np
from scipy import ndimage

PIPELINE_RUNS_DIR = "data/pipeline_runs"
MIN_COMPONENT_AREA = 15  # drop tiny fragment components (likely noise from
                          # buffering artifacts at road intersections/ends)


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


def get_next_segment_id(masks_json_path):
    """Find the max existing segment_id in masks.json so new OSM-derived
    segment_ids never collide with real SAM segment_ids."""
    if not os.path.exists(masks_json_path):
        return 1000  # arbitrary safe starting point if masks.json missing
    with open(masks_json_path) as f:
        masks = json.load(f)
    if not masks:
        return 1000
    max_id = max(m.get("segment_id", 0) for m in masks)
    return max_id + 1


def main():
    if len(sys.argv) != 2:
        print("Usage: python merge_osm_road_masks.py <city>")
        sys.exit(1)
    city = sys.argv[1]

    run_dir = find_run_dir(city)
    if run_dir is None:
        print(f"No run dir found for {city}")
        sys.exit(1)

    mask_path = os.path.join(run_dir, "osm_road_mask", "road_mask.npy")
    if not os.path.exists(mask_path):
        print(f"No road_mask.npy found for {city}. "
              f"Run generate_osm_road_masks.py {city} first, then "
              f"check_generated_road_mask.py {city} to verify it, before "
              f"running this.")
        sys.exit(1)

    road_mask = np.load(mask_path)
    masks_json_path = os.path.join(run_dir, "masks.json")
    next_id = get_next_segment_id(masks_json_path)

    # connected component labeling -- 8-connectivity so diagonal road
    # pixels count as connected (roads are often diagonal in these tiles)
    structure = np.ones((3, 3), dtype=int)
    labeled, num_components = ndimage.label(road_mask, structure=structure)
    print(f"{city}: found {num_components} connected road components "
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
            "human_label": "paved_road",
            "skipped": False,
            "annotated_at": datetime.now(timezone.utc).isoformat(),
            "annotation_priority": "osm_road_generated",
            "annotation_source": "osm_road_vector",
            "crop_confidence": None,
            "crop_top_category": None,
            "tile_confidence": None,
            "tile_suggested_label": None,
        })
        kept += 1

    print(f"Kept {kept} components as segments (dropped {dropped_small} "
          f"below {MIN_COMPONENT_AREA}px as noise).")

    out_path = os.path.join(run_dir, "osm_generated_annotations.json")
    with open(out_path, "w") as f:
        json.dump({"annotations": entries, "source": "osm_road_vector",
                   "city": city}, f, indent=2)

    print(f"Wrote {len(entries)} new paved_road annotations to: {out_path}")
    print("\nThis file is SEPARATE from annotations.json -- your dataset")
    print("build step needs to be updated to also read from")
    print("osm_generated_annotations.json (in addition to annotations.json)")
    print("when constructing training patches, or these won't be used yet.")


if __name__ == "__main__":
    main()