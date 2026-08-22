"""
Phase 8: fuses JRC Global Surface Water baseline
(ingestion.inundation.get_permanent_water_context) and Sentinel-1 SAR
change detection (ingestion.inundation.get_sentinel1_change_context)
into a single observed_inundation result, optionally cross-checked
against the existing optical standing_water classification from the
main land-cover pipeline.

This is EVENT-SPECIFIC OBSERVED EVIDENCE, not a susceptibility/
screening baseline like Phases 4-7 -- see ingestion/inundation.py's
module docstring for the full distinction.
"""


def compute_observed_inundation(jrc_context: dict, s1_context: dict,
                                 optical_standing_water_pct: float = None) -> dict:
    """
    Args:
        jrc_context: output of ingestion.inundation.get_permanent_water_context()
        s1_context: output of ingestion.inundation.get_sentinel1_change_context()
        optical_standing_water_pct: optional, the existing Sentinel-2
            model's standing_water category_area_pct from a land-cover
            run over the SAME (or closely matching) event window --
            included as a cross-check display value only, never fused
            into the score.

    Returns:
        dict matching the master schema's observed_inundation shape.
    """
    jrc_available = jrc_context is not None and jrc_context.get("status") == "available"
    s1_available = s1_context is not None and s1_context.get("status") == "experimental"

    if not jrc_available and not s1_available:
        reason_parts = []
        if jrc_context is not None and jrc_context.get("error"):
            reason_parts.append(f"JRC: {jrc_context['error']}")
        if s1_context is not None:
            reason_parts.append(f"Sentinel-1: {s1_context.get('reason') or s1_context.get('error')}")
        return {
            "status": "insufficient_evidence",
            "reason": "; ".join(reason_parts) if reason_parts else "Neither JRC nor Sentinel-1 context available.",
        }

    result = {
        "status": "experimental",
        "permanent_water_pct": jrc_context.get("permanent_water_pct") if jrc_available else None,
        "seasonal_water_pct": jrc_context.get("seasonal_water_pct") if jrc_available else None,
        "probable_new_inundation_pct": s1_context.get("probable_new_inundation_pct") if s1_available else None,
        "optical_standing_water_pct_cross_check": optical_standing_water_pct,
        "components_used": [],
        "components_excluded": [],
        "validated": False,
        "spatial": False,
    }

    if jrc_available:
        result["components_used"].append("jrc_global_surface_water_baseline")
    else:
        result["components_excluded"].append(
            f"jrc_baseline (unavailable: {jrc_context.get('error') if jrc_context else 'not computed'})"
        )

    if s1_available:
        result["components_used"].append("sentinel1_sar_change_detection")
    else:
        reason = s1_context.get("reason") or s1_context.get("error") if s1_context else "not computed"
        result["components_excluded"].append(f"sentinel1_change_detection (unavailable: {reason})")

    # Cross-check note: flag a real, interpretable discrepancy rather
    # than silently combining numbers into one score.
    notes = []
    if jrc_available and s1_available and s1_context.get("probable_new_inundation_pct") is not None:
        new_pct = s1_context["probable_new_inundation_pct"]
        permanent_pct = jrc_context.get("permanent_water_pct") or 0.0
        if new_pct > permanent_pct + 10.0:
            notes.append(
                f"probable_new_inundation_pct ({new_pct}%) exceeds the historical "
                f"permanent-water baseline ({permanent_pct}%) by more than 10 "
                f"points -- this AOI shows a meaningfully larger water-like SAR "
                f"signal than its historical norm, worth closer review. This is "
                f"a flagged pattern, not a confirmed flood."
            )
    if optical_standing_water_pct is not None and jrc_available:
        permanent_pct = jrc_context.get("permanent_water_pct") or 0.0
        if optical_standing_water_pct > permanent_pct + 10.0:
            notes.append(
                f"Optical standing_water classification ({optical_standing_water_pct}%) "
                f"exceeds the historical permanent-water baseline ({permanent_pct}%) "
                f"by more than 10 points -- consistent with, but not proof of, new "
                f"inundation. Note: this model's standing_water class has a "
                f"documented confusion with dense_vegetation in this project."
            )
    result["notes"] = notes

    result["limitations"] = [
        "This is a screening-level evidence fusion, NOT a validated flood-"
        "detection algorithm. It has not been checked against any real "
        "historical flood event.",
        "permanent_water_pct/seasonal_water_pct are a multi-decade HISTORICAL "
        "baseline (JRC, 1984-2021), not current conditions.",
        "probable_new_inundation_pct comes from a single fixed SAR backscatter "
        "threshold, not locally calibrated -- see "
        "ingestion.inundation.get_sentinel1_change_context()'s own limitations.",
        "optical_standing_water_pct_cross_check (if provided) comes from a "
        "single-snapshot optical classification with its own known confusions "
        "-- shown for comparison only, never fused into the score.",
        "No per-pixel spatial raster is produced in this phase -- all figures "
        "are AOI-wide fractions.",
    ]

    print(f"Observed inundation: permanent={result['permanent_water_pct']}%, "
          f"seasonal={result['seasonal_water_pct']}%, "
          f"probable_new={result['probable_new_inundation_pct']}%, "
          f"optical_cross_check={result['optical_standing_water_pct_cross_check']}%")
    for n in notes:
        print(f"  NOTE: {n}")

    return result