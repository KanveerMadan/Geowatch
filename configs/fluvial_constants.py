"""
Phase 5: constants for fluvial susceptibility.
All thresholds here are PROVISIONAL and UNVALIDATED against real flood
outcomes -- same caveat status as pluvial_constants.py. Do not treat any
of these as calibrated.
"""

# Buffer applied around the AOI before querying MERIT Hydro's HAND/
# upstream-area bands. HAND correctness near AOI edges depends on
# drainage context OUTSIDE the user's rectangle -- water flows in from
# beyond the box. 3km is a provisional default for city-scale AOIs
# (~2.5km across, like canonical Dharavi); not derived from any
# catchment-delineation analysis. Revisit if used on much larger AOIs.
FLUVIAL_BUFFER_KM = 3.0

MERIT_HYDRO_SCALE_M = 90  # MERIT Hydro native resolution

# River-connectivity check: if the max upstream drainage area (km^2)
# found anywhere in the buffered region exceeds this, the AOI is
# considered plausibly river-connected for applicability purposes.
# Provisional -- not validated against a real inland/coastal/river
# ground-truth set.
RIVER_CONNECTIVITY_UPSTREAM_AREA_KM2_THRESHOLD = 1.0

# HAND (meters) -> susceptibility score normalization. Pixels at or
# above this HAND value are treated as maximally non-susceptible (score
# floors to 0). Loosely informed by general HAND-based floodplain
# literature (low-HAND = near-drainage = high susceptibility), but the
# exact ceiling is NOT locally calibrated.
HAND_NORMALIZATION_MAX_M = 30.0

FLUVIAL_CLASS_BREAKS = {
    "very_low": (0.0, 0.2),
    "low": (0.2, 0.4),
    "moderate": (0.4, 0.6),
    "high": (0.6, 0.8),
    "very_high": (0.8, 1.01),
}