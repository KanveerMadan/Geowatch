"""
Flood ranking for river (M1) and waterlogging (M3) floods: plain low-ground
ranking by GLO-30 elevation, per 30 m cell on the hydrology grid.

Why elevation, not the learned model (decided 2026-11-22)
---------------------------------------------------------
- flood_final's learned model passed its pre-registered held-out test for
  river and waterlogging against HAND, but plain elevation scored higher on
  the same held-out cells (river 0.850, waterlogging 0.843).
- flood round 2 (exp/flood-round2, DECISIONS R17) then tested the learned
  gain over elevation on 63 new reserved units, scored once at the freeze tag
  `flood-round2-heldout-freeze`. It was not confirmed for any type:
  river +0.015 [-0.004, +0.044], waterlogging +0.012 [-0.035, +0.054].
- So this output ranks by elevation alone, the simplest method the evidence
  supports, until a later pre-registered round confirms a method that beats it
  (flood round 3; its winners replace this output).

Trust label: `experimental`. Elevation ranking has never been pre-registered
as the method under test for river or waterlogging flooding; it was the
comparator. Its held-out numbers below are reported, not a pass:
- flood_final held-out: river 0.850 (8 units), waterlogging 0.843 (3 units);
- flood round 2 held-out: river 0.897 (17 units), waterlogging 0.707
  (10 units), as the `elev` baseline.

Score: minus the GLO-30 elevation (m), so lower ground ranks higher. It is a
within-AOI ranking, not a depth, extent, return period or probability. The
map is drawn as each cell's percentile in the AOI.

Not assessed (NaN on the map, counted in `not_assessed`), as for the learned
output it replaces, because the evidence behind the ranking comes from the
same references:
- built-up cells (GHSL built share or WorldCover built share >= 0.5): the
  references cannot see flooding among buildings (flood_final D20);
- permanent water (JRC occurrence >= 80 %, as in the labels);
- cells with no GLO-30 elevation (no terrain, no score, never zero).
"""
from __future__ import annotations

import numpy as np

METHOD = "glo30_elevation_rank"
BUILT_NOT_ASSESSED = 0.5           # flood_final D20: majority built share
PERMANENT_WATER_PCT = 80.0         # labels' exclusion (flood_validation.references)
FLOOD_TYPES = ("fluvial", "waterlogging")
INPUT_SOURCES = {
    "terrain": "COPERNICUS/DEM/GLO30_2024_1 (bilinear, 30 m UTM)",
    "jrc": "JRC/GSW1_4/GlobalSurfaceWater occurrence",
    "landcover": "ESA/WorldCover v100/v200 (latest year before ref_year), built fraction",
    "ghsl": "JRC/GHSL/P2023A/GHS_BUILT_S/2020",
}
EVIDENCE = {
    "flood_final_heldout": {"fluvial": 0.850, "waterlogging": 0.843,
                            "evidence": "experiments/flood_final/results/heldout.json "
                                        "(elevation reported beside the verdict, not "
                                        "pre-registered)"},
    "flood_round2_heldout": {"fluvial": 0.897, "waterlogging": 0.707,
                             "evidence": "exp/flood-round2 results/heldout_r2.json (sha256 "
                                         "231710fb...), the `elev` baseline; DECISIONS R17"},
}
LIMITATIONS = [
    "Ranks by elevation alone: lower ground ranks higher. It does not know this event's "
    "water level, flood defences, or which low ground is connected to a river.",
    "Not validated: elevation was the comparator, not the method under test, in the "
    "pre-registered flood rounds. Reported held-out AUC: river 0.85-0.90, "
    "waterlogging 0.71-0.84.",
    "A within-area ranking, not a depth, extent, return period or probability; "
    "evaluated on 4 km boxes.",
    "Built-up cells (built share >= 0.5) and permanent water are not assessed.",
    "Replaces the learned model, whose gain over elevation flood round 2 did not confirm.",
]


