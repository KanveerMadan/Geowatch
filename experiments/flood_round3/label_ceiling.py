"""
Round 3 (R33): label-quality diagnostics, DEV only. Nothing here reads a reserve label.

    python -m experiments.flood_round3.label_ceiling rain    -> results/rain_label_ceiling.json
    python -m experiments.flood_round3.label_ceiling hwm     -> results/hwm_diagnostic.json

rain: a split-half oracle for the 311 labels. Per DEV 311 unit and seed, the storm's flood reports are split at
random into halves A and B. Score = count of A's flood reports within 150 m of a cell. AUC is taken on B's flooded
cells vs the unit's dry cells. It is a noisy oracle: it knows where this storm's other reports fell, which no
model does, but A is itself a sample. If it cannot reach 0.70, the label cannot reward a model at 0.70.
FloodNet: only 14 sensors were installed before 2022, so FloodNet cannot measure this on DEV. Its full network
(~500) covers 2022+, the sealed reserve period.

hwm: Codex's tools/flood-speed (86c7508) peak survey tiles. These are positive-only: surveyed water heights give
no dry cells. So this is a presence-vs-background AUC (wet cells vs every valid cell of the tile) for elevation
(GLO-30) and HAND (MERIT). The marks were kept only where water exceeded 3DEP terrain by > 1 m, so low terrain is
favoured by construction. DEV diagnostic only; never a pass/fail unit.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
FLOODSPEED = os.path.expanduser("~/gw-floodspeed")


def rain(seeds=5, radius=150.0):
    from pyproj import Transformer
    from scipy.spatial import cKDTree
    from sklearn.metrics import roc_auc_score
    from experiments.flood_round3 import rain311 as R3
    from experiments.flood_round3 import fine_feats as FF
    units = json.load(open(os.path.join(R3.REFS, "units.json")))
    evs = {(c, e["event"]): e for c, rows in json.load(open(os.path.join(OUT, "r311_events.json"))).items() for e in rows}
    res = {}
    for n, u in sorted(units.items()):
        z = np.load(os.path.join(R3.REFS, f"{n}.npz"))
        meta = json.loads(str(z["meta"]))
        y = z["y3"].ravel()
        if (y == 1).sum() < 50 or (y == 0).sum() < 50:
            continue
        city = FF.city_of(meta)
        e = evs.get((city, u["event"]))
        if e is None:
            continue
        rep = [r for r in R3.reports(city, e) if r[0] == "flood"]
        g = meta["grid"]
        tr = Transformer.from_crs(4326, g["crs"], always_xy=True)
        X, Y = tr.transform(np.array([r[1] for r in rep]), np.array([r[2] for r in rep]))
        H, W = g["shape"]
        t = g["transform"]
        rr, cc = np.divmod(np.arange(H * W), W)
        xs, ys = t[2] + (cc + 0.5) * t[0], t[5] + (rr + 0.5) * t[4]
        col = np.floor((X - t[2]) / t[0]).astype(int)
        row = np.floor((Y - t[5]) / t[4]).astype(int)
        inside = (row >= 0) & (row < H) & (col >= 0) & (col < W)
        aucs = []
        for s in range(seeds):
            rng = np.random.default_rng(1000 + s)
            half = rng.random(len(X)) < 0.5
            a = ~half
            if a.sum() < 5 or (half & inside).sum() < 20:
                continue
            tree = cKDTree(np.c_[X[a], Y[a]])
            score = tree.query_ball_point(np.c_[xs, ys], radius, return_length=True).astype(float)
            bcells = np.zeros(H * W, bool)
            bcells[(row[half & inside] * W + col[half & inside])] = True
            acells = np.zeros(H * W, bool)
            acells[(row[a & inside] * W + col[a & inside])] = True
            pos = bcells & (y == 1) & ~acells          # B's flooded cells that A did not already mark
            neg = y == 0
            if pos.sum() < 20:
                continue
            yy = np.r_[np.ones(pos.sum()), np.zeros(neg.sum())]
            aucs.append(roc_auc_score(yy, np.r_[score[pos], score[neg]]))
        if aucs:
            res[n] = {"city": city, "event": u["event"], "auc": round(float(np.mean(aucs)), 3), "seeds": len(aucs)}
    by = {}
    for v in res.values():
        by.setdefault(v["city"], []).append(v["auc"])
    summ = {c: {"units": len(a), "median": round(float(np.median(a)), 3), "mean": round(float(np.mean(a)), 3),
                "p25": round(float(np.percentile(a, 25)), 3), "p75": round(float(np.percentile(a, 75)), 3)} for c, a in by.items()}
    allv = [v["auc"] for v in res.values()]
    out = {"method": __doc__.split("rain:")[1].split("hwm:")[0].strip(), "radius_m": radius, "seeds": seeds,
           "by_city": summ, "all": {"units": len(allv), "mean": round(float(np.mean(allv)), 3) if allv else None},
           "units": res, "floodnet": "14 sensors installed before 2022 (496 total); not usable on DEV"}
    json.dump(out, open(os.path.join(OUT, "rain_label_ceiling.json"), "w"), indent=1)
    print(json.dumps({"by_city": summ, "all": out["all"]}, indent=1))
    return 0


def hwm():
    from affine import Affine
    from sklearn.metrics import roc_auc_score
    from susceptibility.hydro_rasters import compute_pixels
    from experiments.flood_round3.diagnose_ee import _init
    sys.path.insert(0, FLOODSPEED)
    from tools.floodspeed_labels import iter_labels
    ee = _init()
    dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic().rename("elev")
    hand = ee.Image("MERIT/Hydro/v1_0_1").select("hnd").rename("hand")
    res = {}
    for ev in ("Harvey", "Irma", "Florence", "Michael", "Ida"):
        pos_e, bg_e, pos_h, bg_h, ntiles = [], [], [], [], 0
        for meta, state in iter_labels("peak", event=ev):
            wet = state == 2
            if not wet.any():
                continue
            g = meta["grid"]
            a = compute_pixels(ee.Image.cat([dem, hand]).toFloat(), Affine(*g["transform"][:6]), tuple(g["shape"]), g["crs"], f"hwm {ev}")
            e_, h_ = np.asarray(a["elev"], float), np.asarray(a["hand"], float)
            ok = np.isfinite(e_) & np.isfinite(h_)
            pos_e += list(e_[wet & ok]); pos_h += list(h_[wet & ok])
            bg_e += list(e_[ok]); bg_h += list(h_[ok])
            ntiles += 1
        if len(pos_e) < 5:
            res[ev] = {"wet_cells": len(pos_e), "note": "too few wet cells"}
            continue
        yy = np.r_[np.ones(len(pos_e)), np.zeros(len(bg_e))]
        res[ev] = {"tiles": ntiles, "wet_cells": len(pos_e), "background_cells": len(bg_e),
                   "auc_low_elevation": round(float(roc_auc_score(yy, -np.r_[pos_e, bg_e])), 3),
                   "auc_low_hand": round(float(roc_auc_score(yy, -np.r_[pos_h, bg_h])), 3)}
        print(ev, res[ev], flush=True)
    out = {"source": "tools/flood-speed 86c7508 peak survey tiles (Codex); DEV only",
           "caveat": "positive-only (no surveyed dry cells): presence-vs-background AUC, not the bar's metric. Marks were "
                     "kept only where water exceeded 3DEP terrain by > 1 m, which favours low terrain by construction.",
           "events": res}
    json.dump(out, open(os.path.join(OUT, "hwm_diagnostic.json"), "w"), indent=1)
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    return {"rain": rain, "hwm": hwm}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
