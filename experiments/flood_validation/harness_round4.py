"""
Flood validation round 4 (flood taxonomy M1-M4). Pre-registered in
PREREGISTRATION_ROUND4.md; the events, methods, grids, rule and bar below
match it.

Order: (1) build the TUNING events and choose each new method's parameters on
them; (2) only then build the TEST events and score each ONCE with the chosen
parameters. Fluvial runs its validated configuration and is not tuned.

    python -m experiments.flood_validation.harness_round4            # fetch + evaluate
    python -m experiments.flood_validation.harness_round4 --evaluate # cached events only
    python -m experiments.flood_validation.harness_round4 --tuning-only

Inputs and references are cached per event (npz) under references.CACHE/round4.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
import traceback

import numpy as np

from experiments.flood_validation import harness_round2 as H2
from experiments.flood_validation import references as R
from experiments.flood_validation.harness import AUC_MIN, MIN_DRY_CELLS, MIN_FLOODED_CELLS

HERE = os.path.dirname(os.path.abspath(__file__))
PREREG = os.path.join(HERE, "PREREGISTRATION_ROUND4.md")
RESULT = os.path.join(HERE, "result_round4_2026-10-30.json")
ROUND3_RESULT = os.path.join(HERE, "result_round3_2026-10-29.json")
CACHE = os.path.join(R.CACHE, "round4")
BOX_SIDE_M = 4000.0
S1_SEARCH_SIDE_M = 20000.0
EE_STEP_TIMEOUT_S = 1800          # one event's whole build (several EE calls)
MODULES = ("fluvial", "pluvial", "waterlogging", "flash_flood")


# ── the pre-registered events ──────────────────────────────────────────

def _s1(lat, lon, event):
    return {"ref": ("s1",), "search_centre": (lat, lon), "event": event}


def _ems(code, aoi, mon, event, kind="DEL"):
    return {"ref": ("ems", code, aoi, mon, kind), "event": event}


def _unosat(key, event):
    return {"ref": ("unosat", key), "event": event}


BIHAR = _s1(25.45, 87.25, "2026-09-11")            # Kursela, Katihar
ASSAM = _s1(26.917, 94.733, "2026-07-20")          # Nazira, Sivasagar
VALENCIA = _ems("EMSR773", 3, 0, "2024-10-29")     # Horta Sud
TEST_EVENTS = {
    "fluvial": {"bihar_2026": BIHAR, "assam_2026": ASSAM,
                "pakistan_2022": _unosat("FL20220808PAK_S2_20220831", "2022-08-31")},
    "pluvial": {"chennai_2023": {"ref": ("none",), "event": "2023-12-04",
                                 "not_run": "no usable reference: no Sentinel-1 image from day 0 "
                                            "to +21, no EMS or UNOSAT product; NRSC's RISAT-1A "
                                            "map of 2023-12-07 exists only as a PDF "
                                            "(pre-registered)"},
                "dubai_2024": _s1(25.2048, 55.2708, "2024-04-16"),
                "valencia_2024": VALENCIA},
    "waterlogging": {"assam_2026": ASSAM,
                     "sylhet_2022": _unosat("FL20220525BGD_RCM1_20220618", "2022-06-18"),
                     "kerala_2018": _s1(9.417, 76.433, "2018-08-16")},   # Mankombu, Kuttanad
    "flash_flood": {"valencia_2024": VALENCIA,
                    "himachal_2023": _s1(31.958, 77.110, "2023-07-10"),  # Kullu, Beas
                    "derna_2023": _ems("EMSR696", 1, 0, "2023-09-11", "GRA")},
}
# Round 3's boxes, re-used exactly (centres read from its result file).
TUNING_EVENTS = {
    "pluvial": ("hai_phong", "milagro", "belize_city"),
    "waterlogging": ("thai_binh", "nam_dinh"),
    "flash_flood": ("volos", "kastelli", "choloma"),
}


def tuning_events() -> dict:
    """{module: {name: event}} with round 3's centres, boxes and references."""
    with open(ROUND3_RESULT) as fh:
        r3 = json.load(fh)["modules"]
    out = {}
    for module, names in TUNING_EVENTS.items():
        out[module] = {}
        for n in names:
            src = r3[module]["events"][n]
            ref = H2.EVENTS[module][n]["ref"]
            lat, lon = src["centre"]
            out[module][n] = {"ref": ("ems", *ref[1:], "DEL"), "event": src["event"],
                              "centre": (lat, lon),
                              "bbox": R.square_bbox(lat, lon, BOX_SIDE_M)}
    return out


