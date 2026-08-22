"""
Phase 8: observed inundation -- REAL satellite EVIDENCE of standing/new
water, as distinct from every prior phase's SUSCEPTIBILITY/screening
baselines (Phases 4-7 answer "is this place prone to flooding"; this
answers "does the imagery show water here, and does it look new").

Two independent data sources, kept separate and never conflated:

    1. get_permanent_water_context() -- JRC Global Surface Water's
       historical occurrence record (1984-2021). Answers "how often has
       this pixel historically been water" -- a BASELINE, not a
       detection of any specific event.

    2. get_sentinel1_change_context() -- Sentinel-1 SAR backscatter
       comparison between a pre-event and an event date window. Answers
       "did this pixel's radar signature change in a way consistent with
       new standing water between these two windows" -- an EVENT-
       SPECIFIC signal, cloud-independent (SAR penetrates cloud cover,
       unlike the existing Sentinel-2 optical pipeline).

    perception/observed_inundation.py fuses these two (plus, optionally,
    the existing optical standing_water classification) into a single
    result. This module only fetches raw evidence -- it does not
    classify or fuse.

IMPORTANT LIMITATIONS, stated up front rather than discovered later:
    - Sentinel-1 SAR interpretation in dense urban areas is genuinely
      hard: building double-bounce effects can INCREASE backscatter
      (opposite of open water's decrease), and radar shadow/layover in
      areas with tall structures or steep terrain can produce false or
      missing signal. This module does NOT attempt building-geometry-
      aware correction -- it applies one fixed VV-drop threshold
      uniformly. Treat results in dense urban AOIs (this project's core
      use case) with real caution.
    - No per-pixel slope-based masking is applied to exclude radar-
      shadow-prone terrain -- only the AOI-wide slope_context from
      Phase 7 exists, not a per-pixel raster.
    - This is single-fixed-threshold change detection, not a validated
      flood-mapping algorithm. It has NOT been checked against any real
      historical flood event in this project. Treat all outputs as
      experimental screening evidence only.
"""

import ee
from ingestion.gee_client import initialize_gee
from configs.inundation_constants import (
    JRC_ASSET, JRC_PERMANENT_WATER_OCCURRENCE_PCT, JRC_SEASONAL_WATER_OCCURRENCE_PCT,
    S1_COLLECTION, S1_INSTRUMENT_MODE, S1_POLARIZATION,
    S1_VV_DROP_THRESHOLD_DB, S1_MIN_IMAGES_PER_WINDOW,
)


def get_permanent_water_context(west: float, south: float, east: float, north: float) -> dict:
    """
    Query JRC Global Surface Water's historical occurrence band over the
    AOI. Returns AOI-WIDE fractions of pixels classified as permanent
    water and seasonal water, based on how often each pixel was observed
    as water across the 1984-2021 record.

    THIS IS A HISTORICAL BASELINE, NOT AN EVENT DETECTION. A high
    permanent-water fraction means this AOI has historically, reliably
    contained water (e.g. a river, lake, reservoir) -- not that water is
    present right now.

    Returns:
        dict with status, permanent_water_pct, seasonal_water_pct,
        source, error.
    """
    try:
        initialize_gee()
        aoi = ee.Geometry.Rectangle([west, south, east, north])

        # BUG FIX: JRC's 'occurrence' band is MASKED (not 0) for pixels
        # that were never observed as water at all -- reduceRegion's
        # mean() reducer excludes masked pixels from the denominator by
        # default, so without .unmask(0) here, permanent/seasonal
        # fractions are computed relative to "pixels ever wet at all",
        # not the whole AOI. Confirmed live: Delhi returned
        # seasonal_water_pct=99.59%, which is only possible if the
        # denominator had shrunk to a tiny ever-wet sliver of the AOI,
        # not the full rectangle. Same bug shape as the Phase 0
        # category_area_pct/unknown_pct denominator mismatch and the
        # Phase 5 upa/upa_max key bug -- a silently wrong percentage,
        # not a crash.
        gsw = ee.Image(JRC_ASSET).select("occurrence").unmask(0).clip(aoi)

        permanent_mask = gsw.gte(JRC_PERMANENT_WATER_OCCURRENCE_PCT)
        seasonal_mask = gsw.gte(JRC_SEASONAL_WATER_OCCURRENCE_PCT).And(
            gsw.lt(JRC_PERMANENT_WATER_OCCURRENCE_PCT)
        )

        combined = permanent_mask.rename("permanent").addBands(seasonal_mask.rename("seasonal"))
        stats = combined.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=aoi, scale=30, maxPixels=1e9,
        ).getInfo()

        permanent_frac = stats.get("permanent")
        seasonal_frac = stats.get("seasonal")

        if permanent_frac is None:
            raise ValueError("JRC occurrence reduction returned no value for this AOI "
                              "(possibly outside JRC's coverage extent).")

        print(f"JRC Global Surface Water: permanent={permanent_frac*100:.2f}%, "
              f"seasonal={(seasonal_frac or 0)*100:.2f}% of AOI")

        return {
            "status": "available",
            "permanent_water_pct": round(float(permanent_frac) * 100, 2),
            "seasonal_water_pct": round(float(seasonal_frac or 0) * 100, 2),
            "source": JRC_ASSET,
            "occurrence_period": "1984-2021",
            "permanent_threshold_pct": JRC_PERMANENT_WATER_OCCURRENCE_PCT,
            "seasonal_threshold_pct": JRC_SEASONAL_WATER_OCCURRENCE_PCT,
            "spatial": False,
            "error": None,
        }

    except Exception as e:
        print(f"JRC Global Surface Water context computation failed: {e}")
        return {
            "status": "unavailable",
            "permanent_water_pct": None,
            "seasonal_water_pct": None,
            "source": JRC_ASSET,
            "occurrence_period": "1984-2021",
            "permanent_threshold_pct": JRC_PERMANENT_WATER_OCCURRENCE_PCT,
            "seasonal_threshold_pct": JRC_SEASONAL_WATER_OCCURRENCE_PCT,
            "spatial": False,
            "error": str(e),
        }


