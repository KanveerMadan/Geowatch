"""
Round 3 (R37): GFM labels on a unit grid (GFM_DESIGN.md §1) and the DEV acceptance gate (§2).

    python -m experiments.flood_round3.gfm_labels agree     -> results/gfm_agreement.json (DEV EMS units only)

GFM is read from the public EODC STAC catalogue (collection GFM; cloud-optimised GeoTIFFs, only the unit window).
The product is the first Sentinel-1 slice over the unit centre (Earth Engine metadata) that has a GFM item.

agree: the DIAGNOSIS §e units (EMS, 2015+, an EMS image, >= 50 EMS-flooded cells). For each unit, the first GFM product
on or after the EMS image date (<= 3 d) is mapped to the unit grid by the §1 rule and compared with the EMS label on
cells both observe. The numbers are the same as §e. No reserve unit is touched.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import sys
import time
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/gfm")
DRY, WET, UNOBS = 0, 1, 2


STAC = "https://stac.eodc.eu/api/v1/search"
ASSETS = ("ensemble_flood_extent", "exclusion_mask", "advisory_flags", "reference_water_mask")


def stac_items(bbox, d0, d1):
    import requests
    out, body = [], {"collections": ["GFM"], "bbox": list(bbox), "datetime": f"{d0}T00:00:00Z/{d1}T23:59:59Z", "limit": 200}
    url = STAC
    while url:
        r = requests.post(url, json=body, timeout=180)
        r.raise_for_status()
        j = r.json()
        out += j.get("features", [])
        nxt = [l for l in j.get("links", []) if l.get("rel") == "next"]
        url, body = (nxt[0]["href"], nxt[0].get("body", body)) if nxt else (None, None)
    return out


def s1_slice_times(ee, lon, lat, d0, d1):
    """Sentinel-1 IW GRD slices covering the point (Earth Engine collection metadata), as UTC datetimes."""
    col = ee.ImageCollection("COPERNICUS/S1_GRD").filter(ee.Filter.eq("instrumentMode", "IW")) \
        .filterBounds(ee.Geometry.Point(lon, lat)).filterDate(d0, (dt.date.fromisoformat(d1) + dt.timedelta(days=1)).isoformat())
    ts = col.aggregate_array("system:time_start").getInfo()
    return sorted(dt.datetime.utcfromtimestamp(t / 1000) for t in ts)


def choose_items(ee, grid, d0, d1):
    """GFM_DESIGN §1 product: the first Sentinel-1 slice over the unit centre in [d0, d1] (EE metadata) that has a GFM
    item (sensing time within 2 s); all GFM items of that pass (same orbit, within 3 min) are returned (tiles, slices)."""
    from affine import Affine
    from susceptibility.hydro_rasters import grid_lonlat_bounds
    w, s, e, n = grid_lonlat_bounds(Affine(*grid["transform"][:6]), tuple(grid["shape"]), grid["crs"])
    items = stac_items((w, s, e, n), d0, d1)
    if not items:
        return None, "no GFM item in window", []
    when = lambda f: dt.datetime.fromisoformat(f["properties"]["datetime"].replace("Z", ""))      # noqa: E731
    for t in s1_slice_times(ee, (w + e) / 2, (s + n) / 2, d0, d1):
        if any(abs((when(f) - t).total_seconds()) <= 2 for f in items):
            pas = [f for f in items if abs((when(f) - t).total_seconds()) <= 180]
            return t.isoformat(), None, pas
    return None, "no GFM item matches a Sentinel-1 slice over the unit centre", []


def label_from_items(items, grid):
    """GFM_DESIGN §1: codes per 20 m pixel, then mode to the unit grid. Returns (wet, dry) boolean arrays."""
    import rasterio
    from affine import Affine
    from rasterio.warp import Resampling, reproject, transform_bounds
    from rasterio.windows import from_bounds
    t = Affine(*grid["transform"][:6])
    H, W = grid["shape"]
    db = (t.c, t.f + t.e * H, t.c + t.a * W, t.f)
    out = np.full((H, W), UNOBS, np.uint8)
    for f in items:
        arrs, prof = {}, None
        for k in ASSETS:
            href = f["assets"].get(k, {}).get("href")
            if not href:
                arrs[k] = None
                continue
            with rasterio.open(href) as src:
                b = transform_bounds(grid["crs"], src.crs, *db, densify_pts=21)
                pad = 4 * src.res[0]
                win = from_bounds(b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad, src.transform).round_offsets().round_lengths()
                a = src.read(1, window=win, boundless=True, fill_value=255)
                tr = src.window_transform(win)
                if prof is None:
                    prof = (tr, src.crs, a.shape)
                    arrs[k] = a
                else:                       # reference water may be on another resolution: onto the flood grid
                    tmp = np.full(prof[2], 255, np.uint8)
                    reproject(a, tmp, src_transform=tr, src_crs=src.crs, dst_transform=prof[0], dst_crs=prof[1],
                              resampling=Resampling.nearest, src_nodata=255, dst_nodata=255)
                    arrs[k] = tmp
        fl = arrs["ensemble_flood_extent"]
        exl = arrs["exclusion_mask"] if arrs["exclusion_mask"] is not None else np.full(fl.shape, 255, np.uint8)
        adv = arrs["advisory_flags"] if arrs["advisory_flags"] is not None else np.full(fl.shape, 255, np.uint8)
        rw = arrs["reference_water_mask"] if arrs["reference_water_mask"] is not None else np.zeros(fl.shape, np.uint8)
        code = np.full(fl.shape, UNOBS, np.uint8)
        code[fl == 1] = WET
        code[(fl == 0) & (exl == 0) & (adv == 0) & ~np.isin(rw, (1, 2))] = DRY
        code[fl == 255] = 255
        dst = np.full((H, W), 255, np.uint8)
        reproject(code, dst, src_transform=prof[0], src_crs=prof[1], dst_transform=t, dst_crs=grid["crs"],
                  resampling=Resampling.mode, src_nodata=255, dst_nodata=255)
        take = (out == UNOBS) & (dst != 255)
        out[take] = dst[take]
    return out == WET, out == DRY


def agree():
    from experiments.flood_round3.diagnose_ee import _init
    cat = json.load(open(os.path.join(OUT, "burned_catalog.json")))
    s1 = json.load(open(os.path.join(OUT, "label_agreement.json")))
    ee = _init()
    os.makedirs(os.path.join(CACHE, "dev"), exist_ok=True)
    out = {}
    for n, row in sorted(cat.items()):
        if row.get("kind") != "ems" or not row.get("images") or not row.get("grid") or row["event"] < "2015-01-01":
            continue
        ems = np.load(os.path.expanduser(row["ref_path"]), allow_pickle=False)
        ef, ev = ems["flooded"].astype(bool), ems["valid"].astype(bool)
        if (ef & ev).sum() < 50:
            continue
        img = dt.date.fromisoformat(min(x[:10] for x in row["images"]))
        cp = os.path.join(CACHE, "dev", f"{n}.npz")
        if not os.path.exists(cp):
            try:
                info, why, items = choose_items(ee, row["grid"], img.isoformat(), (img + dt.timedelta(days=3)).isoformat())
                if info is None:
                    np.savez_compressed(cp, error=why)
                else:
                    wet, dry = label_from_items(items, row["grid"])
                    np.savez_compressed(cp, wet=wet, dry=dry, meta=json.dumps({"time": info, "items": [f["id"] for f in items]}))
            except Exception as e:      # noqa: BLE001
                out[n] = {"tags": row["tags"], "error": f"{type(e).__name__}: {str(e)[:150]}"}
                print(n, "ERROR", out[n]["error"], flush=True)
                continue
        z = np.load(cp, allow_pickle=False)
        if "error" in z.files:
            out[n] = {"tags": row["tags"], "sensors": row.get("sensors"), "error": str(z["error"])}
            print(n, out[n]["error"], flush=True)
            continue
        wet, dry, info = z["wet"], z["dry"], json.loads(str(z["meta"]))["time"]
        gv = (wet | dry).ravel()
        gw = wet.ravel()
        ef, ev = ef.ravel(), ev.ravel()
        both = ev & gv
        a, b = ef[both], gw[both]
        tp, fp, fn, tn = (a & b).sum(), (~a & b).sum(), (a & ~b).sum(), (~a & ~b).sum()
        N = max(1, a.size)
        po = (tp + tn) / N
        pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / N ** 2
        days = (dt.date.fromisoformat(info[:10]) - img).days
        out[n] = {"tags": row["tags"], "sensors": row.get("sensors"), "gfm_time": info, "gfm_minus_ems_days": days,
                  "cells_both": int(N), "ems_flooded": int(a.sum()), "gfm_flooded": int(b.sum()),
                  "coverage_of_ems_flood": round(float((ef & ev & gv).sum() / max(1, (ef & ev).sum())), 3),
                  "kappa": round(float((po - pe) / max(1e-9, 1 - pe)), 3),
                  "gfm_recall_of_ems": round(float(tp / max(1, tp + fn)), 3),
                  "gfm_precision_vs_ems": round(float(tp / max(1, tp + fp)), 3),
                  "auc_gfm_for_ems": round(float(0.5 * (tp / max(1, tp + fn) + tn / max(1, tn + fp))), 3),
                  "s1_kappa_same_unit": (s1.get(n) or {}).get("kappa")}
        print(n, days, out[n]["kappa"], out[n]["coverage_of_ems_flood"], flush=True)
        json.dump(out, open(os.path.join(OUT, "gfm_agreement.json"), "w"), indent=1)
    json.dump(out, open(os.path.join(OUT, "gfm_agreement.json"), "w"), indent=1)
    return 0


def gate():
    """GFM_DESIGN §2 verdict per type. Decision set (as coded before any result): every unit with >= 50 EMS-flooded
    cells and a GFM product <= 3 d after the EMS image; kappa on cells both observe (no GFM view of the flood -> kappa
    ~0, counted). The §e-style set (>= 50 EMS-flooded cells that GFM also observes) is shown alongside."""
    import collections
    from experiments.flood_round3 import labels_r3 as L
    a = json.load(open(os.path.join(OUT, "gfm_agreement.json")))
    rows = [v for v in a.values() if "kappa" in v and v["gfm_minus_ems_days"] <= 3]
    grp = collections.defaultdict(list)
    for v in rows:
        cls = "radar" if L.is_radar(v.get("sensors") or []) else "optical"
        for t in v["tags"]:
            grp[(t, cls)].append(v)
            grp[(t, "all")].append(v)
    med = lambda xs: round(float(np.median(xs)), 3) if xs else None          # noqa: E731
    res = {}
    for (t, cls), v in sorted(grp.items()):
        e_style = [x for x in v if x["ems_flooded"] >= 50]
        res[f"{t}|{cls}"] = {"units": len(v), "kappa_median": med([x["kappa"] for x in v]),
                             "coverage_median": med([x["coverage_of_ems_flood"] for x in v]),
                             "recall_median": med([x["gfm_recall_of_ems"] for x in v]),
                             "auc_median": med([x["auc_gfm_for_ems"] for x in v]),
                             "s1_kappa_median_same_units": med([x["s1_kappa_same_unit"] for x in v if x["s1_kappa_same_unit"] is not None]),
                             "e_style_units": len(e_style), "e_style_kappa_median": med([x["kappa"] for x in e_style])}
    verdict = {}
    for t in ("fluvial", "waterlogging"):
        r = res.get(f"{t}|all", {})
        ok = r.get("units", 0) >= 5 and r.get("kappa_median") is not None and r.get("s1_kappa_median_same_units") is not None \
            and r["kappa_median"] >= r["s1_kappa_median_same_units"]
        verdict[t] = {"accepted": bool(ok), "rule": "median kappa vs EMS (all sensors) >= our S1 label's on the same units, >= 5 units",
                      **{k: r.get(k) for k in ("units", "kappa_median", "s1_kappa_median_same_units")}}
    for t in ("pluvial", "flash_flood", "coastal", "compound"):
        r = res.get(f"{t}|optical", {})
        ok = r.get("units", 0) >= 5 and (r.get("kappa_median") or 0) >= 0.40
        verdict[t] = {"accepted": bool(ok), "rule": "median kappa vs optical/VHR EMS >= 0.40, >= 5 units",
                      **{k: r.get(k) for k in ("units", "kappa_median", "coverage_median")}}
    out = {"verdict": verdict, "groups": res, "used_units": len(rows),
           "no_product_or_error": sum(1 for v in a.values() if "kappa" not in v)}
    json.dump(out, open(os.path.join(OUT, "gfm_gate.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit({"agree": agree, "gate": gate}[sys.argv[1]]())