def check_disjoint(test: dict, tuning: dict) -> None:
    """No tuning event is a test event (pre-registered)."""
    test_names = {n for evs in test.values() for n in evs}
    tune_names = {n for evs in tuning.values() for n in evs}
    if test_names & tune_names:
        raise ValueError(f"tuning events used as test events: {test_names & tune_names}")


# ── pure: the box rule and grids ────────────────────────────────────────

def s1_flood_centre(flooded, valid, transform, crs: str):
    """(lat, lon): the area-weighted centroid of the flooded valid cells (cell
    centres, equal area), or the nearest flooded cell centre if the centroid's
    cell is not flooded. None if no cell is flooded."""
    from pyproj import Transformer
    f = np.asarray(flooded, bool) & np.asarray(valid, bool)
    if not f.any():
        return None
    r, c = np.nonzero(f)
    xs, ys = transform * (c + 0.5, r + 0.5)
    x, y = float(np.mean(xs)), float(np.mean(ys))
    col, row = ~transform * (x, y)
    ri, ci = int(np.floor(row)), int(np.floor(col))
    if not (0 <= ri < f.shape[0] and 0 <= ci < f.shape[1] and f[ri, ci]):
        k = int(np.argmin((xs - x) ** 2 + (ys - y) ** 2))
        x, y = float(xs[k]), float(ys[k])
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(x, y)
    return round(lat, 6), round(lon, 6)


def window_in(outer_t, outer_shape, inner_t, inner_shape):
    """(row0, col0) of an inner grid inside an outer one on the same 30 m
    lattice and CRS. Raises if it does not fit exactly."""
    px = outer_t.a
    c0 = (inner_t.c - outer_t.c) / px
    r0 = (outer_t.f - inner_t.f) / px
    if abs(c0 - round(c0)) > 1e-6 or abs(r0 - round(r0)) > 1e-6:
        raise ValueError("grids are not on one lattice")
    r0, c0 = int(round(r0)), int(round(c0))
    if r0 < 0 or c0 < 0 or r0 + inner_shape[0] > outer_shape[0] \
            or c0 + inner_shape[1] > outer_shape[1]:
        raise ValueError("inner grid is not inside the outer one")
    return r0, c0


def crop(a, r0, c0, shape):
    return np.asarray(a)[r0:r0 + shape[0], c0:c0 + shape[1]]


# ── pure: scoring and choice ────────────────────────────────────────────

def score_event(module: str, arrays: dict, params):
    """The module's score on the event's box grid with `params`."""
    from susceptibility import flash_flood, fluvial, pluvial, waterlogging
    rasters = H2._rasters_from(arrays)
    if module == "fluvial":
        return fluvial.combine(fluvial.components(rasters))
    if module == "flash_flood":
        return flash_flood.combine(flash_flood.components(rasters), params)
    if module == "waterlogging":
        return waterlogging.combine(waterlogging.components(rasters), params)
    comps = pluvial.components(arrays["pl_dem"], arrays["pl_imp"], float(arrays["pl_storm"]),
                               params["c_perv"])
    m = pluvial.combine(comps, params["weights"])
    r0, c0 = (int(v) for v in arrays["pl_window"])
    return crop(m, r0, c0, arrays["flooded"].shape)


def choose(module: str, grid: list, default, built: dict) -> dict:
    """Round 2's rule: the highest mean within-event AUC over qualifying tuning
    events; ties to the default if among them, else first in grid order."""
    table = []
    for p in grid:
        ev = {n: H2.event_auc(score_event(module, b["arrays"], p), b["arrays"]["flooded"],
                              b["arrays"]["valid"], 1) for n, b in built.items()}
        table.append({"params": p, "mean_auc": H2.mean_auc(list(ev.values())),
                      "per_event": {n: e["auc"] for n, e in ev.items()},
                      "cells": {n: [e["flooded_cells"], e["dry_cells"]] for n, e in ev.items()}})
    scored = [t for t in table if t["mean_auc"] is not None]
    if not scored:
        return {"chosen": default, "reason": "no qualifying tuning event; default kept",
                "table": table}
    best = max(t["mean_auc"] for t in scored)
    tied = [t["params"] for t in scored if t["mean_auc"] == best]
    chosen = default if default in tied else tied[0]
    return {"chosen": chosen, "best_tuning_mean_auc": best, "table": table,
            "reason": "default among the tied best" if chosen == default and len(tied) > 1
            else "highest tuning mean"}


