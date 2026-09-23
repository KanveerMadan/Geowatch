import sys as _sys, pathlib as _pl
_HERE = _pl.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_HERE))
RESULTS = _ROOT / "experiments" / "band_reflectance" / "results" / "c43"
RESULTS.mkdir(parents=True, exist_ok=True)
import json, numpy as np
from collections import defaultdict
from scipy import stats
R=json.load(open(RESULTS / "armE_raw.json")); idx={(r["arm"],r["city"],r["seed"]):r for r in R}
CATS=["dense_informal_roofing","sparse_informal_roofing","paved_road","standing_water",
      "vegetation_clearing","active_construction","dense_vegetation"]
FOC=["dense_informal_roofing","active_construction","vegetation_clearing"]
cities=[c for c in ["dharavi","capetown","jakarta","hcmc"] if any(r["city"]==c for r in R)]
seeds=sorted({r["seed"] for r in R}); A,E="A_baseline","E_native_canvas"
pairs=[(c,s) for s in seeds for c in cities if (A,c,s) in idx and (E,c,s) in idx]
print(f"complete pairs: {len(pairs)} of {len(cities)*len(seeds)}\n")

for yard in ["val_base","val_native"]:
    print("="*104)
    print(f"YARDSTICK = {yard}" + ("   (baseline geometry+masks -- comparable to the 132-fold gate run)"
          if yard=="val_base" else "   (native geometry + multi-class canvas masks)"))
    print("="*104)
    print(f"{'city':<10}{'seed':>6}{'arm':<18}{'final':>9}{'last5':>9}{'best*':>9}{'loss':>8}")
    for c,s in pairs:
        for a in (A,E):
            r=idx[(a,c,s)]
            d=""
            if a==E:
                b=idx[(A,c,s)]
                d=f"  ({r[f'last5[{yard}]']-b[f'last5[{yard}]']:+.4f} last5)"
            print(f"{c:<10}{s:>6}{a:<18}{r[f'final[{yard}]']:>9.4f}{r[f'last5[{yard}]']:>9.4f}"
                  f"{r[f'best_ON_TEST[{yard}]']:>9.4f}{r['final_train_loss']:>8.4f}{d}")
    print()
    print(f"  {'metric':<16}{'A baseline':>20}{'E native':>20}{'paired delta':>22}{'p':>8}")
    for m in ["final","last5","best_ON_TEST"]:
        a=np.array([idx[(A,c,s)][f"{m}[{yard}]"] for c,s in pairs])
        e=np.array([idx[(E,c,s)][f"{m}[{yard}]"] for c,s in pairs])
        d=e-a; t,p=(stats.ttest_1samp(d,0) if len(d)>1 else (np.nan,np.nan))
        print(f"  {m:<16}{a.mean():>13.4f}+/-{a.std(ddof=1) if len(a)>1 else 0:<6.4f}"
              f"{e.mean():>13.4f}+/-{e.std(ddof=1) if len(e)>1 else 0:<6.4f}"
              f"{d.mean():>+14.4f} +/-{d.std(ddof=1) if len(d)>1 else 0:<6.4f}{p:>8.3f}")
    print()
    print(f"  PER-CLASS (last5)   {'A':>10}{'E':>10}{'delta':>11}{'sd':>9}{'p':>8}{'signs':>8}")
    for c_ in CATS:
        av,ev=[],[]
        for c,s in pairs:
            x=idx[(A,c,s)][f"per_class_last5[{yard}]"][c_]; y=idx[(E,c,s)][f"per_class_last5[{yard}]"][c_]
            if x is None or y is None: continue
            av.append(x); ev.append(y)
        if not av: print(f"  {c_:<26}{'n/a':>10}"); continue
        av,ev=np.array(av),np.array(ev); d=ev-av
        t,p=(stats.ttest_1samp(d,0) if len(d)>1 else (np.nan,np.nan))
        star=" <<<" if c_ in FOC else ""
        print(f"  {c_:<20}{av.mean():>10.4f}{ev.mean():>10.4f}{d.mean():>+11.4f}"
              f"{d.std(ddof=1) if len(d)>1 else 0:>9.4f}{p:>8.3f}{f'{(d>0).sum()}+/{(d<0).sum()}-':>8}{star}")
    print()
