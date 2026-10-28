"""
Flood validation round 2 (item 26 Phase 1a). Pre-registered in
PREREGISTRATION_ROUND2.md; the events, splits, references and rules below
match it.

Per-pixel modules (pluvial, fluvial, flash flood, waterlogging): AUC within
each event; the module metric is the mean per-event AUC over held-out
events. Weights are chosen on tuning events only, from the module's
pre-registered grid; held-out events are scored ONCE, with the chosen
weights. Coastal stays an AOI-wide scalar and pools held-out sites (round 1).

    python -m experiments.flood_validation.harness_round2            # fetch + evaluate
    python -m experiments.flood_validation.harness_round2 --evaluate # cached inputs only

Inputs and references are cached per event (npz) under
references.CACHE/round2, so evaluation is reproducible offline.
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

from experiments.flood_validation import references as R
from experiments.flood_validation.harness import AUC_MIN, MIN_DRY_CELLS, MIN_FLOODED_CELLS, auc
from experiments.flood_validation.harness import MIN_POOLED_SITES, verdict as pooled_verdict

HERE = os.path.dirname(os.path.abspath(__file__))
PREREG = os.path.join(HERE, "PREREGISTRATION_ROUND2.md")
RESULT = os.path.join(HERE, "result_round2_2026-10-28.json")
CACHE = os.path.join(R.CACHE, "round2")
MIN_HELDOUT_EVENTS = 2
EE_STEP_TIMEOUT_S = 1800        # one event's whole input build (several EE calls)

ROUND1_BBOX = {
    "dharavi": (72.836, 19.037, 72.862, 19.060),
    "derna": (22.62, 32.75, 22.66, 32.78),
    "bad_neuenahr": (7.09, 50.53, 7.13, 50.56),
    "beira": (34.83, -19.85, 34.87, -19.81),
    "fort_myers_beach": (-81.97, 26.43, -81.93, 26.47),
}


def _ems(code, aoi, mon, lat, lon, event):
    return {"ref": ("ems", code, aoi, mon), "bbox": R.square_bbox(lat, lon), "event": event,
            "centre": (lat, lon)}


def _s1(name, event, window):
    return {"ref": ("s1", window), "bbox": ROUND1_BBOX[name], "event": event}


# ── the pre-registered events (PREREGISTRATION_ROUND2.md §Events) ─────

EVENTS = {
    "pluvial": {
        "dharavi": {**_s1("dharavi", "2017-08-29", "default"), "split": "tuning",
                    "veg_window": ("2018-01-01", "2018-03-31")},
        "hai_phong": {**_ems("EMSR754", 5, 0, 20.8449, 106.6881, "2024-09-07"), "split": "held-out",
                      "veg_window": ("2024-11-01", "2025-01-31")},
        "milagro": {**_ems("EMSR796", 6, 0, -2.1347, -79.5872, "2025-02-26"), "split": "held-out",
                    "veg_window": ("2024-07-01", "2024-09-30")},
        "belize_city": {**_ems("EMSR777", 1, 0, 17.5046, -88.1962, "2024-11-15"),
                        "split": "held-out", "veg_window": ("2024-03-01", "2024-05-31")},
    },
    "fluvial": {
        "faenza": {**_ems("EMSR659", 2, 0, 44.2856, 11.8833, "2023-05-02"), "split": "tuning"},
        "encantado": {**_ems("EMSR720", 2, 0, -29.2360, -51.8700, "2024-05-02"), "split": "tuning"},
        "hanoi": {**_ems("EMSR754", 3, 0, 21.0285, 105.8542, "2024-09-09"), "split": "held-out"},
        "kolonnawa": {**_ems("EMSR851", 2, 0, 6.9333, 79.8833, "2025-11-30"), "split": "held-out"},
        "nysa": {**_ems("EMSR756", 3, 0, 50.4747, 17.3337, "2024-09-14"), "split": "held-out"},
        "hue": {**_ems("EMSR848", 6, 0, 16.4637, 107.5909, "2025-10-29"), "split": "held-out"},
    },
    "flash_flood": {
        "paiporta": {**_ems("EMSR773", 3, 0, 39.4280, -0.4177, "2024-10-29"), "split": "tuning"},
        "derna": {**_s1("derna", "2023-09-11", "default"), "split": "tuning"},
        "bad_neuenahr": {**_s1("bad_neuenahr", "2021-07-14", "default"), "split": "tuning"},
        "volos": {**_ems("EMSR692", 1, 3, 39.3622, 22.9420, "2023-09-05"), "split": "held-out"},
        "kastelli": {**_ems("EMSR933", 1, 1, 35.2131, 25.3381, "2026-10-01"), "split": "held-out"},
        "choloma": {**_ems("EMSR778", 10, 0, 15.6133, -87.9531, "2024-11-16"), "split": "held-out"},
    },
    "coastal": {
        "kyaukpyu": {**_ems("EMSR661", 2, 0, 19.4290, 93.5494, "2023-05-14"), "split": "tuning"},
        "beira": {**_s1("beira", "2019-03-15", "coastal"), "split": "held-out"},
        "fort_myers_beach": {**_s1("fort_myers_beach", "2022-09-28", "coastal"),
                             "split": "held-out"},
        "sittwe": {**_ems("EMSR661", 1, 0, 20.1462, 92.8983, "2023-05-14"), "split": "held-out"},
        "black_river": {**_ems("EMSR847", 15, 0, 18.0264, -77.8487, "2025-10-28"),
                        "split": "held-out"},
    },
    "waterlogging": {
        **{n: {"ref": ("jrc",), "bbox": None, "event": "2021-12-31", "split": "tuning"}
           for n in ("dharavi", "hcmc", "kigali", "accra", "dhaka", "capetown", "guatemala",
                     "nusantara")},
        "thai_binh": {**_ems("EMSR754", 6, 0, 20.4463, 106.3366, "2024-09-09"), "split": "held-out"},
        "nam_dinh": {**_ems("EMSR754", 7, 0, 20.4200, 106.1683, "2024-09-09"), "split": "held-out"},
        "jakarta_gfd_3280": {"ref": ("gfd", 3280), "bbox": None, "event": "2008-03-01",
                             "split": "held-out"},
    },
}
TUNED = ("fluvial", "flash_flood", "waterlogging")
# the rainfall layer each module reads (fluvial reads none)
RAINFALL_LAYERS = {"fluvial": (), "flash_flood": ("rain_intensity_mm_h",),
                   "waterlogging": ("rain_annual_mm",)}


def _resolve_baseline_bboxes():
    from vector.aois import BASELINE_AOIS
    for name, ev in EVENTS["waterlogging"].items():
        if ev["bbox"] is None:
            ev["bbox"] = BASELINE_AOIS["jakarta" if name.startswith("jakarta") else name]


# ── pure: request strips ──────────────────────────────────────────────

BUILT_PAINT_M = 2.0
STRIP_MAX_PAINT_PX = 6_000_000      # 2 m pixels per request, ~24 MB as float


def strip_rows(cols: int, pixel_m: float) -> int:
    per_row = cols * (pixel_m / BUILT_PAINT_M) ** 2
    return max(1, int(STRIP_MAX_PAINT_PX // per_row))


def row_strips(transform, shape, rows: int):
    """[(row0, row1, transform of that strip)] covering the grid top to bottom."""
    from rasterio.transform import Affine
    return [(r0, min(r0 + rows, shape[0]), transform * Affine.translation(0, r0))
            for r0 in range(0, shape[0], rows)]


# ── pure: evaluation ──────────────────────────────────────────────────

def event_auc(score, flooded, valid, block: int = 1) -> dict:
    s, f = R.cells(score, flooded, valid, block)
    nf, nd = int(f.sum()), int((~f).sum())
    out = {"flooded_cells": nf, "dry_cells": nd, "evaluation_cell_m": 30 * block}
    if nf < MIN_FLOODED_CELLS or nd < MIN_DRY_CELLS:
        return {**out, "auc": None, "qualifies": False}
    return {**out, "auc": round(auc(s, f.astype(int), (~f).astype(int)), 4), "qualifies": True}


def mean_auc(evaluated: list) -> float | None:
    a = [e["auc"] for e in evaluated if e["qualifies"]]
    return round(float(np.mean(a)), 4) if a else None


def choose_weights(grid: list, default: dict, tuning: dict, combine) -> dict:
    """Pre-registered rule: highest mean within-event AUC over qualifying
    tuning events; ties to the default if among them, else first in grid
    order. `tuning`: {event: (components, flooded, valid, block)}."""
    table = []
    for w in grid:
        ev = [event_auc(combine(c, w), f, v, b) for c, f, v, b in tuning.values()]
        table.append({"weights": w, "mean_auc": mean_auc(ev),
                      "per_event": {n: e["auc"] for n, e in zip(tuning, ev)}})
    scored = [t for t in table if t["mean_auc"] is not None]
    if not scored:
        return {"chosen": default, "reason": "no qualifying tuning event; default kept",
                "table": table}
    best = max(t["mean_auc"] for t in scored)
    tied = [t["weights"] for t in scored if t["mean_auc"] == best]
    chosen = default if default in tied else tied[0]
    return {"chosen": chosen, "best_tuning_mean_auc": best, "table": table,
            "reason": "default among the tied best" if chosen is default and len(tied) > 1
            else "highest tuning mean"}


def heldout_verdict(per_event: dict) -> dict:
    q = [e for e in per_event.values() if e["qualifies"]]
    if len(q) < MIN_HELDOUT_EVENTS:
        return {"verdict": "not-run", "auc": None, "qualifying_events": len(q),
                "reason": f"fewer than {MIN_HELDOUT_EVENTS} qualifying held-out events"}
    a = mean_auc(q)
    return {"verdict": "validated" if a >= AUC_MIN else "failed", "auc": a,
            "qualifying_events": len(q)}


def pooled_auc(items: list) -> float | None:
    s = np.concatenate([x[0] for x in items]) if items else np.array([])
    f = np.concatenate([x[1] for x in items]) if items else np.array([], bool)
    if not f.any() or f.all():
        return None
    return round(auc(s, f.astype(int), (~f).astype(int)), 4)


# ── fetching (Earth Engine, EMS) ───────────────────────────────────────

def _call(fn, label):
    from ee_timeout import call
    return call(fn, timeout=EE_STEP_TIMEOUT_S, retries=1, label=label)


def reference(ev: dict, transform, shape, crs) -> dict:
    kind = ev["ref"][0]
    if kind == "ems":
        _, code, aoi, mon = ev["ref"]
        return R.ems_reference(R.ems_product(code, aoi, mon), ev["bbox"], transform, shape, crs)
    if kind == "s1":
        return R.s1_reference(ev["bbox"], ev["event"], R.S1_EVENT_WINDOW_DAYS[ev["ref"][1]],
                              transform, shape, crs)
    if kind == "gfd":
        return R.gfd_reference(ev["ref"][1], transform, shape, crs)
    return R.jrc_reference(transform, shape, crs)


def built_surface(bbox, transform, shape, crs):
    """Open Buildings footprint union area fraction per 30 m cell (painted at
    2 m) -- task 1's producer, placeholder. None if the box has no footprints."""
    import ee
    from susceptibility.inputs import surface
    from vector.sources import OPEN_BUILDINGS_ASSET
    aoi = ee.Geometry.Rectangle(list(bbox))
    fc = ee.FeatureCollection(OPEN_BUILDINGS_ASSET).filterBounds(aoi)
    n = R._info(lambda: fc.size().getInfo(), "open buildings count")
    if n == 0:
        return None, 0
    img = (ee.Image(0).byte().paint(fc, 1).reproject(crs=crs, scale=2)
           .reduceResolution(ee.Reducer.mean(), maxPixels=256).rename("built"))
    # The 2 m intermediate of a whole 11 km box is ~120 MB, over Earth
    # Engine's request limit (HCMC), so the same image is fetched in strips.
    parts = [R._pixels(img, t, (r1 - r0, shape[1]), crs, f"open buildings rows {r0}-{r1}")["built"]
             for r0, r1, t in row_strips(transform, shape, strip_rows(shape[1], transform.a))]
    b = np.vstack(parts)
    return surface(b, "open_buildings_v3 footprints, EE paint at 2 m",
                   "footprint_union_area_fraction", "placeholder"), n


