"""
Arm E: rebuild the 912 non-sliding-window patches as native 64x64 windows with
the real multi-class canvas masks.

  sam (268)                  window centred on the bbox centroid; mask = canvas crop
  osm_generated (274)        same; canvas crop, then the segment's NATIVE mask_rle
  osm_generated_water (95)   fills only pixels the canvas left IGNORE
  osm (275)                  keeps its existing window xy; canvas crop, then the
                             existing road-buffer fills only IGNORE pixels
  sliding_window (502)       UNTOUCHED

Rule everywhere: the human/SAM canvas wins; builder geometry only fills what the
canvas never labelled. No resize, no blanket IGNORE, no overwrite of a human label.

`label` strings are left alone on purpose -- they drive the class-weight formula,
so keeping them identical to the baseline keeps the two arms paired on everything
except the pixels. READ-ONLY w.r.t. the repo.
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
from collections import Counter
from experiments.band_reflectance.production_patches_v2 import (
    build_all_patches, build_tile_label_canvas, CATEGORIES, CAT2IDX, IGNORE_INDEX,
    LOCO_CLEAN_CITIES, _city_file, decode_mask_rle)
from fix_build_d import _ann_index

PS = 64
REBUILD = ("sam", "osm", "osm_generated", "osm_generated_water")


def build_arm_e():
    base = build_all_patches(verbose=False)
    canv, anns, dims = {}, {}, {}
    for c in LOCO_CLEAN_CITIES:
        canv[c] = build_tile_label_canvas(c, verbose=False)[0]
        anns[c], tw, th = _ann_index(c)
        dims[c] = (tw, th)

    pE, mE, touched = [], [], []
    unmatched = 0
    for i, p in enumerate(base):
        m = p["mask"]
        if p["source"] not in REBUILD:
            pE.append(p); mE.append(m); continue
        cv = canv[p["city"]]; tw, th = dims[p["city"]]
        if cv is None or tw < PS or th < PS:
            pE.append(p); mE.append(m); continue

        if p["geom"]["kind"] == "window":                      # osm: keep the window
            x0, y0 = p["geom"]["xy"]
        else:                                                  # centre on the object
            x1, y1, x2, y2 = p["geom"]["box"]
            x0 = int(np.clip(round((x1 + x2) / 2.0) - PS // 2, 0, tw - PS))
            y0 = int(np.clip(round((y1 + y2) / 2.0) - PS // 2, 0, th - PS))

        nm = cv[y0:y0 + PS, x0:x0 + PS].copy()                 # canvas first
        if nm.shape != (PS, PS):
            pE.append(p); mE.append(m); continue
        own = CAT2IDX[p["label"]]

        if p["source"] == "osm":
            # the existing mask IS the native road buffer (window geom, no resize)
            fill = (m == own) & (nm == IGNORE_INDEX)
            nm[fill] = own
        elif p["source"] in ("osm_generated", "osm_generated_water"):
            key = (tuple(p["geom"]["box"]), p["label"], p["source"])
            cand = anns[p["city"]].get(key)
            if cand:
                seg = decode_mask_rle(cand[0]["mask_rle"])[y0:y0 + PS, x0:x0 + PS]
                if seg.shape == (PS, PS):
                    nm[seg & (nm == IGNORE_INDEX)] = own
            else:
                unmatched += 1
        # sam: the segment is already in the canvas by construction

        q = dict(p); q["geom"] = {"kind": "window", "xy": (int(x0), int(y0))}
        pE.append(q); mE.append(nm); touched.append(i)
    if unmatched:
        print(f"  WARNING: {unmatched} osm_generated patches unmatched")
    return base, pE, mE, touched


if __name__ == "__main__":
    base, pE, mE, touched = build_arm_e()
    mA = [p["mask"] for p in base]
    def prof(ms, name):
        nc = np.array([len(np.unique(m[m != IGNORE_INDEX])) for m in ms])
        lab = np.array([int((m != IGNORE_INDEX).sum()) for m in ms])
        print(f"  {name:<10} single-class {100*(nc<=1).mean():5.1f}%   multi {100*(nc>=2).mean():5.1f}%   "
              f"mean cls {nc.mean():.2f}   labelled px {100*lab.mean()/4096:5.1f}%   total sup px {lab.sum():,}")
        return nc
    print(f"arm E rebuilds {len(touched)} of {len(base)} patches (sliding_window untouched)\n")
    a = prof(mA, "baseline"); e = prof(mE, "arm E")
    print(f"\n  single-class rate 85.4% -> {100*(e<=1).mean():.1f}%   (predicted 63.6%)")
    print(f"\n  per-class supervised pixels:")
    print(f"  {'class':<26}{'baseline':>12}{'arm E':>12}{'change':>12}")
    for k, c in enumerate(CATEGORIES):
        x = sum(int((m == k).sum()) for m in mA); y = sum(int((m == k).sum()) for m in mE)
        print(f"  {c:<26}{x:>12,}{y:>12,}{y-x:>+12,}")
    import collections
    g = collections.Counter(p["geom"]["kind"] for p in pE)
    print(f"\n  geometry: {dict(g)}  (baseline: {dict(collections.Counter(p['geom']['kind'] for p in base))})")
