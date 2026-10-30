"""
Pluvial susceptibility (flood taxonomy M2), flood round 4: depression
("bluespot") detection with fill-and-spill. Method fixed in
experiments/flood_validation/PREREGISTRATION_ROUND4.md before it was built.
The round-1 weighted-mean method is retired
(susceptibility/retired_methods/pluvial_round1.py).

For each hollow in the DEM (susceptibility/bluespots.py), the design storm's
runoff from its catchment -- rainfall x contributing area x a runoff
coefficient from the impervious share -- is set against its storage; what
overflows spills to the next hollow downstream. Components, each 0-1:

    ponding      min(1, ponding depth / PLUVIAL_PONDING_DEPTH_MAX_M); 0 outside
                 bluespots
    runoff_path  log(1 + runoff-weighted upstream cells) / log(1 + cells in
                 the grid), along the same routing

Score = weighted mean (PLUVIAL_WEIGHTS). Runoff coefficient C = C_perv +
(C_imp - C_perv) x imp, imp = min(1, built + road): the CURRENT STAND-INS
(Open Buildings / OSM footprint area, `placeholder`; item 19 road space,
`experimental`). Pluvial must be re-tested when item 21's impervious_total
exists. The design storm is one CHIRPS value per 0.05 deg: it decides which
hollows overflow, not a per-cell weighting.
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image

from configs.pluvial_constants import (
    HYDROLOGY_PIXEL_M, PLUVIAL_BLUESPOT_MIN_DEPTH_M, PLUVIAL_PONDING_DEPTH_MAX_M,
    PLUVIAL_RUNOFF_C_IMPERVIOUS, PLUVIAL_RUNOFF_C_PERVIOUS, PLUVIAL_WEIGHTS,
    SUSCEPTIBILITY_CLASS_BREAKS,
)
from susceptibility.bluespots import fill_and_spill
from susceptibility.hydro_rasters import clip01, layer, map_summary, weighted_map
from susceptibility.inputs import check_surface, provenance, weakest

# Flood round 4 has not been run on this method yet: a real method, not
# validated (C69's meaning). Rounds 1-3's verdicts were on the retired method.
VALIDATION_STATUS = "experimental"
METHOD = "bluespot_fill_and_spill"
CEILINGS = {"ponding_depth_m": PLUVIAL_PONDING_DEPTH_MAX_M,
            "bluespot_min_depth_m": PLUVIAL_BLUESPOT_MIN_DEPTH_M,
            "runoff_c_impervious": PLUVIAL_RUNOFF_C_IMPERVIOUS}
DESIGN_STORM_LAYER = "rain_design_day_mm"


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in SUSCEPTIBILITY_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


def impervious_share(impervious: dict | None, conduits: dict | None, shape) -> np.ndarray:
    """min(1, built + road) per cell; an absent surface counts 0, a NaN cell
    of a present one counts 0 where the other is observed."""
    parts = [np.asarray(s["raster"], dtype=np.float64) for s in (impervious, conduits)
             if s is not None]
    if not parts:
        return np.zeros(shape)
    total = sum(np.nan_to_num(p) for p in parts)
    return np.clip(total, 0.0, 1.0)


def components(dem: np.ndarray, imp: np.ndarray, design_mm: float, c_perv: float,
               pixel_m: float = HYDROLOGY_PIXEL_M) -> dict:
    """{name: 0-1 array} plus the fill-and-spill record. Pure; the harness
    tunes on these."""
    c = c_perv + (PLUVIAL_RUNOFF_C_IMPERVIOUS - c_perv) * np.clip(imp, 0.0, 1.0)
    fs = fill_and_spill(dem, c, design_mm, pixel_m, PLUVIAL_BLUESPOT_MIN_DEPTH_M)
    n = max(fs["domain_cells"], 2)
    return {"ponding": clip01(fs["ponding_depth_m"] / PLUVIAL_PONDING_DEPTH_MAX_M),
            "runoff_path": clip01(np.log1p(fs["upstream_runoff_cells"]) / np.log1p(n)),
            "_fill_and_spill": fs}


def combine(comps: dict, weights: dict = None):
    w = PLUVIAL_WEIGHTS if weights is None else weights
    return weighted_map({k: v for k, v in comps.items() if not k.startswith("_")}, w)


from perception.applicability_gate import gated


@gated("pluvial")
def compute_pluvial_susceptibility(dem: dict = None, impervious: dict = None,
                                   conduits: dict = None, rasters: dict = None,
                                   design_storm_mm: float = None, weights: dict = None,
                                   c_perv: float = None) -> dict:
    """
    Args:
        dem: declared surface of bare-earth elevation (m) on the hydrology grid.
        impervious, conduits: declared surfaces on the same grid (built area
            and road space; the stand-ins).
        rasters: hydro_rasters output on the same grid; its
            rain_design_day_mm is the design storm unless design_storm_mm is given.
        weights, c_perv: override PLUVIAL_WEIGHTS / C_perv (the harness only).
    """
    w = dict(PLUVIAL_WEIGHTS if weights is None else weights)
    cp = PLUVIAL_RUNOFF_C_PERVIOUS if c_perv is None else c_perv
    if dem is None:
        return {"status": "insufficient_evidence", "validation_status": VALIDATION_STATUS,
                "reason": "No DEM: bluespots cannot be found."}
    z = np.asarray(check_surface(dem, "dem")["raster"], dtype=np.float64)
    if not np.isfinite(z).any():
        return {"status": "insufficient_evidence", "validation_status": VALIDATION_STATUS,
                "reason": "The DEM has no observed cell."}
    inputs = {"dem": provenance(dem)}
    for name, s in (("impervious", impervious), ("conduits", conduits)):
        if s is not None:
            if np.shape(s["raster"]) != z.shape:
                raise ValueError(f"pluvial {name} {np.shape(s['raster'])} is not on the "
                                 f"DEM's grid {z.shape}")
            inputs[name] = provenance(check_surface(s, name))
    storm, storm_src = design_storm_mm, "given"
    if storm is None:
        r = layer(rasters, DESIGN_STORM_LAYER)
        if r is not None and np.isfinite(r).any():
            storm = float(np.nanmean(r))
            storm_src = rasters["layers"][DESIGN_STORM_LAYER]
            inputs[DESIGN_STORM_LAYER] = provenance(storm_src)
    if storm is None:
        why = (rasters or {}).get("errors", {}).get(DESIGN_STORM_LAYER, "not provided")
        return {"status": "insufficient_evidence", "validation_status": VALIDATION_STATUS,
                "reason": f"No design storm (CHIRPS annual-maximum day): {why}"}
    imp = impervious_share(impervious, conduits, z.shape)
    comps = components(z, imp, storm, cp)
    fs = comps["_fill_and_spill"]
    m = combine(comps, w)
    excluded = [f"{k} (no surface input; counted 0)" for k, s in
                (("impervious", impervious), ("conduits", conduits)) if s is None]
    return {
        "status": "experimental",
        "validation_status": weakest(VALIDATION_STATUS,
                                     *(i["validation_status"] for i in inputs.values())),
        "inputs": inputs,
        **map_summary(m, _classify),
        "susceptibility_map": None if m is None else m.astype(np.float32),
        "components_used": [k for k in ("ponding", "runoff_path") if w.get(k, 0) > 0],
        "components_excluded": excluded,
        "weights": w,
        "ceilings": dict(CEILINGS, runoff_c_pervious=cp),
        "design_storm_mm": round(float(storm), 2),
        "bluespots": {"count": fs["n_bluespots"],
                      "storage_m3": round(float(fs["storage_m3"].sum()), 1),
                      "stored_m3": round(float(fs["stored_m3"].sum()), 1),
                      "spilled_m3": round(float(fs["spill_m3"].sum()), 1)},
        "method": METHOD,
        "validated": VALIDATION_STATUS == "validated",
        "spatial": True,
        "limitations": [
            "Imperviousness is the stand-in (Open Buildings or OSM footprint area plus "
            "OSM road space), not item 21's impervious_total; pluvial must be re-tested "
            "when that exists. Vegetation is not used.",
            "FABDEM is 30 m with metre-scale vertical error: urban hollows smaller or "
            "shallower than that are invisible; hollows under 0.10 m deep are ignored.",
            "The design storm is the mean annual-maximum day (CHIRPS, 0.05 deg), one "
            "value per AOI. No drains, culverts or sewer capacity are modelled.",
            "The grid edge is the outlet: water leaving the AOI is gone, and inflow from "
            "outside it is missing.",
        ],
    }


def save_pluvial_susceptibility_output(susceptibility_map, run_dir, filename="pluvial_susceptibility.png"):
    if susceptibility_map is None:
        return None
    # unobserved (NaN) cells render black, same as score 0 -- a preview, not data
    arr_u8 = np.clip(np.nan_to_num(susceptibility_map) * 255.0, 0, 255).astype(np.uint8)
    path = os.path.join(run_dir, filename)
    Image.fromarray(arr_u8, mode="L").save(path)
    return filename
