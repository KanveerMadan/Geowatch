"""
Item 21 §9 pilot A (label-free), redesign ruled 2026-09-28: change test.

Window. The high-resolution (HR) date +-90 d; for a date-range site (Rocinha,
Cape Town) the range extended by 90 d on each side, scenes inside the range
included. A "scene" is a distinct acquisition date with a Sentinel-2 L2A
granule under 20% cloud (CLOUDY_PIXEL_PERCENTAGE) intersecting the approved
box -- the unit pilot B counted. Minimum 3 per site.

Composite. The existing recipe (ingestion/sentinel2.py): mask_s2_clouds (SCL
cloud + no-data masked, cloud shadow kept), reflectance / 10000, the 6 bands,
per-pixel median over GRANULES, exactly as Earth Engine's `.median()` does
it. Each granule is fetched once on the 10 m tile lattice; a half-composite
is the per-pixel median over every granule of the half's dates (scenes are
split by date; a date's granules stay together). Checked against Earth
Engine's own `.median()` over the full window (`median_check`). A first run
(2026-09-28) mosaicked each date to one observation instead; that departed
from the recipe where a date has several granules (Monrovia, Karachi, Cape
Town: p99 |diff| 0.009-0.018 reflectance) and was replaced.

Metrics, per 10 m cell, between two composites A and B (6-vectors):
  spectral angle         degrees, arccos(A.B / |A||B|)
  mean-reflectance diff  |mean6(A) - mean6(B)|, reflectance
A cell is evaluable only where both composites have a valid observation.

Noise. All window scenes split at random into two halves (seeded; odd count:
the first half is one larger), each composited; per-cell metrics over the
eligible cells. 20 seeded splits. Noise unit per metric per site = median
over splits of the 95th-percentile per-cell difference (50th / 99th reported
too).

Change. Chronological split of the same scenes: earliest half vs latest half
(odd count: the middle scene goes to the earlier half). A cell is changed if
EITHER metric exceeds k x its noise unit, k = 2, 3, 5. A tile's changed share
= changed cells / evaluable cells (non-evaluable cells are counted and
reported, never treated as unchanged). A tile would be dropped at threshold t
when its changed share is >= t, t = 5 / 10 / 20 %.

Eligible tiles: the frozen strata.gpkg tiles (the real-data frame), excluding
`unassigned`. Tables per site and stratum. Six tiles rendered: the 3 with the
highest changed share at k = 3 and the 3 whose share at k = 3 is nearest 10%.
Nothing is chosen.

    python experiments/item21_sites/pilot_a_change_test.py
"""

from __future__ import annotations

import json
import math
import os
import sys
import warnings
from datetime import date, timedelta

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
CACHE = os.path.join(REPO, "data", "pilot_a")

HALF_WINDOW_D = 90
MIN_SCENES = 3
N_SPLITS = 20
NOISE_PCT = (50, 95, 99)
NOISE_UNIT_PCT = 95
KS = (2, 3, 5)
DROP_AT = (0.05, 0.10, 0.20)
RENDER_K, RENDER_T = 3, 0.10
CELL_M, TILE_M = 10, 200
NCELL = TILE_M // CELL_M
METRICS = ("angle_deg", "mean_refl_diff")
# Operational only (no effect on results): a request that hangs on a dead
# connection (seen 2026-09-28: blocked 22 h in an SSL read) times out and is
# retried.
EE_DEADLINE_MS = 300_000
EE_ATTEMPTS = 3


def _retry(fn, *args):
    for i in range(EE_ATTEMPTS):
        try:
            return fn(*args)
        except Exception as e:                         # timeouts surface as several types
            if i == EE_ATTEMPTS - 1:
                raise
            print(f"retry {i + 1}/{EE_ATTEMPTS - 1} after {type(e).__name__}: {e}", flush=True)


# ── pure functions (tested offline) ──────────────────────────────────────────

def window(hr: tuple) -> tuple:
    d0, d1 = date.fromisoformat(hr[0]), date.fromisoformat(hr[-1])
    return d0 - timedelta(days=HALF_WINDOW_D), d1 + timedelta(days=HALF_WINDOW_D)


def random_halves(n: int, seed: int) -> tuple:
    perm = np.random.default_rng(seed).permutation(n)
    h = math.ceil(n / 2)
    return np.sort(perm[:h]), np.sort(perm[h:])


