"""
Fraction rasters for items 22 and 25: built, vegetation, water ONLY.

    built       footprint coverage of each 10 m pixel, rasterised from the item
                19 layer's footprints (supersampled). This is the architecture's
                own definition of `built` (02_ARCHITECTURE.md §3: "taken from
                vector footprints, not measured spectrally").
    vegetation  PROXY. Share of the pixel classified vegetation by an index
    water       threshold on a Sentinel-2 median composite. These are NOT item
                21's fractions: item 21's spectral regression is the decided
                producer and is not built. A pixel is 0 or 1, so a unit's value
                is the share of its area over the threshold, not a sub-pixel
                fraction. Every output says so (`method`, `producer`).

impervious_total (and paved, bare, ...) are never produced here. Consumers
emit them as status "not_computed", never 0.

Thresholds fixed 2026-10-27, before any composite was examined:
    water       MNDWI = (Green - SWIR1) / (Green + SWIR1) > 0     (Xu 2006,
                Int. J. Remote Sensing 27:3025, the index's own zero threshold)
    vegetation  NDVI = (NIR - Red) / (NIR + Red) > 0.3, and not water
    validity    a pixel is observed if it has >= MIN_VALID_OBS cloud-free
                (SCL-masked) observations in the composite window
"""
from __future__ import annotations

import numpy as np

WATER_MNDWI_MIN = 0.0
VEGETATION_NDVI_MIN = 0.3
MIN_VALID_OBS = 3
PIXEL_M = 10.0

FRACTIONS = ("built", "vegetation", "water")
NOT_COMPUTED = ("impervious_total",)

# Per-fraction validation label (decision 2026-10-28, 08_STATE.md).
# vegetation and water are index-threshold stand-ins for item 21's regression:
# placeholders. built is the architecture's own method, not yet validated.
# Anything not computed is a placeholder by definition.
FRACTION_VALIDATION_STATUS = {
    "built": "experimental",
    "vegetation": "placeholder",
    "water": "placeholder",
    "impervious_total": "placeholder",
}

PROXY_METHOD = {
    "built": "footprint_coverage_rasterised",
    "vegetation": f"ndvi_threshold_proxy(>{VEGETATION_NDVI_MIN}, not water)",
    "water": f"mndwi_threshold_proxy(>{WATER_MNDWI_MIN})",
}
PRODUCER = {
    "built": "vector footprints (item 19 layer)",
    "vegetation": "PROXY: Sentinel-2 index threshold. Item 21 regression not built",
    "water": "PROXY: Sentinel-2 index threshold. Item 21 regression not built",
}


def grid_for(layer, pixel_m: float = PIXEL_M):
    """A `pixel_m` grid (10 m by default) snapped to multiples of `pixel_m`,
    covering the layer's AOI, in the layer's UTM CRS. Returns (transform, (rows, cols))."""
    from rasterio.transform import from_origin
    minx, miny, maxx, maxy = layer.aoi.bounds
    x0 = np.floor(minx / pixel_m) * pixel_m
    y1 = np.ceil(maxy / pixel_m) * pixel_m
    cols = int(np.ceil((maxx - x0) / pixel_m))
    rows = int(np.ceil((y1 - miny) / pixel_m))
    return from_origin(x0, y1, pixel_m, pixel_m), (rows, cols)


def built_raster(layer, transform, shape, supersample: int = 5) -> np.ndarray:
    """Footprint coverage per 10 m pixel, in [0, 1]."""
    from rasterio.features import rasterize
    from rasterio.transform import Affine
    from shapely.geometry import mapping
    H, W = shape
    if not layer.footprints:
        return np.zeros(shape, dtype=np.float32)
    fine = transform * Affine.scale(1.0 / supersample)
    hit = rasterize(((mapping(p), 1) for p in layer.footprints),
                    out_shape=(H * supersample, W * supersample), transform=fine,
                    fill=0, dtype="uint8")
    return hit.reshape(H, supersample, W, supersample).mean(axis=(1, 3)).astype(np.float32)


