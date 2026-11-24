"""Create a bounded, independent optical overview for VHR-positive site discovery.

The optional targeted sample selected on this view is reported separately from
the systematic sample and cannot estimate prevalence, precision or false alarms.
The private local JPEG files hold vendor imagery and are not included in Git.
"""
import argparse
from pathlib import Path

import numpy as np
from affine import Affine
from PIL import Image
import rasterio
from rasterio.vrt import WarpedVRT
from rasterio.enums import Resampling

from .guard import authorize_window
from .grid import grid30
from .legacy_maxar import footprints, validate_subset
from .optical_catalog import grid_extent, require_space


def overview(unit, dt, root):
    authorize_window(unit,dt,dt)
    grid=grid30(unit)
    validate_subset(unit,grid_extent(grid),dt,dt)
    cache=Path(root)/"maxar_cache"
    cache.mkdir(exist_ok=True,parents=True)
    dest=cache/("overview-"+dt+".jpg")
    if dest.exists():
        return
    h,w=grid["shape"]
    dest_shape=(h*5,w*5)
    t=Affine(*grid["transform"])*Affine.scale(1/5)
    rgb=np.zeros((3,*dest_shape),"uint8")
    valid=np.zeros(dest_shape,bool)
    for item in sorted(footprints(unit,dt,cache),key=lambda r:r["visual"]):
        authorize_window(unit,dt,dt)
        require_space(cache)
        from .vhr_pyramid import chip
        data, good = chip(item,item["visual"],grid["crs"],t,(h*5,w*5),cache,
                          lambda b,f,l:validate_subset(unit,b,f,l),level=2)
        new=good & ~valid
        rgb[:,new]=data[:,new];valid|=good
        if valid.all(): break
    Image.fromarray(rgb.transpose(1,2,0)).save(dest,quality=94)


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("unit");p.add_argument("dates",nargs="+");p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    for d in a.dates:
        overview(a.unit,d,a.output)
