"""Snapshot agreement of the frozen change detector with UNOSAT RCM-1 flood water."""
import argparse
from collections import Counter
import hashlib
import json
import mmap
import struct
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from pyproj import CRS, Transformer
import shapely
from shapely.geometry import box
from shapely.ops import transform

from analysis.change_history import _tile_arrays, _observations
from vector.change_detection import detect_cell
from vector.change_observations import open_history
from .amazon_clearing import HERE, ROOT, digest

MANIFEST = HERE / "monsoon_water_manifest.json"
RESULT = HERE / "monsoon_water_result.json"
DATE = "2022-06-18"
START, END = "2022-06-01", "2022-07-01"
EPSG = CRS.from_epsg(32646)


def design():
    return {"source":"United Nations Satellite Centre (UNOSAT), FL20220525BGD, RCM-1",
            "url":"https://unosat-maps.web.cern.ch/BD/FL20220525BGD/FL20220525BGD_SHP.zip",
            "snapshot":DATE, "monitor":[START,END], "sources":"default", "history_start":"2017-06-01",
            "rule":"One 4.8 km square centred on the UNOSAT AnalysisExtent centroid, snapped down "
            "to 100 m. Sample cells with all 25 production centres in both the analysis extent and "
            "the RCM-1 Flood Water class. Select at most 120 by SHA-256 of cell ID to bound work. "
            "No replacement or outside-polygon negatives. Score prospective June replay both as "
            "of June 18 and June 30. Count confirmed open_water_signal_gain and earliest usable "
            "optical dates. Radar backscatter alone has no locked water interpretation. Report all "
            "selected cells, complete water coverage, misses and unknowns. This single flood has "
            "no exact cell onset times, daily persistence labels, precision or global claim."}


def geometry(manifest):
    aoi = box(*manifest["bbox_utm"])
    inv = Transformer.from_crs(EPSG, 4326, always_xy=True).transform
    return SimpleNamespace(aoi=aoi, crs=EPSG, bbox=transform(inv, aoi).bounds)


def polygon_membership(shp, attrs, lon, lat):
    """ESRI polygon features use even/odd ring membership, including interior holes.

    The nationwide multipart shapes have millions of vertices. Read the borrowed
    coordinates of one ring at a time, skipping its GEOS construction when the
    ring bounds miss the grid. No index or sidecar is written into the source.
    """
    union = np.zeros(lon.shape, dtype=bool)
    west, east, south, north = lon.min(), lon.max(), lat.min(), lat.max()
    with shp.open("rb") as raw, mmap.mmap(raw.fileno(), 0, access=mmap.ACCESS_READ) as data:
        offset = 100
        for feature in attrs.itertuples():
            _, words = struct.unpack_from(">ii",data,offset)
            content = offset + 8
            offset = content + 2*words
            if feature.Water_Clas != "Flood Water":
                continue
            if feature.Sensor_ID != "RCM-1" or str(feature.Sensor_Dat)[:10] != DATE:
                raise ValueError("reference sensor or date mismatch")
            kind, = struct.unpack_from("<i",data,content)
            if kind != 5:
                raise ValueError("expected a two-dimensional ESRI Polygon")
            parts, count = struct.unpack_from("<ii",data,content+36)
            starts = np.frombuffer(data,"<i4",parts,content+44).tolist() + [count]
            points = np.frombuffer(data,"<f8",count*2,content+44+parts*4).reshape(-1,2)
            interior = np.zeros(lon.shape, dtype=bool)
            for a,b in zip(starts,starts[1:]):
                xy = points[a:b]
                x0,y0 = xy.min(axis=0)
                x1,y1 = xy.max(axis=0)
                if x1 < west or x0 > east or y1 < south or y0 > north:
                    continue
                selected = (lon>=x0)&(lon<=x1)&(lat>=y0)&(lat<=y1)
                if selected.any():
                    interior[selected] ^= shapely.contains_xy(shapely.Polygon(xy),lon[selected],lat[selected])
            del xy, points
            union |= interior
        if offset != len(data):
            raise ValueError("shapefile and attribute count disagree")
    return union


