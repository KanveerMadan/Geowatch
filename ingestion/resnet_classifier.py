import json
import os
import numpy as np
import torch
from PIL import Image


# ── Model + threshold loading ──────────────────────────────────────────────

def load_production_model(
    checkpoint_path: str,
    caat_path: str,
    device: str = None,
):
    """
    Loads the production checkpoint and its matching CAAT thresholds.

    Returns a dict bundling everything inference needs:
        model, categories, num_classes, ignore_index, caat_thresholds,
        device, checkpoint_metadata (for logging/provenance)

    IMPORTANT: caat_path must be the CAAT file generated FOR this exact
    checkpoint (check 'source_checkpoint' inside it matches
    checkpoint_path) — CAAT thresholds computed against a different
    model's confidence distribution will silently miscalibrate the
    unknown/confident-prediction boundary. This was a real bug caught
    during development; don't skip this check.
    """
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        # CPU-only note: this model is much heavier than RemoteCLIP's
        # forward pass and runs sliding-window inference (many crops per
        # tile) — expect this to be slow on the Mac M3 CPU. Consider
        # keeping inference on a GPU-backed environment if latency matters,
        # or reducing tile resolution / increasing stride as a tradeoff.

    checkpoint = torch.load(checkpoint_path, map_location=device)

    with open(caat_path) as f:
        caat_data = json.load(f)

    if "source_checkpoint" not in caat_data or "thresholds" not in caat_data:
        raise ValueError(
            f"'{caat_path}' does not look like a verified CAAT file — missing "
            f"'source_checkpoint' and/or 'thresholds' keys. This is likely a stale "
            f"file from before the reload-and-verify fix (e.g. an old flat "
            f"{{category: threshold}} dict with no provenance). Recompute CAAT using "
            f"the self-contained reload cell, which tags its output with the "
            f"checkpoint it was verified against — never use an untagged CAAT file "
            f"in production, there's no way to confirm it matches this model."
        )

    if os.path.basename(caat_data["source_checkpoint"]) != os.path.basename(checkpoint_path):
        raise ValueError(
            f"CAAT thresholds file was computed for a different checkpoint "
            f"({caat_data['source_checkpoint']}) than the one being loaded "
            f"({checkpoint_path}). Recompute CAAT against this checkpoint before "
            f"using it in production — mismatched thresholds silently miscalibrate "
            f"confidence, they don't throw an obvious error at inference time."
        )

    caat_thresholds = caat_data["thresholds"]

    # Import here, not at module top, to avoid a hard dependency for any
    # code that only needs e.g. load_production_model for inspection
    from .resnet_model import GeoWatchResNetSeg  # adjust import path to
                                                   # wherever GeoWatchResNetSeg
                                                   # actually lives in your repo

    model = GeoWatchResNetSeg(num_classes=checkpoint["num_classes"], freeze_encoder=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    print(f"Loaded production model: {checkpoint.get('architecture', 'unknown')}")
    print(f"  Trained on: {checkpoint.get('training_cities')}")
    print(f"  LOCO validated: mean mIoU {checkpoint.get('loco_mean_miou')} "
          f"+/- {checkpoint.get('loco_std_miou')} ({checkpoint.get('loco_n_folds')} folds)")
    print(f"  CAAT thresholds loaded, source-verified against this checkpoint.")

    return {
        "model": model,
        "categories": checkpoint["categories"],
        "num_classes": checkpoint["num_classes"],
        "ignore_index": checkpoint["ignore_index"],
        "caat_thresholds": caat_thresholds,
        "device": device,
        "checkpoint_metadata": {
            "training_cities": checkpoint.get("training_cities"),
            "loco_mean_miou": checkpoint.get("loco_mean_miou"),
            "loco_std_miou": checkpoint.get("loco_std_miou"),
            "loco_n_folds": checkpoint.get("loco_n_folds"),
            "monitor_miou_at_save": checkpoint.get("monitor_miou_at_save"),
        },
    }


# ── Sliding-window per-pixel inference ─────────────────────────────────────

# Reserved value for "below CAAT threshold" / no confident prediction.
# Matches IGNORE_INDEX convention used throughout training — this is NOT
# the same as the model predicting a class, it means the prediction was
# rejected for being insufficiently confident in that specific class.
UNKNOWN_INDEX = 255


def run_pixel_inference(
    tile_path: str,
    model_bundle: dict,
    patch_size: int = 64,
    stride: int = 32,
    batch_size: int = 32,
) -> dict:
    """
    Runs sliding-window inference over the full tile, producing a real
    per-pixel land-cover class map.

    Overlapping windows (stride < patch_size, by design here) have their
    softmax probabilities AVERAGED per-pixel across every window that
    covers it, rather than letting the last window win outright — this
    smooths seams at window boundaries. Only after averaging is argmax
    + CAAT thresholding applied, once per pixel, using the final
    averaged confidence.

    Returns:
        {
            "class_map": (H, W) uint8 array, values 0..num_classes-1 or
                         UNKNOWN_INDEX (255)
            "confidence_map": (H, W) float32 array, the winning class's
                         averaged softmax probability at each pixel
                         (useful for debugging / a confidence overlay,
                         not required by result.json)
            "category_area_pct": {category_name: float 0-100} — % of
                         non-unknown pixels belonging to each class
            "unknown_pct": float 0-100 — % of all pixels rejected by CAAT
        }
    """
    model = model_bundle["model"]
    device = model_bundle["device"]
    categories = model_bundle["categories"]
    num_classes = model_bundle["num_classes"]
    caat_thresholds = model_bundle["caat_thresholds"]

    image = Image.open(tile_path).convert("RGB")
    tile_w, tile_h = image.size
    tile_arr = np.array(image, dtype=np.float32) / 255.0  # matches
    # GeoWatchDatasetResNet's normalization (no ImageNet mean/std) —
    # if that dataset class does anything else at train time, mirror
    # it here exactly or inference will be systematically miscalibrated.

    # Accumulators for averaging overlapping window predictions
    prob_sum = np.zeros((tile_h, tile_w, num_classes), dtype=np.float32)
    coverage_count = np.zeros((tile_h, tile_w), dtype=np.int32)

    # Collect window coordinates first, batch them for GPU efficiency
    coords = []
    for y in range(0, max(tile_h - patch_size, 0) + 1, stride):
        for x in range(0, max(tile_w - patch_size, 0) + 1, stride):
            coords.append((x, y))
    # Ensure the tile's right/bottom edges are covered even if
    # (tile_size - patch_size) isn't evenly divisible by stride
    if (tile_w - patch_size) % stride != 0:
        for y in range(0, max(tile_h - patch_size, 0) + 1, stride):
            coords.append((tile_w - patch_size, y))
    if (tile_h - patch_size) % stride != 0:
        for x in range(0, max(tile_w - patch_size, 0) + 1, stride):
            coords.append((x, tile_h - patch_size))
    coords = list(set(coords))  # de-dup any coords added twice by the edge fix

    print(f"Running inference: {len(coords)} windows, patch={patch_size}px, "
          f"stride={stride}px, tile={tile_w}x{tile_h}")

    with torch.no_grad():
        for batch_start in range(0, len(coords), batch_size):
            batch_coords = coords[batch_start:batch_start + batch_size]
            batch_crops = []
            for (x, y) in batch_coords:
                crop = tile_arr[y:y + patch_size, x:x + patch_size]
                batch_crops.append(crop)

            batch_tensor = torch.from_numpy(np.stack(batch_crops)).permute(0, 3, 1, 2).to(device)
            logits = model(batch_tensor)  # (B, C, patch, patch)
            probs = torch.softmax(logits, dim=1).cpu().numpy()  # (B, C, patch, patch)

            for i, (x, y) in enumerate(batch_coords):
                window_probs = probs[i].transpose(1, 2, 0)  # (patch, patch, C)
                prob_sum[y:y + patch_size, x:x + patch_size] += window_probs
                coverage_count[y:y + patch_size, x:x + patch_size] += 1

    # Average probabilities across however many windows covered each pixel
    coverage_count = np.maximum(coverage_count, 1)  # avoid div-by-zero on any gap
    avg_probs = prob_sum / coverage_count[:, :, None]

    pred_class = np.argmax(avg_probs, axis=2)  # (H, W)
    pred_conf = np.max(avg_probs, axis=2)      # (H, W) — winning class's confidence

    # ── Apply CAAT: per-pixel, using that pixel's PREDICTED class's own threshold ──
    class_map = pred_class.astype(np.uint8).copy()
    for class_idx, cat_name in enumerate(categories):
        threshold = caat_thresholds.get(cat_name, 0.5)
        below_threshold = (pred_class == class_idx) & (pred_conf < threshold)
        class_map[below_threshold] = UNKNOWN_INDEX

    # ── Summary stats ──
    total_px = tile_h * tile_w
    unknown_px = int((class_map == UNKNOWN_INDEX).sum())
    unknown_pct = 100.0 * unknown_px / total_px

    category_area_pct = {}
    known_px = total_px - unknown_px
    for class_idx, cat_name in enumerate(categories):
        count = int((class_map == class_idx).sum())
        category_area_pct[cat_name] = round(100.0 * count / known_px, 2) if known_px > 0 else 0.0

    print(f"Inference complete. Unknown/rejected: {unknown_pct:.1f}% of pixels.")
    print("Category area breakdown (% of confidently-classified pixels):")
    for cat, pct in sorted(category_area_pct.items(), key=lambda x: -x[1]):
        print(f"  {cat:28s} {pct:5.1f}%")

    return {
        "class_map": class_map,
        "confidence_map": pred_conf.astype(np.float32),
        "category_area_pct": category_area_pct,
        "unknown_pct": round(unknown_pct, 2),
    }


# ── Saving the per-pixel map for result.json to reference ─────────────────

def save_landcover_map(class_map: np.ndarray, output_path: str):
    """
    Saves the per-pixel class map as a single-channel indexed PNG.
    Values 0..num_classes-1 are real classes (see result.json's
    'categories' list for the index->name mapping); 255 is unknown.

    Lossless, compact, and directly renderable in the frontend as a
    colored overlay via a palette (App.jsx will need a small
    class_idx -> RGBA color map, same categories/order as the
    checkpoint's `categories` list).
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img = Image.fromarray(class_map, mode="L")  # 8-bit single channel
    img.save(output_path)
    print(f"Land-cover map saved: {output_path}")