def build_event(module: str, name: str, ev: dict) -> dict:
    """Module inputs + reference on the event grid, as arrays + meta."""
    from susceptibility.hydro_rasters import fetch_hydro_rasters, utm_grid
    year = datetime.date.fromisoformat(ev["event"]).year
    meta = {"bbox": ev["bbox"], "event": ev["event"], "split": ev["split"],
            "centre": ev.get("centre")}
    if module == "pluvial":
        from susceptibility.inputs import hydrology_surfaces
        from susceptibility.pluvial import compute_pluvial_susceptibility
        from vector.roads import load_road_layer
        fi = _call(lambda: hydrology_surfaces(load_road_layer(f"r2_{name}", ev["bbox"]),
                                              *ev["veg_window"]), f"pluvial inputs {name}")
        m = compute_pluvial_susceptibility(impervious=fi["impervious"],
                                           infiltration=fi["infiltration"],
                                           conduits=fi["conduits"],
                                           terrain=fi["terrain"])["susceptibility_map"]
        transform, shape, crs = fi["transform"], fi["shape"], fi["crs"]
        arrays = {"score": m}
        meta["inputs_validation_status"] = fi["validation_status"]
    elif module == "coastal":
        from ingestion.coastal import get_coastline_context
        from ingestion.hydrology import get_fabdem_elevation_stats
        from susceptibility.coastal import compute_coastal_susceptibility
        c = _call(lambda: get_coastline_context(*ev["bbox"]), f"coastline {name}")
        e = _call(lambda: get_fabdem_elevation_stats(*ev["bbox"]), f"fabdem {name}")
        r = compute_coastal_susceptibility(c, e)
        transform, shape, crs = utm_grid(ev["bbox"])
        arrays = {}
        meta["score"] = r.get("aoi_mean_score")
        meta["coastal_status"] = r.get("status")
    else:
        transform, shape, crs = utm_grid(ev["bbox"])
        rasters = _call(lambda: fetch_hydro_rasters(ev["bbox"], transform, shape, crs, year,
                                                    rainfall=RAINFALL_LAYERS[module]),
                        f"rasters {name}")
        arrays = {f"layer_{k}": v["raster"] for k, v in rasters["layers"].items()}
        meta["raster_errors"] = rasters["errors"]
        if module == "waterlogging":
            b, n = _call(lambda: built_surface(ev["bbox"], transform, shape, crs), f"built {name}")
            meta["open_buildings_footprints"] = n
            if b is not None:
                arrays["built"] = b["raster"]
    ref = _call(lambda: reference(ev, transform, shape, crs), f"reference {name}")
    arrays.update(flooded=ref["flooded"], valid=ref["valid"])
    meta.update(block=ref["block"], reference=ref["meta"],
                grid={"crs": crs, "transform": list(transform)[:6], "shape": list(shape)})
    return {"arrays": arrays, "meta": meta}


