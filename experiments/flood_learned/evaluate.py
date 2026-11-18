"""
Score the learned model's held-out predictions beside HAND and the current
modules, on the same cells, with flood_baselines' spatially blocked
bootstrap; then calibration, feature importance and a learning curve.

    python -m experiments.flood_learned.evaluate        # writes results/learned.json

Same rules as flood_baselines/score.py:
  * within-event ROC AUC on the event's common cells: labelled (flooded or
    dry; never unobserved) and every comparator and model score defined;
  * 990 m (33-cell) blocks, 1000 paired replicates per event, seeds as
    flood_baselines (SEED + sha1(name)), so the comparator AUCs and their
    intervals are the baselines' own;
  * means over events by the two-stage cluster x block bootstrap
    (registry link clusters).
"best baseline" is the best of HAND, JRC occurrence and distance to water
chosen AFTER seeing the event, as in flood_baselines (favours the baseline).
"""
from __future__ import annotations

import datetime
import json
import os
import sys

import numpy as np

from experiments.flood_baselines import blocks as B
from experiments.flood_baselines import score as BS
from experiments.flood_core.registry import registry as REG
from experiments.flood_learned import events as LE
from experiments.flood_learned import features as FT
from experiments.flood_learned import fetch as F
from experiments.flood_learned import model as M
from experiments.flood_learned import settings as ST
from experiments.flood_validation.harness import auc

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
BLOCK = BS.BLOCK_CELLS
REPS = BS.REPS
BASELINES = ("hand", "occurrence", "dist_water")
MODULES = ("fluvial", "pluvial", "waterlogging", "flash_flood")
# Reliability diagram: 10 equal-width bins (Niculescu-Mizil & Caruana 2005).
CAL_BINS = 10
# The headline models (bootstrap + calibration); every other run is scored too.
HEADLINE = ("lco__full__lgbm", "lro__full__lgbm", "lco__full__logreg", "lro__full__logreg",
            "lco__open__lgbm", "lro__open__lgbm")
LEARNING_FRACTIONS = (0.25, 0.5, 0.75)
LEARNING_REPEATS = 3


def _auc(s, y):
    return auc(s, (y == 1).astype(int), (y == 0).astype(int))


# ── per event ─────────────────────────────────────────────────────────

def event_eval(name, table, preds: dict) -> dict:
    shape = tuple(table["meta"]["shape"])
    y = table["y"]
    comp = {c: table["C"][:, i] for i, c in enumerate(FT.COMPARATORS)}
    ok = y >= 0
    for c, v in comp.items():
        ok &= np.isfinite(v)
    for v in preds.values():
        ok &= np.isfinite(v)
    scores = {**{k: v.reshape(shape) for k, v in preds.items()},
              **{c: v.reshape(shape) for c, v in comp.items()}}
    pb = B.paired_block_bootstrap(scores, (y == 1).reshape(shape), ok.reshape(shape), BLOCK,
                                  REPS, BS._seed(name))
    pt = pb["point"]
    best = max(BASELINES, key=lambda b: pt[b])
    rec = {"unit": name, "flooded": int(((y == 1) & ok).sum()), "dry": int(((y == 0) & ok).sum()),
           "tiles": pb["tiles"], "auc": {k: round(v, 4) for k, v in pt.items()},
           "ci": {k: [None if x is None else round(x, 4) for x in B.ci(r)]
                  for k, r in pb["reps"].items()},
           "best_baseline": best, "delta": {}}
    for k in preds:
        rec["delta"][k] = {}
        for ref in ("hand", "best") + MODULES + ("occurrence", "dist_water"):
            other = best if ref == "best" else ref
            d = pb["reps"][k] - pb["reps"][other]
            rec["delta"][k][ref] = {"delta": round(pt[k] - pt[other], 4),
                                    "ci": [None if x is None else round(x, 4) for x in B.ci(d)]}
    rec["_reps"] = pb["reps"]
    return rec


