"""C43 diagnostic: train/inference patch-construction mismatch. READ-ONLY."""

import sys as _sys, pathlib as _pl
_HERE = _pl.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_HERE))
RESULTS = _ROOT / "experiments" / "band_reflectance" / "results" / "c43"
RESULTS.mkdir(parents=True, exist_ok=True)
import sys, json, pickle
from collections import Counter, defaultdict
import numpy as np

from experiments.band_reflectance.production_patches_v2 import (
    build_all_patches, CATEGORIES, IGNORE_INDEX, PATCH_SIZE
)

P = build_all_patches(verbose=False)
print(f"TOTAL PATCHES: {len(P)}")

rows = []
for p in P:
    m = p["mask"]
    labs = np.unique(m[m != IGNORE_INDEX])
    n_lab = int((m != IGNORE_INDEX).sum())
    g = p["geom"]
    if g["kind"] == "resize":
        x1, y1, x2, y2 = g["box"]
        cw, ch = x2 - x1, y2 - y1
    else:
        cw = ch = PATCH_SIZE
    rows.append(dict(
        source=p["source"], label=p["label"], city=p["city"],
        n_classes=len(labs), n_lab_px=n_lab,
        lab_pct=100.0 * n_lab / m.size,
        kind=g["kind"], cw=cw, ch=ch,
    ))

with open(str(RESULTS)+"/c43_rows.json", "w") as f:
    json.dump(rows, f)
print("wrote rows:", len(rows))
