"""
Round 3, Phase 2: rebuild BURNED units' labels under labels_r3 (v3 rules), on
each unit's existing 30 m grid, so its feature table stays valid.

    python -m experiments.flood_round3.relabel_burned build    # Earth Engine, one unit at a time, resumable
    python -m experiments.flood_round3.relabel_burned score    # round-2 predictions vs v3 labels -> results/v3_burned_scores.json

Per unit:
- S1 units: v3 S1 label from every pass in [peak, peak + MAX_LAG[type]]. The peak is the
  IMERG rain peak (timing_imerg.json), or the GEOGloWS discharge peak for river units
  where it exists (timing_discharge.json).
- EMS / UNOSAT units: the published label, unchanged. The v3 observability rules apply
  (radar rules only if the product's images are radar). A unit whose label image is
  later than MAX_LAG is marked `late`: kept for diagnosis, excluded from the v3 design.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time

import numpy as np

from experiments.flood_round3 import labels_r3 as L

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/v3_labels")
# Fixed from DIAGNOSIS.md §b before the reserve is sealed (see DECISIONS R19).
MAX_LAG_DAYS = {"pluvial": 1, "flash_flood": 2, "fluvial": 3, "coastal": 2, "compound": 2, "waterlogging": 14,
                "snowmelt": 3, "dam_breach": 2}


def _peaks():
    im = json.load(open(os.path.join(OUT, "timing_imerg.json")))
    q = {}
    p = os.path.join(OUT, "timing_discharge.json")
    if os.path.exists(p):
        q = json.load(open(p))
    return im, q


def peak_day(n, row, im, q):
    """(peak date, basis). River-led types use the discharge peak when one was found
    with a return period >= 1.5 y (a real flood wave at that reach), else the rain peak."""
    t = row["tags"][0]
    if t in ("fluvial", "snowmelt", "waterlogging") and n in q and q[n].get("peak_day") \
            and (q[n].get("peak_return_period_y") or 0) >= 1.5:
        return q[n]["peak_day"], "geoglows_discharge"
    if n in im:
        return im[n]["rain_peak_day"], "imerg_rain"
    return row["event"], "registry_event"


def build():
    from experiments.flood_round3.diagnose_ee import _init
    from affine import Affine
    ee = _init()
    cat = json.load(open(os.path.join(OUT, "burned_catalog.json")))
    im, q = _peaks()
    os.makedirs(CACHE, exist_ok=True)
    for n, row in sorted(cat.items()):
        p = os.path.join(CACHE, f"{n}.npz")
        if os.path.exists(p):
            continue
        # the feature table's grid is authoritative: v3 labels must align with its rows
        g = json.loads(str(np.load(os.path.expanduser(row["table"]), allow_pickle=False)["meta"]))["grid"]
        t, shape, crs = Affine(*g["transform"][:6]), tuple(g["shape"]), g["crs"]
        ty = row["tags"][0]
        pk, basis = peak_day(n, row, im, q)
        lag = MAX_LAG_DAYS.get(ty, 3)
        meta = {"unit": n, "type": ty, "peak": pk, "peak_basis": basis, "max_lag_days": lag, "kind": row.get("kind")}
        try:
            obs = L.observability(ee, t, shape, crs)
            if row.get("kind") == "s1_vvdrop":
                t1 = (dt.date.fromisoformat(pk) + dt.timedelta(days=lag)).isoformat()
                lab = L.s1_label(ee, row["bbox"], pk, t1, t, shape, crs)
                y = L.s1_states(lab, obs)
                meta.update(passes=lab["passes"], baselines=lab["baselines"], late=False)
            else:
                ref = np.load(os.path.expanduser(row["ref_path"]), allow_pickle=False)
                if ref["flooded"].shape != shape:
                    raise ValueError(f"reference shape {ref['flooded'].shape} != table grid {shape}")
                radar = L.is_radar(row.get("sensors") or [])
                y = L.apply_states(ref["flooded"], ref["valid"], obs, radar=radar)
                img = min(x[:10] for x in row["images"]) if row.get("images") else None
                late = img is None or (dt.date.fromisoformat(img) - dt.date.fromisoformat(pk)).days > lag
                meta.update(radar=radar, image=img, late=bool(late))
            np.savez_compressed(p, y=y.ravel().astype(np.int8), meta=json.dumps(meta))
            print(n, ty, meta.get("late"), int((y == 1).sum()), int((y == 0).sum()), flush=True)
        except Exception as e:      # noqa: BLE001
            np.savez_compressed(p, error=f"{type(e).__name__}: {str(e)[:240]}", meta=json.dumps(meta))
            print(n, "ERROR", type(e).__name__, str(e)[:160], flush=True)
        time.sleep(1.0)
    return 0


def predictions(cat):
    """{unit: {cand: score array}}: DEV from round-2 leave-region-out runs; round-2
    test units from the round-2 final models (trained on all DEV), as scored there."""
    import pickle
    from experiments.flood_round2 import model_v3 as M3
    runs = M3.load_runs("lro")
    finals = {c: pickle.load(open(os.path.join(M3.CACHE, f"final__{c}.pkl"), "rb"))["model"]
              for c in ("full_lr", "resid_lgbm", "flash_lgbm", "coastal_lgbm", "full_lgbm")}
    out = {}
    for n, row in cat.items():
        if row["role"] == "dev":
            out[n] = {c: runs[c][n].astype(np.float64) for c in M3.ORDER}
            continue
        z = np.load(os.path.expanduser(row["table"]), allow_pickle=False)
        t = {"X": z["X"], "C": z["C"]}
        out[n] = {c: M3.predict(c, finals.get(c), t).astype(np.float64) for c in M3.ORDER}
    return out


def score():
    """Per-unit AUC of every round-2 candidate on v3 labels (and on the old labels, same
    units), per-type gain spread and the power table recomputed on v3 labels."""
    from scipy.stats import norm
    from experiments.flood_round3.diagnose import LEARNED_FOR, TYPES
    from experiments.flood_validation.harness import auc
    cat = json.load(open(os.path.join(OUT, "burned_catalog.json")))
    preds = predictions(cat)
    per = {}
    for n, row in cat.items():
        p = os.path.join(CACHE, f"{n}.npz")
        if not os.path.exists(p):
            continue
        z = np.load(p, allow_pickle=False)
        meta = json.loads(str(z["meta"]))
        if "error" in z.files:
            per[n] = {"error": str(z["error"]), **meta}
            continue
        y3 = z["y"]
        y2 = np.load(os.path.expanduser(row["table"]), allow_pickle=False)["y"]
        rec = {"tags": row["tags"], "kind": row.get("kind"), "late": meta.get("late"), "role": row["role"],
               "v3_flooded": int((y3 == 1).sum()), "v3_dry": int((y3 == 0).sum())}
        for tag, y in (("v3", y3), ("old", y2)):
            ok = (y == 0) | (y == 1)
            for r in preds[n].values():
                ok &= np.isfinite(r)
            yy = y[ok]
            if (yy == 1).sum() < 50 or (yy == 0).sum() < 50:
                rec[tag] = None
                continue
            rec[tag] = {c: round(float(auc(r[ok], (yy == 1).astype(int), (yy == 0).astype(int))), 4)
                        for c, r in preds[n].items()}
        per[n] = rec
    z = norm.ppf(0.975) + norm.ppf(0.90)
    summ = {}
    for ty in TYPES:
        lc = LEARNED_FOR[ty]
        for tag in ("old", "v3"):
            g, e, h, l = [], [], [], []
            for n, r in per.items():
                if ty not in r.get("tags", []) or not r.get(tag) or (tag == "v3" and r.get("late")):
                    continue
                a = r[tag]
                bb = "elev" if a["elev"] >= a["hand"] else "hand"
                g.append(a[lc] - a[bb]); e.append(a["elev"]); h.append(a["hand"]); l.append(a[lc])
            if len(g) < 3:
                summ.setdefault(ty, {})[tag] = {"units": len(g)}
                continue
            sd = float(np.std(g, ddof=1))
            summ.setdefault(ty, {})[tag] = {
                "units": len(g), "elev": round(float(np.mean(e)), 3), "hand": round(float(np.mean(h)), 3),
                "learned": round(float(np.mean(l)), 3), "gain_mean": round(float(np.mean(g)), 4), "gain_sd": round(sd, 4),
                "units_needed_plus30": {f"delta_{d}": int(np.ceil(1.3 * (z * sd / d) ** 2)) for d in (0.03, 0.05, 0.08)}}
    json.dump({"per_unit": per, "by_type": summ}, open(os.path.join(OUT, "v3_burned_scores.json"), "w"), indent=1)
    print(json.dumps(summ, indent=1))
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    return {"build": build, "score": score}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
