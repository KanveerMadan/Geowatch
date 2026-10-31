"""
Waterlogging susceptibility (flood taxonomy M3), flood round 4: where water
has stood before, on clay, on low ground, beside a large river. Method fixed
in experiments/flood_validation/PREREGISTRATION_ROUND4.md before it was built.
The round-2 weighted-mean method is retired
(susceptibility/retired_methods/waterlogging_round2.py).

Components on the hydrology grid (susceptibility/hydro_rasters.py), each 0-1:

    persistence  mean of the available of: JRC GSW monthly water frequency
                 (water months / observed months, 1984 to the year before the
                 reference year, at most 2021) and the Sentinel-1 share of
                 acquisitions with VV < -18 dB over the 3 calendar years
                 before it. Only years BEFORE the reference year are read.
    clay         min(1, clay % / 40), SoilGrids 0-30 cm (gaps: 1 km focal mean)
    low_relief   1 - HAND / 15 m (MERIT hnd)
    backwater    (1 - HAND / 5 m) x log10(upa_near / 100 km^2) / 2: low land
                 beside a large river. River stage is not observed; river size
                 stands in for a river that runs high in the wet season.

Score = weighted mean (WATERLOGGING_R4_WEIGHTS). The HAND here is the same
MERIT HAND fluvial reads, read as "nowhere to drain to", not "near a channel
that overflows".
"""
from __future__ import annotations

import numpy as np

from configs.waterlogging_constants import (
    WATERLOGGING_BACKWATER_DECADES, WATERLOGGING_BACKWATER_HAND_MAX_M,
    WATERLOGGING_BACKWATER_MIN_KM2, WATERLOGGING_CLASS_BREAKS, WATERLOGGING_CLAY_MAX_PCT,
    WATERLOGGING_HAND_NORMALIZATION_MAX_M, WATERLOGGING_R4_WEIGHTS,
)
from susceptibility.hydro_rasters import clip01, layer, map_summary, weighted_map
from susceptibility.inputs import provenance, weakest

# Flood round 4 (experiments/flood_validation/result_round4_2026-10-30.json):
# failed -- mean within-event AUC over the qualifying test events, waterlogging 0.613 (Assam 0.406, Sylhet 0.668,
# Kerala 0.766); bar 0.70.
VALIDATION_STATUS = "failed"
METHOD = "persistence_clay_relief_backwater_per_pixel_weighted"
INPUT_LAYERS = ("hand_m", "upa_near_km2", "clay_pct", "jrc_water_freq", "s1_water_freq")
CEILINGS = {"low_relief_hand_m": WATERLOGGING_HAND_NORMALIZATION_MAX_M,
            "clay_pct": WATERLOGGING_CLAY_MAX_PCT,
            "backwater_hand_m": WATERLOGGING_BACKWATER_HAND_MAX_M,
            "backwater_min_km2": WATERLOGGING_BACKWATER_MIN_KM2}


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in WATERLOGGING_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


def persistence(jrc, s1):
    """Per-cell mean of whichever frequencies are finite there; None if neither."""
    parts = [np.asarray(a, dtype=np.float64) for a in (jrc, s1) if a is not None]
    if not parts:
        return None
    stack = np.stack(parts)
    ok = np.isfinite(stack)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = np.where(ok, stack, 0.0).sum(0) / ok.sum(0)
    return clip01(np.where(ok.any(0), m, np.nan))


def components(rasters: dict) -> dict:
    """{name: 0-1 array or None}. Pure; the harness tunes weights on these."""
    hand, upa = layer(rasters, "hand_m"), layer(rasters, "upa_near_km2")
    clay = layer(rasters, "clay_pct")
    with np.errstate(invalid="ignore", divide="ignore"):
        backwater = None if hand is None or upa is None else (
            clip01(1.0 - hand / WATERLOGGING_BACKWATER_HAND_MAX_M)
            * clip01(np.log10(np.maximum(upa, 1e-9) / WATERLOGGING_BACKWATER_MIN_KM2)
                     / WATERLOGGING_BACKWATER_DECADES))
        backwater = None if backwater is None else np.where(
            np.isfinite(hand) & np.isfinite(upa), backwater, np.nan)
    return {
        "persistence": persistence(layer(rasters, "jrc_water_freq"),
                                   layer(rasters, "s1_water_freq")),
        "clay": None if clay is None else clip01(clay / WATERLOGGING_CLAY_MAX_PCT),
        "low_relief": None if hand is None
        else clip01(1.0 - hand / WATERLOGGING_HAND_NORMALIZATION_MAX_M),
        "backwater": backwater,
    }


def combine(comps: dict, weights: dict = None):
    return weighted_map(comps, WATERLOGGING_R4_WEIGHTS if weights is None else weights)


from perception.applicability_gate import gated


@gated("waterlogging")
def compute_waterlogging_susceptibility(rasters: dict = None, weights: dict = None) -> dict:
    """
    Args:
        rasters: susceptibility.hydro_rasters.fetch_hydro_rasters() output,
            persistence layers included.
        weights: override WATERLOGGING_R4_WEIGHTS (the validation harness only).
    """
    w = dict(WATERLOGGING_R4_WEIGHTS if weights is None else weights)
    comps = components(rasters) if rasters else {}
    used = [k for k, c in comps.items() if c is not None and w.get(k, 0) > 0]
    m = combine(comps, w) if used else None
    if m is None or not np.isfinite(m).any():
        return {"status": "insufficient_evidence", "validation_status": VALIDATION_STATUS,
                "reason": "No per-pixel water history, clay, HAND or upstream area is "
                          "available."}
    errors = (rasters or {}).get("errors", {})
    excluded = []
    for k, c in comps.items():
        if k in used:
            continue
        why = "weight 0" if c is not None else "unavailable"
        excluded.append(f"{k} ({why})")
    inputs = {k: provenance(v) for k, v in rasters.get("layers", {}).items()
              if k in INPUT_LAYERS}
    return {
        "status": "experimental",
        "validation_status": weakest(VALIDATION_STATUS,
                                     *(i["validation_status"] for i in inputs.values())),
        "inputs": inputs,
        **map_summary(m, _classify),
        "susceptibility_map": m,
        "components_used": used,
        "components_excluded": excluded,
        "input_errors": {k: v for k, v in errors.items() if k in INPUT_LAYERS},
        "weights": w,
        "ceilings": dict(CEILINGS),
        "method": METHOD,
        "validated": VALIDATION_STATUS == "validated",
        "spatial": True,
        "limitations": [
            "Sentinel-1 persistence reads smooth surfaces (tarmac, sand, airports) as "
            "water; JRC monthly history ends in 2021.",
            "SoilGrids is 250 m and masks built-up land; gaps take the 1 km focal mean.",
            "Backwater has no river-stage input: river size stands in for stage.",
            "Drainage infrastructure and the water table are not modelled.",
        ],
    }