def _cache_path(module, name):
    return os.path.join(CACHE, f"{module}__{name}.npz")


def save_event(module, name, built):
    os.makedirs(CACHE, exist_ok=True)
    np.savez_compressed(_cache_path(module, name), **built["arrays"],
                        meta=np.array(json.dumps(built["meta"], default=str)))


def load_event(module, name):
    z = np.load(_cache_path(module, name), allow_pickle=False)
    return {"arrays": {k: z[k] for k in z.files if k != "meta"},
            "meta": json.loads(str(z["meta"]))}


# ── evaluation from cached events ──────────────────────────────────────

def _rasters_from(arrays):
    from susceptibility.inputs import surface
    layers = {k[len("layer_"):]: surface(v, "cached", "cached", "experimental")
              for k, v in arrays.items() if k.startswith("layer_")}
    shape = arrays["flooded"].shape
    return {"status": "available", "shape": shape, "errors": {}, "layers": layers}


def components_for(module, arrays):
    from susceptibility import flash_flood, fluvial, waterlogging
    r = _rasters_from(arrays)
    if module == "fluvial":
        return fluvial.components(r), fluvial.combine
    if module == "flash_flood":
        return flash_flood.components(r), flash_flood.combine
    from susceptibility.inputs import surface
    imp = (surface(arrays["built"], "open_buildings_v3", "footprint_union_area_fraction",
                   "placeholder") if "built" in arrays else None)
    return waterlogging.components(r, imp), waterlogging.combine


