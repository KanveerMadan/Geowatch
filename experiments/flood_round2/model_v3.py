"""
Phase H: model v3 on DEV only, and the method choice per flood type.

    python -m experiments.flood_round2.model_v3 cv        # leave-region-out (+ cluster-out) predictions per candidate
    python -m experiments.flood_round2.model_v3 choose    # choice per type (PREREGISTRATION_ROUND2 §4), calibration, final models
    python -m experiments.flood_round2.model_v3 report    # DEV bootstrap table per type

DEV:
- every unit with a flood_round2 table (features_r2) that is role dev in the registry, never JRC-circular;
- at least MIN_FLOODED / MIN_DRY labelled cells.

Regions: batch-0 units by flood_learned.events.REGION; others by the registry region ("africa" -> "africa_west_asia").
Clusters: registry links (flood_baselines.events.clusters). Every unit carries equal weight.

Candidates, in tie-break order (simplest first):
1. `elev`: -GLO-30 elevation (plain lowest-ground ranking; no fitting);
2. `hand`: the HAND comparator as stored (already a score: higher = lower HAND);
3. `full_lr`: logistic regression (flood_learned LogReg) on FULL features;
4. `resid_lgbm`: LightGBM on FULL features, boosted from an elevation-only logistic fit on `elev_pct`. It learns only what improves on elevation.
5. `flash_lgbm` / `coastal_lgbm`: LightGBM on type-specific features. Each competes only for its own types (flash_flood; coastal and compound).
6. `full_lgbm`: LightGBM on FULL features.

LightGBM hyperparameters: flood_learned.model.LGBM_PARAMS, unchanged since batch 0.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys
import time

import numpy as np

from experiments.flood_baselines import events as BE
from experiments.flood_core.registry import registry as REG
from experiments.flood_learned import events as LE
from experiments.flood_learned import model as M
from experiments.flood_round2 import features_r2 as R
from experiments.flood_validation.harness import MIN_DRY_CELLS, MIN_FLOODED_CELLS, auc

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_round2/model_v3")
TYPES = ("fluvial", "pluvial", "waterlogging", "flash_flood", "coastal", "compound")
DEV_COMPOUND = ("valencia_2024", "paiporta", "beira", "black_river", "fort_myers_beach", "kyaukpyu", "sittwe")
F = R.FEATURES_R2
_T = tuple(f"{t}_glo30" for t in ("slope", "curv", "tpi990", "relmin2km", "depr", "handmap"))
WC = tuple(f"wc_{c}" for c in ("built", "tree", "shrub", "grass", "crop", "bare", "wetland", "mangrove"))
OPEN = _T + ("log_hs_acc", "dist_water_m", "jrc_occurrence", "jrc_recurrence", "rain_p999_mm_h",
             "rain_design_day_mm", "rain_annual_mm", "clay_pct") + WC + ("ndvi_pre", "elev_glo30", "dist_coast_m",
                                                                         "ghsl_built_frac")
FULL = OPEN + R.NEW
FLASH = ("elev_pct", "elev_above_p10_m", "valley_floor", "hand_d8_m", "log_acc30", "spi", "upslope_mean_slope",
         "kirpich_tc_min", "slope_glo30", "tpi990_glo30", "relmin2km_glo30", "handmap_glo30", "rain_p999_mm_h",
         "rain_design_day_mm", "dist_water_m") + WC
COASTAL = ("elev_glo30", "elev_pct", "elev_above_p10_m", "dist_coast_m", "sea_spill_m", "shield_depth_m",
           "sea_conn_1m", "sea_conn_2m", "sea_conn_3m", "handmap_glo30", "relmin2km_glo30", "depr_glo30",
           "jrc_occurrence", "dist_water_m", "ghsl_built_frac") + WC
ORDER = ("elev", "hand", "full_lr", "resid_lgbm", "flash_lgbm", "coastal_lgbm", "full_lgbm")
ONLY_FOR = {"flash_lgbm": ("flash_flood",), "coastal_lgbm": ("coastal", "compound")}
TIE = 0.005


def cols(names):
    return [F.index(f) for f in names]


def dev_units():
    reg = REG.load()
    units = REG.units(reg)
    b0 = {c["unit"]: c for c in LE.batch0(reg)}
    names, region, tags = [], {}, {}
    for f in sorted(os.listdir(R.CACHE)):
        n = f[:-4]
        u = units.get(n)
        if u is None or u["role"] != "dev" or n in LE.JRC_REFERENCE_UNITS:
            continue
        y = np.load(R.path(n))["y"]
        if (y == 1).sum() < MIN_FLOODED_CELLS or (y == 0).sum() < MIN_DRY_CELLS:
            continue
        if n in b0:
            region[n], t = LE.region(n), set(BE.mechanism(b0[n], reg))
        elif "flood_final" in u:
            r = u["flood_final"].get("region", "")
            region[n] = "africa_west_asia" if r in ("africa", "africa_west_asia") else r
            t = set(u["flood_final"]["tags"])
        else:
            continue
        if n in DEV_COMPOUND:
            t.add("compound")
        names.append(n)
        tags[n] = sorted(t & set(TYPES))
    return names, region, tags


def load_tables(names):
    return {n: R.load(n) for n in names}


def _rows(tables, names, c):
    X, y, w = M.training_rows(tables, names, c)
    return X, y, w


def _base_lr(tables, names):
    from sklearn.linear_model import LogisticRegression
    X, y, w = _rows(tables, names, cols(("elev_pct",)))
    X = np.nan_to_num(X, nan=0.5)
    return LogisticRegression(C=1.0, max_iter=2000).fit(X, y, sample_weight=w)


def _base_logit(lr, X1):
    return lr.decision_function(np.nan_to_num(X1, nan=0.5))


def fit(cand, tables, names):
    import lightgbm as lgb
    if cand in ("elev", "hand"):
        return None
    if cand == "full_lr":
        X, y, w = _rows(tables, names, cols(FULL))
        return M.LogReg().fit(X, y, w)
    feats = {"resid_lgbm": FULL, "flash_lgbm": FLASH, "coastal_lgbm": COASTAL, "full_lgbm": FULL}[cand]
    X, y, w = _rows(tables, names, cols(feats))
    p = {**M.LGBM_PARAMS, "random_state": M.SEED}
    if cand == "resid_lgbm":
        base = _base_lr(tables, names)
        X1, _, _ = _rows(tables, names, cols(("elev_pct",)))
        m = lgb.LGBMClassifier(**p).fit(X, y, sample_weight=w, init_score=_base_logit(base, X1))
        return {"lgbm": m, "base": base}
    return lgb.LGBMClassifier(**p).fit(X, y, sample_weight=w)


def predict(cand, model, t):
    X = t["X"]
    if cand == "elev":
        return -X[:, F.index("elev_glo30")].astype(np.float64)
    if cand == "hand":
        # flood_learned tables store comparators as scores (higher = more flood-prone): HAND is already negated
        return t["C"][:, 0].astype(np.float64)
    if cand == "full_lr":
        return model.predict_proba(X[:, cols(FULL)])[:, 1]
    if cand == "resid_lgbm":
        raw = model["lgbm"].predict(X[:, cols(FULL)], raw_score=True) + _base_logit(model["base"], X[:, cols(("elev_pct",))])
        return 1.0 / (1.0 + np.exp(-raw))
    feats = {"flash_lgbm": FLASH, "coastal_lgbm": COASTAL, "full_lgbm": FULL}[cand]
    return model.predict_proba(X[:, cols(feats)])[:, 1]


def run_cv():
    names, region, tags = dev_units()
    cl = BE.clusters(names, REG.load())
    tables = load_tables(names)
    os.makedirs(CACHE, exist_ok=True)
    for split, key in (("lro", region), ("lco", {n: f"c{cl[n]}" for n in names})):
        folds = {}
        for n in names:
            folds.setdefault(key[n], []).append(n)
        for cand in ORDER:
            p = os.path.join(CACHE, f"{split}__{cand}.npz")
            if os.path.exists(p):
                continue
            t0 = time.time()
            pred = {}
            for fid, held in sorted(folds.items()):
                train = [n for n in names if n not in held]
                m = fit(cand, tables, train)
                for n in held:
                    pred[n] = predict(cand, m, tables[n]).astype(np.float32)
            np.savez_compressed(p, **pred)
            print(f"── {split}__{cand} {time.time() - t0:.0f} s", flush=True)
    json.dump({"names": names, "region": region, "tags": tags, "clusters": cl},
              open(os.path.join(CACHE, "dev_units.json"), "w"), indent=1)
    return 0


def _aucs(tables, names, runs):
    out = {}
    for n in names:
        t = tables[n]
        ok = t["y"] >= 0
        for r in runs.values():
            ok &= np.isfinite(r[n])
        y = t["y"][ok]
        out[n] = {k: round(float(auc(r[n][ok], (y == 1).astype(int), (y == 0).astype(int))), 4)
                  for k, r in runs.items()}
    return out


def load_runs(split):
    out = {}
    for cand in ORDER:
        z = np.load(os.path.join(CACHE, f"{split}__{cand}.npz"))
        out[cand] = {k: z[k] for k in z.files}
    return out


def choose():
    from sklearn.isotonic import IsotonicRegression
    d = json.load(open(os.path.join(CACHE, "dev_units.json")))
    names, tags = d["names"], d["tags"]
    tables = load_tables(names)
    lro, lco = load_runs("lro"), load_runs("lco")
    pa, pc = _aucs(tables, names, lro), _aucs(tables, names, lco)
    choice = {}
    for ty in TYPES:
        mem = [n for n in names if ty in tags[n]]
        if not mem:
            continue
        cands = [c for c in ORDER if ty in ONLY_FOR.get(c, (ty,))]
        means = {c: float(np.mean([pa[n][c] for n in mem])) for c in cands}
        best = max(means.values())
        pick = next(c for c in cands if best - means[c] <= TIE)          # ORDER = simplest first
        choice[ty] = {"members": mem, "n": len(mem), "lro_mean_auc": means, "chosen": pick,
                      "lco_mean_auc": {c: float(np.mean([pc[n][c] for n in mem])) for c in cands}}
        print(f"{ty:12s} n={len(mem):3d} chosen {pick:13s} {means[pick]:.3f} | elev {means['elev']:.3f} "
              f"hand {means['hand']:.3f} best {best:.3f}", flush=True)
    finals = {}
    # every fitted candidate gets a final model: the held-out pass reports them all (PREREGISTRATION_ROUND2 §5)
    for c in ORDER:
        if c in ("elev", "hand"):
            continue
        ys, ps, ws = [], [], []
        for n in names:
            y = tables[n]["y"]
            k = (y >= 0) & np.isfinite(lro[c][n])
            ys.append(y[k]); ps.append(lro[c][n][k]); ws.append(np.full(k.sum(), 1.0 / max(1, k.sum())))
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(
            np.concatenate(ps), np.concatenate(ys), sample_weight=np.concatenate(ws))
        m = fit(c, tables, names)
        p = os.path.join(CACHE, f"final__{c}.pkl")
        with open(p, "wb") as fh:
            pickle.dump({"cand": c, "model": m, "isotonic": iso}, fh)
        finals[c] = {"path": os.path.basename(p), "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(),
                     "n_train_units": len(names)}
    res = {"what": "flood_round2 method choice, DEV only (leave-region-out mean AUC per type; ties -> simplest)",
           "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "order": list(ORDER), "tie": TIE,
           "dev_units": names, "regions": d["region"], "tags": tags, "clusters": d["clusters"],
           "choice": choice, "final_models": finals, "per_unit_lro": pa, "per_unit_lco": pc}
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "method_choice_r2.json"), "w"), indent=1, default=float)
    print("wrote results/method_choice_r2.json")
    return 0


def report():
    """Paired 990 m block bootstrap per unit, cluster x block mean bootstrap per type: the
    chosen candidate and every other, with deltas vs HAND and vs elevation."""
    from experiments.flood_baselines import blocks as B
    from experiments.flood_baselines import score as BS
    d = json.load(open(os.path.join(CACHE, "dev_units.json")))
    names, tags, cl = d["names"], d["tags"], d["clusters"]
    ch = json.load(open(os.path.join(OUT, "method_choice_r2.json")))["choice"]
    lro = load_runs("lro")
    recs = {}
    for n in names:
        t = R.load(n)
        shape = tuple(t["meta"]["shape"])
        ok = t["y"] >= 0
        for r in lro.values():
            ok &= np.isfinite(r[n])
        pb = B.paired_block_bootstrap({k: np.asarray(r[n], np.float64).reshape(shape) for k, r in lro.items()},
                                      (t["y"] == 1).reshape(shape), ok.reshape(shape), BS.BLOCK_CELLS, BS.REPS,
                                      BS._seed(n))
        recs[n] = pb
    res = {"groups": {}}
    for ty, c in ch.items():
        mem = c["members"]
        g = {"chosen": c["chosen"], "units": len(mem), "clusters": len({cl[n] for n in mem}), "mean": {}, "delta": {}}
        for k in lro:
            boot = B.cluster_mean_bootstrap({n: recs[n]["reps"][k] for n in mem}, cl, BS.REPS, BS.SEED)
            g["mean"][k] = [round(float(np.mean([recs[n]["point"][k] for n in mem])), 4), [round(x, 4) for x in B.ci(boot)]]
            for base in ("hand", "elev"):
                if k == base:
                    continue
                db = B.cluster_mean_bootstrap({n: recs[n]["reps"][k] - recs[n]["reps"][base] for n in mem}, cl,
                                              BS.REPS, BS.SEED)
                g["delta"][f"{k}-{base}"] = [round(float(np.mean([recs[n]["point"][k] - recs[n]["point"][base]
                                                                 for n in mem])), 4), [round(x, 4) for x in B.ci(db)]]
        res["groups"][ty] = g
        print(ty, g["chosen"], g["mean"][g["chosen"]], "vs elev", g["delta"].get(f"{g['chosen']}-elev"), flush=True)
    json.dump(res, open(os.path.join(OUT, "dev_report_r2.json"), "w"), indent=1)
    return 0


def main(argv=None):
    step = (argv or sys.argv[1:])[0]
    return {"cv": run_cv, "choose": choose, "report": report}[step]()


if __name__ == "__main__":
    sys.exit(main())
