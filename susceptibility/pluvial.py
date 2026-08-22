"""
Phase 4: pluvial susceptibility baseline. Reuses landcover_map_full and
full_waterway_dist_map that Phase 2's mosaic pass already computes for
free -- genuinely spatial for those two components. rainfall_climatology
and relative_elevation are AOI-WIDE SCALARS applied uniformly (per-pixel
DEM is Phase 5 scope) -- documented explicitly below, not hidden.
"""

import os
import numpy as np
from PIL import Image

from configs.pluvial_constants import (
    RAINFALL_MIN_MM_YEAR, RAINFALL_MAX_MM_YEAR,
    COMPONENT_WEIGHTS, COMPONENT_QUALITY,
    SUSCEPTIBILITY_CLASS_BREAKS,
)
from configs.applicability_constants import (
    IMPERVIOUS_CLASS_WEIGHTS, INFILTRATION_CLASS_WEIGHTS,
)


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in SUSCEPTIBILITY_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


def compute_pluvial_susceptibility(
    landcover_map: np.ndarray,
    categories: list,
    waterway_dist_map: np.ndarray,
    relative_elevation_score,
    rainfall_mean_annual_mm,
    unknown_index: int = 255,
) -> dict:
    H, W = landcover_map.shape
    cat_to_idx = {c: i for i, c in enumerate(categories)}

    impervious_px = np.zeros((H, W), dtype=np.float32)
    for cat, weight in IMPERVIOUS_CLASS_WEIGHTS.items():
        if cat in cat_to_idx:
            impervious_px[landcover_map == cat_to_idx[cat]] = weight

    infiltration_px = np.zeros((H, W), dtype=np.float32)
    for cat, weight in INFILTRATION_CLASS_WEIGHTS.items():
        if cat in cat_to_idx:
            infiltration_px[landcover_map == cat_to_idx[cat]] = weight
    infiltration_deficit_px = 1.0 - infiltration_px

    drainage_available = waterway_dist_map is not None
    drainage_px = waterway_dist_map if drainage_available else None

    rainfall_available = rainfall_mean_annual_mm is not None
    if rainfall_available:
        clamped = max(RAINFALL_MIN_MM_YEAR, min(RAINFALL_MAX_MM_YEAR, rainfall_mean_annual_mm))
        rainfall_factor = (clamped - RAINFALL_MIN_MM_YEAR) / (RAINFALL_MAX_MM_YEAR - RAINFALL_MIN_MM_YEAR)
    else:
        rainfall_factor = None

    elevation_available = relative_elevation_score is not None

    numerator = np.zeros((H, W), dtype=np.float64)
    denominator = 0.0
    components_used = []
    components_excluded = []

    w, q = COMPONENT_WEIGHTS["impervious"], COMPONENT_QUALITY["impervious"]
    numerator += w * q * impervious_px
    denominator += w * q
    components_used.append("impervious")

    w, q = COMPONENT_WEIGHTS["infiltration_deficit"], COMPONENT_QUALITY["infiltration_deficit"]
    numerator += w * q * infiltration_deficit_px
    denominator += w * q
    components_used.append("infiltration_deficit")

    if drainage_available:
        w, q = COMPONENT_WEIGHTS["drainage_distance"], COMPONENT_QUALITY["drainage_distance"]
        numerator += w * q * drainage_px
        denominator += w * q
        components_used.append("drainage_distance")
    else:
        components_excluded.append("drainage_distance (OSM waterways unavailable)")

    if rainfall_available:
        w, q = COMPONENT_WEIGHTS["rainfall_climatology"], COMPONENT_QUALITY["rainfall_climatology"]
        numerator += w * q * rainfall_factor
        denominator += w * q
        components_used.append("rainfall_climatology")
    else:
        components_excluded.append("rainfall_climatology (CHIRPS unavailable)")

    if elevation_available:
        w, q = COMPONENT_WEIGHTS["relative_elevation"], COMPONENT_QUALITY["relative_elevation"]
        numerator += w * q * relative_elevation_score
        denominator += w * q
        components_used.append("relative_elevation")
    else:
        components_excluded.append("relative_elevation (proxy unavailable)")

    if denominator == 0:
        return {"status": "insufficient_evidence",
                "reason": "No pluvial susceptibility components were available.",
                "susceptibility_map": None}

    susceptibility_map = np.clip((numerator / denominator).astype(np.float32), 0.0, 1.0)

    unknown_mask = landcover_map == unknown_index
    valid_mean = float(susceptibility_map[~unknown_mask].mean()) if (~unknown_mask).any() else None

    return {
        "status": "experimental",
        "susceptibility_map": susceptibility_map,
        "aoi_mean_score": round(valid_mean, 4) if valid_mean is not None else None,
        "aoi_mean_class": _classify(valid_mean),
        "components_used": components_used,
        "components_excluded": components_excluded,
        "method": "weighted_mean_fusion_provisional_weights",
        "validated": False,
        "limitations": [
            "Weights and quality-confidence values are provisional, NOT "
            "calibrated against any real flood outcome.",
            "rainfall_climatology and relative_elevation are AOI-WIDE "
            "SCALARS applied uniformly -- they shift the overall level "
            "of the map but contribute NO spatial pattern. Only "
            "land-cover (impervious/infiltration) and drainage distance "
            "vary spatially in this baseline.",
            "drainage_distance uses OSM waterway proximity as a rough "
            "proxy for drainage access, NOT real drainage capacity.",
            "relative_elevation_score is the AOI-relative p10/p90 proxy, "
            "NOT true HAND.",
            "This is a screening baseline, not a calibrated hydraulic "
            "model. Do not use for engineering or parcel-level decisions.",
        ],
    }


def save_pluvial_susceptibility_output(susceptibility_map, run_dir, filename="pluvial_susceptibility.png"):
    if susceptibility_map is None:
        return None
    arr_u8 = np.clip(susceptibility_map * 255.0, 0, 255).astype(np.uint8)
    path = os.path.join(run_dir, filename)
    Image.fromarray(arr_u8, mode="L").save(path)
    print(f"Saved pluvial susceptibility map: {path}")
    return filename