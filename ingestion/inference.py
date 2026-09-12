"""
GeoWatch Copilot — Path B inference module.

Replaces ingestion/classifier.py's classify_tile() (RemoteCLIP, Path A)
with real per-pixel prediction from the trained GeoWatchResNetSeg model
(ResNet50 SSL4EO-S12 MoCo encoder + DeepLabV3+-style decoder).

Model architecture reproduced EXACTLY from the training notebook cell
provided (ASPP / DeepLabDecoder / GeoWatchResNetSeg) — this must stay
byte-for-byte structurally identical to what geowatch_production_model.pth
was trained with, or load_state_dict() will fail or silently mismatch.
Do not "clean up" or refactor this architecture code without re-verifying
against the notebook.

Segment-level aggregation (dominant_landcover_category,
landcover_purity_pct) uses each segment's REAL per-pixel SAM mask shape,
not its bbox — via segmentation.py's decode_mask_rle() for serialized
masks.json entries, or directly from the in-memory 'segmentation' ndarray
when called inline during the same pipeline.py run right after
segment_tile() (the likely case, per the master project notes — no RLE
decode needed at all in that path). Bbox is used only as a last-resort
fallback if neither is present, and that case logs a loud warning since
it should not occur in normal operation.
"""

import os
import json
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

from torchgeo.models import ResNet50_Weights, resnet50

from ingestion.segmentation import decode_mask_rle


# ============================================================
# Model architecture — reproduced exactly from the training notebook.
# ============================================================

class ASPP(nn.Module):
    """Atrous Spatial Pyramid Pooling — standard DeepLabV3+ component."""

    def __init__(self, in_channels: int, out_channels: int = 256, rates=(1, 6, 12, 18)):
        super().__init__()
        self.branches = nn.ModuleList()
        for rate in rates:
            if rate == 1:
                self.branches.append(nn.Sequential(
                    nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
                    nn.BatchNorm2d(out_channels),
                    nn.ReLU(inplace=True),
                ))
            else:
                self.branches.append(nn.Sequential(
                    nn.Conv2d(in_channels, out_channels, kernel_size=3,
                              padding=rate, dilation=rate, bias=False),
                    nn.BatchNorm2d(out_channels),
                    nn.ReLU(inplace=True),
                ))
        self.pool = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )
        self.project = nn.Sequential(
            nn.Conv2d(out_channels * (len(rates) + 1), out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1),
        )

    def forward(self, x):
        size = x.shape[-2:]
        feats = [branch(x) for branch in self.branches]
        pooled = self.pool(x)
        pooled = F.interpolate(pooled, size=size, mode='bilinear', align_corners=False)
        feats.append(pooled)
        x = torch.cat(feats, dim=1)
        return self.project(x)


