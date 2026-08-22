from ingestion.classifier import (
    load_remoteclip, encode_text_prompts,
    classify_tile, save_classifications, summarize_classifications
)
from ingestion.segmentation import load_sam, segment_tile
import json

# Load models
model, preprocess, tokenizer = load_remoteclip()
device = "cuda" if __import__("torch").cuda.is_available() else "cpu"

# Encode text prompts
text_features = encode_text_prompts(model, tokenizer, device)

# Load SAM and segment
mask_generator = load_sam("models/sam/sam_vit_b.pth")
tile_path = "data/tiles/dharavi_test/tile_0_0.png"
masks = segment_tile(tile_path, mask_generator)

# Classify
results = classify_tile(tile_path, model, preprocess, tokenizer, text_features, masks, device)

# Save
save_classifications(results, "data/tiles/dharavi_test/classifications.json")

# Summarize
summary = summarize_classifications(results)
print("\n── Classification Summary ──")
print(f"Total segments: {summary['total_segments']}")
print(f"Dominant category: {summary['dominant_category']}")
print(f"Informal roofing segments: {summary['informal_roofing_segments']}")
print(f"Flood risk segments: {summary['flood_risk_segments']}")
print(f"\nCategory breakdown:")
for cat, count in sorted(summary['category_counts'].items(), key=lambda x: -x[1]):
    print(f"  {cat}: {count}")