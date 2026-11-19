"""
Phase 4 urban-reference diagnostic on Weihui, China (27 Jul 2021), with the
UrbanSARFloods coherence-based labels (DECISIONS.md D10, D11). DEV only.

    python -m experiments.flood_final.urban.weihui boxes     # choose boxes, write label refs
    python -m experiments.flood_final.urban.weihui build     # inputs + tables (EE)
    python -m experiments.flood_final.urban.weihui s1        # round-4 S1 VV-drop reference on the boxes
    python -m experiments.flood_final.urban.weihui score     # the D11 comparison

Box rule (fixed before any label is read at 30 m): the 3 non-overlapping
4 km windows (BOX_SIDE_M, round 4's box side) with the most flooded-urban
(FU) pixels, searched on the label raster aggregated to 600 m (1/20 of 4 km;
coarse search only, the boxes themselves are exact 4 km UTM squares).
Labels per 30 m cell (UrbanSARFloods classes 0 NF, 1 FO, 2 FU; ~18 m):
  fo_share, fu_share = shares of the cell's label pixels (>= half a cell = COVER_MIN, as references)
  flooded_open  = fo_share >= 0.5          (the open-area flood only)
  flooded_all   = fo_share + fu_share >= 0.5
Valid = inside the scene and not JRC permanent water. Unobserved = never dry.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
SRC = os.path.expanduser("~/.cache/geowatch/flood_final/urbansarfloods/weihui/20210727_Weihui_GT.tif")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_final/urban")
EVENT = "2021-07-27"
N_BOXES = 3
FO, FU = 1, 2


def guard(points):
    """Read-only registry check: no Weihui box may link to a reserved unit."""
    from experiments.flood_core.registry import registry as REG
    reg = REG.load()
    for name, bbox in points.items():
        u = {"event_id": name, "role": "dev", "products": ["UrbanSARFloods:Weihui_20210727"],
             "storm_cluster": "henan_jul_2021", "geometry": {"type": "boxes", "boxes": [{"bbox": bbox}]}}
        c = REG.conflicts(reg, u, "reserved")
        if c:
            raise SystemExit(f"{name}: linked to reserved units {c}")


def choose_boxes():
    import rasterio
    from experiments.flood_validation import references as R
    from experiments.flood_validation.harness_round4 import BOX_SIDE_M
    with rasterio.open(SRC) as ds:
        f = 20
        a = ds.read(1, out_shape=(ds.height // f, ds.width // f),
                    resampling=rasterio.enums.Resampling.nearest)
        t = ds.transform * ds.transform.scale(ds.width / a.shape[1], ds.height / a.shape[0])
    lat0 = (ds.bounds.top + ds.bounds.bottom) / 2
    deg = BOX_SIDE_M / (111320.0 * np.cos(np.radians(lat0)))       # box side in degrees lon
    k = max(1, int(round(deg / abs(t.a))))
    fu = (a == FU).astype(float)
    from scipy.ndimage import uniform_filter
    score = uniform_filter(fu, k, mode="constant") * k * k
    boxes = {}
    taken = np.zeros_like(score, bool)
    for i in range(N_BOXES):
        s = np.where(taken, -1, score)
        r, c = np.unravel_index(np.argmax(s), s.shape)
        lon, lat = t * (c + 0.5, r + 0.5)
        boxes[f"usf_weihui_{i + 1}"] = {"bbox": list(R.square_bbox(lat, lon, BOX_SIDE_M)),
                                        "fu_pixels_coarse": int(score[r, c])}
        taken[max(0, r - k):r + k + 1, max(0, c - k):c + k + 1] = True
    guard({n: b["bbox"] for n, b in boxes.items()})
    return boxes


def labels_on_grid(bbox):
    import rasterio
    from rasterio.warp import Resampling, reproject
    from susceptibility.hydro_rasters import utm_grid
    t, shape, crs = utm_grid(bbox)
    out = {}
    with rasterio.open(SRC) as ds:
        win = rasterio.windows.from_bounds(bbox[0] - 0.01, bbox[1] - 0.01, bbox[2] + 0.01,
                                           bbox[3] + 0.01, ds.transform).round_offsets().round_lengths()
        a = ds.read(1, window=win)
        wt = ds.window_transform(win)
    for name, cls in (("fo_share", FO), ("fu_share", FU), ("obs", None)):
        src = (a >= 0).astype(np.float32) if cls is None else (a == cls).astype(np.float32)
        dst = np.full(shape, np.nan, np.float32)
        reproject(src, dst, src_transform=wt, src_crs="EPSG:4326", dst_transform=t, dst_crs=crs,
                  resampling=Resampling.average, src_nodata=None, dst_nodata=np.nan)
        out[name] = dst
    return t, shape, crs, out


def write_refs(boxes):
    from experiments.flood_validation import references as R
    import ee
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    os.makedirs(CACHE, exist_ok=True)
    rows = {}
    for n, b in boxes.items():
        t, shape, crs, L = labels_on_grid(b["bbox"])
        occ = R.jrc_occurrence(t, shape, crs)
        valid = np.isfinite(L["obs"]) & (L["obs"] >= R.COVER_MIN) & R.not_permanent(occ)
        f_all = (np.nan_to_num(L["fo_share"]) + np.nan_to_num(L["fu_share"])) >= R.COVER_MIN
        f_open = np.nan_to_num(L["fo_share"]) >= R.COVER_MIN
        meta = {"unit": n, "event": EVENT, "bbox": b["bbox"], "block": 1,
                "grid": {"crs": crs, "transform": list(t)[:6], "shape": list(shape)},
                "reference": {"source": "UrbanSARFloods v1 (Zhao et al. 2024) Weihui 20210727 GT, "
                                        "FO + FU (coherence + intensity labels), CC BY 4.0"}}
        np.savez_compressed(os.path.join(CACHE, f"{n}.npz"), flooded=f_all, valid=valid,
                            flooded_open=f_open, fu_share=np.nan_to_num(L["fu_share"]),
                            meta=np.array(json.dumps(meta)))
        rows[n] = {**b, "flooded_all": int((f_all & valid).sum()),
                   "flooded_open": int((f_open & valid).sum()),
                   "fu_cells": int(((np.nan_to_num(L["fu_share"]) >= 0.5) & valid).sum()),
                   "dry_all": int((~f_all & valid).sum())}
        print(n, rows[n], flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump(rows, open(os.path.join(OUT, "weihui_boxes.json"), "w"), indent=1)


def entry(n):
    p = os.path.join(CACHE, f"{n}.npz")
    meta = json.loads(str(np.load(p)["meta"]))
    return {"unit": n, "path": p, "meta": meta, "round": "flood_final_urban", "split": "dev",
            "modules": [], "uses": []}


def build(names):
    from experiments.flood_baselines import build as BUILD
    from experiments.flood_baselines import score as BSCORE
    from experiments.flood_learned import features as FT
    from experiments.flood_learned import fetch as F
    import ee
    from experiments.flood_validation import references as R
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    ee.data.setDeadline(R.EE_TIMEOUT_S * 1000)
    for n in names:
        e = entry(n)
        if not os.path.exists(BUILD.path(n)):
            BUILD.save(n, BUILD.build_unit(e))
        if not os.path.exists(F.path(n)):
            F.save(n, *F.fetch_unit(e))
        FT.save(n, FT.build_table(e, BSCORE.round4_chosen()))
        print("built", n, flush=True)


def s1_reference(names):
    """The round-4 S1 VV-drop reference on each box (the method behind the S1 DEV and RESERVED references)."""
    from experiments.flood_validation import references as R
    from experiments.flood_validation.harness_round4 import S1_SEARCH_SIDE_M
    from susceptibility.hydro_rasters import utm_grid
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    out = {}
    for n in names:
        e = entry(n)
        bbox = e["meta"]["bbox"]
        lat, lon = (bbox[1] + bbox[3]) / 2, (bbox[0] + bbox[2]) / 2
        pas = R.s1_event_pass(R.square_bbox(lat, lon, S1_SEARCH_SIDE_M), EVENT)
        t, shape, crs = utm_grid(bbox)
        ref = R.s1_dry_reference(bbox, EVENT, pas, t, shape, crs)
        np.savez_compressed(os.path.join(CACHE, f"{n}__s1.npz"), flooded=ref["flooded"],
                            valid=ref["valid"], meta=np.array(json.dumps(ref["meta"], default=str)))
        out[n] = ref["meta"]
        print(n, json.dumps(ref["meta"], default=str)[:300], flush=True)
    return out


def main(argv=None):
    argv = argv or sys.argv[1:]
    step = argv[0]
    if step == "boxes":
        write_refs(choose_boxes())
    else:
        rows = json.load(open(os.path.join(OUT, "weihui_boxes.json")))
        if step == "build":
            build(list(rows))
        elif step == "s1":
            s1_reference(list(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
