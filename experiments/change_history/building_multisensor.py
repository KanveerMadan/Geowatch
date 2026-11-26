"""Frozen block-scale building-change experiment using SpaceNet 7 and Sentinel-1/2."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union

from analysis.change_history import _comparison, _tile_arrays
from experiments.change_history import building_endpoints as old
from experiments.change_history.spacenet_survey import _save, month_interval
from vector.change_observations import SOURCES, open_history

ROOT = Path(__file__).parent
MANIFEST = ROOT / "building_multisensor_sites.json"
RESULT = ROOT / "building_multisensor_result.json"
PROTOCOL = ROOT / "building_multisensor_protocol.md"
# Catalogue ranks refer to the original sorted list, but IDs (not rank) bind this study.
NEW_SITES = {
    "development": ["L15-1015E-1062N_4061_3941_13", "L15-1203E-1203N_4815_3378_13"],
    "test": ["L15-0457E-1135N_1831_3648_13", "L15-1049E-1370N_4196_2710_13",
             "L15-1185E-0935N_4742_4450_13", "L15-1538E-1163N_6154_3539_13"],
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_sites():
    if MANIFEST.exists():
        raise FileExistsError(MANIFEST)
    seen = json.loads(old.SPLITS.read_text())
    chosen = [(s["site"], "development", sorted(s["epochs"])) for s in seen]
    chosen += [(name, split, None) for split, sites in NEW_SITES.items() for name in sites]
    selected = []
    for site, split, previous in chosen:
        rows = defaultdict(dict)
        for obj in old._listing(old.PREFIX + site + "/").findall("{*}Contents"):
            key = obj.findtext("{*}Key")
            folder, filename = key.split("/")[-2:]
            if folder == "images_masked":
                kind = "image"
            elif folder == "labels" and filename.endswith("_UDM.geojson"):
                kind = "unusable"
            elif folder == "labels_match" and filename.endswith("_Buildings.geojson"):
                kind = "tracked"
            else:
                continue
            month = "_".join(filename.split("_")[2:4])
            rows[month][kind] = {"key": key, "bytes": int(obj.findtext("{*}Size")),
                                 "etag": obj.findtext("{*}ETag").strip('"')}
        pairs = []
        for month, assets in sorted(rows.items()):
            year, number = month.split("_")
            after = f"{int(year)+1}_{number}"
            if len(assets) == 3 and len(rows.get(after, {})) == 3:
                pairs.append([month, after])
        months = previous or pairs[-1]
        if months not in pairs:
            raise ValueError((site, months))
        selected.append(dict(site=site, split=split, centre=old._centre(site),
                             epochs={m: rows[m] for m in months}))
    with MANIFEST.open("x") as f:
        json.dump(selected, f, indent=2)
        f.write("\n")


def group_blocks(ids):
    """Aligned neighboring groups of four 100 m cells; trim incomplete border groups."""
    grouped = defaultdict(list)
    for i, cell in enumerate(ids):
        crs, x, top = str(cell).rsplit("/", 2)
        key = (crs, int(x)//200, (int(top)-100)//200)
        grouped[key].append(i)
    return {f"{crs}/{x*200}/{y*200}":idx for (crs,x,y),idx in sorted(grouped.items()) if len(idx)==4}


def save_arrays(path, **arrays):
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".npz", delete=False) as tmp:
        tmpname = Path(tmp.name)
        try:
            np.savez_compressed(tmp, **arrays)
        except BaseException:
            tmpname.unlink(missing_ok=True)
            raise
    tmpname.replace(path)


def inputs(root, site, sensor):
    name = site["site"]
    out = root / f"{name}-{sensor}.npz"
    meta = root / f"{name}-{sensor}-status.json"
    if out.exists() and meta.exists():
        return
    layer = old._layer(site["centre"])
    cells, _ = old._grid(layer)
    ids = [c["cell_id"] for c in cells]
    records, windows, evidence = [], [], []
    for m in sorted(site["epochs"]):
        first, last = month_interval(m)
        end = (date.fromisoformat(last)+timedelta(days=1)).isoformat()
        windows.append((first,end))
        tile, = open_history(layer, first, end, sources=[sensor], cache_dir=root/"observations").tiles()
        if [c["cell_id"] for c in tile["cells"]] != ids or any(d["errors"] for d in tile["diagnostics"]):
            raise RuntimeError(tile["diagnostics"])
        records.extend(tile["observations"])
        evidence.append({"interval": [first,end], "diagnostics": tile["diagnostics"],
                         "scenes": [[s["system:index"] for s in r["scenes"]] for r in tile["observations"]]})
    arrays = _tile_arrays(records, 0, len(ids))
    bands = []
    for signal in SOURCES[sensor]["signals"]:
        samples = arrays.get(signal)
        if samples is not None:
            # Freeze the same sampled support at both dates. A low cloud-free
            # fraction otherwise lets different parts of a block mimic change.
            samples = np.where(arrays["coverage"] >= 1, samples, np.nan)
        results = _comparison(records, samples, windows, len(ids))
        bands.append([[r["median_before"], r["median_after"], r["delta"]] if r["delta"] is not None
                      else [np.nan]*3 for r in results])
    _save(meta, evidence)
    save_arrays(out, ids=ids, x=np.hstack(bands))


def polygons(path, crs):
    data = json.loads(path.read_text())
    source = CRS.from_user_input(data["crs"]["properties"]["name"])
    project = Transformer.from_crs(source, crs, always_xy=True).transform
    footprints = {}
    for row in data["features"]:
        key = int(row["properties"]["Id"])
        geom = transform(project, shape(row["geometry"]))
        if key in footprints or not geom.is_valid or geom.is_empty:
            raise ValueError(f"ambiguous tracked footprint in {path.name}")
        footprints[key] = geom
    return footprints


def targets(root, site):
    from shapely import area, covers, intersection
    import rasterio
    from rasterio.enums import ColorInterp
    from rasterio.features import shapes
    from experiments.change_history.spacenet_survey import _read_polygons, _reproject
    out = root / f"{site['site']}-targets.npz"
    if out.exists():
        return
    layer = old._layer(site["centre"])
    cells, boxes = old._grid(layer)
    histories, areas = [], []
    for spec in site["epochs"].values():
        files = {k: old._asset(root, v) for k,v in spec.items()}
        with rasterio.open(files["image"]) as im:
            valid = im.read(im.colorinterp.index(ColorInterp.alpha)+1) > 0
            mask = unary_union([shape(g) for g,_ in shapes(valid.astype("uint8"),mask=valid,transform=im.transform)])
            visible = mask.difference(_read_polygons(files["unusable"], im.crs))
            areas.append(_reproject(visible, im.crs, layer.crs))
        histories.append(polygons(files["tracked"], layer.crs))
    before, after = histories
    joint = areas[0].intersection(areas[1])
    keep = covers(joint, boxes)
    # Only wholly observed objects are usable. Blocks containing a partially
    # covered candidate are unknown, even when all four subcells are surveyed.
    targets = []
    for new, other in ((after,before),(before,after)):
        different = [new[i] for i in new.keys()-other.keys()]
        ambiguous = unary_union([p for p in different if not joint.covers(p)])
        keep &= area(intersection(boxes, ambiguous)) == 0
        change = unary_union([p for p in different if joint.covers(p)])
        targets.append(area(intersection(boxes, change)))
    save_arrays(out, ids=[c["cell_id"] for c in cells], y=np.column_stack(targets), keep=keep)

MODES = {"optical": ("sentinel2",), "radar": ("sentinel1",), "combined": ("sentinel2", "sentinel1")}


def block_inputs(root, name, *, with_labels):
    sensors, ids = {}, None
    for source in ("sentinel2","sentinel1"):
        with np.load(root / f"{name}-{source}.npz", allow_pickle=False) as file:
            if ids is not None and not np.array_equal(ids, file["ids"]):
                raise ValueError("sensor grids differ")
            ids = file["ids"]
            sensors[source] = file["x"]
    blocks = group_blocks(ids)
    idx = np.array(list(blocks.values()), dtype=int)
    x = {mode: np.hstack([sensors[s][idx].mean(axis=1) for s in sources]) for mode,sources in MODES.items()}
    result = {"x":x,"ids":list(blocks)}
    if with_labels:
        with np.load(root/f"{name}-targets.npz",allow_pickle=False) as survey:
            if not np.array_equal(ids, survey["ids"]):
                raise ValueError("survey and sensor grids differ")
            result.update(y=survey["y"][idx].sum(axis=1), keep=survey["keep"][idx].all(axis=1))
    return result


def fit(rows):
    from sklearn.ensemble import HistGradientBoostingRegressor
    models, counts = {}, {}
    for mode in MODES:
        xs, ys = [], []
        for data in rows:
            ok = data["keep"] & np.isfinite(data["x"][mode]).all(axis=1)
            if ok.any():
                xs.append(data["x"][mode][ok])
                ys.append(data["y"][ok])
        if len(xs)<2:
            raise ValueError(f"fewer than two supported development sites for {mode}")
        x, y = np.vstack(xs),np.vstack(ys)
        pair = []
        for j in range(2):
            pair.append(HistGradientBoostingRegressor(max_iter=100, max_leaf_nodes=15, min_samples_leaf=20,
                        early_stopping=False, random_state=0).fit(x, y[:,j]))
        models[mode] = pair
        counts[mode] = {"sites":len(xs),"blocks":len(y),"gain_positive":int((y[:,0]>0).sum()),
                        "loss_positive":int((y[:,1]>0).sum())}
    return models, counts


def predict(models, row):
    result = {}
    for mode, regs in models.items():
        x = row["x"][mode]
        ok = np.isfinite(x).all(axis=1)
        out = np.full((len(x),2), np.nan)
        for j, reg in enumerate(regs):
            if ok.any():
                out[ok,j] = reg.predict(x[ok]).clip(0,40_000)
        result[mode] = out
    return result


def metrics(y, pred, ok):
    if not ok.any():
        return None
    e = pred[ok] - y[ok]
    summary = {"blocks":int(ok.sum())}
    for j, name in enumerate(("gain","loss")):
        positive = y[ok,j] > 0
        summary[name] = {
            "mapped_positive":int(positive.sum()),"mae_m2":float(np.abs(e[:,j]).mean()),
            "bias_m2":float(e[:,j].mean()),"reference_m2":float(y[ok,j].sum()),
            "changed_mae_m2":float(np.abs(e[positive,j]).mean()) if positive.any() else None,
            "unchanged_mae_m2":float(np.abs(e[~positive,j]).mean()) if (~positive).any() else None}
    return summary


def score(row, predictions):
    keep, y = row["keep"], row["y"]
    result = {"blocks":len(y),"joint_survey_blocks":int(keep.sum()),
              "mapped_added":int(((y[:,0]>0)&keep).sum()),"mapped_removed":int(((y[:,1]>0)&keep).sum()),
              "stable":int(((y==0).all(axis=1)&keep).sum()),"available":{},"common":{}}
    common = keep.copy()
    for mode, pred in predictions.items():
        ok = keep & np.isfinite(pred).all(axis=1)
        common &= ok
        result["available"][mode] = {"model":metrics(y,pred,ok), "zero":metrics(y,np.zeros_like(y),ok)}
    for mode,pred in {**predictions,"zero":np.zeros_like(y)}.items():
        result["common"][mode] = metrics(y,pred,common)
    return result


def verify_lock():
    lock = json.loads((ROOT / "building_multisensor_lock.json").read_text())
    for name, expected in lock.items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"frozen study file changed: {name}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["prepare","evaluate","predict"])
    p.add_argument("cache",type=Path)
    p.add_argument("--sensor",choices=("sentinel1","sentinel2","targets"))
    p.add_argument("--centre",type=float,nargs=2,metavar=("LONGITUDE","LATITUDE"))
    p.add_argument("--months",nargs=2,metavar=("BEFORE_YYYY_MM","AFTER_YYYY_MM"))
    p.add_argument("--output",type=Path)
    args = p.parse_args()
    root = args.cache
    root.mkdir(parents=True, exist_ok=True)
    verify_lock()
    sites = json.loads(MANIFEST.read_text())
    if args.action == "prepare":
        if not args.sensor:
            p.error("prepare requires --sensor")
        for site in sites:
            print(site["site"],args.sensor,flush=True)
            if args.sensor == "targets":
                targets(root,site)
            else:
                inputs(root,site,args.sensor)
        return
    from threadpoolctl import threadpool_limits
    with threadpool_limits(limits=1):
        dev = [block_inputs(root,s["site"],with_labels=True) for s in sites if s["split"]=="development"]
        models, counts = fit(dev)
        if not args.output or args.output.exists():
            p.error("select a new --output filename")
        if args.action == "predict":
            if not args.centre or not args.months or args.months[0]>=args.months[1]:
                p.error("predict requires --centre and two ordered --months")
            for month in args.months:
                month_interval(month)
            name = "predict-" + hashlib.sha256(json.dumps([args.centre,args.months]).encode()).hexdigest()[:20]
            site = dict(site=name,centre=args.centre,epochs=dict.fromkeys(args.months))
            for s in ("sentinel1","sentinel2"):
                inputs(root,site,s)
            row = block_inputs(root,name,with_labels=False)
            pred = predict(models,row)
            report = {"state":"experimental_unvalidated","centre":args.centre,"months":args.months,
                      "lock_sha256":digest(ROOT/"building_multisensor_lock.json"),
                      "units":"m2 estimated tracked building appearances and disappearances per 200 m block",
                      "blocks":[{"id":key,**{m:(a[i].tolist() if np.isfinite(a[i]).all() else None)
                                           for m,a in pred.items()}} for i,key in enumerate(row["ids"])]}
        else:
            by_site = {}
            for s in sites:
                if s["split"]=="test":
                    row = block_inputs(root,s["site"],with_labels=True)
                    by_site[s["site"]] = score(row,predict(models,row))
            aggregates = {}
            for mode in (*MODES, "zero"):
                rows = [site["common"][mode] for site in by_site.values() if site["common"][mode]]
                aggregates[mode] = {"sites":len(rows), "blocks":sum(r["blocks"] for r in rows),
                                    **{target:float(np.mean([r[target]["mae_m2"] for r in rows])) if rows else None
                                       for target in ("gain","loss")}}
            report = {"lock_sha256":digest(ROOT/"building_multisensor_lock.json"),
                      "training":counts,"sites":by_site,"equal_site_common_mae_m2":aggregates}
        with args.output.open("x") as f:
            json.dump(report,f,indent=2,allow_nan=False)
            f.write("\n")


if __name__ == "__main__":
    main()
