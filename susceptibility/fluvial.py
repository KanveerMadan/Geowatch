"""
Phase 5: fluvial susceptibility baseline, built on MERIT Hydro's real
precomputed HAND. Deliberately a SIMPLER direct HAND-threshold
classification, not a multi-component weighted fusion like pluvial's --
HAND alone is already a physically meaningful signal, and we only have
an AOI-WIDE SCALAR value (not a per-pixel raster) at this stage, so a
complex fusion formula would imply more precision than the input
actually supports.
"""

from configs.fluvial_constants import (
    HAND_NORMALIZATION_MAX_M, FLUVIAL_CLASS_BREAKS,
)


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in FLUVIAL_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


from perception.applicability_gate import gated


@gated("fluvial")
def compute_fluvial_susceptibility(hand_context: dict) -> dict:
    """
    Args:
        hand_context: output of ingestion.hydrology.get_merit_hand_context()

    Returns:
        dict matching the master schema's susceptibility.fluvial shape.
    """
    if hand_context.get("status") != "available":
        return {
            "status": "insufficient_evidence",
            "reason": f"MERIT Hydro HAND unavailable: {hand_context.get('error')}",
        }

    mean_hnd = hand_context["mean_hnd_m"]
    # Lower HAND -> closer to drainage -> higher susceptibility.
    # Score = 1 at HAND=0m, 0 at HAND >= HAND_NORMALIZATION_MAX_M.
    score = max(0.0, min(1.0, 1.0 - (mean_hnd / HAND_NORMALIZATION_MAX_M)))

    river_connected = hand_context.get("river_connectivity")

    limitations = [
        "AOI-WIDE SCALAR only -- mean HAND over the AOI, not a per-pixel "
        "spatial raster. Does not show WHERE within the AOI susceptibility "
        "is higher or lower.",
        "MERIT Hydro is ~90m resolution -- too coarse for street-level "
        "or parcel-level claims.",
        "HAND_NORMALIZATION_MAX_M (30m) is a provisional ceiling, not "
        "calibrated against real flood outcomes.",
        "This HAND is computed from MERIT Hydro's own terrain/routing, "
        "NOT from FABDEM elevation -- the two must not be conflated "
        "even though both are reported in this pipeline run.",
    ]
    if not river_connected:
        limitations.append(
            "No significant upstream drainage area detected within the "
            f"{hand_context.get('buffer_km')}km buffer -- this AOI may not be "
            "meaningfully river-connected; fluvial susceptibility may be "
            "less relevant here than the score alone suggests."
        )

    return {
        "status": "experimental",
        "aoi_mean_score": round(score, 4),
        "aoi_mean_class": _classify(score),
        "mean_hnd_m": mean_hnd,
        "min_hnd_m": hand_context.get("min_hnd_m"),
        "max_hnd_m": hand_context.get("max_hnd_m"),
        "river_connectivity": river_connected,
        "max_upstream_area_km2": hand_context.get("max_upstream_area_km2"),
        "method": "merit_hydro_hand_direct_threshold",
        "true_hand": True,
        "validated": False,
        "spatial": False,
        "limitations": limitations,
    }