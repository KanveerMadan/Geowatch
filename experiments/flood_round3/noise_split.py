"""
Round 3, diagnosis j: how much of the per-unit gain spread is sampling noise inside a
unit (990 m block bootstrap) and how much is real difference between events.

On burned v3 units only (in window, >= 50 flooded and dry). For each unit the paired
block bootstrap (the round-2 scorer's code) gives the within-unit variance of
gain = learned - better baseline. Then
    total var   = sample variance of the per-unit point gains
    within var  = mean of the per-unit bootstrap variances
    between var = total - within   (true event-to-event spread)
If within dominates, larger units (more 990 m blocks) cut the units a type needs.
The block count per unit is reported too, as the bootstrap's resolution.

    python -m experiments.flood_round3.noise_split    # -> results/noise_split.json
"""
from __future__ import annotations

import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/v3_labels")


def main():
    from experiments.flood_baselines import blocks as B
    from experiments.flood_baselines import score as BS
    from experiments.flood_round3.diagnose import LEARNED_FOR, TYPES
    from experiments.flood_round3.relabel_burned import predictions
    cat = json.load(open(os.path.join(OUT, "burned_catalog.json")))
    preds = predictions(cat)
    per, summ = {}, {}
    for n, row in sorted(cat.items()):
        p = os.path.join(CACHE, f"{n}.npz")
        if not os.path.exists(p):
            continue
        z = np.load(p, allow_pickle=False)
        if "error" in z.files:
            continue
        meta = json.loads(str(z["meta"]))
        if meta.get("late"):
            continue
        y = z["y"]
        shape = tuple(row["grid"]["shape"])
        ok = (y == 0) | (y == 1)
        for r in preds[n].values():
            ok &= np.isfinite(r)
        if ((y == 1) & ok).sum() < 50 or ((y == 0) & ok).sum() < 50:
            continue
        cands = sorted({"elev", "hand", *[LEARNED_FOR[t] for t in row["tags"] if t in LEARNED_FOR]})
        rec = B.paired_block_bootstrap({c: preds[n][c].reshape(shape) for c in cands}, (y == 1).reshape(shape),
                                       ok.reshape(shape), BS.BLOCK_CELLS, BS.REPS, BS._seed(n))
        nb = int(np.ceil(shape[0] / BS.BLOCK_CELLS) * np.ceil(shape[1] / BS.BLOCK_CELLS))
        per[n] = {"tags": row["tags"], "blocks": nb, "cells": int(ok.sum()), "point": rec["point"],
                  "var": {c: float(np.nanvar(rec["reps"][c], ddof=1)) for c in cands},
                  "reps": {c: np.asarray(rec["reps"][c], np.float64) for c in cands}}
    for ty in TYPES:
        lc = LEARNED_FOR[ty]
        g, w = [], []
        for n, r in per.items():
            if ty not in r["tags"] or lc not in r["point"]:
                continue
            bb = "elev" if r["point"]["elev"] >= r["point"]["hand"] else "hand"
            g.append(r["point"][lc] - r["point"][bb])
            w.append(float(np.nanvar(r["reps"][lc] - r["reps"][bb], ddof=1)))
        if len(g) < 3:
            summ[ty] = {"units": len(g)}
            continue
        tot = float(np.var(g, ddof=1))
        within = float(np.mean(w))
        summ[ty] = {"units": len(g), "gain_mean": round(float(np.mean(g)), 4), "sd_total": round(tot ** 0.5, 4),
                    "sd_within_mean": round(within ** 0.5, 4),
                    "sd_between": round(max(0.0, tot - within) ** 0.5, 4),
                    "within_share": round(min(1.0, within / tot), 3)}
    blocks = [r["blocks"] for r in per.values()]
    res = {"by_type": summ, "blocks_per_unit": {"median": float(np.median(blocks)), "min": int(min(blocks)),
                                                 "max": int(max(blocks))},
           "per_unit": {n: {k: v for k, v in r.items() if k != "reps"} for n, r in per.items()}}
    json.dump(res, open(os.path.join(OUT, "noise_split.json"), "w"), indent=1, default=float)
    print(json.dumps({k: v for k, v in res.items() if k != "per_unit"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
