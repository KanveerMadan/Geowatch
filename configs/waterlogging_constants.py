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

# Shared with flash_flood_constants.py's rainfall-load proxy -- imported
# here directly so waterlogging.py doesn't need a cross-mechanism import
# from configs.flash_flood_constants at all.
FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM = 2500.0