def grids() -> dict:
    from configs import flash_flood_constants as ffc, pluvial_constants as pc
    from configs import waterlogging_constants as wc
    return {"pluvial": (pc.PLUVIAL_PARAM_GRID, pc.PLUVIAL_PARAM_DEFAULT),
            "waterlogging": (wc.WATERLOGGING_R4_WEIGHT_GRID, wc.WATERLOGGING_R4_WEIGHTS),
            "flash_flood": (ffc.FLASH_POWER_PARAM_GRID, ffc.FLASH_POWER_PARAMS)}


def evaluate_test(module: str, built: dict, params) -> dict:
    held, pooled, dropped = {}, [], {}
    for n, b in built.items():
        if "arrays" not in b:
            dropped[n] = b.get("error", "not built")
            continue
        a = b["arrays"]
        score = score_event(module, a, params)
        held[n] = H2.event_auc(score, a["flooded"], a["valid"], 1)
        if held[n]["qualifies"]:
            pooled.append(R.cells(score, a["flooded"], a["valid"], 1))
    return {"dropped": dropped, "held_out_per_event": held, "held_out": H2.heldout_verdict(held),
            "pooled_held_out_auc_diagnostic": H2.pooled_auc(pooled), "params_used": params}


# ── fetching ───────────────────────────────────────────────────────────

def _call(fn, label):
    from ee_timeout import call
    return call(fn, timeout=EE_STEP_TIMEOUT_S, retries=1, label=label)


def place(ev: dict) -> dict:
    """The event with its centre and 4 km box, by the box rule (reference only)."""
    from susceptibility.hydro_rasters import utm_grid
    if "bbox" in ev or ev["ref"][0] == "none":
        return ev
    kind = ev["ref"][0]
    if kind == "ems":
        _, code, aoi, mon, typ = ev["ref"]
        product = R.ems_product(code, aoi, mon, typ)
        polys, _, _ = R.ems_polygons(product)
        centre = _centre_cached(f"ems_{code}_{aoi}_{mon}_{typ}",
                                lambda: _flood_centre(polys, product["extent"]))
        extra = {}
    elif kind == "unosat":
        centre = _centre_cached(f"unosat_{ev['ref'][1]}", lambda: _flood_centre(
            *(lambda p: (p["polygons"], p["extent"]))(R.unosat_product(ev["ref"][1]))))
        extra = {}
    else:
        lat, lon = ev["search_centre"]
        square = R.square_bbox(lat, lon, S1_SEARCH_SIDE_M)
        pas = _call(lambda: R.s1_event_pass(square, ev["event"]), "s1 pass")
        t, shape, crs = utm_grid(square)
        ref = _call(lambda: R.s1_dry_reference(square, ev["event"], pas, t, shape, crs),
                    "s1 search square")
        centre = s1_flood_centre(ref["flooded"], ref["valid"], t, crs)
        extra = {"s1_pass": pas, "search_square": square,
                 "search_square_flooded_cells": int((ref["flooded"] & ref["valid"]).sum())}
    bbox = None if centre is None else R.square_bbox(*centre, BOX_SIDE_M)
    return {**ev, **extra, "centre": centre, "bbox": bbox}


def _flood_centre(polys, extent):
    from experiments.flood_validation.harness_round3 import flood_extent_centre
    return flood_extent_centre(polys, extent)


def _centre_cached(key, fn):
    path = os.path.join(CACHE, "centres", f"{key}.json")
    if os.path.exists(path):
        with open(path) as fh:
            v = json.load(fh)
        return None if v is None else tuple(v)
    v = fn()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(v, fh)
    return v