def evaluate_module(module: str, events: dict, built: dict) -> dict:
    from configs import flash_flood_constants as ffc, fluvial_constants as fc
    from configs import waterlogging_constants as wc
    grids = {"fluvial": (fc.FLUVIAL_WEIGHT_GRID, fc.FLUVIAL_WEIGHTS),
             "flash_flood": (ffc.FLASH_FLOOD_WEIGHT_GRID, ffc.FLASH_FLOOD_WEIGHTS),
             "waterlogging": (wc.WATERLOGGING_WEIGHT_GRID, wc.WATERLOGGING_WEIGHTS)}
    per = {n: b["meta"] for n, b in built.items() if "arrays" in b}
    dropped = {n: built.get(n, {}).get("error", "not built") for n in events if n not in per}
    out = {"events": per, "dropped": dropped}

    if module == "coastal":
        groups = {}
        for n, ev in events.items():
            if n not in per:
                continue
            a = built[n]["arrays"]
            s, f = R.cells(np.ones(a["flooded"].shape), a["flooded"], a["valid"])
            per[n].update(flooded_cells=int(f.sum()), dry_cells=int((~f).sum()))
            if per[n]["score"] is None:
                dropped[n] = f"score is None ({per[n].get('coastal_status')})"
                continue
            groups.setdefault(ev["split"], []).append((per[n]["score"], int(f.sum()),
                                                       int((~f).sum())))
        out["tuning"] = {"chosen": "not tuned (pre-registered)",
                         "per_event": {n: {k: per[n].get(k) for k in
                                           ("score", "flooded_cells", "dry_cells")}
                                       for n, ev in events.items()
                                       if ev["split"] == "tuning" and n in per}}
        h = groups.get("held-out", [])
        return {**out, "held_out": pooled_verdict(h, len(h), pooled=True)}

    def ev_inputs(n):
        a = built[n]["arrays"]
        if module == "pluvial":
            return {"score": a["score"]}, (lambda c, w: c["score"]), a, per[n]["block"]
        comps, combine = components_for(module, a)
        return comps, combine, a, per[n]["block"]

    tuning = {n: ev_inputs(n) for n, ev in events.items()
              if ev["split"] == "tuning" and n in per}
    if module in TUNED:
        grid, default = grids[module]
        combine = next(iter(tuning.values()))[1] if tuning else None
        sel = choose_weights(grid, default, {n: (c, a["flooded"], a["valid"], b)
                                             for n, (c, _, a, b) in tuning.items()}, combine) \
            if tuning else {"chosen": default, "reason": "no tuning event built", "table": []}
        weights = sel["chosen"]
        out["tuning"] = sel
    else:
        weights = None
        out["tuning"] = {"chosen": "not tuned (pre-registered)", "per_event": {
            n: event_auc(c["score"], a["flooded"], a["valid"], b)
            for n, (c, _, a, b) in tuning.items()}}

    held, pooled = {}, []
    for n, ev in events.items():
        if ev["split"] != "held-out" or n not in per:
            continue
        c, combine, a, b = ev_inputs(n)
        score = combine(c, weights) if module in TUNED else c["score"]
        held[n] = event_auc(score, a["flooded"], a["valid"], b)
        if held[n]["qualifies"]:
            pooled.append(R.cells(score, a["flooded"], a["valid"], b))
    out["held_out_per_event"] = held
    out["held_out"] = heldout_verdict(held)
    out["pooled_held_out_auc_diagnostic"] = pooled_auc(pooled)
    out["weights_used"] = weights
    return out


