"""Export only the three explicitly approved DEV benchmark chips."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine

from .guard import authorize_window
from .optical_catalog import _save


def build(unit, root, existing):
    site = authorize_window(unit, "2021-07-27", "2021-07-27")
    if site["incident"] != "henan_jul_2021" or "UrbanSARFloods:Weihui_20210727" not in site["products"]:
        raise ValueError("Only the reviewed Weihui benchmark is supported")
    src = Path(existing) / (unit + ".npz")
    with np.load(src, allow_pickle=False) as data:
        meta = json.loads(str(data["meta"]))
        if meta["bbox"] != site["bbox"] or meta["event"] != site["date"] or meta["unit"] != unit:
            raise ValueError("Source label identity mismatch")
        grid = meta["grid"]
        valid = data["valid"]
        flooded = data["flooded"]
        openf = data["flooded_open"]
        urban = data["fu_share"] >= .5
        if valid.shape != tuple(grid["shape"]) or valid.dtype != np.bool_ or flooded.dtype != np.bool_:
            raise ValueError("Invalid source arrays")
        values = {"weihui_gt": np.where(valid, flooded.astype("uint8"), 255).astype("uint8"),
                  "weihui_fu": np.where(valid & urban & ~openf, 1, 255).astype("uint8"),
                  "weihui_fo": np.where(valid & openf, 1, 255).astype("uint8")}
    root = Path(root) / unit
    root.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, data in values.items():
        counts[name] = {str(v): int((data == v).sum()) for v in (0,1,255)}
        with rasterio.open(root/(name+".tif"), "w", driver="GTiff", crs=grid["crs"], transform=Affine(*grid["transform"]),
                           height=data.shape[0], width=data.shape[1], count=1, dtype="uint8", nodata=255, compress="deflate") as ds:
            ds.write(data,1)
    provenance = {
        "unit":unit,"date":site["date"],"grid":grid,"source":"UrbanSARFloods v1 — 20210727_Weihui_GT",
        "attribution":"Jie Zhao, Zhitong Xiong and Xiao Xiang Zhu, 2024",
        "source_url":"https://huggingface.co/datasets/S1Floodbenchmark/UrbanSARFloods_v1/tree/main",
        "method_url":"https://openaccess.thecvf.com/content/CVPR2024W/EarthVision/html/Zhao_UrbanSARFloods_Sentinel-1_SLC-Based_Benchmark_Dataset_for_Urban_and_Open-Area_Flood_CVPRW_2024_paper.html",
        "licence":"CC BY 4.0","licence_source":"https://github.com/aliecen/UrbanSARFloods_Dataset",
        "pixel_counts":counts, "input_sha256":hashlib.sha256(src.read_bytes()).hexdigest(),
        "interpretation":"UrbanSARFloods is an external shared-Sentinel-1 benchmark interpreted using intensity and coherence. Class 0 is reference non-flood. It is not surveyed dry ground.",
        "selection":"Three enriched Weihui windows selected in the upstream DEV experiment by flooded-urban pixel count; one storm.",
        "derivation":"Retained upstream exclusion of permanent water and area-majority 30 m labels. FO-only and FU-only evaluate positive recall; non-positive cells are unknown in those files."
    }
    _save(root/"weihui_reference.json", json.dumps(provenance, indent=2).encode())
    return counts


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("unit")
    p.add_argument("--existing", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args=p.parse_args()
    print(json.dumps(build(args.unit,args.output,args.existing)))