def classify_indices(ndvi: np.ndarray, mndwi: np.ndarray, valid_obs: np.ndarray) -> dict:
    """Pure: index arrays -> vegetation and water proxy rasters plus the
    validity mask. Unobserved pixels are NaN in both, never 0."""
    observed = (valid_obs >= MIN_VALID_OBS) & np.isfinite(ndvi) & np.isfinite(mndwi)
    water = np.where(observed, (mndwi > WATER_MNDWI_MIN).astype(np.float32), np.nan)
    veg = np.where(observed, ((ndvi > VEGETATION_NDVI_MIN) & ~(mndwi > WATER_MNDWI_MIN))
                   .astype(np.float32), np.nan)
    return {"vegetation": veg, "water": water, "observed": observed}


def s2_index_composite(layer, start: str, end: str, *, cloud_cover_threshold: int = 60,
                       collection_filter=None, grid=None):
    """Median NDVI and MNDWI, plus the per-pixel count of cloud-free
    observations, on `grid` ((transform, (rows, cols)); default
    grid_for(layer)), from Earth Engine.

    `collection_filter`, if given, is applied to the image collection before
    compositing. Item 25 uses it to build split-half composites for its noise
    estimate. Raises on any Earth Engine error (items 54/55)."""
    import ee
    from ingestion.gee_client import initialize_gee
    from ingestion.sentinel2 import (compute_observation_quality, get_sentinel2_collection,
                                     mask_s2_clouds)
    initialize_gee()
    transform, (H, W) = grid or grid_for(layer)
    aoi_ll = ee.Geometry.Rectangle(list(layer.bbox))
    col = get_sentinel2_collection(aoi_ll, start, end, cloud_cover_threshold)
    if collection_filter is not None:
        col = collection_filter(col)
    n_images = col.size().getInfo()
    if n_images == 0:
        from ingestion.errors import NoDataError
        raise NoDataError(f"no Sentinel-2 images for {layer.name} {start}..{end}")
    masked = col.map(mask_s2_clouds)
    ndvi = masked.map(lambda i: i.normalizedDifference(["NIR", "Red"]).rename("ndvi")).median()
    mndwi = masked.map(lambda i: i.normalizedDifference(["Green", "SWIR1"]).rename("mndwi")).median()
    count = masked.select("Red").count().rename("valid_obs")
    img = ndvi.addBands(mndwi).addBands(count).unmask(-9999).toFloat()
    grid = {"dimensions": {"width": W, "height": H},
            "affineTransform": {"scaleX": transform.a, "shearX": 0, "translateX": transform.c,
                                "shearY": 0, "scaleY": transform.e, "translateY": transform.f},
            "crsCode": layer.crs.to_string()}
    arr = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY", "grid": grid})
    nd = lambda b: np.where(arr[b] == -9999, np.nan, arr[b]).astype(np.float32)
    quality = compute_observation_quality(col, aoi_ll)
    return {"ndvi": nd("ndvi"), "mndwi": nd("mndwi"),
            "valid_obs": np.where(arr["valid_obs"] == -9999, 0, arr["valid_obs"]).astype(np.int32),
            "transform": transform, "shape": (H, W), "window": {"start": start, "end": end},
            "source_image_count": int(n_images), "observation_quality": quality}


def fraction_rasters(layer, composite: dict) -> dict:
    """The three fraction rasters on the composite's grid, with provenance."""
    cls = classify_indices(composite["ndvi"], composite["mndwi"], composite["valid_obs"])
    built = built_raster(layer, composite["transform"], composite["shape"])
    return layer.stamp({
        "rasters": {"built": built, "vegetation": cls["vegetation"], "water": cls["water"]},
        "observed": {"built": np.full(built.shape, layer.footprint_source != "none"),
                     "vegetation": cls["observed"], "water": cls["observed"]},
        "transform": composite["transform"], "shape": composite["shape"],
        "method": dict(PROXY_METHOD), "producer": dict(PRODUCER),
        "fraction_validation_status": dict(FRACTION_VALIDATION_STATUS),
        "window": composite.get("window"),
        "source_image_count": composite.get("source_image_count"),
        "observation_quality": composite.get("observation_quality"),
    })
