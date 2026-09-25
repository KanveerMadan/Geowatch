"""
Item 21 Phase A, part 3 — rule/dataset detectors for the three new fractions
(Decision 11 producers, recorded 2026-09-24). No training.

  snow_ice                spectral signature + low temporal variance (item 18)
  solar                   spectral signature
  mixed_water_vegetation  spectral, sub-typed via Global Mangrove Watch + GLWD

Every threshold comes from configs/fractions.yaml with its source and a
status of UNVALIDATED or UNSET. If any threshold a detector needs is UNSET
the detector returns status "not_computed" with no array -- never an
all-zero array, which would read as "measured, none present" (C33).

A detected pixel has fraction 1.0 (Phase A simplification, ruled
2026-09-25, to be revisited after each detector's own validation case).
Precedence over the vegetation / water regressors is applied in part 5's
bookkeeping, not here.
"""

from __future__ import annotations

import numpy as np

DETECTORS = ("snow_ice", "solar", "mixed_water_vegetation")
DATASET_BANDS = ["gmw_cov", "glwd_class"]
UNATTRIBUTED = "unattributed"


def unset_thresholds(spec: dict) -> list:
    return sorted(k for k, t in spec["thresholds"].items()
                  if t.get("status") == "UNSET" or t.get("value") is None)


def _threshold_record(spec: dict) -> dict:
    return {k: {"value": t.get("value"), "source": t.get("source"),
                "status": t.get("status")} for k, t in spec["thresholds"].items()}


def _not_computed(name: str, spec: dict, missing: list) -> dict:
    return {"name": name, "status": "not_computed", "fraction": None,
            "reason": f"UNSET thresholds: {missing}",
            "thresholds": _threshold_record(spec)}


def _nd(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        return (a - b) / (a + b)


# ── predicates: run only when every threshold is set ────────────────────────

def _snow_ice_mask(bands: dict, t: dict) -> np.ndarray:
    """Hall et al. (1995) NDSI and NIR tests on the valid+snow composite
    (snow observations are kept there; occlusion.py), AND low variance in the
    configured item 18 band."""
    g, swir1, nir = bands["cvs_Green"], bands["cvs_SWIR1"], bands["cvs_NIR"]
    var_band = f"tv_{t['variance_band']['value']}"
    if var_band not in bands:
        raise KeyError(f"snow_ice variance_band {var_band!r} is not an item 18 band")
    return ((_nd(g, swir1) >= t["ndsi_min"]["value"])
            & (nir > t["nir_min"]["value"])
            & (bands[var_band] <= t["variance_max"]["value"]))


def _unimplemented(name):
    def predicate(bands, t):
        raise NotImplementedError(
            f"{name}: every threshold is set but no predicate is implemented. "
            f"Implement the cited method before setting its thresholds.")
    return predicate


PREDICATES = {
    "snow_ice": _snow_ice_mask,
    "solar": _unimplemented("solar"),
    "mixed_water_vegetation": _unimplemented("mixed_water_vegetation"),
}


def run_detector(name: str, cfg: dict, bands: dict, known: np.ndarray) -> dict:
    spec = cfg["detectors"][name]
    missing = unset_thresholds(spec)
    if missing:
        return _not_computed(name, spec, missing)
    mask = PREDICATES[name](bands, spec["thresholds"])
    # NaN spectra (occluded pixels) compare False above; mask them explicitly
    # as NaN so "not detected" and "not observed" stay distinct.
    frac = np.where(known, np.where(mask, 1.0, 0.0), np.nan).astype(np.float32)
    return {"name": name, "status": "computed", "fraction": frac,
            "provenance": "detector", "thresholds": _threshold_record(spec)}


# ── mixed_water_vegetation sub-typing ───────────────────────────────────────

def sub_type(detected: np.ndarray | None, gmw_cov: np.ndarray,
             glwd_class: np.ndarray, legend: dict) -> dict:
    """Per-pixel sub-type label where `detected` is 1; None elsewhere.

    GMW first (mangrove-specific vector); else the GLWD v2 main class name;
    else "unattributed". Returns {"status", "labels" (object array | None),
    "counts"}."""
    if detected is None:
        return {"status": "not_computed",
                "reason": "mixed_water_vegetation detector not computed",
                "labels": None, "counts": None}
    labels = np.full(detected.shape, None, dtype=object)
    hit = np.nan_to_num(detected) > 0
    mangrove = hit & (np.nan_to_num(gmw_cov) > 0)
    labels[mangrove] = "gmw:mangrove"
    rest = hit & ~mangrove
    cls = np.nan_to_num(glwd_class, nan=0).astype(int)
    for code, name in legend.items():
        if int(code) == 0:
            continue
        labels[rest & (cls == int(code))] = f"glwd:{name}"
    labels[rest & (cls == 0)] = UNATTRIBUTED
    vals, n = np.unique(labels[hit].astype(str), return_counts=True)
    return {"status": "computed", "labels": labels,
            "counts": dict(zip(vals.tolist(), n.tolist()))}


def run_detectors(cfg: dict, bands: dict, known: np.ndarray) -> dict:
    out = {name: run_detector(name, cfg, bands, known) for name in DETECTORS}
    mwv = out["mixed_water_vegetation"]
    out["mixed_water_vegetation"]["sub_type"] = sub_type(
        mwv["fraction"], bands.get("gmw_cov"), bands.get("glwd_class"),
        cfg["detectors"]["mixed_water_vegetation"]["sub_typing"]["glwd_legend"])
    return out


def dataset_context(bands: dict, legend: dict) -> dict:
    """AOI summary of the sub-typing datasets themselves, reported whether or
    not the detector ran -- so a reader can see what sub-typing WOULD have
    had to work with."""
    gmw = bands["gmw_cov"]
    cls = np.nan_to_num(bands["glwd_class"], nan=0).astype(int)
    vals, n = np.unique(cls, return_counts=True)
    return {"gmw_mangrove_coverage_mean": float(np.nanmean(gmw)),
            "glwd_class_pixel_share": {legend.get(int(v), str(int(v))): float(c) / cls.size
                                       for v, c in zip(vals, n)}}


# ── Earth Engine: dataset layers on the grid ────────────────────────────────

def export_datasets(cfg: dict, grid, run_dir: str) -> tuple:
    """GMW coverage fraction and GLWD class on `grid`; -> (bands, prov)."""
    import os
    import ee
    from ingestion.tiler import export_image_local
    from surface_fractions.grid import coverage_fraction, ee_projection, grid_region
    from surface_fractions.inputs import NODATA, read_stack

    region = grid_region(grid)
    proj = ee_projection(grid)
    gmw = ee.FeatureCollection(cfg["datasets"]["gmw"]).filterBounds(region)
    gmw_img = coverage_fraction(gmw, proj, cfg["footprints"]["subcell_m"]).rename("gmw_cov")
    # GLWD is categorical at ~464 m: nearest-neighbour onto the 10 m grid
    # (Earth Engine's default resampling), never averaged.
    glwd = ee.Image(cfg["datasets"]["glwd_main_class"]).select(0).rename("glwd_class")
    image = ee.Image.cat([gmw_img, glwd]).toFloat().unmask(NODATA)
    path = os.path.join(run_dir, "datasets.tif")
    export_image_local(image, region, path, crs=grid.crs,
                       crs_transform=list(grid.transform), band_names=DATASET_BANDS)
    prov = {"gmw": cfg["datasets"]["gmw"], "glwd": cfg["datasets"]["glwd_main_class"],
            "glwd_native_resolution_m": 464, "glwd_resampling": "nearest", "path": path}
    return read_stack(path, grid, DATASET_BANDS), prov
