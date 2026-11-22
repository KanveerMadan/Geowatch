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


def main(argv=None):
    a = argv or sys.argv[1:]
    return {"ems": ems}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
