import ee
from datetime import datetime
from ingestion.sentinel2 import (
    S2_BANDS,
    S2_BAND_NAMES,
    mask_s2_clouds,
)

# Scale for temporal variance computation. Unlike
# compute_observation_quality()'s deliberate 60m aggregate scale (see
# sentinel2.py's OBSERVATION_QUALITY_SCALE_M comment for why that one is
# coarse), THIS is a per-pixel product -- every downstream consumer
# (Decision 13's built/paved disambiguation, item 25's change detection)
# needs a value at every 10m cell, not an AOI-wide scalar. Do not confuse
# the two scale decisions; they answer different questions.
TEMPORAL_VARIANCE_SCALE_M = 10

# Indices computed per monthly composite, before variance is taken across
# months. NDVI and NDBI per Decision 13/item 18; raw SWIR1 and SWIR2
# variance added explicitly per project decision, since built/paved
# separation reads most directly off these two bands rather than the
# derived indices alone.
def add_indices(image: ee.Image) -> ee.Image:
    """
    Add NDVI and NDBI bands to a masked, band-renamed Sentinel-2 image
    (i.e. the output of mask_s2_clouds). Uses the renamed band names
    (Red, NIR, SWIR1) rather than raw B4/B8/B11, since this always runs
    after mask_s2_clouds's .select(S2_BANDS, S2_BAND_NAMES) step.
    """
    ndvi = image.normalizedDifference(["NIR", "Red"]).rename("NDVI")
    ndbi = image.normalizedDifference(["SWIR1", "NIR"]).rename("NDBI")
    return image.addBands([ndvi, ndbi])


