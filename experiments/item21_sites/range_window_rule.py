"""
Item 21 §9: date-range window rule decided 2026-09-29 (round 3, decision 1).

For a site whose acquisition date is a range, the Sentinel-2 window is the
scenes within 90 d of EVERY day in the range: [range_end - 90 d,
range_start + 90 d]. This replaces "extend the range by 90 d on each side,
worst case across the range" for the §9.2 window. Rocinha keeps its recorded
181 d exception (its range exceeds 180 d, so the rule gives an empty window).

Cape Town ("2025Jan"): count the clear scenes in the new window (>= 3
needed) and rerun the frozen §9.1 change test (noise units, chronological
split, site-median de-trend, k = 3, drop above 10 %) on the site with that
window, from the cached granules; report the two Stage 1 tiles. If either
check fails the decision says STOP.

    python experiments/item21_sites/range_window_rule.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import pilot_a_change_test as pa
import pilot_a_detrended as pd_

HALF = 90
OUT = os.path.join(HERE, "results", "range_window_rule.json")


def range_window(start: str, end: str, half: int = HALF):
    """[end - half, start + half], or None when the range is longer than 2 x half."""
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    lo, hi = e - timedelta(days=half), s + timedelta(days=half)
    return None if lo > hi else (lo, hi)


def worst_gap(scene_days: list, start: str, end: str) -> int:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    rng = [s + timedelta(days=i) for i in range((e - s).days + 1)]
    return max(abs((d - h).days) for d in scene_days for h in rng)


def main():
    from labelling.common import load_config
    cfg = load_config()
    site, start, end = "cape_town", "2025-01-01", "2025-01-31"
    lo, hi = range_window(start, end)
    rec = json.load(open(os.path.join(HERE, "results", "pilot_a_change_test.json")))["sites"][site]
    dates = [d for d in rec["dates"] if lo <= date.fromisoformat(d) <= hi]
    scene_days = [date.fromisoformat(d) for d in dates]
    out = {"rule": "scenes within 90 d of every day of the range: [end - 90 d, start + 90 d]",
           "site": site, "range": [start, end], "window": [lo.isoformat(), hi.isoformat()],
           "scenes": len(dates), "dates": dates, "min_clear_scenes": cfg["open"]["max_date_gap_days"]["min_clear_scenes"],
           "worst_case_gap_days": worst_gap(scene_days, start, end),
           "rocinha_window": range_window("2024-01-01", "2024-06-30")}
    out["scene_check_passed"] = out["scenes"] >= out["min_clear_scenes"]

    # the frozen change test on this window, from the cached granules
    tiles = pa.eligible_tiles(site, cfg)
    lat = pa.lattice(tiles)
    import glob
    import collections
    by_date = collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(pa.CACHE, site, "granules", "*.npy"))):
        idx = os.path.basename(f)[:-4]
        by_date[f"{idx[:4]}-{idx[4:6]}-{idx[6:8]}"].append(f)
    arrays, groups = [], []
    for d in dates:
        if d not in by_date:
            raise RuntimeError(f"{d}: not in the granule cache")
        groups.append(list(range(len(arrays), len(arrays) + len(by_date[d]))))
        arrays += [np.load(f) for f in sorted(by_date[d])]
    stack = np.stack(arrays)
    cells = np.zeros((lat["height"], lat["width"]), bool)
    for t in tiles:
        t["r0"] = int(round((lat["y1"] - t["y1"]) / pa.CELL_M))
        t["c0"] = int(round((t["x0"] - lat["x0"]) / pa.CELL_M))
        cells[t["r0"]:t["r0"] + pa.NCELL, t["c0"]:t["c0"] + pa.NCELL] = True
    nz = pa.noise(stack, cells, groups=groups)
    units = {m: nz[m]["unit"] for m in pa.METRICS}
    ia, ib = pa.chrono_halves(len(groups))
    met = pa.cell_metrics(pa.composite(stack[pa.granules_of(groups, ia)]),
                          pa.composite(stack[pa.granules_of(groups, ib)]))
    detr, medians = pd_.detrend(met, cells)
    rows = pd_.tile_decisions(pd_.changed(detr, units, pd_.K), tiles)
    sel = json.load(open(os.path.join(REPO, "data", "stage1", "selection.json")))["sites"][site]
    stage1 = [r["chosen"]["tile_id"] for r in sel["strata"].values()]
    out.update({"granules": int(stack.shape[0]), "noise_units": units, "site_median_change": medians,
                "split": {"earlier": [dates[i] for i in ia], "later": [dates[i] for i in ib]},
                "site_summary": pd_.summarise(rows),
                "stage1_tiles": {r["tile_id"]: r for r in rows if r["tile_id"] in stage1},
                "tiles": rows})
    out["change_test_passed"] = all(r["dropped"] is False for r in out["stage1_tiles"].values())
    out["stop"] = not (out["scene_check_passed"] and out["change_test_passed"])
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({k: out[k] for k in ("window", "scenes", "granules", "worst_case_gap_days",
                                           "scene_check_passed", "change_test_passed", "stop", "rocinha_window")}))
    print("noise units", {k: round(v, 4) for k, v in units.items()})
    print("site", out["site_summary"]["all"])
    for tid, r in out["stage1_tiles"].items():
        print(tid, r["stratum"], f"{r['share']:.1%}", "dropped" if r["dropped"] else "kept")


if __name__ == "__main__":
    main()
