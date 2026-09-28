"""
Item 21 §9 pilot B (label-free, 2026-09-28): time window.

Per site, the number of distinct Sentinel-2 L2A acquisition DATES with a scene
under 20% cloud (scene-level CLOUDY_PIXEL_PERCENTAGE, as in the site list)
intersecting the approved 3 x 3 km box, within +-60 and +-90 days of the
chosen high-resolution imagery date. Where that date is only known as a range
(Rocinha: 2024-01-01..06-30; Cape Town: "2025Jan"), the WORST case -- the
fewest -- over every day in the range is reported, with the day it occurs.
Nothing is chosen.

    python experiments/item21_sites/pilot_b_time_window.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "pilot_b_time_window.json")

HALF_WINDOWS = (60, 90)
CLOUD_MAX = 20
# The chosen scene's acquisition date, or (start, end) when only a range is known.
HR_DATES = {
    "makoko": ("2019-10-02",),
    "kibera": ("2023-11-30",),
    "rocinha": ("2024-01-01", "2024-06-30"),     # pre-registered range (IPP "1st half 2024")
    "lima": ("2019-12-19",),
    "monrovia": ("2020-02-23",),
    "karachi": ("2022-03-29",),
    "cape_town": ("2025-01-01", "2025-01-31"),   # service name only: "2025Jan"
}


def clear_dates(crs, box_utm, start: date, end: date) -> list:
    import ee
    g = ee.Geometry.Rectangle(list(box_utm), crs, False)
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(g)
           .filterDate(start.isoformat(), (end + timedelta(days=1)).isoformat())
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", CLOUD_MAX)))
    return sorted({datetime.fromtimestamp(t / 1000, timezone.utc).date()
                   for t in col.aggregate_array("system:time_start").getInfo()})


def counts_around(dates: list, day: date) -> dict:
    return {f"pm{h}": sum(abs((d - day).days) <= h for d in dates) for h in HALF_WINDOWS}


def main():
    from ingestion.gee_client import initialize_gee
    from labelling.common import load_config
    initialize_gee()
    cfg = load_config()
    out = {"rule": f"distinct dates with a scene < {CLOUD_MAX}% cloud intersecting the approved box",
           "sites": {}}
    for site, hr in HR_DATES.items():
        a = cfg["aois"][site]
        d0 = date.fromisoformat(hr[0])
        d1 = date.fromisoformat(hr[-1])
        m = max(HALF_WINDOWS)
        dates = clear_dates(a["crs"], a["box_utm"], d0 - timedelta(days=m), d1 + timedelta(days=m))
        if d0 == d1:
            row = {"hr_date": hr[0], **counts_around(dates, d0)}
        else:
            days = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
            per_day = {d: counts_around(dates, d) for d in days}
            row = {"hr_date_range": list(hr)}
            for h in HALF_WINDOWS:
                k = f"pm{h}"
                worst = min(days, key=lambda d: (per_day[d][k], d))
                row[f"{k}_worst"] = per_day[worst][k]
                row[f"{k}_worst_on"] = worst.isoformat()
                row[f"{k}_best"] = max(per_day[d][k] for d in days)
        out["sites"][site] = row
        print(site, row, flush=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    print(OUT)


if __name__ == "__main__":
    main()
