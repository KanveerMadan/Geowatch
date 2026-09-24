"""
C43 follow-up: is 85.4% single-class a CONSTRUCTION artifact or real data scarcity?

Measured on the label canvases (every annotated segment's real mask painted
largest-area-first), NOT on the extracted patches. READ-ONLY.
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
    build_all_patches, build_tile_label_canvas, CATEGORIES, CAT2IDX, IGNORE_INDEX,
    LOCO_CLEAN_CITIES, _city_file)
PS, NC = 64, len(CATEGORIES)
MIN_LAB = 204          # the sliding_window builder's own min_labeled_pct=5.0
MEANINGFUL = 64        # a second class needs >=1% of the window to count as "meaningful"


def window_class_counts(canvas):
    """Exact per-class pixel count for EVERY native 64x64 window (stride 1),
    via integral images. Returns (counts[C,ny,nx], ny, nx)."""
    H, W = canvas.shape
    if H < PS or W < PS:
        return None, 0, 0
    ny, nx = H - PS + 1, W - PS + 1
    out = np.zeros((NC, ny, nx), dtype=np.int32)
    for c in range(NC):
        I = np.zeros((H + 1, W + 1), dtype=np.int32)
        np.cumsum(np.cumsum((canvas == c).astype(np.int32), 0), 1, out=I[1:, 1:])
        out[c] = (I[PS:PS + ny, PS:PS + nx] - I[0:ny, PS:PS + nx]
                  - I[PS:PS + ny, 0:nx] + I[0:ny, 0:nx])
    return out, ny, nx


def main():
    patches = build_all_patches(verbose=False)
    by_city = defaultdict(list)
    for i, p in enumerate(patches):
        by_city[p["city"]].append(p)

    rows = []
    recentre = []          # question 2: bbox-crop patches re-centred as native windows
    print("Scanning label canvases (stride-1 native 64x64 windows)...\n", flush=True)
    for city in LOCO_CLEAN_CITIES:
        canvas, tw, th = build_tile_label_canvas(city, verbose=False)
        if canvas is None:
            continue
        cnt, ny, nx = window_class_counts(canvas)
        if cnt is None:
            print(f"  {city}: tile smaller than 64px, skipped"); continue
        lab = cnt.sum(0)                       # labelled px per window
        ncls = (cnt > 0).sum(0)                # classes present
        nmean = (cnt >= MEANINGFUL).sum(0)     # classes with >=1% of the window

        usable = lab >= MIN_LAB                # the builder's own usability test
        anylab = lab > 0
        rows.append(dict(
            city=city, tile=f"{tw}x{th}",
            tile_px=int(tw * th),
            lab_px=int((canvas != IGNORE_INDEX).sum()),
            n_windows=int(ny * nx),
            n_usable=int(usable.sum()),
            multi_any_usable=float((ncls[usable] >= 2).mean()) if usable.any() else 0.0,
            multi_mean_usable=float((nmean[usable] >= 2).mean()) if usable.any() else 0.0,
            mean_cls_usable=float(ncls[usable].mean()) if usable.any() else 0.0,
            multi_any_all=float((ncls[anylab] >= 2).mean()) if anylab.any() else 0.0,
            n_classes_in_tile=int(len(np.unique(canvas[canvas != IGNORE_INDEX]))),
        ))

        # --- question 2: what the bbox-crop builders passed up -------------
        for p in by_city[city]:
            if p["geom"]["kind"] != "resize":
                continue
            x1, y1, x2, y2 = p["geom"]["box"]
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            wx = int(np.clip(round(cx) - PS // 2, 0, nx - 1))
            wy = int(np.clip(round(cy) - PS // 2, 0, ny - 1))
            col = cnt[:, wy, wx]
            m = p["mask"]
            recentre.append(dict(
                city=city, source=p["source"], label=p["label"],
                actual_cls=int(len(np.unique(m[m != IGNORE_INDEX]))),
                native_cls=int((col > 0).sum()),
                native_cls_mean=int((col >= MEANINGFUL).sum()),
                native_lab=int(col.sum()),
                crop_side=float(np.sqrt((x2 - x1) * (y2 - y1))),
            ))

        # --- the uncapped sliding-window candidate pool (stride 32) --------
        gy = np.arange(0, ny, 32); gx = np.arange(0, nx, 32)
        g = np.ix_(gy, gx)
        glab, gncls, gnmean = lab[g], ncls[g], nmean[g]
        gu = glab >= MIN_LAB
        rows[-1].update(
            grid_n=int(glab.size), grid_usable=int(gu.sum()),
            grid_multi_any=float((gncls[gu] >= 2).mean()) if gu.any() else 0.0,
            grid_multi_mean=float((gnmean[gu] >= 2).mean()) if gu.any() else 0.0,
        )
        print(f"  {city:<11} {tw}x{th}  labelled {100*rows[-1]['lab_px']/rows[-1]['tile_px']:5.1f}%  "
              f"classes {rows[-1]['n_classes_in_tile']}  usable windows {rows[-1]['n_usable']:>7,}  "
              f"multi-class {100*rows[-1]['multi_any_usable']:5.1f}% (meaningful {100*rows[-1]['multi_mean_usable']:5.1f}%)",
              flush=True)

    json.dump({"rows": rows, "recentre": recentre}, open(SP + "scarcity.json", "w"))
    print(f"\nwrote {len(rows)} cities, {len(recentre)} re-centred bbox patches")


if __name__ == "__main__":
    main()
