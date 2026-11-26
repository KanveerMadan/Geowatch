"""Pre-register and execute a single held-out Round 2 test with resumable receipts."""
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import argparse
import json
import math
import shutil
from pathlib import Path
import subprocess

import numpy as np
from pyproj import Geod

from . import data
from .forest import forest
from .water import water
from experiments.change_history import building_endpoints as sn
from experiments.change_history import building_multisensor as survey

HERE=data.HERE
ROOT=HERE.parents[1]
PLAN=HERE/"fresh_plan.json"
LOCK=HERE/"fresh_lock.json"
OUTPUT=HERE/"fresh_result.json"
BRANCH="refs/heads/codex/change-history"
TARGETS={"gain":"water_gain","loss":"water_loss","loss_forest":"forest_loss"}
WATER_CLASSES={1:"gain",2:"loss",3:"stable_dry",4:"stable_wet"}
FOREST_CLASSES={1:"loss_forest",2:"stable_forest"}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def sealed_files():
    paths=[Path(__file__),PLAN,HERE/"fresh_protocol.md",HERE/"fresh_exclusions.json", HERE/"building_model.json",
           HERE/"buildings.py",HERE/"monitor_lock.py",HERE/"forest.py",HERE/"water.py",HERE/"data.py",
           Path(sn.__file__),Path(survey.__file__)]
    from experiments.change_history import spacenet_survey
    paths.extend([Path(spacenet_survey.__file__),ROOT/"vector/change_observations.py",ROOT/"vector/units.py",
                  sn.SPLITS,survey.MANIFEST,
                  sn.HERE/"ordinary_city_protocol.json",sn.HERE/"ordinary_city_default_protocol.json",
                  sn.HERE/"known_change_protocol.json"])
    return {str(p.relative_to(ROOT)):digest(p) for p in paths}


def seal():
    payload={"sha256":sealed_files(),"created_utc":datetime.now(timezone.utc).isoformat()}
    with LOCK.open("x") as f:
        json.dump(payload,f,indent=2,sort_keys=True)
        f.write("\n")


def git(*args):
    return subprocess.check_output(["git","-C",str(ROOT),*args],text=True).strip()


def check_pushed(revision):
    if len(revision)!=40 or any(c not in "abcdef0123456789" for c in revision):
        raise ValueError("supply the full pushed pre-registration commit")
    files=data.read(LOCK)["sha256"]
    if files!=sealed_files():
        raise ValueError("sealed evaluation or model bytes changed")
    if git("rev-parse","HEAD") != revision or git("ls-remote","origin",BRANCH).split()[0] != revision:
        raise ValueError("local HEAD and live origin must equal the registered revision")
    for name,expected in {**files,str(LOCK.relative_to(ROOT)):digest(LOCK)}.items():
        raw=subprocess.check_output(["git","-C",str(ROOT),"show",revision+":"+name])
        if sha256(raw).hexdigest()!=expected:
            raise ValueError("published bytes differ: "+name)


def raster(ee, image, crs, x0, top, n):
    grid={"crsCode":crs,"dimensions":{"width":n,"height":n},
          "affineTransform":{"translateX":x0,"translateY":top,"shearX":0,"shearY":0,"scaleX":100,"scaleY":-100}}
    return ee.data.computePixels({"expression":image.unmask(0,False).toUint16(),
                                  "fileFormat":"NUMPY_NDARRAY","grid":grid})


def support(ee, flag, crs):
    fine=ee.Projection(crs,[20,0,0,0,-20,0])
    coarse=ee.Projection(crs,[100,0,0,0,-100,0])
    return flag.unmask(0,False).reproject(fine).reduceResolution(ee.Reducer.min(),maxPixels=100).reproject(coarse)


def landsat(ee, geom, start, end, spec):
    a,b=spec["landsat_collections"]
    return ee.ImageCollection(a).merge(ee.ImageCollection(b)).filterBounds(geom).filterDate(start,end)


