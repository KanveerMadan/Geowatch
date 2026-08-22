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
