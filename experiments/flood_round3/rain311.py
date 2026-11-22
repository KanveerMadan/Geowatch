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


def main(argv=None):
    import sys
    a = argv or sys.argv[1:]
    return {"events": events}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
