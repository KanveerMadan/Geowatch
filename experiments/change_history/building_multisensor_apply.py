"""Run the experimental building model with the bundled development measurements."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform
from threadpoolctl import threadpool_limits

from experiments.change_history.building_multisensor import (
    MANIFEST, ROOT, block_inputs, digest, fit, inputs, predict, verify_lock,
)
from experiments.change_history.spacenet_survey import month_interval

DEVELOPMENT = ROOT / "building_multisensor_development.json.gz"
DEVELOPMENT_SHA256 = "184cfbcf2054209d54412a9b47f64d0298f8db8d4e45a791a0e2b2e3e1ea4d50"


def pack(root, path):
    sites = json.loads(MANIFEST.read_text())
    data = {"lock_sha256":digest(ROOT/"building_multisensor_lock.json"),"development":[]}
    for site in sites:
        if site["split"] != "development":
            continue
        row = block_inputs(root,site["site"],with_labels=True)
        features = {}
        for mode,arr in row["x"].items():
            if mode != "combined":
                # All missing values are explicit null, including within a partial block.
                features[mode] = np.where(np.isfinite(arr),arr,None).tolist()
        data["development"].append({"site":site["site"],"ids":row["ids"],"y":row["y"].tolist(),
                                    "keep":row["keep"].tolist(),"x":features})
    raw = json.dumps(data,separators=(",",":"), allow_nan=False).encode()
    with path.open("xb") as f:
        f.write(gzip.compress(raw,mtime=0))


def development(path=DEVELOPMENT):
    if digest(path) != DEVELOPMENT_SHA256:
        raise ValueError("development measurements differ from the published snapshot")
    with gzip.open(path,"rt") as f:
        data = json.load(f)
    sites = json.loads(MANIFEST.read_text())
    expected = [s["site"] for s in sites if s["split"]=="development"]
    if data["lock_sha256"] != digest(ROOT/"building_multisensor_lock.json") or [
            s["site"] for s in data["development"]]!=expected:
        raise ValueError("training bundle does not match locked development sites")
    rows = []
    for site in data["development"]:
        optical,radar = (np.array(site["x"][k],dtype=float) for k in ("optical","radar"))
        rows.append({"x":{"optical":optical,"radar":radar,"combined":np.hstack([optical,radar])},
                     "keep":np.array(site["keep"],dtype=bool),"y":np.array(site["y"],dtype=float)})
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("cache",type=Path)
    p.add_argument("output",type=Path)
    p.add_argument("--centre",type=float,nargs=2,required=True,metavar=("LONGITUDE","LATITUDE"))
    p.add_argument("--months",nargs=2,required=True,metavar=("BEFORE_YYYY_MM","AFTER_YYYY_MM"))
    args = p.parse_args()
    first,last = map(month_interval,args.months)
    lon,lat = args.centre
    if not (-180<=lon<180 and -80<=lat<=84):
        p.error("longitude and latitude must identify a location in UTM coverage")
    if first[0]>=last[0] or args.output.exists():
        p.error("use two ordered months and a new output file")
    verify_lock()
    args.cache.mkdir(parents=True, exist_ok=True)
    ident = hashlib.sha256(json.dumps([args.centre,args.months]).encode()).hexdigest()[:24]
    site = {"site":"apply-"+ident,"centre":args.centre,"epochs":dict.fromkeys(args.months)}
    for sensor in ("sentinel1","sentinel2"):
        inputs(args.cache,site,sensor)
    row = block_inputs(args.cache,site["site"],with_labels=False)
    with threadpool_limits(limits=1):
        models, _ = fit(development())
        estimates = predict(models,row)
    features = []
    for i,key in enumerate(row["ids"]):
        code,x,y = key.split("/")
        x,y = int(x),int(y)
        polygon = transform(Transformer.from_crs(code,"EPSG:4326",always_xy=True).transform,box(x,y,x+200,y+200))
        values = {"id":key}
        for mode, arr in estimates.items():
            for j,target in enumerate(("gain","loss")):
                v = arr[i,j]
                values[f"{mode}_{target}_m2"] = float(v) if np.isfinite(v) else None
        features.append({"type":"Feature","properties":values,"geometry":mapping(polygon)})
    result = {"type":"FeatureCollection","features":features,"method":"experimental building endpoint regressions",
              "windows":[first,last],"grid_m":200,"training_sha256":digest(DEVELOPMENT),
              "reference_target":"area of added or removed tracked building footprints"}
    with args.output.open("x") as f:
        json.dump(result,f,allow_nan=False)


if __name__=="__main__":
    main()
