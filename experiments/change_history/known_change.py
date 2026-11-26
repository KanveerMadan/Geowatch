"""Locked, region-stratified 2021 Sentinel-2 known-change experiment using independent Landsat labels."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import tempfile

import numpy as np
from pyproj import Transformer

from vector import change_detection, change_observations

HERE = Path(__file__).resolve().parent
PROTOCOL = HERE / "known_change_protocol.json"
SIGNALS = ("ndvi", "mndwi", "ndbi")
LABELS = {1: "greenness_loss", 2: "open_water_signal_gain", 3: "open_water_signal_loss"}


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", delete=False) as tmp:
        json.dump(value, tmp, separators=(",", ":"), allow_nan=False)
        tmp.write("\n")
    os.replace(tmp.name, path)


def read(path):
    return json.loads(path.read_text())


def initialise(project):
    import ee
    ee.Initialize(project=project)
    ee.data.setDeadline(150_000)
    ee.data.setMaxRetries(2)
    return ee


def region_grid(region, spec):
    _, _, lon, lat = region
    crs = f"EPSG:{(32600 if lat >= 0 else 32700) + 1 + int((lon + 180) // 6)}"
    x, y = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform(lon, lat)
    half = spec["box_width_m"] // 2
    return crs, int(x // 100) * 100 - half, int(y // 100) * 100 + half


def water_epoch(ee, spec, year, months):
    series = ee.ImageCollection.fromImages([
        ee.Image(f"{spec['water_reference']}/{year}_{month:02d}").select("water").unmask(0)
        for month in months])
    water = series.map(lambda image: image.eq(2)).sum()
    dry = series.map(lambda image: image.eq(1)).sum()
    return (water.gte(2).And(dry.eq(0)).multiply(2)
            .add(dry.gte(2).And(water.eq(0)))).toByte()


def select_cells(classes, region_id, x0, y0, crs, spec):
    cells = []
    for code, transition in LABELS.items():
        yy, xx = np.where(classes == code)
        eligible = [(x0+int(c)*100, y0-(int(r)+1)*100) for r, c in zip(yy, xx)]
        def key(point):
            return sha256(f"{region_id}/{point[0]}/{point[1]}".encode()).digest()
        selected = []
        for point in sorted(eligible, key=key):
            if all(math.dist(point, previous) >= spec["minimum_separation_m"] for previous in selected):
                selected.append(point)
                if len(selected) == spec["cap_per_transition_per_region"]:
                    break
        cells.extend({"id": f"{crs}/{x}/{y}", "xy": [x,y], "expected": transition} for x,y in selected)
    return sorted(cells, key=lambda row: row["id"])


def reference(ee, spec, region):
    name, kind, _, _ = region
    crs, x0, y0 = region_grid(region, spec)
    if kind == "forest":
        classes = ee.Image(spec["forest_reference"]).select("lossyear").eq(21)
    else:
        last = water_epoch(ee, spec, 2020, (7,8,9))
        before = water_epoch(ee, spec, 2021, (3,4,5))
        after = water_epoch(ee, spec, 2021, (7,8,9))
        classes = (last.eq(before).multiply(before.eq(1).And(after.eq(2)).multiply(2)
                                          .add(before.eq(2).And(after.eq(1)).multiply(3))))
    # Full reference agreement on the same 25 sample centres used by production.
    fine = classes.unmask(0,False).reproject(crs, [20,0,0,0,-20,0])
    bounds = fine.reduceResolution(ee.Reducer.minMax(), maxPixels=100)
    image = bounds.select(0).multiply(bounds.select(0).eq(bounds.select(1))).rename("label").toByte()
    size = spec["box_width_m"] // 100
    grid = {"dimensions":{"width":size,"height":size},"crsCode":crs,"affineTransform":{
        "scaleX":100,"scaleY":-100,"shearX":0,"shearY":0,"translateX":x0,"translateY":y0}}
    arr = ee.data.computePixels({"expression":image,"grid":grid,"fileFormat":"NUMPY_NDARRAY"})["label"]
    return {"name":name, "kind":kind, "crs":crs,
            "eligible_counts":{v:int(np.count_nonzero(arr == k)) for k,v in LABELS.items()},
            "cells":select_cells(arr, name, x0,y0,crs,spec)}


def freeze(ee, spec, cache, workers):
    output = HERE / "known_change_manifest.json"
    if output.exists():
        raise ValueError("a frozen manifest already exists")
    def prepare(region):
        path = cache / "references" / (region[0]+".json")
        if not path.exists():
            save(path, {"protocol_sha256":digest(PROTOCOL),"data":reference(ee,spec,region)})
        value = read(path)
        if value["protocol_sha256"] != digest(PROTOCOL):
            raise ValueError("reference cache belongs to a different study")
        print(region[0], len(value["data"]["cells"]), flush=True)
        return value["data"]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(prepare, spec["regions"]))
    save(output, {"protocol_sha256":digest(PROTOCOL),"regions":rows})


def monitoring(kind):
    return ("2021-01-01", "2022-01-01") if kind == "forest" else ("2021-06-01", "2021-10-01")


def image_catalog(ee, region, start, end):
    x, y = zip(*(cell["xy"] for cell in region["cells"]))
    transformer = Transformer.from_crs(region["crs"], "EPSG:4326", always_xy=True)
    bounds = transformer.transform_bounds(min(x), min(y), max(x)+100, max(y)+100)
    return change_observations._groups("sentinel2", change_observations._catalog(
        ee, "sentinel2", bounds, start, end), start, end)


def acquire(ee, region, records):
    # Same normalised indices, valid-mask intersection, native-orbit daily mosaic,
    # fixed 20 m grid and complete support as _block_pixels. Extract many
    # disjoint full cells in one request instead of retrieving the whole box.
    crs = region["crs"]
    fine = {"crs":crs, "crsTransform":[20,0,0,0,-20,0]}
    coarse = ee.Projection(crs, [100,0,0,0,-100,0])
    features = ee.FeatureCollection([ee.Feature(ee.Geometry.Point(
        [c["xy"][0]+50,c["xy"][1]+50], proj=crs), {"cell":c["id"]}) for c in region["cells"]])
    images = []
    for i, r in enumerate(records):
        parts = []
        for scene in r["scenes"]:
            part = change_observations._scene(ee,"sentinel2",scene).reproject(**fine)
            parts.append(part.updateMask(part.mask().reduce(ee.Reducer.min())))
        mosaic = ee.ImageCollection.fromImages(parts).mosaic().reproject(**fine)
        complete = (mosaic.mask().reduce(ee.Reducer.min()).unmask(0,False)
                    .reproject(**fine).reduceResolution(ee.Reducer.min(),maxPixels=100))
        reduced = mosaic.reduceResolution(ee.Reducer.mean(),maxPixels=100)
        names = [f"r{i}_{signal}" for signal in SIGNALS]
        images.append(reduced.updateMask(complete).unmask(-9999,False).toFloat().rename(names))
    # sampleRegions receives explicit UTM point centres; masked measurements
    # survive transport as a sentinel, which never enters model training.
    sampled = ee.Image.cat(images).sampleRegions(collection=features, properties=["cell"],
                                                projection=coarse, geometries=False)
    rows = sampled.getInfo()["features"]
    response = {c["id"]:[] for c in region["cells"]}
    seen = set()
    for f in rows:
        r = f["properties"]
        seen.add(r["cell"])
        for i, meta in enumerate(records):
            vals = [r[f"r{i}_{s}"] for s in SIGNALS]
            if all(v != -9999 and math.isfinite(v) for v in vals):
                response[r["cell"]].append([meta["date"],meta["track"],*vals])
    if seen != set(response) or len(rows) != len(response):
        raise RuntimeError("incomplete sample response for fixed cells")
    return response


def score(cell, rows, kind):
    start, end = monitoring(kind)
    series = [{"date":r[0], "track":r[1], "source":"sentinel2", "support_id":cell["id"],
               "values":dict(zip(SIGNALS,r[2:],strict=True))} for r in rows]
    result = change_detection.detect_cell(cell["id"],series,start=start,end=end)
    expected = cell["expected"]
    target = "ndvi" if expected == "greenness_loss" else "mndwi"
    observed = [s for s in result["series"] if s["signal"] == target]
    matched = [e for e in result["events"] if e["transition"] == expected]
    confirmations = sorted(e["confirmed_on"] for e in matched if e.get("confirmed_on"))
    # Coarse product dates bound the date of a single sustained transition only.
    # A match inside the interval can be incidental; a negative lag is allowed.
    boundary = ("2021-01-01","2021-12-31") if kind == "forest" else ("2021-04-01","2021-08-31")
    first = confirmations[0] if confirmations else None
    return {"id":cell["id"], "expected":expected, "confirmed":bool(first),
            "first_confirmation":first, "target_candidates_or_episodes":len(matched),
            "fully_observed":any(s["status"]=="observed" for s in observed),
            "partially_or_fully_observed":any(s["status"] in ("observed","partial_observation") for s in observed),
            "history_dates":len({r[0] for r in rows if r[0]<start}),
            "monitor_dates":len({r[0] for r in rows if start<=r[0]<end}),
            "first_usable_in_monitor":min((r[0] for r in rows if start<=r[0]<end),default=None),
            "confirmation_minus_reference_interval_days":[(date.fromisoformat(first)-date.fromisoformat(d)).days
                for d in reversed(boundary)] if first else None}


def run(ee,spec,cache,workers):
    manifest_path = HERE / "known_change_manifest.json"
    lock = read(HERE / "known_change_lock.json")
    if lock != {"protocol":digest(PROTOCOL), "manifest":digest(manifest_path), "implementation":digest(__file__)}:
        raise ValueError("study lock mismatch")
    manifest = read(manifest_path)
    if manifest["protocol_sha256"] != lock["protocol"]:
        raise ValueError("protocol mismatch")
    root = cache / lock["manifest"] / lock["implementation"]
    jobs = []
    regions = manifest["regions"]
    for region in regions:
        if not region["cells"]:
            continue
        _, end = monitoring(region["kind"])
        path = root / region["name"] / "catalog.json"
        if not path.exists():
            save(path,image_catalog(ee,region,spec["history_start"],end))
        records = read(path)
        for i in range(0,len(records),48):
            jobs.append((region,records[i:i+48],path.parent/f"block-{i:04}.json"))
    def fetch(job):
        region,records,path = job
        if not path.exists():
            save(path,acquire(ee,region,records))
        print(region["name"], path.stem, flush=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(fetch,jobs))
    results = []
    for region in regions:
        by_id = {c["id"]:[] for c in region["cells"]}
        for reg,_,path in jobs:
            if reg["name"] == region["name"]:
                for key,values in read(path).items():
                    by_id[key].extend(values)
        results.append({"name":region["name"], "cells":[score(c,by_id[c["id"]],region["kind"])
                                                       for c in region["cells"]]})
    save(HERE/"known_change_results.json", {"lock":lock,"regions":results})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["freeze","run"])
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--workers", type=int, choices=[1,2,3], default=2)
    parser.add_argument("--project", default=os.getenv("GEE_PROJECT_ID"))
    args = parser.parse_args()
    spec = read(PROTOCOL)
    if (digest(change_detection.__file__) != spec["detector_sha256"] or
            digest(change_observations.__file__) != spec["observations_sha256"]):
        raise ValueError("frozen production code has changed")
    ee = initialise(args.project)
    if args.stage == "freeze":
        freeze(ee,spec,args.cache,args.workers)
    else:
        run(ee,spec,args.cache,args.workers)


if __name__ == "__main__":
    main()
