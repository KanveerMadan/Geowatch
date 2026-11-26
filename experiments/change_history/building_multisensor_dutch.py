"""Independent blind aerial review of recent building gains in the Netherlands."""
import argparse
import csv
import io
import json
from pathlib import Path
import urllib.parse
import urllib.request

import numpy as np
from PIL import Image, ImageDraw
from pyproj import Transformer
from sklearn.metrics import average_precision_score, roc_auc_score
from threadpoolctl import threadpool_limits

from experiments.change_history.building_multisensor import ROOT, block_inputs, digest, inputs, predict, fit, verify_lock
from experiments.change_history.building_multisensor_apply import development

SITES = {"almere": [5.289, 52.355], "utrecht": [5.067, 52.081], "haarlem": [4.662,52.375]}
YEARS = (2024,2025)
EPOCHS = {"2024_03":{}, "2025_03":{}}
PDOK = "https://service.pdok.nl/hwh/luchtfotorgb/wms/v1_0"
LOCK = ROOT/"building_multisensor_dutch_lock.json"
LABELS = ROOT/"building_multisensor_dutch_labels.csv"
SEAL = ROOT/"building_multisensor_dutch_seal.json"


def fixed_grid(centre):
    x,y = Transformer.from_crs(4326,32631,always_xy=True).transform(*centre)
    # 4 by 4 complete blocks centered on the nearest 200 m grid intersection.
    x,y = round(x/200)*200-400,round(y/200)*200-400
    return x,y, {f"{chr(65+r)}{c+1}":f"EPSG:32631/{x+c*200}/{y+(3-r)*200}"
                 for r in range(4) for c in range(4)}


def review_images(root,site):
    root.mkdir(exist_ok=True, parents=True)
    x,y,_ = fixed_grid(SITES[site])
    tr = Transformer.from_crs(32631,25831,always_xy=True)
    bbox = ",".join(map(str,(*tr.transform(x,y),*tr.transform(x+800,y+800))))
    images = {}
    for year in YEARS:
        path = root/f"{site}-{year}.jpg"
        if not path.exists():
            params = dict(SERVICE="WMS",VERSION="1.3.0",REQUEST="GetMap",CRS="EPSG:25831",BBOX=bbox,
                          WIDTH=1600,HEIGHT=1600,FORMAT="image/jpeg",LAYERS=f"{year}_orthoHR",STYLES="")
            with urllib.request.urlopen(PDOK+"?"+urllib.parse.urlencode(params),timeout=45) as r:
                data = r.read(8*1024*1024)
            im = Image.open(io.BytesIO(data))
            if im.size!=(1600,1600):
                raise ValueError("unexpected PDOK tile")
            path.write_bytes(data)
        images[year] = Image.open(path).convert("RGB")
    for i in range(4):
        for j in range(0,4,2):
            panel = Image.new("RGB",(1000,280))
            draw = ImageDraw.Draw(panel)
            for k,year in enumerate(YEARS):
                for c in range(2):
                    col = j+c
                    cropped = images[year].crop((400*col,400*i,400*col+400,400*i+400)).resize((250,250))
                    offx,offy = 500*k+250*c,30
                    panel.paste(cropped,(offx,offy))
                    draw.text((offx+4,9),f"{year}  {site}  {chr(65+i)}{col+1}",fill="white")
            panel.save(root/f"{site}-{i}-{j}.jpg",quality=95)


def read_labels(path):
    rows = list(csv.DictReader(path.open()))
    pairs = [(r["site"],r["block"]) for r in rows]
    expected = {(s,k) for s in SITES for k in fixed_grid(SITES[s])[2]}
    if set(pairs)!=expected or len(pairs)!=len(expected):
        raise ValueError("each registered block requires exactly one review")
    if any(r["gain"] not in {"yes","no","unknown"} or not r["reason"].strip() for r in rows):
        raise ValueError("unrecognized or unexplained aerial review")
    return rows


def metric(y, scores):
    valid = np.isfinite(scores)
    t,p = y[valid],scores[valid]
    return {"covered_blocks":len(t),"positive":int(t.sum()),"negative":int((~t).sum()),
            "auc":float(roc_auc_score(t,p)) if len(set(t))==2 else None,
            "average_precision":float(average_precision_score(t,p)) if len(set(t))==2 else None}


def evaluate(root):
    reviews = read_labels(LABELS)
    sealed = json.loads(SEAL.read_text())
    if sealed["labels_sha256"]!=digest(LABELS) or sealed["protocol_lock_sha256"]!=digest(LOCK):
        raise ValueError("labels or protocol changed after sealing")
    pred = {}
    with threadpool_limits(limits=1):
        models,_ = fit(development())
        for name,centre in SITES.items():
            site = {"site":"dutch-"+name,"centre":centre,"epochs":EPOCHS}
            for sensor in ("sentinel1","sentinel2"):
                inputs(root,site,sensor)
            row = block_inputs(root,site["site"],with_labels=False)
            values = predict(models,row)
            by_id = {key:i for i,key in enumerate(row["ids"])}
            for code,key in fixed_grid(centre)[2].items():
                pred[name,code] = {m:a[by_id[key],0] for m,a in values.items()}
    outputs = {}
    for scope in ["all",*SITES]:
        sample = [r for r in reviews if scope=="all" or r["site"]==scope]
        kept = [r for r in sample if r["gain"]!="unknown"]
        y = np.array([r["gain"]=="yes" for r in kept],bool)
        scores = {mode:np.array([pred[r["site"],r["block"]][mode] for r in kept])
                  for mode in ("optical","radar","combined")}
        joint = np.isfinite(np.column_stack(list(scores.values()))).all(axis=1)
        outputs[scope] = {"registered":len(sample),"unknown":len(sample)-len(kept),"reference_positive":int(y.sum()),
                          "reference_negative":int((~y).sum()),"available":{m:metric(y,s) for m,s in scores.items()},
                          "common":{m:metric(y[joint],s[joint]) for m,s in {**scores,"zero":np.zeros(len(y))}.items()}}
    return {"labels_sha256":digest(LABELS),"lock_sha256":digest(LOCK),"results":outputs}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action",choices=["imagery","seal","evaluate"])
    ap.add_argument("cache",type=Path)
    ap.add_argument("--output",type=Path)
    args = ap.parse_args()
    verify_lock()
    for f,h in json.loads(LOCK.read_text()).items():
        if digest(ROOT/f)!=h:
            raise ValueError("frozen Dutch study file changed")
    root=args.cache
    root.mkdir(exist_ok=True,parents=True)
    if args.action=="imagery":
        for s in SITES:
            review_images(root,s)
    elif args.action=="seal":
        read_labels(LABELS)
        hashes = {f"{s}-{y}.jpg":digest(root/f"{s}-{y}.jpg") for s in SITES for y in YEARS}
        with SEAL.open("x") as f:
            json.dump({"labels_sha256":digest(LABELS),"protocol_lock_sha256":digest(LOCK),"reference_sha256":hashes},f,indent=2)
            f.write("\n")
    else:
        if not args.output or args.output.exists():
            ap.error("select a new output")
        values = evaluate(root)
        with args.output.open("x") as f:
            json.dump(values,f,indent=2,allow_nan=False)
            f.write("\n")


if __name__=="__main__":
    main()