def prepare(folder):
    import pyogrio
    ext = folder / "RCM1_20220618_AnalysisExtent_Sylhet.shp"
    flood = folder / "RCM1_20220618_FloodExtent_Sylhet.shp"
    extent = pyogrio.read_dataframe(ext).to_crs(EPSG)
    area = shapely.union_all(extent.geometry)
    px, py = area.centroid.coords[0]
    x0, y0 = int(px//100)*100-2400, int(py//100)*100-2400
    manifest = {**design(), "bbox_utm":[x0,y0,x0+4800,y0+4800]}
    coords = np.arange(10,4800,20)
    x, y = np.meshgrid(x0+coords,y0+coords)
    lon, lat = Transformer.from_crs(EPSG,4326,always_xy=True).transform(x,y)
    attrs = pyogrio.read_dataframe(flood, read_geometry=False)
    inside = polygon_membership(flood, attrs, lon, lat)
    inside &= shapely.contains_xy(area,x,y)
    full = inside.reshape(48,5,48,5).all(axis=(1,3))
    ids = [f"EPSG:32646/{x0+100*c}/{y0+100*(r+1)}" for r,c in zip(*np.where(full))]
    sampled = sorted(ids,key=lambda i:hashlib.sha256(i.encode()).digest())[:120]
    locked = [Path(__file__).resolve(), ROOT/"vector/change_observations.py",
              ROOT/"vector/change_detection.py",ROOT/"analysis/change_history.py"]
    manifest.update(eligible=len(ids), cells=sampled, inputs={str(p.relative_to(ROOT)):digest(p) for p in locked},
                    reference_hashes={p.name:digest(p) for base in (ext,flood)
                                      for p in (base,base.with_suffix(".dbf"),base.with_suffix(".prj"))})
    with MANIFEST.open("x") as out:
        json.dump(manifest,out,indent=1)
    print(f"{len(ids)} fully labelled cells; {len(sampled)} sampled")


def run(cache):
    manifest=json.loads(MANIFEST.read_text())
    if any(digest(ROOT/p)!=h for p,h in manifest["inputs"].items()):
        raise ValueError("locked code changed")
    ids=set(manifest["cells"])
    layer=geometry(manifest)
    data=[]
    # Iterate one small spatial tile, retaining sensor measurements only for the registered cells.
    for tile in open_history(layer,manifest["history_start"],END,cache_dir=cache).tiles():
        if any(d["errors"] for d in tile["diagnostics"]):
            raise RuntimeError(str(tile["diagnostics"]))
        records = tile["observations"]
        meta = [{k:v for k,v in o.items() if k not in ("values","coverage")} for o in records]
        indices = [i for i,c in enumerate(tile["cells"]) if c["cell_id"] in ids]
        for i in indices:
            cell=tile["cells"][i]
            rows=_observations(meta,_tile_arrays(records,i,1),0,cell["support_id"])
            june=sorted({o["date"] for o in rows if o["date"]>=START and "mndwi" in o["values"]})
            entry={"id":cell["cell_id"],"first_usable_in_june":june[0] if june else None,
                   "first_usable_on_or_after_reference":next((d for d in june if d>=DATE),None)}
            for cutoff in (DATE,"2022-06-30"):
                d=detect_cell(cell["cell_id"],rows,start=START,end=END,as_of=cutoff)
                dates=[e["confirmed_on"] for e in d["events"]
                       if e["transition"]=="open_water_signal_gain" and e.get("confirmed_on")]
                entry[cutoff]={"confirmed":min(dates,default=None),
                               "complete_window":any(s["signal"]=="mndwi" and s["status"]=="observed" for s in d["series"])}
            data.append(entry)
    if Counter(r["id"] for r in data)!=Counter(manifest["cells"]):
        raise ValueError("incomplete sample")
    with RESULT.open("x") as f:
        json.dump({"manifest_sha256":digest(MANIFEST),"cells":data},f,indent=1)


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command",choices=["register","run"])
    ap.add_argument("directory",type=Path)
    args=ap.parse_args()
    if args.command=="register":
        prepare(args.directory)
    else:
        run(args.directory)
