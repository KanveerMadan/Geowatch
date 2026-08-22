from PIL import Image
import numpy as np

img = Image.open("data/pipeline_runs/dharavi_20260620_150817/tiles/tile_0_0.png")
arr = np.array(img)
print(f"Tile shape: {arr.shape}")
print(f"Mean pixel value: {arr.mean():.2f}  (0=black, 255=white)")
print(f"Max pixel value: {arr.max()}")
print(f"Min pixel value: {arr.min()}")