def group_means(recs: dict, members, cluster_of, tags, refs=("hand", "best") + MODULES):
    q = [r for n, r in recs.items() if n in members]
    out = {"events": sorted(r["unit"] for r in q),
           "clusters": len({cluster_of[r["unit"]] for r in q}), "auc": {}, "delta": {}}
    if not q:
        return out
    for k in list(tags) + list(FT.COMPARATORS):
        reps = {r["unit"]: np.asarray(r["_reps"][k]) for r in q}
        boot = B.cluster_mean_bootstrap(reps, cluster_of, REPS, BS.SEED)
        out["auc"][k] = {"mean": round(float(np.mean([r["auc"][k] for r in q])), 4),
                         "ci": [round(x, 4) for x in B.ci(boot)]}
    for k in tags:
        out["delta"][k] = {}
        for ref in refs:
            reps = {}
            for r in q:
                other = r["best_baseline"] if ref == "best" else ref
                reps[r["unit"]] = np.asarray(r["_reps"][k]) - np.asarray(r["_reps"][other])
            boot = B.cluster_mean_bootstrap(reps, cluster_of, REPS, BS.SEED)
            pts = [r["delta"][k][ref]["delta"] for r in q]
            clear_win = sum(1 for r in q if (r["delta"][k][ref]["ci"][0] or -1) > 0)
            clear_loss = sum(1 for r in q if (r["delta"][k][ref]["ci"][1] or 1) < 0)
            out["delta"][k][ref] = {"mean": round(float(np.mean(pts)), 4),
                                    "ci": [round(x, 4) for x in B.ci(boot)],
                                    "beats": sum(1 for p in pts if p > 0), "n": len(pts),
                                    "clear_wins": clear_win, "clear_losses": clear_loss}
    return out


# ── calibration ───────────────────────────────────────────────────────

