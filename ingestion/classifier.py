import torch
import open_clip
import numpy as np
from PIL import Image
import os
import json


# All 10 locked categories (product-level, per master prompt Section 5).
# NOTE: this dict is retained in full for reference/documentation purposes
# (e.g. so anyone reading this file can see the complete taxonomy), but
# classify_tile() below does NOT use it directly for scoring. See
# ML_CATEGORIES / ML_CATEGORY_NAMES.
CATEGORIES = {
    "dense_informal_roofing": [
        "densely packed corrugated metal rooftops satellite imagery",
        "high density slum rooftops overhead view",
        "closely packed tin sheet roofs aerial remote sensing",
        "informal urban settlement dense rooftop coverage satellite",
    ],
    "sparse_informal_roofing": [
        "scattered corrugated metal rooftops satellite view",
        "low density informal housing rooftops aerial",
        "sparse tin roof structures remote sensing imagery",
        "informal settlement periphery rooftops overhead",
    ],
    "unpaved_dirt_road": [
        "unpaved dirt road aerial view",
        "narrow dirt path between buildings satellite imagery",
        "unpaved lane in informal settlement from above",
    ],
    "paved_road": [
        "paved asphalt road satellite view",
        "concrete road aerial imagery",
        "tarmac street from above",
    ],
    "open_drainage_channel": [
        "open drainage channel satellite view",
        "concrete lined drainage canal aerial view",
        "stormwater drain between buildings from above",
    ],
    "standing_water": [
        "standing water flooding satellite view",
        "waterlogged area aerial imagery",
        "stagnant water pool from above",
    ],
    "vegetation_clearing": [
        "cleared vegetation land satellite view",
        "deforested area before construction aerial view",
        "bare cleared land at urban edge from above",
    ],
    "active_construction": [
        "active construction site satellite view",
        "building under construction aerial imagery",
        "new construction foundation from above",
    ],
    "dense_vegetation": [
        "dense green vegetation urban area satellite view",
        "park or green space aerial imagery",
        "trees and vegetation from above",
    ],
    "open_waste": [
        "open waste dump satellite view",
        "garbage field aerial imagery",
        "debris and waste ground from above",
    ],
}

# Categories physically unresolvable at Sentinel-2 10m resolution
# (per master prompt Section 5/6/9). These are NEVER scored by RemoteCLIP —
# they are assigned exclusively by apply_osm_vector_labels() in osm_dem.py,
# using OSM vector proximity, not spectral/ML classification.
#
# Prior bug: these 3 were previously included in the CLIP text-prompt set,
# which meant they competed directly against the 7 ML-resolvable categories
# in the argmax. Their prompts ("narrow dirt path between buildings",
# "debris and waste ground") describe generic visually-busy texture that
# wins against almost anything in a dense informal-settlement scene,
# regardless of what's actually in the crop. This caused dominant_category
# to be "unpaved_dirt_road" or "open_waste" in every one of the 5 newly
# added cities (Dhaka, Lagos, Accra, Cape Town, Guatemala), independent of
# what each AOI was actually chosen to capture. Fixed by excluding them
# from the ML scoring set entirely.
OSM_ONLY_CATEGORIES = {"unpaved_dirt_road", "open_drainage_channel", "open_waste"}

# The 7 categories RemoteCLIP is actually allowed to vote on.
ML_CATEGORIES = {k: v for k, v in CATEGORIES.items() if k not in OSM_ONLY_CATEGORIES}
ML_CATEGORY_NAMES = list(ML_CATEGORIES.keys())

# Retained for any code that still references the full 10-category list
# (e.g. documentation, result.json schema, frontend display order).
CATEGORY_NAMES = list(CATEGORIES.keys())

# Segments with top raw cosine below this threshold are labeled "unknown"
# instead of being forced into a wrong category. Also the entry point for
# OSM-only categories: a segment starts as "unknown" from ML, and
# apply_osm_vector_labels() then decides whether it's actually
# unpaved_dirt_road / open_drainage_channel / open_waste based on OSM
# proximity, not spectral score.
UNKNOWN_THRESHOLD = 0.20


