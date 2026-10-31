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

# Chosen on the round-2 TUNING events only, from FLASH_FLOOD_WEIGHT_GRID
# (result_round2_2026-10-28.json; pre-registered default was all 1).
FLASH_FLOOD_WEIGHTS = {'valley_floor': 0.5, 'steep_surroundings': 0.0, 'small_catchment': 0.0, 'rainfall_intensity': 1.0}
FLASH_FLOOD_WEIGHT_GRID = [
    {"valley_floor": v, "steep_surroundings": s, "small_catchment": c, "rainfall_intensity": 1.0}
    for v in (0.5, 1.0) for s in (0.0, 0.5, 1.0) for c in (0.0, 0.5, 1.0)]


# ── Flood round 4 (M4): intensity, response time, stream power. Fixed in
# experiments/flood_validation/PREREGISTRATION_ROUND4.md before the method was
# built. The round-2 constants above belong to the retired method
# (susceptibility/retired_methods/flash_flood_round2.py), except the IMERG
# intensity statistic, which is reused. ──

# A = MERIT upa focal max within this radius: the drainage line the cell sits
# on or beside (1 km would read the trunk river from every valley wall).
FLASH_POWER_DRAINAGE_RADIUS_M = 300.0
FLASH_POWER_MIN_AREA_KM2 = 0.01
FLASH_POWER_MIN_SLOPE = 0.001                 # m/m
# Hack's law, metric: L_km = HACK_C * A_km2 ** HACK_EXP.
FLASH_POWER_HACK_C = 1.273
FLASH_POWER_HACK_EXP = 0.6
# Kirpich: t_c [min] = KIRPICH_C * L_m ** 0.77 * S ** -0.385.
FLASH_POWER_KIRPICH_C = 0.0195
# IDF scaling from the half-hourly rate: i(d) = I30 * (max(d, 0.5 h) / 0.5 h) ** -IDF_N.
FLASH_POWER_IDF_EXPONENT = 0.6
FLASH_POWER_BASE_DURATION_H = 0.5
FLASH_POWER_RUNOFF_C = 0.5                    # rational method, Q = C i A / 3.6
FLASH_POWER_WIDTH_COEF = 3.0                  # channel width w = 3 Q ** 0.5
FLASH_POWER_OMEGA_MAX_W_M2 = 10000.0          # power = log10(1+w)/log10(1+this)
# I30 used when IMERG is unavailable (C73): one value per box either way.
FLASH_POWER_INTENSITY_FALLBACK_MM_H = 20.0

FLASH_POWER_PARAMS = {"hand_max_m": 10.0, "power_exponent": 1.0}
FLASH_POWER_PARAM_GRID = [{"hand_max_m": h, "power_exponent": k}
                          for h in (5.0, 10.0, 20.0) for k in (0.5, 1.0, 2.0)]
