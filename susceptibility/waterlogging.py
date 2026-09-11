"""
Phase 7: persistent-waterlogging susceptibility baseline. STATIC/
SCREENING SLICE ONLY. Combines two AOI-WIDE SCALAR signals: HAND
(Phase 5's hand_context, reused) and imperviousness (Phase 3's
hydrological_surfaces, reused).

IMPORTANT: this module reuses the SAME mean_hnd_m value that
susceptibility/fluvial.py uses, but interprets it DIFFERENTLY. Fluvial
reads low HAND as "close to a channel that could overflow" (a river-
connectivity concern). Waterlogging reads low HAND as "flat, low-relief
terrain with nowhere for water to drain to" (a poor-drainage concern) --
independent of whether the AOI is near a river at all. Both readings
can be simultaneously true and are not in conflict; they are two
different physical mechanisms sharing one input statistic. This
dual-use is documented here and in fluvial.py's own limitations list.
"""

from configs.waterlogging_constants import (
    WATERLOGGING_HAND_NORMALIZATION_MAX_M,
    WATERLOGGING_IMPERVIOUS_NORMALIZATION_MAX_PCT,
    WATERLOGGING_CLASS_BREAKS,
    FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM,
)


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in WATERLOGGING_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


from perception.applicability_gate import gated


@gated("waterlogging")
def compute_waterlogging_susceptibility(hand_context: dict, hydrological_surfaces: dict,
                                         rainfall_climatology: dict = None) -> dict:
    """
    Args:
        hand_context: output of ingestion.hydrology.get_merit_hand_context()
            (Phase 5) -- reused for mean_hnd_m, interpreted as a
            low-relief/poor-drainage proxy here (see module docstring).
        hydrological_surfaces: output of
            perception.hydrological_surfaces.compute_hydrological_surfaces()
            (Phase 3) -- reused for impervious_fraction_pct.
        rainfall_climatology: optional, output of
            ingestion.rainfall.get_rainfall_climatology() (Phase 4) --
            same weak-proxy caveat as flash_flood.py; included as an
            optional third component since waterlogging is directly
            about standing water from rainfall accumulation.

    Returns:
        dict matching the master schema's susceptibility.waterlogging shape.
    """
    hand_available = hand_context is not None and hand_context.get("status") == "available"
    impervious_available = (
        hydrological_surfaces is not None
        and hydrological_surfaces.get("impervious_fraction_pct") is not None
    )

    if not hand_available and not impervious_available:
        return {
            "status": "insufficient_evidence",
            "reason": "Neither HAND context nor hydrological surfaces are available.",
        }

    components_used = []
    components_excluded = []
    scores = []

    if hand_available:
        mean_hnd = hand_context["mean_hnd_m"]
        relief_score = max(0.0, min(1.0, 1.0 - (mean_hnd / WATERLOGGING_HAND_NORMALIZATION_MAX_M)))
        scores.append(relief_score)
        components_used.append("low_relief_hand_proxy")
    else:
        components_excluded.append("hand_relief_proxy (unavailable)")

    if impervious_available:
        impervious_pct = hydrological_surfaces["impervious_fraction_pct"]
        impervious_score = max(0.0, min(1.0, impervious_pct / WATERLOGGING_IMPERVIOUS_NORMALIZATION_MAX_PCT))
        scores.append(impervious_score)
        components_used.append("impervious_fraction")
    else:
        components_excluded.append("impervious_fraction (unavailable)")

    rainfall_available = (
        rainfall_climatology is not None
        and rainfall_climatology.get("status") == "available"
        and rainfall_climatology.get("mean_annual_mm") is not None
    )
    if rainfall_available:
        rainfall_mm = rainfall_climatology["mean_annual_mm"]
        rainfall_score = max(0.0, min(1.0, rainfall_mm / FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM))
        scores.append(rainfall_score)
        components_used.append("rainfall_climatology_proxy")
    else:
        components_excluded.append("rainfall_climatology (unavailable or not provided)")

    score = sum(scores) / len(scores)

    return {
        "status": "experimental",
        "aoi_mean_score": round(score, 4),
        "aoi_mean_class": _classify(score),
        "mean_hnd_m": hand_context.get("mean_hnd_m") if hand_available else None,
        "impervious_fraction_pct": hydrological_surfaces.get("impervious_fraction_pct") if impervious_available else None,
        "rainfall_mean_annual_mm": rainfall_climatology.get("mean_annual_mm") if rainfall_available else None,
        "components_used": components_used,
        "components_excluded": components_excluded,
        "method": "relief_imperviousness_rainfall_unweighted_average",
        "validated": False,
        "spatial": False,
        "limitations": [
            "AOI-WIDE SCALAR only -- not a per-pixel spatial raster.",
            "Reuses fluvial susceptibility's mean_hnd_m value under a "
            "DIFFERENT physical interpretation (low-relief/poor-drainage, "
            "not river-overflow-proximity) -- see module docstring.",
            "Does not account for actual drainage infrastructure capacity, "
            "groundwater level, or soil permeability.",
            "Rainfall component (if included) is a coarse annual-mean proxy, "
            "not an event-specific accumulation statistic -- same caveat as "
            "flash_flood.py's rainfall component.",
            "All normalization ceilings are provisional, not calibrated "
            "against real waterlogging/persistent-inundation outcomes.",
        ],
    }