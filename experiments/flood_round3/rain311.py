"""
Round 3: urban rain labels from city 311 street-flooding reports (RAIN_311_DESIGN.md).

    python -m experiments.flood_round3.rain311 events     # daily flood-report COUNTS only -> results/r311_events.json

`events` reads counts per day, never locations. Locations are read only by the label
build, and for reserve events (>= 2022-01-01) only after the freeze.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/r311")
MIN_EVENT_REPORTS = 50          # surface-flood reports city-wide; also the bar's 50-flooded-cell floor
RESERVE_FROM = "2022-01-01"

CITIES = {
    "nyc": {
        "apis": ("https://data.cityofnewyork.us/resource/76ig-c548.json",    # 2010-2019 archive
                 "https://data.cityofnewyork.us/resource/erm2-nwe9.json"),   # 2020 onwards
        "time": "created_date", "kind": "descriptor", "lat": "latitude", "lon": "longitude",
        "flood": ("Street Flooding (SJ)", "Highway Flooding (SH)"),
        # neither flooded nor dry: mixed meaning (clogging OR flooding) or sewer-driven
        "ambiguous": ("Catch Basin Clogged/Flooding (Use Comments) (SC)", "Sewer Backup (Use Comments) (SA)",
                      "Manhole Overflow (Use Comments) (SA1)", "Ready NY - Flooding", "Flooded"),
        "since": "2010-01-01", "centre": (40.70, -73.95),
        "bbox": (-74.26, 40.49, -73.70, 40.92), "tide_station": "8518750",
    },
    "chicago": {
        "apis": ("https://data.cityofchicago.org/resource/v6vf-nfxy.json",),
        "time": "created_date", "kind": "sr_type", "lat": "latitude", "lon": "longitude",
        "flood": ("Water On Street Complaint",),
        "ambiguous": ("Water in Basement Complaint",),
        "since": "2018-12-18", "centre": (41.84, -87.68),
        "bbox": (-87.94, 41.64, -87.52, 42.03), "tide_station": None,      # lake city: no surge check
    },
}


def _soql(api, params):
    url = api + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "geowatch-research"})
    for k in range(4):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except Exception as e:          # noqa: BLE001
            print("311:", type(e).__name__, str(e)[:120], flush=True)
            time.sleep(10 * (k + 1))
    raise RuntimeError("311 query failed")


def daily_counts(city: str) -> dict:
    c = CITIES[city]
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"{city}_daily.json")
    if os.path.exists(p):
        return json.load(open(p))
    kinds = ",".join("'" + k.replace("'", "''") + "'" for k in c["flood"])
    out = {}
    for api in c["apis"]:
        rows = _soql(api, {
            "$select": f"date_trunc_ymd({c['time']}) as d, count(*) as n",
            "$where": f"{c['kind']} in ({kinds}) AND {c['time']} >= '{c['since']}T00:00:00'",
            "$group": "d", "$order": "d", "$limit": 50000})
        for r in rows:
            out[r["d"][:10]] = out.get(r["d"][:10], 0) + int(r["n"])
    json.dump(out, open(p, "w"))
    return out


def events():
    res = {}
    for city in CITIES:
        d = daily_counts(city)
        days = sorted(k for k, v in d.items() if v >= MIN_EVENT_REPORTS)
        evs, cur = [], None
        for k in days:
            kd = dt.date.fromisoformat(k)
            if cur and (kd - dt.date.fromisoformat(cur[-1])).days <= 1:
                cur.append(k)
            else:
                cur = [k]
                evs.append(cur)
        res[city] = [{"event": e[0], "days": e, "flood_reports": sum(d[x] for x in e),
                      "split": "reserve" if e[0] >= RESERVE_FROM else "dev"} for e in evs]
        n_dev = sum(1 for e in res[city] if e["split"] == "dev")
        print(city, len(res[city]), "events;", n_dev, "dev,", len(res[city]) - n_dev, "reserve", flush=True)
    json.dump(res, open(os.path.join(OUT, "r311_events.json"), "w"), indent=1)
    return 0


TIDES = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
FLOODLEVELS = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/{}/floodlevels.json"


def _json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "geowatch-research"})
    for k in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except Exception as e:          # noqa: BLE001
            print("http:", type(e).__name__, str(e)[:120], flush=True)
            time.sleep(10 * (k + 1))
    raise RuntimeError(url)


def tide_max_ft(station, d0, d1):
    """Max hourly water level (ft, station datum) in [d0, d1], NOAA CO-OPS; cached."""
    p = os.path.join(CACHE, f"tide_{station}_{d0}_{d1}.json")
    if not os.path.exists(p):
        q = urllib.parse.urlencode({"product": "hourly_height", "station": station, "begin_date": d0.replace("-", ""),
                                    "end_date": d1.replace("-", ""), "datum": "STND", "units": "english",
                                    "time_zone": "gmt", "format": "json", "application": "geowatch_research"})
        j = _json(TIDES + "?" + q)
        json.dump(j, open(p, "w"))
        time.sleep(0.5)
    v = [float(x["v"]) for x in json.load(open(p)).get("data", []) if x.get("v") not in (None, "")]
    return max(v) if v else None


def drivers():
    """§2 driver checks per event, metadata only: IMERG rain over the city (peak = largest
    3-day centred sum) and the tide gauge's max level vs NOAA's minor-flood threshold."""
    from experiments.flood_round3 import diagnose_ee as D
    import numpy as np
    ee = D._init()
    evs = json.load(open(os.path.join(OUT, "r311_events.json")))
    for city, rows in evs.items():
        c = CITIES[city]
        minor = _json(FLOODLEVELS.format(c["tide_station"]))["nos_minor"] if c["tide_station"] else None
        for e in rows:
            if "type" in e:
                continue
            p = os.path.join(CACHE, f"imerg_{city}_{e['event']}.json")
            if not os.path.exists(p):
                mean, mx = D.rain_series(ee, c["bbox"], e["event"])
                json.dump({"mean": mean, "max": mx}, open(p, "w"))
                time.sleep(1.0)
            s = json.load(open(p))["mean"]
            days = sorted(s)
            v = np.array([s[d] or 0.0 for d in days])
            k3 = np.convolve(v, np.ones(3), mode="same")
            ev = dt.date.fromisoformat(e["event"])
            near = [j for j, d in enumerate(days) if -2 <= (dt.date.fromisoformat(d) - ev).days <= 1]
            i = near[int(np.argmax(k3[near]))]          # the storm of the report days, not an earlier one
            peak = dt.date.fromisoformat(days[i])
            w0, w1 = (peak - dt.timedelta(days=1)).isoformat(), (peak + dt.timedelta(days=1)).isoformat()
            tide = tide_max_ft(c["tide_station"], w0, w1) if c["tide_station"] else None
            rain3 = float(k3[i])
            coastal = tide is not None and minor is not None and tide >= minor
            if coastal:
                ty = "compound" if rain3 >= 50 else "coastal"
            elif rain3 >= 20:
                ty = "pluvial"
            else:
                ty = None
            e.update(rain_peak_day=peak.isoformat(), rain_3day_mm=round(rain3, 1), tide_max_ft=tide,
                     tide_minor_ft=minor, window=[w0 + "T00:00:00", (peak + dt.timedelta(days=2)).isoformat() + "T00:00:00"],
                     type=ty, refused=None if ty else "driver check failed (IMERG 3-day < 20 mm, tide below minor)")
            print(city, e["event"], e["split"], ty, round(rain3, 1), tide, flush=True)
        json.dump(evs, open(os.path.join(OUT, "r311_events.json"), "w"), indent=1)
    return 0


def storms():
    """One labelled event per storm (RAIN_311_DESIGN §2a). Events whose label windows overlap are
    chained into one storm; the event with the most flood reports (metadata, ties -> earliest) is kept,
    the others are refused as "same storm". Same rule for DEV and reserve; no label is read."""
    evs = json.load(open(os.path.join(OUT, "r311_events.json")))
    for city, rows in evs.items():
        typed = sorted((e for e in rows if e.get("window") and not (e.get("refused") or "").startswith("same storm")),
                       key=lambda e: e["window"][0])
        groups, cur = [], []
        for e in typed:
            if cur and e["window"][0] < max(x["window"][1] for x in cur):
                cur.append(e)
            else:
                if cur:
                    groups.append(cur)
                cur = [e]
        if cur:
            groups.append(cur)
        n = 0
        for g in groups:
            ok = [e for e in g if e.get("type")]
            if not ok:
                continue
            keep = max(ok, key=lambda e: (e["flood_reports"], -dt.date.fromisoformat(e["event"]).toordinal()))
            for e in ok:
                if e is not keep:
                    e["refused"], e["type"], n = f"same storm as {keep['event']}", None, n + 1
                    e["storm"] = keep["event"]
            keep["storm"] = keep["event"]
        print(city, "refused as same storm:", n, flush=True)
    json.dump(evs, open(os.path.join(OUT, "r311_events.json"), "w"), indent=1)
    return 0


LATTICE_KM, STEP_KM = 8.0, 4.0          # R25 boxes on a fixed lattice, so features are built once per box
FEATURE_YEAR_EVENT = "2021-07-01"     # one feature build per box (WorldCover / NDVI year); all methods alike
REFS = os.path.expanduser("~/.cache/geowatch/flood_round3/big/r311_refs")
MIN_FLOODED = 50


def lattice(city):
    import math
    w, s_, e, n = CITIES[city]["bbox"]
    lat0 = (s_ + n) / 2
    dlat = STEP_KM / 111.32
    dlon = STEP_KM / (111.32 * math.cos(math.radians(lat0)))
    hl, hw = LATTICE_KM / 2 / 111.32, LATTICE_KM / 2 / (111.32 * math.cos(math.radians(lat0)))
    out = {}
    i = 0
    while s_ + i * dlat <= n:
        j = 0
        while w + j * dlon <= e:
            la, lo = s_ + i * dlat, w + j * dlon
            out[f"{city}_b{i:02d}_{j:02d}"] = (lo - hw, la - hl, lo + hw, la + hl)
            j += 1
        i += 1
    return out


def reports(city, e) -> list:
    """All geocoded reports in the event window: [(kind_class, lon, lat)], kind_class in flood / ambiguous / other."""
    c = CITIES[city]
    p = os.path.join(CACHE, f"reports_{city}_{e['event']}.json")
    if not os.path.exists(p):
        w0, w1 = e["window"]
        rows, api = [], c["apis"][0] if (w0 < "2020-01-01" or len(c["apis"]) == 1) else c["apis"][1]
        off = 0
        while True:
            page = _soql(api, {"$select": f"{c['kind']},{c['lat']},{c['lon']}",
                               "$where": f"{c['time']} >= '{w0}' AND {c['time']} < '{w1}' AND {c['lat']} IS NOT NULL",
                               "$order": ":id", "$limit": 50000, "$offset": off})
            rows += page
            if len(page) < 50000:
                break
            off += 50000
        out = []
        for r in rows:
            k = r.get(c["kind"]) or ""
            cls = "flood" if k in c["flood"] else "ambiguous" if k in c["ambiguous"] else "other"
            out.append((cls, float(r[c["lon"]]), float(r[c["lat"]])))
        json.dump(out, open(p, "w"))
    return [tuple(x) for x in json.load(open(p))]


HIST_RADIUS_M = 150.0


def history(city=None):
    """Flood-category reports (lon, lat, day) before RESERVE_FROM: the causal "flood memory" feature's
    only input. Nothing on or after the reserve start is fetched, so no reserve label is read."""
    import numpy as np
    for cty in ([city] if city else CITIES):
        c = CITIES[cty]
        p = os.path.join(CACHE, f"history_{cty}.npz")
        if os.path.exists(p):
            continue
        kinds = ",".join("'" + k.replace("'", "''") + "'" for k in c["flood"])
        lon, lat, day = [], [], []
        for api in c["apis"]:
            off = 0
            while True:
                page = _soql(api, {"$select": f"{c['time']},{c['lat']},{c['lon']}",
                                   "$where": f"{c['kind']} in ({kinds}) AND {c['time']} >= '{c['since']}T00:00:00' AND "
                                             f"{c['time']} < '{RESERVE_FROM}T00:00:00' AND {c['lat']} IS NOT NULL",
                                   "$order": ":id", "$limit": 50000, "$offset": off})
                for r in page:
                    lon.append(float(r[c["lon"]])); lat.append(float(r[c["lat"]])); day.append(r[c["time"]][:10])
                if len(page) < 50000:
                    break
                off += 50000
                time.sleep(0.5)
        d = np.array(day, dtype="datetime64[D]")
        k = np.unique(np.c_[lon, lat, d.astype(np.int64)], axis=0)       # the two NYC APIs overlap at the seam
        np.savez_compressed(p, lon=k[:, 0], lat=k[:, 1], day=k[:, 2].astype(np.int64))
        print(cty, "history reports:", len(k), flush=True)
    return 0


def hist_feature(city, grid, before, radius_m=HIST_RADIUS_M):
    """log1p(count of the city's flood reports within radius_m of each cell centre, dated strictly before
    `before` (ISO day) and before RESERVE_FROM). grid = {crs, transform, shape}. Returns float32 cells."""
    import numpy as np
    from pyproj import Transformer
    from scipy.spatial import cKDTree
    z = np.load(os.path.join(CACHE, f"history_{city}.npz"))
    cut = min(np.datetime64(before, "D"), np.datetime64(RESERVE_FROM, "D")).astype(np.int64)
    m = z["day"] < cut
    H, W = grid["shape"]
    t = grid["transform"]
    r, c = np.divmod(np.arange(H * W), W)
    x, y = t[2] + (c + 0.5) * t[0], t[5] + (r + 0.5) * t[4]
    if not m.any():
        return np.zeros(H * W, np.float32)
    X, Y = Transformer.from_crs(4326, grid["crs"], always_xy=True).transform(z["lon"][m], z["lat"][m])
    T = cKDTree(np.c_[X, Y])
    n = T.query_ball_point(np.c_[x, y], radius_m, return_length=True)
    return np.log1p(n).astype(np.float32)


def place_boxes(city, rep):
    """At build time: the lattice box with the most flood reports, then a second
    non-overlapping one with >= MIN_FLOODED (RAIN_311_DESIGN units)."""
    fl = [(lo, la) for k, lo, la in rep if k == "flood"]
    cnt = {b: sum(1 for lo, la in fl if bb[0] <= lo < bb[2] and bb[1] <= la < bb[3]) for b, bb in lattice(city).items()}
    order = sorted(cnt, key=lambda b: (-cnt[b], b))
    L = lattice(city)
    picked = []
    for b in order:
        if cnt[b] < MIN_FLOODED or len(picked) == 2:
            break
        if all(L[b][2] <= L[q][0] or L[q][2] <= L[b][0] or L[b][3] <= L[q][1] or L[q][3] <= L[b][1] for q in picked):
            picked.append(b)
    return picked, cnt


def label_box(rep, bbox, ee=None):
    """Four states on the box's 30 m UTM grid (RAIN_311_DESIGN label rules)."""
    import numpy as np
    from pyproj import Transformer
    from susceptibility.hydro_rasters import utm_grid
    from experiments.flood_round3 import labels_r3 as L
    t, shape, crs = utm_grid(bbox)
    tr = Transformer.from_crs(4326, crs, always_xy=True)
    grids = {k: np.zeros(shape, bool) for k in ("flood", "ambiguous", "other")}
    for k, lo, la in rep:
        if not (bbox[0] <= lo < bbox[2] and bbox[1] <= la < bbox[3]):
            continue
        x, y = tr.transform(lo, la)
        c_, r_ = ~t * (x, y)
        r_, c_ = int(r_), int(c_)
        if 0 <= r_ < shape[0] and 0 <= c_ < shape[1]:
            grids[k][r_, c_] = True
    from scipy.ndimage import binary_dilation
    near_flood = binary_dilation(grids["flood"], iterations=3)
    y = np.full(shape, L.UNOBSERVED, np.int8)
    y[grids["other"] & ~near_flood & ~grids["ambiguous"]] = L.DRY
    y[grids["flood"]] = L.FLOODED
    if ee is not None:
        occ = L.observability(ee, t, shape, crs)["occ"]
        y[np.nan_to_num(occ, nan=0.0) >= L.PERMANENT_PCT] = L.PERMANENT
    return y, t, shape, crs


