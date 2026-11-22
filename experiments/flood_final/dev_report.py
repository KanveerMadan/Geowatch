"""
DEV report: leave-region-out out-of-fold predictions of every learned candidate,
plus the comparators, scored per DEV unit with the paired 990 m block bootstrap,
then a per-type cluster x block mean bootstrap and the difference vs HAND.

The statistics are the same as heldout_pass.score, but on DEV.
Run after model_v2 cv and choose.

    python -m experiments.flood_final.dev_report

Writes results/dev_report.json and results/dev_tables.md. DEV only: it never
touches reserved data.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

from experiments.flood_baselines import blocks as B
from experiments.flood_baselines import score as BS
from experiments.flood_final import model_v2 as V
from experiments.flood_learned import model as M

OUT = V.OUT


def main(argv=None):
    d = json.load(open(os.path.join(V.CACHE, "dev_units.json")))
    names, tags, cl = d["names"], d["tags"], d["clusters"]
    choice = json.load(open(os.path.join(OUT, "method_choice.json")))["choice"]
    tables = M.load_tables(names)
    lro = V.load_runs("lro")
    recs = {}
    for n in names:
        t = tables[n]
        shape = tuple(t["meta"]["shape"])
        y = t["y"]
        ok = V.common_ok(t, [r[n] for r in lro.values()])
        scores = {f"lro:{k}": np.asarray(r[n], np.float64) for k, r in lro.items()}
        for k, v in V.comparators(t).items():
            v = np.asarray(v, np.float64)
            if k == "pluvial" and not np.isfinite(v[ok]).all():
                continue                       # missing, never zero (D8)
            scores[k] = v
        pb = B.paired_block_bootstrap({k: v.reshape(shape) for k, v in scores.items()},
                                      (y == 1).reshape(shape), ok.reshape(shape),
                                      BS.BLOCK_CELLS, BS.REPS, BS._seed(n))
        recs[n] = {"auc": pb["point"], "reps": pb["reps"],
                   "flooded": int(((y == 1) & ok).sum()), "dry": int(((y == 0) & ok).sum())}
        print(f"  {n:28s} {time.strftime('%H:%M:%S')}", flush=True)
    res = {"what": "DEV leave-region-out, paired 990 m block bootstrap; cluster x block mean bootstrap",
           "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "units": {n: {"tags": tags[n], "cluster": cl[n], "flooded": r["flooded"], "dry": r["dry"],
                         "auc": {k: round(float(v), 4) for k, v in r["auc"].items() if v is not None},
                         "ci": {k: [None if x is None else round(x, 4) for x in B.ci(v)]
                                for k, v in r["reps"].items()}}
                     for n, r in recs.items()},
           "groups": {}}
    for ty in V.TYPES:
        mem = [n for n in names if ty in tags[n]]
        if not mem:
            continue
        g = {"units": mem, "clusters": len({cl[n] for n in mem}),
             "chosen": choice.get(ty, {}).get("chosen"), "mean_auc": {}, "minus_hand": {}}
        keys = sorted({k for n in mem for k, v in recs[n]["auc"].items() if v is not None})
        for k in keys:
            have = [n for n in mem if recs[n]["auc"].get(k) is not None]
            boot = B.cluster_mean_bootstrap({n: np.asarray(recs[n]["reps"][k]) for n in have},
                                            cl, BS.REPS, BS.SEED)
            g["mean_auc"][k] = {"mean": round(float(np.mean([recs[n]["auc"][k] for n in have])), 4),
                                "ci": [round(x, 4) for x in B.ci(boot)], "n": len(have)}
            if k != "hand":
                dd = B.cluster_mean_bootstrap(
                    {n: np.asarray(recs[n]["reps"][k]) - np.asarray(recs[n]["reps"]["hand"]) for n in have},
                    cl, BS.REPS, BS.SEED)
                g["minus_hand"][k] = {"mean": round(float(np.mean([recs[n]["auc"][k] - recs[n]["auc"]["hand"]
                                                                   for n in have])), 4),
                                      "ci": [round(x, 4) for x in B.ci(dd)], "n": len(have)}
        res["groups"][ty] = g
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "dev_report.json"), "w"), indent=1, default=float)
    lines = ["# DEV results (leave-region-out, out-of-fold)", "",
             "Mean within-event AUC with a cluster x 990 m block bootstrap 95% CI; Δ vs HAND paired on the same blocks.",
             ""]
    for ty, g in res["groups"].items():
        lines += [f"## {ty} — {len(g['units'])} units, {g['clusters']} clusters; chosen `{g['chosen']}`", "",
                  "| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | n |", "|---|---|---|---|"]
        for k, m in sorted(g["mean_auc"].items(), key=lambda kv: -kv[1]["mean"]):
            dh = g["minus_hand"].get(k)
            dtxt = f"{dh['mean']:+.3f} [{dh['ci'][0]:+.3f}, {dh['ci'][1]:+.3f}]" if dh else "—"
            lines.append(f"| {k} | {m['mean']:.3f} [{m['ci'][0]:.3f}, {m['ci'][1]:.3f}] | {dtxt} | {m['n']} |")
        lines.append("")
    open(os.path.join(OUT, "dev_tables.md"), "w").write("\n".join(lines))
    print("wrote results/dev_report.json, results/dev_tables.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
