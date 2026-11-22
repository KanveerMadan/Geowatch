"""Summaries for DIAGNOSIS.md §e (label agreement) and §i (event typing)."""
import collections
import json
import os

import numpy as np

from experiments.flood_round3 import labels_r3 as L

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def e():
    a = json.load(open(os.path.join(R, "label_agreement.json")))
    rows = [v for v in a.values() if "kappa" in v and v["s1_minus_ems_days"] <= 3 and v["ems_flooded"] >= 50]
    out = collections.defaultdict(list)
    for v in rows:
        cls = "ems_radar" if L.is_radar(v.get("sensors") or []) else "ems_optical"
        for t in v["tags"]:
            out[(t, cls)].append(v)
            out[(t, "all")].append(v)
    res = {}
    for k, v in sorted(out.items()):
        res[f"{k[0]}|{k[1]}"] = {"units": len(v), "kappa_median": round(float(np.median([x["kappa"] for x in v])), 3),
                                "s1_recall_median": round(float(np.median([x["s1_recall_of_ems"] for x in v])), 3),
                                "s1_precision_median": round(float(np.median([x["s1_precision_vs_ems"] for x in v])), 3),
                                "auc_s1_for_ems_median": round(float(np.median([x["auc_s1_for_ems"] for x in v])), 3)}
    res["_errors"] = sum(1 for v in a.values() if "error" in v)
    res["_used"] = len(rows)
    return res


def i():
    cat = json.load(open(os.path.join(R, "burned_catalog.json")))
    im = json.load(open(os.path.join(R, "timing_imerg.json")))
    q = json.load(open(os.path.join(R, "timing_discharge.json")))
    flags = {}
    for n, r in cat.items():
        t = r["tags"]
        f = []
        qq, ii = q.get(n, {}), im.get(n, {})
        rp = qq.get("peak_return_period_y")
        if "fluvial" in t and rp is not None and rp < 1.5 and (qq.get("reach") or {}).get("dsarea_km2", 0) > 500:
            f.append(f"river unit, but the box's main reach peaked at a {rp}-y discharge (no flood wave)")
        if "pluvial" in t and rp is not None and rp >= 5 and (qq.get("reach") or {}).get("dsarea_km2", 0) > 1000:
            f.append(f"rain unit, but a large river in the box peaked at a {rp}-y discharge (river-driven?)")
        if ("compound" in t or "coastal" in t) and (r.get("lag_days_min") or 0) > 14:
            f.append(f"surge-type unit imaged {r.get('lag_days_min')} d after the event (surge long gone)")
        if ii and ii.get("peak_3day_mm", 0) < 20 and ("pluvial" in t or "flash_flood" in t):
            f.append(f"rain-driven type, but IMERG shows only {ii['peak_3day_mm']} mm in the peak 3 days")
        if f:
            flags[n] = {"tags": t, "flags": f}
    per_type = collections.Counter(tt for v in flags.values() for tt in v["tags"])
    tot = collections.Counter(tt for r in cat.values() for tt in r["tags"])
    return {"flagged": flags, "per_type": {k: f"{per_type[k]} of {tot[k]}" for k in tot}}


if __name__ == "__main__":
    print(json.dumps(e(), indent=1))
    r = i()
    print(json.dumps(r["per_type"], indent=1))
    for n, v in r["flagged"].items():
        print(n, v)
