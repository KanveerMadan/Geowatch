"""
Item 21 §9 pilot A rerun with the change-test fix decided 2026-09-29, from
the cached granules (no Earth Engine calls).

Rule (decision 2): before thresholding, subtract the site-wide median
per-cell change of each metric from every cell; a cell is changed if its
de-trended change exceeds k x noise unit on either metric; k = 3; a tile is
dropped if MORE THAN 10 % of its (evaluable) cells are changed.

  de-trended angle  = angle_deg      - median(angle_deg over the site's eligible cells)
  de-trended refl.  = mean_refl_diff - median(mean_refl_diff over the same cells)

Window, noise units, composites and the chronological split are unchanged
from pilot_a_change_test.py; the noise units are recomputed from the same
granules and checked against the recorded ones.

Sensitivity only (not the rule): the metric above is an unsigned magnitude,
so subtracting its median also lowers every cell when there is no trend, and
cannot see a cell that changed AGAINST the site trend. The signed variant for
brightness, |d - median(d)| with d = mean6(later) - mean6(earlier), is
reported beside it.

    python experiments/item21_sites/pilot_a_detrended.py
"""

from __future__ import annotations

import collections
import glob
import json
import os
import sys
import warnings

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import pilot_a_change_test as pa

K = 3
DROP_ABOVE = 0.10
STOP_IF_SITE_DROPS_ABOVE = 0.30
RECORDED = os.path.join(HERE, "results", "pilot_a_change_test.json")
OUT = os.path.join(HERE, "results", "pilot_a_detrended.json")


def detrend(met: dict, cells: np.ndarray) -> dict:
    """Subtract each metric's median over the eligible, evaluable cells."""
    out, med = {}, {}
    for m, v in met.items():
        vals = v[cells & np.isfinite(v)]
        med[m] = float(np.median(vals)) if vals.size else float("nan")
        out[m] = v - med[m]
    return out, med


def changed(detr: dict, units: dict, k: float) -> np.ndarray:
    """1 changed / 0 not / NaN not evaluable: EITHER de-trended metric > k x unit."""
    valid = np.isfinite(detr["angle_deg"]) & np.isfinite(detr["mean_refl_diff"])
    ch = (detr["angle_deg"] > k * units["angle_deg"]) | (detr["mean_refl_diff"] > k * units["mean_refl_diff"])
    return np.where(valid, ch.astype(float), np.nan)