class DeepLabDecoder(nn.Module):
    """DeepLabV3+ decoder: ASPP on high-level features fused with a
    low-level skip connection for boundary detail, upsampled to input res."""

    def __init__(self, low_level_channels: int, high_level_channels: int,
                 num_classes: int, aspp_channels: int = 256, low_level_proj: int = 48):
        super().__init__()
        self.aspp = ASPP(high_level_channels, out_channels=aspp_channels)
        self.low_level_proj = nn.Sequential(
            nn.Conv2d(low_level_channels, low_level_proj, kernel_size=1, bias=False),
            nn.BatchNorm2d(low_level_proj),
            nn.ReLU(inplace=True),
        )
        self.fuse = nn.Sequential(
            nn.Conv2d(aspp_channels + low_level_proj, aspp_channels, kernel_size=3,
                      padding=1, bias=False),
            nn.BatchNorm2d(aspp_channels),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Conv2d(aspp_channels, aspp_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(aspp_channels),
            nn.ReLU(inplace=True),
            nn.Dropout(0.1),
        )
        self.classifier = nn.Conv2d(aspp_channels, num_classes, kernel_size=1)

    def forward(self, low_level_feat, high_level_feat, target_size):
        x = self.aspp(high_level_feat)
        x = F.interpolate(x, size=low_level_feat.shape[-2:], mode='bilinear', align_corners=False)
        low = self.low_level_proj(low_level_feat)
        x = torch.cat([x, low], dim=1)
        x = self.fuse(x)
        x = self.classifier(x)
        x = F.interpolate(x, size=target_size, mode='bilinear', align_corners=False)
        return x


class GeoWatchResNetSeg(nn.Module):
    """ResNet50 encoder (torchgeo SSL4EO-S12 MoCo, Sentinel-2 RGB pretrained)
    + DeepLabV3+-style decoder. Reproduced exactly from the training notebook
    so that geowatch_production_model.pth's state_dict loads cleanly."""

    def __init__(self, num_classes: int = 7, freeze_encoder: bool = False):
        super().__init__()

        # weights=None here — at inference time we ALWAYS overwrite with the
        # production checkpoint's state_dict, so downloading pretrained
        # SSL4EO-S12 weights first would be redundant. See load_production_model().
        self.encoder = resnet50(weights=None)

        self._features = {}
        self.encoder.layer1.register_forward_hook(self._hook('low'))
        self.encoder.layer3.register_forward_hook(self._hook('high'))

        if freeze_encoder:
            for param in self.encoder.parameters():
                param.requires_grad = False

        self.decoder = DeepLabDecoder(
            low_level_channels=256,
            high_level_channels=1024,
            num_classes=num_classes,
        )

    def _hook(self, name):
        def fn(module, input, output):
            self._features[name] = output
        return fn

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        target_size = pixel_values.shape[-2:]
        self.encoder.forward_features(pixel_values) if hasattr(self.encoder, 'forward_features') \
            else self.encoder(pixel_values)
        low = self._features['low']
        high = self._features['high']
        return self.decoder(low, high, target_size)


# ============================================================
# Category color palette — C31 / build item 43.
#
# This used to be a literal dict here, above a comment reading "must match
# App.jsx's CAT_COLORS ... exactly, so the frontend legend and the PNG overlay
# agree visually." A Python comment asserting a JavaScript constant: S3, "a rule
# enforced only by prose fails at the first edit made by someone who did not
# read the prose." It failed on all 8 of 8, worst case Δ(34, 37, 75).
#
# The values now live in configs/palette.py and reach the frontend by being
# emitted into result.json, not by being retyped. The names below are re-exported
# unchanged so existing callers (generate_rgb_preview_tiles, the PNG writer)
# keep working untouched.
# ============================================================

from configs.palette import (  # noqa: E402
    CATEGORY_COLORS_RGB,
    UNKNOWN_COLOR_RGB,
    UNKNOWN_INDEX,
)

PATCH_SIZE = 64   # must match training patch size (build_sam_patches / GeoWatchDatasetResNet)

# ============================================================
# Known confusion pairs — informed by Phase 3 LOCO confusion matrix
# analysis (see loco_confusion_export.json). Pixels landing close
# between these specific pairs get flagged as ambiguous rather than
# silently painted with one confident-looking color. Extend this list
# as further confusion-matrix analysis identifies new pairs.
# ============================================================
CONFUSION_PAIRS = [
    frozenset({"paved_road", "dense_informal_roofing"}),
    frozenset({"standing_water", "dense_vegetation"}),
]
AMBIGUITY_MARGIN = 0.15  # top1_prob - top2_prob below this => ambiguous. Tunable, not yet validated empirically.
ROAD_PROXIMITY_PENALTY_STRENGTH = 0.3  # max confidence reduction for paved_road
WATERWAY_PROXIMITY_PENALTY_STRENGTH = 0.2  # weaker than road's 0.3 -- OSM water

def get_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_production_model(checkpoint_path: str, device: str = None):
    """
    Load the trained GeoWatchResNetSeg checkpoint.

    Expects the checkpoint dict shape saved by the production training
    script:
        model_state_dict, categories, num_classes, ignore_index,
        class_weights, training_cities, loco_mean_miou, loco_std_miou,
        loco_n_folds, architecture, ...

    Returns:
        (model, categories, num_classes) — model in eval() mode on `device`
    """
    if device is None:
        device = get_device()

    if not os.path.exists(checkpoint_path):
        raise FileNotFoundError(f"Production checkpoint not found: {checkpoint_path}")

    checkpoint = torch.load(checkpoint_path, map_location=device)

    if "model_state_dict" not in checkpoint or "categories" not in checkpoint:
        raise ValueError(
            f"Checkpoint at {checkpoint_path} is missing required keys "
            f"('model_state_dict', 'categories'). Got keys: {list(checkpoint.keys())}. "
            f"Refusing to load a checkpoint that doesn't match the expected contract — "
            f"this is exactly the kind of mismatch that caused the CAAT file issue."
        )

    categories = checkpoint["categories"]
    num_classes = checkpoint.get("num_classes", len(categories))

    model = GeoWatchResNetSeg(num_classes=num_classes, freeze_encoder=False)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()

    print(f"Loaded production model: {checkpoint.get('architecture', 'unknown architecture')}")
    print(f"Categories ({num_classes}): {categories}")
    print(f"Trained on cities: {checkpoint.get('training_cities', 'unknown')}")
    print(f"LOCO mean mIoU (real generalization number): "
          f"{checkpoint.get('loco_mean_miou', 'unknown')} "
          f"(+/- {checkpoint.get('loco_std_miou', '?')}, "
          f"{checkpoint.get('loco_n_folds', '?')} folds)")
    print(f"NOTE: monitor_miou_at_save ({checkpoint.get('monitor_miou_at_save', '?')}) is NOT "
          f"a generalization metric — it's a random-split monitoring number. "
          f"Do not quote it as the model's real performance.")

    return model, categories, num_classes


def load_caat_thresholds(thresholds_path: str, categories: list) -> np.ndarray:
    """
    Load per-class CAAT confidence thresholds and return them as a numpy
    array in the SAME index order as `categories`, so array indexing
    lines up directly with model output channels.

    Raises if a category is missing from the thresholds file, or if the
    thresholds file has extra/unexpected categories — a silent order
    mismatch here would misapply every threshold.
    """
    if not os.path.exists(thresholds_path):
        raise FileNotFoundError(f"CAAT thresholds file not found: {thresholds_path}")

    with open(thresholds_path) as f:
        data = json.load(f)

    raw_thresholds = data["thresholds"]

    missing = [c for c in categories if c not in raw_thresholds]
    if missing:
        raise ValueError(
            f"CAAT thresholds file is missing categories: {missing}. "
            f"Checkpoint categories: {categories}. Thresholds file categories: "
            f"{list(raw_thresholds.keys())}."
        )

    extra = [c for c in raw_thresholds if c not in categories]
    if extra:
        raise ValueError(
            f"CAAT thresholds file has categories not in the checkpoint: {extra}. "
            f"This suggests the thresholds file doesn't match this model checkpoint — "
            f"refusing to proceed rather than silently ignoring the mismatch."
        )

    thresholds_arr = np.array([raw_thresholds[c] for c in categories], dtype=np.float32)
    print(f"Loaded CAAT thresholds (source_checkpoint={data.get('source_checkpoint', '?')}, "
          f"verified_sanity_check_miou={data.get('verified_sanity_check_miou', '?')}):")
    for cat, t in zip(categories, thresholds_arr):
        print(f"  {cat:28s} {t:.4f}")

    return thresholds_arr


# ============================================================
# Sliding-window per-pixel inference
# ============================================================

def compute_area_stats(landcover_map: np.ndarray, ambiguity_map: np.ndarray, categories: list) -> dict:
    """
    PHASE 2: extracted from run_inference() so pipeline.py can call this
    on a MOSAICKED full-AOI landcover_map/ambiguity_map (multiple tiles
    combined), not just a single tile's. Identical math either way --
    single-tile behavior is unchanged.
    """
    H, W = landcover_map.shape
    total_px = H * W
    known_mask = landcover_map != UNKNOWN_INDEX
    known_px = int(known_mask.sum())
    unknown_pct = round(100.0 * (total_px - known_px) / total_px, 2)

    category_area_pct = {}
    for i, cat in enumerate(categories):
        cat_px = int((landcover_map == i).sum())
        category_area_pct[cat] = round(100.0 * cat_px / total_px, 2)

    ambiguous_px = int((ambiguity_map > 0).sum())
    ambiguous_pct = round(100.0 * ambiguous_px / total_px, 2)
    ambiguous_pct_by_pair = {}
    for pair_num, pair in enumerate(CONFUSION_PAIRS, start=1):
        names = list(pair)
        key = "|".join(sorted(names))
        px = int((ambiguity_map == pair_num).sum())
        ambiguous_pct_by_pair[key] = round(100.0 * px / total_px, 2)

    return {
        "category_area_pct": category_area_pct,
        "unknown_pct": unknown_pct,
        "ambiguous_pct": ambiguous_pct,
        "ambiguous_pct_by_pair": ambiguous_pct_by_pair,
    }

def run_inference(
    tile_path: str,
    model: nn.Module,
    categories: list,
    caat_thresholds: np.ndarray,
    device: str = None,
    patch_size: int = PATCH_SIZE,
    stride: int = None,
    road_dist_map: np.ndarray = None,
    waterway_dist_map: np.ndarray = None,
) -> dict:
    """
    Run sliding-window per-pixel inference over a full tile.

    Overlapping windows (stride < patch_size) have their softmax
    probabilities averaged before the final argmax + CAAT threshold
    decision — this smooths tile-seam artifacts, standard practice for
    patch-based dense prediction.

    Per-pixel decision rule (CAAT):
        predicted_class = argmax(mean_softmax)
        if mean_softmax[predicted_class] < caat_thresholds[predicted_class]:
            final_class = UNKNOWN_INDEX (255)
        else:
            final_class = predicted_class

    This replaces the old flat UNKNOWN_THRESHOLD=0.20 cosine cutoff
    (tuned for RemoteCLIP's embedding space) with per-class thresholds
    calibrated for this model's actual confidence behavior.

    Args:
        tile_path: path to the tile PNG/TIF (RGB)
        model: loaded GeoWatchResNetSeg, eval mode
        categories: category names in model output-channel order
        caat_thresholds: per-class thresholds, same order as categories
        device: 'cuda' or 'cpu'
        patch_size: sliding window size (must match training — 64)
        stride: window stride; defaults to patch_size // 2 (50% overlap)

    Returns:
        dict with:
            landcover_map: (H, W) uint8 array — category index, or
                           UNKNOWN_INDEX (255) where confidence too low
            confidence_map: (H, W) float32 array — the winning class's
                            mean softmax probability at each pixel
            category_area_pct: dict {category: pct} — % of TOTAL pixels
                                (sums with unknown_pct to 100%; see fix
                                note below)
            unknown_pct: float — pct of pixels labeled unknown
    """
    if device is None:
        device = get_device()
    if stride is None:
        stride = patch_size // 2

    image = Image.open(tile_path).convert("RGB")
    img_arr = np.array(image, dtype=np.float32) / 255.0  # matches GeoWatchDatasetResNet: /255 only, no mean/std
    H, W, _ = img_arr.shape
    if road_dist_map is not None and road_dist_map.shape != (H, W):
        print(f"WARNING: road_dist_map shape {road_dist_map.shape} != tile shape {(H,W)} — skipping road proximity adjustment.")
        road_dist_map = None
    if waterway_dist_map is not None and waterway_dist_map.shape != (H, W):
        print(f"WARNING: waterway_dist_map shape {waterway_dist_map.shape} != tile shape {(H,W)} — skipping waterway proximity adjustment.")
        waterway_dist_map = None
    num_classes = len(categories)

    prob_accum = np.zeros((num_classes, H, W), dtype=np.float32)
    count_accum = np.zeros((H, W), dtype=np.float32)

    # Generate window top-left coordinates, always including the final
    # row/col so the right/bottom edges of the tile are covered even if
    # (H - patch_size) isn't a clean multiple of stride.
    ys = list(range(0, max(H - patch_size, 0) + 1, stride))
    xs = list(range(0, max(W - patch_size, 0) + 1, stride))
    if not ys or ys[-1] != H - patch_size:
        ys.append(max(H - patch_size, 0))
    if not xs or xs[-1] != W - patch_size:
        xs.append(max(W - patch_size, 0))

    print(f"Running sliding-window inference: tile {W}x{H}, patch {patch_size}, "
          f"stride {stride}, {len(ys) * len(xs)} windows.")

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

                # Pad any undersized edge patch up to patch_size, run
                # inference, then crop the prediction back down before
                # accumulating — keeps the model input shape consistent
                # with training without distorting edge predictions.
                if ph < patch_size or pw < patch_size:
                    padded = np.zeros((patch_size, patch_size, 3), dtype=np.float32)
                    padded[:ph, :pw, :] = patch
                    patch_in = padded
                else:
                    patch_in = patch

                tensor = torch.from_numpy(patch_in).permute(2, 0, 1).unsqueeze(0).to(device)
                logits = model(tensor)  # (1, num_classes, patch_size, patch_size)
                probs = F.softmax(logits, dim=1).squeeze(0).cpu().numpy()  # (num_classes, patch_size, patch_size)
                probs = probs[:, :ph, :pw]

                prob_accum[:, y1:y1 + ph, x1:x1 + pw] += probs
                count_accum[y1:y1 + ph, x1:x1 + pw] += 1.0

    count_accum = np.maximum(count_accum, 1e-6)
    mean_probs = prob_accum / count_accum[None, :, :]  # (num_classes, H, W)
    # ── NEW: OSM road-proximity confidence adjustment (Phase 3 item #1) ──
    # Discounts paved_road's predicted probability for pixels far from any
    # real OSM road geometry -- soft penalty, not a hard override, since
    # OSM road coverage in informal settlements is known-incomplete (a
    # missing OSM road does not mean a real road doesn't exist there).
    # Only paved_road's channel is touched; every other class's
    # probability is left as-is. This runs BEFORE argmax so it can
    # actually change the winning class, not just cosmetically lower a
    # confidence number after the decision is already made.
    if road_dist_map is not None and "paved_road" in categories:
        road_idx = categories.index("paved_road")
        # road_dist_map: 0=on a real road, 1=farthest from any real road
        penalty = 1.0 - (ROAD_PROXIMITY_PENALTY_STRENGTH * road_dist_map)
        mean_probs[road_idx, :, :] = mean_probs[road_idx, :, :] * penalty
    if waterway_dist_map is not None and "standing_water" in categories:
        water_idx = categories.index("standing_water")
        penalty = 1.0 - (WATERWAY_PROXIMITY_PENALTY_STRENGTH * waterway_dist_map)
        mean_probs[water_idx, :, :] = mean_probs[water_idx, :, :] * penalty

    predicted_idx = np.argmax(mean_probs, axis=0)  # (H, W)
    predicted_conf = np.take_along_axis(
        mean_probs, predicted_idx[None, :, :], axis=0
    ).squeeze(0)  # (H, W)

    per_pixel_threshold = caat_thresholds[predicted_idx]  # (H, W), gathers each pixel's own class threshold
    landcover_map = np.where(
        predicted_conf >= per_pixel_threshold,
        predicted_idx,
        UNKNOWN_INDEX,
    ).astype(np.uint8)

    confidence_map = predicted_conf.astype(np.float32)
    # ── NEW: second-best class per pixel, for ambiguity detection ──
    mean_probs_masked = mean_probs.copy()
    np.put_along_axis(mean_probs_masked, predicted_idx[None, :, :], -1.0, axis=0)
    second_idx = np.argmax(mean_probs_masked, axis=0)
    second_conf = np.take_along_axis(
        mean_probs_masked, second_idx[None, :, :], axis=0
    ).squeeze(0)

    margin = predicted_conf - second_conf

    cat_to_idx = {c: i for i, c in enumerate(categories)}
    pair_lookup = {}
    for pair_num, pair in enumerate(CONFUSION_PAIRS, start=1):
        names = list(pair)
        if len(names) != 2:
            continue
        if names[0] not in cat_to_idx or names[1] not in cat_to_idx:
            continue
        ia, ib = cat_to_idx[names[0]], cat_to_idx[names[1]]
        pair_lookup[(ia, ib)] = pair_num
        pair_lookup[(ib, ia)] = pair_num

    ambiguity_map = np.zeros((H, W), dtype=np.uint8)
    close_enough = margin < AMBIGUITY_MARGIN
    for (ia, ib), pair_num in pair_lookup.items():
        is_this_pair = (predicted_idx == ia) & (second_idx == ib)
        ambiguity_map[close_enough & is_this_pair] = pair_num

    stats = compute_area_stats(landcover_map, ambiguity_map, categories)
    print(f"Inference complete. Unknown: {stats['unknown_pct']}% of pixels.")
    print(f"Ambiguous (torn between known confusion pairs): {stats['ambiguous_pct']}% of pixels.")
    for key, pct in stats['ambiguous_pct_by_pair'].items():
        print(f"  {key:50s} {pct:.2f}%")
    print("Category area breakdown (% of TOTAL pixels; sums with unknown_pct to 100%):")
    for cat, pct in sorted(stats['category_area_pct'].items(), key=lambda kv: -kv[1]):
        print(f"  {cat:28s} {pct:.2f}%")
    _sum_check = round(sum(stats['category_area_pct'].values()) + stats['unknown_pct'], 2)
    if abs(_sum_check - 100.0) > 0.5:
        print(f"  WARNING: category_area_pct + unknown_pct = {_sum_check}%, expected ~100%")

    return {
        "landcover_map": landcover_map,
        "confidence_map": confidence_map,
        "ambiguity_map": ambiguity_map,
        **stats,
    }

def save_landcover_outputs(
    inference_result: dict,
    categories: list,
    run_dir: str,
    map_filename: str = "landcover.png",
    confidence_filename: str = "landcover_confidence.png",
) -> dict:
    """
    Save the per-pixel landcover map as a color-coded PNG (matching
    App.jsx's palette) and the confidence map as a grayscale PNG.

    Returns dict with the two relative filenames, for embedding directly
    into result.json's "landcover" block.
    """
    landcover_map = inference_result["landcover_map"]
    confidence_map = inference_result["confidence_map"]
    H, W = landcover_map.shape

    # ── Color-coded category map ──
    rgb = np.zeros((H, W, 3), dtype=np.uint8)
    for i, cat in enumerate(categories):
        color = CATEGORY_COLORS_RGB.get(cat, (128, 128, 128))
        rgb[landcover_map == i] = color
    rgb[landcover_map == UNKNOWN_INDEX] = UNKNOWN_COLOR_RGB

    map_path = os.path.join(run_dir, map_filename)
    Image.fromarray(rgb, mode="RGB").save(map_path)

    # ── Confidence map, grayscale 0-255 ──
    conf_u8 = np.clip(confidence_map * 255.0, 0, 255).astype(np.uint8)
    conf_path = os.path.join(run_dir, confidence_filename)
    Image.fromarray(conf_u8, mode="L").save(conf_path)

    print(f"Saved landcover map: {map_path}")
    print(f"Saved confidence map: {conf_path}")

    return {
        "map_path": map_filename,
        "confidence_map_path": confidence_filename,
    }


# ============================================================
# Segment-level convenience aggregation (majority vote lookup)
# ============================================================

def _segment_pixel_indices(mask_entry: dict, landcover_map_shape):
    """
    Return the (y, x) pixel index arrays for a segment's REAL per-pixel
    shape -- not its bounding box.

    Supports two input shapes, checked in order of preference:

    1. In-memory SAM output (mask_entry["segmentation"] is an ndarray) --
       this is the fast path. Per the master project notes, pipeline.py's
       Step 6 runs in the same function scope as Step 3's SAM
       segmentation call, so the real boolean masks are very likely
       still in memory at classification time and never need RLE
       decoding at all. If you're calling this from within pipeline.py
       right after segment_tile(), this is the path that will be used.

    2. Serialized masks.json entry (mask_entry["mask_rle"] present,
       COCO-style column-major as produced by segmentation.py's
       encode_mask_rle) -- decoded via segmentation.py's decode_mask_rle.
       Use this path if you're running inference standalone / re-processing
       a saved run rather than inline during the same pipeline execution.

    3. Bbox fallback -- only if neither of the above is present. This
       should not happen in the normal pipeline flow; it's kept only so
       a malformed/older masks.json entry degrades to something rather
       than crashing. Logged loudly if hit, since it means real mask data
       was expected but unavailable for this segment.
    """
    H, W = landcover_map_shape

    seg_mask = mask_entry.get("segmentation")
    if seg_mask is not None and isinstance(seg_mask, np.ndarray):
        yy, xx = np.where(seg_mask)
        return yy, xx

    rle = mask_entry.get("mask_rle")
    if rle is not None:
        decoded = decode_mask_rle(rle)
        yy, xx = np.where(decoded)
        return yy, xx

    print(f"WARNING: segment_id={mask_entry.get('segment_id', '?')} has no real mask "
          f"('segmentation' or 'mask_rle') -- falling back to bbox rectangle. "
          f"This should not happen for masks produced by the current pipeline; "
          f"check that masks.json / in-memory masks are being passed correctly.")
    x, y, w, h = mask_entry["bbox"]
    x1, y1 = max(0, int(x)), max(0, int(y))
    x2, y2 = min(W, int(x + w)), min(H, int(y + h))
    if x2 <= x1 or y2 <= y1:
        return np.array([], dtype=int), np.array([], dtype=int)
    yy, xx = np.meshgrid(np.arange(y1, y2), np.arange(x1, x2), indexing="ij")
    return yy.ravel(), xx.ravel()


def build_segments_with_landcover(
    masks: list,
    landcover_map: np.ndarray,
    categories: list,
    road_access_scores: dict = None,
    ambiguity_map: np.ndarray = None,
) -> list:
    """
    Build the new, slimmed-down segments[] list for result.json.

    Each segment keeps only: segment_id, bbox, area, road_access_score,
    dominant_landcover_category, landcover_purity_pct. All RemoteCLIP-era
    fields (category, confidence, crop_top_category, crop_confidence,
    all_scores, softmax_probs, crop_scores, crop_softmax_probs,
    label_source, annotation_priority) are dropped — none of them map to
    a real per-pixel model's output.

    dominant_landcover_category / landcover_purity_pct are computed via
    majority vote of landcover_map pixels within the segment's REAL mask
    shape (see _segment_pixel_indices — uses in-memory 'segmentation'
    ndarray if present, else decodes 'mask_rle', else bbox as a last-resort
    fallback that should not normally trigger).

    NEW (Phase 3 item #2, ambiguity flagging): if ambiguity_map is passed,
    each segment also gets:
        ambiguous_pct: float -- % of this segment's pixels flagged
                       ambiguous (any known confusion pair)
        ambiguous_between: [class_a, class_b] or None -- the confusion
                       pair this segment is MOST affected by, if
                       ambiguous_pct is non-trivial (>10%). None if the
                       segment is not meaningfully ambiguous, or if
                       ambiguity_map was not provided.

    Args:
        masks: SAM mask list. Either the original in-memory output from
               segment_tile() (has real 'segmentation' ndarray per entry —
               the fast path, no RLE decode needed) or masks.json entries
               (has 'mask_rle' instead — will be decoded).
        landcover_map: (H, W) uint8 array from run_inference()
        categories: category names in landcover_map index order
        road_access_scores: optional dict {segment_id: score}, computed
                             the same way as before (untouched by this change)
        ambiguity_map: optional (H, W) uint8 array from run_inference(),
                        same shape as landcover_map

    Returns:
        list of segment dicts, new slimmed schema
    """
    H, W = landcover_map.shape
    segments = []

    for i, mask in enumerate(masks):
        x, y, w, h = mask["bbox"]
        if w < 8 or h < 8:
            continue

        yy, xx = _segment_pixel_indices(mask, (H, W))
        if len(yy) == 0:
            dominant_cat = "unknown"
            purity_pct = 0.0
        else:
            px_vals = landcover_map[yy, xx]
            known_vals = px_vals[px_vals != UNKNOWN_INDEX]
            if len(known_vals) == 0:
                dominant_cat = "unknown"
                purity_pct = 0.0
            else:
                counts = np.bincount(known_vals.astype(int), minlength=len(categories))
                top_idx = int(np.argmax(counts))
                dominant_cat = categories[top_idx]
                purity_pct = round(100.0 * counts[top_idx] / len(px_vals), 2)

        seg = {
            "segment_id": i,
            "bbox": mask["bbox"],
            "area": mask["area"],
            "dominant_landcover_category": dominant_cat,
            "landcover_purity_pct": purity_pct,
        }

        # ── NEW: segment-level ambiguity ──
        if ambiguity_map is not None and len(yy) > 0:
            amb_vals = ambiguity_map[yy, xx]
            amb_px = int((amb_vals > 0).sum())
            amb_pct = round(100.0 * amb_px / len(yy), 2)
            seg["ambiguous_pct"] = amb_pct
            if amb_pct > 10.0:
                pair_counts = np.bincount(amb_vals[amb_vals > 0].astype(int),
                                           minlength=len(CONFUSION_PAIRS) + 1)
                dominant_pair_num = int(np.argmax(pair_counts))
                if dominant_pair_num > 0:
                    seg["ambiguous_between"] = sorted(list(CONFUSION_PAIRS[dominant_pair_num - 1]))
                else:
                    seg["ambiguous_between"] = None
            else:
                seg["ambiguous_between"] = None
        else:
            seg["ambiguous_pct"] = 0.0
            seg["ambiguous_between"] = None

        if road_access_scores is not None:
            seg["road_access_score"] = road_access_scores.get(i, -1.0)

        segments.append(seg)

    return segments