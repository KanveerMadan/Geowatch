"""
M6–M8 Phase C: DEV comparison with round 3's methods, unchanged (model_r3, dev_cv_r3).

    cd ~/gw-r3pin && PYTHONPATH=.:$HOME/gw-m678/experiments/flood_m678 python -B -m dev_cv_m678 feats   # event + channel features (cached)
    ... python -B -m dev_cv_m678 cv                                                                    # -> results/dev_cv_m678.json

Units: the M6–M8 DEV incidents with a built table and >= 50 flooded and >= 50 dry cells.
Folds: leave-cluster-out (region = cluster). Training pools every M6–M8 DEV unit; each type is
scored on its own units. Round 3's DEV units are not pooled: their CV alone takes hours on this
machine, and none is an M6–M8 event.

Candidates, in tie-break order (simplest first):
- `elev`, `hand`: the baselines.
- `phys_stage`: physics only, no fitting. Round 3's event stage proxy minus HAND
  (`ev_depth_below_stage_m`, GEOGloWS v2 peak in [event - 10 d, event + 7 d]). M7 levee/M8 only;
  GEOGloWS does not simulate dam or lake failures.
- `phys_main`: physics only, no fitting. Minus the height above the nearest trunk-channel cell
  (`m678_hmain_m`): the flood comes down the trunk river (the glacier-lake, breach or melt route),
  not the side streams that ordinary HAND also drains to.
- `elev_hand_lr`: logistic regression on [elev pct, hand pct].
- `anc_elev_lgbm`: anchored correction on round 2's FULL family.
- `anc_elev_lgbm_ev`: + round 3's river event features (M7 and M8).
- `anc_elev_lgbm_main`: + the trunk-channel features (all types).
Choice: model_r3.choose, the highest lower 95 % bound of the gain over the better baseline.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BIG = os.path.expanduser("~/.cache/geowatch/flood_m678/big")
TABLES = os.path.join(BIG, "tables")
EV = os.path.join(BIG, "ev")
OUT = os.path.join(HERE, "results")
EV_FEATS = ("ev_q_ratio", "ev_q_rp", "ev_depth_below_stage_m")
MAIN_FEATS = ("m678_hmain_m", "m678_dmain_m")
TRUNK_SHARE = 0.25          # trunk = MERIT upstream area >= 25 % of the box maximum
NO_GEOGLOWS = ("dam", "lake", "glacial", "outburst", "tailings")


def units(split="dev"):
    import labels_m678 as LM
    out = {}
    for r in LM.records(split):
        n = r["incident"]
        p = os.path.join(TABLES, f"{n}.npz")
        if os.path.exists(p):
            out[n] = r
    return out


def main_channel(ee, grid):
    """Per cell: height above and distance to the nearest trunk-channel cell (GLO-30, MERIT upa)."""
    from experiments.flood_learned import fetch as F
    from susceptibility.hydro_rasters import compute_pixels, grid_lonlat_bounds
    from scipy.ndimage import distance_transform_edt
    t, shape, crs = grid["transform"], tuple(grid["shape"]), grid["crs"]
    from rasterio.transform import Affine
    tr = Affine(*t)
    ll = grid_lonlat_bounds(tr, shape, crs)
    region = ee.Geometry.Rectangle(list(ll))
    dem = F._mosaic(F.GLO30_ASSET, region, "DEM")
    img = ee.Image.cat([dem.rename("z"), ee.Image("MERIT/Hydro/v1_0_1").select("upa").rename("upa")]).toFloat()
    a = compute_pixels(img, tr, shape, crs, "trunk channel")
    z, upa = np.asarray(a["z"], float), np.nan_to_num(np.asarray(a["upa"], float))
    trunk = upa >= TRUNK_SHARE * upa.max()
    d, (ri, ci) = distance_transform_edt(~trunk, return_indices=True)
    h = z - z[ri, ci]
    return {"m678_hmain_m": h.ravel().astype(np.float32), "m678_dmain_m": (d * abs(t[0])).ravel().astype(np.float32)}


def feats():
    import labels_m678 as LM
    from experiments.flood_round3 import diagnose_ee as D
    from experiments.flood_round3 import event_feats as E
    ee = LM.init_ee()
    os.makedirs(EV, exist_ok=True)
    ix = None
    for n, r in sorted(units().items()):
        p = os.path.join(EV, f"{n}.npz")
        if os.path.exists(p):
            continue
        z = np.load(os.path.join(TABLES, f"{n}.npz"), allow_pickle=False)
        m = json.loads(str(z["meta"]))
        out = main_channel(ee, m["grid"])
        if not any(w in r["subtype"] for w in NO_GEOGLOWS) or "levee" in r["subtype"]:
            ix = ix if ix is not None else D._reach_index()
            f = E.river_features(m["grid"], m["event"], z["X"][:, list(m["features"]).index("hand_merit")], ix=ix)
            out.update({k: f[k] for k in EV_FEATS})
        else:
            out.update({k: np.full(len(z["y"]), np.nan, np.float32) for k in EV_FEATS})
        np.savez_compressed(p, **out)
        print(n, {k: float(np.nanmean(v)) for k, v in out.items()}, flush=True)
    return 0


def load_tables(split="dev"):
    tabs = {}
    for n, r in sorted(units(split).items()):
        z = np.load(os.path.join(TABLES, f"{n}.npz"), allow_pickle=False)
        m = json.loads(str(z["meta"]))
        y = z["y"]
        if (y == 1).sum() < 50 or (y == 0).sum() < 50:
            continue
        e = np.load(os.path.join(EV, f"{n}.npz"))
        ev = {k: e[k] for k in EV_FEATS + MAIN_FEATS}
        ev["phys_stage"] = ev["ev_depth_below_stage_m"]
        ev["phys_main"] = -ev["m678_hmain_m"]
        tabs[n] = {"X": z["X"], "C": z["C"], "y": y, "F": list(m["features"]), "shape": tuple(m["shape"]), "ev": ev,
                   "tags": [r["type"]], "region": r["cluster"], "cluster": r["cluster"], "grid": m["grid"],
                   "event": m["event"], "subtype": r["subtype"]}
    return tabs


CANDS = {"M6": ("elev", "hand", "phys_main", "elev_hand_lr", "anc_elev_lgbm", "anc_elev_lgbm_main"),
         "M7": ("elev", "hand", "phys_stage", "phys_main", "elev_hand_lr", "anc_elev_lgbm", "anc_elev_lgbm_ev", "anc_elev_lgbm_main"),
         "M8": ("elev", "hand", "phys_stage", "phys_main", "elev_hand_lr", "anc_elev_lgbm", "anc_elev_lgbm_ev", "anc_elev_lgbm_main")}


def predictions(tabs):
    from experiments.flood_learned.model import LGBM_PARAMS
    from experiments.flood_round3 import dev_cv_r3 as R3
    from experiments.flood_round3 import model_r3 as M
    names = sorted(tabs)
    region = {n: tabs[n]["region"] for n in names}
    params = {k: v for k, v in LGBM_PARAMS.items() if k != "verbose"}
    runs = {"elev": {n: M.anchor_score(tabs[n], "elev") for n in names},
            "hand": {n: M.anchor_score(tabs[n], "hand") for n in names}}
    for k in ("phys_stage", "phys_main"):
        runs[k] = {n: np.asarray(tabs[n]["ev"][k], np.float64) for n in names}
    folds = {}
    for n in names:
        folds.setdefault(region[n], []).append(n)
    runs["elev_hand_lr"] = {}
    for _, held in sorted(folds.items()):
        runs["elev_hand_lr"].update(R3._lr_pred(tabs, [n for n in names if n not in held], held))
    full = [f for f in R3.family("fluvial") if f in tabs[names[0]]["F"]]
    lams = {}
    for key, fs in (("anc_elev_lgbm", full), ("anc_elev_lgbm_ev", full + list(EV_FEATS)),
                    ("anc_elev_lgbm_main", full + list(EV_FEATS) + list(MAIN_FEATS))):
        runs[key], lams[key] = M.lro_predictions(tabs, names, region, fs, "elev", params)
        print(key, lams[key], flush=True)
    return runs, lams


def score(tabs, runs):
    from experiments.flood_round3 import model_r3 as M
    res = {}
    for ty, cands in CANDS.items():
        mem = [n for n in sorted(tabs) if ty in tabs[n]["tags"]]
        clusters = {tabs[n]["cluster"] for n in mem}
        if len(clusters) < 2:
            res[ty] = {"units": len(mem), "clusters": len(clusters), "note": "fewer than 2 DEV clusters: no CV comparison"}
            continue
        out = {}
        for c in cands:
            ok = [n for n in mem if np.isfinite(runs[c][n]).sum() > 100]
            if len(ok) < len(mem):
                out[c] = {"skipped": f"undefined on {len(mem) - len(ok)} of {len(mem)} units"}
                continue
            sub = {"elev": runs["elev"], "hand": runs["hand"], c: runs[c]}
            out[c] = M.gain_lower_bound(tabs, mem, {n: tabs[n]["cluster"] for n in mem}, sub, c)
        valid = {c: v for c, v in out.items() if "ci" in v}
        best = M.choose(valid, [c for c in cands if c in valid])
        per_unit = {n: {c: round(M.within_auc(runs[c][n], tabs[n]["y"]), 4) for c in cands if c in valid} for n in mem}
        res[ty] = {"units": len(mem), "clusters": len(clusters), "candidates": out, "chosen": best, "per_unit": per_unit}
        print(ty, len(mem), best, json.dumps(out.get(best)), flush=True)
    return res


def cv():
    tabs = load_tables()
    runs, lams = predictions(tabs)
    res = {"units": {n: {"type": t["tags"][0], "cluster": t["cluster"], "flooded": int((t["y"] == 1).sum()),
                         "dry": int((t["y"] == 0).sum())} for n, t in tabs.items()},
           "lambdas": lams, "by_type": score(tabs, runs)}
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "dev_cv_m678.json"), "w"), indent=1, default=str)
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    return {"feats": feats, "cv": cv}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