def reference(ev: dict, transform, shape, crs) -> dict:
    kind = ev["ref"][0]
    if kind == "ems":
        _, code, aoi, mon, typ = ev["ref"]
        return R.ems_reference(R.ems_product(code, aoi, mon, typ), ev["bbox"], transform, shape,
                               crs)
    if kind == "unosat":
        return R.unosat_reference(R.unosat_product(ev["ref"][1], ev["bbox"]), ev["bbox"],
                                  transform, shape, crs)
    return R.s1_dry_reference(ev["bbox"], ev["event"], ev["s1_pass"], transform, shape, crs)


RAIN_FOR = {"fluvial": False, "flash_flood": ("rain_intensity_mm_h",), "waterlogging": False,
            "pluvial": ("rain_design_day_mm",)}


def build_event(module: str, name: str, ev: dict) -> dict:
    """Module inputs + reference on the event's 4 km box grid, as arrays + meta."""
    from configs.pluvial_constants import PLUVIAL_CATCHMENT_MARGIN_M
    from susceptibility.hydro_rasters import fetch_hydro_rasters, utm_grid
    year = datetime.date.fromisoformat(ev["event"]).year
    transform, shape, crs = utm_grid(ev["bbox"])
    meta = {k: ev.get(k) for k in ("bbox", "event", "centre", "search_centre", "s1_pass",
                                   "search_square", "search_square_flooded_cells")}
    meta["grid"] = {"crs": crs, "transform": list(transform)[:6], "shape": list(shape)}
    arrays = {}
    if module == "pluvial":
        arrays.update(_pluvial_inputs(name, ev, year, transform, shape, crs,
                                      PLUVIAL_CATCHMENT_MARGIN_M, meta))
    else:
        rasters = _call(lambda: fetch_hydro_rasters(
            ev["bbox"], transform, shape, crs, year, rainfall=RAIN_FOR[module],
            water_history=module == "waterlogging"), f"rasters {name}")
        arrays.update({f"layer_{k}": v["raster"] for k, v in rasters["layers"].items()})
        meta["raster_errors"] = rasters["errors"]
    ref = _call(lambda: reference(ev, transform, shape, crs), f"reference {name}")
    arrays.update(flooded=ref["flooded"], valid=ref["valid"])
    meta["reference"] = ref["meta"]
    return {"arrays": arrays, "meta": meta}


def _pluvial_inputs(name, ev, year, t_box, shape_box, crs, margin_m, meta) -> dict:
    """DEM, impervious share and design storm on the box grid plus the margin
    (round 4: contributing area outside the box). The stand-ins: footprint
    area (Open Buildings, or OSM where it has none) + item 19 road space."""
    from susceptibility.hydro_rasters import compute_pixels, fetch_hydro_rasters, utm_grid
    from susceptibility.inputs import impervious_built_area, road_conduits
    from susceptibility.pluvial import impervious_share
    from vector.roads import load_road_layer
    import ee
    lat, lon = ev["centre"]
    outer = R.square_bbox(lat, lon, BOX_SIDE_M + 2 * margin_m)
    t, shape, crs_o = utm_grid(outer)
    if crs_o != crs:
        raise ValueError(f"margin grid {crs_o} is not the box grid's {crs}")
    r0, c0 = window_in(t, shape, t_box, shape_box)
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
    layer = load_road_layer(f"r4_{name}", outer)
    if layer.crs.to_string() != crs:
        raise ValueError(f"road layer CRS {layer.crs} is not the grid's {crs}")
    built = impervious_built_area(layer, t, shape)
    roads = road_conduits(layer, t, shape)
    meta["pluvial_inputs"] = {"footprint_source": layer.footprint_source,
                              "impervious": {k: built[k] for k in ("source", "method",
                                                                   "validation_status")},
                              "conduits": {k: roads[k] for k in ("source", "method",
                                                                 "validation_status")},
                              "margin_bbox": outer,
                              "design_storm_mm": float(np.nanmean(storm["raster"]))}
    return {"pl_dem": dem, "pl_imp": impervious_share(built, roads, shape),
            "pl_storm": np.array(float(np.nanmean(storm["raster"]))),
            "pl_window": np.array([r0, c0])}


def _path(split, module, name):
    return os.path.join(CACHE, split, f"{module}__{name}.npz")


def save_event(split, module, name, built):
    os.makedirs(os.path.dirname(_path(split, module, name)), exist_ok=True)
    np.savez_compressed(_path(split, module, name), **built["arrays"],
                        meta=np.array(json.dumps(built["meta"], default=str)))


