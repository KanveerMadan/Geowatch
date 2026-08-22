"""
Phase 12B: constants for per-ward landcover-dependent hazard screening
(pluvial + waterlogging), and for the Case 1/2/3 wide-run reuse planner
that feeds it. Separate from Phase 12A's hazard_screening.py, which is
pure geometry/GEE-scalar and has no imagery/staleness/quality concerns
at all -- these constants exist because 12B is the first per-ward
screening step that depends on an actual Sentinel-2 + SAM + inference
run, which 12A deliberately has none of.
"""

from datetime import date

# ── Case 1/2/3 planner: wide-run reuse ──
# A prior wide-AOI run is eligible for reuse (Case 1) only if it is
# younger than this. Sentinel-2 composite content changes over time
# (new cloud-free pixels become available, seasonal land-cover shifts),
# so an old run silently reused indefinitely would go stale without any
# visible signal -- same "don't hide degradation" principle as every
# other status field in this project. Provisional, not empirically
# tuned against any real drift measurement.
LANDCOVER_STALENESS_DAYS = 30

# A prior run's raster footprint must cover at least this fraction of
# the boundary layer's combined extent to be considered a valid match
# for reuse. Below this, the prior run doesn't actually cover enough of
# the wards being screened and Case 1 must not fire -- fall through to
# Case 2/3 instead. Provisional.
MIN_FOOTPRINT_COVERAGE_PCT = 99.0

# ── Case 3: wide-run trigger ──
# Timeout ceiling for a full run_pipeline() call over a wide multi-ward
# AOI. Deliberately separate from hazard_screening.py's
# GEE_CALL_TIMEOUT_SECONDS (90s) -- that constant times single scalar
# GEE queries; this times an entire SAM + sliding-window-inference run
# across many tiles, which is a fundamentally longer, different kind of
# operation and must not reuse the same ceiling.
# Set from the pilot_3ward run (3min8s for a 3-ward/4-tile extent) with
# generous headroom for a ~24-ward/~40-tile extrapolated run -- NOT
# independently measured at full scale, flagged as provisional.
WIDE_RUN_TIMEOUT_SECONDS = 3600

# Sentinel-2 date range for Case 3 wide-AOI runs. Deliberately NOT
# "latest 90 days" auto-mode -- pilot_3ward hit 37.1% cloud contamination
# and an out_of_distribution applicability flag using auto-mode during
# the current monsoon window (2026-05-09 to 2026-08-07). This is a
# one-line mitigation, not a fix to cloud availability itself: widening
# the window increases the chance of finding enough clear observations,
# it does not guarantee it. The quality gate below is what actually
# catches a run that still comes back degraded despite this.
WIDE_RUN_DATE_START = "2025-11-01"  # start of typical post-monsoon clear season
# NOTE: run_pipeline() only takes the manual date-range branch when
# BOTH start_date AND end_date are truthy (`if start_date and end_date:`)
# -- confirmed against the real pipeline.py. A None here would silently
# fall through to the 90-day auto-window and discard WIDE_RUN_DATE_START
# too, defeating the whole point of this mitigation. Must be a real date,
# resolved at call time in landcover_screening.py, not left as None.
WIDE_RUN_DATE_END = date.today().isoformat()

# ── Case 3: post-run quality gate ──
# After a Case 3 wide run completes, its output is only accepted for
# per-ward pluvial/waterlogging extraction if BOTH of these hold.
# Below either threshold, every ward drawing on this run is marked
# not_calculated with a quality-gate reason attached -- never silently
# accepted as usable. Provisional thresholds, same caveat status as
# OOD_UNKNOWN_PCT_THRESHOLD in applicability_constants.py (in fact
# deliberately kept close to it for consistency, not independently
# derived).
MIN_VALID_OBSERVATION_PCT = 60.0
REQUIRE_LANDCOVER_IN_DISTRIBUTION = True  # if True, OOD wide runs are rejected outright