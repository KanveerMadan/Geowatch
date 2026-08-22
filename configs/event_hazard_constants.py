"""
Phase 9: event hazard constants. All provisional/unvalidated.
"""

# ── Pluvial event rainfall (GPM IMERG) ──
IMERG_ASSET = "NASA/GPM_L3/IMERG_V07"
# Event accumulation (mm) at/above which the rainfall-forcing component
# is treated as maximal for hazard conditioning. Provisional.
# NOTE: originally set for single-storm-event totals; a real live test
# with a full month-long monsoon window (Dharavi, July 2026) returned
# 1506.8mm, instantly saturating this ceiling to 1.0 and making the
# entire "event conditioning" step a no-op (hazard score == raw
# susceptibility score, since multiplying by 1.0 changes nothing).
# Raised to accommodate monthly accumulation windows. Still provisional/
# unvalidated -- the RIGHT fix long-term is scaling this ceiling to the
# actual event window LENGTH (a 3-day window should saturate at a much
# lower total than a 31-day window), not a single fixed constant
# regardless of how long the caller's event_start/event_end span is.
# Flagging that as a real follow-up, not fixing the window-length
# normalization in this pass.
EVENT_RAINFALL_NORMALIZATION_MAX_MM = 800.0
# Below this, event rainfall is treated as negligible forcing.
EVENT_RAINFALL_MIN_MM = 0.0

EVENT_HAZARD_CLASS_BREAKS = {
    "very_low": (0.0, 0.2),
    "low": (0.2, 0.4),
    "moderate": (0.4, 0.6),
    "high": (0.6, 0.8),
    "very_high": (0.8, 1.01),
}

# ── Fluvial "discharge proxy" (NOT real discharge -- see
# ingestion/event_hazard.py's explicit warning) ──
# Buffer for catchment-wide event rainfall accumulation, reusing the
# same buffer distance as Phase 5's fluvial HAND context for consistency.
DISCHARGE_PROXY_BUFFER_KM = 3.0
# Same saturation issue as EVENT_RAINFALL_NORMALIZATION_MAX_MM above --
# raised for the same reason, same caveat about window-length scaling
# being the real long-term fix.
DISCHARGE_PROXY_RAINFALL_NORMALIZATION_MAX_MM = 1800.0