"""
Round 3, Phase 4: DEV cross-validation on 8 km burned units (R25), by model_r3's
pre-registered choice rule. DEV = burned units only; no reserved unit is read.

    python -m experiments.flood_round3.dev_cv_r3 ev       # event features per unit (cached)
    python -m experiments.flood_round3.dev_cv_r3 cv       # LRO predictions + gain bounds -> results/dev_cv_r3.json

Candidates, in tie-break order (simplest first):
- `elev`, `hand`: the baselines.
- `elev_hand_lr`: logistic regression on [elev pct, hand pct].
- `anc_elev_lgbm`: anchored on elevation, static features of the type's family (round 2's FULL / FLASH / COASTAL).
- `anc_elev_lgbm_ev`: as above, plus the river event features (event_feats). Only for river-led types.

Training pools all DEV units (every type); each type is scored on its own units. Folds are leave-region-out (catalog region); clusters for the bootstrap come from the catalog.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
BIG = os.path.expanduser("~/.cache/geowatch/flood_round3/big")
TABLES = os.path.join(BIG, "tables")
EV = os.path.join(BIG, "ev")
EV_FEATS = ("ev_q_ratio", "ev_q_rp", "ev_depth_below_stage_m")
RIVER_LED = ("fluvial", "waterlogging", "compound")
TYPES = ("fluvial", "pluvial", "waterlogging", "flash_flood", "coastal", "compound")


def family(ty):
    from experiments.flood_round2 import model_v3 as M3
    return {"flash_flood": M3.FLASH, "coastal": M3.COASTAL, "compound": M3.COASTAL}.get(ty, M3.FULL)


def load_tables():
    cat = json.load(open(os.path.join(OUT, "burned_catalog.json")))
    tabs = {}
    for f in sorted(os.listdir(TABLES)):
        n = f[:-4]
        z = np.load(os.path.join(TABLES, f), allow_pickle=False)
        m = json.loads(str(z["meta"]))
        y = z["y"]
        if (y == 1).sum() < 50 or (y == 0).sum() < 50 or n not in cat:
            continue
        ev = {}
        p = os.path.join(EV, f"{n}.npz")
        if os.path.exists(p):
            e = np.load(p)
            ev = {k: e[k] for k in EV_FEATS}
        else:
            ev = {k: np.full(len(y), np.nan, np.float32) for k in EV_FEATS}
        tabs[n] = {"X": z["X"], "C": z["C"], "y": y, "F": list(m["features"]), "shape": tuple(m["shape"]),
                   "ev": ev, "tags": cat[n]["tags"], "region": cat[n]["region"], "cluster": cat[n]["cluster"],
                   "grid": m["grid"], "event": m["event"]}
    return tabs


def ev():
    from experiments.flood_round3 import diagnose_ee as D
    from experiments.flood_round3 import event_feats as E
    os.makedirs(EV, exist_ok=True)
    ix = D._reach_index()
    for n, t in load_tables().items():
        p = os.path.join(EV, f"{n}.npz")
        if os.path.exists(p) or not set(t["tags"]) & set(RIVER_LED):
            continue
        f = E.river_features(t["grid"], t["event"], t["X"][:, t["F"].index("hand_merit")], ix=ix)
        np.savez_compressed(p, **{k: f[k] for k in EV_FEATS})
        print(n, f.get("_reaches", 0), flush=True)
    return 0


def _lr_pred(tabs, names, held):
    from sklearn.linear_model import LogisticRegression
    from experiments.flood_round3 import model_r3 as M

    def X(t):
        return np.nan_to_num(np.c_[M._pct_within(M.anchor_score(t, "elev")), M._pct_within(M.anchor_score(t, "hand"))],
                             nan=0.5)
    A, y, w = M._rows(tabs, names, X)
    m = LogisticRegression(max_iter=2000).fit(A, y, sample_weight=w)
    return {n: m.decision_function(X(tabs[n])).astype(np.float32) for n in held}


def cv():
    from experiments.flood_learned.model import LGBM_PARAMS
    from experiments.flood_round3 import model_r3 as M
    tabs = load_tables()
    names = sorted(tabs)
    region = {n: tabs[n]["region"] for n in names}
    cluster = {n: tabs[n]["cluster"] for n in names}
    params = {k: v for k, v in LGBM_PARAMS.items() if k not in ("verbose",)}
    runs = {"elev": {n: M.anchor_score(tabs[n], "elev") for n in names},
            "hand": {n: M.anchor_score(tabs[n], "hand") for n in names}}
    folds = {}
    for n in names:
        folds.setdefault(region[n], []).append(n)
    runs["elev_hand_lr"] = {}
    for _, held in sorted(folds.items()):
        runs["elev_hand_lr"].update(_lr_pred(tabs, [n for n in names if n not in held], held))
    lams = {}
    for fam_ty in ("fluvial", "flash_flood", "coastal"):
        feats = [f for f in family(fam_ty) if f in tabs[names[0]]["F"]]
        for suffix, fs in (("", feats), ("_ev", feats + list(EV_FEATS))):
            if suffix and fam_ty != "fluvial":
                continue
            key = f"anc_elev_lgbm{suffix}@{fam_ty}"
            pred, lam = M.lro_predictions(tabs, names, region, fs, "elev", params)
            runs[key], lams[key] = pred, lam
            print(key, lam, flush=True)
    res = {"units": {ty: [n for n in names if ty in tabs[n]["tags"]] for ty in TYPES}, "lambdas": lams, "by_type": {}}
    for ty in TYPES:
        mem = res["units"][ty]
        if len(mem) < 3:
            res["by_type"][ty] = {"units": len(mem)}
            continue
        fam = "flash_flood" if ty == "flash_flood" else "coastal" if ty in ("coastal", "compound") else "fluvial"
        cands = {"elev": "elev", "hand": "hand", "elev_hand_lr": "elev_hand_lr",
                 "anc_elev_lgbm": f"anc_elev_lgbm@{fam}"}
        if ty in RIVER_LED:
            cands["anc_elev_lgbm_ev"] = "anc_elev_lgbm_ev@fluvial"
        sub = {"elev": runs["elev"], "hand": runs["hand"]}
        out = {}
        for c, k in cands.items():
            sub[c] = runs[k]
            out[c] = M.gain_lower_bound(tabs, mem, {n: cluster[n] for n in mem}, sub, c)
        order = list(cands)
        best = M.choose(out, order)
        res["by_type"][ty] = {"units": len(mem), "clusters": len({cluster[n] for n in mem}), "candidates": out,
                              "chosen": best}
        print(ty, len(mem), best, json.dumps(out[best]), flush=True)
    M.save(res, os.path.join(OUT, "dev_cv_r3.json"))
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    return {"ev": ev, "cv": cv}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
