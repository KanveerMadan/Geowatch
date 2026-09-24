"""
Tests 3, 4 (GEE half) and 5 — footprints, morphology descriptors, bare ground.

One AOI loop, because these all come from Earth Engine and the per-site
overhead dominates.

TEST 3 — Open Buildings v3. A hard gate: footprints are the vector half of the
merged `impervious` class, so a candidate with none breaks it. Coverage is
regional, and MENA is the live question.

TEST 4 — descriptors for the distance matrix. Built-up density, footprint size
distribution (median and IQR, not mean: footprint areas are heavily
right-skewed and a mean tracks the few warehouses), terrain from SRTM, and
GHSL built-up / population. Road and intersection density come from test 2 and
are joined later.

  Terrain is the one worth being careful about. None of the existing 11 is a
  hillside settlement, and hillside informal fabric is both morphologically
  distinct and hydrologically different -- which is the flood model's actual
  subject. Slope is reported as mean AND standard deviation over the AOI,
  because a uniformly-tilted plain and a ravine-cut hillside can share a mean.

TEST 5 — bare ground. `bare` is a brand-new class with zero existing
supervision, so a candidate with no bare ground contributes nothing to the
class that most needs examples. Two independent reads:
  * ESA WorldCover v200 class 60 (bare / sparse vegetation) fraction
  * a dry-season BSI/NDVI screen computed from the S2 composite itself,
    because WorldCover's own built-up user's accuracy is 47.1% in Africa
    (03_EVIDENCE.md) and its bare class inherits that neighbourhood of error

SRTM is used for terrain rather than Copernicus GLO30 because every site here
falls inside 60N-56S and SRTM is a single image rather than a collection --
fewer moving parts for a descriptor that only needs to be consistent.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import ee  # noqa: E402

from experiments.city_selection.aois import all_sites  # noqa: E402
from ingestion.gee_client import initialize_gee  # noqa: E402
from ingestion.sentinel2 import SCL_CLOUD_CODES, SCL_NODATA_CODES  # noqa: E402

CACHE = Path(__file__).resolve().parent / "cache" / "test345.json"
OB = "GOOGLE/Research/open-buildings/v3/polygons"
AOI_AREA_KM2 = 25.0


def dry_season_composite(geom, months):
    """Median S2 composite over the site's clearest 3-month window."""
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
           .filterDate("2023-09-01", "2026-09-01").filterBounds(geom)
           .filter(ee.Filter.inList("month", months)
                   if False else ee.Filter.calendarRange(months[0], months[-1], "month")
                   if months[0] <= months[-1] else
                   ee.Filter.Or(ee.Filter.calendarRange(months[0], 12, "month"),
                                ee.Filter.calendarRange(1, months[-1], "month"))))

    def mask(img):
        scl = img.select("SCL")
        bad = (scl.remap(list(SCL_CLOUD_CODES), [1] * len(SCL_CLOUD_CODES), 0)
               .Or(scl.remap(list(SCL_NODATA_CODES), [1] * len(SCL_NODATA_CODES), 0)))
        return img.updateMask(bad.Not())

    return col.map(mask).median()