def get_device() -> str:
    # CPU only — MPS has float64 issues with open_clip on M3
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def load_remoteclip(model_name: str = "ViT-L-14") -> tuple:
    """
    Load RemoteCLIP ViT-L-14 pretrained on RS5M satellite dataset.
    Repo: chendelong/RemoteCLIP on HuggingFace.

    Note: QuickGELU mismatch warning from open_clip is harmless —
    it's a config flag difference, not a weight error.

    Note: the "No pretrained weights loaded ... initialized randomly"
    warning that prints during create_model_and_transforms() is expected
    and correct — pretrained=None deliberately skips OpenAI weights so
    that RemoteCLIP's own state dict (loaded explicitly below) is the only
    thing populating the model. Do not change pretrained to "openai".
    """
    import huggingface_hub

    device = get_device()
    print(f"Loading RemoteCLIP on device: {device}")

    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-L-14",
        pretrained=None
    )
    tokenizer = open_clip.get_tokenizer("ViT-L-14")

    checkpoint_path = huggingface_hub.hf_hub_download(
        repo_id="chendelong/RemoteCLIP",
        filename="RemoteCLIP-ViT-L-14.pt"
    )
    checkpoint = torch.load(checkpoint_path, map_location="cpu")

    state_dict = checkpoint.get("state_dict", checkpoint)
    state_dict = {k.replace("module.", ""): v for k, v in state_dict.items()}

    model.load_state_dict(state_dict, strict=False)
    model.to(device)
    model.eval()

    print("RemoteCLIP ViT-L-14 loaded with satellite weights.")
    return model, preprocess, tokenizer


def encode_text_prompts(
    model,
    tokenizer,
    device: str = "cpu"
) -> torch.Tensor:
    """
    Pre-encode ML-resolvable category text prompts into embeddings.
    Mean-pools across multiple prompts per category, then L2-normalizes.

    IMPORTANT: iterates over ML_CATEGORIES (7 categories), NOT the full
    CATEGORIES dict (10 categories). unpaved_dirt_road, open_drainage_channel,
    and open_waste are intentionally excluded — see OSM_ONLY_CATEGORIES
    comment above for why.

    Returns:
        Tensor of shape (num_ml_categories, embedding_dim)
    """
    category_embeddings = []

    with torch.no_grad():
        for category, prompts in ML_CATEGORIES.items():
            tokens = tokenizer(prompts).to(device)
            embeddings = model.encode_text(tokens)
            embeddings = embeddings / embeddings.norm(dim=-1, keepdim=True)
            mean_embedding = embeddings.mean(dim=0)
            mean_embedding = mean_embedding / mean_embedding.norm()
            category_embeddings.append(mean_embedding)

    text_features = torch.stack(category_embeddings)
    print(f"Text prompts encoded for {len(ML_CATEGORY_NAMES)} ML-resolvable categories "
          f"(excluded from scoring: {sorted(OSM_ONLY_CATEGORIES)}).")
    return text_features


