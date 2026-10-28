"""
Phase 4: constants for the pluvial susceptibility baseline.
All weights/thresholds here are PROVISIONAL and UNVALIDATED against
real flood outcomes -- same caveat status as every other threshold in
this project. See susceptibility/pluvial.py for how these are used.
"""

RAINFALL_MIN_MM_YEAR = 200.0
# PHASE 4 FIX: raised from 3000 -> 4500. Real Dharavi CHIRPS climatology
# (3234.9 mm/yr, confirmed 2026-07 test run) already exceeded the old
# ceiling, clamping rainfall_factor to 1.0 -- meaning any monsoon-climate
# city above 3000mm/yr (a large share of this project's actual target
# cities: coastal West Africa, South/Southeast Asian deltas) would be
# indistinguishable from each other on this component regardless of how
# much wetter one is than another. 4500 leaves headroom for genuinely
# extreme-rainfall AOIs (e.g. parts of coastal India, SE Asia can exceed
# 4000mm/yr) while still being provisional/unvalidated like every other
# threshold here -- not a calibrated ceiling, just a less-immediately-
# saturating one.
RAINFALL_MAX_MM_YEAR = 4500.0
RAINFALL_CLIMATOLOGY_YEARS = 10

# Item 26: the grid every pluvial input is put on. 30 m is the DEM's own
# resolution (Copernicus GLO-30 / FABDEM), so terrain is not resampled.
HYDROLOGY_PIXEL_M = 30.0

COMPONENT_WEIGHTS = {
    "impervious": 1.0,
    "infiltration_deficit": 0.8,
    "drainage_distance": 0.7,
    "rainfall_climatology": 0.9,
    "relative_elevation": 0.6,
    # item 26: sealed road surface that built area omits, and where runoff
    # concentrates. Provisional, like every weight here.
    "road_conduit": 0.6,
}

COMPONENT_QUALITY = {
    "impervious": 0.7,
    "infiltration_deficit": 0.7,
    "drainage_distance": 0.5,
    "rainfall_climatology": 0.8,
    "relative_elevation": 0.4,
    "road_conduit": 0.5,   # widths are class defaults, not measurements
}

SUSCEPTIBILITY_CLASS_BREAKS = {
    "very_low": (0.0, 0.2),
    "low": (0.2, 0.4),
    "moderate": (0.4, 0.6),
    "high": (0.6, 0.8),
    "very_high": (0.8, 1.01),
}