def clear(im):
    return im.select("QA_PIXEL").bitwiseAnd(63).eq(0).And(im.select("QA_RADSAT").eq(0))


def counts(ee,geom,first,last,crs,spec,*,first_look=False):
    # A day can contain overlapping scenes. Each date contributes at most one vote.
    col=landsat(ee,geom,first,last,spec)
    def states(im):
        wet=im.select("QA_PIXEL").bitwiseAnd(128).neq(0)
        good=clear(im)
        return (support(ee,wet.And(good),crs).rename("wet")
                .addBands(support(ee,wet.Not().And(good),crs).rename("dry"))
                .set("day",im.date().format("YYYY-MM-dd")))
    states_col=col.map(states)
    days=states_col.aggregate_array("day").distinct()
    def day_state(day):
        votes=states_col.filter(ee.Filter.eq("day",day)).max()
        agree=votes.select("wet").And(votes.select("dry")).Not()
        votes=votes.multiply(agree).toByte()
        if first_look:
            offset=ee.Date(day).difference(ee.Date(first),"day").add(1)
            dates=(votes.selfMask().multiply(0).add(offset)
                   .rename(["first_wet","first_dry"]).toUint16())
            votes=votes.addBands(dates)
        return votes
    # Empty date windows have zero wet and zero dry support.
    daily=ee.ImageCollection.fromImages(days.map(day_state))
    zero=ee.Image.constant([0,0]).rename(["wet","dry"]).toByte()
    if first_look:
        zero=zero.addBands(zero.rename(["first_wet","first_dry"]).toUint16().selfMask())
    daily=daily.merge(ee.ImageCollection.fromImages([zero]))
    result=daily.select(["wet","dry"]).sum()
    if first_look:
        result=result.addBands(daily.select(["first_wet","first_dry"]).min())
    return result


def water_labels(ee,geom,crs,start,end,spec):
    before=counts(ee,geom,str(date.fromisoformat(start)-timedelta(days=90)),start,crs,spec)
    after=counts(ee,geom,start,end,crs,spec,first_look=True)
    wet=before.select("wet").gte(2).And(before.select("dry").eq(0))
    dry=before.select("dry").gte(2).And(before.select("wet").eq(0))
    pw,pd=after.select("wet"),after.select("dry")
    label=(dry.And(pw.gte(1)).add(wet.And(pd.gte(1)).multiply(2))
            .add(dry.And(pd.gte(2)).And(pw.eq(0)).multiply(3))
            .add(wet.And(pw.gte(2)).And(pd.eq(0)).multiply(4))).rename("label")
    return label.addBands(after.select(["first_wet","first_dry"]))


def forest_labels(ee,geom,crs,spec):
    year=spec["forest_year"]; gfc=ee.Image(spec["forest_reference"])
    forest00=gfc.select("datamask").eq(1).And(gfc.select("treecover2000").gte(30))
    ly=gfc.select("lossyear")
    loss=support(ee,forest00.And(ly.eq(year-2000)),crs)
    def endpoint(y):
        def ndvi(im):
            sr=im.select(["SR_B5","SR_B4"]).multiply(.0000275).subtract(.2)
            return sr.normalizedDifference(["SR_B5","SR_B4"]).updateMask(clear(im)).toFloat()
        empty=ee.Image.constant(0).rename("nd").toFloat().selfMask()
        col=(landsat(ee,geom,f"{y}-07-01",f"{y}-11-01",spec).map(ndvi)
             .merge(ee.ImageCollection.fromImages([empty])))
        return col.median().updateMask(col.count().gte(2))
    before,after=endpoint(year-1),endpoint(year)
    green=before.gte(.5).And(after.gte(.5)).And(before.subtract(after).abs().lte(.1))
    stable=support(ee,forest00.And(ly.eq(0).Or(ly.gt(year-2000))).And(green),crs)
    return loss.add(stable.multiply(2)).rename("label")


