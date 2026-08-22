"""
Diagnostic for why find_paved_road_candidates.py returned 0 everywhere.
Run from geowatch/ repo root:

    python debug_candidates.py
"""

import os
import glob
import json

PIPELINE_RUNS_DIR = "data/pipeline_runs"
TRAINING_CITIES = [
    "accra", "capetown", "dhaka", "dharavi", "guatemala",
    "hcmc", "jakarta", "kigali", "lagos", "nairobi", "nusantara",
]

MIN_ELONGATION = 2.5
MAX_COMPACTNESS = 0.55
MIN_AREA = 30


def find_annotated_run_dir(city):
    candidates = []
    for run_dir in sorted(glob.glob(os.path.join(PIPELINE_RUNS_DIR, f"{city}_*"))):
        if not os.path.isdir(run_dir):
            continue
        tile_path = os.path.join(run_dir, "tiles", "tile_0_0.png")
        ann_path = os.path.join(run_dir, "annotations.json")
        masks_path = os.path.join(run_dir, "masks.json")
        if os.path.exists(tile_path) and os.path.exists(ann_path) and os.path.exists(masks_path):
            candidates.append(run_dir)
    return candidates[-1] if candidates else None, candidates


for city in TRAINING_CITIES:
    run_dir, all_matches = find_annotated_run_dir(city)
    if run_dir is None:
        print(f"{city:<12} NO qualifying run_dir found. all matching dirs: "
              f"{glob.glob(os.path.join(PIPELINE_RUNS_DIR, city + '_*'))}")
        continue

    with open(os.path.join(run_dir, "annotations.json")) as f:
        ann_data = json.load(f)
    anns = ann_data["annotations"] if isinstance(ann_data, dict) else ann_data
    already_handled_ids = {a.get("segment_id") for a in anns}

    with open(os.path.join(run_dir, "masks.json")) as f:
        masks = json.load(f)

    total = len(masks)
    unhandled = [m for m in masks if m.get("segment_id") not in already_handled_ids]

    pass_area = 0
    pass_elong = 0
    pass_compact = 0
    pass_both = 0

    for m in unhandled:
        bbox = m.get("bbox")
        area = m.get("area", 0)
        if bbox is None or area < MIN_AREA:
            continue
        pass_area += 1
        x, y, w, h = bbox
        if w <= 0 or h <= 0:
            continue
        long_side = max(w, h)
        short_side = max(min(w, h), 1)
        elongation = long_side / short_side
        compactness = area / (w * h)
        if elongation >= MIN_ELONGATION:
            pass_elong += 1
        if compactness <= MAX_COMPACTNESS:
            pass_compact += 1
        if elongation >= MIN_ELONGATION and compactness <= MAX_COMPACTNESS:
            pass_both += 1

    print(f"{city:<12} run_dir={os.path.basename(run_dir)} "
          f"(found {len(all_matches)} matching run dirs total)")
    print(f"             total masks: {total}  |  already handled: {len(already_handled_ids)}  "
          f"|  unhandled: {len(unhandled)}")
    print(f"             of unhandled -> pass MIN_AREA: {pass_area}, "
          f"pass elongation>=2.5: {pass_elong}, pass compactness<=0.55: {pass_compact}, "
          f"pass BOTH (=candidate): {pass_both}")
    print()