def classify_tile(
    tile_path: str,
    model,
    preprocess,
    tokenizer,
    text_features: torch.Tensor,
    masks: list,
    device: str = "cpu"
) -> list:
    """
    PATH A SCAFFOLD — tile-level classification with RemoteCLIP.

    Classifies the full tile once, assigns that scene-level label to all
    segments. SAM segments are used for spatial extent only.

    Scores only the 7 ML-resolvable categories (ML_CATEGORY_NAMES).
    unpaved_dirt_road, open_drainage_channel, and open_waste are NEVER
    assigned here — a segment that would otherwise fall into one of those
    is left as "unknown" and is picked up later by
    apply_osm_vector_labels() in osm_dem.py based on OSM proximity, not
    spectral similarity. This is the fix for the bug where those 3
    categories' generic-texture prompts were winning the argmax on almost
    every dense informal-settlement scene, regardless of AOI content.

    Segments where top raw cosine < UNKNOWN_THRESHOLD (0.20) are labeled
    "unknown" — never forced into a wrong category.

    all_scores: raw cosine similarities over the 7 ML categories (the real
        signal driving category selection)
    softmax_probs: softmax over those same 7 raw cosine scores (display
        only — tends to flatten, never used for selection)
    label_source: always "tile_level" for Path A outputs (may be
        overwritten to "osm_vector" downstream by apply_osm_vector_labels())

    This scaffold is replaced by SegFormer fine-tuned on annotation data (Path B).
    """
    image = Image.open(tile_path).convert("RGB")
    results = []

    with torch.no_grad():
        # ── Classify full tile once, over ML categories only ──
        tile_tensor = preprocess(image).unsqueeze(0).to(device)
        image_features = model.encode_image(tile_tensor)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        # Raw cosine similarities — this is the scoring mechanism, not softmax
        raw_similarities = (image_features @ text_features.T).squeeze(0).cpu().numpy()

        # Softmax for display only — stored separately, not used for selection
        softmax_probs = torch.tensor(raw_similarities).softmax(dim=0).numpy()

        tile_top_idx = int(np.argmax(raw_similarities))
        tile_top_score = float(raw_similarities[tile_top_idx])

        # Unknown category: tile itself is unclassifiable (or would only
        # match an OSM-only category, which isn't in this scoring set at all)
        if tile_top_score < UNKNOWN_THRESHOLD:
            tile_category = "unknown"
        else:
            tile_category = ML_CATEGORY_NAMES[tile_top_idx]

        print(f"Tile-level classification: {tile_category} (raw cosine: {tile_top_score:.4f})")
        print(f"Unknown threshold: {UNKNOWN_THRESHOLD} | Tile passes: {tile_top_score >= UNKNOWN_THRESHOLD}")
        print("Full tile raw cosine scores (ML-resolvable categories only):")
        sorted_scores = sorted(
            zip(ML_CATEGORY_NAMES, raw_similarities),
            key=lambda x: x[1], reverse=True
        )
        for cat, score in sorted_scores:
            marker = " ← tile label" if cat == tile_category else ""
            print(f"  {score:.4f}  {cat}{marker}")

        # ── Assign tile label to each segment ──
        for i, mask in enumerate(masks):
            x, y, w, h = mask["bbox"]

            if w < 8 or h < 8:
                continue

            # Per-segment crop scores — noisy but used for annotation prioritization
            crop = image.crop((x, y, x + w, y + h))
            crop_tensor = preprocess(crop).unsqueeze(0).to(device)
            crop_features = model.encode_image(crop_tensor)
            crop_features = crop_features / crop_features.norm(dim=-1, keepdim=True)
            crop_raw = (crop_features @ text_features.T).squeeze(0).cpu().numpy()
            crop_softmax = torch.tensor(crop_raw).softmax(dim=0).numpy()

            crop_top_idx = int(np.argmax(crop_raw))
            crop_top_score = float(crop_raw[crop_top_idx])
            crop_top_category = ML_CATEGORY_NAMES[crop_top_idx]

            results.append({
                "segment_id": i,
                "bbox": mask["bbox"],
                "area": mask["area"],
                # Primary: tile-level label (reliable scene-level signal)
                "category": crop_top_category if crop_top_score >= UNKNOWN_THRESHOLD else "unknown",
                "confidence": round(crop_top_score, 4),
                # Crop-level scores (noisy; flags annotation priority)
                "crop_top_category": crop_top_category,
                "crop_confidence": round(crop_top_score, 4),
                # all_scores / softmax_probs / crop_scores / crop_softmax_probs
                # are all restricted to the 7 ML-resolvable categories now —
                # NOT the full 10. unpaved_dirt_road / open_drainage_channel /
                # open_waste never appear here; they are added only by
                # apply_osm_vector_labels() downstream.
                "all_scores": {
                    ML_CATEGORY_NAMES[j]: round(float(raw_similarities[j]), 4)
                    for j in range(len(ML_CATEGORY_NAMES))
                },
                "softmax_probs": {
                    ML_CATEGORY_NAMES[j]: round(float(softmax_probs[j]), 4)
                    for j in range(len(ML_CATEGORY_NAMES))
                },
                "crop_scores": {
                    ML_CATEGORY_NAMES[j]: round(float(crop_raw[j]), 4)
                    for j in range(len(ML_CATEGORY_NAMES))
                },
                "crop_softmax_probs": {
                    ML_CATEGORY_NAMES[j]: round(float(crop_softmax[j]), 4)
                    for j in range(len(ML_CATEGORY_NAMES))
                },
                "label_source": "tile_level",
                # Annotation priority flag: crop disagrees with tile → human review first
                "annotation_priority": crop_top_category != tile_category,
            })

    print(f"Classified {len(results)} segments.")
    priority_count = sum(1 for r in results if r["annotation_priority"])
    print(f"High annotation priority (crop disagrees with tile): {priority_count} segments")
    return results


def save_classifications(results: list, output_path: str):
    """Save classification results as JSON."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Classifications saved: {output_path}")


def summarize_classifications(results: list) -> dict:
    """
    Aggregate classification results into category counts and coverage.
    Excludes 'unknown' segments from dominant_category calculation.

    Call this AFTER apply_osm_vector_labels() has run, so that
    dominant_category reflects the final label set (ML + OSM vector
    categories combined), not the pre-OSM ML-only state.

    Returns:
        dict with category counts, dominant category, and unknown count
    """
    from collections import Counter

    all_categories = [r["category"] for r in results]
    known_categories = [c for c in all_categories if c != "unknown"]

    counts = Counter(all_categories)
    known_counts = Counter(known_categories)
    total_area = sum(r["area"] for r in results)

    summary = {
        "total_segments": len(results),
        "unknown_segments": counts.get("unknown", 0),
        "total_area_px": total_area,
        "category_counts": dict(counts),
        # Dominant category excludes unknowns — unknown is not a land cover
        "dominant_category": known_counts.most_common(1)[0][0] if known_counts else None,
        "informal_roofing_segments": (
            counts.get("dense_informal_roofing", 0)
            + counts.get("sparse_informal_roofing", 0)
        ),
        "flood_risk_segments": (
            counts.get("standing_water", 0)
            + counts.get("open_drainage_channel", 0)
        ),
        "high_priority_annotation_count": sum(
            1 for r in results if r.get("annotation_priority", False)
        ),
    }
    return summary