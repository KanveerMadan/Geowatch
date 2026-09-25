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

Status "excluded" (ruling 2026-09-25, second round): the detector is known to
be zero in this AOI from a dataset -- snow_ice from a global permanent-snow /
glacier dataset, solar from global solar-installation inventories. The
fraction is 0 on every known pixel with provenance "excluded:<datasets>", and
it does not block the remainder. Excluded only if EVERY configured dataset
shows none.
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


def exclusion_provenance(spec: dict) -> str:
    return "excluded:" + "+".join(d["id"] for d in spec["exclusion"])


def check_exclusion(name: str, cfg: dict, region) -> dict | None:
    """Earth Engine: does any configured dataset show this surface in
    `region`? -> {"excluded", "datasets": {id: {...}}} or None if the
    detector has no exclusion datasets."""
    import ee
    spec = cfg["detectors"][name]
    if not spec.get("exclusion"):
        return None
    evidence = {}
    for d in spec["exclusion"]:
        if d["kind"] == "features":
            n = ee.FeatureCollection(d["id"]).filterBounds(region).size().getInfo()
            evidence[d["id"]] = {"present": n > 0, "features_intersecting": n}
        elif d["kind"] == "class_image":
            col = ee.ImageCollection(d["id"]).sort("system:time_start", False)
            img = ee.Image(col.first())
            year = img.date().format("YYYY").getInfo()
            hit = (img.select(d["band"]).eq(d["class_value"])
                   .reduceRegion(ee.Reducer.max(), region, d["scale_m"], bestEffort=True)
                   .get(d["band"]).getInfo())
            evidence[d["id"]] = {"present": bool(hit), "image_year": year,
                                 "class": f"{d['class_value']} {d['class_name']}"}
        else:
            raise ValueError(f"unknown exclusion kind {d['kind']!r}")
    out = {"excluded": not any(e["present"] for e in evidence.values()),
           "rule": "excluded only if every dataset shows none",
           "datasets": evidence}
    if spec.get("exclusion_caveat"):
        out["caveat"] = spec["exclusion_caveat"]
    return out


def run_detector(name: str, cfg: dict, bands: dict, known: np.ndarray,
                 exclusion: dict | None = None) -> dict:
    spec = cfg["detectors"][name]
    if exclusion is not None and exclusion["excluded"]:
        return {"name": name, "status": "excluded",
                "fraction": np.where(known, 0.0, np.nan).astype(np.float32),
                "provenance": exclusion_provenance(spec), "exclusion": exclusion,
                "thresholds": _threshold_record(spec)}
    missing = unset_thresholds(spec)
    if missing:
        return {**_not_computed(name, spec, missing), "exclusion": exclusion}
    mask = PREDICATES[name](bands, spec["thresholds"])
    # NaN spectra (occluded pixels) compare False above; mask them explicitly
    # as NaN so "not detected" and "not observed" stay distinct.
    frac = np.where(known, np.where(mask, 1.0, 0.0), np.nan).astype(np.float32)
    return {"name": name, "status": "computed", "fraction": frac,
            "provenance": "detector", "thresholds": _threshold_record(spec),
            "exclusion": exclusion}


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


# ── mixed_water_vegetation from datasets (R2, 2026-09-25) ───────────────────

def glwd_wetland_evidence(glwd_class: np.ndarray, cfg: dict) -> dict:
    """Is any blocking (non-Dryland) GLWD class present anywhere in the AOI?"""
    spec = cfg["detectors"]["mixed_water_vegetation"]["non_mangrove_exclusion"]
    lo, hi = spec["blocking_classes"]["from"], spec["blocking_classes"]["to"]
    legend = cfg["detectors"]["mixed_water_vegetation"]["sub_typing"]["glwd_legend"]
    cls = np.nan_to_num(glwd_class, nan=0).astype(int)
    present = sorted(int(c) for c in np.unique(cls) if lo <= c <= hi)
    return {"dataset": cfg["datasets"][spec["dataset"]],
            "blocking_classes": f"{lo}-{hi} (any non-Dryland)",
            "present": bool(present),
            "classes_present": {c: legend.get(c, str(c)) for c in present}}


def mixed_water_vegetation(cfg: dict, bands: dict, known: np.ndarray) -> dict:
    """R2 as amended 2026-09-25 -- PER GLWD CELL, not per AOI.

    mangrove      Global Mangrove Watch coverage, continuous, on every known
                  pixel.
    non-mangrove  excluded on pixels inside a Dryland GLWD cell (the 10 m
                  pixel takes the class of the GLWD cell holding its centre --
                  nearest-neighbour export); not_computed on pixels inside any
                  blocking (non-Dryland) cell.

    The class fraction is the mangrove coverage where non-mangrove is
    excluded, and NaN where it is not computed -- so bookkeeping blocks the
    remainder on exactly those pixels. Status: computed (no blocked pixel),
    partial, or not_computed (every known pixel blocked)."""
    spec = cfg["detectors"]["mixed_water_vegetation"]
    gmw_id = cfg["datasets"][spec["mangrove_producer"]]
    lo = spec["non_mangrove_exclusion"]["blocking_classes"]["from"]
    hi = spec["non_mangrove_exclusion"]["blocking_classes"]["to"]
    mangrove = np.where(known, np.nan_to_num(bands["gmw_cov"]), np.nan).astype(np.float32)
    cls = np.nan_to_num(bands["glwd_class"], nan=0).astype(int)
    blocking = known & (cls >= lo) & (cls <= hi)
    fraction = np.where(known & ~blocking, mangrove, np.nan).astype(np.float32)
    n_known = int(known.sum())
    share = float(blocking.sum()) / n_known if n_known else None
    evidence = {**glwd_wetland_evidence(bands["glwd_class"], cfg),
                "rule": "per GLWD cell (amended 2026-09-25)",
                "blocked_pixel_share": share}
    status = ("not_computed" if n_known and blocking.sum() == n_known
              else "partial" if blocking.any() else "computed")
    return {
        "name": "mixed_water_vegetation", "status": status, "fraction": fraction,
        "provenance": f"dataset:{gmw_id}+excluded_per_cell:{evidence['dataset']}",
        "components": {
            "mangrove": {"status": "computed", "provenance": f"dataset:{gmw_id}",
                         "continuous": True, "overrides_vegetation_water": False},
            "non_mangrove": {"excluded_on": "pixels in Dryland GLWD cells",
                             "not_computed_on": "pixels in non-Dryland GLWD cells",
                             "blocked_pixel_share": share},
        },
        "glwd_evidence": evidence, "mangrove_fraction": mangrove,
        "blocked_mask": blocking,
        "thresholds": _threshold_record(spec),
    }


def run_detectors(cfg: dict, bands: dict, known: np.ndarray,
                  exclusions: dict | None = None) -> dict:
    exclusions = exclusions or {}
    out = {name: run_detector(name, cfg, bands, known, exclusions.get(name))
           for name in ("snow_ice", "solar")}
    out["mixed_water_vegetation"] = mwv = mixed_water_vegetation(cfg, bands, known)
    out["mixed_water_vegetation"]["sub_type"] = sub_type(
        mwv["mangrove_fraction"], bands.get("gmw_cov"), bands.get("glwd_class"),
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
