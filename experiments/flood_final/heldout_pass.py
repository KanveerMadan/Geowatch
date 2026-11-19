"""
Phase 7: the ONE held-out pass (PREREGISTRATION.md §8).

    python -m experiments.flood_final.heldout_pass build     # references + inputs of every RESERVED unit
    python -m experiments.flood_final.heldout_pass score     # writes results/heldout.json once

Refuses to run unless:
  * PREREGISTRATION.md's SHA256 equals PREREG_HASH.txt's;
  * the git tag FREEZE_TAG exists and HEAD is that commit (code frozen);
  * results/method_choice.json is committed at that commit;
  * (score) results/heldout.json does not exist yet.
Each reserved unit is built in a killable subprocess, at most 3 tries; a unit
that does not build or does not qualify is reported missing / not qualifying,
never as zero or as a fail.
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

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
PREREG = os.path.join(HERE, "PREREGISTRATION.md")
HASHFILE = os.path.join(HERE, "PREREG_HASH.txt")
FREEZE_TAG = "flood-final-heldout-freeze"
CACHE = os.path.expanduser("~/.cache/geowatch/flood_final/heldout")
REF_DIR = os.path.join(CACHE, "refs")
LOG = os.path.join(CACHE, "build_log.json")
UNIT_KILL_S = 2 * 1800
PLUVIAL_KILL_S = 3600            # PREREGISTRATION §4: the pluvial module only where its inputs build within 1 h
MAX_TRIES = 3


def _git(*a):
    return subprocess.run(["git", *a], cwd=HERE, capture_output=True, text=True).stdout.strip()


def preflight(scoring: bool):
    sha = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    want = next(l.split()[-1] for l in open(HASHFILE) if l.startswith("sha256:"))
    if sha != want:
        raise SystemExit(f"PREREGISTRATION.md sha256 {sha} != PREREG_HASH.txt {want}")
    tag = _git("rev-list", "-n", "1", FREEZE_TAG)
    if not tag:
        raise SystemExit(f"tag {FREEZE_TAG} missing: freeze the code first")
    if _git("rev-parse", "HEAD") != tag:
        raise SystemExit(f"HEAD is not {FREEZE_TAG} ({tag})")
    if _git("ls-tree", tag, "--", "results/method_choice.json") == "":
        raise SystemExit("results/method_choice.json is not committed at the freeze tag")
    if scoring and os.path.exists(os.path.join(OUT, "heldout.json")):
        raise SystemExit("results/heldout.json exists: the held-out pass has run; no re-runs")
    return {"prereg_sha256": sha, "freeze_commit": tag}


def reserved_units():
    from experiments.flood_core.registry import registry as REG
    reg = REG.load()
    return [u for u in reg["units"] if u["role"] == "reserved"
            and any(x.get("round") == "flood_final" for x in u.get("uses", []))]


def _spec(u):
    from experiments.flood_validation import harness_round4 as H4
    r = u["flood_final"]["reference"]
    if r[0] == "ems":
        _, code, aoi, mon, typ = r
        return H4._ems(code, aoi, mon, u["date"], typ)
    _, lat, lon, date = r
    return H4._s1(lat, lon, date)


def build_reference(u) -> dict:
    """Round 4's place() + reference(), unchanged (PREREGISTRATION §3)."""
    from experiments.flood_validation import harness_round4 as H4
    from susceptibility.hydro_rasters import utm_grid
    name = u["event_id"]
    p = os.path.join(REF_DIR, f"{name}.npz")
    if os.path.exists(p):
        return json.loads(str(np.load(p)["meta"]))
    ev = H4.place(_spec(u))
    if ev.get("bbox") is None:
        meta = {"unit": name, "error": "no flood centre in the product / search square"}
        f = v = np.zeros((1, 1), bool)
    else:
        t, shape, crs = utm_grid(ev["bbox"])
        ref = H4._call(lambda: H4.reference(ev, t, shape, crs), f"ref {name}")
        f, v = ref["flooded"], ref["valid"]
        meta = {"unit": name, "event": u["date"], "bbox": ev["bbox"], "centre": ev.get("centre"),
                "grid": {"crs": crs, "transform": list(t)[:6], "shape": list(shape)},
                "reference": ref["meta"], "block": 1, "s1_pass": ev.get("s1_pass"),
                "flooded_cells": int((f & v).sum()), "dry_cells": int((~f & v).sum())}
    os.makedirs(REF_DIR, exist_ok=True)
    np.savez_compressed(p + ".tmp.npz", flooded=f, valid=v, meta=np.array(json.dumps(meta, default=str)))
    os.replace(p + ".tmp.npz", p)
    return meta


