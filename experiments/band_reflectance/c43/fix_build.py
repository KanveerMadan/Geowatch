"""
C43-fix: build baseline + two corrected variants of the 1,414-patch set.

ONLY osm_generated / osm_generated_water MASK PIXELS change. Patch selection,
images, geometry, `label` strings (hence class weights) are untouched.

  A  baseline   as production builds it
  B  ignore     pixels where the builder painted its class over a DIFFERENT
                non-IGNORE canvas class -> IGNORE   (removes wrong supervision)
  C  human      same pixels -> the canvas (human/SAM) class
                                        (removes wrong + adds correct)
READ-ONLY w.r.t. the repo.
"""

import sys as _sys, pathlib as _pl
_HERE = _pl.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_HERE))
RESULTS = _ROOT / "experiments" / "band_reflectance" / "results" / "c43"
RESULTS.mkdir(parents=True, exist_ok=True)
import sys, json
import numpy as np
from PIL import Image
from collections import defaultdict, Counter
from experiments.band_reflectance.production_patches_v2 import (
    build_all_patches, build_tile_label_canvas, CATEGORIES, CAT2IDX,
    IGNORE_INDEX, LOCO_CLEAN_CITIES)

TARGET_SOURCES = ("osm_generated", "osm_generated_water")


def aligned_canvas(patch, canvas):
    """The canvas region under this patch, in the patch's own 64x64 frame."""
    g = patch["geom"]
    if g["kind"] == "window":
        x, y = g["xy"]
        sub = canvas[y:y + 64, x:x + 64]
    else:
        x1, y1, x2, y2 = g["box"]
        sub = canvas[y1:y2, x1:x2]
        if sub.size == 0:
            return None
        sub = np.array(Image.fromarray(sub).resize((64, 64), Image.NEAREST))
    return sub if sub.shape == (64, 64) else None


def build_variants():
    base = build_all_patches(verbose=False)
    canv = {c: build_tile_label_canvas(c, verbose=False)[0] for c in LOCO_CLEAN_CITIES}

    masks_B, masks_C = [], []
    stat = defaultdict(int)
    per_city = defaultdict(lambda: defaultdict(int))
    moved = defaultdict(int)          # canvas class -> px reclaimed
    lost = defaultdict(int)           # builder class -> px it loses
    for p in base:
        m = p["mask"]
        if p["source"] not in TARGET_SOURCES:
            masks_B.append(m); masks_C.append(m); continue
        cv = canv.get(p["city"])
        sub = aligned_canvas(p, cv) if cv is not None else None
        if sub is None:
            masks_B.append(m); masks_C.append(m); continue
        own = CAT2IDX[p["label"]]
        bad = (m == own) & (sub != IGNORE_INDEX) & (sub != own)
        n = int(bad.sum())
        if n == 0:
            masks_B.append(m); masks_C.append(m); continue
        stat["patches_changed"] += 1
        stat["px_changed"] += n
        per_city[p["city"]]["patches"] += 1
        per_city[p["city"]]["px"] += n
        lost[p["label"]] += n
        for i, c in enumerate(CATEGORIES):
            k = int((bad & (sub == i)).sum())
            if k: moved[c] += k
        b = m.copy(); b[bad] = IGNORE_INDEX
        c_ = m.copy(); c_[bad] = sub[bad]
        masks_B.append(b); masks_C.append(c_)
    return base, masks_B, masks_C, stat, per_city, moved, lost


if __name__ == "__main__":
    base, B, C, stat, per_city, moved, lost = build_variants()
    tgt = [p for p in base if p["source"] in TARGET_SOURCES]
    print(f"patches total {len(base)} | target-builder patches {len(tgt)}")
    print(f"patches whose mask changes: {stat['patches_changed']} "
          f"({100*stat['patches_changed']/len(tgt):.1f}% of target patches, "
          f"{100*stat['patches_changed']/len(base):.1f}% of the set)")
    print(f"pixels changed: {stat['px_changed']:,}")
    print("\npixels the builder LOSES, by the builder's class:")
    for k, v in sorted(lost.items(), key=lambda kv: -kv[1]):
        print(f"   {k:<26}{v:>9,}")
    print("\npixels RECLAIMED, by what the human canvas said they were:")
    for k, v in sorted(moved.items(), key=lambda kv: -kv[1]):
        print(f"   {k:<26}{v:>9,}")
    print("\nper-city footprint of the change (this is where a LOCO fold can see it):")
    print(f"   {'city':<12}{'patches':>9}{'px':>10}{'val patches':>13}{'DIR val px':>12}{'DV val px':>11}")
    for c in LOCO_CLEAN_CITIES:
        vp = [i for i, p in enumerate(base) if p["city"] == c]
        dir_px = sum(int((base[i]['mask'] == CAT2IDX['dense_informal_roofing']).sum()) for i in vp)
        dv_px = sum(int((base[i]['mask'] == CAT2IDX['dense_vegetation']).sum()) for i in vp)
        print(f"   {c:<12}{per_city[c]['patches']:>9}{per_city[c]['px']:>10,}"
              f"{len(vp):>13}{dir_px:>12,}{dv_px:>11,}")
