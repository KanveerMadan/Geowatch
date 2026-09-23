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


def finalize_applicability(applicability: dict, hydrological_surfaces: dict) -> dict:
    """
    Resolve the one status that genuinely needs `hydrological_surfaces`.

    WHY THIS EXISTS (build item 40, C14). Item 40 requires applicability to be
    computed BEFORE `hydrological_surfaces`, because the land-cover verdict is
    what says whether the surfaces derived from that model can be trusted --
    `compute_hydrological_surfaces()` is a weighted sum of the model's own
    `category_area_pct`. Computing the gate after the thing it gates is the
    "designed as a router, wired as a report" inversion S2 describes.

    But `compute_applicability()` also READ `hydrological_surfaces`, for exactly
    one check: whether `waterlogging` has any usable input. So the original
    ordering was not simply backwards -- there was a real back-reference, and
    moving the call without addressing it would have changed behaviour.

    Splitting it resolves the cycle honestly. Stage 1 decides everything that
    depends only on inference output and external context, and runs first.
    Stage 2 -- this function -- runs after `hydrological_surfaces` exists and
    fills in the single status that needed it.

    WORTH KNOWING: the check being resolved here is currently vacuous. It asks
    whether `impervious_fraction_pct is not None`, and
    `compute_hydrological_surfaces()` always returns
    `round(impervious_total, 2)` -- a float, on every path, because that module
    has no failure path at all. That is C21/S1 ("the only module in the analysis
    chain with no status field and no failure path") observed at this specific
    site. The guard is therefore preserved exactly as written rather than
    "fixed": making it meaningful requires giving
    `compute_hydrological_surfaces()` a real failure path, which is C21's own
    item and not item 40's scope. Written down here so the vacuity is a known
    property rather than a rediscovery.
    """
    if not applicability:
        return applicability

    waterlogging_data_available = (
        applicability.get("_hand_context_available", False)
        or (hydrological_surfaces is not None
            and hydrological_surfaces.get("impervious_fraction_pct") is not None)
    )
    if waterlogging_data_available:
        applicability["waterlogging"] = {
            "status": "applicable",
            "reason": "At least one of HAND or impervious-fraction context is available.",
        }
    else:
        applicability["waterlogging"] = {
            "status": "not_calculated",
            "reason": "Neither HAND nor impervious-fraction context is available.",
        }
    applicability.pop("_hand_context_available", None)
    return applicability


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

    STAGE 1 OF TWO (build item 40). This runs BEFORE
    `compute_hydrological_surfaces()`, because the `urban_landcover_model`
    verdict it produces is what tells every downstream consumer whether
    surfaces derived from that model can be trusted. Call
    `finalize_applicability()` afterwards to resolve `waterlogging`, the one
    status that genuinely needs `hydrological_surfaces`; see that function for
    why the back-reference exists and why it is not simply deleted.

    `hydrological_surfaces` remains accepted so that existing single-call
    callers keep their exact previous behaviour. When it is passed, this
    function is self-contained as before. When it is None -- the pipeline's
    path now -- `waterlogging` is provisional until stage 2 runs.
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
        # Consumed and removed by finalize_applicability() (build item 40).
        # Carries stage 1's view of hand_context forward so stage 2 can
        # reproduce the original OR exactly, without re-reading hand_context
        # and risking the two stages disagreeing about it.
        "_hand_context_available": (
            hand_context is not None and hand_context.get("status") == "available"
        ),
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