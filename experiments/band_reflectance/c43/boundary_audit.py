"""C43 part 4: how many SCORED pixels sit on a real class boundary? READ-ONLY."""

import sys as _sys, pathlib as _pl
_HERE = _pl.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_HERE))
RESULTS = _ROOT / "experiments" / "band_reflectance" / "results" / "c43"
RESULTS.mkdir(parents=True, exist_ok=True)
import sys, json
import numpy as np
from experiments.band_reflectance.production_patches_v2 import (
    build_all_patches, build_tile_label_canvas, LOCO_CLEAN_CITIES, IGNORE_INDEX, CATEGORIES)
P=build_all_patches(verbose=False)

def bnd(m, ign=IGNORE_INDEX):
    """px whose 4-neighbourhood contains a DIFFERENT non-ignore class"""
    v=m!=ign; out=np.zeros_like(v)
    for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
        s=np.roll(m,(dy,dx),(0,1)); sv=np.roll(v,(dy,dx),(0,1))
        if dy==1: s[0]=ign; sv[0]=False
        if dy==-1: s[-1]=ign; sv[-1]=False
        if dx==1: s[:,0]=ign; sv[:,0]=False
        if dx==-1: s[:,-1]=ign; sv[:,-1]=False
        out |= v & sv & (s!=m)
    return out

tot=0; b=0
for p in P:
    m=p["mask"]; tot+=int((m!=IGNORE_INDEX).sum()); b+=int(bnd(m).sum())
print(f"TRAIN masks: scored px {tot:,}   on a scored class boundary {b:,}  = {100*b/tot:.2f}%")

# the same tiles' full label canvases -- what the fabric actually looks like
ct=0; cb=0; cl=0; call=0
for c in LOCO_CLEAN_CITIES:
    cv,_,_=build_tile_label_canvas(c,verbose=False)
    if cv is None: continue
    call+=cv.size; cl+=int((cv!=IGNORE_INDEX).sum()); cb+=int(bnd(cv).sum())
print(f"LABEL CANVASES (11 tiles): labelled px {cl:,} of {call:,} ({100*cl/call:.1f}%)   on a boundary {cb:,} = {100*cb/cl:.2f}% of labelled px")
print()
print(f"So the boundary decisions the model is graded on in training are {100*b/tot:.2f}% of its loss surface,")
print(f"versus {100*cb/cl:.2f}% in the annotated fabric -- and at inference EVERY pixel, boundary or not, is argmaxed.")
