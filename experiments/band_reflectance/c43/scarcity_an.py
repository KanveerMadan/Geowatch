import sys as _sys, pathlib as _pl
_HERE = _pl.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_HERE))
RESULTS = _ROOT / "experiments" / "band_reflectance" / "results" / "c43"
RESULTS.mkdir(parents=True, exist_ok=True)
import json, numpy as np
from collections import defaultdict, Counter
D=json.load(open(RESULTS / "scarcity.json")); rows=D["rows"]; rc=D["recentre"]
CITIES=[r["city"] for r in rows]

print("="*112)
print("Q1  WHAT THE ANNOTATED CANVASES ACTUALLY CONTAIN")
print("     every native 64x64 window position (stride 1); 'usable' = >=204 labelled px, the builder's own test")
print("="*112)
print(f"{'city':<11}{'tile':>10}{'labelled':>10}{'cls':>5}{'usable win':>12}{'multi-class':>13}{'meaningful':>12}{'mean cls':>10}")
for r in rows:
    print(f"{r['city']:<11}{r['tile']:>10}{100*r['lab_px']/r['tile_px']:>9.1f}%{r['n_classes_in_tile']:>5}"
          f"{r['n_usable']:>12,}{100*r['multi_any_usable']:>12.1f}%{100*r['multi_mean_usable']:>11.1f}%{r['mean_cls_usable']:>10.2f}")
W=np.array([r["n_usable"] for r in rows],float)
ma=np.array([r["multi_any_usable"] for r in rows]); mm=np.array([r["multi_mean_usable"] for r in rows])
mc=np.array([r["mean_cls_usable"] for r in rows])
print(f"{'POOLED':<11}{'':>10}{'':>10}{'':>5}{int(W.sum()):>12,}{100*(ma*W).sum()/W.sum():>12.1f}%"
      f"{100*(mm*W).sum()/W.sum():>11.1f}%{(mc*W).sum()/W.sum():>10.2f}")
print(f"{'UNWEIGHTED (per-city mean)':<38}{'':>2}{100*ma.mean():>12.1f}%{100*mm.mean():>11.1f}%{mc.mean():>10.2f}")

print()
print("="*112)
print("Q2  DID THE BBOX-CROP BUILDERS PASS UP MULTI-CLASS CONTEXT THAT WAS RIGHT THERE?")
print("     each of the 637 bbox-crop patches, re-centred as a native 64x64 window on the SAME object")
print("="*112)
by=defaultdict(list)
for r in rc: by[r["source"]].append(r)
print(f"{'builder':<24}{'n':>6}{'actual multi':>14}{'re-centred multi':>18}{'meaningful':>12}{'mean cls':>10}{'med crop':>10}")
allr=[]
for s in ["sam","osm_generated","osm_generated_water"]:
    rs=by[s]; allr+=rs
    a=np.array([x["actual_cls"] for x in rs]); n=np.array([x["native_cls"] for x in rs])
    nm=np.array([x["native_cls_mean"] for x in rs]); cs=np.array([x["crop_side"] for x in rs])
    print(f"{s:<24}{len(rs):>6}{100*(a>=2).mean():>13.1f}%{100*(n>=2).mean():>17.1f}%{100*(nm>=2).mean():>11.1f}%{n.mean():>10.2f}{np.median(cs):>9.0f}px")
a=np.array([x["actual_cls"] for x in allr]); n=np.array([x["native_cls"] for x in allr])
nm=np.array([x["native_cls_mean"] for x in allr])
print(f"{'ALL bbox-crop patches':<24}{len(allr):>6}{100*(a>=2).mean():>13.1f}%{100*(n>=2).mean():>17.1f}%{100*(nm>=2).mean():>11.1f}%{n.mean():>10.2f}")
print(f"\n  -> {(n>=2).sum()} of {len(allr)} bbox-crop patches sit inside a native window that HAS >=2 classes.")
print(f"     The builder discarded that context in {100*((n>=2)&(a<2)).mean():.1f}% of cases ({int(((n>=2)&(a<2)).sum())} patches).")
print(f"     Genuinely single-class even at native 64x64: {int((n<2).sum())} patches ({100*(n<2).mean():.1f}%).")
print("\n  by class (re-centred multi-class rate, i.e. context that existed and was thrown away):")
bc=defaultdict(list)
for x in allr: bc[x["label"]].append(x)
for k,v in sorted(bc.items(), key=lambda kv:-len(kv[1])):
    nn=np.array([x["native_cls"] for x in v])
    print(f"     {k:<26}{len(v):>5}   {100*(nn>=2).mean():>5.1f}% multi at native   mean {nn.mean():.2f} classes")

print()
print("="*112)
print("Q3  IF PATCHES WERE CUT AS NATIVE 64x64 WINDOWS ON THE INFERENCE GRID (stride 32)")
print("="*112)
print(f"{'city':<11}{'grid win':>10}{'usable':>9}{'multi-class':>13}{'meaningful':>12}")
gn=np.array([r["grid_n"] for r in rows],float); gu=np.array([r["grid_usable"] for r in rows],float)
gma=np.array([r["grid_multi_any"] for r in rows]); gmm=np.array([r["grid_multi_mean"] for r in rows])
for r in rows:
    print(f"{r['city']:<11}{r['grid_n']:>10,}{r['grid_usable']:>9,}{100*r['grid_multi_any']:>12.1f}%{100*r['grid_multi_mean']:>11.1f}%")
print(f"{'POOLED':<11}{int(gn.sum()):>10,}{int(gu.sum()):>9,}{100*(gma*gu).sum()/gu.sum():>12.1f}%{100*(gmm*gu).sum()/gu.sum():>11.1f}%")
print(f"\n  usable windows on the inference grid across all 11 tiles: {int(gu.sum()):,}")
print(f"  (the current set draws 1,414 patches total, of which 502 are sliding_window AFTER a 30/class/city cap)")