def measure(name: str, site: dict, best_months) -> dict:
    w, s, e, n = site["bbox"]
    geom = ee.Geometry.Rectangle([w, s, e, n])
    out: dict = {}

    # --- Test 3: Open Buildings ---
    ob = ee.FeatureCollection(OB).filterBounds(geom)
    n_poly = ob.size()
    areas = ob.aggregate_array("area_in_meters")
    stats = ee.Algorithms.If(
        n_poly.gt(0),
        ee.Dictionary({
            "n": n_poly,
            "total_area": ee.Number(ee.List(areas).reduce(ee.Reducer.sum())),
            "p25": ee.Number(ee.List(areas).reduce(ee.Reducer.percentile([25]))),
            "p50": ee.Number(ee.List(areas).reduce(ee.Reducer.percentile([50]))),
            "p75": ee.Number(ee.List(areas).reduce(ee.Reducer.percentile([75]))),
        }),
        ee.Dictionary({"n": 0, "total_area": 0, "p25": 0, "p50": 0, "p75": 0}))

    # --- Test 4: terrain ---
    dem = ee.Image("USGS/SRTMGL1_003")
    slope = ee.Terrain.slope(dem)
    terrain = (ee.Image.cat(slope.rename("slope"), dem.rename("elev"))
               .reduceRegion(ee.Reducer.mean().combine(ee.Reducer.stdDev(), None, True)
                             .combine(ee.Reducer.percentile([90]), None, True),
                             geom, 30, maxPixels=1e9, bestEffort=True))

    # --- Test 4: GHSL ---
    ghs_built = (ee.Image("JRC/GHSL/P2023A/GHS_BUILT_S/2020").select("built_surface")
                 .reduceRegion(ee.Reducer.mean(), geom, 100, maxPixels=1e9,
                               bestEffort=True))
    ghs_pop = (ee.Image("JRC/GHSL/P2023A/GHS_POP/2020").select("population_count")
               .reduceRegion(ee.Reducer.sum(), geom, 100, maxPixels=1e9,
                             bestEffort=True))

    # --- Test 5: WorldCover bare fraction ---
    wc = ee.Image("ESA/WorldCover/v200/2021").select("Map")
    wc_frac = (ee.Image.cat(
        wc.eq(60).rename("bare"), wc.eq(50).rename("builtup"),
        wc.eq(80).rename("water"),
        wc.gte(10).And(wc.lte(30)).rename("veg"))
        .reduceRegion(ee.Reducer.mean(), geom, 10, maxPixels=1e9, bestEffort=True))

    # --- Test 5: BSI / NDVI from the site's own clearest window ---
    comp = dry_season_composite(geom, list(best_months))
    b = comp.select(["B2", "B3", "B4", "B8", "B11"]).divide(10000)
    ndvi = b.normalizedDifference(["B8", "B4"]).rename("ndvi")
    bsi = (b.select("B11").add(b.select("B4"))
           .subtract(b.select("B8").add(b.select("B2")))
           .divide(b.select("B11").add(b.select("B4"))
                   .add(b.select("B8").add(b.select("B2")))).rename("bsi"))
    # Bare-ish: low vegetation AND positive soil index.
    bare_screen = ndvi.lt(0.2).And(bsi.gt(0.0)).rename("bare_screen")
    spectral = (ee.Image.cat(ndvi, bsi, bare_screen)
                .reduceRegion(ee.Reducer.mean(), geom, 20, maxPixels=1e9,
                              bestEffort=True))

    got = ee.Dictionary({
        "ob": stats, "terrain": terrain, "ghs_built": ghs_built,
        "ghs_pop": ghs_pop, "wc": wc_frac, "spectral": spectral,
    }).getInfo()

    o, t, wcv, sp = got["ob"], got["terrain"], got["wc"], got["spectral"]
    n_b = int(o["n"])
    total_m2 = float(o["total_area"] or 0)
    out.update({
        "ob_n_buildings": n_b,
        "ob_per_km2": n_b / AOI_AREA_KM2,
        "ob_footprint_area_m2": total_m2,
        "ob_built_fraction": total_m2 / (AOI_AREA_KM2 * 1e6),
        "ob_median_m2": float(o["p50"] or 0),
        "ob_p25_m2": float(o["p25"] or 0),
        "ob_p75_m2": float(o["p75"] or 0),
        "ob_iqr_m2": float((o["p75"] or 0) - (o["p25"] or 0)),
        "slope_mean_deg": t.get("slope_mean"),
        "slope_std_deg": t.get("slope_stdDev"),
        "slope_p90_deg": t.get("slope_p90"),
        "elev_mean_m": t.get("elev_mean"),
        "elev_std_m": t.get("elev_stdDev"),
        "ghsl_built_frac": (None if got["ghs_built"].get("built_surface") is None
                            else float(got["ghs_built"]["built_surface"]) / 10000.0),
        "ghsl_pop_total": got["ghs_pop"].get("population_count"),
        "ghsl_pop_per_km2": (None if got["ghs_pop"].get("population_count") is None
                             else float(got["ghs_pop"]["population_count"]) / AOI_AREA_KM2),
        "wc_bare_frac": wcv.get("bare"),
        "wc_builtup_frac": wcv.get("builtup"),
        "wc_water_frac": wcv.get("water"),
        "wc_veg_frac": wcv.get("veg"),
        "ndvi_mean": sp.get("ndvi"),
        "bsi_mean": sp.get("bsi"),
        "bare_screen_frac": sp.get("bare_screen"),
        "best_months": list(best_months),
    })
    return out


def main() -> int:
    initialize_gee()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    out = json.loads(CACHE.read_text()) if CACHE.exists() else {}

    cloud = json.loads((Path(__file__).resolve().parent / "cache"
                        / "test1_cloud.json").read_text())
    sites = all_sites()
    only = sys.argv[1:] or list(sites)
    for name in only:
        if name in out:
            print(f"  {name:<16} cached")
            continue
        months = cloud.get(name, {}).get("best_window_months") or [1, 2, 3]
        t0 = time.time()
        try:
            out[name] = measure(name, sites[name], months)
            r = out[name]
            sl = r["slope_mean_deg"]
            print(f"  {name:<16} OB {r['ob_n_buildings']:>7} "
                  f"({r['ob_built_fraction'] * 100:>5.1f}% built, med "
                  f"{r['ob_median_m2']:>6.1f} m2) | slope "
                  f"{'n/a' if sl is None else f'{sl:>5.2f}'} deg | "
                  f"WC bare {(r['wc_bare_frac'] or 0) * 100:>5.2f}% | "
                  f"screen {(r['bare_screen_frac'] or 0) * 100:>5.1f}% | "
                  f"{time.time() - t0:.0f}s", flush=True)
        except Exception as exc:
            print(f"  {name:<16} ERROR {type(exc).__name__}: {str(exc)[:140]}", flush=True)
            continue
        CACHE.write_text(json.dumps(out, indent=2))
    CACHE.write_text(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