def _s1_collection(aoi, start, end):
    return (
        ee.ImageCollection(S1_COLLECTION)
        .filterBounds(aoi)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", S1_INSTRUMENT_MODE))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", S1_POLARIZATION))
        .select(S1_POLARIZATION)
    )


def get_sentinel1_change_context(west: float, south: float, east: float, north: float,
                                  pre_event_start: str, pre_event_end: str,
                                  event_start: str, event_end: str,
                                  jrc_permanent_water_pct: float = None) -> dict:
    """
    Compare Sentinel-1 VV backscatter between a pre-event window and an
    event window to flag pixels showing a backscatter DROP consistent
    with new standing water. SAR penetrates cloud cover, so this can
    work when the optical pipeline can't.

    Returns:
        dict with status, pre/event image counts, mean VV backscatter
        change (dB), probable_new_inundation_pct (AOI-wide fraction of
        pixels below the drop threshold), source, thresholds used,
        limitations, error.
    """
    try:
        initialize_gee()
        aoi = ee.Geometry.Rectangle([west, south, east, north])

        pre_collection = _s1_collection(aoi, pre_event_start, pre_event_end)
        event_collection = _s1_collection(aoi, event_start, event_end)

        pre_count = pre_collection.size().getInfo()
        event_count = event_collection.size().getInfo()

        if pre_count < S1_MIN_IMAGES_PER_WINDOW or event_count < S1_MIN_IMAGES_PER_WINDOW:
            print(f"Sentinel-1 image count too low: pre={pre_count}, event={event_count}")
            return {
                "status": "insufficient_evidence",
                "reason": (
                    f"Sentinel-1 image count too low: pre-event={pre_count}, "
                    f"event={event_count} (minimum {S1_MIN_IMAGES_PER_WINDOW} each)."
                ),
                "pre_event_image_count": pre_count,
                "event_image_count": event_count,
                "source": S1_COLLECTION,
                "error": None,
            }

        pre_composite = pre_collection.median()
        event_composite = event_collection.median()

        # VV backscatter is already in dB (log scale) for GRD products,
        # so this is a direct dB difference, not a ratio.
        diff = event_composite.subtract(pre_composite).rename("vv_diff_db")

        mean_diff_stats = diff.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=aoi, scale=10, maxPixels=1e9,
        ).getInfo()
        mean_diff_db = mean_diff_stats.get("vv_diff_db")

        drop_mask = diff.lte(S1_VV_DROP_THRESHOLD_DB)
        drop_stats = drop_mask.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=aoi, scale=10, maxPixels=1e9,
        ).getInfo()
        drop_frac = drop_stats.get("vv_diff_db")

        if mean_diff_db is None or drop_frac is None:
            raise ValueError("Sentinel-1 change reduction returned no value for this AOI.")

        print(f"Sentinel-1 VV change: mean={mean_diff_db:.2f}dB, "
              f"probable_new_inundation={drop_frac*100:.2f}% of AOI "
              f"(pre={pre_count} imgs, event={event_count} imgs)")

        return {
            "status": "experimental",
            "pre_event_image_count": pre_count,
            "event_image_count": event_count,
            "mean_vv_change_db": round(float(mean_diff_db), 3),
            "probable_new_inundation_pct": round(float(drop_frac) * 100, 2),
            "jrc_permanent_water_pct_context": jrc_permanent_water_pct,
            "source": S1_COLLECTION,
            "polarization": S1_POLARIZATION,
            "drop_threshold_db": S1_VV_DROP_THRESHOLD_DB,
            "resolution_m": 10,
            "spatial": False,
            "validated": False,
            "limitations": [
                "AOI-WIDE SCALAR fraction only -- not a per-pixel spatial raster "
                "in this result (a per-pixel mask IS computed internally for the "
                "reduction, but not exported/saved here).",
                "Single fixed VV-drop threshold, not locally calibrated or "
                "validated against any real flood event.",
                "Does NOT exclude existing permanent-water pixels (a lake that "
                "happened to change appearance between the two windows would "
                "also count toward probable_new_inundation_pct) -- cross-check "
                "against jrc_permanent_water_pct_context before interpreting.",
                "Dense urban double-bounce effects can INCREASE backscatter "
                "(opposite of open water) and are not modeled -- this can cause "
                "missed detections in exactly this project's core informal-"
                "settlement use case.",
                "No per-pixel radar-shadow/layover masking applied -- only "
                "AOI-wide slope context exists in this pipeline, not a "
                "per-pixel raster.",
                "Median composites within each window can still smooth out "
                "very short-lived inundation if image count is low.",
            ],
            "error": None,
        }

    except Exception as e:
        print(f"Sentinel-1 change context computation failed: {e}")
        return {
            "status": "unavailable",
            "pre_event_image_count": None,
            "event_image_count": None,
            "mean_vv_change_db": None,
            "probable_new_inundation_pct": None,
            "jrc_permanent_water_pct_context": jrc_permanent_water_pct,
            "source": S1_COLLECTION,
            "polarization": S1_POLARIZATION,
            "drop_threshold_db": S1_VV_DROP_THRESHOLD_DB,
            "resolution_m": 10,
            "spatial": False,
            "validated": False,
            "limitations": [],
            "error": str(e),
        }