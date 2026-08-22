"""
Phase 10A: constants for exposure computation (population, built-up,
roads, facilities intersecting a given evidence layer). This is EXPOSURE
only -- not vulnerability, not risk. See exposure/compute.py and
risk/compute.py module docstrings for the hard boundary between these
concepts, per the project's explicit ethical constraints.

All thresholds/parameters here are provisional where noted. Dataset IDs
must be treated as unverified until checked live (same discipline as
every other GEE asset in this project -- MERIT Hydro, FABDEM, the
shoreline dataset, JRC).
"""

# ── WorldPop ──
# Verified live 2026-07-31 (see verify_worldpop.py output):
#   - collection exists, 5221 images
#   - country filter property is `country` (NOT `ISO3`/`iso3`/etc.)
#   - years available: 2000-2020 (NO fresher data -- must be surfaced
#     explicitly in every output, never silently assumed current)
#   - band name: `population`
#   - null (not zero) for genuinely unpopulated/masked areas -- confirmed
#     via live ocean-point test, no .unmask(0) needed (unlike the JRC
#     Phase 8 bug -- do NOT blindly copy that fix here, it would be WRONG
#     for this dataset)
#
# SCALE BUG FOUND AND FIXED (2026-08-01): reduceRegion() with a `scale=`
# argument on this dataset is NOT safe for population SUMS -- it silently
# resamples the raster before summing, which duplicates or drops
# population mass depending on whether the chosen scale is finer or
# coarser than native. Confirmed live on the canonical Dharavi AOI:
#   scale=100m  -> sum=238,349   (undercounts -- coarser than native)
#   scale=92.77m (this constant) -> sum=282,983
#   scale=30m   -> sum=2,697,428  (10x inflated -- oversampling duplicates)
#   scale=10m   -> sum=24,332,208 (100x inflated)
#   native crsTransform (no scale at all) -> sum=282,983.025 -- MATCHES
#     the 92.77m result exactly, confirming 282,983 is correct and the
#     scale=100 result was silently wrong.
# CONSEQUENCE: WORLDPOP_NOMINAL_SCALE_M below must NEVER be passed as a
# `scale=` argument to any reduceRegion() call that sums population.
# ingestion/exposure_sources.py / exposure/compute.py's real population
# zonal-sum computation uses `crs=`/`crsTransform=` taken directly from
# the image's own .projection(), not this constant, specifically to
# avoid this bug. This constant is retained ONLY for display/metadata
# purposes (e.g. reporting "native resolution ~93m" to the user in
# limitations text) -- it is NOT used to drive any actual computation.
WORLDPOP_COLLECTION_ID = "WorldPop/GP/100m/pop"
WORLDPOP_COUNTRY_PROPERTY = "country"
WORLDPOP_BAND = "population"
WORLDPOP_NOMINAL_SCALE_M = 92.76624203150153  # DISPLAY/METADATA ONLY -- see note above

# ── GHSL built-up (fallback/cross-check reference, per Document 1's
# correction: do not rely only on GeoWatch's own 7-class model for
# built-up area, since it's geographically limited and has an unresolved
# paved_road/roofing confusion). Asset ID below is PROPOSED, NOT YET
# LIVE-VERIFIED -- verify with the same discipline as WorldPop
# (existence, band names, year, resolution, license) before trusting it
# in production. Do not assume this ID is correct without a live check.
GHSL_BUILTUP_ASSET = "JRC/GHSL/P2023A/GHS_BUILT_S/2020"  # UNVERIFIED -- confirm live
GHSL_RESOLUTION_M = 100

# ── Exposure class breaks (for optional ordinal display only --
# raw counts/areas are always preserved alongside these) ──
EXPOSURE_CLASS_BREAKS_POPULATION = {
    "negligible": (0, 100),
    "low": (100, 1000),
    "moderate": (1000, 10000),
    "high": (10000, 50000),
    "very_high": (50000, float("inf")),
}