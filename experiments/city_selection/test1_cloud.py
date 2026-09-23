"""
Test 1 — Sentinel-2 cloud-free availability. The hard gate.

TWO MEASURES, because the one the brief names is a proxy.

`CLOUDY_PIXEL_PERCENTAGE` is granule-level metadata: it describes a ~110 x 110
km tile, not a 25 km^2 AOI inside it. A scene can be 40% cloudy overall and
perfectly clear over the AOI, or 8% cloudy overall with the only cloud sitting
on the AOI. Over a box 0.2% of a granule's area that proxy is weak in both
directions, so it is reported (as asked) AND backed by a direct measurement:
the AOI's own clear fraction from SCL.

The SCL definitions are the repo's own (`ingestion/sentinel2.py`):
valid {2,4,5,6,7,11}, cloud {8,9,10}, shadow {3}, nodata {0,1}. Shadow is
counted separately rather than as cloud, matching item 51's decision to keep
shadow pixels. Reduction runs at 60 m, the scale that file benchmarked as
costing ~0.02 pp against a 10 m baseline for a fraction of the time.

The gate the brief sets: >= 4 scenes under 10% cloud in the best season. It is
applied here to the AOI-level measure, with the granule-level count reported
beside it so the two can be compared.
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import ee  # noqa: E402

from experiments.city_selection.aois import all_sites  # noqa: E402
from ingestion.gee_client import initialize_gee  # noqa: E402
from ingestion.sentinel2 import (  # noqa: E402
    SCL_CLOUD_CODES, SCL_NODATA_CODES, SCL_SHADOW_CODES, SCL_VALID_CODES,
)

START, END = "2023-09-01", "2026-09-01"          # last 3 years
SCALE = 60
GATE_N, GATE_PCT = 4, 10.0
CACHE = Path(__file__).resolve().parent / "cache" / "test1_cloud.json"


def measure(site: dict) -> dict:
    w, s, e, n = site["bbox"]
    geom = ee.Geometry.Rectangle([w, s, e, n])
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterDate(START, END).filterBounds(geom))

    def per_image(img):
        scl = img.select("SCL")
        valid = scl.remap(list(SCL_VALID_CODES), [1] * len(SCL_VALID_CODES), 0)
        cloud = scl.remap(list(SCL_CLOUD_CODES), [1] * len(SCL_CLOUD_CODES), 0)
        shadow = scl.remap(list(SCL_SHADOW_CODES), [1] * len(SCL_SHADOW_CODES), 0)
        nodata = scl.remap(list(SCL_NODATA_CODES), [1] * len(SCL_NODATA_CODES), 0)
        stats = (ee.Image.cat(valid.rename("v"), cloud.rename("c"),
                              shadow.rename("s"), nodata.rename("n"))
                 .reduceRegion(ee.Reducer.mean(), geom, SCALE, maxPixels=1e9,
                               bestEffort=True))
        return img.set({
            "aoi_valid": stats.get("v"), "aoi_cloud": stats.get("c"),
            "aoi_shadow": stats.get("s"), "aoi_nodata": stats.get("n"),
        })

    withstats = col.map(per_image)
    got = withstats.reduceColumns(
        ee.Reducer.toList().repeat(6),
        ["system:time_start", "CLOUDY_PIXEL_PERCENTAGE",
         "aoi_valid", "aoi_cloud", "aoi_shadow", "aoi_nodata"]).getInfo()["list"]

    times, cpp, av, ac, ash, an = got
    scenes = []
    for t, p, v, c, sh, nd in zip(times, cpp, av, ac, ash, an):
        if v is None:
            continue
        import datetime as dt
        d = dt.datetime.fromtimestamp(t / 1000.0, dt.timezone.utc)
        scenes.append({
            "date": d.strftime("%Y-%m-%d"), "month": d.month,
            "granule_cloud_pct": None if p is None else float(p),
            "aoi_valid_pct": float(v) * 100.0,
            "aoi_cloud_pct": float(c) * 100.0,
            "aoi_shadow_pct": float(sh) * 100.0,
            "aoi_nodata_pct": float(nd) * 100.0,
        })

    # Scenes that actually see the AOI at all (a granule edge can clip it).
    seen = [s for s in scenes if s["aoi_nodata_pct"] < 50.0]

    # Adjacent granules overlap, so one satellite pass can return several
    # "scenes" over a 25 km^2 box on the same day. A composite is built from
    # DATES, not granules, so every count below is over distinct dates -- the
    # best (least cloudy) view of the AOI on each date.
    by_date = {}
    for sc in seen:
        cur = by_date.get(sc["date"])
        if cur is None or sc["aoi_cloud_pct"] < cur["aoi_cloud_pct"]:
            by_date[sc["date"]] = sc
    dates = sorted(by_date.values(), key=lambda x: x["date"])

    def n_under(pct, key):
        return sum(1 for s in dates if s[key] is not None and s[key] < pct)

    by_month = defaultdict(int)
    for s in dates:
        if s["aoi_cloud_pct"] < GATE_PCT:
            by_month[s["month"]] += 1

    best_window, best_count = None, -1
    for start_m in range(1, 13):
        months = [((start_m - 1 + k) % 12) + 1 for k in range(3)]
        c = sum(by_month.get(m, 0) for m in months)
        if c > best_count:
            best_count, best_window = c, months

    return {
        "n_scenes_total": len(scenes),
        "n_scenes_seeing_aoi": len(seen),
        "n_distinct_dates": len(dates),
        "granule_lt10": n_under(10.0, "granule_cloud_pct"),
        "granule_lt20": n_under(20.0, "granule_cloud_pct"),
        "aoi_cloud_lt10": n_under(10.0, "aoi_cloud_pct"),
        "aoi_cloud_lt20": n_under(20.0, "aoi_cloud_pct"),
        "best_window_months": best_window,
        "best_window_n_lt10": best_count,
        "median_aoi_cloud_pct": (sorted(s["aoi_cloud_pct"] for s in dates)[len(dates) // 2]
                                 if dates else None),
        "passes_gate": best_count >= GATE_N,
        "scenes": scenes,
    }


def main() -> int:
    initialize_gee()
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
            out[name] = measure(sites[name])
            r = out[name]
            print(f"  {name:<16} {r['n_distinct_dates']:>4} dates | "
                  f"granule<10 {r['granule_lt10']:>3} | AOI<10 {r['aoi_cloud_lt10']:>3} | "
                  f"best {r['best_window_months']} n={r['best_window_n_lt10']:>3} | "
                  f"{'PASS' if r['passes_gate'] else 'FAIL'} | {time.time() - t0:.0f}s",
                  flush=True)
        except Exception as exc:
            print(f"  {name:<16} ERROR {type(exc).__name__}: {str(exc)[:120]}", flush=True)
            continue
        CACHE.write_text(json.dumps(out, indent=2))
    CACHE.write_text(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