def compute_temporal_variance(
    aoi: ee.Geometry,
    year: int,
    cloud_cover_threshold: int = 20,
) -> dict:
    """
    Item 18 -- temporal variance layer.

    Builds 12 monthly median composites across the given calendar year,
    each built from the SCL-based mask_s2_clouds (item 51) -- so
    cloud/no-data pixels are excluded from each month's composite, and
    cloud-shadow pixels are preserved, consistent with Decision 13's
    shadow-as-sixth-endmember treatment. Then computes the standard
    deviation across those 12 monthly values, per pixel, for:
        NDVI, NDBI, and all six raw Sentinel-2 bands (Blue, Green, Red,
        NIR, SWIR1, SWIR2) -- eight variance bands total.

    A permanent, stable surface (a paved road, a rooftop) should show low
    variance across the year. A seasonal surface (bare soil that greens
    up and dries out, a vegetated lot) should show high variance. This is
    the core signal used to help separate `built` from `paved` in
    Decision 13's unmixing step, since the two are near-identical
    spectrally but differ in temporal stability.

    Returns a dict with:
        status: "available" | "unavailable"
        variance_image: ee.Image with bands
            {NDVI,NDBI,Blue,Green,Red,NIR,SWIR1,SWIR2}_stddev
        composite_count: list of 12 ints, number of source images
            contributing to each month's composite (0 = month had no
            usable imagery, that month is fully masked and excluded from
            the stddev at every pixel it would have touched)
        date_range: [start, end] ISO strings for the year covered
        reduction_scale_m: TEMPORAL_VARIANCE_SCALE_M, surfaced for the
            same reason compute_observation_quality() surfaces its scale
            -- so the basis of a downstream number is visible, not implicit
        error: None, or the exception string on failure
    """
    start = f"{year}-01-01"
    end = f"{year}-12-31"

    monthly_images = []
    composite_count = []

    try:
        for month in range(1, 13):
            month_start = datetime(year, month, 1).strftime("%Y-%m-%d")
            if month == 12:
                month_end = f"{year}-12-31"
            else:
                next_month = datetime(year, month + 1, 1)
                month_end = next_month.strftime("%Y-%m-%d")

            month_collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(aoi)
                .filterDate(month_start, month_end)
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_cover_threshold))
            )

            count = month_collection.size().getInfo()
            composite_count.append(count)

            if count == 0:
                # No usable imagery this month. Do not add a phantom
                # composite -- an empty/fully-masked image would
                # silently contribute nothing to stdDev anyway, but
                # skipping it here keeps monthly_images honest about
                # what was actually used, matching composite_count.
                continue

            masked_collection = month_collection.map(mask_s2_clouds)
            month_composite = masked_collection.median()
            month_with_indices = add_indices(month_composite)
            monthly_images.append(month_with_indices)

        if len(monthly_images) == 0:
            return {
                "status": "unavailable",
                "variance_image": None,
                "composite_count": composite_count,
                "date_range": [start, end],
                "reduction_scale_m": TEMPORAL_VARIANCE_SCALE_M,
                "error": "No months in the given year had usable imagery under the cloud threshold.",
            }

        monthly_collection = ee.ImageCollection.fromImages(monthly_images)

        variance_bands = S2_BAND_NAMES + ["NDVI", "NDBI"]
        stddev_image = (
            monthly_collection
            .select(variance_bands)
            .reduce(ee.Reducer.stdDev())
        )
        # ee.Reducer.stdDev() appends "_stdDev" to each band name.
        # Rename to the documented {name}_stddev convention (lowercase,
        # matching the rest of this project's field naming) for
        # consistency with observation_quality's snake_case fields.
        old_names = [f"{b}_stdDev" for b in variance_bands]
        new_names = [f"{b}_stddev" for b in variance_bands]
        stddev_image = stddev_image.select(old_names, new_names)

        # COEFFICIENT OF VARIATION (CV = stddev / mean), for the six raw
        # bands only.
        #
        # WHY: raw stddev is not a fair cross-surface stability
        # comparison when baseline brightness differs. Confirmed
        # empirically on Dharavi/2025 -- a well-isolated stretch of NH48
        # (stable pavement) showed HIGHER raw Blue/Green/SWIR2 stddev
        # than a mangrove/mudflat patch (genuinely seasonal), even though
        # per-month inspection showed the road's relative swing (~36% of
        # its own mean) was essentially identical to the mangrove's
        # (~35% of its own mean) -- pavement is simply brighter in
        # visible light than dense canopy, so the same proportional
        # seasonal/atmospheric effect produces a larger absolute stddev
        # on the brighter surface. This is a units problem, not a signal
        # problem.
        #
        # NDVI and NDBI are excluded here because they are already
        # ratio-based (self-normalizing by construction) -- CV of an
        # index that can be zero or negative is not a meaningful
        # quantity, and per-month inspection showed NDVI already gives
        # a clean, correctly-directioned signal without this correction.
        #
        # VALIDATION (Dharavi, 2025, monthly composites, 9/12 months had
        # usable imagery -- Jun/Jul/Aug had 0 images, Sep had 1):
        #
        #   Point A -- clean NH48 highway stretch, 19.050611, 72.849049
        #   Point B -- NH48 near a bridge/water crossing, 19.051732,
        #              72.848193 -- included deliberately as a probable
        #              BAD sample to test whether the method could
        #              detect contamination
        #   Mangrove -- Dharavi Mangrove Region interior patch,
        #               19.049166, 72.846579
        #
        #   Raw NDVI (unaffected by the brightness issue, no fix needed):
        #     Point A road:  0.033   Mangrove: 0.136   (~4x, correct
        #     direction -- mangrove is the seasonal surface)
        #
        #   Raw stddev, before this fix (misleading):
        #     Blue    -- Point A 0.0105 vs Mangrove 0.0051 (implies road
        #                LESS stable -- wrong, contradicts NDVI)
        #     SWIR2   -- Point A 0.0180 vs Mangrove 0.0136 (same problem)
        #
        #   CV, after this fix (consistent with NDVI):
        #     Blue    -- Point A 0.130 vs Mangrove 0.133 (now ~tied,
        #                not inverted)
        #     NIR     -- Point A 0.107 vs Mangrove 0.235 (road correctly
        #                more stable -- NIR dominates the NDVI formula,
        #                so this now agrees with the NDVI result)
        #     Green, SWIR2 remain mildly counter-intuitive (road reads
        #     slightly less stable) even after the CV correction --
        #     small residual, plausibly the 3 zero-image months, not
        #     investigated further. Documented as an open, named
        #     caveat rather than resolved.
        #
        #   Point B cross-check: CV came back ~2x Point A's, uniformly
        #   across all six bands (e.g. Blue_cv 0.284 vs 0.130). A
        #   genuinely different clean road surface should NOT show a
        #   uniform 2x scaling across every unrelated band -- this
        #   confirms Point B was contaminated by the nearby bridge/
        #   water crossing, not that highways are simply noisier than
        #   Point A suggested. Independent confirmation that the method
        #   can detect a bad sample, not just produce plausible-looking
        #   numbers regardless of input.
        #
        # CONCLUSION: core mechanism (NDVI) was correct from the start.
        # Raw stddev on the 6 base bands was a units artifact, fixed by
        # CV. Small residual disagreement in Green/SWIR2 is named, not
        # hidden, and not currently blocking -- Decision 13's 2-3 city
        # pilot (item 21) will re-test this mechanism on different
        # cities/years, which is the right place to see if this residual
        # persists or was specific to this single AOI/year (see
        # 03_EVIDENCE.md A.13 -- conclusions from one small AOI do not
        # transfer cleanly).
        raw_bands = S2_BAND_NAMES
        mean_image = monthly_collection.select(raw_bands).mean()
        raw_stddev_image = stddev_image.select([f"{b}_stddev" for b in raw_bands])

        # Guard against division by zero / near-zero mean reflectance
        # (e.g. deep shadow, water absorption bands) producing an
        # exploding or undefined CV.
        cv_image = raw_stddev_image.divide(mean_image.max(1e-6))
        cv_old_names = [f"{b}_stddev" for b in raw_bands]
        cv_new_names = [f"{b}_cv" for b in raw_bands]
        cv_image = cv_image.select(cv_old_names, cv_new_names)

        variance_image = stddev_image.addBands(cv_image)

        return {
            "status": "available",
            "variance_image": variance_image,  # now carries both
                                                 # {band}_stddev (raw,
                                                 # all 8 bands+indices)
                                                 # and {band}_cv
                                                 # (normalized, 6 raw
                                                 # bands only)
            "monthly_collection": monthly_collection,
            "composite_count": composite_count,
            "date_range": [start, end],
            "reduction_scale_m": TEMPORAL_VARIANCE_SCALE_M,
            "error": None,
        }
    except Exception as e:
        print(f"Temporal variance computation failed: {e}")
        return {
            "status": "unavailable",
            "variance_image": None,
            "composite_count": composite_count,
            "date_range": [start, end],
            "reduction_scale_m": TEMPORAL_VARIANCE_SCALE_M,
            "error": str(e),
        }
