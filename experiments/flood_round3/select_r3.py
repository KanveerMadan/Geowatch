"""
Round 3, Phase 3: mechanical reserve selection from metadata only
(RESERVE_CRITERIA_R3.md). It reads no label geometry, reference raster, feature
or score.

    python -m experiments.flood_round3.select_r3 ems     # EMS activation + product metadata -> candidates
    python -m experiments.flood_round3.select_r3 seal    # apply targets, write reserve_r3.json (+ sha256)

Metadata read per EMS AOI product:
- type and monitoring number, layer NAMES (not their content);
- image sensor and acquisition time, AOI extent polygon;
- the product's reported `stats` (affected area).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
META = os.path.expanduser("~/.cache/geowatch/flood_round3/ems_meta")
ACT_LIST = os.path.join(META, "activations.json")
EMS_API = "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations/?code={code}"
MAX_LAG = {"pluvial": 1, "flash_flood": 2, "fluvial": 3, "coastal": 2, "compound": 2, "waterlogging": 14}
MIN_AFFECTED_HA = 45.0
MIN_AOI_KM2 = 16.0
PROX_KM = 20.0
AOIS_PER_ACTIVATION = 2

# Mechanical type rules on the activation's own text (name + reason), in order.
RULES = [
    ("coastal", r"storm surge|coastal flood|surge"),
    ("flash_flood", r"flash flood|torrential|landslide|debris"),
    ("waterlogging", r"prolonged|polder|weeks|standing water|lake level|swamp"),
    ("fluvial", r"\briver\b|overflow|basin|\bstream\b|dam release|rising water level"),
    ("pluvial", r"heavy rain|rainfall|downpour|storm|thunderstorm|cloudburst"),
]
COMPOUND = r"(cyclone|hurricane|typhoon|tropical storm)"


def used_codes() -> set:
    root = os.path.dirname(HERE)
    txt = ""
    for p in ("flood_core/registry/events.json", "flood_round2/registry_units_round2.json",
              "flood_final/registry_units.json", "flood_round2/events_round2.py", "flood_final/events_final.py",
              "flood_learned/heldout/select.py", "flood_round3/results/burned_catalog.json"):
        f = os.path.join(root, p)
        if os.path.exists(f):
            txt += open(f).read()
    return set(re.findall(r"EMSR\d+", txt, flags=re.I)) | {c.upper() for c in re.findall(r"emsr\d+", txt)}


def tag(text: str) -> list:
    t = text.lower()
    tags = [ty for ty, pat in RULES if re.search(pat, t)]
    out = tags[:1]
    if re.search(COMPOUND, t):
        out = ["coastal", "compound"] if "coastal" in tags or "surge" in t else ["compound"]
    return out


def _get(code):
    p = os.path.join(META, f"{code}.json")
    if not os.path.exists(p):
        with urllib.request.urlopen(EMS_API.format(code=code), timeout=120) as r:
            open(p, "wb").write(r.read())
        time.sleep(1.0)
    return json.load(open(p))["results"][0]


def _area_km2(poly_wkt):
    from shapely import wkt
    from shapely.ops import transform
    import pyproj
    g = wkt.loads(poly_wkt)
    c = g.centroid
    proj = pyproj.Transformer.from_crs("EPSG:4326", pyproj.CRS.from_proj4(
        f"+proj=aeqd +lat_0={c.y} +lon_0={c.x} +units=m"), always_xy=True).transform
    return transform(proj, g).area / 1e6, (c.x, c.y), g.bounds


def _affected_ha(stats) -> float:
    """Sum of 'affected' areas in ha across the product's reported stats."""
    tot = 0.0

    def walk(x):
        nonlocal tot
        if isinstance(x, dict):
            if x.get("unit") == "ha" and isinstance(x.get("affected"), (int, float)):
                tot += float(x["affected"])
            for v in x.values():
                walk(v)
    walk(stats if isinstance(stats, dict) else {})
    return tot


