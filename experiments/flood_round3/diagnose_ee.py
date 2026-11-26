"""
Round 3, Phase 1, parts needing new data (burned units only).

    python -m experiments.flood_round3.diagnose_ee timing    # IMERG rain peak per unit -> results/timing_imerg.json
    python -m experiments.flood_round3.diagnose_ee agree     # S1 VV-drop vs EMS labels on the same grid -> results/label_agreement.json

Throttled: one small Earth Engine request at a time, cached per unit (resumable).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/diag_ee")
IMERG = "NASA/GPM_L3/IMERG_V07"
DAYS_BEFORE, DAYS_AFTER = 14, 3
BUFFER_M = 25_000          # rain over the box and its surroundings (upstream catchment proxy)


def _init():
    import ee
    from dotenv import dotenv_values
    from experiments.flood_round3 import ee_lock
    ee_lock.install()                      # R33: shared lock with other local EE clients
    env = dotenv_values(os.path.expanduser("~/geowatch/.env"))
    ee.Initialize(project=env.get("GEE_PROJECT_ID") or os.environ.get("GEE_PROJECT_ID"))
    return ee


def rain_series(ee, bbox, event):
    e = dt.date.fromisoformat(event)
    region = ee.Geometry.Rectangle(list(bbox)).buffer(BUFFER_M)
    days = [e + dt.timedelta(days=k) for k in range(-DAYS_BEFORE, DAYS_AFTER + 1)]
    col = ee.ImageCollection(IMERG).select("precipitation")
    bands = [col.filterDate(d.isoformat(), (d + dt.timedelta(days=1)).isoformat()).sum().multiply(0.5)
             .rename(d.isoformat()) for d in days]
    img = ee.Image.cat(bands)
    r = img.reduceRegion(ee.Reducer.mean(), region, 10000, maxPixels=1e9).getInfo()
    rmax = img.reduceRegion(ee.Reducer.max(), region, 10000, maxPixels=1e9).getInfo()
    return {d.isoformat(): r.get(d.isoformat()) for d in days}, {d.isoformat(): rmax.get(d.isoformat()) for d in days}


def timing():
    ee = _init()
    cat = json.load(open(os.path.join(OUT, "burned_catalog.json")))
    os.makedirs(os.path.join(CACHE, "imerg"), exist_ok=True)
    out = {}
    for n, row in sorted(cat.items()):
        p = os.path.join(CACHE, "imerg", f"{n}.json")
        if not os.path.exists(p):
            if not row.get("event") or not row.get("bbox") or row["event"] < "2000-06-01":
                continue
            for k in range(3):
                try:
                    mean, mx = rain_series(ee, row["bbox"], row["event"])
                    json.dump({"mean": mean, "max": mx}, open(p, "w"))
                    break
                except Exception as e:      # noqa: BLE001
                    print(f"{n}: {type(e).__name__}: {str(e)[:160]}", flush=True)
                    time.sleep(10 * (k + 1))
            else:
                continue
            time.sleep(1.0)
        s = json.load(open(p))["mean"]
        days = sorted(s)
        v = np.array([s[d] or 0.0 for d in days])
        # peak = the day with the largest 3-day centred sum (storm total), first if tied
        k3 = np.convolve(v, np.ones(3), mode="same")
        i = int(np.argmax(k3))
        peak = days[i]
        ev = dt.date.fromisoformat(row["event"])
        img = row.get("images") or []
        img_d = min(dt.date.fromisoformat(x[:10]) for x in img) if img else None
        out[n] = {"event": row["event"], "rain_peak_day": peak,
                  "peak_minus_event_days": (dt.date.fromisoformat(peak) - ev).days,
                  "image_minus_rain_peak_days": None if img_d is None else (img_d - dt.date.fromisoformat(peak)).days,
                  "peak_3day_mm": round(float(k3[i]), 1), "total_mm": round(float(v.sum()), 1),
                  "max_day_mm": round(float(v.max()), 1), "tags": row["tags"], "kind": row.get("kind")}
        print(n, out[n]["peak_minus_event_days"], out[n]["image_minus_rain_peak_days"], out[n]["peak_3day_mm"], flush=True)
    json.dump(out, open(os.path.join(OUT, "timing_imerg.json"), "w"), indent=1)
    return 0


REACHES = os.path.expanduser("~/.cache/geowatch/flood_round3/geoglows/reaches.npz")
GEOGLOWS = "https://geoglows.ecmwf.int/api/v2/retrospectivedaily/{}?format=json"
Q_CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/geoglows/q")
RIVER_TAGS = {"fluvial", "waterlogging", "compound", "flash_flood", "snowmelt", "dam_breach"}


def _reach_index():
    z = np.load(REACHES)
    return {k: z[k] for k in z.files}


def pick_reach(ix, bbox, pad=0.05, inside_only=False):
    """The GEOGloWS reach with the largest drainage area whose point lies in the
    box (+pad degrees, none for flash floods: their own valley, not the trunk river)."""
    w, s_, e, n = bbox
    p = 0.0 if inside_only else pad
    m = (ix["lon"] >= w - p) & (ix["lon"] <= e + p) & (ix["lat"] >= s_ - p) & (ix["lat"] <= n + p)
    if not m.any():
        return None
    i = np.flatnonzero(m)[int(np.argmax(ix["dsarea"][m]))]
    return {"link": int(ix["link"][i]), "dsarea_km2": round(float(ix["dsarea"][i]) / 1e6, 1),
            "order": int(ix["order"][i]), "lat": float(ix["lat"][i]), "lon": float(ix["lon"][i])}


def q_series(link):
    """Daily GEOGloWS v2 retrospective discharge (m3/s), cached per reach."""
    import urllib.request
    os.makedirs(Q_CACHE, exist_ok=True)
    p = os.path.join(Q_CACHE, f"{link}.npz")
    if not os.path.exists(p):
        for k in range(3):
            try:
                with urllib.request.urlopen(GEOGLOWS.format(link), timeout=120) as r:
                    d = json.load(r)
                break
            except Exception as e:      # noqa: BLE001
                print(f"reach {link}: {type(e).__name__}: {str(e)[:120]}", flush=True)
                time.sleep(15 * (k + 1))
        else:
            return None
        np.savez_compressed(p, q=np.asarray(d[str(link)], np.float32),
                            t=np.asarray([x[:10] for x in d["datetime"]]))
        time.sleep(0.5)
    z = np.load(p)
    return z["t"], z["q"]


def discharge():
    cat = json.load(open(os.path.join(OUT, "burned_catalog.json")))
    ix = _reach_index()
    out = {}
    for n, row in sorted(cat.items()):
        if not (set(row["tags"]) & RIVER_TAGS) or not row.get("bbox") or not row.get("event"):
            continue
        flash = row["tags"][0] == "flash_flood"
        r = pick_reach(ix, row["bbox"], inside_only=flash)
        if r is None:
            out[n] = {"reach": None}
            continue
        s = q_series(r["link"])
        if s is None:
            out[n] = {"reach": r, "error": "no series"}
            continue
        t, q = s
        ev = dt.date.fromisoformat(row["event"])
        w0, w1 = (ev - dt.timedelta(days=10)).isoformat(), (ev + dt.timedelta(days=7)).isoformat()
        m = (t >= w0) & (t <= w1)
        if not m.any():
            out[n] = {"reach": r, "error": "event outside the series"}
            continue
        i = np.flatnonzero(m)[int(np.argmax(q[m]))]
        peak_d = dt.date.fromisoformat(str(t[i]))
        yrs = np.array([int(x[:4]) for x in t])
        amax = np.array([q[yrs == y].max() for y in np.unique(yrs) if (yrs == y).sum() > 300])
        rp = 1.0 / max(1e-3, float(np.mean(amax >= q[i])))           # empirical annual-max return period
        img = row.get("images") or []
        img_d = min(dt.date.fromisoformat(x[:10]) for x in img) if img else None
        qi = None
        if img_d is not None:
            j = np.flatnonzero(t == img_d.isoformat())
            qi = float(q[j[0]]) if len(j) else None
        out[n] = {"reach": r, "tags": row["tags"], "peak_day": peak_d.isoformat(), "peak_q": round(float(q[i]), 1),
                  "peak_minus_event_days": (peak_d - ev).days,
                  "image_minus_q_peak_days": None if img_d is None else (img_d - peak_d).days,
                  "q_at_image_over_peak": None if qi is None or q[i] <= 0 else round(qi / float(q[i]), 3),
                  "peak_return_period_y": round(rp, 1), "median_q": round(float(np.median(q)), 1)}
        print(n, out[n]["peak_minus_event_days"], out[n]["image_minus_q_peak_days"], out[n]["q_at_image_over_peak"],
              out[n]["peak_return_period_y"], flush=True)
    json.dump(out, open(os.path.join(OUT, "timing_discharge.json"), "w"), indent=1)
    return 0


def agree():
    """1e: label ceiling. For EMS units (2015+), build our Sentinel-1 VV-drop label
    (round-4 code, unchanged) on the same grid from the first S1 pass on or after
    the EMS image date, and measure agreement on cells both observed."""
    ee = _init()
    from affine import Affine
    from experiments.flood_validation import references as RF
    cat = json.load(open(os.path.join(OUT, "burned_catalog.json")))
    d0 = os.path.join(CACHE, "agree")
    os.makedirs(d0, exist_ok=True)
    out = {}
    for n, row in sorted(cat.items()):
        if row.get("kind") != "ems" or not row.get("images") or not row.get("grid") or row["event"] < "2015-01-01":
            continue
        p = os.path.join(d0, f"{n}.npz")
        if not os.path.exists(p):
            g = row["grid"]
            t = Affine(*g["transform"][:6])
            img_d = min(x[:10] for x in row["images"])
            try:
                pas = RF.s1_event_pass(row["bbox"], img_d)
                ref = RF.s1_dry_reference(row["bbox"], row["event"], pas, t, tuple(g["shape"]), g["crs"])
                np.savez_compressed(p, flooded=ref["flooded"], valid=ref["valid"],
                                    meta=json.dumps({**ref["meta"], "s1_minus_ems_days": pas["days_after_event"]}))
            except Exception as e:      # noqa: BLE001
                np.savez_compressed(p, error=f"{type(e).__name__}: {str(e)[:200]}")
            time.sleep(1.0)
        z = np.load(p, allow_pickle=False)
        if "error" in z.files:
            out[n] = {"error": str(z["error"])}
            continue
        ems = np.load(os.path.expanduser(row["ref_path"]), allow_pickle=False)
        ef, ev = ems["flooded"], ems["valid"]
        sf, sv = z["flooded"], z["valid"]
        if ef.shape != sf.shape:
            out[n] = {"error": f"shape {ef.shape} vs {sf.shape}"}
            continue
        both = ev & sv
        a, b = ef[both], sf[both]
        tp, fp, fn, tn = (a & b).sum(), (~a & b).sum(), (a & ~b).sum(), (~a & ~b).sum()
        N = max(1, a.size)
        po = (tp + tn) / N
        pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / N ** 2
        m = json.loads(str(z["meta"]))
        out[n] = {"tags": row["tags"], "sensors": row.get("sensors"), "s1_minus_ems_days": m["s1_minus_ems_days"],
                  "cells_both": int(N), "ems_flooded": int(a.sum()), "s1_flooded": int(b.sum()),
                  "kappa": round(float((po - pe) / max(1e-9, 1 - pe)), 3),
                  "s1_recall_of_ems": round(float(tp / max(1, tp + fn)), 3),
                  "s1_precision_vs_ems": round(float(tp / max(1, tp + fp)), 3),
                  # AUC of the binary S1 label as a score for the EMS label (= balanced accuracy)
                  "auc_s1_for_ems": round(float(0.5 * (tp / max(1, tp + fn) + tn / max(1, tn + fp))), 3)}
        print(n, out[n]["s1_minus_ems_days"], out[n]["kappa"], out[n]["auc_s1_for_ems"], flush=True)
    json.dump(out, open(os.path.join(OUT, "label_agreement.json"), "w"), indent=1)
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    return {"timing": timing, "discharge": discharge, "agree": agree}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
