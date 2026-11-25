"""DEV-only surface-water reference at the Midland gauge. No reserve or hazard-model inputs."""
import argparse
import csv
import fcntl
import hashlib
import io
import json
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path

import numpy as np
from pyproj import Transformer

HERE = Path(__file__).resolve().parent
INCIDENT = "midland-2020-05-19"
BEFORE = "LC08_021030_20200504"
AFTER = "LC08_021030_20200520"
BANDS = ("SR_B3","SR_B4","SR_B5","SR_B6","QA_PIXEL","QA_RADSAT")
CODES = {"unobserved":0,"confident_dry":1,"confident_flooded":2,"ambiguous":3}


def allow_pair(row,scene):
    # Only the exact dated pair identified by the EROS event publication can be queried.
    if (row["incident_id"] != INCIDENT or row["split"] != "DEV" or
        date.fromisoformat(row["date"]) >= date(2022,1,1) or
        scene["scene"] != "LC08_L2SP_021030_20200520_02_T1" or
        not scene["utc"].startswith("2020-05-20") or row["screening"] != "timed_footprint"):
        raise ValueError("Only the catalogued Midland 2020 development pair is allowed")


def clear(qa, sat):
    invalid = (qa & 63) != 0  # fill, dilated cloud, cirrus, cloud, shadow, snow
    cloud_confidence = (qa >> 8) & 3
    return ((qa >= 0) & (sat == 0) & ((qa & 64) != 0) &
            ~invalid & (cloud_confidence < 2))


def indicators(values, prefix):
    green,red,nir,swir=(values[prefix+b].astype(float)*0.0000275-0.2 for b in BANDS[:4])
    qa,sat=(values[prefix+b] for b in BANDS[4:])
    valid=clear(qa,sat)
    for b in BANDS[:4]:
        valid &= values[prefix+b] > 0
    # MNDWI > 0 and NDVI > 0.3 use the existing GeoWatch optical definitions.
    # A nonpositive denominator gives no interpretable sign or ratio.
    good=(green+swir>0) & (nir+red>0)
    water_bit=(qa & 128) != 0
    water=good & water_bit & (green>swir)
    land=good & ~water_bit & (green<swir)
    vegetated=(nir-red) > .3*(nir+red)
    return valid,water,land,vegetated


def classify(values):
    pre,_,pre_land,pre_green=indicators(values,"before_")
    post,post_water,post_land,green=indicators(values,"after_")
    # Only land-cover classes with an open view can decide ground inundation.
    # NLCD barren, grassland, pasture/hay and cultivated crops; leaf cover can still obscure soil.
    open_land=np.isin(values["cover"],[31,71,81,82])
    observed=(pre & post & open_land & (values["history"]>0) &
              (values["occurrence"]>=0) & (values["occurrence"]<80))
    state=np.zeros(observed.shape,np.uint8)
    state[observed]=CODES["ambiguous"]
    visible=observed & pre_land & ~pre_green & ~green
    state[visible & post_water]=CODES["confident_flooded"]
    state[visible & post_land]=CODES["confident_dry"]
    return state


def fetch(ee,grid):
    stack=[]
    for prefix,scene in [("before_",BEFORE),("after_",AFTER)]:
        image=ee.Image("LANDSAT/LC08/C02/T1_L2/"+scene)
        stack.append(image.select(list(BANDS),[prefix+b for b in BANDS]))
    stack.extend([ee.Image("USGS/NLCD_RELEASES/2019_REL/NLCD/2019").select("landcover").rename("cover"),
                  ee.Image("JRC/GSW1_4/Metadata").select("valid_obs").rename("history"),
                  ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0).rename("occurrence")])
    a,b,c,d,e,f=grid["transform"]
    h,w=grid["shape"]
    request={"expression":ee.Image.cat(stack).toInt32().unmask(-1),"fileFormat":"NUMPY_NDARRAY",
             "grid":{"dimensions":{"width":w,"height":h},"crsCode":grid["crs"],
                     "affineTransform":{"scaleX":a,"shearX":b,"translateX":c,"shearY":d,"scaleY":e,"translateY":f}}}
    return ee.data.computePixels(request)


def main():
    import ee
    from dotenv import dotenv_values
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cache",type=Path)
    args=ap.parse_args()
    args.cache.mkdir(parents=True,exist_ok=True)
    with (HERE/"catalog.csv").open() as f:
        row=next(x for x in csv.DictReader(f) if x["incident_id"]==INCIDENT)
    scenes=json.loads((HERE/"scene_metadata.json").read_text())[INCIDENT]["scenes"]
    scene=next(x for x in scenes if x["scene"]=="LC08_L2SP_021030_20200520_02_T1")
    allow_pair(row,scene)
    lon,lat=float(row["longitude"]),float(row["latitude"])
    x,y=Transformer.from_crs(4326,32617,always_xy=True).transform(lon,lat)
    # Use complete native-sized 30 m cells inside a centred 8 km box.
    west,north=30*np.ceil((x-4000)/30),30*np.floor((y+4000)/30)
    width=int(np.floor((x+4000-west)/30))
    height=int(np.floor((north-y+4000)/30))
    grid={"crs":"EPSG:32617","shape":[height,width],"transform":[30,0,float(west),0,-30,float(north)]}
    recipe=hashlib.sha256((Path(__file__).read_text()+json.dumps(grid)).encode()).hexdigest()
    cache=args.cache/(recipe+".npy")
    if not cache.exists():
        if shutil.disk_usage(args.cache).free<15_000_000_000:
            raise RuntimeError("Less than 15 GB available")
        with open("/private/tmp/geowatch-change-round2-ee.lock","a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            ee.Initialize(project=dotenv_values(Path.home()/"geowatch/.env")["GEE_PROJECT_ID"])
            values=fetch(ee,grid)
            with tempfile.NamedTemporaryFile(dir=args.cache,delete=False) as tmp:
                np.save(tmp,values,allow_pickle=False)
            os.replace(tmp.name,cache)
    state=classify(np.load(cache,allow_pickle=False))
    if state.shape != tuple(grid["shape"]):
        raise ValueError("Unexpected source grid")
    meta={"unit":INCIDENT,"event":row["date"],"role":"dev","incident":INCIDENT,"block":1,
          "grid":grid,"state_codes":CODES,"before":BEFORE,"after":AFTER,"acquisition":scene,
          "support":"Open-land optical change proxy from one Landsat pair, acquisition time only.",
          "source":"USGS Landsat and NLCD; EC JRC/Google","recipe_sha256":recipe}
    out=HERE/"dev_references"
    out.mkdir(exist_ok=True)
    payload=io.BytesIO()
    np.savez_compressed(payload,meta=json.dumps(meta),state=state,flooded=state==2,valid=(state==1)|(state==2))
    content=payload.getvalue()
    report=dict(meta=meta,counts={k:int(np.sum(state==v)) for k,v in CODES.items()},
                sha256=hashlib.sha256(content).hexdigest())
    # Atomic individual outputs; the checksum in the receipt detects any interrupted pair.
    for path,body in [(out/"midland_2020.npz",content),
                      (out/"midland_2020.json",(json.dumps(report,indent=2)+"\n").encode())]:
        with tempfile.NamedTemporaryFile(dir=out,delete=False) as tmp:
            tmp.write(body)
        os.replace(tmp.name,path)
    print(json.dumps(report["counts"]))


if __name__=="__main__":
    main()
