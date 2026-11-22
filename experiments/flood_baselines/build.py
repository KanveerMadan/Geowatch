"""
Fetch every input the comparison needs onto each dev box's cached grid.

    python -m experiments.flood_baselines.build            # all catalogue units
    python -m experiments.flood_baselines.build --only volos hanoi

Per unit, with the CURRENT production code (susceptibility/*, the same calls
harness_round4 makes):
  * all hydro layers (MERIT HAND/upa, FABDEM slope/relief, CHIRPS, IMERG,
    SoilGrids clay, JRC monthly and S1 water history) on the box grid;
  * pluvial inputs (FABDEM, design storm, impervious share) on the box grid
    plus PLUVIAL_CATCHMENT_MARGIN_M, as round 4 built them;
  * JRC GSW occurrence on the box grid (baseline 2);
  * mapped water on the box grid plus DIST_MARGIN_M: OSM waterways and water
    areas, and JRC permanent water (occurrence >= the project's existing
    JRC_PERMANENT_WATER_OCCURRENCE_PCT), as a distance in metres (baseline 3).

The reference is NOT rebuilt: flooded/valid stay the cached ones (events.py).
Results are cached per unit under CACHE; a unit already cached is skipped.
Every unit passes the registry gate (events.gate) before any fetch.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import shutil
import sys
import time
import traceback

import numpy as np

from experiments.flood_baselines import events as E
from experiments.flood_validation import references as R

CACHE = os.path.expanduser(os.environ.get("GEOWATCH_BASELINE_CACHE",
                                          "~/.cache/geowatch/flood_baselines"))
PIXEL_M = 30.0
# Distances are exact up to this margin and capped beyond it. Basis: half the
# 4 km box side, so the margin is as wide as the box's own half-width.
DIST_MARGIN_M = 2000.0
MIN_FREE_GB = 15.0            # the user's stop rule before any download
EE_STEP_TIMEOUT_S = 1800      # harness_round4's per-build deadline
# OSM water, one clause per group (Overpass appends the bbox to each).
WATER_CLAUSES = {
    "waterway_lines": 'way["waterway"~"^(river|stream|canal|drain|ditch|tidal_channel)$"]',
    "riverbank": 'way["waterway"="riverbank"]',
    "water_ways": 'way["natural"="water"]',
    "water_relations": 'relation["natural"="water"]',
}


def free_gb(path: str = os.path.expanduser("~")) -> float:
    return shutil.disk_usage(path).free / 1e9


def check_disk():
    gb = free_gb()
    if gb < MIN_FREE_GB:
        raise SystemExit(f"stop: {gb:.1f} GB free, under the {MIN_FREE_GB:g} GB rule")
    return gb


def _affine(meta):
    from affine import Affine
    t = meta["grid"]["transform"]
    return Affine(*t[:6])


def expanded(transform, shape, cells: int):
    """The same 30 m lattice grown by `cells` on every side."""
    from affine import Affine
    t = Affine(transform.a, transform.b, transform.c - cells * transform.a,
               transform.d, transform.e, transform.f - cells * transform.e)
    return t, (shape[0] + 2 * cells, shape[1] + 2 * cells)


def _call(fn, label):
    from ee_timeout import call
    return call(fn, timeout=EE_STEP_TIMEOUT_S, retries=1, label=label)


def water_mask(lonlat_bbox, transform, shape, crs, key) -> tuple:
    """(bool water raster, per-clause element counts) from OSM water features
    and nothing else. Lines are burned all-touched; closed ways and relation
    members are burned as polygons where they close, else as lines."""
    from pyproj import Transformer
    from rasterio.features import rasterize
    from shapely.geometry import LineString, Polygon, mapping
    from vector.sources import CACHE_DIR, _fetch_clause
    tr = Transformer.from_crs(4326, crs, always_xy=True)
    shapes, counts = [], {}
    for group, clause in WATER_CLAUSES.items():
        path = os.path.join(CACHE_DIR, "osm", f"{key}__water_{group}.json")
        els = _fetch_clause(clause, lonlat_bbox, path)
        counts[group] = None if els is None else len(els)
        for el in els or []:
            rings = []
            if el.get("type") == "way" and el.get("geometry"):
                rings.append(el["geometry"])
            for m in el.get("members", []) or []:
                if m.get("geometry"):
                    rings.append(m["geometry"])
            for g in rings:
                xy = [tr.transform(p["lon"], p["lat"]) for p in g]
                if len(xy) >= 4 and xy[0] == xy[-1]:
                    shapes.append(mapping(Polygon(xy)))
                    shapes.append(mapping(LineString(xy)))
                elif len(xy) >= 2:
                    shapes.append(mapping(LineString(xy)))
    if not shapes:
        return np.zeros(shape, bool), counts
    burned = rasterize(((s, 1) for s in shapes), out_shape=shape, transform=transform,
                       all_touched=True, fill=0, dtype="uint8")
    return burned.astype(bool), counts


def distance_to_water(water: np.ndarray, cap_m: float) -> np.ndarray:
    from scipy.ndimage import distance_transform_edt
    if not water.any():
        return np.full(water.shape, cap_m)
    return np.minimum(distance_transform_edt(~water) * PIXEL_M, cap_m)


def pluvial_inputs(name, year, t_box, shape_box, crs, meta_out) -> dict:
    """harness_round4._pluvial_inputs on a margin grid built by exact cell
    offsets (round 4 built it from the box centre; boxes from round 2 have
    no centre, so offsets are the general form)."""
    import ee
    from configs.pluvial_constants import PLUVIAL_CATCHMENT_MARGIN_M
    from susceptibility.hydro_rasters import compute_pixels, fetch_hydro_rasters, grid_lonlat_bounds
    from susceptibility.inputs import impervious_built_area, road_conduits
    from susceptibility.pluvial import impervious_share
    from vector.roads import load_road_layer
    k = math.ceil(PLUVIAL_CATCHMENT_MARGIN_M / PIXEL_M)
    t, shape = expanded(t_box, shape_box, k)
    outer = grid_lonlat_bounds(t, shape, crs)
    col = ee.ImageCollection("projects/sat-io/open-datasets/FABDEM").filterBounds(
        ee.Geometry.Rectangle(list(outer)))
    dem_img = (col.mosaic().setDefaultProjection(col.first().projection()).select(0)
               .resample("bilinear").rename("dem"))
    dem = compute_pixels(dem_img, t, shape, crs, f"fabdem {name}")["dem"]
    rasters = fetch_hydro_rasters(outer, t, shape, crs, year,
                                  rainfall=("rain_design_day_mm",), water_history=False)
    storm = rasters["layers"].get("rain_design_day_mm")
    if storm is None:
        raise LookupError(f"no design storm: {rasters['errors'].get('rain_design_day_mm')}")
    layer = load_road_layer(f"bl_{name}", outer)
    if layer.crs.to_string() != crs:
        raise ValueError(f"road layer CRS {layer.crs} is not the grid's {crs}")
    built = impervious_built_area(layer, t, shape)
    roads = road_conduits(layer, t, shape)
    storm_mm = float(np.nanmean(storm["raster"]))
    meta_out["pluvial_inputs"] = {
        "footprint_source": layer.footprint_source, "margin_cells": k, "margin_bbox": outer,
        "impervious": {x: built[x] for x in ("source", "method", "validation_status")},
        "conduits": {x: roads[x] for x in ("source", "method", "validation_status")},
        "design_storm_mm": storm_mm}
    return {"pl_dem": dem, "pl_imp": impervious_share(built, roads, shape),
            "pl_storm": np.array(storm_mm), "pl_window": np.array([k, k])}


def water_arrays(name, t, shape, crs) -> tuple:
    """Distance (m) to OSM water or JRC permanent water, and to OSM water
    alone, on the box grid; plus a record. `osm_complete` is False when any
    OSM clause was unavailable (never read as 'no water there')."""
    from susceptibility.hydro_rasters import grid_lonlat_bounds
    from vector.sources import bbox_key
    k = math.ceil(DIST_MARGIN_M / PIXEL_M)
    te, she = expanded(t, shape, k)
    ext_ll = grid_lonlat_bounds(te, she, crs)
    occ_ext = _call(lambda: R.jrc_occurrence(te, she, crs), f"jrc ext {name}")
    rec = {"margin_cells": k, "cap_m": k * PIXEL_M}
    try:
        osm, counts = water_mask(ext_ll, te, she, crs, bbox_key(f"bl_{name}", ext_ll))
        rec["osm_counts"] = counts
        rec["osm_complete"] = all(v is not None for v in counts.values())
    except Exception as e:     # noqa: BLE001 -- recorded; the JRC part still stands
        osm, rec["osm_error"] = np.zeros(she, bool), f"{type(e).__name__}: {e}"
        rec["osm_complete"] = False
    perm = ~R.not_permanent(occ_ext)
    rec["osm_cells"], rec["jrc_perm_cells"] = int(osm.sum()), int(perm.sum())
    crop = lambda a: a[k:k + shape[0], k:k + shape[1]]      # noqa: E731
    return ({"dist_water_m": crop(distance_to_water(osm | perm, k * PIXEL_M)),
             "dist_water_osm_only_m": crop(distance_to_water(osm, k * PIXEL_M))}, rec)


def refresh_water(name: str) -> dict:
    """Recompute only the distance arrays of a cached unit (OSM retried;
    cached clauses are reused, unavailable ones are fetched again)."""
    b = load(name)
    m = b["meta"]
    w, rec = water_arrays(name, _affine(m), tuple(m["grid"]["shape"]), m["grid"]["crs"])
    b["arrays"].update(w)
    b["meta"]["dist"] = rec
    save(name, b)
    return rec


def build_unit(entry: dict) -> dict:
    from susceptibility.hydro_rasters import fetch_hydro_rasters, grid_lonlat_bounds
    from vector.sources import bbox_key
    m = entry["meta"]
    name = entry["unit"]
    crs = m["grid"]["crs"]
    t = _affine(m)
    shape = tuple(m["grid"]["shape"])
    ref = E.reference(entry)
    if ref["flooded"].shape != shape:
        raise ValueError(f"{name}: cached grid {shape} != reference {ref['flooded'].shape}")
    year = datetime.date.fromisoformat(m["event"]).year
    box_ll = grid_lonlat_bounds(t, shape, crs)
    meta = {"unit": name, "source_file": entry["path"], "round": entry["round"],
            "split": entry["split"], "event": m["event"], "ref_year": year,
            "grid": m["grid"], "box_lonlat": box_ll, "errors": {}}
    arrays = {}
    # 1. hydro layers, all of them, on the box grid
    r = _call(lambda: fetch_hydro_rasters(box_ll, t, shape, crs, year, rainfall=True,
                                          water_history=True), f"rasters {name}")
    arrays.update({f"layer_{k}": v["raster"] for k, v in r["layers"].items()})
    meta["raster_errors"] = r["errors"]
    # 2. JRC occurrence on the box grid
    arrays["jrc_occurrence"] = _call(lambda: R.jrc_occurrence(t, shape, crs), f"jrc {name}")
    # 3. distance to mapped water on box + margin
    w_arrays, meta["dist"] = water_arrays(name, t, shape, crs)
    arrays.update(w_arrays)
    # 4. pluvial inputs: a separate pass (--pluvial), one subprocess per unit
    meta["errors"]["pluvial"] = "not yet built (run --pluvial)"
    return {"arrays": arrays, "meta": meta}


PLUVIAL_KEYS = ("pl_dem", "pl_imp", "pl_storm", "pl_window")
# A subprocess per unit with a hard kill: ee_timeout abandons a slow call
# but cannot stop its thread, so in-process timeouts would pile up threads.
# One hour = twice round 4's per-build deadline (Hanoi's footprints step
# overran 1800 s in the test build).
PLUVIAL_KILL_S = 3600


def _round4_pluvial(entry: dict):
    """The unit's round-4 cached pluvial inputs if round 4 built pluvial on
    this very box (same code path, same box), else None."""
    for rnd, split, module in entry["uses"]:
        if rnd == "round4" and module == "pluvial":
            p = os.path.join(R.CACHE, "round4", split, f"pluvial__{entry['unit']}.npz")
            z = np.load(p, allow_pickle=False)
            if json.loads(str(z["meta"]))["bbox"] == entry["meta"]["bbox"]:
                return {k: z[k] for k in PLUVIAL_KEYS}, p
    return None


LOCK_DIR = os.path.join(CACHE, "locks")


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def try_lock(name: str) -> bool:
    """Take the unit's lock (O_EXCL). A lock whose holder process is dead
    (e.g. killed at PLUVIAL_KILL_S) is stale and is taken over."""
    os.makedirs(LOCK_DIR, exist_ok=True)
    p = os.path.join(LOCK_DIR, f"{name}.lock")
    for _ in range(2):
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                holder = int(open(p).read().strip() or 0)
            except (OSError, ValueError):
                holder = 0
            if holder and _pid_alive(holder):
                return False
            try:
                os.remove(p)          # stale
            except FileNotFoundError:
                pass
    return False


def unlock(name: str):
    try:
        os.remove(os.path.join(LOCK_DIR, f"{name}.lock"))
    except FileNotFoundError:
        pass


def has_pluvial(name: str) -> bool:
    return os.path.exists(path(name)) and "pl_dem" in np.load(path(name)).files


def pluvial_one(name: str, wait: bool = True) -> dict:
    """Build and store one unit's pluvial inputs (run inside a subprocess).

    Two workers may run at once (pluvial_pass forward, pluvial_reverse
    backward). The unit lock keeps them off the same unit. With `wait`, a
    unit locked by the other worker is waited for, never rebuilt: success
    returns, failure raises (one attempt per unit, as planned)."""
    import vector.sources as VS
    VS.OVERPASS_WORKERS = 1          # two workers x 1 = the project's limit of 2
    while not try_lock(name):
        if not wait:
            raise RuntimeError(f"{name}: locked by the other worker")
        time.sleep(15)
    try:
        if has_pluvial(name):
            return {"built_by": "the other worker"}
        mark = os.path.join(LOCK_DIR, f"{name}.attempted")
        if os.path.exists(mark):
            # The other worker started this unit and did not finish it (it was
            # killed at PLUVIAL_KILL_S or failed): one attempt per unit.
            prior = load(name)["meta"].get("errors", {}).get("pluvial", "")
            raise RuntimeError(f"{name}: already attempted by the other worker "
                               f"(pid {open(mark).read()}): {prior[:250]} -- not retried "
                               "(one attempt per unit)")
        with open(mark, "w") as fh:
            fh.write(str(os.getpid()))
        return _pluvial_build(name)
    finally:
        unlock(name)


def _pluvial_build(name: str) -> dict:
    entry = next(c for c in E.catalogue() if c["unit"] == name)
    b = load(name)
    m = b["meta"]
    reuse = _round4_pluvial(entry)
    if reuse is not None:
        arrays, src = reuse
        m["pluvial_inputs"] = {"reused_from": src}
    else:
        arrays = pluvial_inputs(name, m["ref_year"], _affine(m), tuple(m["grid"]["shape"]),
                                m["grid"]["crs"], m)
    b["arrays"].update(arrays)
    m["errors"].pop("pluvial", None)
    save(name, b)
    return m.get("pluvial_inputs", {})


def pluvial_pass(names: list) -> dict:
    import subprocess
    out = {}
    for name in names:
        if not os.path.exists(path(name)) or "pl_dem" in np.load(path(name)).files:
            continue
        check_disk()
        print(f"── {name}: pluvial", flush=True)
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, "-m", "experiments.flood_baselines.build",
                                "--pluvial-one", name], timeout=PLUVIAL_KILL_S,
                               capture_output=True, text=True)
            ok = r.returncode == 0
            tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        except subprocess.TimeoutExpired:
            ok, tail = False, [f"killed after {PLUVIAL_KILL_S} s"]
        if not ok:
            b = load(name)
            b["meta"]["errors"]["pluvial"] = " | ".join(tail)[-400:]
            save(name, b)
        out[name] = {"ok": ok, "s": round(time.time() - t0), "tail": tail}
        print(f"   {name}: {json.dumps(out[name])[:400]}", flush=True)
    return out


def pluvial_reverse(names: list, floor: str | None = None) -> dict:
    """The second pluvial worker: from the END of the list backwards, until
    it meets a unit the forward pass has done, holds or attempted. It never
    waits and never retries; the forward pass (pluvial_pass) still visits
    every unit afterwards and waits on any unit this worker holds."""
    import subprocess
    out = {}
    for name in reversed(names):
        if floor is not None and name <= floor:
            print(f"── {name}: at or below the floor {floor!r}; second worker stops", flush=True)
            break
        if not os.path.exists(path(name)):
            continue
        err = load(name)["meta"].get("errors", {}).get("pluvial")
        tried = err is not None and not err.startswith("not yet built")
        if tried or has_pluvial(name) or os.path.exists(os.path.join(LOCK_DIR, f"{name}.lock")) \
                or os.path.exists(os.path.join(LOCK_DIR, f"{name}.attempted")):
            print(f"── {name}: met the forward pass; second worker stops", flush=True)
            break
        check_disk()
        print(f"── {name}: pluvial (second worker)", flush=True)
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, "-m", "experiments.flood_baselines.build",
                                "--pluvial-one-nowait", name], timeout=PLUVIAL_KILL_S,
                               capture_output=True, text=True)
            ok = r.returncode == 0
            tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        except subprocess.TimeoutExpired:
            ok, tail = False, [f"killed after {PLUVIAL_KILL_S} s"]
            unlock(name)            # the killed child could not release it
        if not ok and any("locked by the other worker" in t for t in tail):
            print(f"── {name}: taken by the forward pass; second worker stops", flush=True)
            break
        if not ok:
            b = load(name)
            b["meta"]["errors"]["pluvial"] = " | ".join(tail)[-400:]
            save(name, b)
        out[name] = {"ok": ok, "s": round(time.time() - t0), "tail": tail}
        print(f"   {name}: {json.dumps(out[name])[:400]}", flush=True)
    return out


def qualifies(entry: dict) -> bool:
    """The rounds' rule on the cached reference alone (>= 50 flooded and
    >= 50 dry evaluation cells), before any score exists."""
    from experiments.flood_validation.harness import MIN_DRY_CELLS, MIN_FLOODED_CELLS
    ref = E.reference(entry)
    f, v = ref["flooded"], ref["valid"]
    if ref["block"] > 1:
        _, f, v = R.blocks(np.zeros(f.shape), f, v, ref["block"])
    return int((f & v).sum()) >= MIN_FLOODED_CELLS and int((~f & v).sum()) >= MIN_DRY_CELLS


def path(name):
    return os.path.join(CACHE, f"{name}.npz")


def save(name, built):
    os.makedirs(CACHE, exist_ok=True)
    tmp = path(name) + f".tmp{os.getpid()}.npz"
    np.savez_compressed(tmp, **built["arrays"],
                        meta=np.array(json.dumps(built["meta"], default=str)))
    os.replace(tmp, path(name))


def load(name):
    z = np.load(path(name), allow_pickle=False)
    return {"arrays": {k: z[k] for k in z.files if k != "meta"},
            "meta": json.loads(str(z["meta"]))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--refresh-water", action="store_true",
                    help="cached units whose OSM water was incomplete: redo distances only")
    ap.add_argument("--pluvial", action="store_true",
                    help="build pluvial inputs for cached units, one subprocess each")
    ap.add_argument("--pluvial-one", help=argparse.SUPPRESS)
    ap.add_argument("--pluvial-one-nowait", help=argparse.SUPPRESS)
    ap.add_argument("--pluvial-reverse", action="store_true",
                    help="second pluvial worker, from the end of the list backwards")
    ap.add_argument("--reverse-floor", help="the second worker never touches this unit "
                    "or any unit sorted before it")
    ap.add_argument("--qualifying", action="store_true",
                    help="only units whose cached reference qualifies (>= 50/50 cells)")
    args = ap.parse_args(argv)
    print(f"free disk {check_disk():.1f} GB", flush=True)
    import ee
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    ee.data.setDeadline(R.EE_TIMEOUT_S * 1000)
    if args.pluvial_one:
        print(json.dumps(pluvial_one(args.pluvial_one), default=str)[:300], flush=True)
        return 0
    if args.pluvial_one_nowait:
        print(json.dumps(pluvial_one(args.pluvial_one_nowait, wait=False), default=str)[:300],
              flush=True)
        return 0
    cat = E.catalogue()
    if args.only:
        cat = [c for c in cat if c["unit"] in set(args.only)]
    if args.qualifying:
        cat = [c for c in cat if qualifies(c)]
    if args.pluvial_reverse:
        log = pluvial_reverse([c["unit"] for c in cat], args.reverse_floor)
        with open(os.path.join(CACHE, f"pluvial_reverse_log_{int(time.time())}.json"), "w") as fh:
            json.dump(log, fh, indent=1, default=str)
        return 0
    if args.pluvial:
        log = pluvial_pass([c["unit"] for c in cat])
        with open(os.path.join(CACHE, f"pluvial_log_{int(time.time())}.json"), "w") as fh:
            json.dump(log, fh, indent=1, default=str)
        return 0
    if args.refresh_water:
        for c in cat:
            if os.path.exists(path(c["unit"])) and \
                    not load(c["unit"])["meta"].get("dist", {}).get("osm_complete", False):
                print(f"── {c['unit']}: refresh water", flush=True)
                print("  ", json.dumps(refresh_water(c["unit"]), default=str), flush=True)
        return 0
    log = {}
    for c in cat:
        name = c["unit"]
        if os.path.exists(path(name)):
            print(f"── {name}: cached", flush=True)
            continue
        check_disk()
        t0 = time.time()
        print(f"── {name}: build ({c['round']}/{c['split']})", flush=True)
        try:
            b = build_unit(c)
            save(name, b)
            log[name] = {"ok": True, "s": round(time.time() - t0), "errors": b["meta"]["errors"],
                         "raster_errors": b["meta"]["raster_errors"]}
        except Exception as e:     # noqa: BLE001 -- named, then the next unit
            traceback.print_exc()
            log[name] = {"ok": False, "s": round(time.time() - t0),
                         "error": f"{type(e).__name__}: {e}"}
        print(f"   {name}: {json.dumps(log[name], default=str)[:400]}", flush=True)
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, f"build_log_{int(time.time())}.json"), "w") as fh:
        json.dump(log, fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
