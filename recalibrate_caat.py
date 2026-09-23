import os
import sys
import json
import glob
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

sys.path.insert(0, ".")

from ingestion.inference import load_production_model, PATCH_SIZE
from ingestion.segmentation import decode_mask_rle


PIPELINE_RUNS_DIR = "data/pipeline_runs"
IGNORE_INDEX = 255
PERCENTILE = 10.0
MIN_THRESHOLD = 0.15

# All 11 training cities per the master prompt (Section 4h) -- used to
# select which run_dir prefix to look for per city.
TRAINING_CITIES = [
    "accra", "capetown", "dhaka", "dharavi", "guatemala",
    "hcmc", "jakarta", "kigali", "lagos", "nairobi", "nusantara",
]


def find_annotated_run_dir(city: str) -> str:
    """
    Per city, find the one run directory that has BOTH a real tile image
    AND a matching annotations.json + masks.json pair. If more than one
    qualifies (shouldn't happen per the check_gt_format.py output, but
    checked defensively), picks the most recent by directory name.
    """
    candidates = []
    for run_dir in sorted(glob.glob(os.path.join(PIPELINE_RUNS_DIR, f"{city}_*"))):
        if not os.path.isdir(run_dir):
            continue
        tile_path = os.path.join(run_dir, "tiles", "tile_0_0.png")
        ann_path = os.path.join(run_dir, "annotations.json")
        masks_path = os.path.join(run_dir, "masks.json")
        if os.path.exists(tile_path) and os.path.exists(ann_path) and os.path.exists(masks_path):
            candidates.append(run_dir)

    if not candidates:
        return None
    if len(candidates) > 1:
        print(f"  WARNING: {city} has {len(candidates)} qualifying run dirs "
              f"({candidates}); using the most recent: {candidates[-1]}")
    return candidates[-1]


def build_label_canvas(run_dir: str, tile_shape, categories: list) -> np.ndarray:
    """
    Paints a (H, W) uint8 canvas: each pixel is either a class index
    (0..num_classes-1) where a labeled segment's real mask covers it, or
    IGNORE_INDEX (255) everywhere else.

    If two labeled segments overlap on a pixel (shouldn't normally happen
    with SAM's mutually-exclusive-ish masks, but not guaranteed), the
    LAST segment processed wins -- logged if detected.
    """
    H, W = tile_shape
    canvas = np.full((H, W), IGNORE_INDEX, dtype=np.uint8)
    cat_to_idx = {cat: i for i, cat in enumerate(categories)}

    with open(os.path.join(run_dir, "annotations.json")) as f:
        ann_data = json.load(f)
    anns = ann_data["annotations"] if isinstance(ann_data, dict) else ann_data

    with open(os.path.join(run_dir, "masks.json")) as f:
        masks = json.load(f)
    mask_by_segment = {m["segment_id"]: m for m in masks if "segment_id" in m}

    n_painted = 0
    n_skipped_no_mask = 0
    n_skipped_bad_label = 0
    overlap_hits = 0

    for a in anns:
        if a.get("skipped"):
            continue
        human_label = a.get("human_label")
        if not human_label or human_label not in cat_to_idx:
            n_skipped_bad_label += 1
            continue

        seg_id = a.get("segment_id")
        mask_entry = mask_by_segment.get(seg_id)
        if mask_entry is None or "mask_rle" not in mask_entry:
            n_skipped_no_mask += 1
            continue

        decoded = decode_mask_rle(mask_entry["mask_rle"])  # (H, W) bool, same size as tile
        if decoded.shape != (H, W):
            print(f"    WARNING: segment {seg_id} mask shape {decoded.shape} != "
                  f"tile shape {(H, W)}, skipping.")
            continue

        already_labeled = (canvas[decoded] != IGNORE_INDEX)
        if already_labeled.any():
            overlap_hits += int(already_labeled.sum())

        canvas[decoded] = cat_to_idx[human_label]
        n_painted += 1

    print(f"    Painted {n_painted} segments onto canvas "
          f"(skipped: {n_skipped_no_mask} no-mask, {n_skipped_bad_label} bad/OSM-only label)")
    if overlap_hits > 0:
        print(f"    NOTE: {overlap_hits} pixels were covered by more than one labeled "
              f"segment (last-writer-wins).")

    labeled_pct = 100.0 * (canvas != IGNORE_INDEX).sum() / (H * W)
    print(f"    Final labeled coverage: {labeled_pct:.2f}% of raster")

    return canvas


