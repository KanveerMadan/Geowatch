import ee
from datetime import datetime


# Band configuration for Sentinel-2 SR
S2_BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]
S2_BAND_NAMES = ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"]
# SCL (Scene Classification Layer) class codes, per Sentinel-2 L2A spec.
# Used for observation-quality masking -- NOT a landcover class, kept
# entirely separate from the ML model's 7 categories.
SCL_CLASSES = {
    0: "no_data",
    1: "saturated_or_defective",
    2: "dark_area_pixels",
    3: "cloud_shadow",
    4: "vegetation",
    5: "bare_soil",
    6: "water",
    7: "cloud_low_probability",
    8: "cloud_medium_probability",
    9: "cloud_high_probability",
    10: "cirrus",
    11: "snow_or_ice",
}

SCL_VALID_CODES = {2, 4, 5, 6, 7, 11}
SCL_CLOUD_CODES = {8, 9, 10}
SCL_SHADOW_CODES = {3}
SCL_NODATA_CODES = {0, 1}

# Reduction scale for compute_observation_quality() ONLY. Deliberately
# coarser than the pipeline's 10m working scale, and applied to nothing
# else -- imagery export, tiling and inference are untouched.
#
# WHY: these four reductions produce AOI-WIDE AGGREGATE FRACTIONS (what
# share of observations were valid / cloud / shadow / no-data). They are
# scalars describing the whole AOI, not a per-pixel product, so they do
# not need -- and cannot benefit from -- 10m precision. Two facts make
# 10m actively wrong here:
#   1. SCL is natively 20m. Reducing at 10m OVERSAMPLES, reading 4x more
#      pixels than the band actually contains.
#   2. Cost scales with n_images x n_pixels. Over the 943 km2 Mumbai
#      extent with 164 images that is ~1.5 billion pixel-reads PER CALL,
#      x4 calls. Phase 12B stalled there twice: ~17 min with no progress,
#      then 84 min with zero CPU accrued on a single open socket to GEE.
#      Neither attempt ever reached the (already working) chunked export.
#
# MEASURED, not assumed (full numbers in PHASE_12B_VERDICT.md):
#   Mumbai 943 km2, 164 images, all four reductions:
#     scale= 10m -> did not return (stalled >84 min, killed)
#     scale= 60m -> 56.0s   valid=93.08 cloud=6.36 shadow=0.56 nodata=0
#     scale=100m -> 14.1s   valid=93.07 cloud=6.37 shadow=0.56 nodata=0
#   Dharavi 2.6 km2 (where 10m IS tractable, so 10m ground truth exists):
#     scale= 10m -> valid=98.35 cloud=0.00 shadow=1.65   <- baseline
#     scale= 20m -> valid=98.35 cloud=0.00 shadow=1.64   (delta  0.00 pp)
#     scale= 60m -> valid=98.37 cloud=0.00 shadow=1.63   (delta +0.02 pp)
#     scale=100m -> valid=98.41 cloud=0.00 shadow=1.59   (delta +0.06 pp)
#
# 60m chosen over 100m for margin and over 20m for cost: it is a spatial
# SUBSAMPLE of a 20m band (never an oversample), it returns in under a
# minute on the largest AOI this project runs, and it reproduces the 10m
# value to within 0.02 percentage points.
#
# GATE SENSITIVITY: valid_observation_pct feeds MIN_VALID_OBSERVATION_PCT
# (60.0) in configs/zonal_constants.py. A 0.02 pp shift cannot move a
# decision at that threshold -- the nearest observed value is 93.08.
# If this constant is ever changed, re-run the Dharavi comparison, because
# changing how the number is computed changes what the threshold means.
OBSERVATION_QUALITY_SCALE_M = 60

