"""Two fixed 100 m cells for a frozen-detector burn/forest comparison.

Usage: python -m experiments.change_history.vegetation_check --cache /tmp/geowatch-change-check
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from experiments.change_history.live_check import cell

SITES = {"flatiron_ridge": (-121.399, 40.456), "west_park": (-121.582, 40.531)}
START, MONITOR, END = "2018-01-01", "2021-08-01", "2021-11-01"
BOUNDS = "USFS/GTAC/MTBS/burned_area_boundaries/v1"
SEVERITY = "USFS/GTAC/MTBS/annual_burn_severity_mosaics/v1"
LANDSAT = "LANDSAT/LC08/C02/T1_L2"


def reference(area):
    import ee
    from ee_timeout import call
    from shapely.geometry import mapping

    geometry = ee.Geometry(mapping(area.aoi), proj=area.crs.to_string(), geodesic=False)
    fires = (ee.FeatureCollection(BOUNDS).filterBounds(geometry)
             .filter(ee.Filter.gte("Ig_Date", ee.Date("2021-01-01").millis()))
             .filter(ee.Filter.lt("Ig_Date", ee.Date("2022-01-01").millis())))
    fields = ["Event_ID", "Incid_Name", "Ig_Date", "Pre_ID", "Post_ID"]
    ids = fires.map(lambda f: f.set("_row", f.toDictionary(fields))).aggregate_array("_row")
    # The collection's documented study_area property was absent in the
    # 2021 live inventory. Use its verified CONUS image ID instead.
    severity = ee.Image(SEVERITY + "/mtbs_CONUS_2021").select("Severity")
    counts = severity.reduceRegion(ee.Reducer.frequencyHistogram().unweighted(), geometry,
                                   crs=severity.projection(), maxPixels=1000)
    def summarize(image):
        qa = image.select("QA_PIXEL")
        clear = qa.bitwiseAnd(63).eq(0).And(image.select("QA_RADSAT").eq(0))
        bands = image.select(["SR_B4","SR_B5","SR_B7"], ["red","nir","swir2"]).multiply(0.0000275).add(-0.2)
        nbr = bands.normalizedDifference(["nir","swir2"]).rename("nbr")
        ndvi = bands.normalizedDifference(["nir","red"]).rename("ndvi")
        indices = nbr.addBands(ndvi).updateMask(clear)
        stats = indices.reduceRegion(ee.Reducer.median().unweighted().combine(
            ee.Reducer.count(), sharedInputs=True), geometry, crs=qa.projection(), maxPixels=1000)
        return image.set("_row", stats.set("id", image.get("system:index")))
    intervals = {}
    for year in (2020, 2021):
        col = (ee.ImageCollection(LANDSAT).filterBounds(geometry)
               .filterDate(f"{year}-09-01",f"{year}-11-01"))
        intervals[str(year)] = col.map(summarize).aggregate_array("_row")
    q = ee.Dictionary({"fires": ids, "severity_pixel_counts": counts, "reference_severity_id": severity.id(),
                       "landsat_september_october": ee.Dictionary(intervals)})
    return call(q.getInfo, retries=1, label="fire severity, perimeter, independent reflectance")


def run(cache):
    import ee
    from analysis.change_history import cell_detail, run_history
    from ingestion.gee_client import initialize_gee
    from vector import change_detection
    if not ee.data.is_initialized():
        initialize_gee()
    summary = {"version": change_detection.MODEL_VERSION, "detector_sha256": hashlib.sha256(
        Path(change_detection.__file__).read_bytes()).hexdigest(),
        "history_start":START, "window":[MONITOR, END], "end_exclusive":True, "sites":[]}
    for name, ll in SITES.items():
        area = cell(*ll)
        truth = reference(area)
        # Preserve the reference even if network access to the input later fails.
        ref_path = cache / (name + "-mtbs-reference.json")
        ref_path.write_text(json.dumps(truth, indent=2) + "\n")
        product = run_history(area, {"s2": ((START,MONITOR), (MONITOR,END))},
                              cache_dir=cache / "sensor", sources=["sentinel2"])
        try:
            d = cell_detail(Path(product["archive"].name) / "history.sqlite", 0)
            rows = d.pop("observations")
            clean = [r for r in rows if r["values"].get("ndvi") is not None]
            episodes = [{k:e[k] for k in ("event_id","transition","detected_on","confirmed_on",
                                          "onset","last_evidence_on","lifecycle","detections")} |
                        {"track":e["signals"][0]["track"]} for e in d["events"]]
            case = dict(site=name, lon_lat=list(ll), cell_id=d["cell_id"], state=d["state"],
                        acquisitions=len(rows), usable_history=sum(r["date"] < MONITOR for r in clean),
                        usable_monitor=sum(r["date"] >= MONITOR for r in clean),
                        episodes=episodes, reference=truth, series=d["series"], diagnostics=d["diagnostics"],
                        source_status=product["summary"]["source_status"])
        finally:
            product["archive"].cleanup()
        summary["sites"].append(case)
        print(name, case["state"], len(episodes), flush=True)
    (cache/"fire-results.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache",type=Path,required=True)
    cache = parser.parse_args().cache
    cache.mkdir(parents=True,exist_ok=True)
    run(cache)
