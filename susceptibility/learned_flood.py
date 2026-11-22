"""
Learned flood susceptibility (flood_final): one logistic model, scored per
30 m cell on the hydrology grid.

WITHDRAWN from the pipeline on 2026-11-22: flood round 2 did not confirm its
gain over plain elevation (analysis.contract.WITHDRAWN). The river and
waterlogging output is now susceptibility/flood_ranking.py. This module is
kept, unwired, for its tests and for flood round 3.

What it is
----------
- The model chosen by flood_final's pre-registered rule for river (M1) and
  waterlogging (M3) floods: variant `open`, logistic regression, trained on 67
  observed floods (experiments/flood_final/PREREGISTRATION.md §4,
  results/method_choice.json).
- It passed the one held-out test for those two types only
  (results/heldout.json). Pluvial, flash flood, coastal and compound failed,
  and this output says nothing about them.
- Coefficients ship as JSON (configs/learned_flood_open_logreg.json), exported
  from the frozen model; the pickle's sha256 is recorded in the file.

Inputs
------
The 26 `open` features, built by the same code that built them for
training (experiments.flood_learned / flood_baselines; read-only here, so
the features are those the model was validated on):
- GLO-30 terrain on a 2 km margin grid;
- HydroSHEDS accumulation;
- OSM + JRC permanent water;
- JRC occurrence and recurrence;
- WorldCover and pre-event NDVI;
- GHSL built share and distance to coast;
- rain and clay, taken from the pipeline's own hydro_rasters stage, which is
  the function the experiment called.

Missing features are median-imputed with missing indicators, exactly as in
training. An input that failed to fetch makes the whole output unavailable,
never zero.

Not assessed (NaN on the map, counted in `not_assessed`):
- built-up cells (GHSL built share or WorldCover built share >= 0.5). The
  references the model learned from cannot see flooding among buildings, and
  at Weihui it ranks flooded streets below dry ground (DECISIONS.md D20).
  0.5 is the majority-share rule that defined urban cells in that test.
- permanent water (JRC occurrence >= 80 %, as in the labels).

The output is a within-AOI ranking, not a depth or return period. It was
validated on 4 km boxes.
"""
from __future__ import annotations

import hashlib
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(os.path.dirname(HERE), "configs", "learned_flood_open_logreg.json")
METHOD = "flood_final_learned_open_logreg"
BUILT_NOT_ASSESSED = 0.5           # D20: majority built share, the Weihui FU-cell rule
PERMANENT_WATER_PCT = 80.0         # labels' exclusion (flood_validation.references)
RAIN_CLAY = {"rain_p999_mm_h": "rain_intensity_mm_h", "rain_design_day_mm": "rain_design_day_mm",
             "rain_annual_mm": "rain_annual_mm", "clay_pct": "clay_pct"}
INPUT_SOURCES = {
    "terrain": "COPERNICUS/DEM/GLO30_2024_1 (bilinear, 30 m UTM, 2 km margin)",
    "accumulation": "WWF/HydroSHEDS/15ACC",
    "water": "OpenStreetMap water (Overpass) OR JRC/GSW1_4 occurrence >= 80 %",
    "jrc": "JRC/GSW1_4/GlobalSurfaceWater occurrence, recurrence",
    "landcover": "ESA/WorldCover v100/v200 (latest year before ref_year), 8 class fractions",
    "ndvi": "COPERNICUS/S2_HARMONIZED + GOOGLE/CLOUD_SCORE_PLUS cs_cdf >= 0.60, median of ref_year-1",
    "ghsl": "JRC/GHSL/P2023A/GHS_BUILT_S/2020",
    "coast": "sat-io shoreline outlines, distance capped at 50 km",
    "rain_clay": "susceptibility.hydro_rasters (CHIRPS, IMERG V07, SoilGrids)",
}


def model_sha256(path: str = MODEL_PATH) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_model(path: str = MODEL_PATH) -> dict:
    m = json.load(open(path))
    for k in ("impute_median", "mean", "std", "coef", "isotonic_x", "isotonic_y"):
        m[k] = np.asarray(m[k], np.float64)
    return m


