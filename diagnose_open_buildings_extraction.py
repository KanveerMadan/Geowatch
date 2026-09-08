"""
Diagnostic for Decision 13's `built` endmember pixel pool.

Measures, at each filtering stage, how many Open Buildings v3 footprints
survive in the Dharavi pilot AOI:
  1. Raw count (all footprints returned)
  2. After confidence filter
  3. After inward negative buffer (removes edge-mixed pixels)

This is diagnostic, not the final extraction pipeline -- the goal here
is to find out whether Dharavi's known small/sub-pixel footprint problem
(sample building seen earlier: 71.3 m^2, smaller than one 10m pixel)
is a minor footnote or a real blocker for this specific AOI, BEFORE
building the full endmember extraction around untested assumptions.
"""

from ingestion.gee_client import initialize_gee
initialize_gee()

import ee

DHARAVI_AOI = ee.Geometry.Rectangle([72.85, 19.03, 72.87, 19.05])
BUILDINGS_ASSET = "GOOGLE/Research/open-buildings/v3/polygons"

CONFIDENCE_THRESHOLD = 0.7
INWARD_BUFFER_M = -2  # negative = shrink inward

buildings = ee.FeatureCollection(BUILDINGS_ASSET).filterBounds(DHARAVI_AOI)
raw_count = buildings.size().getInfo()
print(f"Stage 1 -- raw footprint count: {raw_count}")

# Stage 2: confidence filter
confident = buildings.filter(ee.Filter.gte("confidence", CONFIDENCE_THRESHOLD))
confident_count = confident.size().getInfo()
print(f"Stage 2 -- after confidence >= {CONFIDENCE_THRESHOLD}: {confident_count} "
      f"({100*confident_count/raw_count:.1f}% of raw)")

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

confident_list = confident.toList(confident.size())
n = confident_list.size().getInfo()

print(f"\nShrinking {n} footprints by {INWARD_BUFFER_M}m inward "
      f"(this may take a moment)...")

shrunk_fc = confident.map(shrink_and_flag)

# "area > 0" was too permissive -- a sliver of 0.0001 m^2 technically
# survives but is not a usable endmember training pixel. Use a real
# minimum: MIN_USABLE_AREA_M2 is meant to represent "at least
# approximately one clean pixel's worth of interior," not "not
# literally zero."
MIN_USABLE_AREA_M2 = 100  # one 10m x 10m pixel-equivalent

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

if survived_usable_count > 0:
    usable_area_stats = survived_usable.aggregate_stats("shrunk_area_m2").getInfo()
    print(f"  shrunk area stats (usable survivors only): {usable_area_stats}")

    total_usable_area = survived_usable.aggregate_sum("shrunk_area_m2").getInfo()
    approx_pixel_equiv = total_usable_area / 100
    print(f"  total usable area: {total_usable_area:.0f} m^2 "
          f"(~{approx_pixel_equiv:.0f} genuine pixel-equivalents at 10m)")
else:
    print("  ZERO buildings clear the usable-area bar. Dharavi's building "
          "stock, after confidence filtering and edge-margin shrinking, "
          "supplies NO usable `built` endmember pixels on its own.")