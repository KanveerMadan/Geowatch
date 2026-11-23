"""Prepare a systematic, detector-blind VHR review on a guarded model grid."""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .guard import authorize, authorize_window
from .grid import grid30
from .legacy_maxar import footprints, validate_subset
from .optical_catalog import _save
from .vhr_reference import LICENCE, SOURCE, TERMS, read_rgb_chip

FRACTIONS = (.2, .5, .8)


def sheet(unit, before, after, root, source_tiles=None):
    site = authorize(unit)
    if not before < site["date"] <= after:
        raise ValueError("Review requires a real pre/post pair bracketing the event")
    authorize_window(unit,before,after)
    root = Path(root)
    root.mkdir(parents=True,exist_ok=True)
    cache=root/"maxar_cache"
    grid=grid30(unit)
    by_day=source_tiles if source_tiles is not None else {d:footprints(unit,d,cache) for d in (before,after)}
    if any(r["datetime"] != d for d in by_day for r in by_day[d]):
        raise ValueError("Wrong VHR acquisition date")
    if not all(by_day.values()):
        raise RuntimeError("One or both VHR dates lack a source footprint over the registered grid")
    h,w=grid["shape"]
    cells=[(int(h*y),int(w*x)) for y in FRACTIONS for x in FRACTIONS]
    preview=Image.new("RGB",(950,520*len(FRACTIONS)),color=(255,255,255))
    draw=ImageDraw.Draw(preview)
    recorded=[]
    for i,(row,col) in enumerate(cells):
        entry={"id":f"S{i+1:02}","row":row,"col":col,"source_dates":[before,after],"observed":{}}
        for j,dt in enumerate((before,after)):
            rgb,valid,source=read_rgb_chip(by_day[dt],grid,row,col,lambda b,f,l:validate_subset(unit,b,f,l),cache,scale=.5)
            size=rgb.shape[-1]
            inner=valid[int(.4*size):int(.6*size),int(.4*size):int(.6*size)]
            entry["observed"][dt]={"raw_valid_fraction":float(valid.mean()),"center_raw_valid_fraction":float(inner.mean()),
                                   "assets":[s["visual"] for s in source]}
            im=Image.fromarray(rgb.transpose(1,2,0))
            overlay=ImageDraw.Draw(im)
            overlay.rectangle((size*.4,size*.4,size*.6-1,size*.6-1),outline="yellow",width=1)
            # Pair vertically; each paired column stays readable in the contact sheet.
            tw,th=252,230
            im.thumbnail((tw,th))
            x=(i%3)*316+10; y=(i//3)*520+j*245+25
            preview.paste(im,(x,y))
            draw.text((x,y-17),f"{entry['id']}  row {row}, col {col}   {dt}", fill=(0,0,0))
        recorded.append(entry)
    preview.save(cache/"systematic_review.jpg",quality=93)
    _save(cache/"systematic_sampling.json",json.dumps({"unit":unit,"pre_date":before,"post_date":after,
          "design":"3 x 3 fixed positions at 20%, 50% and 80% of the model grid; detector-blind",
          "coverage":"All nine selected sites retained; acquisition mask cannot identify clouds and shadow.",
          "source":SOURCE,"licence":LICENCE,"licence_protocol":TERMS,"cells":recorded},indent=2).encode())


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("unit");p.add_argument("pre");p.add_argument("post");p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();sheet(args.unit,args.pre,args.post,args.output)