def load_event(split, module, name):
    z = np.load(_path(split, module, name), allow_pickle=False)
    return {"arrays": {k: z[k] for k in z.files if k != "meta"},
            "meta": json.loads(str(z["meta"]))}


def build_all(split: str, module: str, events: dict, evaluate_only: bool) -> dict:
    built = {}
    for name, ev in events.items():
        if ev.get("not_run"):
            built[name] = {"error": f"not-run: {ev['not_run']}"}
            continue
        if os.path.exists(_path(split, module, name)):
            built[name] = load_event(split, module, name)
            continue
        if evaluate_only:
            built[name] = {"error": "not cached"}
            continue
        try:
            print(f"── place {split} {module}/{name}", flush=True)
            ev = place(ev)
            if ev["bbox"] is None:
                built[name] = {"error": "reference has no flooded area"}
                continue
            print(f"── build {split} {module}/{name} centre {ev['centre']}", flush=True)
            b = _call(lambda: build_event(module, name, ev), f"build {module}/{name}")
            save_event(split, module, name, b)
            built[name] = b
        except Exception as e:   # noqa: BLE001 -- dropped and named
            built[name] = {"error": f"{type(e).__name__}: {e}"}
            traceback.print_exc()
    return built


# ── main ───────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluate", action="store_true", help="use cached events only")
    ap.add_argument("--tuning-only", action="store_true",
                    help="build and choose on the tuning events; touch no test event")
    args = ap.parse_args(argv)
    tuning = tuning_events()
    check_disjoint(TEST_EVENTS, tuning)
    if not args.evaluate:
        import ee
        from ingestion.gee_client import initialize_gee
        initialize_gee()
        ee.data.setDeadline(R.EE_TIMEOUT_S * 1000)

    # 1. tuning: choose parameters before any test event is built
    chosen, tuning_out = {}, {}
    for module, (grid, default) in grids().items():
        built = build_all("tuning", module, tuning[module], args.evaluate)
        ok = {n: b for n, b in built.items() if "arrays" in b}
        sel = choose(module, grid, default, ok)
        sel["dropped"] = {n: b["error"] for n, b in built.items() if "arrays" not in b}
        sel["events"] = {n: b["meta"] for n, b in ok.items()}
        tuning_out[module], chosen[module] = sel, sel["chosen"]
        print(module, "chosen", json.dumps(sel["chosen"]), "tuning mean",
              sel.get("best_tuning_mean_auc"), flush=True)
    if args.tuning_only:
        print(json.dumps({m: {k: v for k, v in t.items() if k != "table"}
                          for m, t in tuning_out.items()}, indent=1, default=str))
        return 0

    # 2. test: each module once, with the chosen parameters
    modules = {}
    for module in MODULES:
        built = build_all("test", module, TEST_EVENTS[module], args.evaluate)
        res = evaluate_test(module, built, chosen.get(module))
        res["events"] = {n: b["meta"] for n, b in built.items() if "meta" in b}
        res["tuning"] = tuning_out.get(module, {"chosen": "not tuned: the validated "
                                                          "configuration (pre-registered)"})
        modules[module] = res
        print(module, json.dumps(res["held_out"]), flush=True)
    result = {
        "test": "flood round 4 -- M1 re-test; new M2 pluvial, M3 waterlogging, M4 flash flood "
                "(Tier 2 discrimination)",
        "preregistration_sha256": hashlib.sha256(open(PREREG, "rb").read()).hexdigest(),
        "run_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "bar": {"metric": "roc_auc_cells", "validated_if_auc_at_least": AUC_MIN,
                "per_module": "mean of within-event AUCs over qualifying test events",
                "min_flooded_cells": MIN_FLOODED_CELLS, "min_dry_cells": MIN_DRY_CELLS,
                "min_test_events": H2.MIN_HELDOUT_EVENTS, "box_side_m": BOX_SIDE_M,
                "s1_search_square_m": S1_SEARCH_SIDE_M},
        "modules": modules,
    }
    with open(RESULT, "w") as f:
        json.dump(result, f, indent=1,
                  default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print("wrote", RESULT)


if __name__ == "__main__":
    sys.exit(main())