def _logit(p):
    p = np.clip(np.asarray(p, np.float64), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def _cal_fit(y, p, w):
    """(calibration-in-the-large intercept a with logit(p) as offset,
    calibration slope b from y ~ c + b logit(p)); weighted, Newton."""
    lp = _logit(p)
    a = 0.0
    for _ in range(50):
        q = 1 / (1 + np.exp(-(a + lp)))
        g, h = np.sum(w * (y - q)), np.sum(w * q * (1 - q))
        a += g / h
        if abs(g / h) < 1e-10:
            break
    from scipy.optimize import minimize

    def nll(th):
        z = th[0] + th[1] * lp
        q = 1 / (1 + np.exp(-z))
        f = np.sum(w * (np.logaddexp(0, z) - y * z))
        g = np.array([np.sum(w * (q - y)), np.sum(w * (q - y) * lp)])
        return f, g
    r = minimize(nll, np.array([0.0, 1.0]), jac=True, method="L-BFGS-B")
    return float(a), float(r.x[1])


# Calibration statistics are computed on per-event aggregates: each event's
# cells are binned on logit(p) into CAL_AGG_BINS equal-width bins over the
# clipped logit range, and each bin carries (weight, weighted mean p,
# weighted y). The fits then run on ~29 x 2000 rows instead of ~450 000
# cells; with bins 0.014 logit wide the aggregation changes no reported digit
# (checked against the cell-level fit in test_learned).
CAL_AGG_BINS = 2000


def _aggregate(y, p, w):
    lp = _logit(p)
    edges = np.linspace(_logit(1e-6), _logit(1 - 1e-6), CAL_AGG_BINS + 1)
    b = np.clip(np.digitize(lp, edges) - 1, 0, CAL_AGG_BINS - 1)
    W = np.bincount(b, w, CAL_AGG_BINS)
    keep = W > 0
    P = np.bincount(b, w * p, CAL_AGG_BINS)[keep] / W[keep]
    Y = np.bincount(b, w * y, CAL_AGG_BINS)[keep] / W[keep]
    return Y, P, W[keep]


def calibration(tables, preds, cluster_of, names) -> dict:
    ys, ps, ws, cl, ev = [], [], [], [], []
    per_event = {}
    for n in names:
        y = tables[n]["y"]
        m = y >= 0
        p = preds[n][m].astype(np.float64)
        yy = y[m].astype(np.float64)
        Y, P, W = _aggregate(yy, p, np.full(yy.size, 1.0 / yy.size))
        ys.append(Y); ps.append(P); ws.append(W)
        cl.append(np.full(Y.size, cluster_of[n])); ev.append(n)
        per_event[n] = {"observed_fraction": round(float(yy.mean()), 4),
                        "mean_predicted": round(float(p.mean()), 4)}
    y, p, w, c = map(np.concatenate, (ys, ps, ws, cl))
    w = w / w.sum()

    def stats(y, p, w):
        w = w / w.sum()
        edges = np.linspace(0, 1, CAL_BINS + 1)
        b = np.clip(np.digitize(p, edges) - 1, 0, CAL_BINS - 1)
        bins = []
        ece = 0.0
        for i in range(CAL_BINS):
            m = b == i
            if not m.any():
                bins.append(None)
                continue
            wi = w[m].sum()
            pm, om = np.sum(w[m] * p[m]) / wi, np.sum(w[m] * y[m]) / wi
            ece += wi * abs(om - pm)
            bins.append({"lo": edges[i], "hi": edges[i + 1], "weight": round(float(wi), 4),
                         "mean_pred": round(float(pm), 4), "observed": round(float(om), 4)})
        prev = np.sum(w * y)
        within = y * (1 - y)              # 0 for cells; the binned variance for aggregates
        brier = np.sum(w * ((p - y) ** 2 + within))
        brier0 = np.sum(w * ((prev - y) ** 2 + within))
        a, s = _cal_fit(y, p, w)
        return {"ece": float(ece), "brier": float(brier), "brier_constant": float(brier0),
                "brier_skill": float(1 - brier / brier0), "intercept": a, "slope": s,
                "bins": bins, "prevalence_weighted": float(prev)}
    pt = stats(y, p, w)
    rng = np.random.default_rng(BS.SEED)
    uc = np.unique(c)
    idx = {k: np.flatnonzero(c == k) for k in uc}
    boot = {"ece": [], "intercept": [], "slope": [], "brier_skill": []}
    for _ in range(REPS):
        pick = rng.choice(uc, uc.size, replace=True)
        ii = np.concatenate([idx[k] for k in pick])
        s = stats(y[ii], p[ii], w[ii])
        for k in boot:
            boot[k].append(s[k])
    out = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in pt.items()}
    out["ci"] = {k: [round(x, 4) for x in B.ci(v)] for k, v in boot.items()}
    obs = np.array([per_event[n]["observed_fraction"] for n in names])
    prd = np.array([per_event[n]["mean_predicted"] for n in names])
    from scipy.stats import spearmanr
    out["per_event"] = per_event
    out["event_prevalence_spearman"] = round(float(spearmanr(obs, prd).statistic), 4)
    lo_i, hi_i = out["ci"]["intercept"]
    lo_s, hi_s = out["ci"]["slope"]
    # Weak calibration (Van Calster et al. 2016, J Clin Epidemiol 74:167):
    # intercept 0 and slope 1 both inside their cluster-bootstrap intervals.
    out["weakly_calibrated"] = bool(lo_i <= 0 <= hi_i and lo_s <= 1 <= hi_s)
    out["call_it"] = "probability" if out["weakly_calibrated"] else "score"
    return out


# ── importance and learning curve ─────────────────────────────────────

def permutation_importance(tables, names, cluster_of, variant="full", split="lco",
                           groups=None) -> dict:
    """Held-out within-event AUC drop when one feature (or group) is permuted
    among an event's labelled cells; the model is refitted per fold as in
    model.cv_predict (same seed, so the same models)."""
    cols = M.columns(variant)
    feats = list(M.FEATURE_SETS[variant])
    groups = groups or {f: [f] for f in feats}
    rng = np.random.default_rng(BS.SEED)
    drops = {g: {} for g in groups}
    gain = {f: [] for f in feats}
    for fid, held in sorted(M.folds(names, split, cluster_of).items()):
        train = [n for n in names if n not in held]
        X, y, w = M.training_rows(tables, train, cols)
        m = M.fit_lgbm(X, y, w)
        g = m.booster_.feature_importance("gain")
        for f, v in zip(feats, g / g.sum()):
            gain[f].append(float(v))
        for n in held:
            t = tables[n]
            lab = t["y"] >= 0
            Xe = t["X"][lab][:, cols].copy()
            ye = t["y"][lab]
            base = _auc(m.predict_proba(Xe)[:, 1], ye)
            for gname, members in groups.items():
                Xp = Xe.copy()
                perm = rng.permutation(Xe.shape[0])
                for f in members:
                    j = feats.index(f)
                    Xp[:, j] = Xe[perm, j]
                drops[gname][n] = base - _auc(m.predict_proba(Xp)[:, 1], ye)
    out = {}
    for gname, d in drops.items():
        v = np.array(list(d.values()))
        out[gname] = {"mean_auc_drop": round(float(v.mean()), 4),
                      "events_hurt": int((v > 0).sum()), "n": int(v.size),
                      "per_event": {k: round(float(x), 4) for k, x in d.items()}}
    gain_mean = {f: round(float(np.mean(v)), 4) for f, v in gain.items()}
    return {"permutation": out, "gain_share_mean_over_folds": gain_mean}


