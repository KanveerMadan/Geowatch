"""
The learned flood model: LightGBM (primary) and logistic regression (sanity
check), cross-validated by event cluster and by region, never by pixel.

    python -m experiments.flood_learned.model           # every split x variant

Training rows: the labelled cells (1 flooded, 0 dry) of the training events;
unobserved cells (-1) are never used, as dry or otherwise. Each training
event carries the same total weight, so a large or flood-heavy box does not
dominate; within an event every labelled cell weighs the same.

Hyperparameters are fixed in advance and NOT tuned on any held-out event:
  num_leaves 15, learning_rate 0.05, 300 trees, row subsample 0.7, column
  subsample 0.8, L2 1.0 -- the LightGBM documentation's "deal with
  over-fitting" direction (few leaves, large leaves, bagging) for a small
  number of independent units;
  min_child_samples 1089 = 33 x 33 cells: every leaf must be supported by at
  least one 990 m block's worth of cells (the flood indicator's measured
  correlation range, flood_baselines A2), so a leaf cannot fit one patch.
PARAM_SENSITIVITY reruns the primary split with a smaller and a larger
model; it is reported, never used to choose.

Predictions are made for EVERY cell of a held-out event's box (the map),
and cached per (split, variant) so a run resumes.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

from experiments.flood_learned import events as LE
from experiments.flood_learned import features as FT

PRED_CACHE = os.path.expanduser(os.environ.get("GEOWATCH_LEARNED_PREDS",
                                               "~/.cache/geowatch/flood_learned/preds"))
SEED = 20261118
LGBM_PARAMS = dict(objective="binary", n_estimators=300, learning_rate=0.05, num_leaves=15,
                   min_child_samples=33 * 33, subsample=0.7, subsample_freq=1,
                   colsample_bytree=0.8, reg_lambda=1.0, n_jobs=4, verbose=-1)
PARAM_SENSITIVITY = {
    "small": dict(num_leaves=7, n_estimators=150),
    "large": dict(num_leaves=31, n_estimators=600),
}
# logistic regression: C = 1 (sklearn's default; L2), on standardised features
LR_C = 1.0

_TERRAIN = FT.TERRAIN
MERIT = ("hand_merit", "log_upa_near", "log_upa_cell", "fluvial_score")
WATER = ("dist_water_m", "jrc_occurrence", "jrc_recurrence")
RAIN = ("rain_p999_mm_h", "rain_design_day_mm", "rain_annual_mm")
LAND = ("clay_pct", "wc_built", "wc_tree", "wc_shrub", "wc_grass", "wc_crop", "wc_bare",
        "wc_wetland", "wc_mangrove", "ndvi_pre")


def terrain(dem):
    return tuple(f"{t}_{dem}" for t in _TERRAIN)


FEATURE_SETS = {
    # the brief's list: FABDEM terrain, MERIT HAND/upa, fluvial score, water,
    # JRC occurrence + recurrence, rain extremes, clay, built-up, vegetation
    "full": terrain("fabdem") + MERIT + WATER + RAIN + LAND,
    # licence swaps (DEM only)
    "full_glo30": terrain("glo30") + MERIT + WATER + RAIN + LAND,
    "full_gedtm30": terrain("gedtm30") + MERIT + WATER + RAIN + LAND,
    # no FABDEM, no MERIT (so no HAND, upa or fluvial score): GLO-30 terrain,
    # the mapped-water HAND and HydroSHEDS accumulation instead
    "open": terrain("glo30") + ("log_hs_acc",) + WATER + RAIN + LAND,
    # ablations
    "no_rain": terrain("fabdem") + MERIT + WATER + LAND,
    "pre_water": terrain("fabdem") + MERIT + ("dist_water_m", "jrc_water_freq_pre") + RAIN + LAND,
    "hand_fluvial": ("hand_merit", "fluvial_score"),
    # added after the first evaluation showed WorldCover cropland as the top
    # feature (REPORT.md, "Feature importance"): how much skill is left
    # without land cover, and with terrain + hydrography + water history only
    "no_landcover": terrain("fabdem") + MERIT + WATER + RAIN + ("clay_pct", "ndvi_pre"),
    "terrain_water": terrain("fabdem") + MERIT + WATER,
}


def load_tables(names):
    return {n: FT.load(n) for n in names}


def columns(variant: str) -> list:
    return [FT.FEATURES.index(f) for f in FEATURE_SETS[variant]]


def training_rows(tables: dict, train: list, cols: list):
    Xs, ys, ws = [], [], []
    for n in train:
        t = tables[n]
        m = t["y"] >= 0
        Xs.append(t["X"][m][:, cols])
        ys.append(t["y"][m].astype(np.int8))
        ws.append(np.full(int(m.sum()), 1.0 / m.sum()))
    w = np.concatenate(ws)
    return np.concatenate(Xs), np.concatenate(ys), w * (w.size / w.sum())


def fit_lgbm(X, y, w, overrides=None, seed=SEED):
    import lightgbm as lgb
    p = {**LGBM_PARAMS, **(overrides or {}), "random_state": seed}
    return lgb.LGBMClassifier(**p).fit(X, y, sample_weight=w)


class LogReg:
    """Median imputation + missing indicators, standardisation, L2 logistic."""

    def __init__(self, C=LR_C):
        self.C = C

    def fit(self, X, y, w):
        from sklearn.linear_model import LogisticRegression
        X = np.asarray(X, np.float64)
        self.med = np.nanmedian(X, axis=0)
        self.med = np.where(np.isfinite(self.med), self.med, 0.0)
        self.miss_cols = np.flatnonzero(np.isnan(X).any(axis=0))
        Z = self._z(X, fit=True)
        self.m = LogisticRegression(C=self.C, max_iter=5000).fit(Z, y, sample_weight=w)
        return self

    def _z(self, X, fit=False):
        X = np.asarray(X, np.float64)
        miss = np.isnan(X[:, self.miss_cols]).astype(np.float64)
        Xf = np.where(np.isnan(X), self.med, X)
        if fit:
            self.mu, self.sd = Xf.mean(0), Xf.std(0)
            self.sd = np.where(self.sd > 0, self.sd, 1.0)
        return np.hstack([(Xf - self.mu) / self.sd, miss])

    def predict_proba(self, X):
        return self.m.predict_proba(self._z(X))


def folds(names: list, split: str, cluster_of: dict) -> dict:
    """{fold id: held-out names}. lco = registry cluster, lro = region."""
    key = (lambda n: f"c{cluster_of[n]}") if split == "lco" else LE.region
    out = {}
    for n in names:
        out.setdefault(key(n), []).append(n)
    return out


def cv_predict(tables, names, split, variant, cluster_of, model="lgbm", overrides=None,
               train_subset=None, seed=SEED):
    """{event: p over every box cell} from the fold that held the event out.
    train_subset(fold_train_names, rng) -> names: optional learning-curve hook."""
    cols = columns(variant)
    out, info = {}, {}
    rng = np.random.default_rng(seed)
    for fid, held in sorted(folds(names, split, cluster_of).items()):
        train = [n for n in names if n not in held]
        if train_subset is not None:
            train = train_subset(train, rng)
        X, y, w = training_rows(tables, train, cols)
        t0 = time.time()
        m = (fit_lgbm(X, y, w, overrides, seed) if model == "lgbm" else LogReg().fit(X, y, w))
        info[fid] = {"held_out": held, "n_train_events": len(train), "n_train_rows": int(y.size),
                     "train_prevalence_weighted": float(np.sum(w * y) / np.sum(w)),
                     "fit_s": round(time.time() - t0, 1)}
        if model == "lgbm":
            info[fid]["gain"] = dict(zip(FEATURE_SETS[variant],
                                         m.booster_.feature_importance("gain").tolist()))
        for n in held:
            out[n] = m.predict_proba(tables[n]["X"][:, cols])[:, 1].astype(np.float32)
    return out, info


def pred_path(tag):
    return os.path.join(PRED_CACHE, f"{tag}.npz")


def save_preds(tag, preds, info):
    os.makedirs(PRED_CACHE, exist_ok=True)
    tmp = pred_path(tag) + f".tmp{os.getpid()}.npz"
    np.savez_compressed(tmp, **preds, _info=np.array(json.dumps(info, default=str)))
    os.replace(tmp, pred_path(tag))


def load_preds(tag):
    z = np.load(pred_path(tag), allow_pickle=False)
    return ({k: z[k] for k in z.files if k != "_info"}, json.loads(str(z["_info"])))


def runs(available_variants):
    """(tag, split, variant, model, overrides) for every planned run."""
    r = []
    for split in ("lco", "lro"):
        r.append((f"{split}__full__lgbm", split, "full", "lgbm", None))
        r.append((f"{split}__full__logreg", split, "full", "logreg", None))
        r.append((f"{split}__open__lgbm", split, "open", "lgbm", None))
    r.append(("lro__no_landcover__lgbm", "lro", "no_landcover", "lgbm", None))
    for v in ("full_glo30", "full_gedtm30", "no_rain", "pre_water", "hand_fluvial",
              "no_landcover", "terrain_water"):
        if v in available_variants:
            r.append((f"lco__{v}__lgbm", "lco", v, "lgbm", None))
    r.append(("lco__open__logreg", "lco", "open", "logreg", None))
    for k, o in PARAM_SENSITIVITY.items():
        r.append((f"lco__full__lgbm_{k}", "lco", "full", "lgbm", o))
    return r


def gedtm30_available(tables) -> bool:
    i = FT.FEATURES.index("relmin2km_gedtm30")
    return all(np.isfinite(t["X"][:, i]).any() for t in tables.values())


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="run tags")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    names = [c["unit"] for c in LE.batch0() if os.path.exists(FT.path(c["unit"]))]
    cluster_of = LE.clusters(names)
    LE.check_folds(names, cluster_of)
    tables = load_tables(names)
    avail = set(FEATURE_SETS) - (set() if gedtm30_available(tables) else {"full_gedtm30"})
    print(f"{len(names)} events, {len(set(cluster_of.values()))} clusters; "
          f"variants {sorted(avail)}", flush=True)
    for tag, split, variant, model, over in runs(avail):
        if args.only and tag not in args.only:
            continue
        if os.path.exists(pred_path(tag)) and not args.force:
            print(f"── {tag}: cached", flush=True)
            continue
        t0 = time.time()
        preds, info = cv_predict(tables, names, split, variant, cluster_of, model, over)
        save_preds(tag, preds, {"split": split, "variant": variant, "model": model,
                                "overrides": over, "folds": info,
                                "features": list(FEATURE_SETS[variant])})
        print(f"── {tag}: {len(info)} folds in {time.time() - t0:.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