def signed_brightness(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        d = np.nanmean(after, 0) - np.nanmean(before, 0)
    valid = np.isfinite(before).all(0) & np.isfinite(after).all(0)
    return np.where(valid, d, np.nan)


def tile_decisions(ch: np.ndarray, tiles: list) -> list:
    rows = []
    for t in tiles:
        s = pa.tile_share(ch, t["r0"], t["c0"])
        rows.append({"tile_id": t["tile_id"], "stratum": t["stratum"], "evaluable": s["evaluable"],
                     "changed": s["changed"], "share": s["share"],
                     "dropped": None if s["share"] is None else s["share"] > DROP_ABOVE})
    return rows


def summarise(rows: list) -> dict:
    groups = {"all": rows}
    for r in rows:
        groups.setdefault(r["stratum"], []).append(r)
    out = {}
    for g, rs in groups.items():
        ok = [r for r in rs if r["dropped"] is not None]
        out[g] = {"n": len(rs), "no_evaluable": len(rs) - len(ok),
                  "dropped": sum(r["dropped"] for r in ok),
                  "drop_share": round(sum(r["dropped"] for r in ok) / len(ok), 4) if ok else None}
    return out


def cached_stack(site: str, dates: list) -> tuple:
    """Granules from the pilot A cache, grouped by acquisition date (the
    system:index starts YYYYMMDD), limited to the recorded window dates."""
    files = sorted(glob.glob(os.path.join(pa.CACHE, site, "granules", "*.npy")))
    by_date = collections.defaultdict(list)
    for f in files:
        idx = os.path.basename(f)[:-4]
        d = f"{idx[:4]}-{idx[4:6]}-{idx[6:8]}"
        by_date[d].append(f)
    missing = [d for d in dates if d not in by_date]
    extra = sorted(set(by_date) - set(dates))
    if missing or extra:
        raise RuntimeError(f"{site}: cache does not match the recorded dates (missing {missing}, extra {extra})")
    arrays, groups = [], []
    for d in dates:
        groups.append(list(range(len(arrays), len(arrays) + len(by_date[d]))))
        arrays += [np.load(f) for f in sorted(by_date[d])]
    return np.stack(arrays), groups


def run_site(site: str, rec: dict, cfg: dict) -> dict:
    tiles = pa.eligible_tiles(site, cfg)
    lat = pa.lattice(tiles)
    stack, groups = cached_stack(site, rec["dates"])
    assert stack.shape[0] == rec["granules"], (site, stack.shape[0], rec["granules"])
    cells = np.zeros((lat["height"], lat["width"]), bool)
    for t in tiles:
        t["r0"] = int(round((lat["y1"] - t["y1"]) / pa.CELL_M))
        t["c0"] = int(round((t["x0"] - lat["x0"]) / pa.CELL_M))
        cells[t["r0"]:t["r0"] + pa.NCELL, t["c0"]:t["c0"] + pa.NCELL] = True

    nz = pa.noise(stack, cells, groups=groups)
    units = {m: nz[m]["unit"] for m in pa.METRICS}
    for m in pa.METRICS:                                   # same granules, same seeds -> same units
        assert abs(units[m] - rec["noise"][m]["unit"]) <= 1e-9 * max(1.0, abs(units[m])), (site, m)
    ia, ib = pa.chrono_halves(len(groups))
    before = pa.composite(stack[pa.granules_of(groups, ia)])
    after = pa.composite(stack[pa.granules_of(groups, ib)])
    met = pa.cell_metrics(before, after)
    detr, medians = detrend(met, cells)
    rows = tile_decisions(changed(detr, units, K), tiles)

    # sensitivity: signed brightness de-trend (angle as in the rule)
    d = signed_brightness(before, after)
    dmed = float(np.median(d[cells & np.isfinite(d)]))
    sens = {"angle_deg": detr["angle_deg"], "mean_refl_diff": np.abs(d - dmed)}
    rows_signed = tile_decisions(changed(sens, units, K), tiles)
    # for comparison: the same k / threshold WITHOUT de-trending
    rows_raw = tile_decisions(changed(met, units, K), tiles)

    return {"scenes": len(groups), "granules": int(stack.shape[0]), "noise_units": units,
            "site_median_change": medians, "signed_brightness_median": dmed,
            "rule": summarise(rows), "sensitivity_signed_brightness": summarise(rows_signed),
            "without_detrend": summarise(rows_raw), "tiles": rows}


def main():
    from labelling.common import load_config
    cfg = load_config()
    with open(RECORDED) as fh:
        recorded = json.load(fh)["sites"]
    out = {"rule": {"k": K, "drop_if_changed_share_above": DROP_ABOVE,
                    "detrend": "subtract the site-wide median per-cell change of each metric"},
           "stop_if_any_site_drops_above": STOP_IF_SITE_DROPS_ABOVE, "sites": {}}
    for site, rec in recorded.items():
        r = run_site(site, rec, cfg)
        out["sites"][site] = r
        a, sg, raw = r["rule"]["all"], r["sensitivity_signed_brightness"]["all"], r["without_detrend"]["all"]
        print(f"{site:10s} rule {a['dropped']:3d}/{a['n']:3d} = {a['drop_share']:.1%} | signed "
              f"{sg['drop_share']:.1%} | no detrend {raw['drop_share']:.1%} | medians "
              f"{r['site_median_change']['angle_deg']:.2f} deg / {r['site_median_change']['mean_refl_diff']:.4f}",
              flush=True)
    worst = max(out["sites"].items(), key=lambda kv: kv[1]["rule"]["all"]["drop_share"] or 0)
    out["stop"] = (worst[1]["rule"]["all"]["drop_share"] or 0) > STOP_IF_SITE_DROPS_ABOVE
    out["worst_site"] = {"site": worst[0], "drop_share": worst[1]["rule"]["all"]["drop_share"]}
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    print("STOP" if out["stop"] else "no site above 30 %", out["worst_site"])


if __name__ == "__main__":
    main()
