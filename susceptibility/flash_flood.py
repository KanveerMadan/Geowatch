"""
Flash-flood susceptibility, per pixel (item 26 Phase 1a; was an AOI-wide
scalar of slope, catchment size and CHIRPS annual total, Phase 7). STATIC /
SCREENING SLICE ONLY. Method fixed in
experiments/flood_validation/PREREGISTRATION_ROUND2.md before any run.

Components on the hydrology grid (susceptibility/hydro_rasters.py), each 0-1:

    valley_floor        1 - HAND / FLASH_FLOOD_HAND_NORMALIZATION_MAX_M
    steep_surroundings  mean slope within FLASH_FLOOD_RELIEF_RADIUS_M
                        / FLASH_FLOOD_SLOPE_NORMALIZATION_MAX_DEG
    small_catchment     1 - upa_near / FLASH_FLOOD_SMALL_CATCHMENT_MAX_KM2
    rainfall_intensity  IMERG p99.9 half-hourly rate
                        / FLASH_FLOOD_INTENSITY_NORMALIZATION_MAX_MM_H

Steepness is the SURROUNDING relief, not the cell's own slope: flash floods
fill flat valley floors under steep ground, and a cell's own slope would rank
the hillsides above them. Rainfall is now an intensity statistic, not the
annual total -- round 1's stated weak proxy. At 0.1 deg it is near-constant
over a city AOI, so it sets the level between places, not the pattern within
one. Weighted mean (FLASH_FLOOD_WEIGHTS); weights change only on the round-2
tuning events. Ceilings provisional.
"""
import numpy as np

from configs.flash_flood_constants import (
    FLASH_FLOOD_CLASS_BREAKS, FLASH_FLOOD_HAND_NORMALIZATION_MAX_M,
    FLASH_FLOOD_INTENSITY_NORMALIZATION_MAX_MM_H, FLASH_FLOOD_SLOPE_NORMALIZATION_MAX_DEG,
    FLASH_FLOOD_SMALL_CATCHMENT_MAX_KM2, FLASH_FLOOD_WEIGHTS,
)
from susceptibility.hydro_rasters import clip01, layer, map_summary, weighted_map


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in FLASH_FLOOD_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


# Item 26 Phase 1a, round 2 (experiments/flood_validation/result_round2_2026-10-28.json):
# not-run -- 1 of 3 held-out events had >= 50 flooded cells (Kastelli 0.881;
# Volos 0 flooded, Choloma outside its EMS product), fewer than the 2 required.
# Not-run is "experimental": the per-pixel method is untested at the bar.
# (Round 1's scalar method failed, 0.447; that method is gone.)
VALIDATION_STATUS = "experimental"

from perception.applicability_gate import gated

INPUT_LAYERS = ("hand_m", "relief_slope_deg", "upa_near_km2", "rain_intensity_mm_h")


def components(rasters: dict) -> dict:
    """{name: 0-1 array or None}. Pure; the harness tunes weights on these."""
    hand, relief = layer(rasters, "hand_m"), layer(rasters, "relief_slope_deg")
    upa, rain = layer(rasters, "upa_near_km2"), layer(rasters, "rain_intensity_mm_h")
    return {
        "valley_floor": None if hand is None
        else clip01(1.0 - hand / FLASH_FLOOD_HAND_NORMALIZATION_MAX_M),
        "steep_surroundings": None if relief is None
        else clip01(relief / FLASH_FLOOD_SLOPE_NORMALIZATION_MAX_DEG),
        "small_catchment": None if upa is None
        else clip01(1.0 - upa / FLASH_FLOOD_SMALL_CATCHMENT_MAX_KM2),
        "rainfall_intensity": None if rain is None
        else clip01(rain / FLASH_FLOOD_INTENSITY_NORMALIZATION_MAX_MM_H),
    }


def combine(comps: dict, weights: dict = None):
    return weighted_map(comps, FLASH_FLOOD_WEIGHTS if weights is None else weights)


@gated("flash_flood")
def compute_flash_flood_susceptibility(rasters: dict = None, weights: dict = None) -> dict:
    """
    Args:
        rasters: susceptibility.hydro_rasters.fetch_hydro_rasters() output.
        weights: override FLASH_FLOOD_WEIGHTS (the validation harness only).

    Returns:
        dict matching the master schema's susceptibility.flash_flood shape,
        plus `susceptibility_map` (per-pixel, NaN = no data).
    """
    w = FLASH_FLOOD_WEIGHTS if weights is None else weights
    comps = components(rasters) if rasters else {}
    terrain = [k for k in ("valley_floor", "steep_surroundings", "small_catchment")
               if comps.get(k) is not None and w.get(k, 0) > 0]
    if not terrain:
        return {
            "status": "insufficient_evidence",
            "validation_status": VALIDATION_STATUS,
            "reason": "No per-pixel terrain raster (HAND, relief slope, upstream area) is available.",
        }
    used = [k for k, c in comps.items() if c is not None and w.get(k, 0) > 0]
    errors = (rasters or {}).get("errors", {})
    excluded = []
    for k in comps:
        if k in used:
            continue
        why = "weight 0" if comps[k] is not None else "unavailable"
        if k == "rainfall_intensity" and "rain_intensity_mm_h" in errors:
            why += f": {errors['rain_intensity_mm_h']}"
        excluded.append(f"{k} ({why})")
    m = combine(comps, w)
    return {
        "status": "experimental",
        "validation_status": VALIDATION_STATUS,
        **map_summary(m, _classify),
        "susceptibility_map": m,
        "components_used": used,
        "components_excluded": excluded,
        "weights": dict(w),
        "inputs": {k: {kk: v[kk] for kk in ("source", "method", "validation_status")}
                   for k, v in rasters["layers"].items() if k in INPUT_LAYERS},
        "method": "valley_relief_catchment_intensity_per_pixel_weighted",
        "validated": VALIDATION_STATUS == "validated",
        "spatial": True,
        "limitations": [
            "Rainfall intensity is a climatological percentile (IMERG, 0.1 deg), "
            "not an event forecast, and is near-constant across a city AOI.",
            "HAND and upstream area are MERIT Hydro (~90m) -- too coarse for "
            "small urban micro-catchments.",
            "All normalization ceilings (HAND 10 m, slope 15deg, catchment "
            "50km^2, intensity 20 mm/h) are provisional, not calibrated "
            "against real flash-flood outcomes.",
            "Does not account for drainage infrastructure, culvert capacity, "
            "or channel confinement.",
        ],
    }
