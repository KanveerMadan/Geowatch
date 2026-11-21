"""
Build inputs and feature tables for flood_final units, one unit at a time,
each in a killable subprocess (Earth Engine / Overpass calls can hang).

    python -m experiments.flood_final.build_units --dev            # the 38 new DEV units
    python -m experiments.flood_final.build_units --one <unit>     # (internal)

Per unit, each step cached and skipped when done:
  1. flood_baselines inputs (build.build_unit: MERIT, FABDEM slope, CHIRPS,
     IMERG, clay, JRC, distance to water) -> BUILD.path(unit)
  2. learned-model layers (flood_learned.fetch.fetch_unit, incl. coastal /
     GHSL extras) -> fetch.path(unit)
  3. feature table (flood_learned.features.build_table) -> features.path(unit)
The pluvial module's inputs are not built here (an hour per unit; DECISIONS.md D8).
Reserved units are refused here; they are built only by the held-out pass.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

import numpy as np

from experiments.flood_core.registry import registry as REG

REF_DIR = os.path.expanduser("~/.cache/geowatch/flood_learned/heldout/refs")
UNIT_KILL_S = 2 * 1800          # two of harness_round4's per-build deadlines (1800 s)
LOG = os.path.expanduser("~/.cache/geowatch/flood_final/build_units_log.json")


def dev_new_units(reg=None) -> list:
    reg = reg or REG.load()
    return [u for u in reg["units"] if u["role"] == "dev"
            and any(x.get("round") == "flood_final" for x in u.get("uses", []))]


def entry(name: str) -> dict:
    reg = REG.load()
    u = REG.units(reg)[name]
    if u["role"] != "dev":
        raise RuntimeError(f"{name}: role {u['role']!r}; build_units builds DEV units only")
    p = os.path.join(REF_DIR, f"{name}.npz")
    z = np.load(p, allow_pickle=False)
    meta = json.loads(str(z["meta"]))
    return {"unit": name, "path": p, "meta": meta, "round": "flood_final", "split": "dev",
            "modules": [], "uses": []}


def build_one(name: str) -> dict:
    from experiments.flood_baselines import build as BUILD
    from experiments.flood_baselines import score as BSCORE
    from experiments.flood_learned import features as FT
    from experiments.flood_learned import fetch as F
    e = entry(name)
    done = {}
    if not os.path.exists(BUILD.path(name)):
        BUILD.save(name, BUILD.build_unit(e))
        done["baseline"] = True
    if not os.path.exists(F.path(name)):
        arrays, meta = F.fetch_unit(e)
        F.save(name, arrays, meta)
        done["fetch"] = meta["errors"]
    if not os.path.exists(FT.path(name)) or os.path.getmtime(FT.path(name)) < os.path.getmtime(F.path(name)):
        t = FT.build_table(e, BSCORE.round4_chosen())
        FT.save(name, t)
        done["table"] = {k: t["meta"][k] for k in ("n_flooded", "n_dry", "n_unobserved")}
    return done


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--one")
    args = ap.parse_args(argv)
    if args.one:
        import ee
        from experiments.flood_validation import references as R
        from ingestion.gee_client import initialize_gee
        initialize_gee()
        ee.data.setDeadline(R.EE_TIMEOUT_S * 1000)
        print(json.dumps(build_one(args.one), default=str)[:600], flush=True)
        return 0
    from experiments.flood_baselines.build import check_disk
    from experiments.flood_learned import features as FT
    log = json.load(open(LOG)) if os.path.exists(LOG) else {}
    for u in dev_new_units():
        n = u["event_id"]
        if os.path.exists(FT.path(n)):
            continue
        if log.get(n, {}).get("attempts", 0) >= 3:          # brief: 3 tries, then missing
            continue
        check_disk()
        t0 = time.time()
        print(f"── {n}", flush=True)
        try:
            r = subprocess.run([sys.executable, "-m", "experiments.flood_final.build_units",
                                "--one", n], timeout=UNIT_KILL_S, capture_output=True, text=True)
            ok, tail = r.returncode == 0, (r.stdout + r.stderr).strip().splitlines()[-3:]
        except subprocess.TimeoutExpired:
            ok, tail = False, [f"killed after {UNIT_KILL_S} s"]
        rec = log.setdefault(n, {"attempts": 0})
        rec["attempts"] += 0 if ok else 1
        rec.update(ok=ok, s=round(time.time() - t0), tail=tail)
        print(f"   {n}: {json.dumps(rec, default=str)[:400]}", flush=True)
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "w") as fh:
            json.dump(log, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
