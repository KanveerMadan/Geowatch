"""Run the registered SpaceNet 7 building-area endpoint benchmark in bounded stages."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, timedelta
from hashlib import md5
import json
import math
from pathlib import Path
import shutil
import tempfile
import time
from types import SimpleNamespace
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import numpy as np
from pyproj import CRS, Geod
import rasterio
from rasterio.enums import ColorInterp
from shapely.geometry import box, shape
from shapely.ops import unary_union

from analysis.change_history import _comparison, _tile_arrays
from experiments.change_history.spacenet_survey import MIB, _reproject, _save, epoch_features, month_interval
from vector.change_observations import _spatial_tiles, open_history

HERE = Path(__file__).parent
BUCKET = "https://spacenet-dataset.s3.amazonaws.com/"
PREFIX = "spacenet/SN7_buildings/train/"
SPLITS = HERE / "building_endpoint_sites.json"
INDEX = ("ndvi", "mndwi", "ndbi")


def _listing(prefix, *, delimiter=None):
    params = {"list-type": 2, "prefix": prefix, "max-keys": 300}
    if delimiter:
        params["delimiter"] = delimiter
    url = BUCKET + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as r:
        data = r.read(256 * 1024)
    result = ET.fromstring(data)
    if result.findtext("{*}IsTruncated") == "true":
        raise ValueError("source catalogue exceeds registered listing size")
    return result


def _assets(site):
    rows = {}
    for obj in _listing(PREFIX + site + "/").findall("{*}Contents"):
        key = obj.findtext("{*}Key")
        folder, fname = key.split("/")[-2:]
        if folder == "images_masked":
            kind = "image"
        elif folder == "labels" and fname.endswith("_UDM.geojson"):
            kind = "unusable"
        elif folder == "labels" and fname.endswith("_Buildings.geojson"):
            kind = "buildings"
        else:
            continue
        month = "_".join(fname.split("_")[2:4])
        rows.setdefault(month, {})[kind] = {
            "key": key, "bytes": int(obj.findtext("{*}Size")), "etag": obj.findtext("{*}ETag").strip('"')}
    return rows


def _centre(site):
    x, y, z = [int(v) for v in site.split("_")[-3:]]
    n = 2**z
    return (x + .5) / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1-2*(y+.5)/n))))


def select():
    listing = _listing(PREFIX, delimiter="/")
    sites = sorted(x.findtext("{*}Prefix").strip("/").split("/")[-1] for x in listing.findall("{*}CommonPrefixes"))
    chosen = []
    geod = Geod(ellps="WGS84")
    for split, rank in [("development",0),("development",20),("development",40),("heldout",10),("heldout",50)]:
        for i in range(len(sites)):
            site = sites[(rank+i) % len(sites)]
            centre = _centre(site)
            if any(geod.inv(*centre, *other["centre"])[2] < 300_000 for other in chosen):
                continue
            assets = _assets(site)
            pairs = []
            for month, files in sorted(assets.items()):
                year, mon = month.split("_")
                other = f"{int(year)+1}_{mon}"
                if len(files) == 3 and len(assets.get(other, {})) == 3:
                    pairs.append((month, other))
            if not pairs:
                continue
            pair = pairs[0] if split == "development" else pairs[-1]
            epochs = {m: assets[m] for m in pair}
            if sum(f["bytes"] for fs in epochs.values() for f in fs.values()) > 12 * MIB:
                continue
            chosen.append(dict(split=split, site=site, rank=sites.index(site), centre=centre, epochs=epochs))
            break
        else:
            raise RuntimeError(f"no eligible site for {split} rank {rank}")
    with SPLITS.open("x") as f:
        json.dump(chosen, f, indent=2)
        f.write("\n")


def _asset(root, meta):
    path = root / "raw" / Path(meta["key"]).parent.name / Path(meta["key"]).name
    path.parent.mkdir(parents=True, exist_ok=True)
    def valid(p):
        return (p.is_file() and p.stat().st_size == meta["bytes"]
                and md5(p.read_bytes()).hexdigest() == meta["etag"])
    if valid(path):
        return path
    if len(meta["etag"]) != 32:
        raise ValueError("non-MD5 source ETag requires an independent digest")
    if shutil.disk_usage(root).free < 15 * 1024**3:
        raise RuntimeError("less than 15 GiB free")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        partial = Path(tmp.name)
    try:
        until = time.monotonic() + 60
        with urllib.request.urlopen(BUCKET + meta["key"], timeout=20) as src, partial.open("wb") as f:
            while chunk := src.read(128 * 1024):
                if time.monotonic() > until or f.tell()+len(chunk) > meta["bytes"]:
                    raise RuntimeError("bounded SpaceNet transfer exceeded budget")
                f.write(chunk)
        if not valid(partial):
            raise ValueError("SpaceNet source differs from frozen catalogue")
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
    return path


def _layer(centre):
    lon, lat = centre
    code = (32600 if lat >= 0 else 32700) + int((lon+180)//6) + 1
    crs = CRS.from_epsg(code)
    from shapely.geometry import Point
    mid = _reproject(Point(lon, lat), "EPSG:4326", crs)
    x, y = math.floor(mid.x / 100)*100, math.floor(mid.y / 100)*100
    area = box(x-1000, y-1000, x+1000, y+1000)
    return SimpleNamespace(aoi=area, crs=crs, bbox=_reproject(area, crs, "EPSG:4326").bounds)


def _survey(files, crs):
    fc, _ = epoch_features(files)
    if fc is None:
        return box(0,0,0,0), box(0,0,0,0)
    grouped = defaultdict(list)
    for f in fc["features"]:
        grouped[f["properties"]["role"]].append(shape(f["geometry"]))
    return tuple(_reproject(unary_union(grouped[k]), "EPSG:4326", crs) for k in ("coverage","surface"))


def _grid(layer):
    tile, = _spatial_tiles(layer)
    # The stable UTM keys encode the exact integer top-left corner.
    boxes = []
    for cell in tile["cells"]:
        _, x, y = cell["cell_id"].rsplit("/", 2)
        x, y = int(x), int(y)
        boxes.append(box(x,y-100,x+100,y))
    return tile["cells"], np.array(boxes, dtype=object)


def labels(root, site):
    from shapely import area, covers, intersection
    layer = _layer(site["centre"])
    cells, boxes = _grid(layer)
    surveys = []
    for _, spec in sorted(site["epochs"].items()):
        files = {k:_asset(root, v) for k,v in spec.items()}
        surveys.append(_survey(files, layer.crs))
    (ca, fa), (cb, fb) = surveys
    joint = ca.intersection(cb)
    keep = covers(joint, boxes)
    gain = area(intersection(boxes, fb.difference(fa)))
    loss = area(intersection(boxes, fa.difference(fb)))
    out = root / (site["site"]+"-survey.npz")
    np.savez(out, ids=[c["cell_id"] for c in cells], y=np.column_stack([gain,loss]), keep=keep)


def s2(root, site):
    layer = _layer(site["centre"])
    records, windows, info = [], [], []
    until = time.monotonic() + 170
    for m in sorted(site["epochs"]):
        first, last = month_interval(m)
        end = (date.fromisoformat(last)+timedelta(days=1)).isoformat()
        windows.append((first,end))
        tiles = list(open_history(layer, first, end, sources=["sentinel2"], cache_dir=root/"s2",
                                  cancelled=lambda: time.monotonic() >= until).tiles())
        tile, = tiles
        info.append(tile["diagnostics"])
        if any(r["errors"] for r in tile["diagnostics"]):
            raise RuntimeError(str(tile["diagnostics"])[:500])
        records.extend(tile["observations"])
    cells, _ = _grid(layer)
    ids = [c["cell_id"] for c in cells]
    if ids != [c["cell_id"] for c in tile["cells"]]:
        raise ValueError("S2 grid differs from survey support")
    arr = _tile_arrays(records, 0, len(cells))
    bands = []
    for signal in INDEX:
        results = _comparison(records, arr.get(signal), windows, len(cells))
        bands.append([[r.get("median_before", np.nan),r.get("median_after", np.nan),r.get("delta", np.nan)]
                      if r["delta"] is not None else [np.nan]*3 for r in results])
    np.savez(root/(site["site"]+"-s2.npz"), ids=ids, x=np.hstack(bands))
    _save(root/(site["site"]+"-s2-status.json"),info)


def planet(root, site):
    from rasterio.features import rasterize
    layer = _layer(site["centre"])
    cells, boxes = _grid(layer)
    epochs = []
    for _, spec in sorted(site["epochs"].items()):
        path = _asset(root, spec["image"])
        with rasterio.open(path) as im:
            ix = rasterize([(_reproject(g,layer.crs,im.crs),i+1) for i,g in enumerate(boxes)],
                           out_shape=im.shape,transform=im.transform)
            clear = im.read(im.colorinterp.index(ColorInterp.alpha)+1) > 0
            counts = np.bincount(ix[clear],minlength=len(boxes)+1)[1:]
            sums = [np.bincount(ix[clear],weights=im.read(im.colorinterp.index(c)+1)[clear],
                                minlength=len(boxes)+1)[1:] for c in (ColorInterp.red,ColorInterp.green,ColorInterp.blue)]
            epochs.append(np.divide(np.array(sums).T, counts[:,None],out=np.full((len(boxes),3),np.nan),
                                    where=counts[:,None]>0))
    a,b = epochs
    np.savez(root/(site["site"]+"-planet.npz"), ids=[c["cell_id"] for c in cells], x=np.hstack([a,b,b-a]))


def evaluate(root, sites, sensor):
    from sklearn.ensemble import HistGradientBoostingRegressor
    from threadpoolctl import threadpool_limits
    supported = {}
    counts = {}
    for site in sites:
        name = site["site"]
        with np.load(root/(name+"-survey.npz"), allow_pickle=False) as survey:
            counts[name] = {"grid": len(survey["ids"]), "survey": int(survey["keep"].sum()), "joint":0}
            path = root/(name+"-"+sensor+".npz")
            if not path.exists():
                continue
            with np.load(path,allow_pickle=False) as data:
                if not np.array_equal(data["ids"],survey["ids"]):
                    raise ValueError("reference and source grids differ")
                ok = np.all(np.isfinite(data["x"]),axis=1) & survey["keep"]
                counts[name]["joint"] = int(ok.sum())
                if ok.any():
                    supported[name] = (data["x"][ok],survey["y"][ok])
    dev = [s["site"] for s in sites if s["split"] == "development" and s["site"] in supported]
    hold = [s["site"] for s in sites if s["split"] == "heldout" and s["site"] in supported]
    report = {"sensor":sensor, "coverage":counts, "development_sites":dev, "holdout_sites":hold}
    if len(dev)<2 or not hold:
        return {**report,"status":"insufficient_geographic_support"}
    X,Y = [np.vstack([supported[n][idx] for n in dev]) for idx in (0,1)]
    rows = {}
    with threadpool_limits(limits=1):
        for i,target in enumerate(("gain","loss")):
            reg = HistGradientBoostingRegressor(max_iter=100,max_leaf_nodes=15,min_samples_leaf=20,
                                                early_stopping=False,random_state=0).fit(X,Y[:,i])
            for n in hold:
                x,y = supported[n]
                true = y[:,i]
                result = {"mean_target":float(true.mean())}
                for model,pred in (("boost",reg.predict(x).clip(0,10000)),("zero",0.0),("median",np.median(Y[:,i]))):
                    error = pred - true
                    result[model] = {"mae":float(np.mean(abs(error))), "rmse":float(np.sqrt(np.mean(error**2))),
                                     "bias":float(np.mean(error))}
                rows.setdefault(n,{})[target] = result
    return {**report,"status":"evaluated","by_site":rows,
            "equal_site_mae":{t:{m:float(np.mean([rows[n][t][m]["mae"] for n in hold]))
                                 for m in ("boost","zero","median")} for t in ("gain","loss")}}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action",choices=["select","labels","s2","evaluate"])
    ap.add_argument("cache",type=Path)
    args = ap.parse_args()
    root = args.cache
    root.mkdir(parents=True,exist_ok=True)
    if args.action == "select":
        select()
        return
    sites = json.loads(SPLITS.read_text())
    if args.action == "evaluate":
        first = evaluate(root, sites, "s2")
        reports = [first]
        if first["status"] != "evaluated":
            for site in sites:
                planet(root,site)
            reports.append(evaluate(root, sites, "planet"))
        _save(root/"building_endpoint_result.json",reports)
        print(json.dumps(reports,indent=2))
        return
    for site in sites:
        if args.action == "labels":
            labels(root,site)
        else:
            try:
                s2(root,site)
            except Exception as exc:
                _save(root/(site["site"]+"-s2-status.json"), {"error":str(exc)})
                print(site["site"],str(exc)[:250],flush=True)


if __name__ == "__main__":
    main()
