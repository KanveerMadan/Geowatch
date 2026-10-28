"""
Phase 4: pluvial susceptibility baseline. Item 26: no longer reads the
retired 7-class land-cover map. Imperviousness, infiltration, road
conduits and DEM hydrology (susceptibility/terrain.py) arrive as declared
surface inputs (susceptibility/inputs.py) -- swappable, each naming
its source and validation status. Drainage distance is OSM waterway
proximity. rainfall_climatology and relative_elevation are AOI-WIDE SCALARS
applied uniformly -- documented explicitly below, not hidden.

Every raster input must share one grid (the hydrology grid in the pipeline).
NaN marks an unobserved cell; it stays NaN in the map and is left out of the
AOI mean.
"""

import os
import numpy as np
from PIL import Image

from configs.pluvial_constants import (
    RAINFALL_MIN_MM_YEAR, RAINFALL_MAX_MM_YEAR,
    COMPONENT_WEIGHTS, COMPONENT_QUALITY,
    SUSCEPTIBILITY_CLASS_BREAKS,
)
from susceptibility.inputs import check_surface, provenance, weakest


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in SUSCEPTIBILITY_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


from perception.applicability_gate import gated


@gated("pluvial")
def compute_pluvial_susceptibility(
    impervious: dict = None,
    infiltration: dict = None,
    waterway_dist_map: np.ndarray = None,
    relative_elevation_score=None,
    rainfall_mean_annual_mm=None,
    conduits: dict = None,
    terrain: dict = None,
) -> dict:
    inputs = {}
    rasters = []           # (component, array)
    components_excluded = []

    if impervious is not None:
        inputs["impervious"] = provenance(check_surface(impervious, "impervious"))
        rasters.append(("impervious", impervious["raster"]))
    else:
        components_excluded.append("impervious (no surface input)")

    if infiltration is not None:
        inputs["infiltration"] = provenance(check_surface(infiltration, "infiltration"))
        rasters.append(("infiltration_deficit", 1.0 - infiltration["raster"]))
    else:
        components_excluded.append("infiltration_deficit (no surface input)")

    if conduits is not None:
        inputs["conduits"] = provenance(check_surface(conduits, "conduits"))
        rasters.append(("road_conduit", conduits["raster"]))
    else:
        components_excluded.append("road_conduit (no road layer)")

    for name, s in (terrain or {}).items():
        inputs[name] = provenance(check_surface(s, name))
        rasters.append((name, s["raster"]))
    if not terrain:
        components_excluded.append("terrain (no DEM)")

    if waterway_dist_map is not None:
        rasters.append(("drainage_distance", waterway_dist_map))
    else:
        components_excluded.append("drainage_distance (OSM waterways unavailable)")

    if not rasters:
        return {"status": "insufficient_evidence",
                "reason": "No spatial pluvial input was available.",
                "susceptibility_map": None, "validation_status": "placeholder"}

    shapes = {name: np.shape(a) for name, a in rasters}
    if len(set(shapes.values())) != 1:
        raise ValueError(f"pluvial inputs are not on one grid: {shapes}")
    shape = rasters[0][1].shape

    scalars = []
    if rainfall_mean_annual_mm is not None:
        clamped = max(RAINFALL_MIN_MM_YEAR, min(RAINFALL_MAX_MM_YEAR, rainfall_mean_annual_mm))
        scalars.append(("rainfall_climatology",
                        (clamped - RAINFALL_MIN_MM_YEAR) / (RAINFALL_MAX_MM_YEAR - RAINFALL_MIN_MM_YEAR)))
    else:
        components_excluded.append("rainfall_climatology (CHIRPS unavailable)")

    if relative_elevation_score is not None:
        scalars.append(("relative_elevation", relative_elevation_score))
    else:
        components_excluded.append("relative_elevation (proxy unavailable)")

    numerator = np.zeros(shape, dtype=np.float64)
    denominator = 0.0
    components_used = []
    for name, value in rasters + scalars:
        w, q = COMPONENT_WEIGHTS[name], COMPONENT_QUALITY[name]
        numerator += w * q * np.asarray(value, dtype=np.float64)
        denominator += w * q
        components_used.append(name)

    susceptibility_map = np.clip((numerator / denominator).astype(np.float32), 0.0, 1.0)

    observed = np.isfinite(susceptibility_map)
    valid_mean = float(susceptibility_map[observed].mean()) if observed.any() else None

    return {
        "status": "experimental",
        "validation_status": weakest("experimental",
                                     *(i["validation_status"] for i in inputs.values())),
        "inputs": inputs,
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
            "Imperviousness is Open Buildings built AREA and infiltration is "
            "a Sentinel-2 NDVI stand-in -- both placeholders until item 21's "
            "fractions exist. Built area omits sealed ground that is not a "
            "roof (roads, paving).",
            "rainfall_climatology and relative_elevation are AOI-WIDE "
            "SCALARS applied uniformly -- they shift the overall level "
            "of the map but contribute NO spatial pattern.",
            "road_conduit is OSM road space at class-default widths, not "
            "measured widths; it scores where runoff concentrates on sealed "
            "road surface, not drain capacity.",
            "Terrain inputs come from FABDEM at 30 m with metre-scale "
            "vertical error; D8 runs on the unfilled DEM, the grid edge "
            "stands in for an outlet, and flat cells count as pits.",
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
    # unobserved (NaN) cells render black, same as score 0 -- a preview, not data
    arr_u8 = np.clip(np.nan_to_num(susceptibility_map) * 255.0, 0, 255).astype(np.uint8)
    path = os.path.join(run_dir, filename)
    Image.fromarray(arr_u8, mode="L").save(path)
    print(f"Saved pluvial susceptibility map: {path}")
    return filename