"""
Round 3 freeze (PREREGISTRATION_R3.md §3): the final model for each type whose DEV-chosen method is learned and that
has reserve units, trained on all DEV units.

- lambda: model_r3.choose_lambda's rule on all DEV units. Leave-region-out over every DEV region, mean within-unit AUC
  per lambda, the best (ties to the smaller).
- model: model_r3.fit_anchored on all DEV units (cv_lean.fit, the same rows, order, weights and seed; equivalence
  checked in R34).
- Saved to big/frozen_r3/<key>.pkl. Their SHA256 go into results/frozen_r3.json and FREEZE_R3.txt.

    python -m experiments.flood_round3.freeze_r3
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys
import time

import numpy as np

from experiments.flood_round3 import cv_lean as L
from experiments.flood_round3 import dev_cv_r3 as D
from experiments.flood_round3 import model_r3 as M

FROZEN = os.path.join(D.BIG, "frozen_r3")
METHODS = {"waterlogging": "anc_elev_lgbm_wl@fluvial", "pluvial": "anc_elev_lgbm_fine@fluvial"}


def final(types, key):
    from experiments.flood_learned.model import LGBM_PARAMS
    params = {k: v for k, v in LGBM_PARAMS.items() if k not in ("verbose",)}
    tabs, U, need, cands, F0 = L.load(types)
    L._NAMES["U"] = U
    names = sorted(tabs)
    region = {n: tabs[n]["region"] for n in names}
    idx = [U.index(f) for f in L.feats_of(key, F0)]
    folds = {}
    for n in names:
        folds.setdefault(region[n], []).append(n)
    scores = {lam: [] for lam in M.LAMBDAS}
    for o, held in sorted(folds.items()):
        t0 = time.time()
        m = L.fit(tabs, [n for n in names if region[n] != o], idx, params)
        for n in held:
            b, f = L.parts(m, tabs[n], idx)
            for lam in M.LAMBDAS:
                scores[lam].append(M.within_auc(b + lam * f, tabs[n]["y"]))
        print(key, "lambda fold", o, f"{time.time() - t0:.0f}s", flush=True)
    mean = {lam: float(np.mean(v)) for lam, v in scores.items()}
    lam = max(M.LAMBDAS, key=lambda x: (round(mean[x], 4), -x))
    m = L.fit(tabs, names, idx, params)
    model = {"key": key, "base": m["base"], "lgbm": m["lgbm"], "feats": L.feats_of(key, F0), "anchor": "elev",
             "lambda": lam, "lambda_mean_auc": mean, "dev_units": len(names)}
    os.makedirs(FROZEN, exist_ok=True)
    p = os.path.join(FROZEN, key.replace("@", "__") + ".pkl")
    pickle.dump(model, open(p, "wb"))
    return p, model


def predict(model, t_full):
    """Score of a frozen model on a unit table in dev_cv_r3 form (X, F, C, ev)."""
    a = M._pct_within(M.anchor_score(t_full, "elev"))[:, None]
    b = model["base"].decision_function(np.nan_to_num(a, nan=0.5))
    f = model["lgbm"].predict(M.design(t_full, model["feats"]), raw_score=True)
    return (b + model["lambda"] * f).astype(np.float32)


def main(argv=None):
    out = {}
    for ty, key in METHODS.items():
        p, m = final([ty], key)
        out[ty] = {"key": key, "path": os.path.relpath(p, os.path.expanduser("~")).join(["~/", ""]),
                   "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(), "lambda": m["lambda"],
                   "lambda_mean_auc": m["lambda_mean_auc"], "dev_units": m["dev_units"], "features": m["feats"]}
        print(ty, json.dumps({k: v for k, v in out[ty].items() if k != "features"}), flush=True)
    json.dump(out, open(os.path.join(D.OUT, "frozen_r3.json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
