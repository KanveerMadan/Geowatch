"""
Phase 3: centralized constants for the applicability router and
hydrological surface derivation. Created because no config/constants
file existed anywhere in the repo before this phase -- every threshold
was previously inline in whichever file used it (e.g. AMBIGUITY_MARGIN
in inference.py, the 0.6/10.0 thresholds in osm_dem.py). Those are left
where they are for now (not worth the churn of moving working code just
to centralize it) -- this file is for NEW Phase 3+ constants only, so
future phases have an obvious place to add to rather than scattering
more inline numbers.
"""

# ── OOD / applicability thresholds ──
# If a scene's unknown_pct exceeds this, the semantic land-cover model's
# output is flagged low-confidence for hydrological-surface derivation
# purposes. NOT empirically validated yet -- provisional, same caveat
# status as every other unvalidated threshold in this project (see
# osm_dem.py's 0.6/10.0 thresholds for precedent language).
OOD_UNKNOWN_PCT_THRESHOLD = 45.0

# If ambiguous_pct (Phase 3 confidence-bundle ambiguity flagging, see
# inference.py CONFUSION_PAIRS) exceeds this, treat the land-cover
# model's applicability as degraded rather than in_distribution.
OOD_AMBIGUOUS_PCT_THRESHOLD = 15.0

# ── Hydrological surface derivation weights ──
# Fractional contribution of each semantic class to the derived
# "impervious_fraction" surface. Provisional/uniform for now -- these
# are NOT calibrated against any real runoff measurement. Classes not
# listed contribute 0 imperviousness (dense_vegetation, vegetation_clearing,
# standing_water, active_construction -- construction sites are mixed/
# variable and deliberately left at 0 rather than guessed).
IMPERVIOUS_CLASS_WEIGHTS = {
    "paved_road": 1.0,
    "dense_informal_roofing": 0.9,
    "sparse_informal_roofing": 0.6,
}

# Fractional contribution to the derived "infiltration_proxy" surface.
# Higher = more absorption capacity. Also provisional/uncalibrated.
INFILTRATION_CLASS_WEIGHTS = {
    "dense_vegetation": 1.0,
    "vegetation_clearing": 0.3,  # actively losing absorption capacity
}