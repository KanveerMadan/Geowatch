"""C43 part 3: pixel-aligned label conflict / deletion inside OSM patches. READ-ONLY."""

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
from collections import defaultdict
from experiments.band_reflectance.production_patches_v2 import (
    build_all_patches, build_tile_label_canvas, CATEGORIES, IGNORE_INDEX,
    LOCO_CLEAN_CITIES, CAT2IDX)
P=build_all_patches(verbose=False)
canv={c:build_tile_label_canvas(c,verbose=False)[0] for c in LOCO_CLEAN_CITIES}

deleted=defaultdict(lambda: defaultdict(int))   # source -> canvas class -> px set to IGNORE
conflict=defaultdict(lambda: defaultdict(int))  # source -> canvas class -> px overwritten with the builder's class
agree=defaultdict(int); nsrc=defaultdict(int)
for p in P:
    s=p["source"]
    if s not in ("osm","osm_generated","osm_generated_water"): continue
    cv=canv.get(p["city"]);  g=p["geom"]
    if cv is None: continue
    if g["kind"]=="window":
        x,y=g["xy"]; sub=cv[y:y+64,x:x+64]
    else:
        x1,y1,x2,y2=g["box"]; sub=cv[y1:y2,x1:x2]
        if sub.size==0: continue
        sub=np.array(Image.fromarray(sub).resize((64,64),Image.NEAREST))
    if sub.shape!=(64,64): continue
    nsrc[s]+=1
    m=p["mask"]; own=CAT2IDX[p["label"]]
    has=sub!=IGNORE_INDEX
    for i,c in enumerate(CATEGORIES):
        sel=has&(sub==i)
        deleted[s][c]+=int((sel&(m==IGNORE_INDEX)).sum())
        if i!=own: conflict[s][c]+=int((sel&(m==own)).sum())
        else: agree[s]+=int((sel&(m==own)).sum())
json.dump(dict(deleted={k:dict(v) for k,v in deleted.items()},
               conflict={k:dict(v) for k,v in conflict.items()},
               agree=dict(agree), n=dict(nsrc)), open(str(RESULTS)+"/"+"c43_conflict.json","w"), indent=1)
for s in ["osm","osm_generated","osm_generated_water"]:
    td=sum(deleted[s].values()); tc=sum(conflict[s].values())
    print(f"\n=== {s}  (n={nsrc[s]} patches, pixel-aligned to the SAM label canvas) ===")
    print(f"  canvas-labelled px inside these patches : {td+tc+agree[s]:,}")
    print(f"    -> set to IGNORE by the builder       : {td:,}  ({100*td/max(td+tc+agree[s],1):.1f}%)")
    print(f"    -> OVERWRITTEN with '{p and s}' class  : {tc:,}  ({100*tc/max(td+tc+agree[s],1):.1f}%)")
    print(f"    -> agree with the builder's own class : {agree[s]:,}")
    print("  deleted-to-IGNORE, by what the canvas said it was:")
    for k,v in sorted(deleted[s].items(),key=lambda kv:-kv[1]):
        if v: print(f"     {k:<26}{v:>9,}  {100*v/max(td,1):>5.1f}%")
    if tc:
        print("  OVERWRITTEN (canvas said X, builder painted its own class):")
        for k,v in sorted(conflict[s].items(),key=lambda kv:-kv[1]):
            if v: print(f"     {k:<26}{v:>9,}  {100*v/tc:>5.1f}%")
