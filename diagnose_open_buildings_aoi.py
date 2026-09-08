"""
AOI-parameterized version of `diagnose_open_buildings_extraction.py`.

Same staged breakdown of Decision 13's `built` endmember pixel pool, but the
AOI is supplied at runtime instead of being the hardcoded Dharavi rectangle:

  1.  Raw count (all Open Buildings v3 footprints in the AOI)
  2.  After confidence filter (>= 0.7)
  3a. After -2m inward buffer, permissive (shrunk area > 0, slivers included)
  3b. After -2m inward buffer AND >= 100 m^2 usable-area threshold

Why a second file rather than an import: `diagnose_open_buildings_extraction.py`
is flat top-level script code -- importing it would re-run the whole Dharavi
diagnostic as a side effect. The staged logic below is a straight copy of that
script's, deliberately unchanged, so the two are comparable line-for-line.

AOI sources:
  --city <name>   resolve the AOI from an existing pipeline run's raw.tif
                  (real-world bbox in WGS84, same rasterio/transform_bounds
                  pattern as generate_osm_road_masks.py)
  --dharavi       the original hardcoded Dharavi rectangle, so the baseline
                  can be re-derived through this exact code path
  --bbox          an explicit WGS84 rectangle, for probing an AOI that has no
                  pipeline run yet (e.g. a formal-fabric control area)

Usage:
    python diagnose_open_buildings_aoi.py --city capetown
    python diagnose_open_buildings_aoi.py --dharavi
    python diagnose_open_buildings_aoi.py --bbox 18.46 -33.98 18.49 -33.95 --label "Cape Town formal suburbs"
"""

import argparse
import glob
import os
import sys

import rasterio
from rasterio.warp import transform_bounds

from ingestion.gee_client import initialize_gee

initialize_gee()

import ee

PIPELINE_RUNS_DIR = "data/pipeline_runs"
BUILDINGS_ASSET = "GOOGLE/Research/open-buildings/v3/polygons"

CONFIDENCE_THRESHOLD = 0.7
INWARD_BUFFER_M = -2  # negative = shrink inward
MIN_USABLE_AREA_M2 = 100  # one 10m x 10m pixel-equivalent

# The original hardcoded Dharavi AOI, kept verbatim for baseline comparison.
DHARAVI_BOUNDS = [72.85, 19.03, 72.87, 19.05]


def find_run_dir(city):
    """Latest pipeline run directory for a city (same rule as
    generate_osm_road_masks.py: lexically last match wins)."""
    matches = sorted(glob.glob(os.path.join(PIPELINE_RUNS_DIR, f"{city}_*")))
    return matches[-1] if matches else None


def aoi_bounds_from_run(city):
    """Return (min_lon, min_lat, max_lon, max_lat) for a city's existing
    pipeline run, read from that run's raw.tif and reprojected to WGS84.

    This is the AOI the pipeline actually processed for that city -- not a
    hand-drawn rectangle -- so the diagnostic runs over exactly the footprint
    the rest of the pipeline's Cape Town artifacts were built from.
    """
    run_dir = find_run_dir(city)
    if run_dir is None:
        sys.exit(f"No pipeline run directory found for '{city}' under {PIPELINE_RUNS_DIR}/")

    raw_tif_path = os.path.join(run_dir, "raw.tif")
    if not os.path.exists(raw_tif_path):
        sys.exit(f"raw.tif not found at {raw_tif_path}")

    with rasterio.open(raw_tif_path) as src:
        print(f"AOI source: {raw_tif_path}")
        print(f"  raw.tif: {src.height}x{src.width}, {src.count} bands, CRS={src.crs}")
        bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds)

    return bounds, run_dir