def mask_s2_clouds(image: ee.Image) -> ee.Image:
    """
    Mask clouds and no-data pixels using the Sentinel-2 SCL (Scene
    Classification Layer), applied per-pixel via updateMask -- cheap,
    no AOI-wide reduction, unlike compute_observation_quality's
    aggregate stats.

    Cloud (SCL_CLOUD_CODES) and no-data (SCL_NODATA_CODES) pixels are
    masked out -- not real reflectance. Cloud SHADOW pixels
    (SCL_SHADOW_CODES) are deliberately LEFT IN: shadow is real (dim)
    reflectance, not missing data. *(Updated 2026-09-25: the reason
    originally given here -- Decision 13's sixth endmember term for an
    unmixing solver -- is superseded; there is no solve. Under the shadow
    rule (Decision 11, locked 2026-09-24) partially shadowed pixels stay in
    the known-pixel denominator and the item 21 regressors learn robustness
    to them. SCL 3 is cloud shadow only and is NOT the full-shadow
    occlusion field; see surface_fractions/occlusion.py.)*

    PHASE 2: replaces QA60 with SCL. QA60 has been deprecated/
    zero-filled on newer processing baselines (C1), so this now shares
    its basis with compute_observation_quality() instead of disagreeing
    with it. Verified live (Dharavi AOI, 2026-01 to 2026-03,
    get_sentinel2_collection): SCL is a native band on every image in
    this collection, alongside QA60/QA10/QA20/MSK_CLDPRB/MSK_SNWPRB.
    """
    scl = image.select("SCL")
    is_cloud = scl.eq(list(SCL_CLOUD_CODES)[0])
    for code in list(SCL_CLOUD_CODES)[1:]:
        is_cloud = is_cloud.Or(scl.eq(code))
    is_nodata = scl.eq(list(SCL_NODATA_CODES)[0])
    for code in list(SCL_NODATA_CODES)[1:]:
        is_nodata = is_nodata.Or(scl.eq(code))
    mask = is_cloud.Or(is_nodata).Not()
    return image.updateMask(mask).divide(10000).select(S2_BANDS, S2_BAND_NAMES)


def get_sentinel2_collection(
    aoi: ee.Geometry,
    start_date: str,
    end_date: str,
    cloud_cover_threshold: int = 20,
) -> ee.ImageCollection:
    """
    Fetch a cloud-filtered Sentinel-2 SR image collection for a given AOI.
    Returns the RAW (unmasked, unmapped) collection -- SCL/QA60 intact --
    so callers can run quality analysis before any masking happens.
    """
    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(aoi)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_cover_threshold))
    )
    count = collection.size().getInfo()
    print(f"Found {count} Sentinel-2 images after cloud filtering.")
    return collection

def compute_observation_quality(collection: ee.ImageCollection, aoi: ee.Geometry) -> dict:
    """
    PHASE 1 NEW: compute per-AOI observation quality from SCL across the
    full collection, before compositing. Distinguishes valid observation
    from cloud, cloud shadow, and no-data -- previously indistinguishable
    from model uncertainty in unknown_pct.
    """
    def scl_fraction(codes):
        def per_image_mask(img):
            scl = img.select("SCL")
            in_class = scl.eq(codes[0])
            for c in codes[1:]:
                in_class = in_class.Or(scl.eq(c))
            return in_class.rename("mask")
        fraction_image = collection.map(per_image_mask).mean()
        result = fraction_image.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=aoi,
            scale=OBSERVATION_QUALITY_SCALE_M, maxPixels=1e8,
        ).getInfo()
        return result.get("mask")

    try:
        valid_frac = scl_fraction(list(SCL_VALID_CODES))
        cloud_frac = scl_fraction(list(SCL_CLOUD_CODES))
        shadow_frac = scl_fraction(list(SCL_SHADOW_CODES))
        nodata_frac = scl_fraction(list(SCL_NODATA_CODES))

        return {
            "status": "available",
            "method": "scl_fraction_across_collection",
            # Surfaced so the basis of these numbers is visible in
            # result.json rather than implicit. valid_observation_pct is a
            # hard-gate input (MIN_VALID_OBSERVATION_PCT); a reader must be
            # able to see at what scale it was reduced.
            "reduction_scale_m": OBSERVATION_QUALITY_SCALE_M,
            "valid_observation_pct": round((valid_frac or 0) * 100, 2),
            "cloud_pct": round((cloud_frac or 0) * 100, 2),
            "cloud_shadow_pct": round((shadow_frac or 0) * 100, 2),
            "no_data_pct": round((nodata_frac or 0) * 100, 2),
            "error": None,
        }
    except Exception as e:
        print(f"Observation quality computation failed: {e}")
        return {
            "status": "unavailable",
            "method": "scl_fraction_across_collection",
            "valid_observation_pct": None,
            "cloud_pct": None,
            "cloud_shadow_pct": None,
            "no_data_pct": None,
            "error": str(e),
        }


