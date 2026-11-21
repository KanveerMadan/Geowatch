"""Serial Earth Engine feature extraction on fixed UTM blocks, with resumable local batches."""
from datetime import date, timedelta
from pathlib import Path
import hashlib
import json
import os
import shutil
from tempfile import NamedTemporaryFile

from pyproj import Transformer

HERE = Path(__file__).resolve().parent
CACHE = Path(os.getenv("GW_R2_CACHE", "/private/tmp/geowatch-change-round2"))
S1 = "COPERNICUS/S1_GRD"
S2 = "COPERNICUS/S2_SR_HARMONIZED"
GSW = "JRC/GSW1_4/MonthlyHistory"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w",dir=path.parent,delete=False) as f:
        json.dump(value,f,allow_nan=False,separators=(",",":"))
        f.write("\n")
    os.replace(f.name,path)


def read(path):
    return json.loads(path.read_text())


def connect():
    from dotenv import load_dotenv
    import ee
    load_dotenv(Path.home()/ "geowatch/.env")
    ee.Initialize(project=os.environ["GEE_PROJECT_ID"])
    ee.data.setDeadline(120000)
    return ee


def cached(key, fn):
    tag=hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()
    path=CACHE/(tag+".json")
    if not path.exists():
        if shutil.disk_usage(CACHE.parent).free < 15_000_000_000:
            raise RuntimeError("download paused: less than 15 GB free")
        save(path,fn())
    return read(path)


def grid(lon,lat,side=3,spacing=100):
    crs=f"EPSG:{(32601 if lat>=0 else 32701)+int((lon+180)//6)}"
    a,b=Transformer.from_crs(4326,crs,always_xy=True).transform(lon,lat)
    x,y=int(a//spacing)*spacing,int(b//spacing)*spacing
    return crs,[(x+(i-side//2)*spacing,y+(j-side//2)*spacing) for i in range(side) for j in range(side)]


def geometry(ee,crs,cells,width):
    return ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x,y,x+width,y+width],proj=crs,geodesic=False),
                                {"i":i}) for i,(x,y) in enumerate(cells)])


def history(ee,crs,cells,start,end,*,sensors=("radar","optical"),width=100):
    if len(cells)>150 or width not in (100,200):
        raise ValueError("bounded request requires up to 150 blocks")
    fc=geometry(ee,crs,cells,width)
    region=fc.geometry().bounds(10)
    dem=ee.ImageCollection("COPERNICUS/DEM/GLO30").filterBounds(region).select("DEM").mosaic().setDefaultProjection(crs,None,30)
    terrain=ee.Terrain.products(dem)
    def batch(sensor,first,last):
        col=ee.ImageCollection(S1 if sensor=="radar" else S2).filterBounds(region).filterDate(first,last)
        if sensor=="radar":
            col=(col.filter(ee.Filter.eq("instrumentMode","IW")).filter(ee.Filter.eq("resolution_meters",10))
                 .filter(ee.Filter.listContains("transmitterReceiverPolarisation","VH"))
                 .filter(ee.Filter.listContains("transmitterReceiverPolarisation","VV")))
        def extract(im):
            if sensor=="radar":
                track=ee.String(im.get("platform_number")).cat("/").cat(im.getString("orbitProperties_pass")).cat("/").cat(im.getNumber("relativeOrbitNumber_start").format())
                # Approximate right-looking direction of Sentinel-1 over land. Signed
                # terrain slope along the look direction screens layover and shadow.
                az=ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(im.get("orbitProperties_pass"),"ASCENDING"),77,283))
                slope=terrain.select("slope").multiply(0.017453293)
                along=slope.tan().multiply(terrain.select("aspect").subtract(az).multiply(0.017453293).cos()).atan().multiply(57.29578)
                inc=im.select("angle")
                valid=inc.gt(30).And(inc.lt(46)).And(along.gt(inc.multiply(-1))).And(along.lt(ee.Image.constant(90).subtract(inc)))
                vv,vh=im.select("VV"),im.select("VH")
                texture=vh.reduceNeighborhood(ee.Reducer.stdDev(),ee.Kernel.square(1)).rename("texture")
                sample=vv.addBands(vh).addBands(texture).updateMask(valid)
            else:
                track=im.getNumber("SENSING_ORBIT_NUMBER").format()
                scl=im.select("SCL")
                sample=im.normalizedDifference(["B8","B4"]).rename("ndvi").addBands(
                    im.normalizedDifference(["B3","B11"]).rename("water")).updateMask(scl.gte(4).And(scl.lte(6)))
            mask=sample.mask().reduce(ee.Reducer.min())
            sample=sample.updateMask(mask).addBands(mask.unmask(0,False).rename("coverage"))
            stats=sample.reduceRegions(collection=fc,reducer=ee.Reducer.mean().unweighted(),crs=crs,crsTransform=[20,0,0,0,-20,0])
            fields=(["VV","VH","texture"] if sensor=="radar" else ["water","ndvi"])+["coverage","i"]
            rows=stats.filter(ee.Filter.gte("coverage",0.999999)).map(lambda f:f.set("rec",f.toDictionary(fields))).aggregate_array("rec")
            return im.set("batch",ee.Dictionary({"day":im.date().format("YYYY-MM-dd"),"track":track,"id":im.get("system:index"),"rows":rows}))
        return col.map(extract).aggregate_array("batch").getInfo()
    histories=[{} for c in cells]
    for sensor in sensors:
        t=date.fromisoformat(start)
        while t<date.fromisoformat(end):
            stop=min(date.fromisoformat(end),t+timedelta(days=90))
            frames=cached(["scene-v1",sensor,crs,cells,width,str(t),str(stop)],lambda:batch(sensor,str(t),str(stop)))
            for frame in sorted(frames,key=lambda f:f["id"]):
                for r in frame["rows"]:
                    idx=r["i"]
                    key=(sensor,frame["track"],frame["day"])
                    histories[idx][key]={**r,"source":sensor,"track":frame["track"],"day":frame["day"]}
            t=stop
    return [sorted(d.values(),key=lambda r:r["day"]) for d in histories]


def permanence(ee,crs,cells,start,width=100):
    def get():
        obs=ee.ImageCollection(GSW).filterDate("1984-01-01",start).select("water")
        n=obs.map(lambda im:im.gt(0)).sum()
        frac=obs.map(lambda im:im.eq(2)).sum().divide(n).updateMask(n.gt(0)).rename("p")
        # Require classified history across the whole reporting footprint.
        frac=frac.addBands(frac.mask().unmask(0,False).rename("valid"))
        rows=frac.reduceRegions(collection=geometry(ee,crs,cells,width),reducer=ee.Reducer.mean().unweighted(),crs=crs,crsTransform=[20,0,0,0,-20,0]).getInfo()["features"]
        out=[None]*len(cells)
        for f in rows:
            p=f["properties"]
            if p.get("valid",0)>=0.999999:
                out[p["i"]]=p.get("p")
        return out
    return cached(["permanence1",crs,cells,width,start],get)
