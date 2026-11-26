"""Context for flood round 5's conditional types (susceptibility/conditional_flood.py).

- glacial_lakes: inventoried glacial lakes (GLOF v4.2 lake source points, bundled in
  configs/data/glof_lakes.csv, CC BY 4.0) within LAKE_SEARCH_KM of the area. Offline, no network.
- snow_days: mean annual number of MODIS Terra snow-covered days (NDSI snow cover >= 10) over the
  area, 2015-2024. One Earth Engine reduction.
"""
from __future__ import annotations

import csv
import math
import os

from configs import m678_constants as K

LAKES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs", "data", "glof_lakes.csv")


def _km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2)
    return 12742.0 * math.asin(math.sqrt(a))


def glacial_lakes(w, s, e, n, search_km: float = K.LAKE_SEARCH_KM) -> dict:
    lat, lon = (s + n) / 2, (w + e) / 2
    half = 0.5 * max(_km(s, lon, n, lon), _km(lat, w, lat, e))
    near = []
    with open(LAKES) as fh:
        for r in csv.DictReader(fh):
            d = _km(lat, lon, float(r["lat"]), float(r["lon"]))
            if d <= search_km + half:
                near.append({"lake": r["lake"], "km": round(d, 1)})
    near.sort(key=lambda x: x["km"])
    return {"status": "available", "count_within_km": len(near), "search_km": search_km,
            "nearest": near[:5], "source": "GLOF v4.2 (Lützow & Veh), CC BY 4.0"}


def snow_days(w, s, e, n) -> dict:
    import ee
    region = ee.Geometry.Rectangle([w, s, e, n])
    c = ee.ImageCollection("MODIS/061/MOD10A1").filterDate("2015-01-01", "2025-01-01").select("NDSI_Snow_Cover")
    days = c.map(lambda im: im.gte(10).unmask(0)).sum().divide(10)
    v = days.reduceRegion(ee.Reducer.mean(), region, 500, maxPixels=1e8, bestEffort=True).getInfo()
    val = v.get("NDSI_Snow_Cover")
    return {"status": "available" if val is not None else "unavailable",
            "snow_days_per_year": None if val is None else round(float(val), 1),
            "source": "MODIS/061/MOD10A1 NDSI_Snow_Cover >= 10, mean days per year 2015-2024"}
