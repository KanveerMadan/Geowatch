"""
Phase 8: constants for observed inundation (JRC permanent/seasonal water
baseline + Sentinel-1 SAR change detection). All thresholds PROVISIONAL
and UNVALIDATED against real flood events -- same caveat status as every
other threshold in this project. This is event-detection infrastructure,
not a susceptibility/screening baseline like Phases 4-7 -- it answers
"does imagery show something changed", not "is this place prone to
flooding".
"""

# JRC Global Surface Water 'occurrence' band: % of valid observations
# 1984-2021 where a pixel was classified as water. Threshold at/above
# which a pixel is treated as PERMANENT water (always wet). Provisional,
# commonly-used convention in surface-water literature, not independently
# validated here.
JRC_PERMANENT_WATER_OCCURRENCE_PCT = 80.0

# Occurrence threshold at/above which a pixel is treated as SEASONAL
# water (sometimes wet) but below the permanent threshold.
JRC_SEASONAL_WATER_OCCURRENCE_PCT = 5.0

JRC_ASSET = "JRC/GSW1_4/GlobalSurfaceWater"

# ── Sentinel-1 SAR change detection ──
# VV backscatter DROP (dB) between pre-event and event composites at/
# below which a pixel is flagged as a probable-new-inundation candidate.
# Smooth open water causes specular reflection away from the radar,
# producing a strong backscatter DROP for VV over previously non-water
# surfaces. Provisional threshold, not locally calibrated -- real SAR
# flood-mapping literature commonly uses -3dB to -6dB depending on land
# cover, incidence angle, and sensor mode; this is a single fixed value,
# a simplification.
S1_VV_DROP_THRESHOLD_DB = -3.0

S1_COLLECTION = "COPERNICUS/S1_GRD"
S1_INSTRUMENT_MODE = "IW"
S1_POLARIZATION = "VV"

# Minimum number of source images required in EACH window (pre-event,
# event) before a change result is trusted enough to report as
# "experimental" rather than "insufficient_evidence".
S1_MIN_IMAGES_PER_WINDOW = 1