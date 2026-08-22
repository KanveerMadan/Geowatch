"""
Phase 7: flash-flood susceptibility baseline. STATIC/SCREENING SLICE
ONLY. Combines three AOI-WIDE SCALAR signals: terrain slope (Phase 7,
new), upstream catchment size (Phase 5's hand_context, reused), and
rainfall climatology (Phase 4's rainfall_climatology, reused).

The rainfall component is DELIBERATELY WEAK EVIDENCE, flagged
explicitly: CHIRPS mean_annual_mm is a long-term climatology mean, NOT
an extreme-rainfall-intensity statistic (e.g. no 24hr/1hr percentile).
Flash floods are driven by short-duration intensity, not annual totals
-- a place with high but evenly-distributed annual rainfall is not
necessarily flash-flood-prone, while a place with lower annual totals
but occasional violent bursts could be. This proxy cannot distinguish
those cases. A real fix (rainfall intensity percentiles via GPM IMERG)
is deferred to Phase 9 (event hazard).
"""

from configs.flash_flood_constants import (
    FLASH_FLOOD_SLOPE_NORMALIZATION_MAX_DEG,
    FLASH_FLOOD_SMALL_CATCHMENT_MAX_KM2,
    FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM,
    FLASH_FLOOD_CLASS_BREAKS,
)


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in FLASH_FLOOD_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


def compute_flash_flood_susceptibility(slope_context: dict, hand_context: dict,
                                        rainfall_climatology: dict) -> dict:
    """
    Args:
        slope_context: output of ingestion.hydrology.get_slope_stats()
        hand_context: output of ingestion.hydrology.get_merit_hand_context()
            (Phase 5) -- reused for max_upstream_area_km2, NOT for HAND
            itself (flash-flood doesn't use HAND directly; waterlogging
            does, with a different physical interpretation -- see that
            module).
        rainfall_climatology: output of ingestion.rainfall.get_rainfall_climatology()
            (Phase 4) -- reused, see module docstring for why this is a
            weak proxy here specifically.

    Returns:
        dict matching the master schema's susceptibility.flash_flood shape.
    """
    slope_available = slope_context is not None and slope_context.get("status") == "available"
    catchment_available = (
        hand_context is not None
        and hand_context.get("status") == "available"
        and hand_context.get("max_upstream_area_km2") is not None
    )
    rainfall_available = (
        rainfall_climatology is not None
        and rainfall_climatology.get("status") == "available"
        and rainfall_climatology.get("mean_annual_mm") is not None
    )

    if not slope_available and not catchment_available:
        return {
            "status": "insufficient_evidence",
            "reason": "Neither slope nor upstream-catchment context is available.",
        }

    components_used = []
    components_excluded = []
    scores = []

    if slope_available:
        slope_deg = slope_context["mean_slope_deg"]
        slope_score = max(0.0, min(1.0, slope_deg / FLASH_FLOOD_SLOPE_NORMALIZATION_MAX_DEG))
        scores.append(slope_score)
        components_used.append("terrain_slope")
    else:
        components_excluded.append("terrain_slope (unavailable)")

    if catchment_available:
        upstream_km2 = hand_context["max_upstream_area_km2"]
        # SMALLER catchment -> higher flash-flood score (faster runoff
        # concentration). Inverted relative to fluvial's use of the
        # same upstream-area figure.
        catchment_score = max(0.0, min(1.0, 1.0 - (upstream_km2 / FLASH_FLOOD_SMALL_CATCHMENT_MAX_KM2)))
        scores.append(catchment_score)
        components_used.append("small_catchment_upstream_area")
    else:
        components_excluded.append("upstream_catchment_area (unavailable)")

    if rainfall_available:
        rainfall_mm = rainfall_climatology["mean_annual_mm"]
        rainfall_score = max(0.0, min(1.0, rainfall_mm / FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM))
        scores.append(rainfall_score)
        components_used.append("rainfall_climatology_proxy")
    else:
        components_excluded.append("rainfall_climatology (unavailable)")

    score = sum(scores) / len(scores)

    return {
        "status": "experimental",
        "aoi_mean_score": round(score, 4),
        "aoi_mean_class": _classify(score),
        "mean_slope_deg": slope_context.get("mean_slope_deg") if slope_available else None,
        "max_upstream_area_km2": hand_context.get("max_upstream_area_km2") if catchment_available else None,
        "rainfall_mean_annual_mm": rainfall_climatology.get("mean_annual_mm") if rainfall_available else None,
        "components_used": components_used,
        "components_excluded": components_excluded,
        "method": "slope_catchment_rainfall_unweighted_average",
        "validated": False,
        "spatial": False,
        "limitations": [
            "AOI-WIDE SCALAR only -- not a per-pixel spatial raster.",
            "RAINFALL COMPONENT IS A WEAK PROXY: CHIRPS mean_annual_mm is a "
            "long-term climatology mean, NOT an extreme-rainfall-intensity "
            "statistic. Flash floods are driven by short-duration intensity, "
            "not annual totals -- this cannot distinguish 'high annual, evenly "
            "distributed rainfall' from 'lower annual, violent bursts'. A real "
            "fix (GPM IMERG intensity percentiles) is deferred to Phase 9.",
            "Upstream catchment area reused from MERIT Hydro (~90m resolution) "
            "-- too coarse for small urban micro-catchments.",
            "All normalization ceilings (slope 15deg, catchment 50km^2, "
            "rainfall 2500mm) are provisional, not calibrated against real "
            "flash-flood outcomes.",
            "Does not account for drainage infrastructure, culvert capacity, "
            "or channel confinement.",
        ],
    }