def get_sentinel2_median_composite(
    aoi: ee.Geometry,
    start_date: str,
    end_date: str,
    cloud_cover_threshold: int = 20,
) -> dict:
    """
    PHASE 1 RENAME: formerly get_best_image() -- misleading name, it
    never selected a single least-cloudy image. Returns a median
    composite PLUS full provenance and observation-quality metadata.

    PHASE 2: the composite's masking (via mask_s2_clouds) now uses SCL
    rather than QA60, and deliberately preserves cloud-shadow pixels --
    see mask_s2_clouds()'s docstring for why.

    Returns:
        dict with keys: image, provenance, observation_quality
    """
    collection = get_sentinel2_collection(aoi, start_date, end_date, cloud_cover_threshold)
    count = collection.size().getInfo()

    if count == 0:
        raise ValueError(
            f"No cloud-free images found for given AOI between {start_date} and {end_date}. "
            "Try widening the date range or increasing cloud_cover_threshold."
        )

    quality = compute_observation_quality(collection, aoi)

    masked_collection = collection.map(mask_s2_clouds)
    image = masked_collection.median().clip(aoi)
    print(f"Median composite generated from {count} source images.")

    return {
        "image": image,
        "provenance": {
            "dataset": "COPERNICUS/S2_SR_HARMONIZED",
            "composite_method": "median",
            "requested_period": {"start": start_date, "end": end_date},
            "source_image_count": count,
        },
        "observation_quality": quality,
    }

def get_best_image(aoi, start_date, end_date, cloud_cover_threshold=20):
    """DEPRECATED (Phase 1): renamed to get_sentinel2_median_composite(),
    which returns a dict with provenance/quality info, not a bare image."""
    print("DEPRECATION WARNING: get_best_image() is renamed to "
          "get_sentinel2_median_composite(). Update the caller.")
    bundle = get_sentinel2_median_composite(aoi, start_date, end_date, cloud_cover_threshold)
    return bundle["image"]

def get_latest_image(
    aoi: ee.Geometry,
    lookback_days: int = 90,
    cloud_cover_threshold: int = 20,
) -> ee.Image:
    """
    Fetch the most recent cloud-free Sentinel-2 composite automatically.
    NOTE: returns just the image for backward compat. Callers wanting
    quality data should call get_sentinel2_median_composite() directly
    with an explicit date range.
    """
    import datetime
    end_date = datetime.date.today().isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=lookback_days)).isoformat()
    print(f"Latest imagery mode: {start_date} → {end_date} ({lookback_days}d lookback)")
    bundle = get_sentinel2_median_composite(aoi, start_date, end_date, cloud_cover_threshold)
    return bundle["image"]

def aoi_from_bbox(west: float, south: float, east: float, north: float) -> ee.Geometry:
    """
    Create an AOI from bounding box coordinates.
    Args: west, south, east, north (decimal degrees)
    """
    return ee.Geometry.Rectangle([west, south, east, north])


def aoi_from_coords(coords: list) -> ee.Geometry:
    """
    Create an AOI from a list of [lon, lat] coordinate pairs.
    coords: [[lon1, lat1], [lon2, lat2], ...]
    """
    return ee.Geometry.Polygon(coords)