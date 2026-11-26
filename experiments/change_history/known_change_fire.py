"""USGS/USFS MTBS incident-level holdout with date-verified Landsat references."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import os
from pathlib import Path
import re

from experiments.change_history import known_change as paired
from vector import change_detection, change_observations

HERE = paired.HERE
BOUNDARIES = "USFS/GTAC/MTBS/burned_area_boundaries/v1"
SEVERITY = "USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1/mtbs_CONUS_2022"
PROTOCOL = HERE / "known_change_fire_protocol.md"
MANIFEST = HERE / "known_change_fire_manifest.json"
LOCK = HERE / "known_change_fire_lock.json"
RESULT = HERE / "known_change_fire_results.json"


def parse_scene(identifier):
    match = re.fullmatch(r"([89])(\d{6})(\d{8})",str(identifier))
    if not match:
        return None
    mission, pathrow, stamp = match.groups()
    try:
        day = datetime.strptime(stamp,"%Y%m%d").date()
    except ValueError:
        return None
    index = f"LC0{mission}_{pathrow}_{stamp}"
    return mission,index,day


def digest_lock():
    return {"driver":paired.digest(__file__), "extractor":paired.digest(paired.__file__),
            "protocol":paired.digest(PROTOCOL),"manifest":paired.digest(MANIFEST),
            "detector":paired.digest(change_detection.__file__),
            "source_reader":paired.digest(change_observations.__file__)}


def boundaries(ee):
    return (ee.FeatureCollection(BOUNDARIES)
            .filterBounds(ee.Geometry.Rectangle([-125,24,-66,50]))
            .filter(ee.Filter.gte("Ig_Date",ee.Date("2022-01-01").millis()))
            .filter(ee.Filter.lt("Ig_Date",ee.Date("2023-01-01").millis())))


def metadata(ee):
    fires = boundaries(ee).filter(ee.Filter.eq("Incid_Type","Wildfire"))
    fields = ["Event_ID","Incid_Name","Ig_Date","BurnBndLon","BurnBndLat","Pre_ID","Post_ID"]
    features = fires.map(lambda f:f.set("v",f.toDictionary(fields))).aggregate_array("v").getInfo()
    counts = Counter(r["Event_ID"] for r in features)
    candidates = []
    for f in features:
        if counts[f["Event_ID"]] != 1:
            continue
        lat,lon = float(f["BurnBndLat"]),float(f["BurnBndLon"])
        if not (-125 < lon < -66 and 24 < lat < 50):
            continue
        day = datetime.fromtimestamp(f["Ig_Date"]/1000,timezone.utc).date()
        pre,post = parse_scene(f.get("Pre_ID")),parse_scene(f.get("Post_ID"))
        if pre and post and pre[2] < day <= post[2]:
            candidates.append({"id":f["Event_ID"],"name":f.get("Incid_Name"),
                "ignition":day.isoformat(),"pre":pre[1],"post":post[1],
                "crs":f"EPSG:{32601+int((lon+180)//6)}",
                "stratum":("west" if lon < -100 else "east")+("_north" if lat>=37 else "_south")})
    indices = {r[k] for r in candidates for k in ("pre","post")}
    confirmed = set()
    for mission in ("8","9"):
        ids = sorted(i for i in indices if i.startswith("LC0"+mission))
        for i in range(0,len(ids),200):
            col = ee.ImageCollection(f"LANDSAT/LC0{mission}/C02/T1_L2").filter(
                ee.Filter.inList("system:index", ids[i:i+200]))
            confirmed.update(col.aggregate_array("system:index").getInfo())
    verified = [r for r in candidates if r["pre"] in confirmed and r["post"] in confirmed]
    return {"wildfire_features":len(features),"dated_unique_landsat_candidates":len(candidates),
            "verified":verified}


def select_support(ee,crs,rows):
    fires = boundaries(ee)
    ids = [r["id"] for r in rows]
    focus = fires.filter(ee.Filter.inList("Event_ID",ids))
    fine = ee.Projection(crs,[20,0,0,0,-20,0])
    coarse = ee.Projection(crs,[100,0,0,0,-100,0])
    overlaps = fires.map(lambda f:f.set("n",1)).reduceToImage(["n"],ee.Reducer.count())
    valid = (ee.Image(SEVERITY).select("Severity").eq(4).And(overlaps.eq(1)).unmask(0,False)
             .reproject(fine).reduceResolution(ee.Reducer.min(),maxPixels=100))
    rank = ee.Image.random(2022).reproject(coarse).addBands(ee.Image.pixelCoordinates(coarse))
    eroded = focus.map(lambda f:f.setGeometry(f.geometry().buffer(-75,0.5)))
    output = rank.updateMask(valid).reduceRegions(collection=eroded,crs=coarse,
        reducer=ee.Reducer.min(3).unweighted().setOutputs(["rank","gx","gy"]),tileScale=2)
    fields = ["Event_ID","gx","gy"]
    by_id = {r["Event_ID"]:r for r in output.map(lambda f:f.set("r",f.toDictionary(fields)))
             .aggregate_array("r").getInfo() if r.get("gx") is not None}
    return [dict(row,xy=[100*int(by_id[row["id"]]["gx"]),-100*(1+int(by_id[row["id"]]["gy"]))])
            for row in rows if row["id"] in by_id]


def assignment(rows):
    counts = Counter()
    for row in sorted(rows,key=lambda r:sha256(r["id"].encode()).digest()):
        row["split"] = "test" if counts[row["stratum"]] < 3 else "reserved"
        counts[row["stratum"]] += 1
    return sorted(rows,key=lambda r:r["id"])


def prepare(ee,cache):
    if LOCK.exists() or MANIFEST.exists():
        raise ValueError("fire manifest already frozen")
    root = cache/paired.digest(PROTOCOL)
    info = root/"reference_metadata.json"
    if not info.exists():
        paired.save(info,metadata(ee))
    meta = paired.read(info)
    by_crs = defaultdict(list)
    for row in meta["verified"]:
        by_crs[row["crs"]].append(row)
    selected = []
    for crs,regions in sorted(by_crs.items()):
        for i in range(0,len(regions),24):
            key = root/f"support-{crs.split(':')[1]}-{i}.json"
            if not key.exists():
                paired.save(key,select_support(ee,crs,regions[i:i+24]))
            selected += paired.read(key)
    doc = {"wildfire_features":meta["wildfire_features"],
           "dated_unique_landsat_candidates":meta["dated_unique_landsat_candidates"],
           "verified_pre_post":len(meta["verified"]),"incidents":assignment(selected)}
    paired.save(MANIFEST,doc)
    paired.save(LOCK,digest_lock())


def score(row,values):
    day = date.fromisoformat(row["ignition"])
    end = (day+timedelta(days=90)).isoformat()
    records = [{"source":"sentinel2","date":r[0],"track":r[1],"support_id":row["id"],
                "values":dict(zip(paired.SIGNALS,r[2:],strict=True))} for r in values]
    result = change_detection.detect_cell(row["id"],records,start=day.isoformat(),end=end)
    episodes = sorted((e for e in result["events"] if e["transition"]=="greenness_loss"
        and e["confirmed_on"]),key=lambda e:e["confirmed_on"])
    target = [s for s in result["series"] if s["signal"]=="ndvi"]
    first = episodes[0]["confirmed_on"] if episodes else None
    visible = sorted({r[0] for r in values if row["ignition"]<=r[0]<end})
    return {"id":row["id"],"stratum":row["stratum"],"name":row["name"],"ignition":row["ignition"],
        "confirmed":bool(first),"fully_observed":any(s["status"]=="observed" for s in target),
        "partially_or_fully_observed":any(s["status"] in ("observed","partial_observation") for s in target),
        "first_usable":visible[0] if visible else None,"usable_monitor_dates":len(visible),
        "confirmed_on":first,"days_since_ignition":(date.fromisoformat(first)-day).days if first else None}


def evaluate(ee,cache,workers):
    lock = paired.read(LOCK)
    if digest_lock() != lock:
        raise ValueError("fire study lock mismatch")
    root = cache/paired.digest(LOCK)
    test = [r for r in paired.read(MANIFEST)["incidents"] if r["split"]=="test"]
    jobs = []
    for r in test:
        day = date.fromisoformat(r["ignition"])
        history = day.replace(year=day.year-5).isoformat()
        region = {"crs":r["crs"],"cells":[{"id":r["id"],"xy":r["xy"]}]}
        path = root/r["id"]/"catalog.json"
        if not path.exists():
            paired.save(path,paired.image_catalog(ee,region,history,(day+timedelta(days=90)).isoformat()))
        records = paired.read(path)
        for i in range(0,len(records),48):
            jobs.append((region, records[i:i+48],path.parent/f"block-{i:04}.json"))
    def fetch(job):
        region,records,path = job
        if not path.exists():
            paired.save(path,paired.acquire(ee,region,records))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(fetch,jobs))
    values = defaultdict(list)
    for _,_,path in jobs:
        for key,rows in paired.read(path).items():
            values[key] += rows
    paired.save(RESULT,{"lock":lock,"incidents":[score(r,values[r["id"]]) for r in test]})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("stage",choices=["prepare","run"]); p.add_argument("--cache",type=Path,required=True)
    p.add_argument("--workers",type=int,choices=[1,2,3],default=2)
    p.add_argument("--project", default=os.getenv("GEE_PROJECT_ID"))
    args=p.parse_args()
    source = paired.read(paired.PROTOCOL)
    actual = (paired.digest(change_detection.__file__),paired.digest(change_observations.__file__))
    if actual != (source["detector_sha256"],source["observations_sha256"]):
        raise ValueError("frozen detector version mismatch")
    ee = paired.initialise(args.project)
    if args.stage=="prepare":
        prepare(ee,args.cache)
    else:
        evaluate(ee,args.cache,args.workers)


if __name__ == "__main__":
    main()
