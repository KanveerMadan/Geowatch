"""
Before retraining with a separation loss between paved_road and
dense_informal_roofing, check whether the EXISTING ground-truth labels
for this pair are themselves a source of noise -- i.e., are there many
cases where a paved_road-labeled segment sits immediately adjacent to a
dense_informal_roofing-labeled segment, suggesting the human annotation
boundary between them was drawn through a genuinely ambiguous zone (or
inconsistently between similar-looking cases)?

This does NOT relabel anything. It flags candidate boundary-ambiguity
segment pairs for manual review, and reports how common this pattern is
across all 11 cities -- if it's rare, the confusion is probably purely a
model/architecture problem (step 2's separation loss should help a lot).
If it's common, some of the "ground truth" itself may be inconsistent at
the boundary, and retraining alone won't fully fix it -- a label review
pass would need to happen first or alongside.

USAGE (run from geowatch/ repo root):
    python audit_boundary_labels.py

Uses the same auto-selected per-city run dirs as recalibrate_caat.py
(the one run dir per city with both a tile and a matching annotations.json
+ masks.json pair).
"""

import os
import sys
import json
import glob
import numpy as np

sys.path.insert(0, ".")

from ingestion.segmentation import decode_mask_rle

PIPELINE_RUNS_DIR = "data/pipeline_runs"
TRAINING_CITIES = [
    "accra", "capetown", "dhaka", "dharavi", "guatemala",
    "hcmc", "jakarta", "kigali", "lagos", "nairobi", "nusantara",
]
FOCUS_PAIR = ("paved_road", "dense_informal_roofing")
ADJACENCY_DILATION_PX = 3  # how many pixels of "nearby" counts as adjacent


def find_annotated_run_dir(city: str) -> str:
    candidates = []
    for run_dir in sorted(glob.glob(os.path.join(PIPELINE_RUNS_DIR, f"{city}_*"))):
        if not os.path.isdir(run_dir):
            continue
        tile_path = os.path.join(run_dir, "tiles", "tile_0_0.png")
        ann_path = os.path.join(run_dir, "annotations.json")
        masks_path = os.path.join(run_dir, "masks.json")
        if os.path.exists(tile_path) and os.path.exists(ann_path) and os.path.exists(masks_path):
            candidates.append(run_dir)
    return candidates[-1] if candidates else None


def dilate_mask(mask: np.ndarray, px: int) -> np.ndarray:
    """Simple box dilation without needing scipy/cv2 -- shifts and ORs."""
    out = mask.copy()
    for dy in range(-px, px + 1):
        for dx in range(-px, px + 1):
            shifted = np.zeros_like(mask)
            H, W = mask.shape
            y1, y2 = max(0, dy), H + min(0, dy)
            x1, x2 = max(0, dx), W + min(0, dx)
            sy1, sy2 = max(0, -dy), H - max(0, dy)
            sx1, sx2 = max(0, -dx), W - max(0, dx)
            shifted[y1:y2, x1:x2] = mask[sy1:sy2, sx1:sx2]
            out |= shifted
    return out


def main():
    focus_a, focus_b = FOCUS_PAIR
    total_a_segments = 0
    total_b_segments = 0
    adjacent_pairs_found = 0
    flagged_pairs = []

    for city in TRAINING_CITIES:
        run_dir = find_annotated_run_dir(city)
        if run_dir is None:
            print(f"{city}: no qualifying run dir, skipping.")
            continue

        with open(os.path.join(run_dir, "annotations.json")) as f:
            ann_data = json.load(f)
        anns = ann_data["annotations"] if isinstance(ann_data, dict) else ann_data

        with open(os.path.join(run_dir, "masks.json")) as f:
            masks = json.load(f)
        mask_by_segment = {m["segment_id"]: m for m in masks if "segment_id" in m}

        a_segments = []  # list of (segment_id, decoded_mask)
        b_segments = []

        for a in anns:
            if a.get("skipped"):
                continue
            label = a.get("human_label")
            seg_id = a.get("segment_id")
            mask_entry = mask_by_segment.get(seg_id)
            if mask_entry is None or "mask_rle" not in mask_entry:
                continue
            if label == focus_a:
                a_segments.append((seg_id, decode_mask_rle(mask_entry["mask_rle"])))
            elif label == focus_b:
                b_segments.append((seg_id, decode_mask_rle(mask_entry["mask_rle"])))

        total_a_segments += len(a_segments)
        total_b_segments += len(b_segments)

        city_adjacent = 0
        for a_id, a_mask in a_segments:
            a_dilated = dilate_mask(a_mask, ADJACENCY_DILATION_PX)
            for b_id, b_mask in b_segments:
                if (a_dilated & b_mask).any():
                    city_adjacent += 1
                    adjacent_pairs_found += 1
                    flagged_pairs.append({
                        "city": city, "run_dir": run_dir,
                        f"{focus_a}_segment_id": a_id,
                        f"{focus_b}_segment_id": b_id,
                    })

        print(f"{city:<15} {focus_a}: {len(a_segments):>3} segments, "
              f"{focus_b}: {len(b_segments):>3} segments, "
              f"adjacent pairs (within {ADJACENCY_DILATION_PX}px): {city_adjacent}")

    print("\n" + "=" * 70)
    print(f"Total {focus_a} segments across all cities: {total_a_segments}")
    print(f"Total {focus_b} segments across all cities: {total_b_segments}")
    print(f"Total adjacent (potentially boundary-ambiguous) segment pairs: {adjacent_pairs_found}")

    if flagged_pairs:
        print(f"\nFlagged pairs (city, segment ids) for manual review:")
        for p in flagged_pairs:
            print(f"  {p['city']:<12} {focus_a}#{p[f'{focus_a}_segment_id']} <-> "
                  f"{focus_b}#{p[f'{focus_b}_segment_id']}   ({p['run_dir']})")

    print("\n" + "=" * 70)
    print("INTERPRETATION")
    rate = 100.0 * adjacent_pairs_found / max(total_a_segments + total_b_segments, 1)
    print(f"  Adjacent pairs relative to total segments in this pair: {rate:.1f}%")
    if adjacent_pairs_found == 0:
        print("  -> No spatially adjacent label pairs found. The confusion is very")
        print("     likely a pure model/architecture issue (spectral similarity the")
        print("     current features can't separate) -- proceed straight to the")
        print("     separation-loss retraining fix, ground truth itself looks fine.")
    elif rate < 15:
        print("  -> A small number of adjacent pairs exist -- worth a quick manual")
        print("     look at the flagged list above, but not enough to suggest")
        print("     widespread labeling inconsistency. Proceed with the separation-loss")
        print("     retraining fix; spot-check the flagged pairs opportunistically.")
    else:
        print("  -> A substantial share of segments in this pair sit directly adjacent")
        print("     to each other. Worth manually reviewing the flagged pairs BEFORE")
        print("     retraining -- if several turn out to be inconsistently labeled,")
        print("     fixing those labels first will make the separation-loss retraining")
        print("     meaningfully more effective, rather than training against noise.")


if __name__ == "__main__":
    main()