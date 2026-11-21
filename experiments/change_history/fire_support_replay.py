"""Repair and independently verify sampled fire cells before interpreting detection results."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from . import known_change as paired
from . import known_change_fire as fire

HERE = paired.HERE
MANIFEST = HERE / "fire_support_verified.json"
RESULT = HERE / "fire_support_result.json"
PLAN = """Same ten registered test incident IDs and time windows. Preserve original cell where
eligible. Otherwise search the nearest eligible 100 m cell in a 4.1 km square centred on the
original cell. Radius bounds reference retrieval. Break distance ties by increasing easting then
northing. Require all 25 fixed centres to be high severity and covered by exactly one 2022
perimeter. Require the cell centre inside its incident's 75 m negative buffer and the square
inside the incident. Independently recheck support at the exact coordinates using reduceRegion.
If no cell qualifies, count the incident as unresolved. No replacement incidents or changes to the
detector, observation history, or 90-day outcome. This amendment followed a geographic audit.
No original wildfire detector scores had been inspected when the amendment was designed."""


def seal():
    return {"driver":paired.digest(__file__), "original":paired.digest(fire.LOCK), "plan":PLAN}


def qualify(ee, r):
    x, y = r["xy"]
    radius = 20
    side = 2*radius + 1
    left, top = x-100*radius, y+100*(radius+1)
    fires = fire.boundaries(ee)
    boundary = fires.filter(ee.Filter.eq("Event_ID",r["id"])).first().geometry()
    high = ee.Image(fire.SEVERITY).select("Severity").eq(4).unmask(0,False)
    overlap = fires.map(lambda f:f.set("n",1)).reduceToImage(["n"],ee.Reducer.count()).eq(1)
    inside = ee.Image.constant(1).clip(boundary.buffer(-75,.5)).unmask(0,False)
    img = high.rename("high").addBands(overlap.rename("single")).addBands(inside.rename("inside")).unmask(0,False).toByte()
    grid = {"dimensions":{"width":side*5,"height":side*5},"crsCode":r["crs"],
            "affineTransform":{"scaleX":20,"scaleY":-20,"translateX":left,"translateY":top,"shearX":0,"shearY":0}}
    img = ee.data.computePixels({"expression":img,"fileFormat":"NUMPY_NDARRAY","grid":grid})
    blocks = lambda key: img[key].reshape(side,5,side,5)
    total = blocks("high").sum(axis=(1,3))
    keep = (total==25) & blocks("single").all(axis=(1,3)) & (blocks("inside")[:,2,:,2]==1)
    candidates = [(left+100*int(j),top-100*(int(i)+1)) for i,j in zip(*np.where(keep))]
    row = {**r,"original_xy":r["xy"],"original_high_count":int(total[radius,radius]),"xy":None}
    if candidates:
        a,b=min(candidates,key=lambda v:((v[0]-x)**2+(v[1]-y)**2,*v))
        geom=ee.Geometry.Rectangle([a,b,a+100,b+100],proj=r["crs"],geodesic=False)
        n=high.And(overlap).rename("n").reduceRegion(ee.Reducer.sum().unweighted(),geom,
            crs=r["crs"],crsTransform=[20,0,0,0,-20,0]).get("n")
        verified=ee.Dictionary({"count":n,"inside":boundary.contains(geom,1)}).getInfo()
        if verified != {"count":25,"inside":True}:
            raise ValueError(f"coordinate verification failed for {r['id']}: {verified}")
        row.update(xy=[a,b], verified=verified)
    return row


def run(ee,cache):
    if fire.digest_lock()!=paired.read(fire.LOCK):
        raise ValueError("original study files changed")
    if not MANIFEST.exists():
        test = [r for r in paired.read(fire.MANIFEST)["incidents"] if r["split"]=="test"]
        rows=[qualify(ee,r) for r in test]
        paired.save(MANIFEST,{"seal":seal(),"incidents":rows})
    doc=paired.read(MANIFEST)
    if doc["seal"]!=seal():
        raise ValueError("amended study files changed")
    root=cache/paired.digest(MANIFEST)
    jobs=[]
    for r in doc["incidents"]:
        if r["xy"] is None:
            continue
        day=date.fromisoformat(r["ignition"])
        region={"crs":r["crs"],"cells":[{"id":r["id"],"xy":r["xy"]}]}
        folder=root/r["id"]
        path=folder/"catalog.json"
        if not path.exists():
            paired.save(path,paired.image_catalog(ee,region,day.replace(year=day.year-5).isoformat(),
                                                   (day+timedelta(days=90)).isoformat()))
        catalog=paired.read(path)
        jobs.extend((region,catalog[i:i+48],folder/f"block-{i}.json") for i in range(0,len(catalog),48))
    def retrieve(job):
        region,scenes,path=job
        if not path.exists():
            paired.save(path,paired.acquire(ee,region,scenes))
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(retrieve,jobs))
    results=[]
    for r in doc["incidents"]:
        values=[v for region,_,path in jobs if region["cells"][0]["id"]==r["id"]
                for v in paired.read(path)[r["id"]]]
        results.append({**fire.score(r,values),"reference_eligible":r["xy"] is not None})
    paired.save(RESULT,{"manifest_sha256":paired.digest(MANIFEST),"incidents":results})


if __name__=="__main__":
    import os
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache",type=Path,required=True)
    args=ap.parse_args()
    run(paired.initialise(os.environ["GEE_PROJECT_ID"]),args.cache)
