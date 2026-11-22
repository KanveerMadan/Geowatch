"""
Round 3, rain (R30): survey of open 311 / flood-report data in more cities, by fixed intake criteria
(RAIN_311_DESIGN "City intake"). Metadata only: type names and daily counts, never report locations.

    python -m experiments.flood_round3.city_survey      -> results/r311_city_survey.json

Criteria:
- C1: open machine-readable access with a timestamp, a type and point coordinates;
- C2: a type that names street / surface flooding, separate from basement, sewer-backup and catch-basin types;
- C3: >= 1 day with >= 50 such reports city-wide (rain311's event rule) in DEV (< 2022) and in the reserve (>= 2022);
- C4: no licence term that forbids research use.
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
UA = {"User-Agent": "geowatch-research"}
CUT = "2022-01-01"


def _get(url, params=None, data=None):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, headers=UA)
    for k in range(3):
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                return json.load(r)
        except Exception as e:          # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:120]}"
            time.sleep(5 * (k + 1))
    return {"_error": err}


def socrata_days(api, tfield, kfield, kinds, extra_where=""):
    ks = ",".join("'" + k.replace("'", "''") + "'" for k in kinds)
    w = f"{kfield} in ({ks})" + (f" AND {extra_where}" if extra_where else "")
    r = _get(api, {"$select": f"date_trunc_ymd({tfield}) as d, count(*) as n", "$where": w,
                   "$group": "d", "$order": "d", "$limit": 50000})
    if isinstance(r, dict):
        return None, r.get("_error") or str(r)[:150]
    return {x["d"][:10]: int(x["n"]) for x in r}, None


def ckan_days(base, resources, tfield, kfield, kinds):
    out = {}
    ks = ",".join("'" + k.replace("'", "''") + "'" for k in kinds)
    for rid in resources:
        sql = (f'SELECT substr({tfield}::text,1,10) d, count(*) n FROM "{rid}" WHERE {kfield} IN ({ks}) GROUP BY 1')
        r = _get(base + "/api/3/action/datastore_search_sql", {"sql": sql})
        if "_error" in r or not r.get("success"):
            return None, (r.get("_error") or str(r.get("error"))[:150])
        for x in r["result"]["records"]:
            out[x["d"]] = out.get(x["d"], 0) + int(x["n"])
        time.sleep(0.5)
    return out, None


def arcgis_days(layer, tfield, kfield, kinds):
    """ArcGIS FeatureServer/MapServer layer: daily counts via outStatistics on a date cast."""
    ks = ",".join("'" + k.replace("'", "''") + "'" for k in kinds)
    r = _get(layer + "/query", {"where": f"{kfield} IN ({ks})", "outFields": tfield, "returnGeometry": "false",
                                "f": "json", "resultRecordCount": 2000, "orderByFields": tfield})
    if "_error" in r or "error" in r:
        return None, str(r.get("_error") or r.get("error"))[:150]
    return r, None


def summarise(days):
    if not days:
        return {"days_ge50_dev": 0, "days_ge50_reserve": 0, "reports": 0}
    return {"reports": sum(days.values()),
            "days_ge50_dev": sum(1 for d, n in days.items() if n >= 50 and d < CUT),
            "days_ge50_reserve": sum(1 for d, n in days.items() if n >= 50 and d >= CUT),
            "max_day": max(days.items(), key=lambda kv: kv[1]), "first": min(days), "last": max(days)}


def main():
    res = {}
    # New Orleans (Socrata, OPCD 311 2012-present)
    d, e = socrata_days("https://data.nola.gov/resource/2jgv-pqrq.json", "date_created", "request_reason",
                        ("Street Flooding", "Street Flooding / Drainage"))
    res["new_orleans"] = {"portal": "data.nola.gov 2jgv-pqrq", "flood_types": ["Street Flooding", "Street Flooding / Drainage"],
                          "error": e, **summarise(d)}
    # San Francisco (Socrata, 311 Cases)
    d, e = socrata_days("https://data.sfgov.org/resource/vw6y-z8j6.json", "requested_datetime", "service_subtype",
                        ("Flooding", "flooding"), "service_name in ('Sewer Issues','Sewer')")
    res["san_francisco"] = {"portal": "data.sfgov.org vw6y-z8j6", "flood_types": ["Sewer Issues | Flooding"],
                            "error": e, **summarise(d)}
    # Boston (CKAN; legacy yearly 2011-2025 + new system)
    years = {"2011": "94b499d9-712a-4d2a-b790-7ceec5c9c4b1", "2012": "382e10d9-1864-40ba-bef6-4eea3c75463c",
             "2013": "407c5cd0-f764-4a41-adf8-054ff535049e", "2014": "bdae89c8-d4ce-40e9-a6e1-a5203953a2e0",
             "2015": "c9509ab4-6f6d-4b97-979a-0cf2a10c922b", "2016": "b7ea6b1b-3ca4-4c5b-9713-6dc1db52379a",
             "2017": "30022137-709d-465e-baae-ca155b51927d", "2018": "2be28d90-3a90-4af1-a3f6-f28c1e25880a",
             "2019": "ea2e4696-4a2d-429c-9807-d02eb92e0222", "2020": "6ff6a6fd-3141-4440-a880-6f60a37fe789",
             "2021": "f53ebccd-bc61-49f9-83db-625f209c95f5", "2022": "81a7b022-f8fc-4da5-80e4-b160058ca207",
             "2023": "e6013a93-1321-4f2a-bf91-8d8a02f1e62f", "2024": "dff4d804-5031-443a-8409-8344efd0e5c8",
             "2025": "9d7c2214-4709-478a-a2e8-fb2020a5bb94"}
    d, e = ckan_days("https://data.boston.gov", list(years.values()), "open_dt", "type", ("Roadway Flooding",))
    res["boston"] = {"portal": "data.boston.gov 311-service-requests (PDDL)", "flood_types": ["Roadway Flooding"],
                     "error": e, **summarise(d)}
    json.dump(res, open(os.path.join(OUT, "r311_city_survey.json"), "w"), indent=1, default=str)
    for k, v in res.items():
        print(k, json.dumps(v, default=str)[:300], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
