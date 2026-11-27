"""
M6–M8 v2: corridor diagnostic (decisions.md 2026-11-27, fixed before any corridor number).

    cd ~/gw-r3pin-r35 && PYTHONPATH=.:$HOME/gw-m678v2/experiments/flood_m678 python -B ~/gw-m678v2/experiments/flood_m678/v2/corridor.py [--limit N]

For each DEV lead with a usable 8 km box label (M8 sustained melt first):
- 40 km domain around the anchor; v2 labels on the whole domain (same scenes, same rules);
- network upa >= 10 km2; corridor = within 1.5 km of the network and HAND <= 30 m;
- physics under forcing variants: real, seasonal, exchanged, x0.5, x2;
- reports AUCs (variants, elevation, HAND), Spearman(real, seasonal), share of corridor cells whose
  predicted wet status flips, wet-extent direction with Q. Results: v2/corridor_results.json (DEV).
Diagnostic only: never the primary footprint.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import numpy as np

V2 = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(V2))


def _load(n):
    spec = importlib.util.spec_from_file_location(f"v2{n}", os.path.join(V2, f"{n}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


S, R, F, LB, DT = _load("storage"), _load("routing"), _load("forcing"), _load("labels"), _load("dev_tables")
DOMAIN_M, BUFFER_M, HAND_MAX, UPA_NET = 40000.0, 1500.0, 30.0, 10.0
OUT = os.path.join(V2, "corridor_results.json")


def corridor_mask(T):
    from scipy.ndimage import distance_transform_edt
    net = np.nan_to_num(T["upa"]) >= UPA_NET
    if not net.any():
        return net
    d = distance_transform_edt(~net) * 30.0
    return (d <= BUFFER_M) & (np.nan_to_num(T["hand"], nan=1e9) <= HAND_MAX)


def phys_for(T, q, upa_g):
    ch, st = DT.stages(T, q, upa_g)
    g, lv = R.channel_groups(T["z"], ch, st)          # same 8 bins as the box score
    return R.physics_score(T["z"], g, lv) if g else np.full(T["z"].shape, np.nan)


def auc(s, y, m):
    from experiments.flood_validation.harness import auc as A
    k = m & np.isfinite(s) & np.isin(y, (0, 1))
    if (y[k] == 1).sum() < 50 or (y[k] == 0).sum() < 50:
        return None
    a = A(s[k], (y[k] == 1).astype(int), (y[k] == 0).astype(int))
    return None if a is None else round(float(a), 4)


def run(limit=None):
    import labels_m678 as LM
    import requests
    from scipy.stats import spearmanr
    from experiments.flood_validation import references as Rf
    S.init()
    ee = LM.init_ee()
    qtab = DT.wsc_discharge()
    tables = S.dev_path("tables")
    done = json.load(open(OUT)) if os.path.exists(OUT) else {}
    units = []
    for f in sorted(os.listdir(tables)) if os.path.isdir(tables) else []:
        if f.endswith(".npz"):
            m = json.loads(str(np.load(os.path.join(tables, f), allow_pickle=False)["meta"]))
            if m.get("q_peak") and m.get("q_median"):
                units.append((f, m))
    ratios = [m["q_peak"] / m["q_median"] for _, m in units]
    for k, (f, m) in enumerate(units[:limit] if limit else units):
        if f in done:
            continue
        lead = {"lead_id": m["lead"], "type": m["type"], "submode": m["submode"], "date": m["date"],
                "crest_utc_min": m["crest_utc"][0], "crest_utc_max": m["crest_utc"][1]}
        lat0, lon0 = (np.mean(m["search_square"][1::2]), np.mean(m["search_square"][0::2]))
        scenes, lo, hi = LB.scenes_for(lead, lat0, lon0, requests.Session())
        radar = [dict(s, scene_orbit=LM.s1_relative_orbit(s["scene"])) for s in scenes
                 if s["collection"] == "sentinel-1-grd" and s.get("baseline")]
        optical = [s for s in scenes if s["collection"] != "sentinel-1-grd"]
        dom = Rf.square_bbox(lat0, lon0, DOMAIN_M)
        t, shape, crs, T = DT.terrain(ee, dom)
        lab = LB.domain_labels(ee, optical, radar, lo, hi, dom, t, shape, crs)
        if lab is None:
            done[f] = {"dropout": "no label source on the corridor domain"}
            continue
        y = lab["state"]
        cm = corridor_mask(T)
        upa_g = float(np.nanmax(T["upa"]))
        q, qmed = m["q_peak"], m["q_median"]
        other = ratios[(k + 1) % len(ratios)] if len(ratios) > 1 else q / qmed
        var = {"real": q, "seasonal": qmed, "exchanged": qmed * other, "half": 0.5 * q, "double": 2.0 * q}
        sc = {v: phys_for(T, qq, upa_g) for v, qq in var.items()}
        res = {"flooded": int(((y == 1) & cm).sum()), "dry": int(((y == 0) & cm).sum()),
               "corridor_cells": int(cm.sum()), "q": var}
        res["auc"] = {v: auc(s, y, cm) for v, s in sc.items()}
        res["auc"]["elev"] = auc(-T["z"], y, cm)
        res["auc"]["hand"] = auc(-T["hand"], y, cm)
        ok = cm & np.isfinite(sc["real"]) & np.isfinite(sc["seasonal"])
        res["spearman_real_seasonal"] = round(float(spearmanr(sc["real"][ok], sc["seasonal"][ok]).correlation), 5) if ok.sum() > 100 else None
        res["wet_flip_share"] = round(float(((sc["real"] > 0) != (sc["seasonal"] > 0))[ok].mean()), 5) if ok.sum() else None
        wet = {v: float((s[cm] > 0).mean()) for v, s in sc.items() if np.isfinite(s[cm]).any()}
        res["wet_extent"] = {k2: round(v2, 4) for k2, v2 in wet.items()}
        res["direction_ok"] = bool(wet.get("half", 0) <= wet.get("real", 0) <= wet.get("double", 0))
        done[f] = res
        json.dump(done, open(OUT, "w"), indent=1, sort_keys=True)
        print(f, json.dumps({k3: res[k3] for k3 in ("flooded", "dry", "auc", "spearman_real_seasonal", "wet_flip_share", "direction_ok")}), flush=True)
    summarize(done)


def summarize(done):
    use = [r for r in done.values() if r.get("auc") and r["auc"].get("real") is not None and r["auc"].get("seasonal") is not None]
    if not use:
        print("no usable corridor units yet")
        return
    d = [abs(r["auc"]["real"] - r["auc"]["seasonal"]) for r in use]
    sp = [r["spearman_real_seasonal"] for r in use if r["spearman_real_seasonal"] is not None]
    s = {"usable_units": len(use), "median_abs_auc_real_minus_seasonal": round(float(np.median(d)), 4),
         "median_spearman_real_seasonal": round(float(np.median(sp)), 5) if sp else None,
         "stop_rule_met": bool(len(use) >= 20 and np.median(d) < 0.005 and sp and np.median(sp) > 0.99),
         "stop_rule_evaluable": len(use) >= 20}
    print(json.dumps(s))
    json.dump({**done, "_summary": s}, open(OUT, "w"), indent=1, sort_keys=True)


if __name__ == "__main__":
    a = sys.argv[1:]
    run(int(a[a.index("--limit") + 1]) if "--limit" in a else None)
