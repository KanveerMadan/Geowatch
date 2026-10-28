"""
Swappable surface inputs for the flood modules (build item 26).

The 7-class land-cover map is retired (08_STATE.md §RETIRED): no
susceptibility module reads it. Every spatial input is a dict that declares
where it came from, so a producer is swapped by building a different dict:

    {"raster": ndarray in [0, 1] (NaN = unobserved), "source": str,
     "method": str, "validation_status": "validated" | "experimental" | "placeholder"}

Producers here, all on the hydrology grid (HYDROLOGY_PIXEL_M, the layer's UTM CRS):

    impervious    Open Buildings built AREA fraction: the footprint union's area
                  per cell. Never a count -- Open Buildings fragments formal
                  houses into several polygons (item 23, the Chandigarh 50 m^2
                  median), so a count would inflate exactly where houses split.
                  `placeholder`: the final impervious input is item 21's.
    infiltration  the Sentinel-2 NDVI vegetation stand-in from Lane B
                  (vector/fractions.py). `placeholder`: item 21's regression
                  is the decided producer and is not built.
"""
from __future__ import annotations

import warnings

import numpy as np

from configs.pluvial_constants import HYDROLOGY_PIXEL_M

VALIDATION_ORDER = ("placeholder", "experimental", "validated")
SURFACE_KEYS = ("raster", "source", "method", "validation_status")


def surface(raster, source: str, method: str, validation_status: str) -> dict:
    if validation_status not in VALIDATION_ORDER:
        raise ValueError(f"validation_status {validation_status!r} not in {VALIDATION_ORDER}")
    return {"raster": np.asarray(raster, dtype=np.float32), "source": source,
            "method": method, "validation_status": validation_status}


def check_surface(s, name: str) -> dict:
    """Trust boundary: a consumer accepts only a surface that declares its source."""
    missing = [k for k in SURFACE_KEYS if not isinstance(s, dict) or k not in s]
    if missing:
        raise ValueError(f"{name}: not a declared surface input, missing {missing}")
    return s


def provenance(s: dict) -> dict:
    return {k: s[k] for k in ("source", "method", "validation_status")}


def weakest(*statuses: str) -> str:
    """An output is no more validated than its least-validated input."""
    return min(statuses, key=VALIDATION_ORDER.index)


def mean_pct(s: dict | None):
    """AOI share of a surface in percent, over observed cells; None if none."""
    if s is None:
        return None
    r = s["raster"]
    return round(float(np.nanmean(r)) * 100.0, 2) if np.isfinite(r).any() else None


def block_nanmean(a: np.ndarray, k: int) -> np.ndarray:
    """Mean of each k x k block, ignoring NaN; all-NaN blocks stay NaN."""
    H, W = a.shape[0] // k, a.shape[1] // k
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(a[:H * k, :W * k].reshape(H, k, W, k), axis=(1, 3)).astype(np.float32)


def hydrology_grid(layer):
    from vector.fractions import grid_for
    return grid_for(layer, HYDROLOGY_PIXEL_M)


def impervious_built_area(layer, transform, shape) -> dict:
    """Footprint union area per cell. Rasterising every footprint into one
    hit mask (2 m sub-cells at 30 m) counts overlapping or fragmented
    polygons once, by area."""
    from vector.fractions import built_raster
    sub = max(1, int(round(abs(transform.a) / 2.0)))
    return surface(built_raster(layer, transform, shape, supersample=sub),
                   source=f"{layer.footprint_source} footprints, item 19 layer {layer.layer_id}",
                   method="footprint_union_area_fraction",
                   validation_status="placeholder")


def infiltration_vegetation(vegetation) -> dict:
    from vector.fractions import PRODUCER, PROXY_METHOD
    return surface(vegetation, source=PRODUCER["vegetation"],
                   method=PROXY_METHOD["vegetation"], validation_status="placeholder")


def hydrology_surfaces(layer, start: str, end: str) -> dict:
    """impervious and infiltration for `layer` on its hydrology grid.
    Vegetation is classified on an aligned 10 m grid, then averaged to the
    hydrology cell, so a cell's value is the share of its area over the
    NDVI threshold. Needs Earth Engine; raises on its errors."""
    from rasterio.transform import Affine
    from vector.fractions import PIXEL_M, classify_indices, s2_index_composite
    transform, (H, W) = hydrology_grid(layer)
    k = int(round(HYDROLOGY_PIXEL_M / PIXEL_M))
    comp = s2_index_composite(layer, start, end,
                              grid=(transform * Affine.scale(1.0 / k), (H * k, W * k)))
    veg = classify_indices(comp["ndvi"], comp["mndwi"], comp["valid_obs"])["vegetation"]
    return layer.stamp({
        "status": "available", "validation_status": "placeholder",
        "transform": transform, "shape": (H, W),
        "crs": layer.crs.to_string(), "window": comp["window"],
        "impervious": impervious_built_area(layer, transform, (H, W)),
        "infiltration": infiltration_vegetation(block_nanmean(veg, k)),
    })


def build_flood_inputs(name: str, bbox, start: str, end: str) -> dict:
    """Load item 19's layer for the AOI and build every flood input from it."""
    from vector.roads import load_road_layer
    return hydrology_surfaces(load_road_layer(name, bbox), start, end)


def to_grid(arr, bbox, inputs: dict | None):
    """Reproject a raster on the legacy pipeline's EPSG:4326 bbox grid onto
    the hydrology grid (`inputs` from build_flood_inputs). With no hydrology
    grid the array is returned as-is, so every input still shares one grid."""
    if arr is None or inputs is None:
        return arr
    from rasterio.transform import from_bounds
    from rasterio.warp import Resampling, reproject
    out = np.full(inputs["shape"], np.nan, dtype=np.float32)
    reproject(np.asarray(arr, dtype=np.float32), out,
              src_transform=from_bounds(*bbox, arr.shape[1], arr.shape[0]), src_crs="EPSG:4326",
              dst_transform=inputs["transform"], dst_crs=inputs["crs"],
              src_nodata=np.nan, dst_nodata=np.nan, resampling=Resampling.average)
    return out
