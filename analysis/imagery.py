"""
True-colour Sentinel-2 imagery of a stored result's area, one year at a time,
for the Change tab's before / after swipe (Phase 4 Step B).

Each year's picture is the median of the same collection and cloud mask the
analysis reads (ingestion.sentinel2: S2_SR_HARMONIZED, SCL mask), over the
result's own calendar window moved to that year, so the swipe shows what the
change test compared and nothing it did not. It is a picture, not a
measurement: no number is derived from it.

Rendered in Web Mercator over the result's bbox, so it lies on the map's own
projection. Cached on disk outside the immutable result store
(data/imagery/<result_id>/<year>.png); a year with no clear scene is cached as
a JSON note saying so, never as a blank image.
"""
from __future__ import annotations

import json
import os
from datetime import date

IMAGERY_ROOT = os.path.join("data", "imagery")
FIRST_YEAR = 2017                    # S2_SR_HARMONIZED's first full year
CLOUD_COVER_THRESHOLD = 60           # the fraction producer's (vector.fractions)
MAX_PX = 1024                        # long side of the PNG
# Display stretch for surface reflectance (B4, B3, B2 / 10000). Fixed
# 2026-10-30: a picture setting, not an analysis parameter.
VIS = {"min": 0.0, "max": 0.3, "gamma": 1.3}


def years_for(window: dict) -> list:
    """Every year the swipe can show for a result's window."""
    end = date.fromisoformat(window["end"]).year
    return list(range(FIRST_YEAR, end + 1))


def window_in(window: dict, year: int) -> tuple:
    """The result's calendar window moved to `year` (end year = `year`)."""
    from analysis.run import _years_back
    s, e = date.fromisoformat(window["start"]), date.fromisoformat(window["end"])
    n = e.year - year
    return _years_back(s, n).isoformat(), _years_back(e, n).isoformat()


def _paths(rid: str, year: int, root: str) -> tuple:
    d = os.path.join(root, rid)
    return d, os.path.join(d, f"{year}.png"), os.path.join(d, f"{year}.json")


def cached(rid: str, year: int, root: str = IMAGERY_ROOT):
    """(png bytes, None) or (None, note) when cached, else (None, None)."""
    _, png, note = _paths(rid, year, root)
    if os.path.exists(png):
        with open(png, "rb") as fh:
            return fh.read(), None
    if os.path.exists(note):
        with open(note) as fh:
            return None, json.load(fh)
    return None, None


def fetch_png(bbox, start: str, end: str) -> tuple:
    """(png bytes, scene count), or (None, 0) when no scene covers the window."""
    import ee
    import requests
    from ingestion.gee_client import initialize_gee
    from ingestion.sentinel2 import get_sentinel2_collection, mask_s2_clouds
    initialize_gee()
    w, s, e, n = bbox
    region = ee.Geometry.Rectangle([w, s, e, n])
    col = get_sentinel2_collection(region, start, end, CLOUD_COVER_THRESHOLD)
    count = col.size().getInfo()
    if count == 0:
        return None, 0
    img = col.map(mask_s2_clouds).select(["Red", "Green", "Blue"]).median()
    url = img.visualize(bands=["Red", "Green", "Blue"], **VIS).getThumbURL(
        {"region": region, "dimensions": MAX_PX, "crs": "EPSG:3857", "format": "png"})
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    return r.content, int(count)


def get_year(rid: str, result: dict, year: int, *, root: str = IMAGERY_ROOT, fetch=None) -> tuple:
    """(png bytes, None) or (None, note). Fetches once, then serves the cache."""
    png, note = cached(rid, year, root)
    if png is not None or note is not None:
        return png, note
    start, end = window_in(result["request"]["window"], year)
    png, count = (fetch or fetch_png)(result["request"]["bbox"], start, end)
    d, p_png, p_note = _paths(rid, year, root)
    os.makedirs(d, exist_ok=True)
    if png is None:
        note = {"year": year, "window": [start, end], "status": "unavailable",
                "reason": "no Sentinel-2 scene under the cloud limit in this window"}
        _write(p_note, json.dumps(note).encode())
        return None, note
    _write(p_png, png)
    return png, None


def _write(path: str, data: bytes) -> None:
    """Atomic, so a reader never sees half a file."""
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, path)
