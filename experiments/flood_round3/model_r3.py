"""
Round 3, Phase 4: candidates and the pre-registered choice rule (DEV = burned units only).

Every learned candidate is a correction on an anchor:

    logit(x) = base(anchor) + lambda * f(x)

- base: a one-feature logistic fit on the anchor's within-unit percentile;
- f: LightGBM boosted from that base (init_score), so it learns only what improves on the anchor;
- lambda: chosen from LAMBDAS by inner leave-region-out CV on the training folds
  (the highest mean within-event AUC; ties go to the smaller lambda).

lambda = 0 is the anchor itself, so a candidate can fall below its anchor only by the
inner-to-outer CV gap, never by construction. Monotone constraints hold where physics
fixes the direction (MONOTONE).

Candidates (tie-break order, simplest first):
  elev, hand            the two baselines (no fitting);
  physics               the type's physics score where one exists (event water depth, SFINCS hmax);
  elev_hand_lr          logistic regression on [elev_pct, hand percentile];
  anc_<anchor>_lgbm     anchored correction on FEATURES[type] (+ event features), per anchor.

Choice rule (fixed before any reserved unit is read):
  per type, the candidate with the highest LOWER 95 % bound of the gain over the better
  baseline in DEV leave-region-out CV. The gain is the paired 990 m block x cluster
  bootstrap of flood_baselines (the round-2 scorer's code). Ties within 0.005 go to the
  earlier candidate. A type whose best lower bound is <= 0 keeps its better baseline as
  the method (a baseline can pass the bar only against the other baseline).
"""
from __future__ import annotations

import json
import os

import numpy as np

LAMBDAS = (0.0, 0.25, 0.5, 0.75, 1.0)
MONOTONE = {  # +1: higher value -> more flood-prone; -1: less
    "elev_glo30": -1, "elev_pct": -1, "elev_above_p10_m": -1, "hand_merit": -1, "handmap_glo30": -1,
    "hand_d8_m": -1, "dist_water_m": -1, "sea_spill_m": -1,
    "ev_depth_below_stage_m": +1, "ev_rain_3d_mm": +1, "ev_rain_weighted_acc": +1, "ev_fillspill": +1,
    "ev_surge_depth_m": +1, "ev_sfincs_hmax_m": +1, "ev_q_ratio": +1, "ev_q_rp": +1,
}


def _pct_within(v):
    from scipy.stats import rankdata
    out = np.full(v.shape, np.nan)
    ok = np.isfinite(v)
    if ok.sum() > 1:
        out[ok] = (rankdata(v[ok]) - 1) / (ok.sum() - 1)
    return out


def anchor_score(t, anchor):
    """Higher = more flood-prone, per cell. t: {"X", "C", "F" (feature names), "ev" (event feats)}."""
    if anchor == "elev":
        return -t["X"][:, t["F"].index("elev_glo30")].astype(np.float64)
    if anchor == "hand":
        return t["C"][:, 0].astype(np.float64)          # stored as a score (negated HAND)
    if anchor == "physics":
        return t["ev"]["physics"].astype(np.float64)
    raise ValueError(anchor)


def design(t, feats):
    cols = []
    for f in feats:
        if f in t["F"]:
            cols.append(t["X"][:, t["F"].index(f)].astype(np.float64))
        else:
            cols.append(np.asarray(t["ev"][f], np.float64))
    return np.stack(cols, axis=1)


def _rows(tables, names, fn):
    """Stack labelled rows with equal weight per unit."""
    Xs, ys, ws = [], [], []
    for n in names:
        t = tables[n]
        ok = (t["y"] == 0) | (t["y"] == 1)
        X = fn(t)[ok]
        Xs.append(X)
        ys.append(t["y"][ok].astype(int))
        ws.append(np.full(ok.sum(), 1.0 / max(1, ok.sum())))
    return np.concatenate(Xs), np.concatenate(ys), np.concatenate(ws) * len(names)


def fit_anchored(tables, names, feats, anchor, params, seed=20261122):
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression
    A, y, w = _rows(tables, names, lambda t: _pct_within(anchor_score(t, anchor))[:, None])
    base = LogisticRegression(C=1.0, max_iter=2000).fit(np.nan_to_num(A, nan=0.5), y, sample_weight=w)
    X, _, _ = _rows(tables, names, lambda t: design(t, feats))
    mono = [MONOTONE.get(f, 0) for f in feats]
    m = lgb.LGBMClassifier(**{**params, "random_state": seed, "monotone_constraints": mono,
                              "monotone_constraints_method": "advanced", "verbose": -1})
    m.fit(X, y, sample_weight=w, init_score=base.decision_function(np.nan_to_num(A, nan=0.5)))
    return {"base": base, "lgbm": m, "feats": list(feats), "anchor": anchor}


