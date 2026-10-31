"""
Phase 7: constants for persistent-waterlogging susceptibility.
STATIC/SCREENING baseline only. All thresholds PROVISIONAL and
UNVALIDATED against real flood outcomes -- same caveat status as every
other threshold in this project.
"""

# HAND (meters, MERIT Hydro, already fetched in Phase 5) at/below which
# terrain is treated as maximally low-relief/waterlogging-prone from a
# relief standpoint. Provisional -- reuses the same HAND value fluvial
# uses, but a LOW HAND here is read as "flat, poorly-draining" rather
# than "near a channel that could overflow" -- different physical
# interpretation of the same underlying number, explicitly documented
# in susceptibility/waterlogging.py.
WATERLOGGING_HAND_NORMALIZATION_MAX_M = 15.0

# Imperviousness (%, from Phase 3's hydrological_surfaces) at/above
# which the drainage-limiting component is treated as maximal.
# Provisional.
WATERLOGGING_IMPERVIOUS_NORMALIZATION_MAX_PCT = 70.0

WATERLOGGING_CLASS_BREAKS = {
    "very_low": (0.0, 0.2),
    "low": (0.2, 0.4),
    "moderate": (0.4, 0.6),
    "high": (0.6, 0.8),
    "very_high": (0.8, 1.01),
}

# The rainfall-load ceiling is shared with flash flood and defined once, in
# configs/flash_flood_constants.py (item 26: it was duplicated here).

# ── Item 26 Phase 1a (round 2): per-pixel waterlogging. Fixed in
# experiments/flood_validation/PREREGISTRATION_ROUND2.md before any run. ──

# flatness = 1 - slope / this; equal to PLUVIAL_SLOPE_NORMALIZATION_MAX_DEG.
WATERLOGGING_SLOPE_NORMALIZATION_MAX_DEG = 5.0

# Chosen on the round-2 TUNING events only, from WATERLOGGING_WEIGHT_GRID
# (result_round2_2026-10-28.json; pre-registered default was all 1).
WATERLOGGING_WEIGHTS = {'low_relief': 1.0, 'impervious': 0.0, 'flatness': 0.0, 'rainfall_climatology': 1.0}
WATERLOGGING_WEIGHT_GRID = [
    {"low_relief": r, "impervious": i, "flatness": f, "rainfall_climatology": 1.0}
    for r in (0.0, 0.5, 1.0) for i in (0.0, 0.5, 1.0) for f in (0.0, 0.5, 1.0)
    if (r, i, f) != (0.0, 0.0, 0.0)]


# ── Flood round 4 (M3): persistence, clay, low relief, backwater. Fixed in
# experiments/flood_validation/PREREGISTRATION_ROUND4.md before the method was
# built. WATERLOGGING_HAND_NORMALIZATION_MAX_M (15 m) above is reused for
# low_relief; the rest above belongs to the retired method
# (susceptibility/retired_methods/waterlogging_round2.py). ──

# JRC GSW monthly history ends in December 2021.
WATERLOGGING_JRC_MONTHLY_LAST_YEAR = 2021
WATERLOGGING_JRC_MONTHLY_FIRST_YEAR = 1984
# Sentinel-1 open water: VV below this, over the calendar years before the event.
WATERLOGGING_S1_WATER_DB = -18.0
WATERLOGGING_S1_YEARS = 3
# clay = min(1, clay % / this); SoilGrids 0-30 cm, thickness-weighted; gaps
# filled from the focal mean within the radius.
WATERLOGGING_CLAY_MAX_PCT = 40.0
WATERLOGGING_CLAY_FILL_RADIUS_M = 1000.0
# backwater = (1 - HAND / this) * log10(upa_near / BACKWATER_MIN) / BACKWATER_DECADES.
WATERLOGGING_BACKWATER_HAND_MAX_M = 5.0
WATERLOGGING_BACKWATER_MIN_KM2 = 100.0
WATERLOGGING_BACKWATER_DECADES = 2.0

WATERLOGGING_R4_WEIGHTS = {"persistence": 1.0, "clay": 1.0, "low_relief": 1.0, "backwater": 1.0}
WATERLOGGING_R4_WEIGHT_GRID = [
    {"persistence": p, "clay": c, "low_relief": r, "backwater": b}
    for p in (1.0, 2.0) for c in (0.0, 0.5, 1.0) for r in (0.5, 1.0) for b in (0.0, 0.5, 1.0)]