def build_dev():
    """DEV events only (< RESERVE_FROM): labels per (event, box); one feature build per box (build_r3)."""
    import numpy as np
    from experiments.flood_round3 import diagnose_ee as D
    ee = D._init()
    evs = json.load(open(os.path.join(OUT, "r311_events.json")))
    os.makedirs(REFS, exist_ok=True)
    units = {}
    for city, rows in evs.items():
        L = lattice(city)
        for e in rows:
            if e.get("split") != "dev" or e.get("type") not in ("pluvial", "coastal", "compound"):
                continue
            rep = reports(city, e)
            boxes, cnt = place_boxes(city, rep)
            for b in boxes:
                n = f"r311_{city}_{e['event']}_{b.split('_', 1)[1]}"
                p = os.path.join(REFS, f"{n}.npz")
                if not os.path.exists(p):
                    y, t, shape, crs = label_box(rep, L[b], ee)
                    meta = {"unit": n, "box": b, "event": e["event"], "window": e["window"], "bbox": list(L[b]),
                            "grid": {"crs": crs, "transform": list(t)[:6], "shape": list(shape)},
                            "flooded_cells": int((y == 1).sum()), "dry_cells": int((y == 0).sum()),
                            "reports": {k: sum(1 for r in rep if r[0] == k) for k in ("flood", "ambiguous", "other")}}
                    np.savez_compressed(p, y3=y, meta=np.array(json.dumps(meta)))
                    print(n, meta["flooded_cells"], meta["dry_cells"], flush=True)
                units[n] = {"box": b, "event": e["event"], "type": e["type"], "city": city,
                            "cluster": f"r311_{city}_{e['event']}"}
            time.sleep(0.5)
    json.dump(units, open(os.path.join(REFS, "units.json"), "w"), indent=1)
    print(len(units), "units on", len({u["box"] for u in units.values()}), "boxes")
    return 0


def main(argv=None):
    import sys
    a = argv or sys.argv[1:]
    return {"events": events, "drivers": drivers, "storms": storms, "history": history, "build_dev": build_dev}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
