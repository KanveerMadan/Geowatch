"""
For every pixel currently rejected as 'unknown' by CAAT, this recovers
what class the model actually predicted (argmax, before thresholding) and
tabulates it. This answers a narrower question than the earlier
diagnostics: is the ~50% unknown mass concentrated in one or two classes
(a narrow, fixable problem -- e.g. one class's decoder head is
under-trained, or one class is systematically ambiguous with another) or
spread roughly evenly across all 7 (a broad, genuine-uncertainty problem
that recalibration/thresholding can't fix, per the validation result
already found).

USAGE:
    python breakdown_unknown_class.py <checkpoint_path> <caat_json_path> <tile_path> [<tile_path> ...]

Example:
    python breakdown_unknown_class.py \
      models/production/geowatch_production_model.pth \
      models/production/caat_thresholds.json \
      data/pipeline_runs/capetown_20260702_164022/tiles/tile_0_0.png \
      data/pipeline_runs/dharavi_20260702_163012/tiles/tile_0_0.png

Uses the CURRENT PRODUCTION caat_thresholds.json by default (pass the
recalibrated one instead if you want to see the breakdown under the new
thresholds -- either is valid, they'll just show slightly different
unknown masses per the validation result already found).
"""

import sys
import json
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

sys.path.insert(0, ".")

from ingestion.inference import load_production_model, PATCH_SIZE

UNKNOWN_INDEX = 255


def load_thresholds_array(path: str, categories: list) -> np.ndarray:
    with open(path) as f:
        data = json.load(f)
    raw = data["thresholds"]
    return np.array([raw[c] for c in categories], dtype=np.float32)


def sliding_window_mean_probs(tile_path: str, model, num_classes: int,
                               patch_size: int, stride: int, device: str) -> np.ndarray:
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
    return prob_accum / count_accum[None, :, :]


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)

    checkpoint_path = sys.argv[1]
    caat_path = sys.argv[2]
    tile_paths = sys.argv[3:]

    print("=" * 70)
    print("Loading model + thresholds...")
    model, categories, num_classes = load_production_model(checkpoint_path)
    thresholds = load_thresholds_array(caat_path, categories)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Pooled across all tiles passed in
    pooled_unknown_argmax_counts = np.zeros(num_classes, dtype=np.int64)
    pooled_total_unknown = 0
    pooled_total_pixels = 0

    per_tile_results = []

    for tile_path in tile_paths:
        print("\n" + "=" * 70)
        print(f"TILE: {tile_path}")

        mean_probs = sliding_window_mean_probs(
            tile_path, model, num_classes,
            patch_size=PATCH_SIZE, stride=PATCH_SIZE // 2, device=device,
        )  # (C, H, W)

        pred_idx = np.argmax(mean_probs, axis=0)          # (H, W) -- raw argmax, no rejection
        pred_conf = np.max(mean_probs, axis=0)             # (H, W)
        per_pixel_threshold = thresholds[pred_idx]          # (H, W)

        is_unknown = pred_conf < per_pixel_threshold        # (H, W) bool -- CAAT-rejected pixels
        H, W = pred_idx.shape
        total_px = H * W
        n_unknown = int(is_unknown.sum())

        print(f"  Total pixels: {total_px}, unknown (CAAT-rejected): {n_unknown} "
              f"({100.0 * n_unknown / total_px:.2f}%)")

        # For unknown pixels ONLY, tabulate what class they WOULD have been
        # (their raw argmax, before CAAT rejected them)
        unknown_argmax = pred_idx[is_unknown]
        counts = np.bincount(unknown_argmax, minlength=num_classes)

        print(f"\n  Breakdown of unknown pixels by their pre-rejection argmax class:")
        print(f"  {'category':<30} {'count':>10} {'% of unknown mass':>20} {'% of ALL pixels':>18}")
        order = np.argsort(-counts)
        for i in order:
            pct_of_unknown = 100.0 * counts[i] / n_unknown if n_unknown > 0 else 0.0
            pct_of_all = 100.0 * counts[i] / total_px
            print(f"  {categories[i]:<30} {counts[i]:>10} {pct_of_unknown:>19.2f}% {pct_of_all:>17.2f}%")

        pooled_unknown_argmax_counts += counts
        pooled_total_unknown += n_unknown
        pooled_total_pixels += total_px

        per_tile_results.append({
            "tile": tile_path, "n_unknown": n_unknown, "total_px": total_px,
        })

    print("\n" + "=" * 70)
    print("POOLED ACROSS ALL TILES")
    print(f"Total unknown pixels: {pooled_total_unknown} / {pooled_total_pixels} "
          f"({100.0 * pooled_total_unknown / pooled_total_pixels:.2f}%)")
    print(f"\n  {'category':<30} {'count':>10} {'% of unknown mass':>20} {'% of ALL pixels':>18}")
    order = np.argsort(-pooled_unknown_argmax_counts)
    top_share = 0.0
    for rank, i in enumerate(order):
        pct_of_unknown = (100.0 * pooled_unknown_argmax_counts[i] / pooled_total_unknown
                           if pooled_total_unknown > 0 else 0.0)
        pct_of_all = 100.0 * pooled_unknown_argmax_counts[i] / pooled_total_pixels
        print(f"  {categories[i]:<30} {pooled_unknown_argmax_counts[i]:>10} "
              f"{pct_of_unknown:>19.2f}% {pct_of_all:>17.2f}%")
        if rank < 2:
            top_share += pct_of_unknown

    print("\n" + "=" * 70)
    print("INTERPRETATION")
    if top_share > 60:
        print(f"  Top 2 classes account for {top_share:.1f}% of the unknown mass.")
        print("  -> CONCENTRATED. This is a narrow, potentially fixable problem --")
        print("     look specifically at why those 1-2 classes are systematically")
        print("     low-confidence (undertrained decoder head, class imbalance in")
        print("     training patches, or confusion with a visually similar class).")
    else:
        print(f"  Top 2 classes account for only {top_share:.1f}% of the unknown mass --")
        print("  roughly spread across most/all 7 classes.")
        print("  -> BROAD. This is consistent with genuine, distributed model")
        print("     uncertainty (limited training data per LOCO fold, 10m resolution")
        print("     ceiling, and/or the missing formal-housing category diluting")
        print("     confidence broadly) -- not fixable by touching thresholds or")
        print("     any single class's data. Needs more training data/cities or an")
        print("     architecture change, not another inference-side fix.")


if __name__ == "__main__":
    main()