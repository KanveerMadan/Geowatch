"""
Flood validation harness (item 26, task 8). Pre-registered in
PREREGISTRATION.md; the constants below match it.

For each of the five hazard modules: score cells, label them flooded / dry
from Sentinel-1 event extents or JRC GSW recurrent water, and report ROC AUC
against a fixed bar as validated / failed / not-run.

    python -m experiments.flood_validation.harness
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import traceback

import numpy as np

from configs.inundation_constants import (
    JRC_ASSET, JRC_PERMANENT_WATER_OCCURRENCE_PCT, JRC_SEASONAL_WATER_OCCURRENCE_PCT,
    S1_VV_DROP_THRESHOLD_DB,
)
from configs.pluvial_constants import HYDROLOGY_PIXEL_M

AUC_MIN = 0.70
MIN_FLOODED_CELLS = 50
MIN_DRY_CELLS = 50
MIN_POOLED_SITES = 3
PRE_EVENT_DAYS = 30
EVENT_DAYS = 3
HERE = os.path.dirname(os.path.abspath(__file__))

JRC_SITES = ("dharavi", "jakarta", "hcmc", "kigali", "accra", "dhaka", "capetown",
             "guatemala", "nusantara")   # BASELINE_AOIS minus held-out Lagos, Nairobi
PLUVIAL_SITES = {"dharavi": {"bbox": (72.836, 19.037, 72.862, 19.060), "event": "2017-08-29",
                             "veg_window": ("2018-01-01", "2018-03-31")}}
COASTAL_SITES = {
    "beira": {"bbox": (34.83, -19.85, 34.87, -19.81), "event": "2019-03-15"},
    "chennai_velachery": {"bbox": (80.20, 12.96, 80.24, 13.00), "event": "2023-12-04"},
    "fort_myers_beach": {"bbox": (-81.97, 26.43, -81.93, 26.47), "event": "2022-09-28"},
}
FLASH_SITES = {
    "paiporta": {"bbox": (-0.44, 39.41, -0.40, 39.45), "event": "2024-10-29"},
    "derna": {"bbox": (22.62, 32.75, 22.66, 32.78), "event": "2023-09-11"},
    "bad_neuenahr": {"bbox": (7.09, 50.53, 7.13, 50.56), "event": "2021-07-14"},
}


# ── pure: metric and verdict ──────────────────────────────────────────────

def auc(scores, flooded, dry) -> float | None:
    """ROC AUC from (score, flooded count, dry count) groups; ties count 1/2."""
    s, p, n = (np.asarray(a, dtype=np.float64) for a in (scores, flooded, dry))
    P, N = p.sum(), n.sum()
    if P == 0 or N == 0:
        return None
    order = np.argsort(s)
    s, p, n = s[order], p[order], n[order]
    uniq, inv = np.unique(s, return_inverse=True)
    pg, ng = np.bincount(inv, p), np.bincount(inv, n)
    below = np.concatenate([[0.0], np.cumsum(ng)[:-1]])
    return float((pg * (below + 0.5 * ng)).sum() / (P * N))


def verdict(groups: list, n_sites: int, pooled: bool) -> dict:
    """groups: [(score, flooded, dry)] -> the pre-registered verdict."""
    flooded = int(sum(g[1] for g in groups))
    dry = int(sum(g[2] for g in groups))
    out = {"flooded_cells": flooded, "dry_cells": dry, "n_sites": n_sites, "auc": None}
    short = flooded < MIN_FLOODED_CELLS or dry < MIN_DRY_CELLS or (pooled and n_sites < MIN_POOLED_SITES)
    if short:
        return {**out, "verdict": "not-run", "reason": "insufficient reference"}
    a = auc(*zip(*groups))
    return {**out, "auc": round(a, 4), "verdict": "validated" if a >= AUC_MIN else "failed"}


# ── Earth Engine references ──────────────────────────────────────────────

def _windows(event: str):
    e = datetime.date.fromisoformat(event)
    d = datetime.timedelta
    return ((e - d(days=PRE_EVENT_DAYS)).isoformat(), e.isoformat(),
            e.isoformat(), (e + d(days=EVENT_DAYS)).isoformat())


def s1_flooded(bbox, event: str):
    """(flooded, valid) ee.Images: S1 VV drop at 10 m, flooded share >= 0.5
    per 30 m cell, JRC permanent water excluded. Raises if a window is empty."""
    import ee
    from ingestion.inundation import _s1_collection
    aoi = ee.Geometry.Rectangle(list(bbox))
    pre0, pre1, ev0, ev1 = _windows(event)
    pre, ev = _s1_collection(aoi, pre0, pre1), _s1_collection(aoi, ev0, ev1)
    counts = (pre.size().getInfo(), ev.size().getInfo())
    if min(counts) == 0:
        raise LookupError(f"no Sentinel-1 image: pre={counts[0]} event={counts[1]}")
    drop = ev.median().subtract(pre.median()).lte(S1_VV_DROP_THRESHOLD_DB)
    proj = ee.Projection("EPSG:3857").atScale(HYDROLOGY_PIXEL_M)
    share = (drop.reproject(crs="EPSG:3857", scale=10)
             .reduceResolution(ee.Reducer.mean(), maxPixels=64).reproject(proj))
    occ = ee.Image(JRC_ASSET).select("occurrence").unmask(0)
    keep = occ.lt(JRC_PERMANENT_WATER_OCCURRENCE_PCT)
    return share.gte(0.5).rename("flooded"), keep, counts


def jrc_flooded(bbox):
    import ee
    occ = ee.Image(JRC_ASSET).select("occurrence").unmask(0)
    flooded = occ.gte(JRC_SEASONAL_WATER_OCCURRENCE_PCT).And(
        occ.lt(JRC_PERMANENT_WATER_OCCURRENCE_PCT)).rename("flooded")
    return flooded, occ.lt(JRC_PERMANENT_WATER_OCCURRENCE_PCT), None


def counts(flooded, keep, bbox) -> tuple:
    """(flooded cells, dry cells) over the bbox at 30 m, permanent water excluded."""
    import ee
    aoi = ee.Geometry.Rectangle(list(bbox))
    img = flooded.rename("f").addBands(flooded.Not().rename("d")).updateMask(keep)
    r = img.reduceRegion(ee.Reducer.sum(), aoi, HYDROLOGY_PIXEL_M, crs="EPSG:3857",
                         maxPixels=1e9).getInfo()
    return int(round(r["f"] or 0)), int(round(r["d"] or 0))


# ── module scores ────────────────────────────────────────────────────────

def _contexts(bbox):
    from ingestion.coastal import get_coastline_context
    from ingestion.hydrology import (get_fabdem_elevation_stats, get_merit_hand_context,
                                     get_slope_stats)
    from ingestion.rainfall import get_rainfall_climatology
    from ingestion.sentinel2 import aoi_from_bbox
    return {
        "hand": lambda: get_merit_hand_context(*bbox),
        "coast": lambda: get_coastline_context(*bbox),
        "fabdem": lambda: get_fabdem_elevation_stats(*bbox),
        "slope": lambda: get_slope_stats(*bbox),
        "rain": lambda: get_rainfall_climatology(aoi_from_bbox(*bbox)),
    }


def built_area_surface(bbox):
    """Waterlogging's impervious input for a bbox: Open Buildings footprint
    union area, averaged server-side (the same producer as task 1, reduced
    to the bbox because waterlogging only reads the AOI mean)."""
    import ee
    from susceptibility.inputs import surface
    from vector.sources import OPEN_BUILDINGS_ASSET
    aoi = ee.Geometry.Rectangle(list(bbox))
    built = ee.Image(0).byte().paint(ee.FeatureCollection(OPEN_BUILDINGS_ASSET).filterBounds(aoi), 1)
    v = built.reduceRegion(ee.Reducer.mean(), aoi, 2, crs="EPSG:3857", maxPixels=1e10,
                           tileScale=4).getInfo()["constant"]
    return surface(np.array([[v]]), "open_buildings_v3 footprints, EE mean over bbox",
                   "footprint_union_area_fraction", "placeholder")


def scalar_score(module: str, bbox) -> float | None:
    from susceptibility.coastal import compute_coastal_susceptibility
    from susceptibility.flash_flood import compute_flash_flood_susceptibility
    from susceptibility.fluvial import compute_fluvial_susceptibility
    from susceptibility.waterlogging import compute_waterlogging_susceptibility
    c = _contexts(bbox)
    if module == "fluvial":
        r = compute_fluvial_susceptibility(c["hand"]())
    elif module == "coastal":
        r = compute_coastal_susceptibility(c["coast"](), c["fabdem"]())
    elif module == "flash_flood":
        r = compute_flash_flood_susceptibility(c["slope"](), c["hand"](), c["rain"]())
    else:
        r = compute_waterlogging_susceptibility(c["hand"](), built_area_surface(bbox), c["rain"]())
    return r.get("aoi_mean_score")


# ── runners ──────────────────────────────────────────────────────────────

def run_pooled(module: str, sites: dict, reference) -> dict:
    groups, per_site = [], {}
    for name, site in sites.items():
        try:
            score = scalar_score(module, site["bbox"])
            flooded, keep, s1 = reference(site)
            f, d = counts(flooded, keep, site["bbox"])
            per_site[name] = {"score": score, "flooded_cells": f, "dry_cells": d,
                              **({"s1_images_pre_event": s1} if s1 else {})}
            if score is not None:
                groups.append((score, f, d))
            else:
                per_site[name]["dropped"] = "score is None"
        except Exception as e:
            per_site[name] = {"dropped": f"{type(e).__name__}: {e}"}
    return {**verdict(groups, len(groups), pooled=True), "sites": per_site}


def run_pluvial() -> dict:
    import ee
    from susceptibility.inputs import hydrology_surfaces
    from susceptibility.pluvial import compute_pluvial_susceptibility
    from vector.roads import load_road_layer
    groups, per_site = [], {}
    for name, site in PLUVIAL_SITES.items():
        try:
            layer = load_road_layer(name, site["bbox"])
            fi = hydrology_surfaces(layer, *site["veg_window"])
            m = compute_pluvial_susceptibility(impervious=fi["impervious"],
                                               infiltration=fi["infiltration"],
                                               conduits=fi["conduits"],
                                               terrain=fi["terrain"])["susceptibility_map"]
            flooded, keep, s1 = s1_flooded(site["bbox"], site["event"])
            t, (H, W) = fi["transform"], fi["shape"]
            grid = {"dimensions": {"width": W, "height": H},
                    "affineTransform": {"scaleX": t.a, "shearX": 0, "translateX": t.c,
                                        "shearY": 0, "scaleY": t.e, "translateY": t.f},
                    "crsCode": fi["crs"]}
            img = flooded.unmask(0).addBands(keep.rename("keep")).toByte()
            arr = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY",
                                         "grid": grid})
            ok = (arr["keep"] == 1) & np.isfinite(m)
            fl = arr["flooded"][ok] == 1
            sc = m[ok]
            groups += [(v, int(f), int(not f)) for v, f in zip(sc, fl)]
            per_site[name] = {"flooded_cells": int(fl.sum()), "dry_cells": int((~fl).sum()),
                              "s1_images_pre_event": s1, "validation_status_of_inputs":
                              fi["validation_status"]}
        except Exception as e:
            per_site[name] = {"dropped": f"{type(e).__name__}: {e}"}
            traceback.print_exc()
    return {**verdict(groups, len([s for s in per_site.values() if "dropped" not in s]),
                      pooled=False), "sites": per_site}


def main():
    from ingestion.gee_client import initialize_gee
    from vector.aois import BASELINE_AOIS
    initialize_gee()
    jrc_sites = {n: {"bbox": BASELINE_AOIS[n]} for n in JRC_SITES}
    jrc = lambda site: jrc_flooded(site["bbox"])
    s1 = lambda site: s1_flooded(site["bbox"], site["event"])
    modules = {}
    for name, fn in (("pluvial", run_pluvial),
                     ("fluvial", lambda: run_pooled("fluvial", jrc_sites, jrc)),
                     ("waterlogging", lambda: run_pooled("waterlogging", jrc_sites, jrc)),
                     ("coastal", lambda: run_pooled("coastal", COASTAL_SITES, s1)),
                     ("flash_flood", lambda: run_pooled("flash_flood", FLASH_SITES, s1))):
        print(f"── {name}", flush=True)
        modules[name] = fn()
        print(json.dumps({k: v for k, v in modules[name].items() if k != "sites"}), flush=True)
    result = {
        "test": "item 26 task 8 -- flood discrimination (Tier 2)",
        "preregistration_sha256": hashlib.sha256(
            open(os.path.join(HERE, "PREREGISTRATION.md"), "rb").read()).hexdigest(),
        "run_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "bar": {"metric": "roc_auc_cells", "validated_if_auc_at_least": AUC_MIN,
                "min_flooded_cells": MIN_FLOODED_CELLS, "min_dry_cells": MIN_DRY_CELLS,
                "min_pooled_sites": MIN_POOLED_SITES},
        "modules": modules,
    }
    with open(os.path.join(HERE, "result_2026-10-28.json"), "w") as f:
        json.dump(result, f, indent=2, default=float)


if __name__ == "__main__":
    main()
