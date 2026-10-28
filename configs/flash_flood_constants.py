"""
Phase 7: constants for flash-flood and waterlogging susceptibility.
Both are STATIC/SCREENING baselines only. All thresholds PROVISIONAL and
UNVALIDATED against real flood outcomes -- same caveat status as every
other threshold in this project.
"""

# ── Flash-flood ──
# Slope (degrees) at/above which terrain is considered maximally
# flash-flood-prone from a steepness standpoint. Provisional.
FLASH_FLOOD_SLOPE_NORMALIZATION_MAX_DEG = 15.0

# Upstream drainage area (km^2, from MERIT Hydro, already fetched in
# Phase 5's hand_context) at/below which a catchment is considered
# "small" -- small catchments concentrate runoff faster, a real
# flash-flood driver. AOIs with LARGER upstream area score LOWER on
# this component (large, slow-responding river systems are a fluvial
# concern, not primarily a flash-flood one). Provisional.
FLASH_FLOOD_SMALL_CATCHMENT_MAX_KM2 = 50.0

# Rainfall (mm/year, CHIRPS climatology -- a COARSE proxy for rainfall
# "load", NOT an extreme-intensity statistic). At/above this annual
# total, the rainfall-load component is treated as maximal. Provisional,
# and weaker evidence than the other two components -- see
# susceptibility/flash_flood.py's limitations for why.
FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM = 2500.0

FLASH_FLOOD_CLASS_BREAKS = {
    "very_low": (0.0, 0.2),
    "low": (0.2, 0.4),
    "moderate": (0.4, 0.6),
    "high": (0.6, 0.8),
    "very_high": (0.8, 1.01),
}


# ── Item 26 Phase 1a (round 2): per-pixel flash flood. Fixed in
# experiments/flood_validation/PREREGISTRATION_ROUND2.md before any run. ──

# valley_floor = 1 - HAND / this. Flash floods fill valley floors. Provisional.
FLASH_FLOOD_HAND_NORMALIZATION_MAX_M = 10.0

# steep_surroundings is the mean slope within this radius, not the cell's
# own slope: a cell's own slope would rank hillsides above the valley floors
# that flood.
FLASH_FLOOD_RELIEF_RADIUS_M = 1000.0

# small_catchment reads the largest drainage line within this radius
# (same reason as FLUVIAL_DRAINAGE_SEARCH_RADIUS_M).
FLASH_FLOOD_DRAINAGE_SEARCH_RADIUS_M = 1000.0

# Rainfall intensity replaces the annual total: the 99.9th percentile of
# IMERG V07 half-hourly rate over the 10 calendar years before the year of
# interest. Ceiling fixed before any IMERG value was read. Provisional.
FLASH_FLOOD_INTENSITY_PERCENTILE = 99.9
FLASH_FLOOD_INTENSITY_YEARS = 10
FLASH_FLOOD_INTENSITY_NORMALIZATION_MAX_MM_H = 20.0

FLASH_FLOOD_WEIGHTS = {"valley_floor": 1.0, "steep_surroundings": 1.0,
                       "small_catchment": 1.0, "rainfall_intensity": 1.0}
FLASH_FLOOD_WEIGHT_GRID = [
    {"valley_floor": v, "steep_surroundings": s, "small_catchment": c, "rainfall_intensity": 1.0}
    for v in (0.5, 1.0) for s in (0.0, 0.5, 1.0) for c in (0.0, 0.5, 1.0)]
