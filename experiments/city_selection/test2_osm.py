"""
Test 2 — OSM road and waterway coverage.

Measures what the pipeline's OSM layers would actually get, using the same
query shape and User-Agent as `generate_osm_road_masks.py`, so a candidate's
number means the same thing as the existing 11's.

The ENDPOINT LIST deliberately differs from that file's. Its round-robin
carries three hosts and two of them -- overpass.kumi.systems and
overpass.openstreetmap.ru -- time out from here, so `URLS[attempt % 3]` spent
two of every four retries on dead servers. This script uses only the reachable
host. The production path still has the stale list; filed as C44.

MAJOR TYPES ARE REPORTED SEPARATELY because they are what the road builder
consumes: `build_osm_patches` filters to PAVED_TYPES = primary, secondary,
tertiary, trunk, motorway and their _link variants, and ignores residential,
unclassified and service entirely. A city can be densely mapped in residential
streets and still supply almost nothing to that builder.

Lengths are geodesic (haversine over each way's node list). That is accurate
to well under a percent at these distances and avoids a reprojection step per
city.

INTERSECTION DENSITY is counted here rather than in test 4 because it needs
the same node data: a node shared by two or more distinct ways. It is a
morphology descriptor -- gridded formal fabric and organic informal fabric
differ in it sharply -- and it costs nothing extra once the ways are in hand.

The absolute numbers do not mean much on their own, which is why the existing
11 are measured identically. The comparison is the measurement.
"""
from __future__ import annotations

import json
import math
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.city_selection.aois import all_sites  # noqa: E402

# ONLY the endpoint that is actually reachable from here. The repo's
# round-robin list (generate_osm_road_masks.py) also carries
# overpass.kumi.systems and overpass.openstreetmap.ru; both were probed via
# /api/status and both time out, so cycling URLS[attempt % 3] spent attempts
# 2 and 3 of every retry on dead hosts. Filed as C44.
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# overpass-api.de reports "Rate limit: 2" -- two concurrent slots per client.
# Requests here are strictly serial, and the delay that matters is BETWEEN
# CITIES, not between retries: a retry storm against a rate-limited server
# just deepens the hole.
CITY_DELAY_S = 12
INTRA_CITY_DELAY_S = 4
HEADERS = {
    "User-Agent": "GeoWatchCopilot/1.0 (research project, contact: local dev)",
    "Content-Type": "application/x-www-form-urlencoded",
}
MAJOR = {"primary", "secondary", "tertiary", "trunk", "motorway",
         "primary_link", "secondary_link", "tertiary_link"}
AOI_AREA_KM2 = 25.0
CACHE = Path(__file__).resolve().parent / "cache" / "test2_osm.json"


def haversine_km(a, b) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


STATUS_SEEN = Counter()