def build_one(name: str) -> dict:
    """Reference, flood_baselines inputs, learned layers, feature table (own caches)."""
    os.environ["GEOWATCH_BASELINE_CACHE"] = os.path.join(CACHE, "baseline_inputs")
    os.environ["GEOWATCH_LEARNED_CACHE"] = os.path.join(CACHE, "inputs")
    os.environ["GEOWATCH_LEARNED_TABLES"] = os.path.join(CACHE, "tables")
    from experiments.flood_baselines import build as BUILD
    from experiments.flood_baselines import score as BSCORE
    from experiments.flood_learned import features as FT
    from experiments.flood_learned import fetch as F
    u = next(x for x in reserved_units() if x["event_id"] == name)
    meta = build_reference(u)
    if "error" in meta:
        return {"missing": meta["error"]}
    from experiments.flood_validation.harness import MIN_DRY_CELLS, MIN_FLOODED_CELLS
    if meta["flooded_cells"] < MIN_FLOODED_CELLS or meta["dry_cells"] < MIN_DRY_CELLS:
        return {"not_qualifying": [meta["flooded_cells"], meta["dry_cells"]]}
    e = {"unit": name, "path": os.path.join(REF_DIR, f"{name}.npz"), "meta": meta,
         "round": "flood_final", "split": "reserved", "modules": [], "uses": []}
    if not os.path.exists(BUILD.path(name)):
        BUILD.save(name, BUILD.build_unit(e))
    if not os.path.exists(F.path(name)):
        F.save(name, *F.fetch_unit(e))
    if not os.path.exists(FT.path(name)):
        FT.save(name, FT.build_table(e, BSCORE.round4_chosen()))
    return {"built": True}


def pluvial_one(name: str) -> dict:
    """The pluvial module's inputs (flood_baselines.build.pluvial_inputs), then the table again."""
    os.environ["GEOWATCH_BASELINE_CACHE"] = os.path.join(CACHE, "baseline_inputs")
    os.environ["GEOWATCH_LEARNED_CACHE"] = os.path.join(CACHE, "inputs")
    os.environ["GEOWATCH_LEARNED_TABLES"] = os.path.join(CACHE, "tables")
    from experiments.flood_baselines import build as BUILD
    from experiments.flood_baselines import score as BSCORE
    from experiments.flood_learned import features as FT
    b = BUILD.load(name)
    m = b["meta"]
    if "pl_dem" not in b["arrays"]:
        b["arrays"].update(BUILD.pluvial_inputs(name, m["ref_year"], BUILD._affine(m),
                                                tuple(m["grid"]["shape"]), m["grid"]["crs"], m))
        BUILD.save(name, b)
    meta = json.loads(str(np.load(os.path.join(REF_DIR, f"{name}.npz"))["meta"]))
    e = {"unit": name, "path": os.path.join(REF_DIR, f"{name}.npz"), "meta": meta,
         "round": "flood_final", "split": "reserved", "modules": [], "uses": []}
    FT.save(name, FT.build_table(e, BSCORE.round4_chosen()))
    return {"pluvial": True}


def _subprocess(arg, name, limit):
    try:
        r = subprocess.run([sys.executable, "-m", "experiments.flood_final.heldout_pass", arg, name],
                           timeout=limit, capture_output=True, text=True)
        return r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-3:]
    except subprocess.TimeoutExpired:
        return False, [f"killed after {limit} s"]


def build_all():
    from experiments.flood_baselines.build import check_disk
    log = json.load(open(LOG)) if os.path.exists(LOG) else {}
    for u in reserved_units():
        n = u["event_id"]
        rec = log.setdefault(n, {"tries": 0})
        while not rec.get("done") and rec["tries"] < MAX_TRIES:
            check_disk()
            t0 = time.time()
            ok, tail = _subprocess("--build-one", n, UNIT_KILL_S)
            rec["tries"] += 1
            rec.update(ok=ok, tail=tail, s=round(time.time() - t0))
            if ok:
                rec["done"] = True
                rec["result"] = json.loads(tail[-1]) if tail and tail[-1].startswith("{") else tail
            else:
                time.sleep(30 * rec["tries"])          # backoff
            print(n, json.dumps(rec, default=str)[:300], flush=True)
            os.makedirs(CACHE, exist_ok=True)
            json.dump(log, open(LOG, "w"), indent=1)
        if rec.get("done") and "pluvial" in u["flood_final"]["tags"] and \
                rec.get("result", {}).get("built") and "pluvial" not in rec:
            ok, tail = _subprocess("--pluvial-one", n, PLUVIAL_KILL_S)
            rec["pluvial"] = {"ok": ok, "tail": tail}
            json.dump(log, open(LOG, "w"), indent=1)
    return 0


