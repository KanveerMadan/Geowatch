from ingestion.segmentation import load_sam, segment_tile, save_masks, visualize_masks

# Load SAM
mask_generator = load_sam("models/sam/sam_vit_b.pth")

# Run on Dharavi tile
tile_path = "data/tiles/dharavi_test/tile_0_0.png"

masks = segment_tile(tile_path, mask_generator)

# Save metadata
save_masks(masks, "data/tiles/dharavi_test/masks.json")

# Save visualization
visualize_masks(tile_path, masks, "data/tiles/dharavi_test/tile_0_0_segmented.png")

print(f"\nDone. Total segments: {len(masks)}")
print(f"Largest segment area: {masks[0]['area']} px")
print(f"Smallest segment area: {masks[-1]['area']} px")