def _hav(a, b):
    R = 6371.0
    la1, lo1, la2, lo2 = map(math.radians, (a[1], a[0], b[1], b[0]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def _used_points():
    cat = json.load(open(os.path.join(OUT, "burned_catalog.json")))
    pts = []
    for r in cat.values():
        b = r.get("bbox")
        if b:
            pts.append(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, r.get("event")))
    return pts


def ems():
    acts = json.load(open(ACT_LIST))["results"]
    used = used_codes()
    pts = _used_points()
    rows, refused = [], []
    for a in sorted(acts, key=lambda x: x["code"]):
        if a.get("category") not in ("Flood", "Storm") or a["code"] in used or a["eventTime"][:4] < "2015":
            continue
        act = _get(a["code"])
        text = f"{act.get('name', '')}. {act.get('reason', '')}"
        tags = tag(text)
        if not tags:
            refused.append({"code": a["code"], "why": "no type from the activation text"})
            continue
        ev = act["eventTime"][:10]
        for aoi in act.get("aois", []):
            prods = [p for p in aoi.get("products", []) if p.get("type") in ("DEL", "GRA")
                     and any("_observedEventA" in (l.get("name") or "") for l in p.get("layers", []))]
            dels = sorted([p for p in prods if p["type"] == "DEL"], key=lambda p: int(p.get("monitoringNumber") or 0))
            pick = dels[0] if dels else (sorted(prods, key=lambda p: int(p.get("monitoringNumber") or 0)) or [None])[0]
            unit = f"r3_{a['code'].lower()}_aoi{int(aoi['number']):02d}"
            if pick is None:
                refused.append({"unit": unit, "why": "no DEL/GRA product with an observed-event layer"})
                continue
            km2, cen, bounds = _area_km2(aoi["extent"])
            imgs = sorted(i.get("acquisitionTime") or i.get("acquisition_time") or "" for i in (pick.get("images") or []))
            imgs = [i for i in imgs if i]
            sensors = sorted({i.get("sensorName") for i in (pick.get("images") or []) if i.get("sensorName")})
            near = [p for p in pts if _hav(cen, p[:2]) <= PROX_KM]
            rows.append({"unit": unit, "code": a["code"], "aoi": int(aoi["number"]), "tags": tags, "event": ev,
                         "text": text[:300], "product": f"{pick['type']} monitoring {pick.get('monitoringNumber')}",
                         "images": imgs, "sensors": sensors, "aoi_km2": round(km2, 1), "centre": cen, "bounds": bounds,
                         "affected_ha": round(_affected_ha(pick.get("stats")), 1),
                         "near_used_units": len(near), "category": a.get("category")})
    json.dump({"candidates": rows, "refused": refused}, open(os.path.join(OUT, "r3_ems_candidates.json"), "w"), indent=1)
    print(len(rows), "AOI candidates from", len({r["code"] for r in rows}), "activations;", len(refused), "refused")
    return 0


MM_META = os.path.expanduser("~/.cache/geowatch/flood_round3/mmflood_meta")
BOX_KM = 8.0          # R24
S1_ROUTE_TYPES = ("fluvial", "waterlogging")
S1_CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/s1_passes")


def _mm_groups():
    """MMFlood AOI groups (EMSRxxx-k) -> union footprint of their DEM tiles (EPSG:4326)."""
    fp = json.load(open(os.path.join(MM_META, "footprints.json")))
    groups = {}
    for tile, h in fp.items():
        if not h or "error" in h or h.get("epsg") != 4326:
            continue
        g = tile.rsplit("-", 1)[0]
        b = h["bounds"]
        if g in groups:
            o = groups[g]
            groups[g] = [min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3])]
        else:
            groups[g] = list(b)
    return groups


def _box(lon, lat, km):
    dlat = km / 2 / 111.32
    dlon = km / 2 / (111.32 * math.cos(math.radians(lat)))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


def _inside(a, b):
    return a[0] >= b[0] and a[1] >= b[1] and a[2] <= b[2] and a[3] <= b[3]