# ── main ───────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluate", action="store_true", help="use cached events only")
    ap.add_argument("--modules", nargs="*", default=list(EVENTS))
    args = ap.parse_args(argv)
    _resolve_baseline_bboxes()
    if not args.evaluate:
        import ee
        from ingestion.gee_client import initialize_gee
        initialize_gee()
        ee.data.setDeadline(R.EE_TIMEOUT_S * 1000)
    errors = {}
    for module in args.modules:
        for name, ev in EVENTS[module].items():
            if args.evaluate or os.path.exists(_cache_path(module, name)):
                continue
            print(f"── build {module}/{name}", flush=True)
            try:
                save_event(module, name, build_event(module, name, ev))
            except Exception as e:   # noqa: BLE001 -- dropped and named
                errors[(module, name)] = f"{type(e).__name__}: {e}"
                traceback.print_exc()
    modules = {}
    for module in EVENTS:
        built = {}
        for name in EVENTS[module]:
            if os.path.exists(_cache_path(module, name)):
                built[name] = load_event(module, name)
            elif (module, name) in errors:
                built[name] = {"error": errors[(module, name)]}
        res = evaluate_module(module, EVENTS[module], built)
        modules[module] = res
        print(module, json.dumps(res["held_out"]), flush=True)
    result = {
        "test": "item 26 Phase 1a -- flood discrimination round 2 (Tier 2)",
        "preregistration_sha256": hashlib.sha256(open(PREREG, "rb").read()).hexdigest(),
        "run_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "bar": {"metric": "roc_auc_cells", "validated_if_auc_at_least": AUC_MIN,
                "per_pixel_modules": "mean of within-event AUCs over held-out events",
                "coastal": "pooled cells over held-out sites (round 1 rule)",
                "min_flooded_cells": MIN_FLOODED_CELLS, "min_dry_cells": MIN_DRY_CELLS,
                "min_heldout_events": MIN_HELDOUT_EVENTS, "min_pooled_sites": MIN_POOLED_SITES},
        "modules": modules,
    }
    with open(RESULT, "w") as f:
        json.dump(result, f, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print("wrote", RESULT)


if __name__ == "__main__":
    sys.exit(main())
