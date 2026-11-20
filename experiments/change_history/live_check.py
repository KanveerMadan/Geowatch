"""Development check on two hand-selected cells, run with python -m experiments.change_history.live_check.

Run 'prepare' to fetch observations and independent endpoint reference, then
'evaluate' to execute the ordinary detector. All caches are local to --cache.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform

# Fixed prospectively for this development check; do not select fallback sites
# where the reference is ambiguous or the signal fails to trigger.
SITES = {"kakhovka_interior": (34.355, 47.525), "kremenchuk_upstream": (32.485, 49.318)}
HISTORY = "2020-01-01"
MONITOR = "2023-06-01"
END = "2023-09-01"
BEFORE = ("2023-05-01", "2023-06-06")
AFTER = ("2023-07-01", "2023-09-01")


def cell(lon, lat):
    # Use the full 100 m UTM cell containing the predeclared coordinate.
    crs = CRS.from_epsg(32600 + int((lon + 180) // 6) + 1)
    project = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    x, y = (int(v // 100) * 100 for v in project(lon, lat))
    square = box(x, y, x + 100, y + 100)
    return SimpleNamespace(aoi=square, bbox=transform(to_ll, square).bounds, crs=crs)


def reference(layer, window):
    """USGS CFMASK water bit on separate Landsat platforms. Record every date,
    including cloud-obscured ones. Report the water-label share on clear pixels
    only, with the clear pixel count. Landsat is excluded from detector input.
    """
    import ee
    from ee_timeout import call

    if not ee.data.is_initialized():
        from ingestion.gee_client import initialize_gee
        initialize_gee()
    geom = ee.Geometry(mapping(layer.aoi), proj=layer.crs.to_string(), geodesic=False)
    output = []
    for mission in ("LC08", "LC09"):
        asset = f"LANDSAT/{mission}/C02/T1_L2"
        collection = ee.ImageCollection(asset).filterBounds(geom).filterDate(*window)
        def summarize(image):
            image = ee.Image(image)
            qa = image.select("QA_PIXEL")
            clear = qa.bitwiseAnd(63).eq(0).And(image.select("QA_RADSAT").eq(0))
            water = qa.bitwiseAnd(128).neq(0).rename("water").updateMask(clear)
            clear_count = water.multiply(0).add(1).rename("clear")
            stats = water.addBands(clear_count).reduceRegion(
                reducer=ee.Reducer.sum().unweighted(), geometry=geom, crs=qa.projection(),
                maxPixels=1000)
            return image.set("_check", stats.set("id", image.get("system:index"))
                             .set("timestamp", image.get("system:time_start")))
        rows = call(collection.map(summarize).aggregate_array("_check").getInfo,
                    retries=1, label=f"independent Landsat {window[0]}")
        for r in rows:
            n = int(r.get("clear") or 0)
            output.append({"id": asset + "/" + r["id"], "date": datetime.fromtimestamp(
                r["timestamp"] / 1000, timezone.utc).date().isoformat(), "clear_pixels": n,
                           "water_pixels": int(r.get("water") or 0) if n else None})
    return sorted(output, key=lambda r:r["date"])


def prepare(cache):
    from vector.change_observations import open_history
    for name, ll in SITES.items():
        area = cell(*ll)
        tiles = list(open_history(area, HISTORY, END, cache_dir=cache / "sensor",
                                  sources=["sentinel2"]).tiles())
        if len(tiles) != 1 or len(tiles[0]["cells"]) != 1:
            raise ValueError("test geometry should comprise one reporting cell")
        tile, = tiles
        report = {"site": name, "cell": tile["cells"][0]["cell_id"], "catalog": tile["diagnostics"],
                  "before": reference(area, BEFORE), "after": reference(area, AFTER)}
        if any(d["errors"] for d in report["catalog"]):
            raise RuntimeError(f"source errors for {name}: {report['catalog']}")
        (cache / (name + "-reference.json")).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(name, report["catalog"], flush=True)


def evaluate(cache):
    from analysis.change_history import run_history, cell_detail
    from vector.change_detection import MODEL_VERSION
    epochs = {"s2": ((HISTORY, MONITOR), (MONITOR, END))}
    outputs = []
    for name, ll in SITES.items():
        area = cell(*ll)
        report = json.loads((cache / (name + "-reference.json")).read_text(encoding="utf-8"))
        run = run_history(area, epochs, cache_dir=cache / "sensor", sources=["sentinel2"])
        try:
            detail = cell_detail(Path(run["archive"].name) / "history.sqlite", 0)
            rows = detail.pop("observations")
            dates = Counter("history" if r["date"] < MONITOR else "monitor"
                            for r in rows if np.isfinite(r["values"].get("mndwi", np.nan)))
            report.update(model_version=MODEL_VERSION, bounds=list(area.bbox), monitoring=[MONITOR, END],
                          usable_dates_by_period=dict(dates), detector=detail)
        finally:
            run["archive"].cleanup()
        outputs.append(report)
    print(json.dumps(outputs, indent=2))


def historical_buildings(cache):
    """One annual product on one full 100 m Navi Mumbai cell, using real product dates."""
    from vector.change_observations import open_history
    area = cell(73.054, 18.99)
    for tile in open_history(area, "2022-01-01", "2023-01-01", cache_dir=cache / "sensor",
                             sources=["open_buildings"]).tiles():
        rows = [{"effective_date": o["date"], "target": o["inference_date"],
                 "contributing_imagery": o["imagery_interval"], "coverage": float(o["coverage"][0]),
                 "confidence": float(o["values"]["building_presence"][0]),
                 "ids": [s["system:index"] for s in o["scenes"]]}
                for o in tile["observations"]]
        print(json.dumps({"catalog": tile["diagnostics"], "records": rows}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "evaluate", "buildings"])
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    stages = {"prepare": prepare, "evaluate": evaluate, "buildings": historical_buildings}
    stages[args.stage](args.cache)


if __name__ == "__main__":
    main()
