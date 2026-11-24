"""
Round 3 (R32): prefetch the IMERG heavy-rain layer (`rain_intensity_mm_h`, 10-year 99.9th percentile) for the
Sentinel-1-route DEV target units, many requests at once, cached per native cell.

Why not an Earth Engine batch export: the project has no asset root (createAsset refused) and no Drive / Cloud
Storage destination is set up (owner decision). This sends the same per-unit computePixels request the builder
would send (the unit's own deg-aligned native window, same image from hydro_rasters._rain_images), but in a
thread pool ahead of the builders. Same cells, same values; tilecache_r3 then reads them per cell.

    python -m experiments.flood_round3.imerg_prefetch [workers]
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import os
import sys
import time

import numpy as np

CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/tilecache/imerg_cells")


def cell_path(year):
    return os.path.join(CACHE, f"{year}.json")


def load_cells(year):
    p = cell_path(year)
    return json.load(open(p)) if os.path.exists(p) else {}


def save_cells(year, add):
    os.makedirs(CACHE, exist_ok=True)
    cur = load_cells(year)
    cur.update(add)
    json.dump(cur, open(cell_path(year) + ".part", "w"))
    os.replace(cell_path(year) + ".part", cell_path(year))


def unit_window(meta):
    from affine import Affine
    from susceptibility import hydro_rasters as HR
    g = meta["grid"]
    deg = HR.RAIN_NATIVE_DEG[HR.IMERG_LAYER]
    x0, y1, cols, rows = HR.native_grid(HR.grid_lonlat_bounds(Affine(*g["transform"][:6]), tuple(g["shape"]), g["crs"]), deg)
    return x0, y1, cols, rows, deg


def fetch_unit(n, meta):
    import ee
    from ee_timeout import call
    from rasterio.transform import from_origin
    from susceptibility import hydro_rasters as HR
    year = dt.date.fromisoformat(meta["event"]).year
    x0, y1, cols, rows, deg = unit_window(meta)
    c0, r0 = int(round(x0 / deg)), int(round(y1 / deg))
    have = load_cells(year)
    keys = [f"{c0 + c},{r0 - r - 1}" for r in range(rows) for c in range(cols)]
    if all(k in have for k in keys):
        return n, "cached", 0.0
    img = HR._rain_images(year)[HR.IMERG_LAYER]
    t0 = time.time()
    arr = call(lambda: ee.data.computePixels({
        "expression": img.unmask(HR.NODATA).toFloat(), "fileFormat": "NUMPY_NDARRAY",
        "grid": HR.ee_grid(from_origin(x0, y1, deg, deg), (rows, cols), "EPSG:4326")}),
        timeout=HR.IMERG_DEADLINE_S, retries=HR.IMERG_RETRIES, label=f"imerg {n}")
    v = np.where(arr[HR.IMERG_LAYER] == HR.NODATA, np.nan, arr[HR.IMERG_LAYER]).astype(np.float64)
    add = {f"{c0 + c},{r0 - r - 1}": (None if np.isnan(v[r, c]) else float(v[r, c])) for r in range(rows) for c in range(cols)}
    return n, add, time.time() - t0, year


def targets():
    """The target DEV units still without a table, in the builder's round-robin order."""
    from experiments.flood_round3 import build_r3 as B
    return B.s1route_order(only_missing=True)


def main(argv=None):
    from ingestion.gee_client import initialize_gee
    from experiments.flood_round3 import build_r3 as B
    initialize_gee()
    a = argv or sys.argv[1:]
    workers = int(a[0]) if a else 6
    units = targets()
    print(len(units), "target units to prefetch with", workers, "workers", flush=True)
    metas = {n: json.loads(str(np.load(os.path.join(B.REFS, f"{n}.npz"))["meta"])) for n in units}
    done = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(fetch_unit, n, metas[n]): n for n in units}
        for f in cf.as_completed(futs):
            n = futs[f]
            try:
                r = f.result()
            except Exception as e:          # noqa: BLE001
                print(n, "FAILED", type(e).__name__, str(e)[:150], flush=True)
                continue
            if r[1] != "cached":
                save_cells(r[3], r[1])
            done += 1
            print(n, "ok" if r[1] != "cached" else "cached", round(r[2]), f"{done}/{len(units)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