def sliding_window_mean_probs(tile_path: str, model, num_classes: int,
                               patch_size: int = PATCH_SIZE, stride: int = None,
                               device: str = None) -> np.ndarray:
    """
    Same sliding-window-averaging logic as ingestion/inference.py's
    run_inference(), but returns the full (num_classes, H, W) mean
    softmax array instead of the already-thresholded class map -- needed
    here since we want raw confidences to compare against, not a final
    unknown/known decision.
    """
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if stride is None:
        stride = patch_size // 2

    image = Image.open(tile_path).convert("RGB")
    img_arr = np.array(image, dtype=np.float32) / 255.0
    H, W, _ = img_arr.shape

    prob_accum = np.zeros((num_classes, H, W), dtype=np.float32)
    count_accum = np.zeros((H, W), dtype=np.float32)

    ys = list(range(0, max(H - patch_size, 0) + 1, stride))
    xs = list(range(0, max(W - patch_size, 0) + 1, stride))
    if not ys or ys[-1] != H - patch_size:
        ys.append(max(H - patch_size, 0))
    if not xs or xs[-1] != W - patch_size:
        xs.append(max(W - patch_size, 0))

    model.eval()
    with torch.no_grad():
        for y in ys:
            for x in xs:
                y2 = min(y + patch_size, H)
                x2 = min(x + patch_size, W)
                y1 = y2 - patch_size if y2 - patch_size >= 0 else 0
                x1 = x2 - patch_size if x2 - patch_size >= 0 else 0

                patch = img_arr[y1:y2, x1:x2, :]
                ph, pw = patch.shape[:2]

                if ph < patch_size or pw < patch_size:
                    padded = np.zeros((patch_size, patch_size, 3), dtype=np.float32)
                    padded[:ph, :pw, :] = patch
                    patch_in = padded
                else:
                    patch_in = patch

                tensor = torch.from_numpy(patch_in).permute(2, 0, 1).unsqueeze(0).to(device)
                logits = model(tensor)
                probs = F.softmax(logits, dim=1).squeeze(0).cpu().numpy()
                probs = probs[:, :ph, :pw]

                prob_accum[:, y1:y1 + ph, x1:x1 + pw] += probs
                count_accum[y1:y1 + ph, x1:x1 + pw] += 1.0

    count_accum = np.maximum(count_accum, 1e-6)
    mean_probs = prob_accum / count_accum[None, :, :]
    return mean_probs