def predict_parts(model, t):
    a = _pct_within(anchor_score(t, model["anchor"]))[:, None]
    b = model["base"].decision_function(np.nan_to_num(a, nan=0.5))
    f = model["lgbm"].predict(design(t, model["feats"]), raw_score=True)   # boosted part only
    return b, f


def predict(model, t, lam):
    b, f = predict_parts(model, t)
    return b + lam * f


def within_auc(score, y):
    from experiments.flood_validation.harness import auc
    ok = ((y == 0) | (y == 1)) & np.isfinite(score)
    yy = y[ok]
    a = auc(score[ok], (yy == 1).astype(int), (yy == 0).astype(int))
    return float("nan") if a is None else float(a)


def choose_lambda(tables, names, region, feats, anchor, params):
    """Inner leave-region-out on `names`: mean within-event AUC per lambda; the best
    (ties to the smaller). One fit per inner fold; lambda only rescales f."""
    folds = {}
    for n in names:
        folds.setdefault(region[n], []).append(n)
    if len(folds) < 2:
        return 0.0, {}
    scores = {lam: [] for lam in LAMBDAS}
    for _, held in sorted(folds.items()):
        tr = [n for n in names if n not in held]
        m = fit_anchored(tables, tr, feats, anchor, params)
        for n in held:
            b, f = predict_parts(m, tables[n])
            for lam in LAMBDAS:
                scores[lam].append(within_auc(b + lam * f, tables[n]["y"]))
    mean = {lam: float(np.mean(v)) for lam, v in scores.items()}
    best = max(LAMBDAS, key=lambda lam: (round(mean[lam], 4), -lam))
    return best, mean


def lro_predictions(tables, names, region, feats, anchor, params):
    """Outer leave-region-out predictions with lambda chosen inside each outer fold."""
    folds = {}
    for n in names:
        folds.setdefault(region[n], []).append(n)
    pred, lams = {}, {}
    for fid, held in sorted(folds.items()):
        tr = [n for n in names if n not in held]
        lam, _ = choose_lambda(tables, tr, region, feats, anchor, params)
        m = fit_anchored(tables, tr, feats, anchor, params)
        lams[fid] = lam
        for n in held:
            pred[n] = predict(m, tables[n], lam).astype(np.float32)
    return pred, lams


def gain_lower_bound(tables, members, cluster, runs, cand):
    """Mean paired gain of `cand` over the better baseline and its 95 % interval, by the
    round-2 scorer's bootstrap (flood_baselines.blocks; 990 m blocks, cluster x block)."""
    from experiments.flood_baselines import blocks as B
    from experiments.flood_baselines import score as BS
    recs = {}
    for n in members:
        t = tables[n]
        shape = tuple(t["shape"])
        ok = (t["y"] == 0) | (t["y"] == 1)
        for k in ("elev", "hand", cand):
            ok &= np.isfinite(runs[k][n])
        recs[n] = B.paired_block_bootstrap({k: np.asarray(runs[k][n], np.float64).reshape(shape)
                                            for k in ("elev", "hand", cand)},
                                           (t["y"] == 1).reshape(shape), ok.reshape(shape),
                                           BS.BLOCK_CELLS, BS.REPS, BS._seed(n))
    me = {k: float(np.mean([recs[n]["point"][k] for n in members])) for k in ("elev", "hand")}
    base = "elev" if me["elev"] >= me["hand"] else "hand"
    if cand in ("elev", "hand"):
        base = "hand" if cand == "elev" else "elev"
    db = B.cluster_mean_bootstrap({n: recs[n]["reps"][cand] - recs[n]["reps"][base] for n in members},
                                  cluster, BS.REPS, BS.SEED)
    lo, hi = B.ci(db)
    return {"vs": base, "gain": round(float(np.mean([recs[n]["point"][cand] - recs[n]["point"][base]
                                                     for n in members])), 4),
            "ci": [round(lo, 4), round(hi, 4)],
            "mean_auc": round(float(np.mean([recs[n]["point"][cand] for n in members])), 4)}


def choose(results: dict, order: list, tie: float = 0.005) -> str:
    """results: {cand: gain_lower_bound(...)}; the highest lower bound, ties to the earlier."""
    best = max(results[c]["ci"][0] for c in order if c in results)
    for c in order:
        if c in results and results[c]["ci"][0] >= best - tie:
            return c
    raise ValueError("no candidate")


def save(obj, path):
    json.dump(obj, open(path, "w"), indent=1, default=str)
