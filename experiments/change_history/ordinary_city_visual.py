"""Build blinded independent Landsat image strips for water endpoint review."""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from experiments.change_history import ordinary_city as ordinary

ROWS = ordinary.HERE / "ordinary_city_predictions.jsonl.gz"
ROW_HASH = "c78259ad5705cf90ae1fb5e81cebc7485f726a663aa99595b1cd6a1f1c0b3775"
SEED = "ordinary-water-visual-1"


def blind_id(row):
    identifier = "|".join(row[k] for k in ("site", "cell", "start"))
    return sha256((SEED + identifier).encode()).hexdigest()[:12]


def sample():
    if sha256(ROWS.read_bytes()).hexdigest() != ROW_HASH:
        raise ValueError("ordinary predictions differ from the registered review sample")
    with gzip.open(ROWS, "rt") as stream:
        rows = [json.loads(line) for line in stream]
    positive = [r for r in rows if any(e[0].startswith("open_water_signal") for e in r["confirmed"])]
    controls = []
    selected = {blind_id(r) for r in positive}
    for pos in sorted(positive, key=blind_id):
        pool = [r for r in rows if r["site"] == pos["site"] and r["start"] == pos["start"]
                and blind_id(r) not in selected]
        control = min(pool, key=lambda r: sha256((blind_id(pos) + blind_id(r)).encode()).digest())
        controls.append(control)
        selected.add(blind_id(control))
    return sorted(positive + controls, key=blind_id)


def fetch_strip(ee, row):
    from ee_timeout import call
    code, west, north = row["cell"].split("/")
    # Center a 20x20 lattice of 30m sampling points on the reporting cell.
    x, y = int(west) + 50, int(north) - 50
    first, last = date.fromisoformat(row["start"]), date.fromisoformat(row["end"])
    begin = (first - timedelta(days=45)).isoformat()
    geom = ee.Geometry.Point([x, y], proj=code)
    images = []
    metadata = []
    for mission in ["LC08", "LC09"]:
        coll = ee.ImageCollection("LANDSAT/" + mission + "/C02/T1_L2")
        ids = call(coll.filterBounds(geom).filterDate(begin,last.isoformat()).aggregate_array("system:id").getInfo,
                   retries=1, label="Landsat visual inventory")
        for image_id in sorted(ids):
            im = ee.Image(image_id)
            qa = im.select("QA_PIXEL")
            ok = qa.bitwiseAnd(63).eq(0).And(im.select("QA_RADSAT").eq(0))
            bands = im.select(["SR_B2","SR_B3","SR_B4","SR_B5","SR_B6"]).multiply(.0000275).add(-.2)
            day = image_id.split("/")[-1].split("_")[-1]
            offset = (date(int(day[:4]),int(day[4:6]),int(day[6:8])) - first).days
            names = [f"x{len(images)}b{i}" for i in range(5)]
            images.append(bands.updateMask(ok).rename(names).unmask(-999, False).toFloat())
            metadata.append({"id": image_id, "offset": offset, "bands": names})
    if not images:
        return [], []
    grid = {"dimensions":{"width":20,"height":20},"crsCode":code,
            "affineTransform":{"scaleX":30,"scaleY":-30,"translateX":x-300,"translateY":y+300,
                               "shearX":0,"shearY":0}}
    data = call(lambda: ee.data.computePixels({"expression":ee.Image.cat(images),
                "fileFormat":"NUMPY_NDARRAY","grid":grid}), retries=1,label="Landsat visual swatches")
    usable = []
    for info in metadata:
        image = np.stack([data[k] for k in info["bands"]], axis=2)
        # Keep only views where every 30m sample center inside the 100m box is clear.
        if np.all(image[8:12,8:12,0] > -100):
            usable.append((info, image))
    return sorted(usable, key=lambda p:(p[0]["offset"],p[0]["id"])), metadata


def display(row, views, folder):
    scale = 5
    canvas = Image.new("RGB",(230, 35 + max(len(views),1)*122),"white")
    draw = ImageDraw.Draw(canvas)
    case = blind_id(row)
    draw.text((3,3),case + "   RGB / SWIR-NIR-red", fill="black")
    prior = [v[0]["id"] for v in views if v[0]["offset"] < 0]
    during = [v[0]["id"] for v in views if v[0]["offset"] >= 0]
    for n,(info,values) in enumerate(views):
        loc = 26 + n*122
        day = info["offset"]
        draw.text((3,loc),f"{day:+d} days from month start",fill="black")
        # Use fixed reflectance scaling across case, time, and Landsat platforms.
        for j,channels in enumerate(((2,1,0),(4,3,2))):
            vals = np.clip(values[:,:,channels] / .35, 0, 1)
            rgb = np.uint8(vals**.7*255)
            rgb[values[:,:,0] < -100] = [180,30,155]
            patch = Image.fromarray(rgb).resize((100,100),Image.Resampling.NEAREST)
            # four corner marks; the interior remains readable.
            pen = ImageDraw.Draw(patch)
            for u,v,dx,dy in [(42,42,1,1),(58,42,-1,1),(42,58,1,-1),(58,58,-1,-1)]:
                pen.line([(u,v+3*dy),(u,v),(u+3*dx,v)], fill="yellow")
            canvas.paste(patch,(3+111*j,loc+15))
    canvas.save(folder / (case + ".png"))
    return {"prior":prior, "during":during}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache",type=Path,required=True)
    p.add_argument("--env-file",type=Path)
    p.add_argument("--join",type=Path, help="scored blind case IDs and water verdicts")
    args = p.parse_args()
    cases = sample()
    folder = args.cache / "blind"
    folder.mkdir(parents=True,exist_ok=True)
    if args.join:
        labels = json.loads(args.join.read_text())
        if set(labels) != {blind_id(r) for r in cases}:
            raise ValueError("all blind cases required")
        output = []
        for r in cases:
            key = blind_id(r)
            meta = json.loads((args.cache/(key+".json")).read_text())
            verdict = labels[key]
            if verdict not in ("unknown","stable","gain","loss"):
                raise ValueError("invalid review")
            output.append({"site":r["site"], "cell":r["cell"], "start":r["start"], "blind_id":key,
                "reviewer":"Codex independent image interpretation", "target":"water", "verdict":verdict,
                "prediction_blind":True,"independent_of_sentinel2":True,
                "evidence_source":"USGS Landsat Collection 2 T1 L2 RGB and SWIR-NIR-red",
                "evidence_id":meta,"water_confirmations":[e for e in r["confirmed"] if e[0].startswith("open_water_signal")]})
        print(json.dumps(output,indent=2))
        return
    import ee
    from dotenv import load_dotenv
    if args.env_file:
        load_dotenv(args.env_file)
    ee.Initialize(project=os.environ["GEE_PROJECT_ID"])
    for r in cases:
        case = blind_id(r)
        if (args.cache/(case+".json")).exists() and (folder/(case+".png")).exists():
            continue
        views, _ = fetch_strip(ee,r)
        evidence = display(r,views,folder)
        ordinary.write_json(args.cache/(case+".json"),evidence)


if __name__ == "__main__":
    main()