def fetch_inputs(transform, shape, crs: str, ref_year: int, key: str) -> dict:
    """GLO-30 elevation, JRC occurrence and the two built-up shares on the
    hydrology grid (Earth Engine). Raises on failure: the caller records the
    stage as failed, and the output gets no score."""
    import ee
    from experiments.flood_learned import fetch as F
    from susceptibility.hydro_rasters import compute_pixels, grid_lonlat_bounds
    ll = grid_lonlat_bounds(transform, shape, crs)
    region = ee.Geometry.Rectangle(list(ll))
    wy = F.worldcover_year(ref_year)
    wc = ee.ImageCollection(F.WORLDCOVER[wy]).first().select("Map")
    wc_built = (wc.eq(F.WC_CLASSES["built"]).toFloat().setDefaultProjection(wc.projection())
                .reduceResolution(ee.Reducer.mean(), maxPixels=64))
    img = ee.Image.cat([
        F._mosaic(F.GLO30_ASSET, region, "DEM").resample("bilinear").rename("dem_glo30"),
        ee.Image(F.JRC_ASSET).select("occurrence").unmask(0).rename("jrc_occurrence"),
        wc_built.rename("wc_built"),
        ee.Image(F.GHSL_BUILT_S).select(0).divide(F.GHSL_CELL_M2).rename("ghsl_built_frac"),
    ])
    arr = compute_pixels(img, transform, shape, crs, "flood ranking stack")
    return {"arrays": {k: np.asarray(v, np.float32) for k, v in arr.items()},
            "meta": {"worldcover_year": wy, "worldcover_asset": F.WORLDCOVER[wy]}}


def compute_flood_ranking(inputs: dict | None, shape) -> dict:
    """The output in the susceptibility modules' shape. `inputs`:
    fetch_inputs() result, or None when that stage did not finish."""
    base = {"method": METHOD, "weights": None, "ceilings": None,
            "inputs": {k: {"source": v, "method": "elevation rank"}
                       for k, v in INPUT_SOURCES.items()},
            "flood_types_scored": list(FLOOD_TYPES), "evidence": EVIDENCE,
            "limitations": list(LIMITATIONS), "aoi_mean_class": None,
            "validation_status": "experimental"}
    if inputs is None:
        return {**base, "status": "failed", "aoi_mean_score": None, "susceptibility_map": None,
                "reason": "the input stage did not finish; no score, never zero"}
    a = inputs["arrays"]
    dem = np.asarray(a["dem_glo30"], np.float64)
    if dem.shape != tuple(shape):
        raise ValueError(f"flood ranking: dem shape {dem.shape} != {tuple(shape)}")
    no_terrain = ~np.isfinite(dem)
    if no_terrain.all():
        return {**base, "status": "insufficient_evidence", "aoi_mean_score": None,
                "susceptibility_map": None,
                "reason": "no GLO-30 elevation in the AOI; no score, never zero"}
    zeros = np.zeros(shape)
    built = np.fmax(np.nan_to_num(np.asarray(a.get("ghsl_built_frac", zeros), np.float64), nan=0.0),
                    np.nan_to_num(np.asarray(a.get("wc_built", zeros), np.float64), nan=0.0)
                    ) >= BUILT_NOT_ASSESSED
    perm = np.nan_to_num(np.asarray(a["jrc_occurrence"], np.float64), nan=0.0) >= PERMANENT_WATER_PCT
    smap = np.where(built | perm | no_terrain, np.nan, -dem).astype(np.float32)
    ok = np.isfinite(smap)
    if not ok.any():
        return {**base, "status": "not_applicable", "aoi_mean_score": None,
                "susceptibility_map": smap, "reason": "every cell is built-up or permanent water"}
    # A ranking has no absolute level, so the AOI value is a plain fact about
    # the ranked cells, not a likelihood: their median GLO-30 elevation (m).
    return {**base, "status": "computed", "reason": None, "susceptibility_map": smap,
            "aoi_mean_score": round(float(np.nanmedian(dem[ok])), 2),
            "aoi_score_kind": "median GLO-30 elevation (m) of the assessed cells; not a likelihood",
            "not_assessed": {"built_up_cells": int(built.sum()),
                             "permanent_water_cells": int((perm & ~built).sum()),
                             "share": round(float(1 - ok.mean()), 4),
                             "reason": "built-up share >= 0.5 (reference blind spot, flood_final "
                                       "D20) or JRC permanent water"},
            "inputs_meta": inputs.get("meta", {})}
