import sys as _sys, pathlib as _pl
_HERE = _pl.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_HERE))
RESULTS = _ROOT / "experiments" / "band_reflectance" / "results" / "c43"
RESULTS.mkdir(parents=True, exist_ok=True)
import json, sys, numpy as np
from collections import defaultdict
R=json.load(open(str(RESULTS)+"/"+"fix_probe_raw.json"))
CATS=["dense_informal_roofing","sparse_informal_roofing","paved_road","standing_water",
      "vegetation_clearing","active_construction","dense_vegetation"]
ARMS=["A_baseline","B_ignore","C_human"]
idx={(r["arm"],r["city"]):r for r in R}
cities=sorted({r["city"] for r in R})
FOCUS=["dense_informal_roofing","dense_vegetation"]
for yard in ["orig","corrected"]:
    print("="*104)
    print(f"YARDSTICK = {yard} val masks   (steps={R[0]['steps']}, seed={R[0]['seed']}, last-5 mean)")
    print("="*104)
    print(f"{'city':<12}{'arm':<13}{'mIoU':>8}   " + "".join(f"{c[:20]:>22}" for c in FOCUS))
    for city in cities:
        for a in ARMS:
            r=idx.get((a,city))
            if not r: continue
            pc=r[f"per_class_last5[{yard}]"]
            base=idx[("A_baseline",city)][f"per_class_last5[{yard}]"]
            bm=idx[("A_baseline",city)][f"miou_last5[{yard}]"]
            dm="" if a=="A_baseline" else f" ({r[f'miou_last5[{yard}]']-bm:+.4f})"
            cells=""
            for c in FOCUS:
                v=pc[c]
                if v is None: cells+=f"{'n/a':>22}"; continue
                d="" if a=="A_baseline" else f" ({v-base[c]:+.4f})"
                cells+=f"{v:.4f}{d:>{22-6}}"
            print(f"{city:<12}{a:<13}{r[f'miou_last5[{yard}]']:>8.4f}{dm:<10}{cells}")
        print()
    print(f"--- PAIRED DELTAS vs A_baseline, mean over {len(cities)} folds ---")
    print(f"{'class':<26}" + "".join(f"{a+' delta':>22}" for a in ARMS[1:]))
    for c in CATS+["__miou__"]:
        row=f"{c if c!='__miou__' else 'OVERALL mIoU':<26}"
        for a in ARMS[1:]:
            ds=[]
            for city in cities:
                r=idx.get((a,city)); b=idx.get(("A_baseline",city))
                if not r or not b: continue
                if c=="__miou__": ds.append(r[f"miou_last5[{yard}]"]-b[f"miou_last5[{yard}]"])
                else:
                    x,y=r[f"per_class_last5[{yard}]"][c], b[f"per_class_last5[{yard}]"][c]
                    if x is None or y is None: continue
                    ds.append(x-y)
            if not ds: row+=f"{'n/a':>22}"; continue
            ds=np.array(ds)
            sd=ds.std(ddof=1) if len(ds)>1 else 0.0
            row+=f"{ds.mean():>+11.4f} +/-{sd:<8.4f}"
        print(row)
    print()
