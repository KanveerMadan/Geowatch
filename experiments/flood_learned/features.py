"""
Per-event feature tables for the learned model (pure, from cached inputs).

    python -m experiments.flood_learned.features          # every fetched event

For each event: every 30 m cell of the cached box, its label (1 flooded,
0 dry, -1 unobserved; events.labels) and two blocks of columns:
  FEATURES     model inputs (all variants; feature sets pick from them)
  COMPARATORS  the scores the model is compared with on the same cells: the
               three flood_baselines baselines and the four production
               modules at their current config defaults
               (flood_baselines.score.all_scores, unchanged)

Terrain derivatives, one set per DEM (fabdem, glo30, gedtm30), computed on
the box + MARGIN_CELLS grid and cropped to the box so no box edge is
truncated. Windows and their basis:
  slope_<dem>       degrees, central differences at 30 m.
  curv_<dem>        Laplacian of z (m^-1 x 1000); > 0 = concave (hollow). 3 x 3,
                    the native-resolution form (Zevenbergen & Thorne 1987).
  tpi990_<dem>      z minus its mean over a 33 x 33-cell (990 m) window: the
                    block size flood_baselines measured as the flood indicator's
                    correlation range (upper quartile 960 m).
  relmin2km_<dem>   z minus the minimum within 2 km (a 135 x 135-cell window,
                    exactly the margin): height above the lowest nearby ground,
                    independent of where the scoring box was placed.
  depr_<dem>        depression depth (m): priority-flood filled z minus z
                    (susceptibility.bluespots.priority_flood; continuous, no
                    minimum-depth threshold).
  handmap_<dem>     height above the nearest mapped water cell (OSM water or
                    JRC permanent water; fetch.water_ext): a HAND computed
                    without MERIT Hydro. NaN where the margin grid holds no
                    water with a defined elevation (missing, never zero).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

from experiments.flood_baselines import build as BUILD
from experiments.flood_baselines import score as BSCORE
from experiments.flood_learned import events as LE
from experiments.flood_learned import fetch as F

CACHE = os.path.expanduser(os.environ.get("GEOWATCH_LEARNED_TABLES",
                                          "~/.cache/geowatch/flood_learned/tables"))
PIXEL_M = BUILD.PIXEL_M
DEMS = ("fabdem", "glo30", "gedtm30")
TPI_CELLS = 33                                  # = flood_baselines BLOCK_CELLS
RELMIN_CELLS = 2 * F.MARGIN_CELLS + 1           # 2 km either side
TERRAIN = ("slope", "curv", "tpi990", "relmin2km", "depr", "handmap")
OTHER = (
    # hydrography (MERIT Hydro unless named)
    "hand_merit", "log_upa_near", "log_upa_cell", "log_hs_acc", "fluvial_score",
    # water
    "dist_water_m", "jrc_occurrence", "jrc_recurrence", "jrc_water_freq_pre",
    "s1_water_freq_pre",
    # rainfall extremes (one value per CHIRPS / IMERG cell: near-constant in a box)
    "rain_p999_mm_h", "rain_design_day_mm", "rain_annual_mm",
    # soil, land cover, vegetation
    "clay_pct", "wc_built", "wc_tree", "wc_shrub", "wc_grass", "wc_crop", "wc_bare",
    "wc_wetland", "wc_mangrove", "ndvi_pre",
    # flood_final additions (appended so earlier column indices are unchanged)
    "elev_glo30", "dist_coast_m", "ghsl_built_frac",
)
FEATURES = tuple(f"{t}_{d}" for d in DEMS for t in TERRAIN) + OTHER
COMPARATORS = ("hand", "occurrence", "dist_water", "fluvial", "pluvial", "waterlogging",
               "flash_flood")


# ── pure terrain helpers ──────────────────────────────────────────────

def nan_mean_filter(z: np.ndarray, size: int) -> np.ndarray:
    from scipy.ndimage import uniform_filter
    ok = np.isfinite(z)
    s = uniform_filter(np.where(ok, z, 0.0), size, mode="constant")
    n = uniform_filter(ok.astype(float), size, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, s / n, np.nan)


def nan_min_filter(z: np.ndarray, size: int) -> np.ndarray:
    from scipy.ndimage import minimum_filter
    m = minimum_filter(np.where(np.isfinite(z), z, np.inf), size, mode="constant", cval=np.inf)
    return np.where(np.isfinite(m), m, np.nan)


def slope_deg(z: np.ndarray, dx: float = PIXEL_M) -> np.ndarray:
    gy, gx = np.gradient(z, dx)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def laplacian(z: np.ndarray, dx: float = PIXEL_M) -> np.ndarray:
    out = np.full(z.shape, np.nan)
    c = z[1:-1, 1:-1]
    out[1:-1, 1:-1] = (z[:-2, 1:-1] + z[2:, 1:-1] + z[1:-1, :-2] + z[1:-1, 2:] - 4 * c) / dx ** 2
    return out


def depression_depth(z: np.ndarray) -> np.ndarray:
    from susceptibility.bluespots import priority_flood
    filled, _, _ = priority_flood(z)
    return filled - z


def height_above_mapped_water(z: np.ndarray, water: np.ndarray) -> np.ndarray:
    from scipy.ndimage import distance_transform_edt
    src = np.asarray(water, bool) & np.isfinite(z)
    if not src.any():
        return np.full(z.shape, np.nan)
    _, (ri, ci) = distance_transform_edt(~src, return_indices=True)
    return z - z[ri, ci]


def terrain(z: np.ndarray, water: np.ndarray, k: int) -> dict:
    """{name: box-cropped array} for one DEM on the margin grid (k = margin)."""
    crop = lambda a: a[k:a.shape[0] - k, k:a.shape[1] - k]      # noqa: E731
    return {
        "slope": crop(slope_deg(z)),
        "curv": crop(laplacian(z) * 1000.0),
        "tpi990": crop(z - nan_mean_filter(z, TPI_CELLS)),
        "relmin2km": crop(z - nan_min_filter(z, RELMIN_CELLS)),
        "depr": crop(depression_depth(z)),
        "handmap": crop(height_above_mapped_water(z, water)),
    }


def _log10(a, add=0.0):
    a = np.asarray(a, np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(np.isfinite(a) & (a + add > 0), np.log10(a + add), np.nan)


# ── one event ─────────────────────────────────────────────────────────

def build_table(entry: dict, chosen: dict) -> dict:
    name = entry["unit"]
    base = BUILD.load(name)
    a = base["arrays"]
    li = F.load(name)
    L = li["arrays"]
    shape = tuple(base["meta"]["grid"]["shape"])
    k = li["meta"]["margin_cells"]
    cols = {}
    missing = {}
    for d in DEMS:
        key = f"dem_{d}"
        if key not in L or not np.isfinite(L[key]).any():
            missing[d] = li["meta"]["errors"].get(d if d != "gedtm30" else "gedtm30",
                                                  "not fetched")
            for t in TERRAIN:
                cols[f"{t}_{d}"] = np.full(shape, np.nan)
            continue
        tr = terrain(L[key].astype(np.float64), L["water_ext"], k)
        for t in TERRAIN:
            cols[f"{t}_{d}"] = tr[t]
    crop = lambda x: x[k:x.shape[0] - k, k:x.shape[1] - k]      # noqa: E731
    sc = BSCORE.all_scores(a, shape, chosen)
    cols.update({
        "hand_merit": a["layer_hand_m"], "log_upa_near": _log10(a["layer_upa_near_km2"]),
        "log_upa_cell": _log10(crop(L["upa_cell_km2"])),
        "log_hs_acc": _log10(crop(L["hs_acc_cells"]), 1.0),
        "fluvial_score": sc["fluvial"],
        "dist_water_m": a["dist_water_m"], "jrc_occurrence": a["jrc_occurrence"],
        "jrc_recurrence": L.get("jrc_recurrence", np.full(shape, np.nan)),
        "jrc_water_freq_pre": a.get("layer_jrc_water_freq", np.full(shape, np.nan)),
        "s1_water_freq_pre": a.get("layer_s1_water_freq", np.full(shape, np.nan)),
        "rain_p999_mm_h": a.get("layer_rain_intensity_mm_h", np.full(shape, np.nan)),
        "rain_design_day_mm": a.get("layer_rain_design_day_mm", np.full(shape, np.nan)),
        "rain_annual_mm": a.get("layer_rain_annual_mm", np.full(shape, np.nan)),
        "clay_pct": a["layer_clay_pct"],
        "ndvi_pre": L.get("ndvi_pre", np.full(shape, np.nan)),
        "elev_glo30": crop(L["dem_glo30"]).astype(np.float64),
        "dist_coast_m": L.get("dist_coast_m", np.full(shape, np.nan)),
        "ghsl_built_frac": L.get("ghsl_built_frac", np.full(shape, np.nan)),
    })
    for c in ("built", "tree", "shrub", "grass", "crop", "bare", "wetland", "mangrove"):
        cols[f"wc_{c}"] = L.get(f"wc_{c}", np.full(shape, np.nan))
    for f in FEATURES:
        if cols[f].shape != shape:
            raise ValueError(f"{name}: {f} shape {cols[f].shape} != {shape}")
    X = np.stack([np.asarray(cols[f], np.float32).ravel() for f in FEATURES], axis=1)
    C = np.stack([(np.full(shape, np.nan) if sc[c] is None else np.asarray(sc[c])).ravel()
                  for c in COMPARATORS], axis=1).astype(np.float32)
    y = LE.labels(entry, a["jrc_occurrence"]).ravel()
    meta = {"unit": name, "shape": shape, "features": FEATURES, "comparators": COMPARATORS,
            "missing_dems": missing, "inputs_meta": {k2: li["meta"].get(k2) for k2 in (
                "worldcover_year", "ndvi_year", "s2_images", "osm_complete", "errors")},
            "grid": base["meta"]["grid"], "event": entry["meta"]["event"],
            "n_flooded": int((y == 1).sum()), "n_dry": int((y == 0).sum()),
            "n_unobserved": int((y == -1).sum())}
    return {"X": X, "C": C, "y": y, "meta": meta}


def path(name):
    return os.path.join(CACHE, f"{name}.npz")


def save(name, t):
    os.makedirs(CACHE, exist_ok=True)
    tmp = path(name) + f".tmp{os.getpid()}.npz"
    np.savez_compressed(tmp, X=t["X"], C=t["C"], y=t["y"],
                        meta=np.array(json.dumps(t["meta"], default=str)))
    os.replace(tmp, path(name))


def load(name):
    z = np.load(path(name), allow_pickle=False)
    return {"X": z["X"], "C": z["C"], "y": z["y"], "meta": json.loads(str(z["meta"]))}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    chosen = BSCORE.round4_chosen()
    for c in LE.batch0():
        n = c["unit"]
        if args.only and n not in args.only:
            continue
        if not os.path.exists(F.path(n)):
            print(f"── {n}: inputs not fetched; skipped", flush=True)
            continue
        if os.path.exists(path(n)) and not args.force and \
                os.path.getmtime(path(n)) >= os.path.getmtime(F.path(n)):
            continue                     # cached and not older than its inputs
        t = build_table(c, chosen)
        save(n, t)
        m = t["meta"]
        print(f"── {n}: {m['n_flooded']} flooded / {m['n_dry']} dry / {m['n_unobserved']} "
              f"unobserved; missing DEMs {list(m['missing_dems'])}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
