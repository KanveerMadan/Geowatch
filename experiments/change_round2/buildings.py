"""Weakly supervised 200 m construction and removal screening. No production alerts."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path
from statistics import median

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from .data import HERE, cached, connect, geometry, grid, history, read, save

OB = "GOOGLE/Research/open-buildings-temporal/v1"
GHSL = "JRC/GHSL/P2023A/GHS_BUILT_S/2015"
BUNDLE = HERE / "building_model.json"
RESULTS = HERE / "building_development_results.json"
DATASET = HERE / "building_development_rows.json.gz"
MODES = {"combined":("radar","optical"), "radar":("radar",), "optical":("optical",)}
FIELDS = {"radar":("VV","VH","texture"),"optical":("ndvi","water")}
PAIRS = [(2017,2018),(2019,2020),(2021,2022)]
TARGETS = ("gain","loss")


def seen_sites():
    directory=HERE.parent/"change_history"
    ordinary=read(directory/"ordinary_city_protocol.json")["sites"] + read(directory/"ordinary_city_default_protocol.json")["sites"]
    # Includes cities outside Google's footprint coverage. Retain all registered
    # sites and explicitly report empty coverage where the reference is absent.
    return {s["id"]:(s["lon"],s["lat"]) for s in ordinary}


def anchor_range(anchor):
    d=date.fromisoformat(anchor)
    return str(d-timedelta(days=45)),str(d+timedelta(days=45))


def context(ee,crs,cells):
    def get():
        controls=geometry(ee,crs,cells,200)
        raster=ee.Image(GHSL).select("built_surface").divide(10000).rename("share")
        bands=raster.addBands(raster.mask().unmask(0,False).rename("valid"))
        rows=bands.reduceRegions(collection=controls,reducer=ee.Reducer.mean().unweighted(),
                                  crs=crs,crsTransform=[20,0,0,0,-20,0]).getInfo()["features"]
        out=[None]*len(cells)
        for feature in rows:
            r=feature["properties"]
            if r.get("valid",0)>=.999999:
                out[r["i"]]=r.get("share")
        return out
    return cached(["building_ghsl2015_v1",GHSL,crs,cells],get)


def dated_labels(ee,crs,cells,first,second):
    """Persistent flips in OB confidence on the same 4 m support; return unknown gaps."""
    def get():
        fc=geometry(ee,crs,cells,200)
        geog=fc.geometry().bounds(10)
        layers=[]
        for year in (first-1,first,second,second+1):
            col=(ee.ImageCollection(OB).filterBounds(geog).filterDate(f"{year}-01-01",f"{year+1}-01-01")
                 .select("building_presence").sort("system:index"))
            blank=ee.Image.constant(0).rename("building_presence").toFloat().selfMask()
            layers.append(ee.ImageCollection.fromImages([blank]).merge(col).mosaic())
        a,b,c,d=layers
        old_high=a.gte(.75).And(b.gte(.75))
        old_low=a.lte(.25).And(b.lte(.25))
        new_high=c.gte(.75).And(d.gte(.75))
        new_low=c.lte(.25).And(d.lte(.25))
        gain=old_low.And(new_high).rename("gain")
        loss=old_high.And(new_low).rename("loss")
        # Four-year masks must cover every sample. A missing footprint survey
        # tile cannot make a change look stable.
        valid=gain.mask().unmask(0,False).rename("valid")
        img=gain.addBands(loss).addBands(valid)
        rows=img.reduceRegions(collection=fc,reducer=ee.Reducer.sum().unweighted(),crs=crs,
                               crsTransform=[4,0,0,0,-4,0]).getInfo()["features"]
        out=[None]*len(cells)
        for f in rows:
            p=f["properties"]
            if p.get("valid")==2500:
                out[p["i"]]={k:float(p[k])*16 for k in TARGETS}
        return out
    return cached(["building_ob_4m_flips_v1",OB,crs,cells,first,second],get)


def sensor_features(before,after):
    def medians(rows):
        groups=defaultdict(list)
        for r in rows: groups[r["source"],r["track"]].append(r)
        out={}
        for (sensor,track),rr in groups.items():
            if len({r["day"] for r in rr})>=2:
                out[sensor,track]=np.array([median(r[f] for r in rr) for f in FIELDS[sensor]])
        return out
    a,b=medians(before),medians(after)
    out={}
    for sensor in FIELDS:
        pairs=[np.concatenate([a[t],b[t],b[t]-a[t]]) for t in sorted(a.keys()&b.keys()) if t[0]==sensor]
        out[sensor]=np.median(pairs,axis=0).tolist() if pairs else None
    return out


def predictors(ee,crs,cells,before,after):
    if anchor_range(before)[1]>anchor_range(after)[0]:
        raise ValueError("building comparison requires disjoint endpoint windows")
    rows=[history(ee,crs,cells,*anchor_range(anchor),width=200) for anchor in (before,after)]
    ghsl=context(ee,crs,cells)
    return [dict(**sensor_features(a,b),ghsl=s) for a,b,s in zip(*rows,ghsl,strict=True)]


def vector(row, mode):
    if row["ghsl"] is None or any(row[s] is None for s in MODES[mode]):
        return None
    return [row["ghsl"]]+[n for s in MODES[mode] for n in row[s]]


def weak_target(area):
    if area is None: return None
    if area>=100: return True
    if area==0: return False
    return None


def fit(rows):
    models={}
    for mode in MODES:
        models[mode]={}
        for target in TARGETS:
            observations=[(x,y) for r in rows if (x:=vector(r,mode)) is not None and (y:=r[target]) is not None]
            if len({y for x,y in observations})<2:
                models[mode][target]=None
                continue
            x,y=map(np.array,zip(*observations))
            scaler=StandardScaler().fit(x)
            # Balanced weighting yields a ranking, not a calibrated probability.
            model=LogisticRegression(class_weight="balanced",C=1,max_iter=1000).fit(scaler.transform(x),y)
            models[mode][target]={"mean":scaler.mean_.tolist(),"scale":scaler.scale_.tolist(),
                                 "coef":model.coef_[0].tolist(),"intercept":float(model.intercept_[0]),
                                 "positive":int(y.sum()),"negative":int(len(y)-y.sum())}
    return models


def classify(row,models):
    result={}
    for target in TARGETS:
        result.update({target:None,target+"_score":None,target+"_mode":None})
        for mode in MODES:
            v=vector(row,mode)
            model=models[mode][target]
            if v is None or model is None: continue
            logit=np.dot((np.array(v)-model["mean"])/model["scale"],model["coef"])+model["intercept"]
            s=float(1/(1+np.exp(-np.clip(logit,-700,700))))
            result.update({target:s>=.5,target+"_score":s,target+"_mode":mode})
            break
    result["mode"]=result["gain_mode"] if result["gain_mode"]==result["loss_mode"] else "target_specific"
    return result


def classify_blocks(ee, crs, cells, before, after):
    models=read(BUNDLE)["models"]
    return [classify(r,models) for r in predictors(ee,crs,cells,before,after)]


def metrics(rows,target,baseline=False):
    labels=[r for r in rows if r[target] is not None]
    pairs=[(bool(r[target]),0.0 if baseline else r[target+"_score"]) for r in labels if r[target+"_score"] is not None]
    truth=np.array([y for y,s in pairs],dtype=bool)
    scores=np.array([s for y,s in pairs])
    reported=scores>=.5
    return {"reference_known":len(labels),"reference_unknown":len(rows)-len(labels),
            "observed":len(pairs),"positive_observed":int(truth.sum()),
            "positives_including_abstentions":sum(bool(r[target]) for r in labels),
            "tp":int((reported&truth).sum()),"fp":int((reported&~truth).sum()),
            "tn":int((~reported&~truth).sum()),"fn_observed":int((~reported&truth).sum()),
            "auc":float(roc_auc_score(truth,scores)) if len(set(truth))==2 else None,
            "average_precision":float(average_precision_score(truth,scores)) if len(set(truth))==2 else None}


def collect():
    import gzip,json
    ee=connect()
    rows=[]
    for site,(lon,lat) in seen_sites().items():
        crs,cells=grid(lon,lat,side=7,spacing=200)
        for a,b in PAIRS:
            labs=dated_labels(ee,crs,cells,a,b)
            pred=(predictors(ee,crs,cells,f"{a}-06-30",f"{b}-06-30") if any(v is not None for v in labs)
                  else [dict(radar=None,optical=None,ghsl=None)]*len(labs))
            for xy,y,x in zip(cells,labs,pred,strict=True):
                rows.append(dict(site=site,xy=xy,crs=crs,before=a,after=b,**x,proxy_area=y,
                                 **{k:weak_target(y[k] if y else None) for k in TARGETS}))
            print(site,a,b,sum(v is not None for v in labs),flush=True)
    DATASET.write_bytes(gzip.compress(json.dumps(rows,separators=(",",":"),allow_nan=False).encode(),mtime=0))


def train():
    import gzip,json
    rows=json.loads(gzip.decompress(DATASET.read_bytes()))
    by_site={}
    all_rows=[]
    with threadpool_limits(limits=1):
        for site in seen_sites():
            models=fit([r for r in rows if r["site"]!=site])
            test=[dict(**r,**{k:v for k,v in classify(r,models).items() if k not in TARGETS})
                  for r in rows if r["site"]==site]
            all_rows.extend(test)
            by_site[site]={t:metrics(test,t) for t in TARGETS}
        bundle={"method":"balanced L2 logistic per endpoint and source; score 0.5 operating point",
                "development_sha256":sha256(DATASET.read_bytes()).hexdigest(),"sites":list(seen_sites()),
                "models":fit(rows)}
    save(BUNDLE,bundle)
    save(RESULTS,{"rows":len(rows),"cities":len(by_site),"leave_city_out":by_site,
                  "all":{t:{"model":metrics(all_rows,t),"no_detection":metrics(all_rows,t,True)} for t in TARGETS}})


def map_site(ee,lon,lat,before,after):
    from pyproj import Transformer
    from shapely.geometry import box,mapping
    from shapely.ops import transform
    if not (-180<=lon<180 and -80<=lat<84):
        raise ValueError("centre is outside UTM coverage")
    crs,cells=grid(lon,lat,side=7,spacing=200)
    estimates=classify_blocks(ee,crs,cells,before,after)
    to_ll=Transformer.from_crs(crs,4326,always_xy=True).transform
    features=[]
    for (x,y),estimate in zip(cells,estimates,strict=True):
        geom=transform(to_ll,box(x,y,x+200,y+200))
        features.append({"type":"Feature","id":f"{crs}/{x}/{y}",
                         "geometry":mapping(geom),"properties":estimate})
    return {"type":"FeatureCollection","features":features,"epochs":[before,after],
            "model_sha256":sha256(BUNDLE.read_bytes()).hexdigest(),
            "status":"experimental weak-reference classification","block_m":200}


if __name__=="__main__":
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("collect","train","all","map"))
    parser.add_argument("--centre",type=float,nargs=2,metavar=("LON","LAT"))
    parser.add_argument("--epochs",nargs=2,metavar=("BEFORE_DATE","AFTER_DATE"))
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.action in ("collect","all"): collect()
    if args.action in ("train","all"): train()
    if args.action=="map":
        if not args.centre or not args.epochs or args.output is None or args.output.exists():
            parser.error("map needs --centre, --epochs and a new --output path")
        value=map_site(connect(),*args.centre,*args.epochs)
        with args.output.open("x") as f:
            json.dump(value,f,allow_nan=False)
            f.write("\n")