def predict(model: dict, X: np.ndarray) -> tuple:
    """(raw score, calibrated score) per row; the training-time imputation."""
    X = np.asarray(X, np.float64)
    miss = np.isnan(X[:, model["missing_indicator_cols"]]).astype(np.float64)
    Xf = np.where(np.isnan(X), model["impute_median"], X)
    Z = np.hstack([(Xf - model["mean"]) / model["std"], miss])
    raw = 1.0 / (1.0 + np.exp(-(Z @ model["coef"] + model["intercept"])))
    return raw, np.interp(raw, model["isotonic_x"], model["isotonic_y"])


def assemble(features: list, inp: dict, layers: dict, k: int, shape) -> np.ndarray:
    """X (cells x features) in `features` order, from fetched arrays on the
    margin grid (`inp`, margin k cells) and the pipeline's hydro layers.
    The same arithmetic as experiments.flood_learned.features.build_table;
    test_learned_flood.py checks equality against a training table."""
    from experiments.flood_learned import features as FT
    crop = lambda a: a[k:a.shape[0] - k, k:a.shape[1] - k]      # noqa: E731
    cols = {}
    tr = FT.terrain(inp["dem_glo30"].astype(np.float64), inp["water_ext"], k)
    for t in FT.TERRAIN:
        cols[f"{t}_glo30"] = tr[t]
    cols["log_hs_acc"] = FT._log10(crop(inp["hs_acc_cells"]), 1.0)
    cols["elev_glo30"] = crop(inp["dem_glo30"]).astype(np.float64)
    for f in ("dist_water_m", "jrc_occurrence", "jrc_recurrence", "ndvi_pre", "dist_coast_m",
              "ghsl_built_frac") + tuple(f"wc_{c}" for c in ("built", "tree", "shrub", "grass",
                                                             "crop", "bare", "wetland", "mangrove")):
        cols[f] = inp.get(f, np.full(shape, np.nan))
    for f, lay in RAIN_CLAY.items():
        cols[f] = layers.get(lay, np.full(shape, np.nan))
    for f in features:
        if np.shape(cols[f]) != tuple(shape):
            raise ValueError(f"learned flood: {f} shape {np.shape(cols[f])} != {tuple(shape)}")
    return np.stack([np.asarray(cols[f], np.float32).ravel() for f in features], axis=1)


def fetch_inputs(transform, shape, crs: str, ref_year: int, key: str) -> dict:
    """Every non-pipeline input on the hydrology grid (Earth Engine, Overpass).
    Raises on a failed stack: the caller records the module as failed."""
    from experiments.flood_baselines import build as BUILD
    from experiments.flood_learned import fetch as F
    from experiments.flood_validation import references as R
    from susceptibility.hydro_rasters import grid_lonlat_bounds
    from vector.sources import bbox_key
    k = F.MARGIN_CELLS
    te, she = BUILD.expanded(transform, shape, k)
    ll_ext = grid_lonlat_bounds(te, she, crs)
    ll_box = grid_lonlat_bounds(transform, shape, crs)
    ms = BUILD._call(lambda: F.margin_stack(te, she, crs, ll_ext), "learned margin")
    occ_ext = R.jrc_occurrence(te, she, crs)
    osm, counts = BUILD.water_mask(ll_ext, te, she, crs, bbox_key(f"lf_{key}", ll_ext))
    water = osm | ~R.not_permanent(occ_ext)
    crop = lambda a: a[k:k + shape[0], k:k + shape[1]]      # noqa: E731
    inp = {"dem_glo30": ms["dem_glo30"], "hs_acc_cells": ms["hs_acc_cells"], "water_ext": water,
           "dist_water_m": crop(BUILD.distance_to_water(water, k * BUILD.PIXEL_M)),
           "jrc_occurrence": R.jrc_occurrence(transform, shape, crs)}
    bs, bmeta = BUILD._call(lambda: F.box_stack(transform, shape, crs, ll_box, ref_year), "learned box")
    inp.update(bs)
    inp.update(BUILD._call(lambda: F.extra_stack(transform, shape, crs, ll_box), "learned extra"))
    meta = {"margin_cells": k, "osm_counts": counts,
            "osm_complete": all(v is not None for v in counts.values()), **bmeta}
    return {"arrays": inp, "meta": meta}


