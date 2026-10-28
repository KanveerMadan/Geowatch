"""
Ward-ranking test (item 26, task 5). Pre-registered in PREREGISTRATION.md
before any (b)/(c) value existed; the constants below match it.

Ranks Mumbai's 24 BMC wards by three impervious estimates and compares the
orders by Spearman rho against a fixed bar. Evidence only.

    python -m experiments.ward_ranking.c3_ward_ranking \
        --wards data/pipeline_runs/phase12b_ward_landcover_v2.json \
        --boundary data/boundaries/datameet_mumbai_bmc_wards/boundary.geojson
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os

STABILITY_RHO_MIN = 0.80
MIN_WARDS = 20
PAIRS = (("a", "b"), ("a", "c"), ("b", "c"))
WINDOW = ("2025-11-01", "2026-08-22")      # the stored run's composite window
CLOUD_COVER_THRESHOLD = 60                  # Lane B's default
BUILT_SCALE_M = 2
PIXEL_M = 10
UTM = "EPSG:32643"
EE_DEADLINE_MS = 600_000   # a reduceRegion stalled silently for 2 h 40 min on ward 20 (2026-10-28)
HERE = os.path.dirname(os.path.abspath(__file__))


def evaluate(values: dict) -> dict:
    """values: {"a"|"b"|"c": {ward_id: float | None}} -> per-pair verdicts."""
    from scipy.stats import spearmanr
    out = {}
    for x, y in PAIRS:
        wards = sorted(w for w in values[x]
                       if values[x][w] is not None and values[y].get(w) is not None)
        key = f"{x}_vs_{y}"
        if len(wards) < MIN_WARDS:
            out[key] = {"n_wards": len(wards), "rho": None, "verdict": "not_evaluated"}
            continue
        rho = float(spearmanr([values[x][w] for w in wards], [values[y][w] for w in wards])[0])
        out[key] = {"n_wards": len(wards), "rho": round(rho, 4),
                    "verdict": "stable" if rho >= STABILITY_RHO_MIN else "unstable"}
    return out


def ee_estimates(features: list) -> tuple:
    """(b) and (c) per ward, computed server-side in Earth Engine."""
    import ee
    from ingestion.gee_client import initialize_gee
    from ingestion.sentinel2 import get_sentinel2_collection, mask_s2_clouds
    from vector.fractions import MIN_VALID_OBS, VEGETATION_NDVI_MIN, WATER_MNDWI_MIN
    from vector.sources import OPEN_BUILDINGS_ASSET
    initialize_gee()

    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]), {"gid": f["properties"]["gid"]})
                               for f in features])
    region = fc.geometry().bounds()
    ob = ee.FeatureCollection(OPEN_BUILDINGS_ASSET).filterBounds(region)
    built2 = ee.Image(0).byte().paint(ob, 1).rename("built")      # union, by area
    built10 = (built2.reproject(crs=UTM, scale=BUILT_SCALE_M)
               .reduceResolution(ee.Reducer.mean(), maxPixels=1024)
               .reproject(crs=UTM, scale=PIXEL_M))

    col = get_sentinel2_collection(region, WINDOW[0], WINDOW[1], CLOUD_COVER_THRESHOLD).map(mask_s2_clouds)
    ndvi = col.map(lambda i: i.normalizedDifference(["NIR", "Red"])).median()
    mndwi = col.map(lambda i: i.normalizedDifference(["Green", "SWIR1"])).median()
    nobs = col.select("Red").count()
    water = mndwi.gt(WATER_MNDWI_MIN)
    veg = ndvi.gt(VEGETATION_NDVI_MIN).And(water.Not())
    remainder = ee.Image(1).subtract(built10).subtract(veg).subtract(water).max(0)
    c_img = built10.add(remainder).updateMask(nobs.gte(MIN_VALID_OBS)).rename("c")

    def get(value):
        for attempt in (1, 2):
            try:
                return value.getInfo()
            except ee.EEException as e:
                if attempt == 2:
                    raise
                print(f"    retrying after {e}", flush=True)

    ee.data.setDeadline(EE_DEADLINE_MS)
    b, c = {}, {}
    for f in features:
        gid = f["properties"]["gid"]
        geom = ee.Geometry(f["geometry"])
        b[gid] = get(built2.reduceRegion(ee.Reducer.mean(), geom, BUILT_SCALE_M, crs=UTM,
                                     maxPixels=1e10, tileScale=8).get("built"))
        c[gid] = get(c_img.reduceRegion(ee.Reducer.mean(), geom, PIXEL_M, crs=UTM,
                                    maxPixels=1e10, tileScale=8).get("c"))
        print(f"  ward {gid} {f['properties']['name']}: b={b[gid]} c={c[gid]}", flush=True)
    return b, c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wards", required=True)
    ap.add_argument("--boundary", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "result_2026-10-28.json"))
    args = ap.parse_args()

    stored = json.load(open(args.wards))
    a = {w["ward_id"]: w.get("hydrological_surfaces", {}).get("impervious_fraction_pct")
         for w in stored["wards"]}
    a = {k: (v / 100.0 if v is not None else None) for k, v in a.items()}
    features = json.load(open(args.boundary))["features"]
    names = {f["properties"]["gid"]: f["properties"]["name"] for f in features}
    b, c = ee_estimates(features)

    values = {"a": a, "b": b, "c": c}
    result = {
        "test": "item 26 task 5 -- ward-ranking test",
        "validation_status": "experimental",
        "preregistration_sha256": hashlib.sha256(
            open(os.path.join(HERE, "PREREGISTRATION.md"), "rb").read()).hexdigest(),
        "run_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "bar": {"metric": "spearman_rho_over_wards", "stable_if_rho_at_least": STABILITY_RHO_MIN,
                "min_wards": MIN_WARDS},
        "sources": {"a": f"{args.wards} hydrological_surfaces.impervious_fraction_pct / 100",
                    "b": "Open Buildings v3 footprint union area fraction (2 m paint)",
                    "c": f"built + max(0, 1 - built - veg - water), S2 {WINDOW[0]}..{WINDOW[1]}"},
        "pairs": evaluate(values),
        "wards": [{"ward_id": w, "name": names.get(w), **{k: values[k].get(w) for k in "abc"}}
                  for w in sorted(a)],
    }
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result["pairs"], indent=2))


if __name__ == "__main__":
    main()
