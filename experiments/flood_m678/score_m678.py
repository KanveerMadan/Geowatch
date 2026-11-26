"""
M6–M8 one-shot reserve test (PREREGISTRATION_M678.md). Run once, after the freeze tag.

    cd ~/gw-r3pin && PYTHONPATH=.:$HOME/gw-m678/experiments/flood_m678 python -B -m score_m678 freeze   # at freeze: fit + save chosen learned models on all DEV
    ... python -B -m score_m678 test                                                                 # after the reserve is built: score once -> results/test_m678.json

The bar (unchanged from round 3), per type:
- within-event AUC, the 990 m blocked bootstrap (model_r3.gain_lower_bound, flood_baselines scorer);
- the method's gain over the better of elevation and HAND must have a 95 % lower bound > 0
  (a baseline method is compared with the other baseline, round 3's convention);
- mean AUC >= 0.70;
- >= 5 usable independent clusters (a unit is usable with >= 50 flooded and >= 50 dry cells).
Verdicts: pass | fail | too_few_events. Every dropout is listed with its reason; none is replaced.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
FROZEN = os.path.join(OUT, "frozen_models")
CHOSEN_P = os.path.join(OUT, "chosen_methods.json")
MIN_CLUSTERS, MIN_AUC = 5, 0.70
TYPE_OF = {"M6": "M6", "M7": "M7", "M8": "M8"}


def _features_for(method):
    import dev_cv_m678 as D
    from experiments.flood_round3 import dev_cv_r3 as R3
    full = None

    def fs(t):
        nonlocal full
        full = full or [f for f in R3.family("fluvial") if f in t["F"]]
        return {"anc_elev_lgbm": full, "anc_elev_lgbm_ev": full + list(D.EV_FEATS),
                "anc_elev_lgbm_main": full + list(D.EV_FEATS) + list(D.MAIN_FEATS)}[method]
    return fs


def freeze():
    """Fit each type's chosen learned method on ALL DEV units (lambda by inner leave-cluster-out CV,
    model_r3.choose_lambda) and save it with its hash. Baselines and physics need no fit."""
    import dev_cv_m678 as D
    from experiments.flood_learned.model import LGBM_PARAMS
    from experiments.flood_round3 import dev_cv_r3 as R3
    from experiments.flood_round3 import model_r3 as M
    chosen = json.load(open(CHOSEN_P))["chosen"]
    tabs = D.load_tables("dev")
    names = sorted(tabs)
    region = {n: tabs[n]["cluster"] for n in names}
    params = {k: v for k, v in LGBM_PARAMS.items() if k != "verbose"}
    os.makedirs(FROZEN, exist_ok=True)
    hashes = {}
    for ty, method in sorted(chosen.items()):
        if method in ("elev", "hand", "phys_main", "phys_stage"):
            continue
        p = os.path.join(FROZEN, f"{ty}_{method}.pkl")
        if method == "elev_hand_lr":
            from sklearn.linear_model import LogisticRegression

            def X(t):
                return np.nan_to_num(np.c_[M._pct_within(M.anchor_score(t, "elev")), M._pct_within(M.anchor_score(t, "hand"))], nan=0.5)
            A, y, w = M._rows(tabs, names, X)
            obj = {"kind": "lr", "model": LogisticRegression(max_iter=2000).fit(A, y, sample_weight=w)}
        else:
            feats = _features_for(method)(tabs[names[0]])
            lam, _ = M.choose_lambda(tabs, names, region, feats, "elev", params)
            obj = {"kind": "anchored", "model": M.fit_anchored(tabs, names, feats, "elev", params), "lambda": lam}
        pickle.dump(obj, open(p, "wb"))
        hashes[os.path.basename(p)] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    json.dump(hashes, open(os.path.join(FROZEN, "SHA256.json"), "w"), indent=1, sort_keys=True)
    print(json.dumps(hashes))
    _ = R3
    return 0


def predict(method, ty, t):
    from experiments.flood_round3 import model_r3 as M
    if method in ("elev", "hand"):
        return M.anchor_score(t, method)
    if method in ("phys_main", "phys_stage"):
        return np.asarray(t["ev"][method], np.float64)
    obj = pickle.load(open(os.path.join(FROZEN, f"{ty}_{method}.pkl"), "rb"))
    if obj["kind"] == "lr":
        X = np.nan_to_num(np.c_[M._pct_within(M.anchor_score(t, "elev")), M._pct_within(M.anchor_score(t, "hand"))], nan=0.5)
        return obj["model"].decision_function(X)
    return M.predict(obj["model"], t, obj["lambda"])


def verify_frozen():
    p = os.path.join(FROZEN, "SHA256.json")
    if not os.path.exists(p):
        return
    for f, h in json.load(open(p)).items():
        if hashlib.sha256(open(os.path.join(FROZEN, f), "rb").read()).hexdigest() != h:
            raise SystemExit(f"frozen model {f} changed after the freeze")


def test():
    import dev_cv_m678 as D
    import labels_m678 as LM
    from experiments.flood_round3 import model_r3 as M
    if os.path.exists(os.path.join(OUT, "test_m678.json")):
        raise SystemExit("the reserve has already been scored once; results/test_m678.json exists")
    verify_frozen()
    chosen = json.load(open(CHOSEN_P))["chosen"]
    recs = {r["incident"]: r for r in LM.records("reserve")}
    tabs = D.load_tables("reserve")
    res = {"by_type": {}, "chosen": chosen}
    for ty in ("M6", "M7", "M8"):
        mine = {n: r for n, r in recs.items() if r["type"] == ty}
        drop = {}
        for n in mine:
            if n not in tabs:
                rp = os.path.join(LM.REFS, f"{n}.npz")
                if os.path.exists(rp):
                    m = json.loads(str(np.load(rp, allow_pickle=False)["meta"]))
                    drop[n] = m.get("dropout") or f"{m.get('flooded_cells')} flooded / {m.get('dry_cells')} dry (< 50)"
                else:
                    drop[n] = "no label built"
        mem = sorted(n for n in tabs if tabs[n]["tags"][0] == ty)
        clusters = sorted({tabs[n]["cluster"] for n in mem})
        method = chosen[ty]
        out = {"method": method, "units": len(mem), "clusters": len(clusters), "cluster_ids": clusters,
               "dropouts": drop, "incidents": len(mine)}
        if len(clusters) < MIN_CLUSTERS:
            out.update(verdict="too_few_events",
                       reason=f"only {len(clusters)} usable independent events (clusters) of the {MIN_CLUSTERS} the bar needs")
        if len(clusters) >= 2:
            runs = {"elev": {n: M.anchor_score(tabs[n], "elev") for n in mem},
                    "hand": {n: M.anchor_score(tabs[n], "hand") for n in mem}}
            runs[method] = {n: predict(method, ty, tabs[n]) for n in mem}
            g = M.gain_lower_bound(tabs, mem, {n: tabs[n]["cluster"] for n in mem}, runs, method)
            out.update(score=g, per_unit={n: {k: round(M.within_auc(runs[k][n], tabs[n]["y"]), 4) for k in runs} for n in mem})
            if "verdict" not in out:
                ok = g["ci"][0] > 0 and g["mean_auc"] >= MIN_AUC
                out["verdict"] = "pass" if ok else "fail"
                if not ok:
                    why = []
                    if g["ci"][0] <= 0:
                        why.append(f"gain over {g['vs']} {g['gain']:+.3f}, 95 % CI [{g['ci'][0]:+.3f}, {g['ci'][1]:+.3f}] includes 0")
                    if g["mean_auc"] < MIN_AUC:
                        why.append(f"mean AUC {g['mean_auc']:.3f} < {MIN_AUC}")
                    out["reason"] = "; ".join(why)
                else:
                    out["scope"] = f"{len(clusters)} held-out events: " + ", ".join(clusters)
        res["by_type"][ty] = out
        print(ty, json.dumps({k: out.get(k) for k in ("verdict", "clusters", "reason")}), flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "test_m678.json"), "w"), indent=1, default=str)
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    return {"freeze": freeze, "test": test}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