LIMITATIONS = [
    "Validated for river and waterlogging flooding only (flood_final held-out pass); "
    "failed for pluvial, flash flood, coastal and compound flooding.",
    "A within-area ranking, not a depth, extent or return period; validated on 4 km boxes.",
    "Plain low-ground ranking (GLO-30 elevation) scored higher on the same held-out cells; "
    "the model's added skill over it is not shown.",
    "Built-up cells (built share >= 0.5) and permanent water are not assessed.",
    "Not a probability: the logistic model is not weakly calibrated on held-out data.",
]


def compute_learned_flood(inputs: dict | None, rasters: dict | None, shape,
                          model: dict | None = None) -> dict:
    """The module output, in the shape of the other susceptibility modules
    (aoi_mean_score, susceptibility_map, status, validation_status, method,
    inputs). `inputs`: fetch_inputs() result, or None when that stage did not
    finish; the hazard builder then reports the stage's own status."""
    base = {"method": METHOD, "weights": None, "ceilings": None, "model_sha256": model_sha256(),
            "inputs": {k: {"source": v, "method": "flood_final feature code"}
                       for k, v in INPUT_SOURCES.items()},
            "validated_types": ["fluvial", "waterlogging"], "limitations": list(LIMITATIONS),
            "aoi_mean_class": None, "validation_status": "validated"}
    if inputs is None or rasters is None:
        return {**base, "status": "failed", "aoi_mean_score": None, "susceptibility_map": None,
                "reason": "an input stage did not finish; no score, never zero"}
    model = model or load_model()
    layers = {k: v["raster"] for k, v in rasters.get("layers", {}).items()}
    a = inputs["arrays"]
    X = assemble(model["features"], a, layers, inputs["meta"]["margin_cells"], shape)
    _, cal = predict(model, X)
    smap = cal.reshape(shape)
    zeros = np.zeros(shape)
    built = np.fmax(np.nan_to_num(a.get("ghsl_built_frac", zeros), nan=0.0),
                    np.nan_to_num(a.get("wc_built", zeros), nan=0.0)) >= BUILT_NOT_ASSESSED
    perm = np.nan_to_num(np.asarray(a["jrc_occurrence"], np.float64), nan=0.0) >= PERMANENT_WATER_PCT
    # No terrain, no score: imputation covers a missing feature, never a cell
    # (or an AOI) with no elevation at all.
    k = inputs["meta"]["margin_cells"]
    dem = np.asarray(a["dem_glo30"], np.float64)[k:a["dem_glo30"].shape[0] - k, k:a["dem_glo30"].shape[1] - k]
    no_terrain = ~np.isfinite(dem)
    if no_terrain.all():
        return {**base, "status": "insufficient_evidence", "aoi_mean_score": None,
                "susceptibility_map": None, "reason": "no GLO-30 elevation in the AOI; no score, never zero"}
    smap = np.where(built | perm | no_terrain, np.nan, smap).astype(np.float32)
    ok = np.isfinite(smap)
    return {**base, "status": "computed" if ok.any() else "not_applicable",
            "reason": None if ok.any() else "every cell is built-up or permanent water",
            "susceptibility_map": smap,
            "aoi_mean_score": float(np.nanmean(smap)) if ok.any() else None,
            "not_assessed": {"built_up_cells": int(built.sum()),
                             "permanent_water_cells": int((perm & ~built).sum()),
                             "share": round(float(1 - ok.mean()), 4),
                             "reason": "built-up share >= 0.5 (reference blind spot, flood_final "
                                       "D20) or JRC permanent water"},
            "inputs_meta": inputs["meta"]}