def run_diagnostic(aoi, label, aoi_area_km2=None):
    """The staged breakdown, copied unchanged from
    diagnose_open_buildings_extraction.py, run against an arbitrary AOI."""

    print(f"\n{'=' * 70}")
    print(f"Open Buildings v3 `built` endmember diagnostic -- {label}")
    print(f"{'=' * 70}")
    if aoi_area_km2:
        print(f"AOI area: {aoi_area_km2:.2f} km^2")

    buildings = ee.FeatureCollection(BUILDINGS_ASSET).filterBounds(aoi)
    raw_count = buildings.size().getInfo()
    print(f"Stage 1 -- raw footprint count: {raw_count}")

    if raw_count == 0:
        print("  No footprints in this AOI at all -- nothing further to measure.")
        return None

    # Stage 2: confidence filter
    confident = buildings.filter(ee.Filter.gte("confidence", CONFIDENCE_THRESHOLD))
    confident_count = confident.size().getInfo()
    print(f"Stage 2 -- after confidence >= {CONFIDENCE_THRESHOLD}: {confident_count} "
          f"({100*confident_count/raw_count:.1f}% of raw)")

    if confident_count == 0:
        print("  Nothing clears the confidence bar -- no usable endmember pool.")
        return None

    # Area stats BEFORE shrinking, so we know what we're working with
    area_stats = confident.aggregate_stats("area_in_meters").getInfo()
    print(f"  area_in_meters stats (pre-shrink): {area_stats}")

    # How many are already sub-pixel (< 100 m^2, i.e. smaller than one
    # 10m Sentinel-2 pixel) BEFORE any shrinking is applied
    subpixel_count = confident.filter(
        ee.Filter.lt("area_in_meters", 100)
    ).size().getInfo()
    print(f"  already sub-pixel (<100 m^2) before shrinking: {subpixel_count} "
          f"({100*subpixel_count/confident_count:.1f}% of confident set)")

    # Stage 3: inward buffer, then filter out anything that became empty
    # (a polygon with a large negative buffer can collapse entirely)
    def shrink_and_flag(feature):
        shrunk = feature.geometry().buffer(INWARD_BUFFER_M)
        return feature.set({
            "shrunk_area_m2": shrunk.area(1),  # 1m error margin, plenty for this
        })

    print(f"\nShrinking {confident_count} footprints by {INWARD_BUFFER_M}m inward "
          f"(this may take a moment)...")

    shrunk_fc = confident.map(shrink_and_flag)

    # "area > 0" was too permissive -- a sliver of 0.0001 m^2 technically
    # survives but is not a usable endmember training pixel. Use a real
    # minimum: MIN_USABLE_AREA_M2 is meant to represent "at least
    # approximately one clean pixel's worth of interior," not "not
    # literally zero."
    survived_any = shrunk_fc.filter(ee.Filter.gt("shrunk_area_m2", 0))
    survived_any_count = survived_any.size().getInfo()
    print(f"Stage 3a -- survived inward shrink (area > 0, PERMISSIVE, "
          f"includes slivers): {survived_any_count} "
          f"({100*survived_any_count/confident_count:.1f}% of confident set)")

    survived_usable = shrunk_fc.filter(
        ee.Filter.gte("shrunk_area_m2", MIN_USABLE_AREA_M2)
    )
    survived_usable_count = survived_usable.size().getInfo()
    print(f"\nStage 3b -- survived inward shrink AND usable "
          f"(area >= {MIN_USABLE_AREA_M2} m^2, one clean pixel-equivalent): "
          f"{survived_usable_count} "
          f"({100*survived_usable_count/confident_count:.1f}% of confident set, "
          f"{100*survived_usable_count/raw_count:.1f}% of raw)")

    total_usable_area = None
    if survived_usable_count > 0:
        usable_area_stats = survived_usable.aggregate_stats("shrunk_area_m2").getInfo()
        print(f"  shrunk area stats (usable survivors only): {usable_area_stats}")

        total_usable_area = survived_usable.aggregate_sum("shrunk_area_m2").getInfo()
        approx_pixel_equiv = total_usable_area / 100
        print(f"  total usable area: {total_usable_area:.0f} m^2 "
              f"(~{approx_pixel_equiv:.0f} genuine pixel-equivalents at 10m)")
    else:
        print(f"  ZERO buildings clear the usable-area bar. {label}'s building "
              "stock, after confidence filtering and edge-margin shrinking, "
              "supplies NO usable `built` endmember pixels on its own.")

    return {
        "label": label,
        "raw": raw_count,
        "confident": confident_count,
        "subpixel_pre_shrink": subpixel_count,
        "survived_any": survived_any_count,
        "survived_usable": survived_usable_count,
        "total_usable_area_m2": total_usable_area,
        "aoi_area_km2": aoi_area_km2,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--city", help="resolve AOI from data/pipeline_runs/<city>_*/raw.tif")
    group.add_argument("--dharavi", action="store_true",
                       help="use the original hardcoded Dharavi rectangle")
    group.add_argument("--bbox", nargs=4, type=float,
                       metavar=("MIN_LON", "MIN_LAT", "MAX_LON", "MAX_LAT"),
                       help="explicit WGS84 rectangle")
    parser.add_argument("--label", help="display label for --bbox runs")
    args = parser.parse_args()

    if args.dharavi:
        bounds = DHARAVI_BOUNDS
        label = "Dharavi (hardcoded baseline rectangle)"
    elif args.bbox:
        bounds = args.bbox
        label = args.label or "ad-hoc bbox"
    else:
        bounds, run_dir = aoi_bounds_from_run(args.city)
        label = f"{args.city} ({os.path.basename(run_dir)})"

    min_lon, min_lat, max_lon, max_lat = bounds
    print(f"AOI bbox (WGS84): lon=[{min_lon:.5f},{max_lon:.5f}] "
          f"lat=[{min_lat:.5f},{max_lat:.5f}]")

    aoi = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])
    aoi_area_km2 = aoi.area(1).getInfo() / 1e6

    result = run_diagnostic(aoi, label, aoi_area_km2)

    if result and result["raw"] > 0:
        print(f"\n{'-' * 70}")
        print("Headline (Stage 3b as % of raw -- the directly comparable number):")
        print(f"  {label}: {result['survived_usable']}/{result['raw']} = "
              f"{100*result['survived_usable']/result['raw']:.1f}%")
        if result["aoi_area_km2"]:
            per_km2 = result["survived_usable"] / result["aoi_area_km2"]
            print(f"  usable footprints per km^2: {per_km2:.1f}")
        print(f"{'-' * 70}")


if __name__ == "__main__":
    main()
