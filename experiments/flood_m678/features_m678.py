"""
Round 2/3's feature pipeline on M6–M8 8 km boxes, unchanged (build_r3._features), with every cache
under ~/.cache/geowatch/flood_m678/big so no round-3 cache or table is touched.

    cd ~/gw-r3pin && PYTHONPATH=.:$HOME/gw-m678/experiments/flood_m678 python -B -m features_m678 dev|reserve [incident ...]

One subprocess per unit with a time limit, resumable; units with fewer than 50 flooded or 50 dry
cells are skipped by the bar's own rule. A memory guard pauses while free memory is below 15 %.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time

BIG = os.path.expanduser("~/.cache/geowatch/flood_m678/big")
os.environ["GEOWATCH_BASELINE_CACHE"] = os.path.join(BIG, "baseline")
os.environ["GEOWATCH_LEARNED_CACHE"] = os.path.join(BIG, "inputs")
os.environ["GEOWATCH_LEARNED_TABLES"] = os.path.join(BIG, "tables_l")
TABLES = os.path.join(BIG, "tables")
LOG = os.path.join(BIG, "build_log.json")
UNIT_KILL_S, TRIES = 5400, 2


def free_pct():
    try:
        out = subprocess.run(["memory_pressure"], capture_output=True, text=True, timeout=30).stdout
        return int(out.strip().splitlines()[-1].split(":")[1].strip().rstrip("%"))
    except Exception:      # noqa: BLE001
        return 100


def guard():
    while free_pct() < 15:
        print("memory guard: free < 15 %, waiting", flush=True)
        time.sleep(120)


def one(n):
    import numpy as np
    import labels_m678 as LM
    LM.init_ee()                                    # exclusive EE lock before round 3's modules load
    from experiments.flood_round3 import build_r3 as B
    B.TABLES = TABLES
    rp = os.path.join(LM.REFS, f"{n}.npz")
    meta = json.loads(str(np.load(rp, allow_pickle=False)["meta"]))
    p = B._features(n, rp, meta)
    z = np.load(p, allow_pickle=False)
    print("RESULT", json.dumps({"flooded": int((z["y"] == 1).sum()), "dry": int((z["y"] == 0).sum()), "cells": int(len(z["y"]))}))


def run(split, only=()):
    import numpy as np
    import labels_m678 as LM
    os.makedirs(BIG, exist_ok=True)
    log = json.load(open(LOG)) if os.path.exists(LOG) else {}
    for r in LM.records(split):
        n = r["incident"]
        if only and n not in only:
            continue
        rp = os.path.join(LM.REFS, f"{n}.npz")
        if not os.path.exists(rp):
            continue
        m = json.loads(str(np.load(rp, allow_pickle=False)["meta"]))
        if m.get("dropout") or m.get("flooded_cells", 0) < 50 or m.get("dry_cells", 0) < 50:
            log[n] = {"done": True, "skipped": m.get("dropout") or [m.get("flooded_cells"), m.get("dry_cells")]}
            continue
        rec = log.setdefault(n, {"tries": 0})
        while not rec.get("done") and rec["tries"] < TRIES:
            guard()
            try:
                p = subprocess.run([sys.executable, "-B", "-m", "features_m678", "--one", n], timeout=UNIT_KILL_S,
                                   capture_output=True, text=True)
                tail = (p.stdout + p.stderr).strip().splitlines()[-3:]
                ok = p.returncode == 0
            except subprocess.TimeoutExpired:
                ok, tail = False, [f"killed after {UNIT_KILL_S} s"]
            rec["tries"] += 1
            rec.update(ok=ok, tail=tail, done=bool(ok and tail and tail[-1].startswith("RESULT ")))
            print(n, json.dumps(rec)[:300], flush=True)
            json.dump(log, open(LOG + ".tmp", "w"), indent=1)
            os.replace(LOG + ".tmp", LOG)
    json.dump(log, open(LOG, "w"), indent=1)
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    if a[0] == "--one":
        return one(a[1])
    return run(a[0], set(a[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
