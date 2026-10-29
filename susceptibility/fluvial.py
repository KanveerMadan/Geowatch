"""
Fluvial susceptibility, per pixel (item 26 Phase 1a; was an AOI-wide scalar,
Phase 5). Method fixed in experiments/flood_validation/PREREGISTRATION_ROUND2.md.

Components on the hydrology grid (susceptibility/hydro_rasters.py), each 0-1:

    low_hand    1 - HAND / HAND_NORMALIZATION_MAX_M      (MERIT Hydro hnd)
    river_size  log10(1 + upa_near) / log10(1 + FLUVIAL_UPSTREAM_AREA_NORMALIZATION_MAX_KM2)

combined as a weighted mean (FLUVIAL_WEIGHTS). The default is round 1's
HAND-only method, now per pixel. Weights change only on the round-2 tuning
events. The ceilings stay provisional.
"""

import numpy as np

from configs.fluvial_constants import (
    HAND_NORMALIZATION_MAX_M, FLUVIAL_CLASS_BREAKS, FLUVIAL_UPSTREAM_AREA_NORMALIZATION_MAX_KM2,
    FLUVIAL_WEIGHTS,
)
from susceptibility.hydro_rasters import clip01, layer, map_summary, weighted_map


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in FLUVIAL_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


# Item 26 Phase 1a, round 2 (experiments/flood_validation/result_round2_2026-10-28.json):
# held-out mean within-event AUC 0.8579 over 2 Copernicus EMS events
# (Hanoi, Kolonnawa), bar 0.70: validated -- for these events and inputs only.
# Round 1's AOI-wide scalar failed (0.448); that method is gone.
VALIDATION_STATUS = "validated"

from perception.applicability_gate import gated


def components(rasters: dict) -> dict:
    """{name: 0-1 array or None}. Pure; the harness tunes weights on these."""
    hand, upa = layer(rasters, "hand_m"), layer(rasters, "upa_near_km2")
    return {
        "low_hand": None if hand is None else clip01(1.0 - hand / HAND_NORMALIZATION_MAX_M),
        "river_size": None if upa is None else clip01(
            np.log10(1.0 + np.maximum(upa, 0.0))
            / np.log10(1.0 + FLUVIAL_UPSTREAM_AREA_NORMALIZATION_MAX_KM2)),
    }


def combine(comps: dict, weights: dict = None):
    return weighted_map(comps, FLUVIAL_WEIGHTS if weights is None else weights)


@gated("fluvial")
def compute_fluvial_susceptibility(rasters: dict = None, hand_context: dict = None,
                                   weights: dict = None) -> dict:
    """
    Args:
        rasters: susceptibility.hydro_rasters.fetch_hydro_rasters() output.
        hand_context: optional ingestion.hydrology.get_merit_hand_context()
            output, read only for the river-connectivity caveat.
        weights: override FLUVIAL_WEIGHTS (the validation harness only).

    Returns:
        dict matching the master schema's susceptibility.fluvial shape, plus
        `susceptibility_map` (per-pixel, NaN = no data) on the rasters' grid.
    """
    w = FLUVIAL_WEIGHTS if weights is None else weights
    comps = components(rasters) if rasters else {}
    used = [k for k, c in comps.items() if c is not None and w.get(k, 0) > 0]
    m = combine(comps, w) if used else None
    if m is None or not np.isfinite(m).any():
        return {
            "status": "insufficient_evidence",
            "validation_status": VALIDATION_STATUS,
            "reason": "per-pixel MERIT Hydro rasters unavailable"
                      + (f": {rasters.get('error')}" if rasters and rasters.get("error") else ""),
        }

    river_connected = (hand_context or {}).get("river_connectivity")
    limitations = [
        "MERIT Hydro is ~90m resolution, resampled to the 30 m hydrology grid "
        "-- too coarse for street-level or parcel-level claims.",
        "HAND_NORMALIZATION_MAX_M (30m) and the 10,000 km^2 river-size "
        "ceiling are provisional, not calibrated against real flood outcomes.",
        "This HAND is computed from MERIT Hydro's own terrain/routing, "
        "NOT from FABDEM elevation -- the two must not be conflated "
        "even though both are reported in this pipeline run.",
    ]
    if river_connected is False:
        limitations.append(
            "No significant upstream drainage area detected within the "
            f"{hand_context.get('buffer_km')}km buffer -- this AOI may not be "
            "meaningfully river-connected; fluvial susceptibility may be "
            "less relevant here than the score alone suggests."
        )

    return {
        "status": "experimental",
        "validation_status": VALIDATION_STATUS,
        **map_summary(m, _classify),
        "susceptibility_map": m,
        "components_used": used,
        "components_excluded": [k for k in comps if k not in used],
        "weights": dict(w),
        "ceilings": {"hand_m": HAND_NORMALIZATION_MAX_M,
                     "upstream_area_km2": FLUVIAL_UPSTREAM_AREA_NORMALIZATION_MAX_KM2},
        "inputs": {k: {kk: v[kk] for kk in ("source", "method", "validation_status")}
                   for k, v in rasters["layers"].items() if k in ("hand_m", "upa_near_km2")},
        "river_connectivity": river_connected,
        "method": "merit_hydro_hand_per_pixel_weighted",
        "true_hand": True,
        "validated": VALIDATION_STATUS == "validated",
        "spatial": True,
        "limitations": limitations,
    }
