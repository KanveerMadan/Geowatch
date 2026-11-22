"""
Round 3: units on R24's 8 km boxes. The labels are v3 and the features are round 2's own pipeline, unchanged.

    python -m experiments.flood_round3.build_r3 dev            # burned in-window units, one subprocess each, resumable
    python -m experiments.flood_round3.build_r3 --one <unit>   # (internal)

**Per unit:**
1. **Box:** an 8 km square on the unit's round-2 centre. That centre came from round 4's `place()`: the flood centre of the label in the AOI or search square. This is the same rule as rounds 1–2; only the side changes (R24).
2. **Label (v3, `labels_r3`):**
   - Sentinel-1 units: every pass in [peak, peak + MAX_LAG];
   - EMS units: the published product rasterised on the new grid (round 4's `ems_reference`), with the v3 observability states.
   - Written as a reference file: `flooded` = FLOODED, `valid` = FLOODED or DRY.
3. **Features:** `flood_baselines.build.build_unit`, then `flood_learned.fetch.fetch_unit`, then `features.build_table`, then `flood_round2.features_r2.build`.
   - All caches sit under ~/.cache/geowatch/flood_round3/big/, so no round-2 cache is touched.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import time

BIG = os.path.expanduser("~/.cache/geowatch/flood_round3/big")
os.environ.setdefault("GEOWATCH_BASELINE_CACHE", os.path.join(BIG, "baseline"))
os.environ.setdefault("GEOWATCH_LEARNED_CACHE", os.path.join(BIG, "inputs"))
os.environ.setdefault("GEOWATCH_LEARNED_TABLES", os.path.join(BIG, "tables_l"))

import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
REFS = os.path.join(BIG, "refs")
TABLES = os.path.join(BIG, "tables")
LOG = os.path.join(BIG, "build_log.json")
SIDE_M = 8000.0            # R24
UNIT_KILL_S = 5400
TRIES = 2


def dev_units() -> list:
    s = json.load(open(os.path.join(OUT, "v3_burned_scores.json")))["per_unit"]
    return sorted(n for n, r in s.items() if "error" not in r and not r.get("late"))


def _ems_ids(source: str):
    m = re.search(r"(EMSR\d+) AOI(\d+).*?(DEL|GRA) monitoring (\d+)", source)
    if not m:
        raise ValueError(f"cannot parse EMS source: {source!r}")
    return m.group(1), int(m.group(2)), int(m.group(4)), m.group(3)


def label(ee, n, row, t, shape, crs, bbox):
    from experiments.flood_round3 import labels_r3 as L
    from experiments.flood_round3.relabel_burned import MAX_LAG_DAYS, _peaks, peak_day
    from experiments.flood_validation import references as R
    im, q = _peaks()
    ty = row["tags"][0]
    pk, basis = peak_day(n, row, im, q)
    lag = MAX_LAG_DAYS.get(ty, 3)
    obs = L.observability(ee, t, shape, crs)
    meta = {"type": ty, "peak": pk, "peak_basis": basis, "max_lag_days": lag, "kind": row.get("kind")}
    if row.get("kind") == "s1_vvdrop":
        t1 = (dt.date.fromisoformat(pk) + dt.timedelta(days=lag)).isoformat()
        lab = L.s1_label(ee, list(bbox), pk, t1, t, shape, crs)
        y = L.s1_states(lab, obs)
        meta.update(passes=lab["passes"], baselines=lab["baselines"])
    elif row.get("kind") == "ems":
        code, aoi, mon, typ = _ems_ids(row["source"])
        ref = R.ems_reference(R.ems_product(code, aoi, mon, typ), bbox, t, shape, crs)
        y = L.apply_states(ref["flooded"], ref["valid"], obs, radar=L.is_radar(row.get("sensors") or []))
        meta.update(source=row["source"], images=row.get("images"))
    else:
        raise ValueError(f"kind {row.get('kind')} not rebuilt")
    return y, meta


def build_one(n: str) -> dict:
    from experiments.flood_baselines import build as BUILD
    from experiments.flood_baselines import score as BSCORE
    from experiments.flood_learned import features as FT
    from experiments.flood_learned import fetch as F
    from experiments.flood_round2 import features_r2 as FR2
    from experiments.flood_round3 import labels_r3 as L
    from experiments.flood_round3.diagnose_ee import _init
    from experiments.flood_validation import references as R
    from susceptibility.hydro_rasters import utm_grid
    cat = json.load(open(os.path.join(OUT, "burned_catalog.json")))
    row = cat[n]
    os.makedirs(REFS, exist_ok=True)
    rp = os.path.join(REFS, f"{n}.npz")
    if not os.path.exists(rp):
        ee = _init()
        lat, lon = row["centre"]
        bbox = R.square_bbox(lat, lon, SIDE_M)
        t, shape, crs = utm_grid(bbox)
        y, lm = label(ee, n, row, t, shape, crs, bbox)
        meta = {"unit": n, "event": row["event"], "bbox": list(bbox), "centre": row["centre"], "side_m": SIDE_M,
                "grid": {"crs": crs, "transform": list(t)[:6], "shape": list(shape)}, "block": 1,
                "label_v3": lm, "flooded_cells": int((y == L.FLOODED).sum()), "dry_cells": int((y == L.DRY).sum())}
        np.savez_compressed(rp + ".tmp.npz", flooded=(y == L.FLOODED), valid=(y == L.FLOODED) | (y == L.DRY),
                            y3=y.astype(np.int8), meta=np.array(json.dumps(meta, default=str)))
        os.replace(rp + ".tmp.npz", rp)
    meta = json.loads(str(np.load(rp, allow_pickle=False)["meta"]))
    if meta["flooded_cells"] < 50 or meta["dry_cells"] < 50:
        return {"not_qualifying": [meta["flooded_cells"], meta["dry_cells"]]}
    e = {"unit": n, "path": rp, "meta": meta, "round": "flood_round3", "split": "dev", "modules": [], "uses": []}
    if not os.path.exists(BUILD.path(n)):
        BUILD.save(n, BUILD.build_unit(e))
    if not os.path.exists(F.path(n)):
        arrays, fm = F.fetch_unit(e)
        F.save(n, arrays, fm)
    if not os.path.exists(FT.path(n)):
        FT.save(n, FT.build_table(e, BSCORE.round4_chosen()))
    FR2.CACHE = TABLES
    FR2.SRC_TABLES = [FT.CACHE]
    FR2.SRC_INPUTS = [F.CACHE]
    if not os.path.exists(FR2.path(n)):
        FR2.build(n)
    z = np.load(FR2.path(n), allow_pickle=False)
    return {"flooded": int((z["y"] == 1).sum()), "dry": int((z["y"] == 0).sum()), "cells": int(len(z["y"]))}


def dev():
    from experiments.flood_baselines.build import check_disk
    log = json.load(open(LOG)) if os.path.exists(LOG) else {}
    os.makedirs(BIG, exist_ok=True)
    for n in dev_units():
        rec = log.setdefault(n, {"tries": 0})
        if rec.get("done"):
            continue
        while not rec.get("done") and rec["tries"] < TRIES:
            check_disk()
            t0 = time.time()
            try:
                r = subprocess.run([sys.executable, "-m", "experiments.flood_round3.build_r3", "--one", n],
                                   timeout=UNIT_KILL_S, capture_output=True, text=True)
                out = (r.stdout + r.stderr).strip().splitlines()
                ok = r.returncode == 0
                tail = out[-3:]
            except subprocess.TimeoutExpired:
                ok, tail = False, [f"killed after {UNIT_KILL_S} s"]
            rec["tries"] += 1
            rec.update(ok=ok, tail=tail, s=round(time.time() - t0))
            if ok and tail and tail[-1].startswith("RESULT "):
                rec["result"] = json.loads(tail[-1][7:])
                rec["done"] = True
            print(n, json.dumps(rec)[:300], flush=True)
            json.dump(log, open(LOG, "w"), indent=1)
    print("built", sum(1 for r in log.values() if r.get("done")), "of", len(log))
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    if a[0] == "--one":
        res = build_one(a[1])
        print("RESULT " + json.dumps(res))
        return 0
    return {"dev": dev}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
