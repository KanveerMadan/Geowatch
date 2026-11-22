"""
Round 3, waterlogging: standing water on flat plains, on the Sentinel-1 route (WATERLOG_PLAINS_DESIGN.md, R29).
Metadata only: IMERG rain, GLO-30 relief, Sentinel-1 pass times. No label is read.

    python -m experiments.flood_round3.plains screen [dev|reserve]   -> results/plains_candidates.json

Event = one (plain, year): the plain's wet-season window; peak = the day with the largest centred 3-day IMERG
mean over the plain. DEV years 2016-2021, reserve years 2022-2025.
Search squares: a 20 km lattice over the plain; kept if flat (GLO-30 SD over the square < 4 m, criteria §9's
number) and inland; ranked by the square's IMERG 3-day total at the peak (ties: lattice id).
The first SQUARES_PER_EVENT that pass the Sentinel-1 timing rule (pass in [peak - 1 d, peak + 14 d], >= 2
same-orbit baselines) and are > 20 km from every burned unit are taken; one cluster per event.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/plains")
IMERG = "NASA/GPM_L3/IMERG_V07"
SQUARE_KM = 20.0
SQUARES_PER_EVENT = 6
FLAT_SD_M = 4.0
MAX_LAG = 14
DEV_YEARS = range(2016, 2022)
RESERVE_YEARS = range(2022, 2026)

# name: (bbox lon/lat, wet-season window "MM-DD".."MM-DD"). Owner-named plains (R29).
PLAINS = {
    "sindh": ((66.5, 23.6, 71.2, 28.6), ("07-01", "09-30")),
    "bangladesh": ((88.0, 20.7, 92.7, 26.6), ("06-01", "09-30")),
    "punjab": ((69.3, 27.7, 77.0, 32.6), ("07-01", "09-30")),
    "south_sudan": ((29.0, 6.0, 34.0, 10.0), ("08-01", "11-30")),
    "nigeria": ((3.0, 6.5, 14.5, 13.5), ("08-01", "10-31")),
}


def _ee():
    from experiments.flood_round3 import diagnose_ee as D
    return D._init()


def _retry(fn, label):
    for k in range(4):
        try:
            return fn()
        except Exception as e:          # noqa: BLE001
            print(label, type(e).__name__, str(e)[:120], flush=True)
            time.sleep(15 * (k + 1))
    raise RuntimeError(label + " failed")


def lattice(plain):
    (w, s, e, n), _ = PLAINS[plain]
    lat0 = (s + n) / 2
    dlat = SQUARE_KM / 111.32
    dlon = SQUARE_KM / (111.32 * math.cos(math.radians(lat0)))
    out = {}
    i = 0
    while s + (i + 1) * dlat <= n:
        j = 0
        while w + (j + 1) * dlon <= e:
            out[f"{plain}_{i:03d}_{j:03d}"] = (w + j * dlon, s + i * dlat, w + (j + 1) * dlon, s + (i + 1) * dlat)
            j += 1
        i += 1
    return out


def flat_squares(ee, plain):
    """{square: GLO-30 elevation SD} for land squares (cached per plain)."""
    p = os.path.join(CACHE, f"relief_{plain}.json")
    if os.path.exists(p):
        return json.load(open(p))
    L = lattice(plain)
    dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic()
    wc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
    land = wc.neq(80).And(wc.mask())               # WorldCover maps land only; class 80 = permanent water
    keys = sorted(L)
    out = {}
    for k0 in range(0, len(keys), 200):
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle(list(L[k])), {"k": k}) for k in keys[k0:k0 + 200]])
        red = dem.updateMask(land).reduceRegions(fc, ee.Reducer.stdDev().combine(ee.Reducer.count(), "", True), 90)
        for f in _retry(lambda: red.getInfo()["features"], "relief"):
            pr = f["properties"]
            if pr.get("count", 0) > 0.5 * (SQUARE_KM * 1000 / 90) ** 2 and pr.get("stdDev") is not None:
                out[pr["k"]] = round(float(pr["stdDev"]), 2)
        time.sleep(1)
    os.makedirs(CACHE, exist_ok=True)
    json.dump(out, open(p, "w"))
    return out


def event_peak(ee, plain, year):
    """(peak day, 3-day plain mean mm) from daily IMERG means over the plain in the season window (cached)."""
    p = os.path.join(CACHE, f"imerg_{plain}_{year}.json")
    if not os.path.exists(p):
        (w, s, e, n), (a, b) = PLAINS[plain]
        d0, d1 = dt.date.fromisoformat(f"{year}-{a}"), dt.date.fromisoformat(f"{year}-{b}")
        days = [d0 + dt.timedelta(days=k) for k in range((d1 - d0).days + 1)]
        col = ee.ImageCollection(IMERG).select("precipitation")
        img = ee.Image.cat([col.filterDate(d.isoformat(), (d + dt.timedelta(days=1)).isoformat()).sum().multiply(0.5)
                            .rename(d.isoformat()) for d in days])
        r = _retry(lambda: img.reduceRegion(ee.Reducer.mean(), ee.Geometry.Rectangle([w, s, e, n]), 25000,
                                            maxPixels=1e9).getInfo(), "imerg")
        os.makedirs(CACHE, exist_ok=True)
        json.dump(r, open(p, "w"))
        time.sleep(1)
    r = json.load(open(p))
    days = sorted(r)
    v = [r[d] or 0.0 for d in days]
    k3 = [sum(v[max(0, i - 1):i + 2]) for i in range(len(v))]
    i = max(range(len(v)), key=lambda j: (k3[j], -j))
    return days[i], round(k3[i], 1)


def square_rain(ee, plain, year, peak):
    """{square: IMERG 3-day total (mm) centred on the peak} (cached)."""
    p = os.path.join(CACHE, f"sqrain_{plain}_{year}.json")
    if os.path.exists(p):
        return json.load(open(p))
    L = lattice(plain)
    pk = dt.date.fromisoformat(peak)
    img = (ee.ImageCollection(IMERG).select("precipitation")
           .filterDate((pk - dt.timedelta(days=1)).isoformat(), (pk + dt.timedelta(days=2)).isoformat()).sum().multiply(0.5))
    keys = sorted(L)
    out = {}
    for k0 in range(0, len(keys), 300):
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle(list(L[k])), {"k": k}) for k in keys[k0:k0 + 300]])
        for f in _retry(lambda: img.reduceRegions(fc, ee.Reducer.mean(), 10000).getInfo()["features"], "sqrain"):
            out[f["properties"]["k"]] = round(float(f["properties"].get("mean") or 0.0), 1)
        time.sleep(1)
    json.dump(out, open(p, "w"))
    return out


def screen(split="dev"):
    from experiments.flood_round3 import select_r3 as S
    ee = _ee()
    years = DEV_YEARS if split == "dev" else RESERVE_YEARS
    pts = S._used_points()
    path = os.path.join(OUT, "plains_candidates.json")
    res = json.load(open(path)) if os.path.exists(path) else {"candidates": [], "refused": [], "events": []}
    seen = {(e["plain"], e["year"]) for e in res["events"]}
    for plain in PLAINS:
        relief = flat_squares(ee, plain)
        L = lattice(plain)
        for year in years:
            if (plain, year) in seen:
                continue
            peak, rain3 = event_peak(ee, plain, year)
            ev = {"plain": plain, "year": year, "split": split, "peak_day": peak, "rain_3day_mm": rain3}
            if rain3 < 20:
                ev["refused"] = "driver check failed (plain IMERG 3-day < 20 mm)"
                res["events"].append(ev)
                continue
            sr = square_rain(ee, plain, year, peak)
            order = sorted((k for k in relief if relief[k] < FLAT_SD_M), key=lambda k: (-sr.get(k, 0.0), k))
            taken = 0
            pk = dt.date.fromisoformat(peak)
            for k in order:
                if taken >= SQUARES_PER_EVENT:
                    break
                w, s_, e, n = L[k]
                lon, lat = (w + e) / 2, (s_ + n) / 2
                unit = f"r3pl_{plain}_{year}_{k.split('_', 1)[1]}"
                if any(S._hav((lon, lat), q[:2]) <= 20.0 for q in pts):
                    res["refused"].append({"unit": unit, "why": "within 20 km of a burned unit"})
                    continue
                win = S.s1_passes(ee, lon, lat, (pk - dt.timedelta(days=1)).isoformat(),
                                  (pk + dt.timedelta(days=MAX_LAG + 1)).isoformat())
                if not win:
                    res["refused"].append({"unit": unit, "why": "no Sentinel-1 pass in [peak - 1 d, peak + 14 d]"})
                    continue
                t0, orbit = win[0]
                t0d = dt.date.fromisoformat(t0)
                nb, yr = 0, 0
                for yr in (0, 1):
                    b0 = (t0d - dt.timedelta(days=60 + 365 * yr)).isoformat()
                    b1 = (t0d - dt.timedelta(days=5 + 365 * yr)).isoformat()
                    nb = sum(1 for _, o in S.s1_passes(ee, lon, lat, b0, b1) if o == orbit)
                    if nb >= 2:
                        break
                if nb < 2:
                    res["refused"].append({"unit": unit, "why": "fewer than 2 same-orbit baseline passes"})
                    continue
                res["candidates"].append({
                    "unit": unit, "plain": plain, "year": year, "tags": ["waterlogging"], "event": peak,
                    "peak_day": peak, "rain_3day_mm_plain": rain3, "rain_3day_mm_square": sr.get(k),
                    "relief_sd_m": relief[k], "image": t0, "orbit": orbit, "lag_days": (t0d - pk).days,
                    "baseline_passes": nb, "baseline_year_before": yr == 1, "search_point": [lat, lon],
                    "square": [round(x, 6) for x in L[k]], "split": split, "cluster": f"pl_{plain}_{year}",
                    "source": "R29 plains screen (IMERG, GLO-30 relief, S1 metadata); v3 Sentinel-1 label"})
                taken += 1
                print(unit, peak, sr.get(k), relief[k], t0, flush=True)
            ev["taken"] = taken
            res["events"].append(ev)
            json.dump(res, open(path, "w"), indent=1)
    json.dump(res, open(path, "w"), indent=1)
    print(split, sum(c["split"] == split for c in res["candidates"]), "candidates", flush=True)
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    return screen(a[1] if len(a) > 1 else "dev")


if __name__ == "__main__":
    raise SystemExit(main())
