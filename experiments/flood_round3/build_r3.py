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
        if row.get("centre"):
            lat, lon = row["centre"]
        else:                       # the round-2 box was centred on the same point
            b = row["bbox"]
            lat, lon = (b[1] + b[3]) / 2, (b[0] + b[2]) / 2
        bbox = R.square_bbox(lat, lon, SIDE_M)
        t, shape, crs = utm_grid(bbox)
        y, lm = label(ee, n, row, t, shape, crs, bbox)
        meta = {"unit": n, "event": row["event"], "bbox": list(bbox), "centre": [lat, lon], "side_m": SIDE_M,
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


def _features(n, rp, meta):
    """Round 2's feature pipeline for a reference file rp (flooded/valid/meta) -> FR2 table path."""
    from experiments.flood_baselines import build as BUILD
    from experiments.flood_baselines import score as BSCORE
    from experiments.flood_learned import features as FT
    from experiments.flood_learned import fetch as F
    from experiments.flood_round2 import features_r2 as FR2
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
    return FR2.path(n)


def build_box(box: str) -> dict:
    """311 lattice box: features once (reference year FEATURE_YEAR_EVENT); per-event labels stay in r311_refs."""
    from experiments.flood_round3 import rain311 as R3
    units = json.load(open(os.path.join(R3.REFS, "units.json")))
    mine = sorted(n for n, u in units.items() if u["box"] == box)
    z = np.load(os.path.join(R3.REFS, f"{mine[0]}.npz"), allow_pickle=False)
    y = z["y3"]
    m0 = json.loads(str(z["meta"]))
    rp = os.path.join(REFS, f"{box}.npz")
    meta = {"unit": box, "event": R3.FEATURE_YEAR_EVENT, "bbox": m0["bbox"], "grid": m0["grid"], "block": 1,
            "note": "features only; labels per event in r311_refs"}
    if not os.path.exists(rp):
        os.makedirs(REFS, exist_ok=True)
        np.savez_compressed(rp + ".tmp.npz", flooded=(y == 1), valid=(y == 1) | (y == 0),
                            meta=np.array(json.dumps(meta)))
        os.replace(rp + ".tmp.npz", rp)
    p = _features(box, rp, meta)
    return {"table": os.path.basename(p), "events": len(mine)}


def r311():
    from experiments.flood_round3 import rain311 as R3
    units = json.load(open(os.path.join(R3.REFS, "units.json")))
    log_p = LOG.replace(".json", "_r311.json")
    log = json.load(open(log_p)) if os.path.exists(log_p) else {}
    for box in sorted({u["box"] for u in units.values()}):
        rec = log.setdefault(box, {"tries": 0})
        while not rec.get("done") and rec["tries"] < TRIES:
            try:
                r = subprocess.run([sys.executable, "-m", "experiments.flood_round3.build_r3", "--box", box],
                                   timeout=UNIT_KILL_S, capture_output=True, text=True)
                tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
                ok = r.returncode == 0
            except subprocess.TimeoutExpired:
                ok, tail = False, [f"killed after {UNIT_KILL_S} s"]
            rec["tries"] += 1
            rec.update(ok=ok, tail=tail, done=bool(ok and tail and tail[-1].startswith("RESULT ")))
            print(box, json.dumps(rec)[:300], flush=True)
            json.dump(log, open(log_p, "w"), indent=1)
    return 0


def dev(shard=0, shards=1):
    from experiments.flood_baselines.build import check_disk
    log_p = LOG if shards == 1 else LOG.replace(".json", f"_{shard}of{shards}.json")
    log = json.load(open(log_p)) if os.path.exists(log_p) else {}
    os.makedirs(BIG, exist_ok=True)
    for k, n in enumerate(dev_units()):
        if k % shards != shard:
            continue
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
            json.dump(log, open(log_p, "w"), indent=1)
    print("built", sum(1 for r in log.values() if r.get("done")), "of", len(log))
    return 0


S1ROUTE_LOG = os.path.join(BIG, "s1route_log.json")


def s1route_ref(row: dict, ee=None) -> dict:
    """Sentinel-1-route unit (MMFlood §8, Storm Events flash): box by round 4's place() on the 20 km search
    square around the search point (R25: side 8 km), then the v3 Sentinel-1 label in
    [peak - 1 d, peak + MAX_LAG] on that box. Writes REFS/<unit>.npz; returns its meta."""
    import datetime as dt
    from experiments.flood_round3 import labels_r3 as L
    from experiments.flood_round3.relabel_burned import MAX_LAG_DAYS
    from experiments.flood_validation import harness_round4 as H4
    from susceptibility.hydro_rasters import utm_grid
    n = row["unit"]
    rp = os.path.join(REFS, f"{n}.npz")
    if os.path.exists(rp):
        return json.loads(str(np.load(rp, allow_pickle=False)["meta"]))
    if ee is None:
        from experiments.flood_round3.diagnose_ee import _init
        ee = _init()
    H4.BOX_SIDE_M = SIDE_M
    ty = row["tags"][0]
    pk = dt.date.fromisoformat(row["peak_day"])
    pl = H4.place({"ref": ("s1",), "search_centre": tuple(row["search_point"]), "event": row["peak_day"]})
    meta = {"unit": n, "event": row["event"], "peak": row["peak_day"], "type": ty, "side_m": SIDE_M,
            "search_point": row["search_point"], "centre": pl.get("centre"), "bbox": pl.get("bbox"),
            "place": {k: pl.get(k) for k in ("s1_pass", "search_square", "search_square_flooded_cells")}}
    os.makedirs(REFS, exist_ok=True)
    if pl.get("bbox") is None:
        meta.update(flooded_cells=0, dry_cells=0, why="no flood centre in the search square")
        y = np.zeros((1, 1), np.int8) + L.UNOBSERVED
    else:
        bbox = pl["bbox"]
        t, shape, crs = utm_grid(bbox)
        lag = MAX_LAG_DAYS.get(ty, 3)
        t0, t1 = (pk - dt.timedelta(days=1)).isoformat(), (pk + dt.timedelta(days=lag)).isoformat()
        obs = L.observability(ee, t, shape, crs)
        lab = L.s1_label(ee, list(bbox), t0, t1, t, shape, crs)
        y = L.s1_states(lab, obs)
        meta.update(grid={"crs": crs, "transform": list(t)[:6], "shape": list(shape)}, block=1,
                    label_v3={"type": ty, "peak": row["peak_day"], "window": [t0, t1], "kind": "s1_vvdrop",
                              "passes": lab["passes"], "baselines": lab["baselines"]},
                    flooded_cells=int((y == L.FLOODED).sum()), dry_cells=int((y == L.DRY).sum()))
    np.savez_compressed(rp + ".tmp.npz", flooded=(y == L.FLOODED), valid=(y == L.FLOODED) | (y == L.DRY),
                        y3=y.astype(np.int8), meta=np.array(json.dumps(meta, default=str)))
    os.replace(rp + ".tmp.npz", rp)
    return meta


def s1route(cands: str, split: str = "dev", labels_only: bool = True):
    """Label (and optionally feature) every candidate of `split` in results/<cands>.json.
    DEV only until the freeze: a reserve split is refused here."""
    if split != "dev":
        raise SystemExit("reserve units are built only by the frozen heldout_r3 harness")
    from experiments.flood_round3.diagnose_ee import _init
    ee = _init()
    rows = [r for r in json.load(open(os.path.join(OUT, f"{cands}.json")))["candidates"]
            if r.get("split", "dev") == split]
    log = json.load(open(S1ROUTE_LOG)) if os.path.exists(S1ROUTE_LOG) else {}
    for r in rows:
        n = r["unit"]
        rec = log.setdefault(n, {"tries": 0})
        if rec.get("done") or rec["tries"] >= TRIES:
            continue
        rec["tries"] += 1
        try:
            m = s1route_ref(r, ee)
            rec.update(done=True, flooded=m["flooded_cells"], dry=m["dry_cells"], why=m.get("why"))
        except Exception as e:          # noqa: BLE001
            rec.update(error=f"{type(e).__name__}: {str(e)[:160]}")
        print(n, json.dumps(rec)[:200], flush=True)
        json.dump(log, open(S1ROUTE_LOG, "w"), indent=1)
    q = [n for n, v in log.items() if v.get("done") and v.get("flooded", 0) >= 50 and v.get("dry", 0) >= 50]
    print(len(q), "of", len(rows), "qualify (>= 50 flooded and dry cells)")
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    if a[0] == "--box":
        print("RESULT " + json.dumps(build_box(a[1])))
        return 0
    if a[0] == "r311":
        return r311()
    if a[0] == "s1route":           # s1route <candidates file stem> [dev]
        return s1route(a[1], a[2] if len(a) > 2 else "dev")
    if a[0] == "--one":
        res = build_one(a[1])
        print("RESULT " + json.dumps(res))
        return 0
    if a[0] == "dev":
        return dev(*(int(x) for x in a[1:3])) if len(a) > 2 else dev()
    raise SystemExit(f"unknown command {a[0]}")


if __name__ == "__main__":
    raise SystemExit(main())