def learning_curve(tables, names, cluster_of, variant="full") -> dict:
    """Train on a random share of each fold's training CLUSTERS (whole
    clusters), predict the held-out cluster, repeat; mean within-event AUC
    and mean AUC minus HAND over all events (point values)."""
    hand_i = FT.COMPARATORS.index("hand")
    res = {}
    for frac in LEARNING_FRACTIONS:
        runs = []
        for rep in range(LEARNING_REPEATS):
            def subset(train, rng, frac=frac):
                cls = sorted({cluster_of[n] for n in train})
                k = max(1, int(round(frac * len(cls))))
                keep = set(rng.choice(cls, k, replace=False).tolist())
                return [n for n in train if cluster_of[n] in keep]
            preds, info = M.cv_predict(tables, names, "lco", variant, cluster_of,
                                       train_subset=subset, seed=M.SEED + rep + 1)
            a, d = [], []
            for n in names:
                t = tables[n]
                ok = (t["y"] >= 0) & np.isfinite(t["C"][:, hand_i])
                am = _auc(preds[n][ok], t["y"][ok])
                ah = _auc(t["C"][ok, hand_i], t["y"][ok])
                a.append(am); d.append(am - ah)
            ntr = np.mean([v["n_train_events"] for v in info.values()])
            runs.append({"mean_auc": float(np.mean(a)), "mean_minus_hand": float(np.mean(d)),
                         "mean_train_events": float(ntr)})
        res[str(frac)] = {"runs": runs,
                          "mean_auc": round(float(np.mean([r["mean_auc"] for r in runs])), 4),
                          "mean_minus_hand": round(float(np.mean([r["mean_minus_hand"]
                                                                  for r in runs])), 4),
                          "mean_train_events": round(float(np.mean([r["mean_train_events"]
                                                                    for r in runs])), 1)}
    return res


