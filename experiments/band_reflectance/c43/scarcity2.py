"""Pass 2: window-size sweep, finer-stride pool sizes, and the osm windows."""

import sys as _sys, pathlib as _pl
_HERE = _pl.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_HERE))
RESULTS = _ROOT / "experiments" / "band_reflectance" / "results" / "c43"
RESULTS.mkdir(parents=True, exist_ok=True)
import sys, json
import numpy as np
from collections import defaultdict
from experiments.band_reflectance.production_patches_v2 import (
    build_all_patches, build_tile_label_canvas, CATEGORIES, IGNORE_INDEX, LOCO_CLEAN_CITIES)
NC = len(CATEGORIES)


def counts_for(canvas, ps):
    H, W = canvas.shape
    if H < ps or W < ps: return None
    ny, nx = H - ps + 1, W - ps + 1
    out = np.zeros((NC, ny, nx), dtype=np.int32)
    for c in range(NC):
        I = np.zeros((H + 1, W + 1), dtype=np.int32)
        np.cumsum(np.cumsum((canvas == c).astype(np.int32), 0), 1, out=I[1:, 1:])
        out[c] = I[ps:ps+ny, ps:ps+nx] - I[0:ny, ps:ps+nx] - I[ps:ps+ny, 0:nx] + I[0:ny, 0:nx]
    return out


patches = build_all_patches(verbose=False)
canv = {c: build_tile_label_canvas(c, verbose=False)[0] for c in LOCO_CLEAN_CITIES}

# --- A. window-size sweep: is single-class a scale effect? -------------------
print("="*96)
print("A  MULTI-CLASS RATE vs WINDOW SIZE   (usable = >=5% of the window labelled)")
print("="*96)
print(f"{'window':>8}{'ground span':>14}{'usable win':>13}{'multi-class':>13}{'meaningful':>12}{'mean cls':>10}")
for ps in (32, 64, 128, 192, 256):
    tot = mult = meang = 0; cls_sum = 0
    for city in LOCO_CLEAN_CITIES:
        cnt = counts_for(canv[city], ps)
        if cnt is None: continue
        lab = cnt.sum(0); ncl = (cnt > 0).sum(0); nm = (cnt >= ps*ps//100).sum(0)
        u = lab >= ps*ps*0.05
        tot += int(u.sum()); mult += int((ncl[u] >= 2).sum())
        meang += int((nm[u] >= 2).sum()); cls_sum += int(ncl[u].sum())
    if tot:
        print(f"{f'{ps}x{ps}':>8}{f'~{ps*11.5:.0f} m':>14}{tot:>13,}{100*mult/tot:>12.1f}%"
              f"{100*meang/tot:>11.1f}%{cls_sum/tot:>10.2f}")

# --- B. pool size at finer strides ------------------------------------------
print()
print("="*96)
print("B  HOW MANY NATIVE 64x64 PATCHES COULD YOU EVEN BUILD?")
print("="*96)
print(f"{'stride':>8}{'grid win':>11}{'usable':>9}{'multi-class':>13}{'meaningful':>12}")
for st in (32, 16, 8, 4):
    tot = usable = mult = meang = 0
    for city in LOCO_CLEAN_CITIES:
        cnt = counts_for(canv[city], 64)
        if cnt is None: continue
        ny, nx = cnt.shape[1:]
        g = np.ix_(np.arange(0, ny, st), np.arange(0, nx, st))
        lab = cnt.sum(0)[g]; ncl = (cnt > 0).sum(0)[g]; nm = (cnt >= 64).sum(0)[g]
        u = lab >= 204
        tot += lab.size; usable += int(u.sum())
        mult += int((ncl[u] >= 2).sum()); meang += int((nm[u] >= 2).sum())
    print(f"{st:>8}{tot:>11,}{usable:>9,}{100*mult/usable:>12.1f}%{100*meang/usable:>11.1f}%")

# --- C. the osm windows: what the canvas says vs what the builder kept -------
print()
print("="*96)
print("C  THE 275 `osm` PATCHES -- already native windows, mask thrown away by construction")
print("="*96)
res = []
for p in patches:
    if p["source"] != "osm": continue
    x, y = p["geom"]["xy"]; cv = canv[p["city"]]
    sub = cv[y:y+64, x:x+64]
    if sub.shape != (64, 64): continue
    u, c = np.unique(sub[sub != IGNORE_INDEX], return_counts=True)
    res.append((len(u), int((c >= 64).sum()), int(sub.size - (sub == IGNORE_INDEX).sum())))
a = np.array(res)
print(f"  n={len(a)}   builder's mask: 100.0% single-class (paved_road only, rest IGNORE)")
print(f"  canvas in the SAME window: {100*(a[:,0]>=2).mean():.1f}% multi-class, "
      f"{100*(a[:,1]>=2).mean():.1f}% meaningful, mean {a[:,0].mean():.2f} classes")
print(f"  windows where the canvas has ANY label at all: {100*(a[:,0]>=1).mean():.1f}%")
print(f"  windows meeting the >=204px usability bar:     {100*(a[:,2]>=204).mean():.1f}%")
json.dump({"osm": a.tolist()}, open(SP + "scarcity2.json", "w"))
