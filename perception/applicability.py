"""
Phase 3: applicability router.

Determines, for each hazard mechanism, whether it's even relevant to
this AOI, and whether the semantic land-cover model's output should be
trusted for hydrological-surface derivation. Does NOT calculate any
actual hazard/susceptibility value -- that's Phase 4+. This module only
answers "should we even try, and how much should we trust the inputs."

Phase 6 update: coastal applicability is now calculated using a real
GEE polygon shoreline dataset (see ingestion/coastal.py), not an
OSM-coastline heuristic. Distance-to-coast + connectivity threshold
only -- still no tide/surge event forcing, which remains deferred
pending its own dataset ADR.
"""

from configs.applicability_constants import (
    OOD_UNKNOWN_PCT_THRESHOLD,
    OOD_AMBIGUOUS_PCT_THRESHOLD,
)


def compute_applicability(unknown_pct: float, ambiguous_pct: float, hand_context: dict = None,
                           coastal_context: dict = None, slope_context: dict = None,
                           hydrological_surfaces: dict = None) -> dict:
    """
    Determine per-mechanism applicability status.

    Args:
        unknown_pct: from inference_result (mosaicked, full-AOI value)
        ambiguous_pct: from inference_result (mosaicked, full-AOI value)
        hand_context: Phase 5 -- output of
            ingestion.hydrology.get_merit_hand_context(), or None if not
            yet computed by the caller. Used to give fluvial a real
            status instead of a hardcoded not_calculated stub.
        coastal_context: Phase 6 -- output of
            ingestion.coastal.get_coastline_context(), or None if not
            yet computed by the caller. Used to give coastal a real
            status instead of a hardcoded not_calculated stub.

    Returns:
        dict matching the master spec's applicability block shape.
    """
    if unknown_pct > OOD_UNKNOWN_PCT_THRESHOLD:
        landcover_status = "out_of_distribution"
        landcover_reason = (
            f"unknown_pct ({unknown_pct}%) exceeds OOD threshold "
            f"({OOD_UNKNOWN_PCT_THRESHOLD}%) -- semantic model output "
            f"is unreliable for this scene."
        )
    elif ambiguous_pct > OOD_AMBIGUOUS_PCT_THRESHOLD:
        landcover_status = "degraded"
        landcover_reason = (
            f"ambiguous_pct ({ambiguous_pct}%) exceeds threshold "
            f"({OOD_AMBIGUOUS_PCT_THRESHOLD}%) -- model is torn between "
            f"known confusion pairs across a large share of the AOI."
        )
    else:
        landcover_status = "in_distribution"
        landcover_reason = None

    # ── Phase 5: fluvial applicability now derived from a real
    # MERIT Hydro river-connectivity check, replacing the Phase 3
    # hardcoded not_calculated stub. ──
    if hand_context is not None and hand_context.get("status") == "available":
        if hand_context.get("river_connectivity"):
            fluvial_status = "applicable"
            fluvial_reason = (
                f"River-connected: max upstream drainage area "
                f"{hand_context.get('max_upstream_area_km2')} km^2 found "
                f"within {hand_context.get('buffer_km')}km buffer "
                f"(MERIT Hydro)."
            )
        else:
            fluvial_status = "low_relevance"
            fluvial_reason = (
                f"No significant upstream drainage area detected within "
                f"{hand_context.get('buffer_km')}km buffer -- AOI may not "
                f"be meaningfully river-connected."
            )
    else:
        fluvial_status = "not_calculated"
        fluvial_reason = (
            "MERIT Hydro HAND context unavailable or not computed for "
            "this run."
        )

    # ── Phase 6: coastal applicability now derived from a real
    # GEE shoreline-distance check, replacing the Phase 3 hardcoded
    # not_calculated stub. ──
    if coastal_context is not None and coastal_context.get("status") == "available":
        distance_km = coastal_context.get("distance_km")
        if distance_km is None:
            coastal_status = "not_applicable"
            coastal_reason = (
                f"No coastline geometry found within "
                f"{coastal_context.get('search_radius_km')}km of this AOI."
            )
        elif coastal_context.get("coastal_connectivity"):
            coastal_status = "applicable"
            coastal_reason = f"AOI is {distance_km}km from the nearest mapped coastline."
        else:
            coastal_status = "low_relevance"
            coastal_reason = (
                f"AOI is {distance_km}km from the nearest mapped coastline -- "
                f"beyond the applicability threshold, coastal mechanisms are "
                f"less likely to dominate here."
            )
    else:
        coastal_status = "not_calculated"
        coastal_reason = "Coastline context unavailable or not computed for this run."

    # ── Phase 7: flash-flood/waterlogging applicability -- gated to match
    # EXACTLY what compute_flash_flood_susceptibility() and
    # compute_waterlogging_susceptibility() actually require (an OR of
    # their usable inputs), not a single hardcoded input each. Otherwise
    # applicability and susceptibility can disagree in the same result.json
    # (e.g. slope fails but catchment+rainfall are fine -- susceptibility
    # still computes a real score, but applicability would wrongly say
    # not_calculated). ──
    flash_flood_data_available = (
        (slope_context is not None and slope_context.get("status") == "available")
        or (hand_context is not None and hand_context.get("status") == "available"
            and hand_context.get("max_upstream_area_km2") is not None)
    )
    if flash_flood_data_available:
        flash_flood_status = "applicable"
        flash_flood_reason = "At least one of slope or upstream-catchment context is available."
    else:
        flash_flood_status = "not_calculated"
        flash_flood_reason = "Neither slope nor upstream-catchment context is available."

    waterlogging_data_available = (
        (hand_context is not None and hand_context.get("status") == "available")
        or (hydrological_surfaces is not None
            and hydrological_surfaces.get("impervious_fraction_pct") is not None)
    )
    if waterlogging_data_available:
        waterlogging_status = "applicable"
        waterlogging_reason = "At least one of HAND or impervious-fraction context is available."
    else:
        waterlogging_status = "not_calculated"
        waterlogging_reason = "Neither HAND nor impervious-fraction context is available."

    return {
        "urban_landcover_model": {
            "status": landcover_status,
            "reason": landcover_reason,
        },
        "pluvial": {
            "status": "applicable",
            "reason": "Pluvial flooding can occur in any urban/peri-urban "
                       "setting; no exclusion criteria implemented yet.",
        },
        "fluvial": {
            "status": fluvial_status,
            "reason": fluvial_reason,
        },
        "coastal": {
            "status": coastal_status,
            "reason": coastal_reason,
        },
        "flash_flood": {
            "status": flash_flood_status,
            "reason": flash_flood_reason,
        },
        "waterlogging": {
            "status": waterlogging_status,
            "reason": waterlogging_reason,
        },
    }