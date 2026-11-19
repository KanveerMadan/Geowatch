"""
Phase 5: learned model v2 on DEV only, and the pre-registered method choice
(PREREGISTRATION.md §4).

    python -m experiments.flood_final.model_v2 cv        # LRO + LCO out-of-fold predictions per candidate
    python -m experiments.flood_final.model_v2 choose    # per-type choice + calibration + final models

DEV units = flood_learned batch 0 (29) + the new flood_final DEV units with a
feature table. Regions: batch-0 regions (flood_learned.events.REGION); new
units by their registry `flood_final.region`, "africa" merged into
"africa_west_asia" (batch 0's grouping). Clusters: any registry link
(flood_baselines.events.clusters), so linked units always leave together.
Hyperparameters: flood_learned.model.LGBM_PARAMS / LR_C, unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

import numpy as np

from experiments.flood_baselines import events as BE
from experiments.flood_core.registry import registry as REG
from experiments.flood_learned import events as LE
from experiments.flood_learned import features as FT
from experiments.flood_learned import model as M
from experiments.flood_validation.harness import auc

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_final/model_v2")
TYPES = ("fluvial", "pluvial", "waterlogging", "flash_flood", "coastal", "compound")
# DEV compound units (rain + river, or rain + surge, documented): DECISIONS.md D12.
DEV_COMPOUND = ("valencia_2024", "paiporta", "beira", "black_river", "fort_myers_beach",
                "kyaukpyu", "sittwe")
COAST = ("elev_glo30", "dist_coast_m")
_T = M.terrain
VARIANTS = {
    "full": _T("fabdem") + M.MERIT + M.WATER + M.RAIN + M.LAND + COAST + ("ghsl_built_frac",),
    "open": _T("glo30") + ("log_hs_acc",) + M.WATER + M.RAIN + M.LAND + COAST + ("ghsl_built_frac",),
    "no_landcover": _T("fabdem") + M.MERIT + M.WATER + M.RAIN + ("clay_pct", "ndvi_pre") + COAST,
}
MODELS = ("logreg", "lgbm")          # tie-break order: logistic first (PREREGISTRATION §4)
TIE = 0.005
# Comparators on the same cells: features.COMPARATORS + coastal baselines
# (negated so higher = more flood-prone).
COASTAL_BASELINES = {"neg_elev_glo30": "elev_glo30", "neg_dist_coast": "dist_coast_m"}


def dev_units(reg=None):
    reg = reg or REG.load()
    units = REG.units(reg)
    names = [c["unit"] for c in LE.batch0(reg)]
    names += [u["event_id"] for u in reg["units"] if u["role"] == "dev"
              and any(x.get("round") == "flood_final" for x in u.get("uses", []))
              and os.path.exists(FT.path(u["event_id"]))]
    region, tags = {}, {}
    cat = {c["unit"]: c for c in LE.batch0(reg)}
    for n in names:
        u = units[n]
        if n in cat:
            region[n] = LE.region(n)
            t = set(BE.mechanism(cat[n], reg))
        else:
            r = u["flood_final"]["region"]
            region[n] = "africa_west_asia" if r == "africa" else r
            t = set(u["flood_final"]["tags"])
        if n in DEV_COMPOUND:
            t.add("compound")
        tags[n] = sorted(t)
    return names, region, tags


def cols(variant):
    return [FT.FEATURES.index(f) for f in VARIANTS[variant]]


def folds(names, key):
    out = {}
    for n in names:
        out.setdefault(key[n], []).append(n)
    return out


def cv(tables, names, key, variant, model):
    c = cols(variant)
    pred = {}
    for fid, held in sorted(folds(names, key).items()):
        train = [n for n in names if n not in held]
        X, y, w = M.training_rows(tables, train, c)
        m = M.fit_lgbm(X, y, w) if model == "lgbm" else M.LogReg().fit(X, y, w)
        for n in held:
            pred[n] = m.predict_proba(tables[n]["X"][:, c])[:, 1].astype(np.float32)
    return pred


def comparators(t):
    C = {k: t["C"][:, i] for i, k in enumerate(FT.COMPARATORS)}
    for k, f in COASTAL_BASELINES.items():
        C[k] = -t["X"][:, FT.FEATURES.index(f)].astype(np.float32)
    return C


def common_ok(t, preds):
    ok = t["y"] >= 0
    for k, v in comparators(t).items():
        if k in ("pluvial",):                 # missing on new DEV units (D8): not a gate
            continue
        ok &= np.isfinite(v)
    for v in preds:
        ok &= np.isfinite(v)
    return ok


def point_aucs(tables, names, runs):
    out = {}
    for n in names:
        t = tables[n]
        ok = common_ok(t, [r[n] for r in runs.values()])
        y = t["y"][ok]
        f = lambda s: auc(s, (y == 1).astype(int), (y == 0).astype(int))    # noqa: E731
        rec = {k: f(r[n][ok]) for k, r in runs.items()}
        for k, v in comparators(t).items():
            vv = v[ok]
            rec[k] = f(vv) if np.isfinite(vv).all() else None
        rec["_cells"] = [int((y == 1).sum()), int((y == 0).sum())]
        out[n] = rec
    return out


def run_cv():
    names, region, tags = dev_units()
    cl = BE.clusters(names, REG.load())
    seen = {}
    for n in names:
        if seen.setdefault(cl[n], region[n]) != region[n]:
            raise SystemExit(f"cluster {cl[n]} spans {seen[cl[n]]} and {region[n]} ({n})")
    tables = M.load_tables(names)
    os.makedirs(CACHE, exist_ok=True)
    for split, key in (("lro", region), ("lco", {n: f"c{cl[n]}" for n in names})):
        for v in VARIANTS:
            for m in MODELS:
                tag = f"{split}__{v}__{m}"
                p = os.path.join(CACHE, f"{tag}.npz")
                if os.path.exists(p):
                    continue
                t0 = time.time()
                np.savez_compressed(p, **cv(tables, names, key, v, m))
                print(f"── {tag} {time.time() - t0:.0f} s", flush=True)
    json.dump({"names": names, "region": region, "tags": tags, "clusters": cl},
              open(os.path.join(CACHE, "dev_units.json"), "w"), indent=1)
    return 0


def load_runs(split):
    out = {}
    for v in VARIANTS:
        for m in MODELS:
            z = np.load(os.path.join(CACHE, f"{split}__{v}__{m}.npz"))
            out[f"{v}__{m}"] = {k: z[k] for k in z.files}
    return out


def choose():
    d = json.load(open(os.path.join(CACHE, "dev_units.json")))
    names, tags = d["names"], d["tags"]
    tables = M.load_tables(names)
    lro, lco = load_runs("lro"), load_runs("lco")
    pa_lro = point_aucs(tables, names, lro)
    pa_lco = point_aucs(tables, names, lco)
    candidates = list(lro)                       # learned candidates
    modules = {"fluvial": "fluvial", "pluvial": "pluvial", "waterlogging": "waterlogging",
               "flash_flood": "flash_flood"}
    choice = {}
    for ty in TYPES:
        mem = [n for n in names if ty in tags[n]]
        if not mem:
            continue
        means = {}
        for c in candidates:
            means[c] = float(np.mean([pa_lro[n][c] for n in mem]))
        mod = modules.get(ty)
        if mod:
            vals = [pa_lro[n][mod] for n in mem if pa_lro[n][mod] is not None]
            if len(vals) == len(mem):            # a module competes only where defined on every member
                means[f"module:{mod}"] = float(np.mean(vals))
        best = max(means.values())
        near = [c for c in means if best - means[c] <= TIE]

        def rank(c):        # PREREGISTRATION §4 tie-break: logistic before LGBM, open before full
            return (0 if c.endswith("logreg") else 1 if c.endswith("lgbm") else 2,
                    0 if c.startswith("open") else 1)
        pick = sorted(near, key=rank)[0]
        base = {b: float(np.mean([pa_lro[n][b] for n in mem if pa_lro[n][b] is not None]))
                for b in ("hand", "occurrence", "dist_water", "neg_elev_glo30", "neg_dist_coast")}
        choice[ty] = {"members": mem, "n": len(mem), "lro_mean_auc": means, "chosen": pick,
                      "baselines_lro": base,
                      "lco_mean_auc": {c: float(np.mean([pa_lco[n][c] for n in mem]))
                                       for c in candidates}}
        print(f"{ty:12s} n={len(mem):2d} chosen {pick:22s} {means[pick]:.3f} | HAND {base['hand']:.3f}",
              flush=True)
    # calibration (isotonic on pooled LRO out-of-fold, each event equal weight) and final models
    from sklearn.isotonic import IsotonicRegression
    finals = {}
    for ty, ch in choice.items():
        c = ch["chosen"]
        if c.startswith("module:") or c in finals:
            continue
        v, m = c.split("__")
        ys, ps, ws = [], [], []
        for n in names:
            y = tables[n]["y"]
            k = y >= 0
            ys.append(y[k]); ps.append(lro[c][n][k]); ws.append(np.full(k.sum(), 1.0 / k.sum()))
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(
            np.concatenate(ps), np.concatenate(ys), sample_weight=np.concatenate(ws))
        X, y, w = M.training_rows(tables, names, cols(v))
        mdl = M.fit_lgbm(X, y, w) if m == "lgbm" else M.LogReg().fit(X, y, w)
        import pickle
        path = os.path.join(CACHE, f"final__{c}.pkl")
        with open(path, "wb") as fh:
            pickle.dump({"model": mdl, "isotonic": iso, "features": list(VARIANTS[v])}, fh)
        finals[c] = {"path": os.path.basename(path),
                     "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
                     "features": list(VARIANTS[v]), "n_train_units": len(names)}
    res = {"what": "PREREGISTRATION §4 method choice, DEV only (leave-region-out mean AUC per type)",
           "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "dev_units": names, "regions": d["region"], "tags": tags, "clusters": d["clusters"],
           "choice": choice, "final_models": finals,
           "per_unit_lro": pa_lro, "per_unit_lco": pa_lco}
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "method_choice.json"), "w"), indent=1, default=float)
    print("wrote", os.path.join(OUT, "method_choice.json"))
    return 0


def main(argv=None):
    step = (argv or sys.argv[1:])[0]
    return run_cv() if step == "cv" else choose()


if __name__ == "__main__":
    sys.exit(main())
