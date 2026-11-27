"""
Round 3 (R34): the same DEV comparison as `dev_cv_r3 cv <types>`, run lean and checkpointed.

Why: on the 8 GB machine `dev_cv_r3 cv flash_flood,waterlogging` held every unit's full table in RAM
(float64 copies; 311 units each carried a copy of their box's table) and swapped. It ran 10 h
for 1 of 5 models (R34).

The method is unchanged: the same candidates, feature lists, folds, lambda grid, row subsample and seeds as
model_r3, the same choice rule and the same scorer (model_r3.gain_lower_bound). The engineering changes:
- per unit, only the columns the needed candidates use are kept, as a float32 .npy on disk (memory-mapped).
  The tables are float32 already, so nothing is lost. The training subsample is held in RAM once.
- inner leave-region-out fits are shared. Outer fold A's inner fold B trains on "all regions except A and B",
  the same rows in the same order as outer B's inner fold A. Each region pair is fitted once (C(R,2)+R fits per
  candidate instead of R^2).
- every fit, outer prediction and (type, candidate) score is saved as it finishes, so a restart skips work done.

    python -m experiments.flood_round3.cv_lean flash_flood,waterlogging
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time

import numpy as np

from experiments.flood_round3 import dev_cv_r3 as D
from experiments.flood_round3 import model_r3 as M

CK = os.path.join(D.BIG, "cvlean")


def _log(*a):
    print(time.strftime("%F %T"), *a, flush=True)


def _fam(ty):
    return "flash_flood" if ty == "flash_flood" else "coastal" if ty in ("coastal", "compound") else "fluvial"


def needed(types):
    """Candidate keys per type, exactly as dev_cv_r3.cv builds them."""
    need, cands = [], {}
    for ty in types:
        fam = _fam(ty)
        c = {"elev": "elev", "hand": "hand", "elev_hand_lr": "elev_hand_lr", "anc_elev_lgbm": f"anc_elev_lgbm@{fam}"}
        if ty in D.RIVER_LED:
            c["anc_elev_lgbm_ev"] = "anc_elev_lgbm_ev@fluvial"
        if ty in D.FINE_TYPES:
            c["anc_elev_lgbm_fine"] = "anc_elev_lgbm_fine@fluvial"
        if ty in D.MRMS_TYPES:
            c["anc_elev_lgbm_mrms"] = "anc_elev_lgbm_mrms@flash_flood"
        if ty in D.WL_TYPES:
            c["anc_elev_lgbm_wl"] = "anc_elev_lgbm_wl@fluvial"
        cands[ty] = c
        need += [k for k in c.values() if "@" in k and k not in need]
    return need, cands


def _units():
    """(name, table path, label source, meta) in dev_cv_r3.load_tables order, with the same filters."""
    cat = json.load(open(os.path.join(D.OUT, "burned_catalog.json")))
    p1 = os.path.join(D.OUT, "s1route_catalog.json")
    if os.path.exists(p1):
        cat.update(json.load(open(p1)))
    for f in sorted(os.listdir(D.TABLES)):
        n = f[:-4]
        if n in cat:
            yield n, os.path.join(D.TABLES, f), None, {"tags": cat[n]["tags"], "region": cat[n]["region"],
                                                        "cluster": cat[n]["cluster"]}
    from experiments.flood_round3 import rain311 as R3
    p = os.path.join(R3.REFS, "units.json")
    if os.path.exists(p):
        for n, u in json.load(open(p)).items():
            tp = os.path.join(D.TABLES, f"{u['box']}.npz")
            if os.path.exists(tp):
                yield n, tp, os.path.join(R3.REFS, f"{n}.npz"), {
                    "tags": [u.get("type", "pluvial")], "region": f"r311_{u.get('city', n.split('_')[1])}",
                    "cluster": u["cluster"]}


def load(types):
    """Lite tables: y, shape, elev column, hand score, the training subsample of the needed columns (RAM), and the
    full needed columns as a memory-mapped float32 .npy."""
    need, cands = needed(types)
    os.makedirs(os.path.join(CK, "D"), exist_ok=True)
    tabs, F0, U = {}, None, None
    for n, tp, lp, info in _units():
        z = np.load(tp, allow_pickle=False)
        m = json.loads(str(z["meta"]))
        if lp is None:
            y = z["y"]
            if (y == 1).sum() < 50 or (y == 0).sum() < 50:
                continue
        else:
            y = np.load(lp)["y3"].ravel().astype(np.int8)
            if len(y) != len(z["y"]):
                raise ValueError(f"{n}: label cells {len(y)} != table cells {len(z['y'])}")
            y = np.where(np.isin(y, (0, 1)), y, -1).astype(np.int8)
            if (y == 1).sum() < 50 or (y == 0).sum() < 50:
                continue
        F = list(m["features"])
        if U is None:                      # dev_cv_r3 takes the family lists against the first unit's features
            F0 = F
            U = []
            for k in need:
                for f in feats_of(k, F0):
                    if f not in U:
                        U.append(f)
        dp = os.path.join(CK, "D", f"{n}.npy")
        if not os.path.exists(dp):
            ev = {}
            if lp is None:
                p = os.path.join(D.EV, f"{n}.npz")
                if os.path.exists(p):
                    e = np.load(p)
                    ev = {k: e[k] for k in D.EV_FEATS}
            ev.update(D._extra(n, y))
            cols = []
            for f in U:
                if f in F:
                    cols.append(z["X"][:, F.index(f)].astype(np.float32))
                elif f in ev:
                    cols.append(np.asarray(ev[f], np.float32))
                else:                      # EV_FEATS on units without river features: NaN, as dev_cv_r3
                    cols.append(np.full(len(y), np.nan, np.float32))
            np.save(dp + ".tmp.npy", np.stack(cols, axis=1))
            os.replace(dp + ".tmp.npy", dp)
        t = {"X": z["X"][:, [F.index("elev_glo30")]].copy(), "F": ["elev_glo30"], "C": z["C"][:, :1].copy(),
             "y": y, "shape": tuple(m["shape"]), **info}
        t["D"] = np.load(dp, mmap_mode="r")
        t["ok"] = M._train_idx(t)
        t["Dtr"] = np.ascontiguousarray(t["D"][t["ok"]])
        tabs[n] = t
        del z
    return tabs, U, need, cands, F0


def feats_of(key, F0):
    base, fam = key.split("@")
    feats = [f for f in D.family(fam) if f in F0]
    extra = {"anc_elev_lgbm": [], "anc_elev_lgbm_ev": list(D.EV_FEATS), "anc_elev_lgbm_fine": list(D._fine()),
             "anc_elev_lgbm_mrms": list(D._mrms()), "anc_elev_lgbm_wl": list(D._wl())}[base]
    return feats + extra


def fit(tabs, names, idx, params, seed=20261122):
    """model_r3.fit_anchored on the cached rows (same rows, order, weights, base and LightGBM settings)."""
    import lightgbm as lgb
    from sklearn.linear_model import LogisticRegression
    A, y, w = M._rows(tabs, names, lambda t: M._pct_within(M.anchor_score(t, "elev"))[:, None])
    base = LogisticRegression(C=1.0, max_iter=2000).fit(np.nan_to_num(A, nan=0.5), y, sample_weight=w)
    X = np.concatenate([tabs[n]["Dtr"][:, idx] for n in names])
    mono = [M.MONOTONE.get(f, 0) for f in idx_names(idx)]
    m = lgb.LGBMClassifier(**{**params, "random_state": seed, "monotone_constraints": mono,
                              "monotone_constraints_method": "advanced", "verbose": -1})
    m.fit(X, y, sample_weight=w, init_score=base.decision_function(np.nan_to_num(A, nan=0.5)))
    del X
    return {"base": base, "lgbm": m}


_NAMES = {}


def idx_names(idx):
    return [_NAMES["U"][i] for i in idx]


def parts(model, t, idx):
    a = M._pct_within(M.anchor_score(t, "elev"))[:, None]
    b = model["base"].decision_function(np.nan_to_num(a, nan=0.5))
    f = model["lgbm"].predict(np.asarray(t["D"][:, idx]), raw_score=True)
    return b, f


def run_candidate(tabs, names, region, key, U, F0, params):
    """Outer leave-region-out predictions with the inner lambda choice, checkpointed per fit."""
    ck = os.path.join(CK, key.replace("@", "__"))
    os.makedirs(ck, exist_ok=True)
    feats = feats_of(key, F0)
    idx = [U.index(f) for f in feats]
    folds = {}
    for n in names:
        folds.setdefault(region[n], []).append(n)
    regs = sorted(folds)
    # inner fits: one per region pair; held AUCs per lambda for the units of both regions
    for a, b in itertools.combinations(regs, 2):
        p = os.path.join(ck, f"pair__{a}__{b}.json")
        if os.path.exists(p):
            continue
        t0 = time.time()
        tr = [n for n in names if region[n] not in (a, b)]
        m = fit(tabs, tr, idx, params)
        aucs = {}
        for n in folds[a] + folds[b]:
            bb, ff = parts(m, tabs[n], idx)
            aucs[n] = [M.within_auc(bb + lam * ff, tabs[n]["y"]) for lam in M.LAMBDAS]
        json.dump(aucs, open(p + f".{os.getpid()}.tmp", "w"))
        os.replace(p + f".{os.getpid()}.tmp", p)
        _log(key, "pair", a, b, f"{time.time() - t0:.0f}s")
    pred, lams = {}, {}
    for o in regs:
        p = os.path.join(ck, f"outer__{o}.npz")
        inner = [r for r in regs if r != o]
        if len(inner) < 2:
            lam = 0.0
        else:
            scores = {lam: [] for lam in M.LAMBDAS}
            for i in inner:                  # the order of model_r3.choose_lambda: inner folds sorted, held units
                a, b = sorted((o, i))
                aucs = json.load(open(os.path.join(ck, f"pair__{a}__{b}.json")))
                for n in folds[i]:
                    for j, lam in enumerate(M.LAMBDAS):
                        scores[lam].append(aucs[n][j])
            mean = {lam: float(np.mean(v)) for lam, v in scores.items()}
            lam = max(M.LAMBDAS, key=lambda x: (round(mean[x], 4), -x))
        lams[o] = lam
        if not os.path.exists(p):
            t0 = time.time()
            m = fit(tabs, [n for n in names if region[n] != o], idx, params)
            out = {}
            for n in folds[o]:
                bb, ff = parts(m, tabs[n], idx)
                out[n] = (bb + lam * ff).astype(np.float32)
            np.savez(p + f".{os.getpid()}.tmp.npz", **out)
            os.replace(p + f".{os.getpid()}.tmp.npz", p)
            _log(key, "outer", o, "lambda", lam, f"{time.time() - t0:.0f}s")
        z = np.load(p)
        pred.update({n: z[n] for n in z.files})
    return pred, lams


def lr_pred(tabs, names, region):
    p = os.path.join(CK, "elev_hand_lr.npz")
    if os.path.exists(p):
        z = np.load(p)
        return {n: z[n] for n in z.files}
    folds = {}
    for n in names:
        folds.setdefault(region[n], []).append(n)
    out = {}
    for _, held in sorted(folds.items()):
        out.update(D._lr_pred(tabs, [n for n in names if n not in held], held))
    np.savez(p + f".{os.getpid()}.tmp.npz", **out)
    os.replace(p + f".{os.getpid()}.tmp.npz", p)
    return out


def main(argv=None):
    from experiments.flood_learned.model import LGBM_PARAMS
    types = (argv or sys.argv[1:])[0].split(",")
    params = {k: v for k, v in LGBM_PARAMS.items() if k not in ("verbose",)}
    tabs, U, need, cands, F0 = load(types)
    _NAMES["U"] = U
    names = sorted(tabs)
    region = {n: tabs[n]["region"] for n in names}
    cluster = {n: tabs[n]["cluster"] for n in names}
    _log("loaded", len(names), "units,", len(set(region.values())), "regions,", len(U), "columns; candidates", need)
    runs = {"elev": {n: M.anchor_score(tabs[n], "elev") for n in names},
            "hand": {n: M.anchor_score(tabs[n], "hand") for n in names},
            "elev_hand_lr": lr_pred(tabs, names, region)}
    lams = {}
    for key in need:
        runs[key], lams[key] = run_candidate(tabs, names, region, key, U, F0, params)
        _log(key, "done", lams[key])
    res = {"units": {ty: [n for n in names if ty in tabs[n]["tags"]] for ty in D.TYPES}, "lambdas": lams, "by_type": {}}
    prev_p = os.path.join(D.OUT, "dev_cv_r3.json")
    if os.path.exists(prev_p):
        prev = json.load(open(prev_p))
        res["by_type"] = {k: v for k, v in prev.get("by_type", {}).items() if k not in types}
        res["lambdas"] = {**prev.get("lambdas", {}), **lams}
    for ty in types:
        mem = res["units"][ty]
        if len(mem) < 3:
            res["by_type"][ty] = {"units": len(mem)}
            continue
        out = {}
        for c, k in cands[ty].items():
            p = os.path.join(CK, f"score__{ty}__{c}.json")
            if not os.path.exists(p):
                sub = {"elev": runs["elev"], "hand": runs["hand"], c: runs[k]}
                json.dump(M.gain_lower_bound(tabs, mem, {n: cluster[n] for n in mem}, sub, c), open(p, "w"))
            out[c] = json.load(open(p))
            _log(ty, c, out[c])
        best = M.choose(out, list(cands[ty]))
        res["by_type"][ty] = {"units": len(mem), "clusters": len({cluster[n] for n in mem}), "candidates": out,
                              "chosen": best}
        _log(ty, len(mem), best, json.dumps(out[best]))
    res["run"] = "cv_lean (R34): same method as dev_cv_r3.cv, lean and checkpointed"
    M.save(res, prev_p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
