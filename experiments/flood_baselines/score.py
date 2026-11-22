"""
Score three trivial baselines beside the four current flood modules on every
qualifying dev box, with spatially blocked bootstrap intervals.

    python -m experiments.flood_baselines.score            # writes results/

Reads only: the cached round 2-4 references (events.py) and the inputs that
build.py fetched. Changes no label, verdict, method or pre-registration. This
is a report, not a stop rule.

Scores (higher = more flood-prone), all on the same cells:
  baselines   hand        -MERIT hnd (m)
              occurrence  JRC GSW occurrence (%), 1984-2021
              dist_water  -distance to OSM water or JRC permanent water (m)
  modules     fluvial, pluvial, waterlogging, flash_flood: the production
              functions with their production (config default) parameters
  sensitivity occurrence_pre  JRC monthly water frequency, years before the
                              event only (the waterlogging input; no post-event years)
              dist_osm_only   distance to OSM water alone
              <module>_r4chosen  the parameters round 4's tuning chose
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import sys

import numpy as np

from experiments.flood_baselines import blocks as B
from experiments.flood_baselines import build as BUILD
from experiments.flood_baselines import events as E
from experiments.flood_core.registry import registry as REG
from experiments.flood_validation import references as R
from experiments.flood_validation.harness import MIN_DRY_CELLS, MIN_FLOODED_CELLS

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
ROUND4_RESULT = os.path.join(HERE, "..", "flood_validation", "result_round4_2026-10-30.json")
BASELINES = ("hand", "occurrence", "dist_water")
MODULES = ("fluvial", "pluvial", "waterlogging", "flash_flood")
PRIMARY = BASELINES + MODULES
SENSITIVITY = ("occurrence_pre", "dist_osm_only", "pluvial_r4chosen",
               "waterlogging_r4chosen", "flash_flood_r4chosen")
# Block side in 30 m cells: 33 cells = 990 m, at or above the upper quartile
# (960 m) of the measured practical ranges of the reference flood indicator
# (blocks.correlation_range over the qualifying events; REPORT.md), and small
# enough to leave ~16 tiles in a 4 km box. Sensitivity: 66 cells (1980 m, at
# or above the largest measured range) and each event's own measured range.
BLOCK_CELLS = 33
BLOCK_CELLS_WIDE = 66
# 1000 replicates: Efron & Tibshirani (1993, ch. 13) for percentile intervals.
REPS = 1000
SEED = 20261114


def _seed(name: str) -> int:
    return SEED + int(hashlib.sha1(name.encode()).hexdigest()[:6], 16)


def rasters_from(arrays: dict, shape) -> dict:
    from susceptibility.inputs import surface
    layers = {k[len("layer_"):]: surface(v, "fetched", "fetched", "experimental")
              for k, v in arrays.items() if k.startswith("layer_")}
    return {"status": "available", "shape": shape, "errors": {}, "layers": layers}


def round4_chosen() -> dict:
    with open(ROUND4_RESULT) as fh:
        r4 = json.load(fh)["modules"]
    return {m: r4[m].get("params_used") for m in ("pluvial", "waterlogging", "flash_flood")}


def pluvial_score(a: dict, params: dict | None, shape):
    from configs.pluvial_constants import PLUVIAL_RUNOFF_C_PERVIOUS
    from susceptibility import pluvial
    if "pl_dem" not in a:
        return None
    c_perv = PLUVIAL_RUNOFF_C_PERVIOUS if params is None else params["c_perv"]
    comps = pluvial.components(a["pl_dem"], a["pl_imp"], float(a["pl_storm"]), c_perv)
    m = pluvial.combine(comps, None if params is None else params["weights"])
    r0, c0 = (int(v) for v in a["pl_window"])
    return m[r0:r0 + shape[0], c0:c0 + shape[1]]


def all_scores(a: dict, shape, chosen: dict) -> dict:
    """{name: 2-D array or None} for PRIMARY + SENSITIVITY."""
    from susceptibility import flash_flood, fluvial, waterlogging
    rs = rasters_from(a, shape)
    hand = a.get("layer_hand_m")
    out = {
        "hand": None if hand is None else -np.asarray(hand, np.float64),
        "occurrence": np.asarray(a["jrc_occurrence"], np.float64),
        "dist_water": -np.asarray(a["dist_water_m"], np.float64),
        "occurrence_pre": a.get("layer_jrc_water_freq"),
        "dist_osm_only": -np.asarray(a["dist_water_osm_only_m"], np.float64),
    }
    out["fluvial"] = fluvial.combine(fluvial.components(rs))
    wl = waterlogging.components(rs)
    out["waterlogging"] = waterlogging.combine(wl)
    out["waterlogging_r4chosen"] = waterlogging.combine(wl, chosen["waterlogging"])
    ff = flash_flood.components(rs)
    out["flash_flood"] = flash_flood.combine(ff)
    out["flash_flood_r4chosen"] = flash_flood.combine(ff, chosen["flash_flood"])
    out["pluvial"] = pluvial_score(a, None, shape)
    out["pluvial_r4chosen"] = pluvial_score(a, chosen["pluvial"], shape)
    return {k: (None if v is None else np.asarray(v, np.float64)) for k, v in out.items()}


def evaluation_grid(scores: dict, flooded, valid, block: int):
    """Aggregate to the reference's evaluation cells (R.blocks for GFD's
    240 m cells; identity at block 1). Returns (scores, flooded, valid)."""
    if block == 1:
        return scores, flooded, valid
    agg, f, v = {}, None, None
    for k, s in scores.items():
        if s is None:
            agg[k] = None
            continue
        bs, bf, bv = R.blocks(s, flooded, valid, block)
        agg[k] = bs
        f = bf if f is None else f
        v = bv if v is None else v
    return agg, f, v


def score_unit(entry: dict, chosen: dict, reg: dict) -> dict:
    name = entry["unit"]
    built = BUILD.load(name)
    ref = E.reference(entry)
    shape = ref["flooded"].shape
    sc = all_scores(built["arrays"], shape, chosen)
    sc, flooded, valid = evaluation_grid(sc, ref["flooded"], ref["valid"], ref["block"])
    present = [k for k in PRIMARY if sc.get(k) is not None and np.isfinite(sc[k]).any()]
    ok = valid.copy()
    for k in present:
        ok &= np.isfinite(sc[k])
    nf, nd = int((flooded & ok).sum()), int((~flooded & ok).sum())
    rec = {"unit": name, "round": entry["round"], "split": entry["split"],
           "event": entry["meta"]["event"], "cached_modules": entry["modules"],
           "mechanism": E.mechanism(entry, reg), "evaluation_cell_m": 30 * ref["block"],
           "valid_cells": int(valid.sum()), "common_cells": int(ok.sum()),
           "flooded_cells": nf, "dry_cells": nd, "missing": [k for k in PRIMARY if k not in present],
           "build_errors": built["meta"].get("errors"),
           "osm_water_complete": built["meta"].get("dist", {}).get("osm_complete"),
           "osm_counts": built["meta"].get("dist", {}).get("osm_counts"),
           "raster_errors": {k: v for k, v in (built["meta"].get("raster_errors") or {}).items()
                             if v and v != "not requested"}}
    rec["qualifies"] = nf >= MIN_FLOODED_CELLS and nd >= MIN_DRY_CELLS
    rng_cells, _ = B.correlation_range(flooded.astype(float), valid, max_lag=min(shape) // 2)
    rec["indicator_range_m"] = None if rng_cells is None else rng_cells * 30 * ref["block"]
    if not rec["qualifies"]:
        return rec
    use = {k: v for k, v in sc.items() if v is not None and k in present + list(SENSITIVITY)}
    sens_ok = {k: v for k, v in use.items() if k in SENSITIVITY and np.isfinite(v[ok]).all()}
    use = {**{k: use[k] for k in present}, **sens_ok}
    per_block = {}
    eval_block = lambda cells: max(1, int(np.ceil(cells / ref["block"])))   # noqa: E731
    sizes = {"990m": eval_block(BLOCK_CELLS), "1980m": eval_block(BLOCK_CELLS_WIDE),
             "own_range": max(1, rng_cells or 1)}
    for label, b in sizes.items():
        per_block[label] = B.paired_block_bootstrap(use, flooded, ok, b, REPS, _seed(name))
    main = per_block["990m"]
    rec["auc"] = {k: round(v, 4) for k, v in main["point"].items()}
    rec["tiles"] = {k: v["tiles"] for k, v in per_block.items()}
    rec["block_cells"] = sizes
    rec["ci"] = {lab: {k: [None if x is None else round(x, 4) for x in B.ci(r)]
                       for k, r in pb["reps"].items()} for lab, pb in per_block.items()}
    base_pts = {k: main["point"][k] for k in BASELINES if k in main["point"]}
    best = max(base_pts, key=base_pts.get)
    rec["best_baseline"] = best
    rec["delta_vs_best"] = {}
    for m in MODULES + ("pluvial_r4chosen", "waterlogging_r4chosen", "flash_flood_r4chosen"):
        if m not in main["point"]:
            continue
        d = {}
        for lab, pb in per_block.items():
            diff = pb["reps"][m] - pb["reps"][best]
            d[lab] = [None if x is None else round(x, 4) for x in B.ci(diff)]
        rec["delta_vs_best"][m] = {"delta": round(main["point"][m] - main["point"][best], 4),
                                   "ci": d}
    rec["_reps"] = {k: v.tolist() for k, v in main["reps"].items()}   # for the means
    return rec


def group_means(recs: list, cluster_of: dict, members) -> dict:
    """Mean AUC per score over `members` (qualifying unit names), with the
    cluster two-stage bootstrap interval; and the mean paired difference of
    each module against each baseline."""
    q = [r for r in recs if r.get("qualifies") and r["unit"] in members]
    out = {"events": [r["unit"] for r in q],
           "clusters": len({cluster_of[r["unit"]] for r in q}), "auc": {}, "delta": {}}
    for k in PRIMARY + SENSITIVITY:
        have = [r for r in q if k in r.get("auc", {})]
        if not have:
            continue
        reps = {r["unit"]: np.asarray(r["_reps"][k]) for r in have}
        boot = B.cluster_mean_bootstrap(reps, cluster_of, REPS, SEED)
        out["auc"][k] = {"mean": round(float(np.mean([r["auc"][k] for r in have])), 4),
                         "ci": [round(x, 4) for x in B.ci(boot)], "n_events": len(have)}
    for m in MODULES:
        for b in BASELINES:
            have = [r for r in q if m in r.get("auc", {}) and b in r.get("auc", {})]
            if not have:
                continue
            reps = {r["unit"]: np.asarray(r["_reps"][m]) - np.asarray(r["_reps"][b]) for r in have}
            boot = B.cluster_mean_bootstrap(reps, cluster_of, REPS, SEED)
            out["delta"][f"{m}-{b}"] = {
                "mean": round(float(np.mean([r["auc"][m] - r["auc"][b] for r in have])), 4),
                "ci": [round(x, 4) for x in B.ci(boot)], "n_events": len(have)}
    return out


def excluding_round4_test(cat: list, reg: dict, qual: list):
    """Qualifying units minus (a) every unit round 4 used as a TEST event and
    (b) every unit with a block-level registry link to one (same product,
    intersecting box or same storm), because those re-enter the same
    observation under another name (e.g. paiporta = valencia_2024's EMS
    product). Returns (kept, removed_test, removed_aliases)."""
    units = REG.units(reg)
    r4_test = {c["unit"] for c in cat
               if any(r == "round4" and s == "test" for r, s, _ in c["uses"])}
    aliases = {n for n in qual if n not in r4_test and any(
        sev == REG.BLOCK for t in r4_test for _, sev in REG.links(units[n], units[t]))}
    return set(qual) - r4_test - aliases, r4_test & set(qual), aliases


def reproduce_round4(chosen: dict) -> dict:
    """Check the scoring path: round 4's cached TEST arrays, its chosen
    parameters and its own event_auc must give its pinned per-event AUCs.
    (These boxes are dev units now; this re-reads numbers already published.)"""
    from experiments.flood_validation import harness_round2 as H2
    from experiments.flood_validation import harness_round4 as H4
    with open(ROUND4_RESULT) as fh:
        pinned = json.load(fh)["modules"]
    out = {}
    for module, evs in H4.TEST_EVENTS.items():
        for n in evs:
            p = H4._path("test", module, n)
            if not os.path.exists(p):
                continue
            a = H4.load_event("test", module, n)["arrays"]
            got = H2.event_auc(H4.score_event(module, a, chosen.get(module)), a["flooded"],
                               a["valid"], 1)["auc"]
            want = pinned[module]["held_out_per_event"][n]["auc"]
            out[f"{module}/{n}"] = {"pinned": want, "recomputed": got,
                                    "match": got == want}
    return out


def wait_for_builders(poll_s: float = 15.0):
    """Do not score while the second pluvial worker (build --pluvial-reverse)
    is alive or any unit lock is held: a unit could still be saving."""
    import glob
    import subprocess
    import time
    while True:
        alive = subprocess.run(["pgrep", "-f", "flood_baselines.build --.*pluvial"],
                               capture_output=True, text=True).stdout.split()
        alive = [p for p in alive if int(p) != os.getpid()]
        locks = []
        for lk in glob.glob(os.path.join(BUILD.LOCK_DIR, "*.lock")):
            try:
                holder = int(open(lk).read().strip() or 0)
            except (OSError, ValueError):
                holder = 0
            if holder and BUILD._pid_alive(holder):     # a dead holder's lock is stale
                locks.append(lk)
        if not alive and not locks:
            return
        print(f"waiting for builders: pids {alive}, locks {[os.path.basename(x) for x in locks]}",
              flush=True)
        time.sleep(poll_s)


def main():
    wait_for_builders()
    reg = REG.load()
    chosen = round4_chosen()
    cat = [c for c in E.catalogue(reg) if os.path.exists(BUILD.path(c["unit"]))]
    names = [c["unit"] for c in cat]
    cluster_of = E.clusters(names, reg)
    recs = []
    for c in cat:
        print("score", c["unit"], flush=True)
        recs.append(score_unit(c, chosen, reg))
    qual = [r["unit"] for r in recs if r.get("qualifies")]
    excl, r4_test, aliases = excluding_round4_test(cat, reg, qual)
    # Units whose reference IS JRC GSW occurrence (round 2's recurrent 5-80 %
    # waterlogging reference): the occurrence baseline is the reference's own
    # source there (AUC 1 by construction) and dist_water uses JRC >= 80 %, so
    # baseline comparisons on them are circular. Reported, never dropped from "all".
    src = {c["unit"]: c["meta"].get("reference", {}).get("source", "") for c in cat}
    for r in recs:
        r["reference_source"] = src[r["unit"]]
    jrc_ref = {n for n in qual if src[n].startswith("JRC/GSW")}
    no_jrc = set(qual) - jrc_ref
    groups = {"all": set(qual), "excl_r4_test": excl, "excl_jrc_ref": no_jrc,
              "excl_r4_test|excl_jrc_ref": excl & no_jrc}
    for m in MODULES + ("coastal",):
        mech = {r["unit"] for r in recs if r.get("qualifies") and m in r["mechanism"]}
        groups[f"mechanism:{m}"] = mech
        groups[f"mechanism:{m}|excl_r4_test"] = mech & excl
        groups[f"mechanism:{m}|excl_r4_test|excl_jrc_ref"] = mech & excl & no_jrc
    means = {g: group_means(recs, cluster_of, mem) for g, mem in groups.items() if mem}
    res = {
        "what": "baselines beside the current flood modules on dev boxes (exp/flood-baselines)",
        "run_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "settings": {"block_cells": BLOCK_CELLS, "block_cells_wide": BLOCK_CELLS_WIDE,
                     "reps": REPS, "seed": SEED, "min_flooded_cells": MIN_FLOODED_CELLS,
                     "min_dry_cells": MIN_DRY_CELLS, "dist_cap_m": BUILD.DIST_MARGIN_M,
                     "round4_chosen": chosen},
        "catalogue": [{k: c[k] for k in ("unit", "round", "split", "modules")} for c in cat],
        "clusters": cluster_of,
        "excl_r4_test": {"removed_round4_test_units": sorted(r4_test),
                         "removed_block_level_aliases": sorted(aliases), "kept": sorted(excl)},
        "jrc_reference_units": sorted(jrc_ref),
        "reproduce_round4": reproduce_round4(chosen),
        "events": [{k: v for k, v in r.items() if k != "_reps"} for r in recs],
        "means": means,
    }
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "baselines.json")
    with open(path, "w") as fh:
        json.dump(res, fh, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print("wrote", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
