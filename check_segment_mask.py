"""
Checks a specific segment's decoded mask -- how many pixels are True,
and where. Run from geowatch/ repo root:

    python check_segment_mask.py dhaka 41

(replace 41 with whatever segment_id annotate_queue.py is currently
showing you)
"""

import sys
import os
import json
import glob
import numpy as np

sys.path.insert(0, ".")
from annotate_queue import decode_rle  # reuse the real decoder

PIPELINE_RUNS_DIR = "data/pipeline_runs"


def find_run_dir(city):
    matches = sorted(glob.glob(os.path.join(PIPELINE_RUNS_DIR, f"{city}_*")))
    return matches[-1] if matches else None


if __name__ == "__main__":
    city = sys.argv[1]
    seg_id = int(sys.argv[2])

    run_dir = find_run_dir(city)
    with open(os.path.join(run_dir, "masks.json")) as f:
        masks = json.load(f)

    m = next((x for x in masks if x["segment_id"] == seg_id), None)
    if m is None:
        print(f"segment_id {seg_id} not found in {city}'s masks.json")
        sys.exit(1)

    mask = decode_rle(m["mask_rle"])
    print(f"bbox: {m['bbox']}")
    print(f"reported area: {m['area']}")
    print(f"decoded mask shape: {mask.shape}")
    print(f"decoded mask True pixel count: {mask.sum()}")
    print(f"mask dtype: {mask.dtype}")

    ys, xs = np.where(mask)
    if len(ys) > 0:
        print(f"mask bounding extent: x=[{xs.min()},{xs.max()}] y=[{ys.min()},{ys.max()}]")
    else:
        print("MASK IS COMPLETELY EMPTY -- this is the bug. RLE decode returned zero True pixels.")