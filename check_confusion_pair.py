"""
Follow-up to breakdown_unknown_class.py's finding: paved_road and
dense_informal_roofing together account for 72.9% of all unknown-pixel
mass, pooled across Cape Town + Dharavi.

This checks WHY: for every unknown pixel whose top (argmax) class is
paved_road or dense_informal_roofing, what is the SECOND-highest
probability class? If it's overwhelmingly the other member of this pair,
that confirms a genuine confusion pair -- the model can't cleanly separate
these two visually, at 10m, in these AOIs. If the second choice is spread
across many other classes instead, it's not a clean pair-confusion and is
more likely general undertraining for these two classes independently.

USAGE:
    python check_confusion_pair.py <checkpoint_path> <tile_path> [<tile_path> ...]
"""

import sys
import json
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

sys.path.insert(0, ".")

from ingestion.inference import load_production_model, PATCH_SIZE


def sliding_window_mean_probs(tile_path, model, num_classes, patch_size, stride, device):
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
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    checkpoint_path = sys.argv[1]
    tile_paths = sys.argv[2:]
    caat_path = "models/production/caat_thresholds.json"

    model, categories, num_classes = load_production_model(checkpoint_path)
    with open(caat_path) as f:
        raw_thresh = json.load(f)["thresholds"]
    thresholds = np.array([raw_thresh[c] for c in categories], dtype=np.float32)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    paved_idx = categories.index("paved_road")
    roofing_idx = categories.index("dense_informal_roofing")

    # pooled second-choice tally, separately for each of the two focus classes
    pooled_second_choice = {paved_idx: np.zeros(num_classes, dtype=np.int64),
                             roofing_idx: np.zeros(num_classes, dtype=np.int64)}
    pooled_n = {paved_idx: 0, roofing_idx: 0}

    for tile_path in tile_paths:
        print("=" * 70)
        print(f"TILE: {tile_path}")

        mean_probs = sliding_window_mean_probs(
            tile_path, model, num_classes, PATCH_SIZE, PATCH_SIZE // 2, device
        )  # (C, H, W)

        sorted_idx = np.argsort(-mean_probs, axis=0)  # (C, H, W), best..worst per pixel
        top1_idx = sorted_idx[0]
        top2_idx = sorted_idx[1]
        top1_conf = np.take_along_axis(mean_probs, top1_idx[None, :, :], axis=0).squeeze(0)
        per_pixel_thresh = thresholds[top1_idx]
        is_unknown = top1_conf < per_pixel_thresh

        for focus_idx, focus_name in [(paved_idx, "paved_road"), (roofing_idx, "dense_informal_roofing")]:
            mask = is_unknown & (top1_idx == focus_idx)
            n = int(mask.sum())
            if n == 0:
                print(f"  No unknown pixels with top1={focus_name} in this tile.")
                continue
            seconds = top2_idx[mask]
            counts = np.bincount(seconds, minlength=num_classes)
            print(f"\n  Unknown pixels with top1={focus_name} (n={n}) -- second-choice class breakdown:")
            order = np.argsort(-counts)
            for i in order:
                if counts[i] == 0:
                    continue
                pct = 100.0 * counts[i] / n
                print(f"    {categories[i]:<30} {counts[i]:>8}  ({pct:.1f}%)")

            pooled_second_choice[focus_idx] += counts
            pooled_n[focus_idx] += n

    print("\n" + "=" * 70)
    print("POOLED ACROSS ALL TILES")
    for focus_idx, focus_name in [(paved_idx, "paved_road"), (roofing_idx, "dense_informal_roofing")]:
        n = pooled_n[focus_idx]
        if n == 0:
            continue
        counts = pooled_second_choice[focus_idx]
        print(f"\n  Unknown pixels with top1={focus_name} (pooled n={n}):")
        order = np.argsort(-counts)
        other_member_idx = roofing_idx if focus_idx == paved_idx else paved_idx
        other_member_pct = 100.0 * counts[other_member_idx] / n
        for i in order:
            if counts[i] == 0:
                continue
            pct = 100.0 * counts[i] / n
            marker = "  <-- the other member of the suspected pair" if i == other_member_idx else ""
            print(f"    {categories[i]:<30} {counts[i]:>8}  ({pct:.1f}%){marker}")

    print("\n" + "=" * 70)
    print("INTERPRETATION")
    p_to_r = pooled_second_choice[paved_idx][roofing_idx] / max(pooled_n[paved_idx], 1) * 100
    r_to_p = pooled_second_choice[roofing_idx][paved_idx] / max(pooled_n[roofing_idx], 1) * 100
    print(f"  paved_road-unknowns whose 2nd choice is dense_informal_roofing: {p_to_r:.1f}%")
    print(f"  dense_informal_roofing-unknowns whose 2nd choice is paved_road: {r_to_p:.1f}%")
    if p_to_r > 40 and r_to_p > 40:
        print("\n  -> CONFIRMED confusion pair. The model genuinely can't cleanly separate")
        print("     these two classes in a large share of cases. This is fixable with:")
        print("       - targeted annotation of ambiguous paved/roofing boundary pixels")
        print("       - a boundary-aware or contrastive loss term between these two classes")
        print("       - potentially reviewing whether some 'ground truth' labels for these")
        print("         two classes are themselves inconsistent (annotator disagreement)")
    else:
        print("\n  -> NOT a clean confusion pair -- second choices are scattered.")
        print("     More consistent with each class independently being undertrained")
        print("     or having noisy/inconsistent ground truth labels.")


if __name__ == "__main__":
    main()