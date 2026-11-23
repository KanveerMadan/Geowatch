"""Extract only explicitly permitted historical intensity references on their declared grids."""
import argparse
import json
from pathlib import Path

import numpy as np
import rasterio

from .guard import authorize
from .package import check_grid,sha

DEV_FILES = {
    "beira":"flood_refs/round2/coastal__beira.npz",
    "dharavi":"flood_refs/round2/pluvial__dharavi.npz",
    "kerala_2018":"flood_refs/round4/test/waterlogging__kerala_2018.npz",
}
WEIHUI = tuple(f"usf_weihui_{i}" for i in (1,2,3))


def archive_unit(unit, out, *, cache=None):
    site=authorize(unit)
    cache=(Path.home()/".cache/geowatch") if cache is None else Path(cache)
    if unit in WEIHUI:
        companion=cache/"flood_final/urban"/(unit+".npz")
        with np.load(companion,allow_pickle=False) as z:
            meta=json.loads(str(z["meta"]))
        rel=f"flood_final/urban/{unit}__s1.npz"
    elif unit in DEV_FILES:
        rel=DEV_FILES[unit]
        with np.load(cache/rel,allow_pickle=False) as z:
            meta=json.loads(str(z["meta"]))
    else:
        raise ValueError("No reviewed old reference for this site")
    if site["bbox"]!=meta.get("bbox") or site["date"]!=meta.get("event"):
        raise ValueError("Legacy geometry/date differs from the guarded event identity")
    grid=meta["grid"]
    crs,t,shape=check_grid(grid)
    with np.load(cache/rel,allow_pickle=False) as z:
        evidence=json.loads(str(z["meta"])) if unit in WEIHUI else meta["reference"]
        if "COPERNICUS/S1_GRD" not in evidence["source"] or "event_image_date" not in evidence:
            raise ValueError("Historical reference lacks dated S1 provenance")
        wet,observed = z["flooded"],z["valid"]
        if wet.dtype!=bool or observed.dtype!=bool or wet.shape!=shape or observed.shape!=shape:
            raise ValueError("Legacy reader requires exact shape and Boolean flood/observed arrays")
        labels=np.where(observed,wet.astype("uint8"),255).astype("uint8")
    dest=Path(out)/"historical"/unit
    dest.mkdir(parents=True,exist_ok=True)
    p=dest/"intensity.tif"
    with rasterio.open(p,"w",driver="GTiff",height=shape[0],width=shape[1],count=1,
                       dtype="uint8",crs=crs,transform=t,nodata=255,compress="deflate") as ds:
        ds.write(labels,1)
        ds.set_band_description(1,"0 observed no VV-drop; 1 observed VV-drop; 255 unavailable")
    receipt={"unit":unit,"event":site["date"],"grid":grid,"archive":rel,
             "source_sha256":sha(cache/rel),"sha256":sha(p),"reference":evidence,
             "licence":"Copernicus Sentinel data terms; legacy derived comparator",
             "valid":int(observed.sum()),"wet":int((labels==1).sum()),
             "grid_source":f"{unit}.npz companion and matching weihui.py producer" if unit in WEIHUI else "archive metadata"}
    (dest/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    return receipt


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("units",nargs="+")
    a=p.parse_args()
    for unit in a.units:
        r=archive_unit(unit,a.out)
        print(unit,r["valid"],r["wet"],r["reference"]["event_image_date"])
