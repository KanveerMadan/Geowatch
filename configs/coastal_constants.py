"""
Phase 6: constants for coastal susceptibility (static/screening slice only
-- NOT tide/surge event hazard, which needs its own dataset ADR and is
explicitly deferred). All thresholds here are PROVISIONAL and
UNVALIDATED against real coastal flood outcomes -- same caveat status as
every other threshold in this project (see fluvial_constants.py,
pluvial_constants.py).
"""

# Radius searched around the AOI for nearby coastline geometry. If no
# coastline is found within this radius, the AOI is treated as far
# inland and distance_km is left as None rather than guessed. 50km is a
# provisional default -- generous enough to catch AOIs near a coast
# without triggering excessively large/slow GEE queries. Not derived
# from any hazard-relevant analysis.
COASTAL_SEARCH_RADIUS_KM = 50.0

# If the AOI's distance to the nearest mapped coastline is at or below
# this threshold, it is considered plausibly coastal for applicability
# purposes. Provisional -- not validated against a real
# coastal/non-coastal ground-truth set. Loosely informed by the idea
# that tidal/storm-surge influence typically doesn't extend far past a
# handful of km inland for most coastlines, but this varies hugely by
# coastal geomorphology (deltas, estuaries can carry influence much
# further) and is NOT locally calibrated here.
COASTAL_APPLICABILITY_THRESHOLD_KM = 10.0

# Distance (km) -> susceptibility score normalization. AOIs AT the
# coastline (distance=0) are treated as maximally susceptible (score=1);
# AOIs at or beyond this distance are treated as maximally
# non-susceptible (score floors to 0). Provisional ceiling, not
# calibrated against real coastal flood outcomes.
COASTAL_DISTANCE_NORMALIZATION_MAX_KM = 15.0

# Elevation (m, from FABDEM bare-earth) -> susceptibility contribution.
# AOIs at or above this elevation are treated as maximally
# non-susceptible on the elevation component, regardless of proximity to
# the coast. Provisional -- coastal flood exposure at higher elevations
# is possible in extreme surge/wave events, but this baseline treats
# elevation as a strong protective factor, consistent with the general
# "low-lying coastal land = vulnerable" framing used in most coastal
# hazard screening literature. NOT locally calibrated.
COASTAL_ELEVATION_NORMALIZATION_MAX_M = 10.0

COASTAL_CLASS_BREAKS = {
    "very_low": (0.0, 0.2),
    "low": (0.2, 0.4),
    "moderate": (0.4, 0.6),
    "high": (0.6, 0.8),
    "very_high": (0.8, 1.01),
}