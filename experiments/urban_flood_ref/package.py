"""Portable 10/30 m four-state products and flood-final's masked DEV reference."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from affine import Affine
import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import transform_bounds

UNOBSERVED, DRY, WET, AMBIGUOUS = range(4)
NODATA = -9999
EPOCH = date(1970, 1, 1)
BANDS = ("state", "confidence", "method", "baseline_state", "urban", "observed_fraction",
         "flooded_fraction", "pre_first_day", "pre_last_day", "post_day", "days_from_peak")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as src:
        for chunk in iter(lambda: src.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_grid(grid):
    h, w = grid["shape"]
    crs = CRS.from_user_input(grid["crs"])
    t = Affine(*grid["transform"][:6])
    if not (h == int(h) and w == int(w) and min(h, w) > 0 and crs.is_projected
            and crs.linear_units_factor[1] == 1 and (t.a, t.b, t.d, t.e) == (30, 0, 0, -30)):
        raise ValueError("Expected north-up, metric flood-model grid with 30 m square cells")
    return crs, t, (int(h), int(w))


def _blocks(x):
    h, w = x.shape
    if h % 3 or w % 3:
        raise ValueError("Expected an exact 3×3 nested grid")
    return x.reshape(h//3, 3, w//3, 3).transpose(0, 2, 1, 3).reshape(h//3, w//3, 9)


def coarse_state(state):
    cells = _blocks(state)
    wet = (cells == WET).sum(axis=-1)
    dry = (cells == DRY).sum(axis=-1)
    seen = (cells != UNOBSERVED).sum(axis=-1)
    result = np.where(seen, AMBIGUOUS, UNOBSERVED).astype(np.uint8)
    result[(seen == 9) & (wet >= 5) & (dry == 0)] = WET
    result[(seen == 9) & (dry >= 5) & (wet == 0)] = DRY
    return result


def _days(value):
    return (date.fromisoformat(value) - EPOCH).days


def products(grid30, result10, meta, reference_dates=None):
    """Aggregate aligned labels. Never resample state identifiers or confidence across classes."""
    _, _, shape = check_grid(grid30)
    fine = {k: np.asarray(result10[k]) for k in ("state", "confidence", "method", "baseline_state", "urban")}
    if any(v.shape != (3*shape[0], 3*shape[1]) for v in fine.values()):
        raise ValueError("10 m arrays must cover exactly 3× the model grid in each axis")
    state = fine["state"]
    if any(not np.isin(fine[k], (0, 1, 2, 3)).all() for k in ("state","baseline_state")):
        raise ValueError("Unknown reference state")
    seen = state != UNOBSERVED
    if not np.isin(fine["urban"], (0, 1)).all():
        raise ValueError("Urban context must be a complete Boolean mask")
    if not np.array_equal(seen, fine["baseline_state"] != UNOBSERVED):
        raise ValueError("Baseline and candidate require matched observation support")
    if not np.issubdtype(fine["method"].dtype, np.integer) or not ((fine["method"] >= 0) & (fine["method"] < 256)).all():
        raise ValueError("Expected an unsigned-byte method bitmask")
    labelled = (state == WET) | (state == DRY)
    conf = fine["confidence"]
    if np.any(labelled & (~np.isfinite(conf) | (conf < 0) | (conf > 1))):
        raise ValueError("Confident classes require finite evidence scores in [0,1]")
    fine["confidence"] = np.where(seen, np.where(labelled,conf,0), NODATA)
    fine["method"] = np.where(seen, fine["method"], 0).astype(np.uint8)
    fine["observed_fraction"] = seen.astype(np.float32)
    fine["flooded_fraction"] = (state == WET).astype(np.float32)
    fine["post_day"] = np.where(seen, _days(meta["post_date"]), NODATA)
    offset = _days(meta["post_date"]) - _days(meta["peak_date"]) if meta.get("peak_date") else NODATA
    fine["days_from_peak"] = np.where(seen, offset, NODATA)
    envelope = [_days(x) for x in meta["pre_dates"]]
    if not envelope or max(envelope) >= _days(meta["post_date"]):
        raise ValueError("Require at least one dated pre-event look, preceding the target look")
    if reference_dates is None:
        # A multi-look median has no unique acquisition day. Keep dates only
        # when there is exactly one possible baseline day at a pixel.
        start = end = np.full(state.shape, envelope[0] if len(set(envelope)) == 1 else NODATA)
    else:
        start, end = map(np.asarray, reference_dates)
        if start.shape != state.shape or end.shape != state.shape:
            raise ValueError("Per-pixel pre-date bands have an unexpected shape")
        valid_start = (start != NODATA) & np.isfinite(start)
        valid_end = (end != NODATA) & np.isfinite(end)
        if (seen & (valid_start != valid_end)).any():
            raise ValueError("Acquisition interval requires both endpoints")
        valid = seen & valid_start & valid_end
        if (start[valid] > end[valid]).any() or any(not np.isin(d[valid], envelope).all() for d in (start,end)):
            raise ValueError("Invalid acquisition day in pre-date bands")
    for name, value in (("pre_first_day",start), ("pre_last_day",end)):
        fine[name] = np.where(seen & np.isfinite(value), value, NODATA)

    coarse = {k:coarse_state(fine[k]) for k in ("state","baseline_state")}
    s = coarse["state"]
    matching = (_blocks(state) == s[...,None]) & np.isin(s[...,None], (WET, DRY))
    weight = matching.sum(axis=-1)
    coarse["confidence"] = np.where(s == UNOBSERVED, NODATA,
        np.where(matching, _blocks(fine["confidence"]), 0).sum(axis=-1) / np.maximum(weight,1))
    coarse["method"] = np.bitwise_or.reduce(np.where(
        matching | ((s == AMBIGUOUS)[...,None] & _blocks(seen)), _blocks(fine["method"]), 0),axis=-1)
    coarse["urban"] = _blocks(fine["urban"]).sum(axis=-1) >= 5
    for key in ("observed_fraction","flooded_fraction"):
        coarse[key] = _blocks(fine[key]).mean(axis=-1)
    for key in ("pre_first_day", "pre_last_day", "post_day", "days_from_peak"):
        cells = _blocks(fine[key])
        valid = _blocks(seen) & (cells != NODATA)
        # The scan dates describe the observation envelope. A partial record
        # cannot define its endpoints for the full observed group.
        complete = (_blocks(seen) == valid).all(axis=-1) & valid.any(axis=-1)
        first = key == "pre_first_day"
        vals = np.where(valid,cells,np.inf if first else -np.inf)
        coarse[key] = np.where(complete,(vals.min if first else vals.max)(axis=-1),NODATA)
    return fine, coarse


def _write_raster(path, layers, crs, transform):
    h,w = layers["state"].shape
    with rasterio.open(path,"w",driver="GTiff",crs=crs,transform=transform,width=w,height=h,
                       count=len(BANDS),dtype="float32",nodata=NODATA,compress="deflate",
                       tiled=True,blockxsize=128,blockysize=128) as dst:
        for i,key in enumerate(BANDS,1):
            dst.write(layers[key].astype("float32"),i)
            dst.set_band_description(i,key)
        dst.update_tags(state_legend="0 unobserved/excluded; 1 confident dry; 2 confident flooded; 3 ambiguous",
                        date_unit="days since 1970-01-01 UTC", confidence_type="heuristic evidence, uncalibrated")


def package_event(root, unit, grid30, result10, metadata, *, reference_dates=None):
    """Publish a new event. Caller must authorize its identity before any event I/O."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_\-]*", unit):
        raise ValueError("Provide a safe unique unit identifier")
    if metadata.get("role", "dev") != "dev":
        raise ValueError("Only development outputs may be written")
    crs,t,(h,w) = check_grid(grid30)
    date.fromisoformat(metadata["event"])
    canonical_grid = {"crs":crs.to_string(),"transform":list(t)[:6],"shape":[h,w]}
    root = Path(root)
    events, refs = root/"events", root/"refs"
    events.mkdir(parents=True,exist_ok=True)
    refs.mkdir(parents=True,exist_ok=True)
    dest, reference = events/unit, refs/(unit+".npz")
    if dest.exists() or reference.exists():
        raise FileExistsError(f"Event output already exists: {unit}. Verify its manifest before reuse.")
    fine, coarse = products(grid30,result10,metadata,reference_dates)
    obs = (coarse["state"] == DRY) | (coarse["state"] == WET)
    wet = coarse["state"] == WET
    bounds = rasterio.transform.array_bounds(h,w,t)
    meta = {**metadata,"unit":unit,"event":metadata["event"],"grid":canonical_grid,
            "block":1,"bbox":list(transform_bounds(crs,"EPSG:4326",*bounds)),
            "role":"dev","state_codes":{"unobserved":0,"confident_dry":1,"confident_flooded":2,"ambiguous":3}}
    with TemporaryDirectory(prefix="urban-ref-",dir=root) as scratch:
        tmp = Path(scratch)
        out = tmp/"event"
        out.mkdir()
        for resolution,layers,affine in ((10,fine,t*Affine.scale(1/3)),(30,coarse,t)):
            _write_raster(out/f"reference_{resolution}m.tif",layers,crs,affine)
        npz = out/"model_ref.npz"
        np.savez_compressed(npz,flooded=wet,valid=obs,meta=json.dumps(meta,allow_nan=False))
        report = {**meta, "bands":list(BANDS), "nodata":NODATA,
                  "sha256":{f"refs/{unit}.npz":sha(npz),**{f"events/{unit}/{f.name}":sha(f) for f in out.iterdir()}},
                  "confidence_type":"uncalibrated radar evidence score",
                  "confidence_summary":{str(scale):{
                      key:{"count":int((layers["state"] == value).sum()),
                           "mean":float(layers["confidence"][layers["state"] == value].mean())
                                  if (layers["state"] == value).any() else None}
                      for key,value in (("confident_dry",DRY),("confident_flooded",WET))}
                      for scale,layers in ((10,fine),(30,coarse))},
                  "counts30":{k:int((coarse["state"]==v).sum()) for k,v in meta["state_codes"].items()}}
        (out/"manifest.json").write_text(json.dumps(report,indent=2,allow_nan=False)+"\n")
        # Commit directory first; the stream consumed by the model appears only
        # after all ancillary products are on disk. The npz inside the event
        # directory supports recovery after an interrupted link creation.
        out.rename(dest)
        os.link(dest/npz.name,reference)
    return report


def recover_reference(root, unit):
    """Complete an interrupted publish after verifying all archived files."""
    root = Path(root)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_\-]*",unit):
        raise ValueError("Unsafe unit")
    event = root/"events"/unit
    manifest = json.loads((event/"manifest.json").read_text())
    reference = root/"refs"/(unit+".npz")
    source = event/"model_ref.npz"
    for filename in ("reference_10m.tif","reference_30m.tif","model_ref.npz"):
        if sha(event/filename) != manifest["sha256"][f"events/{unit}/{filename}"]:
            raise ValueError("Event file checksum mismatch")
    expected = manifest["sha256"][f"refs/{unit}.npz"]
    if sha(source) != expected or (reference.exists() and sha(reference) != expected):
        raise ValueError("Model label checksum mismatch")
    if not reference.exists():
        os.link(source,reference)
    return manifest