def main():
    if len(sys.argv) != 2:
        print("USAGE: python recalibrate_caat.py <checkpoint_path>")
        sys.exit(1)

    checkpoint_path = sys.argv[1]

    print("=" * 70)
    print("Loading production model...")
    model, categories, num_classes = load_production_model(checkpoint_path)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    class_correct_probs = {c: [] for c in range(num_classes)}
    cities_used = []
    cities_missing = []

    for city in TRAINING_CITIES:
        print("\n" + "=" * 70)
        print(f"City: {city}")
        run_dir = find_annotated_run_dir(city)
        if run_dir is None:
            print(f"  No qualifying run dir found (need tile + annotations.json + "
                  f"masks.json all present) -- SKIPPING this city.")
            cities_missing.append(city)
            continue

        print(f"  Using run dir: {run_dir}")
        tile_path = os.path.join(run_dir, "tiles", "tile_0_0.png")

        with Image.open(tile_path) as im:
            w, h = im.size
        tile_shape = (h, w)

        canvas = build_label_canvas(run_dir, tile_shape, categories)

        print(f"  Running production-config sliding-window inference "
              f"(patch={PATCH_SIZE}, stride={PATCH_SIZE // 2})...")
        mean_probs = sliding_window_mean_probs(
            tile_path, model, num_classes,
            patch_size=PATCH_SIZE, stride=PATCH_SIZE // 2, device=device,
        )  # (num_classes, H, W)

        pred_idx = np.argmax(mean_probs, axis=0)  # (H, W)

        labeled_mask = canvas != IGNORE_INDEX
        n_labeled = int(labeled_mask.sum())
        if n_labeled == 0:
            print(f"  No labeled pixels after rasterization -- skipping.")
            cities_missing.append(city)
            continue

        correct_mask = labeled_mask & (pred_idx == canvas)
        n_correct = int(correct_mask.sum())
        print(f"  Labeled pixels: {n_labeled}, correctly predicted: {n_correct} "
              f"({100.0 * n_correct / n_labeled:.1f}%)")

        for c in range(num_classes):
            c_correct_mask = correct_mask & (canvas == c)
            if c_correct_mask.any():
                yy, xx = np.where(c_correct_mask)
                confs = mean_probs[c, yy, xx]
                class_correct_probs[c].extend(confs.tolist())

        cities_used.append(city)

    print("\n" + "=" * 70)
    print(f"Cities used: {cities_used}")
    if cities_missing:
        print(f"Cities SKIPPED (no qualifying run dir): {cities_missing}")
        print("NOTE: fewer cities pooled means less reliable per-class percentiles --")
        print("check whether these cities' annotation data can be located elsewhere.")

    print("\n" + "=" * 70)
    print(f"CAAT thresholds ({PERCENTILE}th percentile of pooled correct-prediction "
          f"confidence, production sliding-window config):")
    print("-" * 60)

    new_thresholds = {}
    for c in range(num_classes):
        cat_name = categories[c]
        n_samples = len(class_correct_probs[c])
        if n_samples == 0:
            thresh = 0.50
            print(f"  {cat_name:<30} NO CORRECT PREDICTIONS ACROSS ALL POOLED CITIES "
                  f"-- threshold=0.50 (conservative fallback)")
        else:
            thresh = float(np.percentile(class_correct_probs[c], PERCENTILE))
            thresh = max(thresh, MIN_THRESHOLD)
            print(f"  {cat_name:<30} threshold={thresh:.4f}  (from {n_samples} pooled "
                  f"correct predictions across {len(cities_used)} cities)")
        new_thresholds[cat_name] = thresh

    # C10 / build item 45: record the checkpoint's CONTENT HASH, not just its
    # path. The loader verifies against this. A path alone is not provenance --
    # a retrained checkpoint written to the same filename would pass a basename
    # comparison while being a different model.
    from ingestion.inference import sha256_file
    checkpoint_sha256 = sha256_file(checkpoint_path)
    print(f"\nRecording provenance: {checkpoint_path}")
    print(f"  sha256 {checkpoint_sha256}")

    output = {
        "thresholds": new_thresholds,
        "source_checkpoint": checkpoint_path,
        "source_checkpoint_sha256": checkpoint_sha256,
        "methodology": (
            "Recalibrated against production sliding-window-averaged inference "
            "(patch=64, stride=32) on rasterized sparse segment annotations, "
            "pooled across cities: " + ", ".join(cities_used) +
            ". Supersedes the original CAAT which was computed from isolated "
            "64x64 patch forward passes -- see caat_diagnostic.py for the "
            "confirmed +22pp unknown-rate gap this was causing."
        ),
        "cities_pooled": cities_used,
        "cities_skipped": cities_missing,
        "percentile": PERCENTILE,
        "min_threshold_floor": MIN_THRESHOLD,
    }

    out_path = "models/production/caat_thresholds_recalibrated.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved: {out_path}")
    print("This is a NEW file -- caat_thresholds.json (production) was NOT")
    print("overwritten. Compare old vs. new thresholds below, then decide whether")
    print("to swap it into production.")

    old_caat_path = "models/production/caat_thresholds.json"
    if os.path.exists(old_caat_path):
        with open(old_caat_path) as f:
            old_data = json.load(f)
        old_thresholds = old_data.get("thresholds", {})
        print("\n" + "=" * 70)
        print("OLD vs. NEW threshold comparison:")
        print(f"  {'category':<30} {'old':>8} {'new':>8} {'delta':>8}")
        for cat in categories:
            old_t = old_thresholds.get(cat, float("nan"))
            new_t = new_thresholds.get(cat, float("nan"))
            delta = new_t - old_t if old_t == old_t else float("nan")
            print(f"  {cat:<30} {old_t:8.4f} {new_t:8.4f} {delta:+8.4f}")


if __name__ == "__main__":
    main()