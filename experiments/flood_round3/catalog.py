"""
Round 3, Phase 1: catalogue of every BURNED unit (round-2 DEV, which includes
the round-1 test units, plus the 55 built round-2 reserved units, now burned).

    python -m experiments.flood_round3.catalog      # writes results/burned_catalog.json

Per unit: role (dev | r2_test), tags, region, cluster, reference source kind,
event date, label-image date(s), lag in days, flooded / dry counts, table path.
Metadata only; no model is read here.
"""
from __future__ import annotations

import glob
import json
import os
from datetime import date

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
C = os.path.expanduser("~/.cache/geowatch")
REF_DIRS = [f"{C}/flood_round2/heldout/refs", f"{C}/flood_round2/dev_refs/refs", f"{C}/flood_final/heldout/refs",
            f"{C}/flood_learned/heldout/refs", f"{C}/flood_refs/round2", f"{C}/flood_refs/round3",
            f"{C}/flood_refs/round4/test", f"{C}/flood_refs/round4/tuning"]
DEV_TABLES = f"{C}/flood_round2/tables"
R2_TABLES = f"{C}/flood_round2/heldout/tables_r2"
DEV_UNITS = f"{C}/flood_round2/model_v3/dev_units.json"
R2_RESULT = os.path.join(os.path.dirname(HERE), "flood_round2", "results", "heldout_r2.json")


TYPES_PREFIX = ("fluvial", "pluvial", "waterlogging", "flash_flood", "coastal")


def find_ref(n):
    """Newest format first; old rounds store refs as <type>__<unit>.npz."""
    for d in REF_DIRS:
        for cand in (n, n[2:] if n.startswith("r_") else "r_" + n) + tuple(f"{t}__{n}" for t in TYPES_PREFIX):
            p = os.path.join(d, f"{cand}.npz")
            if os.path.exists(p):
                return p
    return None


def _d(s):
    return date.fromisoformat(str(s)[:10]) if s else None


def ref_meta(p):
    m = json.loads(str(np.load(p, allow_pickle=False)["meta"]))
    r = m.get("reference", {}) or {}
    src = r.get("source", "")
    if "S1_GRD" in src or "Sentinel-1" in src:
        kind, imgs = "s1_vvdrop", [r.get("event_image_date") or (m.get("s1_pass") or {}).get("date")]
    elif "EMS" in src:
        kind, imgs = "ems", [i.get("acquired") for i in r.get("images", [])]
    elif "UNOSAT" in src:
        kind, imgs = "unosat", [i.get("acquired") for i in r.get("images", [])] or [r.get("image_date")]
    else:
        kind, imgs = (src.split()[0].lower() if src else "unknown"), [r.get("image_date") or r.get("event_image_date")]
    imgs = [i for i in imgs if i]
    ev = _d(m.get("event"))
    lags = [(_d(i) - ev).days for i in imgs] if ev else []
    sensors = sorted({i.get("sensor") for i in r.get("images", []) if isinstance(i, dict) and i.get("sensor")})
    return {"source": src[:160], "kind": kind, "event": str(ev) if ev else None, "images": imgs,
            "sensors": sensors or (["Sentinel-1"] if kind == "s1_vvdrop" else []),
            "lag_days_min": min(lags) if lags else None, "lag_days_max": max(lags) if lags else None,
            "centre": m.get("centre"), "bbox": m.get("bbox"), "grid": m.get("grid")}


def build():
    dev = json.load(open(DEV_UNITS))
    r2 = json.load(open(R2_RESULT))
    rows = {}
    for n in dev["names"]:
        rows[n] = {"role": "dev", "tags": dev["tags"][n], "region": dev["region"][n],
                   "cluster": f"c{dev['clusters'][n]}", "table": os.path.join(DEV_TABLES, f"{n}.npz")}
    for n, u in r2["units"].items():
        rows[n] = {"role": "r2_test", "tags": u["tags"], "region": u["region"], "cluster": u["cluster"],
                   "table": os.path.join(R2_TABLES, f"{n}.npz")}
    for n, r in rows.items():
        p = find_ref(n)
        r["ref_path"] = p
        if p:
            r.update(ref_meta(p))
        y = np.load(os.path.expanduser(r["table"]))["y"]
        r["flooded"], r["dry"] = int((y == 1).sum()), int((y == 0).sum())
        r["unobserved"] = int((y < 0).sum())
    home = os.path.expanduser("~")
    for r in rows.values():                 # no home paths in committed files
        for k in ("table", "ref_path"):
            if r.get(k):
                r[k] = r[k].replace(home, "~", 1)
    os.makedirs(OUT, exist_ok=True)
    json.dump(rows, open(os.path.join(OUT, "burned_catalog.json"), "w"), indent=1)
    return rows


if __name__ == "__main__":
    rows = build()
    import collections
    print(len(rows), "units;", sum(r.get("ref_path") is None for r in rows.values()), "without a reference file")
    print(collections.Counter(r.get("kind") for r in rows.values()))
    print(collections.Counter(t for r in rows.values() for t in r["tags"]))
    miss = [n for n, r in rows.items() if r.get("ref_path") is None]
    print("no ref:", miss[:40])