# ── main ──────────────────────────────────────────────────────────────

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-learning-curve", action="store_true")
    args = ap.parse_args(argv)
    reg = REG.load()
    cat = [c for c in LE.batch0(reg) if os.path.exists(FT.path(c["unit"]))]
    names = [c["unit"] for c in cat]
    cluster_of = LE.clusters(names, reg)
    tables = M.load_tables(names)
    tags = sorted(t[:-4] for t in os.listdir(M.PRED_CACHE) if t.endswith(".npz")
                  and ".tmp" not in t)
    preds = {t: M.load_preds(t) for t in tags}
    # per event, every run scored together (paired)
    recs = {}
    rec_dir = os.path.join(M.PRED_CACHE, "..", "event_eval")
    os.makedirs(rec_dir, exist_ok=True)
    stamp = sorted((t, os.path.getmtime(M.pred_path(t))) for t in tags)
    for n in names:
        rp = os.path.join(rec_dir, f"{n}.pkl")
        if os.path.exists(rp):                    # resume: same runs, same files
            import pickle
            with open(rp, "rb") as fh:
                got = pickle.load(fh)
            if got["stamp"] == stamp:
                recs[n] = got["rec"]
                continue
        print("evaluate", n, flush=True)
        recs[n] = event_eval(n, tables[n], {t: preds[t][0][n] for t in tags})
        import pickle
        with open(rp + ".tmp", "wb") as fh:
            pickle.dump({"stamp": stamp, "rec": recs[n]}, fh)
        os.replace(rp + ".tmp", rp)
    # checks: the comparator AUCs equal flood_baselines' own on these cells
    with open(os.path.join(HERE, "..", "flood_baselines", "results", "baselines.json")) as fh:
        bl = {e["unit"]: e for e in json.load(fh)["events"]}
    check = {n: {c: (recs[n]["auc"][c], bl[n]["auc"].get(c)) for c in FT.COMPARATORS}
             for n in names}
    mismatches = {n: {c: v for c, v in d.items() if v[1] is not None and abs(v[0] - v[1]) > 1e-4}
                  for n, d in check.items()}
    mismatches = {n: d for n, d in mismatches.items() if d}
    # tags and groups
    tag_of = {}
    for n in names:
        s = F.load(n)["meta"].get("settings")
        tag_of[n] = ST.tags(n, s) if s else None
    mech = {c["unit"]: LE.BE.mechanism(c, reg) for c in cat}
    excl, r4_test, aliases = BS.excluding_round4_test(cat, reg, names)
    groups = {"all": set(names), "excl_r4_test": excl}
    for ft in LE.FLOOD_TYPES:
        groups[f"type:{ft}"] = {n for n in names if ft in mech[n]}
    for st in ("urban", "peri_urban", "rural", "mountain", "arid", "coastal", "delta"):
        groups[f"setting:{st}"] = {n for n in names if tag_of[n] and tag_of[n][st]}
        groups[f"setting:not_{st}"] = {n for n in names if tag_of[n] and not tag_of[n][st]}
    for r in sorted(set(LE.REGION.values())):
        groups[f"region:{r}"] = {n for n in names if LE.region(n) == r}
    means = {g: group_means(recs, mem, cluster_of, tags) for g, mem in groups.items() if mem}
    cal = {t: calibration(tables, preds[t][0], cluster_of, names) for t in HEADLINE if t in preds}
    print("importance", flush=True)
    grp = {"terrain_fabdem": list(M.terrain("fabdem")), "merit_hydro": list(M.MERIT),
           "water_history": list(M.WATER), "rain": list(M.RAIN),
           "land_cover": [f for f in M.LAND if f.startswith("wc_")],
           "vegetation_ndvi": ["ndvi_pre"], "clay": ["clay_pct"]}
    imp = permutation_importance(tables, names, cluster_of)
    imp_groups = permutation_importance(tables, names, cluster_of, groups=grp)["permutation"]
    lc = None
    if not args.skip_learning_curve:
        print("learning curve", flush=True)
        lc = learning_curve(tables, names, cluster_of)
    res = {
        "what": "learned flood model vs HAND and the current modules (exp/flood-learned)",
        "run_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "settings": {"block_cells": BLOCK, "reps": REPS, "seed": BS.SEED,
                     "lgbm_params": M.LGBM_PARAMS, "param_sensitivity": M.PARAM_SENSITIVITY,
                     "lgbm_seed": M.SEED, "lr_c": M.LR_C, "cal_bins": CAL_BINS,
                     "feature_sets": M.FEATURE_SETS},
        "events": names, "clusters": cluster_of,
        "regions": {n: LE.region(n) for n in names}, "mechanism": mech, "setting_tags": tag_of,
        "excl_r4_test": {"kept": sorted(excl), "removed_test": sorted(r4_test),
                         "removed_aliases": sorted(aliases)},
        "comparator_check_vs_baselines": {"mismatches": mismatches, "n_checked": len(check)},
        "runs": {t: {k: v for k, v in preds[t][1].items() if k != "folds"} | {
            "folds": {f: {k: v for k, v in d.items() if k != "gain"}
                      for f, d in preds[t][1]["folds"].items()}} for t in tags},
        "per_event": {n: {k: v for k, v in r.items() if k != "_reps"} for n, r in recs.items()},
        "means": means, "calibration": cal, "importance": imp,
        "importance_groups": imp_groups, "learning_curve": lc,
        "table_meta": {n: tables[n]["meta"] for n in names},
    }
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "learned.json")
    with open(p, "w") as fh:
        json.dump(res, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print("wrote", p, "| comparator mismatches:", len(mismatches))
    return 0


if __name__ == "__main__":
    sys.exit(main())
