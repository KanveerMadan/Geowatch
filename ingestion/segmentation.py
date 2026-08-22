import numpy as np
import torch
from PIL import Image
from segment_anything import sam_model_registry, SamAutomaticMaskGenerator
import os
import json


def get_device() -> str:
    return "cpu"


def load_sam(model_path: str = "models/sam/sam_vit_b.pth") -> SamAutomaticMaskGenerator:
    device = get_device()
    print(f"Loading SAM on device: {device}")
    sam = sam_model_registry["vit_b"](checkpoint=model_path)
    sam.to(device=device)
    torch.set_default_dtype(torch.float32)
    mask_generator = SamAutomaticMaskGenerator(
        model=sam,
        points_per_side=16,
        pred_iou_thresh=0.88,
        stability_score_thresh=0.92,
        min_mask_region_area=500,
    )
    print("SAM loaded successfully.")
    return mask_generator


def segment_tile(tile_path: str, mask_generator: SamAutomaticMaskGenerator) -> list:
    image = np.array(Image.open(tile_path).convert("RGB"))
    torch.set_default_dtype(torch.float32)
    masks = mask_generator.generate(image)
    masks = sorted(masks, key=lambda x: x["area"], reverse=True)
    print(f"Tile: {os.path.basename(tile_path)} -> {len(masks)} segments found.")
    return masks


def encode_mask_rle(mask: np.ndarray) -> dict:
    """
    RLE-encode a boolean HxW mask (COCO-style, column-major).
    Compact and exact -- unlike bbox, this recovers the real segment
    shape, not just its rectangle. No pycocotools dependency needed --
    this is a small self-contained encoder/decoder pair.
    """
    h, w = mask.shape
    flat = mask.T.flatten()  # column-major, COCO convention
    runs = []
    prev = 0
    count = 0
    for val in flat:
        v = int(val)
        if v == prev:
            count += 1
        else:
            runs.append(count)
            count = 1
            prev = v
    runs.append(count)
    return {"size": [h, w], "counts": runs}


def decode_mask_rle(rle: dict) -> np.ndarray:
    """Inverse of encode_mask_rle -- returns the boolean HxW mask."""
    h, w = rle["size"]
    counts = rle["counts"]
    flat = np.zeros(h * w, dtype=bool)
    idx = 0
    val = False
    for c in counts:
        if val:
            flat[idx:idx + c] = True
        idx += c
        val = not val
    return flat.reshape(w, h).T  # undo column-major flatten


def save_masks(masks: list, output_path: str):
    """
    Save mask metadata AND the real per-pixel mask (RLE-encoded) so
    downstream annotation/training can recover actual segment shape,
    not just a bounding box.

    CHANGED: previously excluded m["segmentation"] entirely. Now
    RLE-encodes it -- adds a few KB per tile, not the megabytes a raw
    boolean array would cost, and is exact (lossless) unlike any
    box-based approximation.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    serializable = []
    for i, m in enumerate(masks):
        entry = {
            "segment_id": i,
            "area": int(m["area"]),
            "bbox": m["bbox"],
            "predicted_iou": float(m["predicted_iou"]),
            "stability_score": float(m["stability_score"]),
        }
        if "segmentation" in m and isinstance(m["segmentation"], np.ndarray):
            entry["mask_rle"] = encode_mask_rle(m["segmentation"])
        serializable.append(entry)

    with open(output_path, "w") as f:
        json.dump(serializable, f, indent=2)

    print(f"Mask metadata + RLE masks saved: {output_path}")


def visualize_masks(tile_path: str, masks: list, output_path: str):
    from PIL import ImageDraw
    import random
    image = Image.open(tile_path).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for mask in masks:
        x, y, w, h = mask["bbox"]
        color = (random.randint(50, 255), random.randint(50, 255),
                  random.randint(50, 255), 80)
        draw.rectangle([x, y, x + w, y + h], outline=color, width=1)
    combined = Image.alpha_composite(image, overlay).convert("RGB")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    combined.save(output_path)
    print(f"Visualization saved: {output_path}")