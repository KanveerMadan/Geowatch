"""External 2025 stress test against CAL FIRE inspections, independent of SpaceNet labels."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import urllib.parse
import urllib.request

import numpy as np
from pyproj import Transformer
from sklearn.metrics import average_precision_score, roc_auc_score
from threadpoolctl import threadpool_limits

from experiments.change_history.building_multisensor import (
    MANIFEST, ROOT, block_inputs, digest, fit, inputs, predict, verify_lock,
)
from experiments.change_history.building_endpoints import _layer
from experiments.change_history.spacenet_survey import _save

URL = "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/ArcGIS/rest/services/POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0/query"
SITE = {"site":"palisades_2025","centre":[-118.525,34.047],"epochs":{"2024_02":{},"2025_02":{}}}


def inspections(layer):
    west,south,east,north = layer.bbox
    crs = layer.crs.to_string()
    reproject = Transformer.from_crs("EPSG:4326",layer.crs,always_xy=True).transform
    params = dict(where="INCIDENTSTARTDATE >= DATE '2025-01-01' AND INCIDENTSTARTDATE < DATE '2025-02-01'",
                  geometry=f"{west},{south},{east},{north}",geometryType="esriGeometryEnvelope",
                  spatialRel="esriSpatialRelIntersects", inSR=4326,outSR=4326,returnGeometry="true",
                  outFields="OBJECTID,DAMAGE,INCIDENTNAME",orderByFields="OBJECTID ASC",resultRecordCount=1000,f="json")
    groups, seen = defaultdict(Counter),set()
    while True:
        params["resultOffset"] = len(seen)
        with urllib.request.urlopen(URL+"?"+urllib.parse.urlencode(params),timeout=45) as stream:
            obj = json.load(stream)
        if "error" in obj:
            raise ValueError(obj["error"])
        for row in obj["features"]:
            prop = row["attributes"]
            ident = prop["OBJECTID"]
            if ident in seen:
                raise ValueError("duplicated inspection across pages")
            seen.add(ident)
            if prop["INCIDENTNAME"].strip().casefold() not in ("palisades","palisades fire"):
                continue
            x,y = reproject(row["geometry"]["x"],row["geometry"]["y"])
            key = f"{crs}/{int(x//200)*200}/{int(y//200)*200}"
            groups[key][prop["DAMAGE"]] += 1
        if not obj.get("exceededTransferLimit"):
            break
        if not obj["features"]:
            raise ValueError("incomplete inspection pagination")
    return {k:dict(v) for k,v in groups.items()}


def score(predictions, ids, groups):
    selected, positives = [], []
    for i,key in enumerate(ids):
        counts = groups.get(key,{})
        if counts.get("Destroyed (>50%)",0):
            selected.append(i)
            positives.append(True)
        elif counts and set(counts)=={"No Damage"}:
            selected.append(i)
            positives.append(False)
    y = np.array(positives,bool)
    result = {"grid_blocks":len(ids), "blocks_with_inspections":sum(k in groups for k in ids),
              "inspections_in_blocks":sum(sum(groups.get(k,{}).values()) for k in ids),
              "destroyed_positive_blocks":sum(positives),"assessed_undamaged_blocks":len(y)-sum(positives)}
    scores = {m:a[selected,1] for m,a in predictions.items()}
    joint = np.logical_and.reduce([np.isfinite(s) for s in scores.values()])
    scores["zero"] = np.zeros(len(y))
    result["common_block_scores"] = {}
    for mode,s in scores.items():
        result["common_block_scores"][mode] = {
            "blocks":int(joint.sum()),"positive":int(y[joint].sum()),
            "auc":float(roc_auc_score(y[joint],s[joint])) if len(set(y[joint]))==2 else None,
            "average_precision":float(average_precision_score(y[joint],s[joint])) if len(set(y[joint]))==2 else None}
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=["prepare","evaluate"])
    p.add_argument("cache",type=Path)
    p.add_argument("--output",type=Path)
    args = p.parse_args()
    verify_lock()
    lockfile = ROOT/"building_multisensor_recent_lock.json"
    for name,h in json.loads(lockfile.read_text()).items():
        if digest(ROOT/name)!=h:
            raise ValueError("external check lock mismatch")
    counts = args.cache/"palisades_inspections_200m.json"
    if args.action=="prepare":
        args.cache.mkdir(parents=True,exist_ok=True)
        if not counts.exists():
            _save(counts,inspections(_layer(SITE["centre"])))
        for sensor in ("sentinel1","sentinel2"):
            inputs(args.cache,SITE,sensor)
        return
    if not args.output or args.output.exists():
        p.error("select a new --output filename")
    with threadpool_limits(limits=1):
        sites = json.loads(MANIFEST.read_text())
        models,train = fit([block_inputs(args.cache,s["site"],with_labels=True) for s in sites if s["split"]=="development"])
        row = block_inputs(args.cache,SITE["site"],with_labels=False)
        result = score(predict(models,row),row["ids"],json.loads(counts.read_text()))
    result.update(site=SITE, inspection_counts_sha256=digest(counts), lock_sha256=digest(lockfile))
    with args.output.open("x") as f:
        json.dump(result,f,indent=2,allow_nan=False)
        f.write("\n")


if __name__=="__main__":
    main()