class OverpassStatus(RuntimeError):
    """Carries the HTTP status so the caller can react to it."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def overpass(query: str, label: str = "", retries: int = 5):
    """
    One request at a time, with the HTTP STATUS logged, not just the exception
    type. 429 and 504 are different problems: 429 means back off and slow down,
    504 means the query itself is too heavy and needs splitting. The previous
    version logged only `HTTPError` for both, which made them indistinguishable
    and the right response unknowable.
    """
    last_status, last_exc = None, None
    for attempt in range(retries):
        try:
            r = requests.post(OVERPASS_URL, data={"data": query},
                              headers=HEADERS, timeout=180)
            STATUS_SEEN[r.status_code] += 1
            if r.status_code == 200:
                return r.json()["elements"]
            last_status = r.status_code
            # 429: rate limited -- back off hard and long.
            # 504: gateway timeout -- the query is too heavy; retrying the same
            #      query rarely helps, so fail fast and let the caller split it.
            if r.status_code == 504:
                wait = 10
            elif r.status_code == 429:
                wait = 60 * (attempt + 1)
            else:
                wait = 20 * (attempt + 1)
            body = r.text.strip().splitlines()
            hint = next((ln.strip() for ln in body if "error" in ln.lower()), "")[:120]
            print(f"    [{label}] HTTP {r.status_code} "
                  f"(attempt {attempt + 1}/{retries})"
                  + (f" -- {hint}" if hint else "")
                  + (f"; waiting {wait}s" if attempt < retries - 1 else ""), flush=True)
        except Exception as exc:                      # noqa: BLE001
            last_exc, last_status = exc, None
            STATUS_SEEN[type(exc).__name__] += 1
            wait = 20 * (attempt + 1)
            print(f"    [{label}] {type(exc).__name__} "
                  f"(attempt {attempt + 1}/{retries})"
                  + (f"; waiting {wait}s" if attempt < retries - 1 else ""), flush=True)
        if attempt < retries - 1:
            time.sleep(wait)
    raise OverpassStatus(last_status,
                         f"{label}: failed after {retries} attempts "
                         f"(last status {last_status}, last exc {last_exc})")


def fetch_waterways(bb: str, label: str):
    """
    Combined query first; split into one request per clause on a 504.

    A 504 from Overpass means the query exceeded the server's time budget, so
    retrying it unchanged is wasted. Four narrow queries cost four round trips
    but each is well inside the budget.
    """
    combined = (f'[out:json][timeout:120];'
                f'(way["waterway"]({bb});way["natural"="water"]({bb});'
                f'way["water"]({bb});relation["natural"="water"]({bb}););out geom;')
    try:
        return overpass(combined, f"{label}/water"), False
    except OverpassStatus as exc:
        if exc.status != 504:
            raise
        print(f"    [{label}] water query 504 -- splitting into 4 requests",
              flush=True)
        out = []
        for clause in ('way["waterway"]', 'way["natural"="water"]',
                       'way["water"]', 'relation["natural"="water"]'):
            out.extend(overpass(f'[out:json][timeout:120];({clause}({bb}););out geom;',
                                f"{label}/water:{clause[:18]}"))
            time.sleep(INTRA_CITY_DELAY_S)
        return out, True


def measure(site: dict, label: str = "") -> dict:
    w, s, e, n = site["bbox"]
    bb = f"{s},{w},{n},{e}"

    roads = overpass(f'[out:json][timeout:120];(way["highway"]({bb}););out geom;',
                     f"{label}/roads")
    time.sleep(INTRA_CITY_DELAY_S)
    waters, water_was_split = fetch_waterways(bb, label)

    by_type = Counter()
    len_by_type = defaultdict(float)
    node_ways = defaultdict(set)
    total_km = major_km = 0.0

    for el in roads:
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        hw = (el.get("tags") or {}).get("highway", "unknown")
        km = sum(haversine_km((geom[i]["lat"], geom[i]["lon"]),
                              (geom[i + 1]["lat"], geom[i + 1]["lon"]))
                 for i in range(len(geom) - 1))
        by_type[hw] += 1
        len_by_type[hw] += km
        total_km += km
        if hw in MAJOR:
            major_km += km
        for nd in el.get("nodes") or []:
            node_ways[nd].add(el["id"])

    intersections = sum(1 for ways in node_ways.values() if len(ways) >= 2)

    water_ways = sum(1 for el in waters if el.get("type") == "way")
    water_rels = sum(1 for el in waters if el.get("type") == "relation")
    water_km = 0.0
    for el in waters:
        geom = el.get("geometry") or []
        if len(geom) >= 2 and (el.get("tags") or {}).get("waterway"):
            water_km += sum(haversine_km((geom[i]["lat"], geom[i]["lon"]),
                                         (geom[i + 1]["lat"], geom[i + 1]["lon"]))
                            for i in range(len(geom) - 1))

    return {
        "road_ways": sum(by_type.values()),
        "road_km": total_km,
        "road_km_per_km2": total_km / AOI_AREA_KM2,
        "major_km": major_km,
        "major_km_per_km2": major_km / AOI_AREA_KM2,
        "major_share": (major_km / total_km) if total_km else 0.0,
        "intersections": intersections,
        "intersections_per_km2": intersections / AOI_AREA_KM2,
        "waterway_features": water_ways + water_rels,
        "waterway_km": water_km,
        "water_query_split": water_was_split,
        "top_types": dict(by_type.most_common(8)),
        "km_by_type": {k: round(v, 2) for k, v in
                       sorted(len_by_type.items(), key=lambda kv: -kv[1])[:8]},
    }


def main() -> int:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    out = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    sites = all_sites()
    only = sys.argv[1:] or list(sites)
    for name in only:
        if name in out:
            print(f"  {name:<16} cached")
            continue
        t0 = time.time()
        try:
            out[name] = measure(sites[name], name)
            r = out[name]
            print(f"  {name:<16} {r['road_km']:>8.1f} km "
                  f"({r['road_km_per_km2']:>6.2f}/km2) | major {r['major_km']:>6.1f} km "
                  f"({r['major_km_per_km2']:>5.2f}/km2, {r['major_share'] * 100:>4.1f}%) | "
                  f"int {r['intersections_per_km2']:>6.1f}/km2 | "
                  f"water {r['waterway_features']:>4} | {time.time() - t0:.0f}s",
                  flush=True)
        except Exception as exc:                      # noqa: BLE001
            print(f"  {name:<16} ERROR {type(exc).__name__}: {str(exc)[:120]}", flush=True)
            continue
        CACHE.write_text(json.dumps(out, indent=2))
        time.sleep(CITY_DELAY_S)
    CACHE.write_text(json.dumps(out, indent=2))
    print("\n  HTTP status / exception tally across the run:")
    for k, v in STATUS_SEEN.most_common():
        print(f"    {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
