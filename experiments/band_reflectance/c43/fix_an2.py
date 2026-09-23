import sys as _sys, pathlib as _pl
_HERE = _pl.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_HERE))
RESULTS = _ROOT / "experiments" / "band_reflectance" / "results" / "c43"
RESULTS.mkdir(parents=True, exist_ok=True)
import json, numpy as np
from scipy import stats
R=json.load(open(RESULTS / "fix_probe_raw.json")); idx={(r["arm"],r["city"]):r for r in R}
CATS=["dense_informal_roofing","sparse_informal_roofing","paved_road","standing_water",
      "vegetation_clearing","active_construction","dense_vegetation"]
ARMS=["A_baseline","B_ignore","C_human","D_human_native"]
cities=["capetown","dhaka","guatemala"]
FOC=["dense_informal_roofing","dense_vegetation"]
have=[a for a in ARMS if all((a,c) in idx for c in cities)]
for yard in ["corrected","orig"]:
    print("="*100); print(f"YARDSTICK = {yard} (val held at baseline geometry for every arm)"); print("="*100)
    print(f"{'city':<11}{'arm':<16}{'mIoU':>18}{'dense_informal_roof':>22}{'dense_vegetation':>22}")
    for c in cities:
        b=idx[("A_baseline",c)]
        for a in have:
            r=idx[(a,c)]; pc=r[f"per_class_last5[{yard}]"]; bp=b[f"per_class_last5[{yard}]"]
            def f(v,bv):
                if v is None: return f"{'n/a':>22}"
                return f"{v:.4f}"+("".rjust(15) if a=="A_baseline" else f" ({v-bv:+.4f})".rjust(15))
            mi=r[f"miou_last5[{yard}]"]; bm=b[f"miou_last5[{yard}]"]
            mc=f"{mi:.4f}"+("".rjust(11) if a=="A_baseline" else f" ({mi-bm:+.4f})".rjust(11))
            print(f"{c:<11}{a:<16}{mc:>18}{f(pc[FOC[0]],bp[FOC[0]]):>22}{f(pc[FOC[1]],bp[FOC[1]]):>22}")
        print()
    print(f"--- PAIRED DELTAS vs A_baseline (n=3 folds) ---")
    print(f"{'class':<26}"+"".join(f"{a:>26}" for a in have[1:]))
    for c in CATS+["__miou__"]:
        row=f"{'OVERALL mIoU' if c=='__miou__' else c:<26}"
        for a in have[1:]:
            ds=[]
            for ct in cities:
                r,b=idx[(a,ct)],idx[("A_baseline",ct)]
                if c=="__miou__": ds.append(r[f"miou_last5[{yard}]"]-b[f"miou_last5[{yard}]"])
                else:
                    x,y=r[f"per_class_last5[{yard}]"][c],b[f"per_class_last5[{yard}]"][c]
                    if x is None or y is None: continue
                    ds.append(x-y)
            ds=np.array(ds); sd=ds.std(ddof=1) if len(ds)>1 else 0
            row+=f"{ds.mean():>+12.4f} +/-{sd:<6.4f} {f'{(ds>0).sum()}+/{(ds<0).sum()}-':>5}"
        print(row)
    print()
print("="*100); print("ARM D vs ARM C  (scale-corrected vs magnified, same label correction)"); print("="*100)
if "D_human_native" in have:
    for c in FOC+["__miou__"]:
        ds=[]
        for ct in cities:
            d,cc=idx[("D_human_native",ct)],idx[("C_human",ct)]
            k="miou_last5[corrected]" if c=="__miou__" else None
            ds.append(d[k]-cc[k] if k else d["per_class_last5[corrected]"][c]-cc["per_class_last5[corrected]"][c])
        ds=np.array(ds); t,p=stats.ttest_1samp(ds,0)
        print(f"  {'OVERALL mIoU' if c=='__miou__' else c:<26}{ds.mean():>+9.4f} +/-{ds.std(ddof=1):<7.4f} "
              f"t={t:>5.2f} p={p:.3f}  "+" ".join(f"{ct[:4]}{v:+.4f}" for ct,v in zip(cities,ds)))
    print("\n  mean final train loss: "+"  ".join(
        f"{a.split('_')[0]} {np.mean([idx[(a,c)]['final_train_loss'] for c in cities]):.4f}" for a in have))