def score():
    """Every pre-registered candidate, once (PREREGISTRATION §4-§7)."""
    os.environ["GEOWATCH_LEARNED_TABLES"] = os.path.join(CACHE, "tables")
    from experiments.flood_baselines import blocks as B
    from experiments.flood_baselines import score as BS
    from experiments.flood_learned import evaluate as EV
    from experiments.flood_learned import features as FT
    from experiments.flood_final import model_v2 as V
    from experiments.flood_validation.harness import MIN_DRY_CELLS, MIN_FLOODED_CELLS, auc
    pre = preflight(scoring=True)
    choice = json.load(open(os.path.join(OUT, "method_choice.json")))
    units = reserved_units()
    log = json.load(open(LOG)) if os.path.exists(LOG) else {}
    finals = {}
    for c, f in choice["final_models"].items():
        p = os.path.join(V.CACHE, f["path"])
        if hashlib.sha256(open(p, "rb").read()).hexdigest() != f["sha256"]:
            raise SystemExit(f"final model {c} hash mismatch")
        finals[c] = pickle.load(open(p, "rb"))
    res = {"preflight": pre, "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "choice": {t: ch["chosen"] for t, ch in choice["choice"].items()},
           "units": {}, "missing": {}, "not_qualifying": {}, "groups": {}, "verdicts": {}}
    recs = {}
    for u in units:
        n = u["event_id"]
        r = log.get(n, {})
        if not os.path.exists(FT.path(n)):
            key = "not_qualifying" if "not_qualifying" in str(r.get("result")) else "missing"
            res[key][n] = r.get("result") or r.get("tail")
            continue
        t = FT.load(n)
        shape = tuple(t["meta"]["shape"])
        y = t["y"]
        if int((y == 1).sum()) < MIN_FLOODED_CELLS or int((y == 0).sum()) < MIN_DRY_CELLS:
            res["not_qualifying"][n] = [int((y == 1).sum()), int((y == 0).sum())]
            continue
        scores = {}
        for c, fin in finals.items():
            ci = [FT.FEATURES.index(f) for f in fin["features"]]
            raw = fin["model"].predict_proba(t["X"][:, ci])[:, 1]
            scores[f"learned:{c}"] = fin["isotonic"].predict(raw).astype(np.float64)
            scores[f"learned_raw:{c}"] = raw.astype(np.float64)
        comps = V.comparators(t)
        for k, v in comps.items():
            scores[k] = np.asarray(v, np.float64)
        need = [k for k in scores if k != "pluvial"]
        ok = y >= 0
        for k in need:
            ok &= np.isfinite(scores[k])
        have_pl = np.isfinite(scores["pluvial"][ok]).all()
        use = {k: v.reshape(shape) for k, v in scores.items() if k != "pluvial" or have_pl}
        pb = B.paired_block_bootstrap(use, (y == 1).reshape(shape), ok.reshape(shape),
                                      BS.BLOCK_CELLS, BS.REPS, BS._seed(n))
        rec = {"tags": u["flood_final"]["tags"], "region": u["flood_final"]["region"],
               "cluster": u["storm_cluster"], "flooded": int(((y == 1) & ok).sum()),
               "dry": int(((y == 0) & ok).sum()),
               "auc": {k: round(v, 4) for k, v in pb["point"].items()},
               "ci": {k: [None if x is None else round(x, 4) for x in B.ci(r)] for k, r in pb["reps"].items()},
               "_reps": pb["reps"]}
        # secondary: average precision, area-matched IoU
        from sklearn.metrics import average_precision_score
        yy = y[ok]
        rec["ap"] = {k: round(float(average_precision_score(yy, v.ravel()[ok])), 4) for k, v in use.items()}
        k_obs = int((yy == 1).sum())
        rec["iou_area_matched"] = {}
        for k, v in use.items():
            s = v.ravel()[ok]
            top = np.zeros(s.size, bool)
            top[np.argsort(-s, kind="stable")[:k_obs]] = True
            rec["iou_area_matched"][k] = round(float((top & (yy == 1)).sum() / max(1, (top | (yy == 1)).sum())), 4)
        recs[n] = rec
    res["units"] = {n: {k: v for k, v in r.items() if k != "_reps"} for n, r in recs.items()}
    cluster_of = {n: r["cluster"] for n, r in recs.items()}
    for ty in V.TYPES:
        mem = [n for n, r in recs.items() if ty in r["tags"]]
        if not mem:
            continue
        chosen = res["choice"].get(ty)
        cands = sorted({k for n in mem for k in recs[n]["auc"]})
        g = {"units": mem, "clusters": len({cluster_of[n] for n in mem}), "mean_auc": {}, "minus_hand": {}}
        for k in cands:
            have = [n for n in mem if k in recs[n]["auc"]]
            boot = B.cluster_mean_bootstrap({n: np.asarray(recs[n]["_reps"][k]) for n in have},
                                            cluster_of, BS.REPS, BS.SEED)
            g["mean_auc"][k] = {"mean": round(float(np.mean([recs[n]["auc"][k] for n in have])), 4),
                                "ci": [round(x, 4) for x in B.ci(boot)], "n": len(have)}
            if k != "hand":
                d = B.cluster_mean_bootstrap({n: np.asarray(recs[n]["_reps"][k]) - np.asarray(recs[n]["_reps"]["hand"])
                                              for n in have}, cluster_of, BS.REPS, BS.SEED)
                g["minus_hand"][k] = {"mean": round(float(np.mean([recs[n]["auc"][k] - recs[n]["auc"]["hand"]
                                                                   for n in have])), 4),
                                      "ci": [round(x, 4) for x in B.ci(d)], "n": len(have)}
        res["groups"][ty] = g

        def verdict(k):
            if k not in g["mean_auc"]:
                return {"verdict": "not-run", "reason": "no score"}
            n_ok, n_cl = g["mean_auc"][k]["n"], len({cluster_of[n] for n in mem if k in recs[n]["auc"]})
            if n_ok < 3 or n_cl < 2:
                return {"verdict": "not-run (insufficient)", "units": n_ok, "clusters": n_cl}
            m, lo = g["mean_auc"][k]["mean"], g["minus_hand"][k]["ci"][0]
            return {"verdict": "passed" if (m >= 0.70 and lo > 0) else "failed", "mean_auc": m,
                    "minus_hand": g["minus_hand"][k], "units": n_ok, "clusters": n_cl}
        key = (f"learned_raw:{chosen}" if chosen and not chosen.startswith("module:")   # D15
               else chosen.split(":", 1)[1] if chosen else None)
        res["verdicts"][ty] = {"chosen": chosen, **verdict(key)} if key else {"verdict": "not-run"}
        if ty == "fluvial":
            res["verdicts"]["fluvial_module_retest"] = {"method": "fluvial (validated config)",
                                                        **verdict("fluvial")}
    # calibration of each learned final on pooled reserved labelled cells (secondary)
    res["calibration"] = {}
    for c in finals:
        preds = {n: (lambda t: finals[c]["isotonic"].predict(finals[c]["model"].predict_proba(
            t["X"][:, [FT.FEATURES.index(f) for f in finals[c]["features"]]])[:, 1]))(FT.load(n))
            for n in recs}
        tabs = {n: FT.load(n) for n in recs}
        res["calibration"][c] = EV.calibration(tabs, preds, cluster_of, list(recs))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "heldout.json"), "x") as fh:        # "x": never overwrite
        json.dump(res, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print("wrote results/heldout.json")
    for k, v in res["verdicts"].items():
        print(k, json.dumps(v)[:300])
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    if a[0] == "--build-one":
        import ee
        from experiments.flood_validation import references as R
        from ingestion.gee_client import initialize_gee
        initialize_gee()
        ee.data.setDeadline(R.EE_TIMEOUT_S * 1000)
        print(json.dumps(build_one(a[1]), default=str), flush=True)
        return 0
    if a[0] == "--pluvial-one":
        from ingestion.gee_client import initialize_gee
        initialize_gee()
        print(json.dumps(pluvial_one(a[1]), default=str), flush=True)
        return 0
    if a[0] == "build":
        preflight(scoring=False)
        return build_all()
    if a[0] == "score":
        return score()
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
