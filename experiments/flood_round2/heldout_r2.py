"""
flood_round2 held-out pass (PREREGISTRATION_ROUND2.md). It runs once.

    python -m experiments.flood_round2.heldout_r2 build    # references, inputs, tables, round-2 features (reserved units)
    python -m experiments.flood_round2.heldout_r2 score    # every candidate once; writes results/heldout_r2.json (mode x)

Both steps refuse to run unless:
- the pre-registration hash matches PREREG_HASH_ROUND2.txt;
- the tag flood-round2-heldout-freeze exists and equals HEAD;
- results/method_choice_r2.json is committed at the tag.

`score` also refuses if heldout_r2.json exists.

Building reuses flood_final.heldout_pass (round 4's references, the same input code, a killable subprocess per unit, 3 tries, the pluvial module's inputs within 1 h), with this round's caches and reserved units.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import subprocess
import sys
import time

import numpy as np

from experiments.flood_final import heldout_pass as HP

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
PREREG = os.path.join(HERE, "PREREGISTRATION_ROUND2.md")
HASHFILE = os.path.join(HERE, "PREREG_HASH_ROUND2.txt")
FREEZE_TAG = "flood-round2-heldout-freeze"
CACHE = os.path.expanduser("~/.cache/geowatch/flood_round2/heldout")
TABLES_R2 = os.path.join(CACHE, "tables_r2")
# PREREGISTRATION_ROUND2 §6.3 (R12): a verdict needs >= 5 qualifying units in >= 3 clusters
MIN_UNITS, MIN_CLUSTERS = 5, 3


def _git(*a):
    return subprocess.run(["git", *a], cwd=HERE, capture_output=True, text=True).stdout.strip()


def preflight(scoring: bool) -> dict:
    sha = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    want = next(l.split()[-1] for l in open(HASHFILE) if l.startswith("sha256:"))
    if sha != want:
        raise SystemExit(f"PREREGISTRATION_ROUND2.md sha256 {sha} != {want}")
    tag = _git("rev-list", "-n", "1", FREEZE_TAG)
    if not tag:
        raise SystemExit(f"tag {FREEZE_TAG} missing: freeze first")
    if _git("rev-parse", "HEAD") != tag:
        raise SystemExit(f"HEAD is not {FREEZE_TAG}")
    if not _git("ls-tree", tag, "--", "results/method_choice_r2.json"):
        raise SystemExit("results/method_choice_r2.json not committed at the tag")
    if scoring and os.path.exists(os.path.join(OUT, "heldout_r2.json")):
        raise SystemExit("results/heldout_r2.json exists: the held-out pass has run; no re-runs")
    return {"prereg_sha256": sha, "freeze_commit": tag}


def reserved_units():
    from experiments.flood_core.registry import registry as REG
    reg = REG.load()
    return [u for u in reg["units"] if u["role"] == "reserved"
            and any(x.get("round") == "flood_round2" for x in u.get("uses", []))]


def _patch():
    HP.CACHE = CACHE
    HP.REF_DIR = os.path.join(CACHE, "refs")
    HP.LOG = os.path.join(CACHE, "build_log.json")
    HP.reserved_units = reserved_units

    def _sub(arg, name, limit):
        try:
            r = subprocess.run([sys.executable, "-m", "experiments.flood_round2.heldout_r2", arg, name],
                               timeout=limit, capture_output=True, text=True)
            return r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-3:]
        except subprocess.TimeoutExpired:
            return False, [f"killed after {limit} s"]
    HP._subprocess = _sub


def features():
    from experiments.flood_round2 import features_r2 as R
    R.SRC_TABLES = [os.path.join(CACHE, "tables")]
    R.SRC_INPUTS = [os.path.join(CACHE, "inputs")]
    R.CACHE = TABLES_R2
    out = {}
    for u in reserved_units():
        n = u["event_id"]
        if R._find(n, R.SRC_TABLES) is None:
            continue
        try:
            out[n] = R.build(n)
        except Exception as e:          # noqa: BLE001 -- recorded; the unit is then missing
            out[n] = {"error": f"{type(e).__name__}: {e}"[:300]}
    json.dump(out, open(os.path.join(CACHE, "features_log.json"), "w"), indent=1)
    return out


def build():
    preflight(scoring=False)
    _patch()
    HP.build_all()
    features()
    return 0


def _redact(x):
    """Error tails can carry absolute home paths (flood_final D22): replace the home directory with ~."""
    home = os.path.expanduser("~")
    return json.loads(json.dumps(x, default=str).replace(home, "~"))


def _comparators(t):
    from experiments.flood_learned import features as FT
    from experiments.flood_round2 import features_r2 as R
    C = {k: t["C"][:, i].astype(np.float64) for i, k in enumerate(FT.COMPARATORS)}
    C["elev"] = -t["X"][:, R.FEATURES_R2.index("elev_glo30")].astype(np.float64)
    # comparators are stored as scores (higher = more flood-prone); HAND is already negated
    return C


def score():
    from experiments.flood_baselines import blocks as B
    from experiments.flood_baselines import score as BS
    from experiments.flood_learned import evaluate as EV
    from experiments.flood_round2 import features_r2 as R
    from experiments.flood_round2 import model_v3 as V
    from experiments.flood_validation.harness import MIN_DRY_CELLS, MIN_FLOODED_CELLS
    from sklearn.metrics import average_precision_score
    pre = preflight(scoring=True)
    choice = json.load(open(os.path.join(OUT, "method_choice_r2.json")))
    finals = {}
    for c, f in choice["final_models"].items():
        p = os.path.join(V.CACHE, f["path"])
        if hashlib.sha256(open(p, "rb").read()).hexdigest() != f["sha256"]:
            raise SystemExit(f"final model {c} hash mismatch")
        finals[c] = pickle.load(open(p, "rb"))
    log = json.load(open(os.path.join(CACHE, "build_log.json")))
    res = {"preflight": pre, "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "choice": {t: ch["chosen"] for t, ch in choice["choice"].items()},
           "units": {}, "missing": {}, "not_qualifying": {}, "groups": {}, "verdicts": {}}
    recs, cluster_of = {}, {}
    for u in reserved_units():
        n = u["event_id"]
        p = os.path.join(TABLES_R2, f"{n}.npz")
        if not os.path.exists(p):
            r = log.get(n, {})
            key = "not_qualifying" if "not_qualifying" in str(r.get("result")) else "missing"
            res[key][n] = _redact(r.get("result") or r.get("tail"))
            continue
        z = np.load(p, allow_pickle=False)
        t = {"X": z["X"], "C": z["C"], "y": z["y"], "meta": json.loads(str(z["meta"]))}
        shape, y = tuple(t["meta"]["shape"]), t["y"]
        if (y == 1).sum() < MIN_FLOODED_CELLS or (y == 0).sum() < MIN_DRY_CELLS:
            res["not_qualifying"][n] = [int((y == 1).sum()), int((y == 0).sum())]
            continue
        scores = _comparators(t)
        for c, fin in finals.items():
            raw = np.asarray(V.predict(c, fin["model"], t), np.float64)
            scores[c] = raw
            scores[f"{c}:calibrated"] = fin["isotonic"].predict(raw)
        ok = y >= 0
        need = [k for k in scores if k != "pluvial"]
        for k in need:
            ok &= np.isfinite(scores[k])
        use = {k: v.reshape(shape) for k, v in scores.items() if k != "pluvial" or np.isfinite(v[ok]).all()}
        pb = B.paired_block_bootstrap(use, (y == 1).reshape(shape), ok.reshape(shape), BS.BLOCK_CELLS, BS.REPS,
                                      BS._seed(n))
        yy = y[ok]
        rec = {"tags": u["flood_final"]["tags"], "region": u["flood_final"]["region"], "cluster": u["storm_cluster"],
               "flooded": int((yy == 1).sum()), "dry": int((yy == 0).sum()),
               "auc": {k: round(v, 4) for k, v in pb["point"].items()},
               "ci": {k: [None if x is None else round(x, 4) for x in B.ci(r)] for k, r in pb["reps"].items()},
               "ap": {k: round(float(average_precision_score(yy, v.ravel()[ok])), 4) for k, v in use.items()},
               "_reps": pb["reps"]}
        k_obs = int((yy == 1).sum())
        rec["iou_area_matched"] = {}
        for k, v in use.items():
            s = v.ravel()[ok]
            top = np.zeros(s.size, bool)
            top[np.argsort(-s, kind="stable")[:k_obs]] = True
            rec["iou_area_matched"][k] = round(float((top & (yy == 1)).sum() / max(1, (top | (yy == 1)).sum())), 4)
        recs[n], cluster_of[n] = rec, u["storm_cluster"]
    res["units"] = {n: {k: v for k, v in r.items() if k != "_reps"} for n, r in recs.items()}
    for ty in V.TYPES:
        mem = [n for n, r in recs.items() if ty in r["tags"]]
        if not mem:
            res["verdicts"][ty] = {"verdict": "not-run (insufficient)", "units": 0}
            continue
        keys = sorted({k for n in mem for k in recs[n]["auc"]})
        g = {"units": mem, "clusters": len({cluster_of[n] for n in mem}), "mean_auc": {}, "delta": {}}
        for k in keys:
            have = [n for n in mem if k in recs[n]["auc"]]
            boot = B.cluster_mean_bootstrap({n: np.asarray(recs[n]["_reps"][k]) for n in have}, cluster_of, BS.REPS, BS.SEED)
            g["mean_auc"][k] = {"mean": round(float(np.mean([recs[n]["auc"][k] for n in have])), 4),
                                "ci": [round(x, 4) for x in B.ci(boot)], "n": len(have)}
            for base in ("hand", "elev"):
                if k == base:
                    continue
                db = B.cluster_mean_bootstrap({n: np.asarray(recs[n]["_reps"][k]) - np.asarray(recs[n]["_reps"][base])
                                               for n in have}, cluster_of, BS.REPS, BS.SEED)
                g["delta"][f"{k}-{base}"] = {"mean": round(float(np.mean([recs[n]["auc"][k] - recs[n]["auc"][base]
                                                                          for n in have])), 4),
                                             "ci": [round(x, 4) for x in B.ci(db)]}
        res["groups"][ty] = g
        chosen = res["choice"].get(ty)
        n_cl = g["clusters"]
        if chosen is None or len(mem) < MIN_UNITS or n_cl < MIN_CLUSTERS:
            res["verdicts"][ty] = {"chosen": chosen, "verdict": "not-run (insufficient)", "units": len(mem), "clusters": n_cl}
            continue
        # PREREGISTRATION_ROUND2 §6: vs the stronger of {hand, elev} on these units (the other one if chosen is a baseline)
        bases = [b for b in ("hand", "elev") if b != chosen]
        strong = max(bases, key=lambda b: g["mean_auc"][b]["mean"])
        d = g["delta"][f"{chosen}-{strong}"]
        m = g["mean_auc"][chosen]["mean"]
        res["verdicts"][ty] = {"chosen": chosen, "verdict": "passed" if (m >= 0.70 and d["ci"][0] > 0) else "failed",
                               "mean_auc": m, "vs": strong, "delta": d, "units": len(mem), "clusters": n_cl}
    res["calibration"] = {}
    for c, fin in finals.items():
        tabs = {}
        preds = {}
        for n in recs:
            z = np.load(os.path.join(TABLES_R2, f"{n}.npz"), allow_pickle=False)
            t = {"X": z["X"], "C": z["C"], "y": z["y"], "meta": json.loads(str(z["meta"]))}
            tabs[n] = t
            preds[n] = fin["isotonic"].predict(np.asarray(V.predict(c, fin["model"], t), np.float64))
        res["calibration"][c] = EV.calibration(tabs, preds, cluster_of, list(recs))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "heldout_r2.json"), "x") as fh:
        json.dump(res, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    for k, v in res["verdicts"].items():
        print(k, json.dumps(v)[:300])
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    if a[0] in ("--build-one", "--pluvial-one"):
        _patch()
        return HP.main(a)
    return {"build": build, "score": score}[a[0]]()


if __name__ == "__main__":
    sys.exit(main())