def chrono_halves(n: int) -> tuple:
    """Indices into date-sorted scenes; odd n: the middle scene goes to the earlier half."""
    h = math.ceil(n / 2)
    return np.arange(h), np.arange(h, n)


def composite(stack: np.ndarray) -> np.ndarray:
    """(n, 6, H, W) NaN-masked -> (6, H, W) per-pixel median; NaN where no valid obs."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)       # all-NaN slices -> NaN
        return np.nanmedian(stack, axis=0)


def cell_metrics(a: np.ndarray, b: np.ndarray) -> dict:
    """(6, H, W) x 2 -> per-cell spectral angle (deg) and |mean6 difference|."""
    valid = np.isfinite(a).all(0) & np.isfinite(b).all(0)
    dot = np.nansum(a * b, 0)
    na, nb = np.sqrt(np.nansum(a * a, 0)), np.sqrt(np.nansum(b * b, 0))
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = np.clip(dot / (na * nb), -1.0, 1.0)
    angle = np.degrees(np.arccos(cos))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)       # all-NaN cells -> NaN
        mdiff = np.abs(np.nanmean(a, 0) - np.nanmean(b, 0))
    angle[~valid] = np.nan
    mdiff = np.where(valid, mdiff, np.nan)
    return {"angle_deg": angle, "mean_refl_diff": mdiff}


def granules_of(groups: list, date_idx) -> np.ndarray:
    """groups[i] = granule indices of date i -> all granules of the chosen dates."""
    return np.concatenate([np.asarray(groups[i], int) for i in date_idx])


def noise(stack: np.ndarray, cells: np.ndarray, n_splits: int = N_SPLITS, groups: list | None = None) -> dict:
    """Split-half noise over the cells where `cells` is True. Dates are split;
    `groups` maps each date to its granules (default: one granule per date)."""
    per = {m: {p: [] for p in NOISE_PCT} for m in METRICS}
    groups = groups if groups is not None else [[i] for i in range(stack.shape[0])]
    for seed in range(n_splits):
        ia, ib = random_halves(len(groups), seed)
        met = cell_metrics(composite(stack[granules_of(groups, ia)]), composite(stack[granules_of(groups, ib)]))
        for m in METRICS:
            v = met[m][cells]
            v = v[np.isfinite(v)]
            for p in NOISE_PCT:
                per[m][p].append(float(np.percentile(v, p)) if v.size else float("nan"))
    return {m: {"unit": float(np.median(per[m][NOISE_UNIT_PCT])),
                **{f"p{p}_median_over_splits": float(np.median(per[m][p])) for p in NOISE_PCT},
                f"p{NOISE_UNIT_PCT}_per_split": per[m][NOISE_UNIT_PCT]} for m in METRICS}


def changed_cells(met: dict, units: dict, k: float) -> np.ndarray:
    """Float map: 1 changed, 0 not, NaN not evaluable. EITHER metric > k x unit."""
    valid = np.isfinite(met["angle_deg"]) & np.isfinite(met["mean_refl_diff"])
    ch = (met["angle_deg"] > k * units["angle_deg"]) | (met["mean_refl_diff"] > k * units["mean_refl_diff"])
    return np.where(valid, ch.astype(float), np.nan)


def tile_share(changed: np.ndarray, r0: int, c0: int) -> dict:
    t = changed[r0:r0 + NCELL, c0:c0 + NCELL]
    ev = int(np.isfinite(t).sum())
    n = int(np.nansum(t))
    return {"evaluable": ev, "changed": n, "share": (n / ev) if ev else None}


def drop_table(rows: list) -> dict:
    """rows: {stratum, shares: {k: share|None}} -> {stratum|"all": {n, no_evaluable,
    k: {t: share of tiles dropped}}}. A tile with no evaluable cell is counted
    in `no_evaluable` and excluded from the shares (never read as unchanged)."""
    out = {}
    groups = {"all": rows}
    for r in rows:
        groups.setdefault(r["stratum"], []).append(r)
    for g, rs in groups.items():
        ok = [r for r in rs if r["shares"][str(KS[0])] is not None]
        out[g] = {"n": len(rs), "no_evaluable": len(rs) - len(ok),
                  **{f"k{k}": {f"{int(t * 100)}pct": (round(sum(r["shares"][str(k)] >= t for r in ok) / len(ok), 4)
                                                      if ok else None) for t in DROP_AT} for k in KS}}
    return out


# ── Earth Engine / data ──────────────────────────────────────────────────────

def eligible_tiles(site: str, cfg: dict) -> list:
    import pyogrio
    from labelling.strata_io import check_frozen
    from labelling.strata_style import UNASSIGNED
    path = os.path.join(REPO, "data", "strata_packages", site, "strata.gpkg")
    check_frozen(path, site, cfg)
    g = pyogrio.read_dataframe(path, layer="strata")
    out = []
    for tid, st, geom in zip(g.tile_id, g.stratum, g.geometry):
        if st == UNASSIGNED:
            continue
        x0, _, _, y1 = geom.bounds
        out.append({"tile_id": tid, "stratum": st, "x0": round(x0, 3), "y1": round(y1, 3)})
    return out


def lattice(tiles: list) -> dict:
    x0 = min(t["x0"] for t in tiles)
    y1 = max(t["y1"] for t in tiles)
    w = int(round((max(t["x0"] for t in tiles) + TILE_M - x0) / CELL_M))
    h = int(round((y1 - (min(t["y1"] for t in tiles) - TILE_M)) / CELL_M))
    return {"x0": x0, "y1": y1, "width": w, "height": h}


def _pixels(img, crs: str, lat: dict) -> np.ndarray:
    import ee
    arr = ee.data.computePixels({
        "expression": img.unmask(-1).toFloat(), "fileFormat": "NUMPY_NDARRAY",
        "grid": {"dimensions": {"width": lat["width"], "height": lat["height"]},
                 "affineTransform": {"scaleX": CELL_M, "shearX": 0, "translateX": lat["x0"],
                                     "shearY": 0, "scaleY": -CELL_M, "translateY": lat["y1"]},
                 "crsCode": crs}})
    from ingestion.sentinel2 import S2_BAND_NAMES
    out = np.stack([arr[b].astype(np.float32) for b in S2_BAND_NAMES])
    out[:, (out < 0).any(0)] = np.nan                         # masked in any band -> no obs
    return out


def granules(a: dict, day: date) -> list:
    """system:index of every clear granule of `day` intersecting the box."""
    import ee
    g = ee.Geometry.Rectangle(list(a["box_utm"]), a["crs"], False)
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(g)
           .filterDate(day.isoformat(), (day + timedelta(days=1)).isoformat())
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20)))
    return sorted(_retry(col.aggregate_array("system:index").getInfo))


def fetch_granule(site: str, a: dict, idx: str, lat: dict) -> np.ndarray:
    import ee
    from ingestion.sentinel2 import mask_s2_clouds
    p = os.path.join(CACHE, site, "granules", f"{idx}.npy")
    if os.path.exists(p):
        return np.load(p)
    arr = _retry(_pixels, mask_s2_clouds(ee.Image(f"COPERNICUS/S2_SR_HARMONIZED/{idx}")), a["crs"], lat)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    np.save(p, arr)
    return arr


def ee_median(a: dict, start: date, end: date, lat: dict) -> np.ndarray:
    """The existing recipe run by Earth Engine over the whole window (check only)."""
    import ee
    from ingestion.sentinel2 import get_sentinel2_collection, mask_s2_clouds
    g = ee.Geometry.Rectangle(list(a["box_utm"]), a["crs"], False)
    col = get_sentinel2_collection(g, start.isoformat(), (end + timedelta(days=1)).isoformat(), 20)
    return _retry(_pixels, col.map(mask_s2_clouds).median(), a["crs"], lat)


def run_site(site: str, hr: tuple, cfg: dict) -> tuple:
    from pilot_b_time_window import clear_dates
    a = cfg["aois"][site]
    start, end = window(hr)
    dates = _retry(clear_dates, a["crs"], a["box_utm"], start, end)
    tiles = eligible_tiles(site, cfg)
    lat = lattice(tiles)
    ids, groups = [], []
    for d in dates:
        g = granules(a, d)
        groups.append(list(range(len(ids), len(ids) + len(g))))
        ids += g
    stack = np.stack([fetch_granule(site, a, i, lat) for i in ids])
    cells = np.zeros((lat["height"], lat["width"]), bool)
    for t in tiles:
        t["r0"] = int(round((lat["y1"] - t["y1"]) / CELL_M))
        t["c0"] = int(round((t["x0"] - lat["x0"]) / CELL_M))
        cells[t["r0"]:t["r0"] + NCELL, t["c0"]:t["c0"] + NCELL] = True

    nz = noise(stack, cells, groups=groups)
    units = {m: nz[m]["unit"] for m in METRICS}
    ia, ib = chrono_halves(len(dates))
    before, after = composite(stack[granules_of(groups, ia)]), composite(stack[granules_of(groups, ib)])
    met = cell_metrics(before, after)
    ch = {k: changed_cells(met, units, k) for k in KS}
    rows = []
    for t in tiles:
        per = {str(k): tile_share(ch[k], t["r0"], t["c0"]) for k in KS}
        rows.append({"tile_id": t["tile_id"], "stratum": t["stratum"],
                     "evaluable_cells": per[str(KS[0])]["evaluable"],
                     "shares": {k: v["share"] for k, v in per.items()}})

    full = composite(stack)
    eem = ee_median(a, start, end, lat)
    both = cells & np.isfinite(full).all(0) & np.isfinite(eem).all(0)
    d = np.abs(full - eem)[:, both]
    res = {
        "hr": list(hr), "window": [start.isoformat(), end.isoformat()],
        "scenes": len(dates), "granules": len(ids), "dates": [x.isoformat() for x in dates],
        "noise_split_sizes": [len(random_halves(len(dates), 0)[0]), len(random_halves(len(dates), 0)[1])],
        "chrono_halves": {"earlier": [dates[i].isoformat() for i in ia], "later": [dates[i].isoformat() for i in ib]},
        "eligible_tiles": len(tiles), "eligible_cells": int(cells.sum()),
        "noise": nz,
        "cells_not_evaluable": int((cells & ~np.isfinite(met["angle_deg"])).sum()),
        "tiles_with_any_not_evaluable": sum(r["evaluable_cells"] < NCELL * NCELL for r in rows),
        "drop_table": drop_table(rows),
        "median_check": {"cells_compared": int(both.sum()),
                         "abs_diff_p99": float(np.percentile(d, 99)) if d.size else None,
                         "abs_diff_max": float(d.max()) if d.size else None,
                         "share_equal_1e-4": float((d.max(0) <= 1e-4).mean()) if d.size else None},
        "tiles": rows,
    }
    maps = {"lattice": lat, "tiles": tiles, "before": before, "after": after, "changed": ch[RENDER_K]}
    return res, maps


# ── rendering ────────────────────────────────────────────────────────────────

def _rgb(comp, r0, c0):
    t = comp[[2, 1, 0], r0:r0 + NCELL, c0:c0 + NCELL]
    return np.clip(np.nan_to_num(np.moveaxis(t, 0, -1), nan=0) / 0.3, 0, 1)


def render(site: str, tile: dict, maps: dict, share: float, why: str, out: str):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import rasterio
    from rasterio.windows import from_bounds
    x0, y1 = tile["x0"], tile["y1"]
    with rasterio.open(os.path.join(REPO, "data", "strata_packages", site, "preview.tif")) as s:
        hr = s.read(window=from_bounds(x0, y1 - TILE_M, x0 + TILE_M, y1, s.transform), boundless=True, fill_value=0)
    ch = maps["changed"][tile["r0"]:tile["r0"] + NCELL, tile["c0"]:tile["c0"] + NCELL]
    fig, ax = plt.subplots(1, 4, figsize=(16, 4.4))
    ax[0].imshow(np.moveaxis(hr[:3], 0, -1))
    ax[0].set_title("HR preview (~1 m)")
    ax[1].imshow(_rgb(maps["before"], tile["r0"], tile["c0"]), interpolation="nearest")
    ax[1].set_title("S2 earlier half (RGB, 0-0.3)")
    ax[2].imshow(_rgb(maps["after"], tile["r0"], tile["c0"]), interpolation="nearest")
    ax[2].set_title("S2 later half (RGB, 0-0.3)")
    mask = np.dstack([np.nan_to_num(ch, nan=0), np.zeros_like(ch), np.isnan(ch).astype(float)])
    ax[3].imshow(mask, interpolation="nearest")
    ax[3].set_title(f"changed at k={RENDER_K} (red); not evaluable (blue)")
    for a_ in ax:
        a_.set_xticks([]); a_.set_yticks([])
    fig.suptitle(f"{site} {tile['tile_id']} [{tile['stratum']}] -- changed share at k={RENDER_K}: "
                 f"{share:.1%} -- {why}")
    fig.tight_layout()
    fig.savefig(out, dpi=90)
    plt.close(fig)


def md_tables(results: dict) -> str:
    lines = ["# Pilot A -- change test (label-free), 2026-09-28", "",
             "Share of eligible tiles that would be dropped. Rows k (x the per-site p95 noise unit); "
             "columns: changed-cell share >= 5 / 10 / 20 %. Nothing is chosen.", ""]
    for site, r in results["sites"].items():
        nz = r["noise"]
        lines += [f"## {site}", "",
                  f"Window {r['window'][0]} .. {r['window'][1]}; {r['scenes']} scenes "
                  f"(noise halves {r['noise_split_sizes'][0]} / {r['noise_split_sizes'][1]}; chronological "
                  f"{len(r['chrono_halves']['earlier'])} / {len(r['chrono_halves']['later'])}). "
                  f"Noise units: angle {nz['angle_deg']['unit']:.3f} deg, mean reflectance "
                  f"{nz['mean_refl_diff']['unit']:.4f} (p50 {nz['angle_deg']['p50_median_over_splits']:.3f} / "
                  f"{nz['mean_refl_diff']['p50_median_over_splits']:.4f}; p99 "
                  f"{nz['angle_deg']['p99_median_over_splits']:.3f} / {nz['mean_refl_diff']['p99_median_over_splits']:.4f}). "
                  f"Non-evaluable cells: {r['cells_not_evaluable']} of {r['eligible_cells']}.", "",
                  "| Stratum | n | k | >=5% | >=10% | >=20% |", "|---|---:|---:|---:|---:|---:|"]
        for g, t in r["drop_table"].items():
            for k in KS:
                row = t[f"k{k}"]
                f = lambda v: "--" if v is None else f"{v:.0%}"
                lines.append(f"| {g} | {t['n']} | {k} | {f(row['5pct'])} | {f(row['10pct'])} | {f(row['20pct'])} |")
        lines.append("")
    return "\n".join(lines)


def main():
    from ingestion.gee_client import initialize_gee
    from labelling.common import load_config
    from pilot_b_time_window import HR_DATES
    import ee
    initialize_gee()
    ee.data.setDeadline(EE_DEADLINE_MS)
    cfg = load_config()
    results = {"ruled": "2026-09-28 redesign", "sites": {}}
    all_maps = {}
    for site, hr in HR_DATES.items():
        res, maps = run_site(site, hr, cfg)
        if res["scenes"] < MIN_SCENES:
            res["below_min_scenes"] = True
        results["sites"][site] = res
        all_maps[site] = maps
        print(site, res["scenes"], {m: round(res["noise"][m]["unit"], 4) for m in METRICS},
              res["drop_table"]["all"], res["median_check"], flush=True)

    flat = [(s, r) for s, res in results["sites"].items() for r in res["tiles"]
            if r["shares"][str(RENDER_K)] is not None]
    top = sorted(flat, key=lambda x: -x[1]["shares"][str(RENDER_K)])[:3]
    rest = [x for x in flat if x not in top]
    near = sorted(rest, key=lambda x: abs(x[1]["shares"][str(RENDER_K)] - RENDER_T))[:3]
    out_dir = os.path.join(CACHE, "renders")
    os.makedirs(out_dir, exist_ok=True)
    rendered = []
    for why, group in (("most flagged", top), (f"near k={RENDER_K} / {RENDER_T:.0%}", near)):
        for s, r in group:
            tile = next(t for t in all_maps[s]["tiles"] if t["tile_id"] == r["tile_id"])
            p = os.path.join(out_dir, f"{len(rendered) + 1}_{s}_{r['tile_id']}.png")
            render(s, tile, all_maps[s], r["shares"][str(RENDER_K)], why, p)
            rendered.append({"site": s, "tile_id": r["tile_id"], "stratum": r["stratum"], "why": why,
                             "share_k3": r["shares"][str(RENDER_K)], "png": os.path.relpath(p, REPO)})
    results["rendered"] = rendered
    with open(os.path.join(RESULTS, "pilot_a_change_test.json"), "w") as fh:
        json.dump(results, fh, indent=1)
    with open(os.path.join(RESULTS, "pilot_a_change_test.md"), "w") as fh:
        fh.write(md_tables(results))
    print(json.dumps(rendered, indent=1))


if __name__ == "__main__":
    main()
