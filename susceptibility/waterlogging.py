"""
Persistent-waterlogging susceptibility, per pixel (item 26 Phase 1a; was an
AOI-wide scalar, Phase 7). STATIC / SCREENING SLICE ONLY. Method fixed in
experiments/flood_validation/PREREGISTRATION_ROUND2.md before any run.

Components on the hydrology grid, each 0-1:

    low_relief            1 - HAND / WATERLOGGING_HAND_NORMALIZATION_MAX_M
    impervious            built area fraction / WATERLOGGING_IMPERVIOUS_NORMALIZATION_MAX_PCT
                          (a declared surface, susceptibility/inputs.py: Open
                          Buildings built area, placeholder -- not the
                          retired 7-class map's hydrological_surfaces)
    flatness              1 - slope / WATERLOGGING_SLOPE_NORMALIZATION_MAX_DEG
    rainfall_climatology  CHIRPS mean annual total
                          / FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM

IMPORTANT: the HAND here is the SAME MERIT Hydro HAND that
susceptibility/fluvial.py reads, interpreted DIFFERENTLY. Fluvial reads low
HAND as "close to a channel that could overflow" (a river-connectivity
concern). Waterlogging reads it as "low-relief terrain with nowhere for water
to drain to" (a poor-drainage concern), independent of whether a river is
near. Both readings can be true at once; they are two mechanisms sharing one
input.

Weighted mean (WATERLOGGING_WEIGHTS); weights change only on the round-2
tuning events. Ceilings provisional. An output is no more validated than its
weakest input.
"""
import numpy as np

from susceptibility.hydro_rasters import clip01, layer, map_summary, weighted_map
from susceptibility.inputs import check_surface, mean_pct, provenance, weakest
from configs.waterlogging_constants import (
    WATERLOGGING_HAND_NORMALIZATION_MAX_M,
    WATERLOGGING_IMPERVIOUS_NORMALIZATION_MAX_PCT,
    WATERLOGGING_CLASS_BREAKS,
    WATERLOGGING_SLOPE_NORMALIZATION_MAX_DEG,
    WATERLOGGING_WEIGHTS,
)
from configs.flash_flood_constants import FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in WATERLOGGING_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


from perception.applicability_gate import gated

# The module's own label, before its weakest input caps it.
VALIDATION_STATUS = "experimental"


def components(rasters: dict, impervious: dict = None) -> dict:
    """{name: 0-1 array or None}. Pure; the harness tunes weights on these.
    `impervious` must be a declared surface on the rasters' grid."""
    hand, slope = layer(rasters, "hand_m"), layer(rasters, "slope_deg")
    rain = layer(rasters, "rain_annual_mm")
    imp = None
    if impervious is not None:
        r = np.asarray(check_surface(impervious, "impervious")["raster"], dtype=np.float64)
        if rasters and r.shape != tuple(rasters["shape"]):
            raise ValueError(f"impervious {r.shape} is not on the rasters' grid {rasters['shape']}")
        imp = r if np.isfinite(r).any() else None
    return {
        "low_relief": None if hand is None
        else clip01(1.0 - hand / WATERLOGGING_HAND_NORMALIZATION_MAX_M),
        "impervious": None if imp is None
        else clip01(imp * 100.0 / WATERLOGGING_IMPERVIOUS_NORMALIZATION_MAX_PCT),
        "flatness": None if slope is None
        else clip01(1.0 - slope / WATERLOGGING_SLOPE_NORMALIZATION_MAX_DEG),
        "rainfall_climatology": None if rain is None
        else clip01(rain / FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM),
    }


def combine(comps: dict, weights: dict = None):
    return weighted_map(comps, WATERLOGGING_WEIGHTS if weights is None else weights)


@gated("waterlogging")
def compute_waterlogging_susceptibility(rasters: dict = None, impervious: dict = None,
                                         weights: dict = None) -> dict:
    """
    Args:
        rasters: susceptibility.hydro_rasters.fetch_hydro_rasters() output.
        impervious: a declared surface input (susceptibility/inputs.py) on the
            same grid; its per-cell built fraction is the imperviousness
            component.
        weights: override WATERLOGGING_WEIGHTS (the validation harness only).

    Returns:
        dict matching the master schema's susceptibility.waterlogging shape,
        plus `susceptibility_map` (per-pixel, NaN = no data).
    """
    w = WATERLOGGING_WEIGHTS if weights is None else weights
    comps = components(rasters, impervious) if (rasters or impervious is not None) else {}
    spatial = [k for k in ("low_relief", "impervious", "flatness")
               if comps.get(k) is not None and w.get(k, 0) > 0]
    if not spatial:
        return {
            "status": "insufficient_evidence",
            "reason": "No per-pixel HAND, slope or impervious surface is available.",
            "validation_status": "placeholder",
        }
    used = [k for k, c in comps.items() if c is not None and w.get(k, 0) > 0]
    imp_used = "impervious" in used
    m = combine(comps, w)
    inputs = {k: provenance(v) for k, v in (rasters or {}).get("layers", {}).items()
              if k in ("hand_m", "slope_deg", "rain_annual_mm")}
    if impervious is not None:
        inputs["impervious"] = provenance(impervious)
    return {
        "status": "experimental",
        "validation_status": weakest(VALIDATION_STATUS,
                                     *([impervious["validation_status"]] if imp_used else [])),
        "inputs": inputs,
        **map_summary(m, _classify),
        "susceptibility_map": m,
        "impervious_fraction_pct": mean_pct(impervious) if impervious is not None else None,
        "components_used": used,
        "components_excluded": [f"{k} ({'weight 0' if comps.get(k) is not None else 'unavailable'})"
                                for k in comps if k not in used],
        "weights": dict(w),
        "method": "relief_imperviousness_flatness_rainfall_per_pixel_weighted",
        "validated": False,
        "spatial": True,
        "limitations": [
            "Reuses fluvial susceptibility's MERIT HAND under a DIFFERENT "
            "physical interpretation (low-relief/poor-drainage, not "
            "river-overflow-proximity) -- see module docstring.",
            "Does not account for actual drainage infrastructure capacity, "
            "groundwater level, or soil permeability.",
            "Rainfall component is a coarse annual-mean climatology (CHIRPS, "
            "0.05 deg), near-constant across a city AOI.",
            "All normalization ceilings are provisional, not calibrated "
            "against real waterlogging/persistent-inundation outcomes.",
        ],
    }
