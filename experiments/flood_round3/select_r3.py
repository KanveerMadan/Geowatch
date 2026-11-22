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


def main(argv=None):
    a = argv or sys.argv[1:]
    return {"ems": ems, "mmflood": mmflood}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