def _overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def s1_passes(ee, lon, lat, d0, d1):
    """Sentinel-1 IW GRD VV acquisitions covering (lon, lat) in [d0, d1): [(date, relative orbit)].
    Earth Engine collection metadata only; cached."""
    os.makedirs(S1_CACHE, exist_ok=True)
    p = os.path.join(S1_CACHE, f"{lon:.4f}_{lat:.4f}_{d0}_{d1}.json")
    if os.path.exists(p):
        return [tuple(x) for x in json.load(open(p))]
    col = (ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(ee.Geometry.Point([lon, lat]))
           .filterDate(d0, d1).filter(ee.Filter.eq("instrumentMode", "IW"))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")))
    for k in range(3):
        try:
            t = col.aggregate_array("system:time_start").getInfo()
            o = col.aggregate_array("relativeOrbitNumber_start").getInfo()
            break
        except Exception as e:          # noqa: BLE001
            print("EE:", type(e).__name__, str(e)[:120], flush=True)
            time.sleep(10 * (k + 1))
    else:
        raise RuntimeError("EE failed")
    out = sorted((dt.datetime.utcfromtimestamp(a / 1000).date().isoformat(), int(b)) for a, b in zip(t, o))
    json.dump(out, open(p, "w"))
    time.sleep(0.5)
    return out


def _river_peak(ix, box, start):
    from experiments.flood_round3 import diagnose_ee as D
    r = D.pick_reach(ix, box, inside_only=True)
    if r is None:
        return None, "no GEOGloWS reach in the box"
    s = D.q_series(r["link"])
    if s is None:
        return None, "no discharge series"
    t, q = s
    ev = dt.date.fromisoformat(start)
    m = (t >= (ev - dt.timedelta(days=10)).isoformat()) & (t <= (ev + dt.timedelta(days=7)).isoformat())
    if not m.any():
        return None, "event outside the discharge series"
    i = np.flatnonzero(m)[int(np.argmax(q[m]))]
    yrs = np.array([int(x[:4]) for x in t])
    amax = np.array([q[yrs == y].max() for y in np.unique(yrs) if (yrs == y).sum() > 300])
    rp = 1.0 / max(1e-3, float(np.mean(amax >= q[i])))
    return {"reach": r, "peak_day": str(t[i]), "peak_q": round(float(q[i]), 1), "rp_y": round(rp, 2)}, None


def mmflood():
    """§8: MMFlood activations -> Sentinel-1-route river / waterlogging candidates (metadata only)."""
    from experiments.flood_round3 import diagnose_ee as D
    acts = json.load(open(os.path.join(MM_META, "activations.json")))
    groups = _mm_groups()
    used = used_codes()
    pts = _used_points()
    ix = D._reach_index()
    ee = D._init()
    rows, refused = [], []
    for code in sorted(acts, key=lambda c: int(c[4:])):
        a = acts[code]
        start = a["start"][:10]

        def refuse(unit, why, **kw):
            refused.append({"unit": unit, "code": code, "why": why, **kw})
        if code.upper() in used:
            refuse(code, "activation used before")
            continue
        if start < "2015-01-01":
            refuse(code, "before 2015")
            continue
        tags = tag(a["title"])
        ty = tags[0] if tags else "fluvial"
        if ty not in S1_ROUTE_TYPES:
            refuse(code, f"type {ty} not taken on the Sentinel-1 route (DIAGNOSIS §e)")
            continue
        taken = []
        gs = sorted((g for g in groups if g.split("-")[0] == code), key=lambda g: int(g.split("-")[1]))
        if not gs:
            refuse(code, "no footprint")
        for g in gs:
            unit = f"r3mm_{g.lower().replace('-', '_')}"
            if len(taken) >= AOIS_PER_ACTIVATION:
                break
            w, s_, e, n = groups[g]
            cen = ((w + e) / 2, (s_ + n) / 2)
            if any(_hav(cen, p[:2]) <= PROX_KM for p in pts):
                refuse(unit, "within 20 km of a burned unit")
                continue
            sh_lat, sh_lon = 2.0 / 111.32, 2.0 / (111.32 * math.cos(math.radians(cen[1])))
            inner = [w + sh_lon, s_ + sh_lat, e - sh_lon, n - sh_lat]
            if inner[0] >= inner[2] or inner[1] >= inner[3]:
                refuse(unit, "footprint too small for a box")
                continue
            r = D.pick_reach(ix, inner, inside_only=True)
            if r is None:
                refuse(unit, "no GEOGloWS reach inside the footprint")
                continue
            box = _box(r["lon"], r["lat"], BOX_KM)        # for the overlap rule and the reach check only
            if any(_overlap(box, b) for b in taken):
                refuse(unit, "box overlaps this activation's first unit")
                continue
            pk, why = _river_peak(ix, box, start)
            if pk is None:
                refuse(unit, why)
                continue
            if pk["rp_y"] < 1.5:
                refuse(unit, "river driver check failed (return period < 1.5 y)", rp_y=pk["rp_y"])
                continue
            peak = dt.date.fromisoformat(pk["peak_day"])
            win = s1_passes(ee, r["lon"], r["lat"], (peak - dt.timedelta(days=1)).isoformat(),
                            (peak + dt.timedelta(days=MAX_LAG[ty] + 1)).isoformat())
            if not win:
                refuse(unit, "no Sentinel-1 pass in [peak - 1 d, peak + MAX_LAG]", peak=pk["peak_day"])
                continue
            t0, orbit = win[0]
            t0d = dt.date.fromisoformat(t0)
            nb = 0
            for yr in (0, 1):
                b0 = (t0d - dt.timedelta(days=60 + 365 * yr)).isoformat()
                b1 = (t0d - dt.timedelta(days=6 + 365 * yr) + dt.timedelta(days=1)).isoformat()
                nb = sum(1 for d_, o in s1_passes(ee, r["lon"], r["lat"], b0, b1) if o == orbit)
                if nb >= 2:
                    break
            if nb < 2:
                refuse(unit, "fewer than 2 same-orbit baseline passes", t0=t0)
                continue
            taken.append(box)
            rows.append({"unit": unit, "code": code, "aoi_group": g, "tags": [ty], "title": a["title"],
                         "event": start, "peak_day": pk["peak_day"], "peak_rp_y": pk["rp_y"], "reach": r,
                         "image": t0, "orbit": orbit, "lag_days": (t0d - peak).days, "baseline_passes": nb,
                         "baseline_year_before": yr == 1, "search_point": [r["lat"], r["lon"]], "bbox_at_search_point": [round(x, 6) for x in box],
                         "cluster": f"mm_{code.lower()}", "source": "MMFlood event list; v3 Sentinel-1 label"})
            print(unit, ty, pk["peak_day"], pk["rp_y"], t0, flush=True)
    json.dump({"candidates": rows, "refused": refused}, open(os.path.join(OUT, "r3_mmflood_candidates.json"), "w"),
              indent=1)
    print(len(rows), "units from", len({r["code"] for r in rows}), "activations;", len(refused), "refused")
    return 0


# ---------------------------------------------------------------- R40: login-free seal (criteria §11, §12)
SEAL_DATE = "2026-11-28"
FN_SENSORS = "https://data.cityofnewyork.us/resource/kb2e-tjy3.json?$limit=5000"
FN_CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/floodnet")
BATTERY = "8518750"
FN_EXCLUDED_DAY = "2026-11-09"          # FLOODNET_TEST_DESIGN rule 6
EVENT_CAP = 2                           # §6 / §11: at most 2 units per joined event
FN_STORM_CAP = 12                       # §12: FloodNet storms taken (compute)


def _imerg_daily(ee, bbox, d0, d1):
    """IMERG daily totals (mm), mean over bbox (no buffer), one value per UTC day in [d0, d1); cached per year."""
    from experiments.flood_round3 import diagnose_ee as D
    out = {}
    y0, y1 = int(d0[:4]), int(d1[:4])
    for y in range(y0, y1 + 1):
        p = os.path.join(FN_CACHE, f"imerg_nyc_{y}.json")
        if not os.path.exists(p):
            a, b = dt.date(y, 1, 1), min(dt.date(y + 1, 1, 1), dt.date.fromisoformat(d1))
            col = ee.ImageCollection(D.IMERG).select("precipitation")
            region = ee.Geometry.Rectangle(list(bbox))
            days = [a + dt.timedelta(days=k) for k in range((b - a).days)]
            vals = {}
            for i in range(0, len(days), 60):
                chunk = days[i:i + 60]
                img = ee.Image.cat([col.filterDate(d.isoformat(), (d + dt.timedelta(days=1)).isoformat()).sum()
                                    .multiply(0.5).rename(d.isoformat()) for d in chunk])
                for k in range(3):
                    try:
                        vals.update(img.reduceRegion(ee.Reducer.mean(), region, 10000, maxPixels=1e9).getInfo())
                        break
                    except Exception as e:          # noqa: BLE001
                        print("EE:", type(e).__name__, str(e)[:120], flush=True)
                        time.sleep(15 * (k + 1))
                else:
                    raise RuntimeError("IMERG failed")
            if b.year == y + 1 or b >= dt.date(y, 12, 31):
                json.dump(vals, open(p, "w"))
            else:
                out.update(vals)
                continue
        out.update(json.load(open(p)))
    return {k: v for k, v in out.items() if d0 <= k < d1}


def floodnet_storms():
    """FLOODNET_TEST_DESIGN rules 1-4 and 6, metadata only (IMERG, Battery tide, sensor install dates)."""
    from experiments.flood_round3 import diagnose_ee as D
    from experiments.flood_round3 import rain311 as R3
    os.makedirs(FN_CACHE, exist_ok=True)
    sp = os.path.join(FN_CACHE, "sensors.json")
    if not os.path.exists(sp):
        open(sp, "wb").write(urllib.request.urlopen(FN_SENSORS, timeout=120).read())
    sensors = [x for x in json.load(open(sp)) if x.get("tidally_influenced") == "No" and x.get("date_installed")
               and x.get("latitude") and x.get("longitude")]
    ee = D._init()
    rain = _imerg_daily(ee, R3.CITIES["nyc"]["bbox"], "2021-12-30", SEAL_DATE)
    days = sorted(rain)
    v = np.array([rain[d] or 0.0 for d in days])
    k3 = np.convolve(v, np.ones(3), mode="same")
    peaks = [(days[i], float(k3[i])) for i in range(1, len(days) - 1) if k3[i] >= 25.0 and days[i] >= "2022-01-01"]
    groups, cur = [], []                          # overlapping windows -> one storm (largest 3-day sum)
    for d, r in peaks:
        w0 = dt.date.fromisoformat(d) - dt.timedelta(days=1)
        if cur and w0 < dt.date.fromisoformat(cur[-1][0]) + dt.timedelta(days=2):
            cur.append((d, r))
        else:
            if cur:
                groups.append(cur)
            cur = [(d, r)]
    if cur:
        groups.append(cur)
    minor = R3._json(R3.FLOODLEVELS.format(BATTERY))["nos_minor"]
    out = []
    for g in groups:
        d, r = max(g, key=lambda x: (x[1], x[0]))
        pk = dt.date.fromisoformat(d)
        w0, w1 = pk - dt.timedelta(days=1), pk + dt.timedelta(days=2)
        row = {"unit": f"r3fn_{d}", "peak_day": d, "rain_3day_mm": round(r, 1), "window": [w0.isoformat(), w1.isoformat()]}
        if w1.isoformat() > SEAL_DATE:
            row["refused"] = "window not complete at the seal date"
        elif w0.isoformat() <= FN_EXCLUDED_DAY < w1.isoformat():
            row["refused"] = "rule 6: window contains 2026-11-09 (one record seen)"
        else:
            tide = R3.tide_max_ft(BATTERY, (pk - dt.timedelta(days=1)).isoformat(), (pk + dt.timedelta(days=1)).isoformat())
            row["tide_max_ft"], row["tide_minor_ft"] = tide, minor
            active = [x for x in sensors if x["date_installed"][:10] <= (w0 - dt.timedelta(days=1)).isoformat()]
            row["active_nontidal_sensors"] = len(active)
            if tide is None:
                row["refused"] = "rule 2: no Battery tide record for the window (cannot confirm below minor)"
            elif tide >= minor:
                row["refused"] = "rule 2: Battery at or above NOAA minor flood level"
            elif len(active) < 100:
                row["refused"] = "rule 4: fewer than 100 active non-tidal sensors"
        out.append(row)
        print(row, flush=True)
    return out


def ems_timing():
    """§1-§4 on the public EMS candidates, with the driver and timing checks (metadata only)."""
    from experiments.flood_round3 import diagnose_ee as D
    cands = json.load(open(os.path.join(OUT, "r3_ems_candidates.json")))["candidates"]
    used = used_codes()
    ix = D._reach_index()
    ee = D._init()
    rows = []
    for c in cands:
        r = {**c, "label_family": "EMS", "source": "public EMS activation (dashboard list)"}
        ty = c["tags"][0]
        if c["code"] in used:
            r["refused"] = "§1 activation already used"
        elif c["near_used_units"]:
            r["refused"] = "§1 within 20 km of a used unit"
        elif c["aoi_km2"] < MIN_AOI_KM2:
            r["refused"] = f"§4 AOI {c['aoi_km2']} km2 < {MIN_AOI_KM2}"
        elif c["affected_ha"] < MIN_AFFECTED_HA:
            r["refused"] = f"§4 affected {c['affected_ha']} ha < {MIN_AFFECTED_HA}"
        elif not c["images"]:
            r["refused"] = "§3 no image time in the product metadata"
        else:
            img = dt.date.fromisoformat(c["images"][0][:10])
            if ty in ("fluvial", "waterlogging"):
                pk, why = _river_peak(ix, c["bounds"], c["event"])
                if pk is None:
                    r["refused"] = f"§2 {why}"
                elif pk["rp_y"] < 1.5:
                    r["refused"], r["peak"] = "§2 river driver: return period < 1.5 y", pk["peak_day"]
                else:
                    r["peak"], r["driver"] = pk["peak_day"], {"rp_y": pk["rp_y"], "peak_q": pk["peak_q"]}
            else:
                mean, _ = D.rain_series(ee, c["bounds"], c["event"])
                dd = sorted(mean)
                vv = np.array([mean[d] or 0.0 for d in dd])
                k3 = np.convolve(vv, np.ones(3), mode="same")
                ev = dt.date.fromisoformat(c["event"])
                near = [j for j, d in enumerate(dd) if -3 <= (dt.date.fromisoformat(d) - ev).days <= 1]
                j = near[int(np.argmax(k3[near]))]
                r["peak"], r["driver"] = dd[j], {"imerg_3day_mm": round(float(k3[j]), 1)}
                if k3[j] < 20:
                    r["refused"] = "§2 rain driver: IMERG 3-day < 20 mm"
            if "refused" not in r:
                lag = (img - dt.date.fromisoformat(r["peak"])).days
                r["image_lag_days"] = lag
                if not (-1 <= lag <= MAX_LAG[ty]):
                    r["refused"] = f"§3 first image {lag} d from the peak, outside [-1, {MAX_LAG[ty]}]"
        rows.append(r)
        print(r["unit"], ty, r.get("peak"), r.get("image_lag_days"), r.get("refused", "OK"), flush=True)
    return rows


def _join(units):
    """§11 / GFM_DESIGN §3: same named storm, or centres <= 20 km and peaks <= 10 d apart, chained."""
    par = list(range(len(units)))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i
    for i, a in enumerate(units):
        for j in range(i + 1, len(units)):
            b = units[j]
            same = a.get("storm") and a.get("storm") == b.get("storm")
            near = _hav(a["centre"], b["centre"]) <= PROX_KM and abs(
                (dt.date.fromisoformat(a["peak"]) - dt.date.fromisoformat(b["peak"])).days) <= 10
            if same or near:
                par[f(i)] = f(j)
    roots = {}
    for i, u in enumerate(units):
        u["event_id"] = roots.setdefault(f(i), f"ev{len(roots):03d}")
    return units


def seal():
    """Write reserve_r3.json (+ sha256) from metadata only. No label, feature or score is read."""
    import hashlib
    dev_pts = _used_points()
    pl = [c for c in json.load(open(os.path.join(OUT, "plains_candidates.json")))["candidates"] if c["split"] == "reserve"]
    units, refused = [], []
    for c in pl:
        lat, lon = c["search_point"]
        units.append({"unit": c["unit"], "type": "waterlogging", "label_family": "S1v3", "source": c["source"],
                      "event": c["event"], "peak": c["peak_day"], "image": c["image"], "centre": [lon, lat],
                      "square": c["square"], "storm": c["cluster"], "order": len(units)})     # §12: one (plain, year) = one event
    for r in ems_timing():
        if r.get("refused"):
            refused.append({"unit": r["unit"], "why": r["refused"]})
            continue
        units.append({"unit": r["unit"], "type": r["tags"][0], "label_family": "EMS", "source": r["source"],
                      "code": r["code"], "aoi": r["aoi"], "event": r["event"], "peak": r["peak"], "images": r["images"],
                      "sensors": r["sensors"], "centre": r["centre"], "bounds": r["bounds"], "driver": r.get("driver"),
                      "storm": None, "order": len(units)})
    _join(units)
    taken, per_event, per_act = [], {}, {}
    for u in sorted(units, key=lambda u: u["order"]):
        k = u["event_id"]
        if per_event.get(k, 0) >= EVENT_CAP or (u.get("code") and per_act.get(u["code"], 0) >= AOIS_PER_ACTIVATION):
            refused.append({"unit": u["unit"], "why": f"§11 event cap ({EVENT_CAP} per joined event / activation)"})
            continue
        per_event[k] = per_event.get(k, 0) + 1
        if u.get("code"):
            per_act[u["code"]] = per_act.get(u["code"], 0) + 1
        u["near_dev_unit_20km"] = any(_hav(u["centre"], q[:2]) <= PROX_KM for q in dev_pts)
        taken.append(u)
    fn = floodnet_storms()
    ok = sorted((x for x in fn if not x.get("refused")), key=lambda x: (-x["rain_3day_mm"], x["peak_day"]))
    for x in ok[FN_STORM_CAP:]:                  # §12 compute cap: the FN_STORM_CAP largest IMERG storms
        x["refused"] = f"§12 cap: not among the {FN_STORM_CAP} storms with the largest IMERG 3-day totals (compute)"
    crit = os.path.join(HERE, "RESERVE_CRITERIA_R3.md")
    out = {"sealed": SEAL_DATE, "criteria_sha256": hashlib.sha256(open(crit, "rb").read()).hexdigest(),
           "design_sha256": {f: hashlib.sha256(open(os.path.join(HERE, f), "rb").read()).hexdigest()
                             for f in ("GFM_DESIGN.md", "FLOODNET_TEST_DESIGN.md")},
           "units": taken, "floodnet_storms": [s for s in fn if not s.get("refused")],
           "floodnet_refused": [s for s in fn if s.get("refused")], "refused": refused,
           "counts": {t: sum(1 for u in taken if u["type"] == t) for t in sorted({u["type"] for u in taken})}}
    out["counts"]["rain_floodnet_storms"] = len(out["floodnet_storms"])
    p = os.path.join(OUT, "reserve_r3.json")
    json.dump(out, open(p, "w"), indent=1)
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
    print(json.dumps(out["counts"]), "sha256", h, flush=True)
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    return {"ems": ems, "mmflood": mmflood, "seal": seal}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