def choose(arr,site,x0,top,codes,spec):
    rows=[]
    for k,label in codes.items():
        yy,xx=np.where(arr==k)
        choices=[(int(x0+c*100),int(top-(r+1)*100)) for r,c in zip(yy,xx)]
        ordered=sorted(choices,key=lambda xy:sha256(f"r2/{site}/{xy[0]}/{xy[1]}".encode()).digest())
        kept=[]
        for xy in ordered:
            if all(math.dist(xy,other)>=spec["minimum_separation_m"] for other in kept):
                kept.append(xy)
            if len(kept)==spec["cap_per_direction"]:break
        rows.extend({"xy":list(xy),"label":label} for xy in kept)
    return rows


def land_site(ee,site,kind,spec):
    name,lon,lat,*period=site
    crs,[(x,y)]=data.grid(lon,lat,1)
    width=spec["box_width_m"]; x0,top=x-width//2,y+width//2
    geom=ee.Geometry.Rectangle([x0,top-width,x0+width,top],proj=crs,geodesic=False)
    is_water=kind=="water"
    if is_water:
        start,end,_=period; image=water_labels(ee,geom,crs,start,end,spec)
        history_start=str(date.fromisoformat(start)-timedelta(days=120)); codes=WATER_CLASSES
    else:
        year=spec["forest_year"]
        start,end,history_start=f"{year}-01-01",f"{year+1}-01-01",f"{year-2}-01-01"
        image=forest_labels(ee,geom,crs,spec); codes=FOREST_CLASSES
    path=run_folder()/f"refs-{name}.json"
    if not path.exists():
        pixels=raster(ee,image,crs,x0,top,width//100)
        arr=pixels["label"]
        chosen=choose(arr,name,x0,top,codes,spec)
        if is_water:
            for cell in chosen:
                label=cell["label"]
                if label in ("gain","loss"):
                    x,y=cell["xy"]
                    field="first_wet" if label=="gain" else "first_dry"
                    offset=int(pixels[field][(top-y)//100-1,(x-x0)//100])
                    if not 0<offset<=(date.fromisoformat(end)-date.fromisoformat(start)).days:
                        raise ValueError("reference date outside registered window")
                    cell["reference_observed_on"]=str(date.fromisoformat(start)+timedelta(days=offset-1))
        data.save(path,{"cells":chosen,"frame_counts":{
            codes.get(int(k),"unclassified"):int(n) for k,n in zip(*np.unique(arr,return_counts=True))}})
    refs=data.read(path)
    xy=[r["xy"] for r in refs["cells"]]
    pred=[]
    if xy:
        histories=data.history(ee,crs,xy,history_start,end)
        prior=(data.permanence(ee,crs,xy,start) if is_water else data.forest_cover(ee,crs,xy,start))
        for ref,h,p in zip(refs["cells"],histories,prior,strict=True):
            label=ref["label"]
            if is_water:
                det=water(h,start,end,p)
                target="gain" if label in ("gain","stable_dry") else "loss"
                hits=det[target]; observed=bool(hits) or target in det["observed_targets"]
                candidates=len([c for c in det["candidates"] if c["target"]==target])
            else:
                det=forest(h,start,end,forest_share=p); target="loss_forest"
                hits=[r["day"] for r in det["confirmed"]]; observed=bool(hits) or bool(det["observed_sources"])
                candidates=len(det["candidates"])
            first=min(hits,default=None)
            def lag(since):
                return (date.fromisoformat(first)-date.fromisoformat(since)).days if first and since else None
            pred.append({**ref,"target":TARGETS[target],"positive":not label.startswith("stable"),
                         "call":bool(hits) if observed else None,"confirmed_on":first,
                         "candidates":candidates,"days_from_monitor_start":lag(start),
                         "days_from_reference_observation":lag(ref.get("reference_observed_on"))})
    return {"site":name,"kind":kind,"crs":crs,"period":[start,end],"reference_frame":refs["frame_counts"],"rows":pred}


def building_sites(spec):
    # Only list previously unseen regional metadata after the publication guard.
    seen=data.read(HERE/"fresh_exclusions.json")+[r[1:3] for r in spec["water"]+spec["forest"]]
    sites=[obj.findtext("{*}Prefix").strip("/").split("/")[-1] for obj in
           sn._listing(sn.PREFIX,delimiter="/").findall("{*}CommonPrefixes")]
    geo=Geod(ellps="WGS84")
    result=[]
    for site in sorted(sites,key=lambda name:sha256(("round2/"+name).encode()).digest()):
        centre=sn._centre(site)
        if any(geo.inv(*centre,*c)[2]<spec["building_min_separation_km"]*1000 for c in seen): continue
        assets={}
        for obj in sn._listing(sn.PREFIX+site+"/").findall("{*}Contents"):
            key=obj.findtext("{*}Key");folder,filename=key.split("/")[-2:]
            if folder=="labels_match" and filename.endswith("_Buildings.geojson"): kind="tracked"
            elif folder=="labels" and filename.endswith("_UDM.geojson"): kind="unusable"
            elif folder=="images_masked": kind="image"
            else: continue
            month="_".join(filename.split("_")[2:4])
            assets.setdefault(month,{})[kind]={"key":key,"bytes":int(obj.findtext("{*}Size")),
                                               "etag":obj.findtext("{*}ETag").strip('"')}
        pairs=[]
        for m,v in sorted(assets.items()):
            y,num=m.split("_"); after=f"{int(y)+1}_{num}"
            if len(v)==3 and len(assets.get(after,{}))==3: pairs.append((m,after))
        if not pairs: continue
        epochs={m:assets[m] for m in pairs[-1]}
        if sum(v["bytes"] for e in epochs.values() for v in e.values())>32*1024**2:continue
        result.append({"site":site,"centre":centre,"epochs":epochs})
        seen.append(centre)
        if len(result)==spec["building_sites"]:break
    return result


def building_site(ee,site,spec):
    from .buildings import classify_blocks
    root=run_folder()
    survey.targets(root,site)
    with np.load(root/(site["site"]+"-targets.npz"),allow_pickle=False) as f:
        keep=f["keep"]; areas=f["y"]; groups=survey.group_blocks(f["ids"])
    ids=list(groups)
    crs=ids[0].split("/")[0]
    xy=[list(map(int,i.split("/")[1:])) for i in ids]
    first,last=sorted(site["epochs"])
    dates=[m.replace("_","-")+"-15" for m in (first,last)]
    preds=classify_blocks(ee,crs,xy,*dates)
    rows=[]
    for i,r in enumerate(preds):
        idx=groups[ids[i]]
        valid=bool(keep[idx].all())
        for j,target in enumerate(("gain","loss")):
            ref=float(areas[idx,j].sum()) if valid else None
            rows.append({"xy":xy[i],"target":"building_"+target,"area":ref,
                         "positive":(True if ref is not None and ref>=spec["building_target_m2"] else False if ref==0 else None),
                         "call":r[target],"score":r[target+"_score"],"mode":r[target+"_mode"]})
    return {"site":site["site"],"kind":"buildings","crs":crs,"period":dates,"rows":rows,"assets":site}


def metrics(rows):
    known=[r for r in rows if r["positive"] is not None]
    seen=[r for r in known if r["call"] is not None]
    pos=sum(r["positive"] for r in known)
    p=sum(r["positive"] for r in seen); n=len(seen)-p
    tp=sum(r["call"] and r["positive"] for r in seen)
    fp=sum(r["call"] and not r["positive"] for r in seen)
    div=lambda a,b:a/b if b else None
    ranked=[(r["score"],r["positive"]) for r in seen if r.get("score") is not None]
    ranking={}
    if ranked and len({y for _,y in ranked})==2:
        from sklearn.metrics import roc_auc_score,average_precision_score
        scores,labels=zip(*ranked)
        ranking={"auc":roc_auc_score(labels,scores),"average_precision":average_precision_score(labels,scores),
                 "constant_auc":.5,"constant_average_precision":sum(labels)/len(labels)}
    return {"ranking":ranking,"total":len(rows),"labelled":len(known),"positive":pos,"observable_positive":p,
            "observable_negative":n,"tp":tp,"fp":fp,"tn":n-fp,"fn_on_observed":p-tp,
            "unknown_prediction_on_positive":pos-p,"unknown_prediction_on_negative":len(known)-pos-n,
            "unknown_reference":len(rows)-len(known),"recall_all":div(tp,pos),"recall_observed":div(tp,p),
            "stable_false_alarm_fraction_observed":div(fp,n),"sample_precision":div(tp,tp+fp),
            "sensitivity_minus_false_alarm_fraction":tp/p-fp/n if p and n else None,
            "baseline_no_change":{"tp":0,"fp":0,"tn_on_observed":n,"fn_on_observed":p,
                                  "recall_all":div(0,pos),"recall_observed":div(0,p),"sample_precision":None,
                                  "sensitivity_minus_false_alarm_fraction":0 if p and n else None,
                                  "stable_false_alarm_fraction_observed":div(0,n),"unknown_predictions":len(known)-len(seen)}}


def run_folder():
    return data.CACHE/("fresh-"+digest(LOCK))


def evaluate(rev):
    check_pushed(rev)
    if OUTPUT.exists():raise ValueError("the single final evaluation is already published")
    if shutil.disk_usage(data.CACHE.parent).free < 15_000_000_000:
        raise RuntimeError("less than 15 GB available for held-out acquisition")
    spec=data.read(PLAN); folder=run_folder();folder.mkdir(parents=True,exist_ok=True)
    entry=folder/"entry.json"
    if not entry.exists():
        data.save(entry,{"remote_commit":rev,"remote_verified_utc":datetime.now(timezone.utc).isoformat(),
                         "lock_sha256":digest(LOCK)})
    receipt=data.read(entry)
    if receipt["remote_commit"]!=rev or receipt["lock_sha256"]!=digest(LOCK):raise ValueError("resumption lock mismatch")
    ee=data.connect()
    results=[]
    def checkpoint(name,fn):
        path=folder/f"result-{name}.json"
        if not path.exists():
            if shutil.disk_usage(folder).free < 15_000_000_000:
                raise RuntimeError("less than 15 GB available for held-out acquisition")
            data.save(path,fn())
        results.append(data.read(path))
        print(f"completed {name}",flush=True)
    for family in ("water","forest"):
        for site in spec[family]:
            checkpoint(site[0],lambda:land_site(ee,site,family,spec))
    chosen=folder/"building-roster.json"
    if not chosen.exists():data.save(chosen,building_sites(spec))
    for site in data.read(chosen):
        checkpoint(site["site"],lambda:building_site(ee,site,spec))
    for site_result in results:
        site_rows=site_result["rows"]
        site_targets={"water":["water_gain","water_loss"],"forest":["forest_loss"],
                      "buildings":["building_gain","building_loss"]}[site_result["kind"]]
        site_result["metrics"]={t:metrics([r for r in site_rows if r["target"]==t]) for t in site_targets}
    all_rows=[r for s in results for r in s["rows"]]
    targets=["water_gain","water_loss","forest_loss","building_gain","building_loss"]
    payload={"entry":receipt,"completed_utc":datetime.now(timezone.utc).isoformat(),
             "metrics":{t:metrics([r for r in all_rows if r["target"]==t]) for t in targets},"sites":results}
    if data.read(LOCK)["sha256"]!=sealed_files() or digest(LOCK)!=receipt["lock_sha256"]:
        raise ValueError("sealed inputs changed during this evaluation")
    data.save(OUTPUT,payload)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage",choices=["seal","run"]);p.add_argument("--revision")
    args=p.parse_args()
    if args.stage=="seal":seal()
    else:
        from .monitor_lock import ee_lock
        with ee_lock():
            evaluate(args.revision or "")
