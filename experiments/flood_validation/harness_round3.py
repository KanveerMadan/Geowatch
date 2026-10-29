"""
Flood validation round 3 (item 26 follow-ups). Pre-registered in
PREREGISTRATION_ROUND3.md; the events, rule and bar below match it.

One change from round 2: each event's 4 km box is centred on its reference
product's mapped flood extent (flood_extent_centre), not on a town centre.
Methods and weights are frozen (round 2's); nothing is tuned. Inputs,
references, metric and bar are round 2's (harness_round2).

    python -m experiments.flood_validation.harness_round3            # fetch + evaluate
    python -m experiments.flood_validation.harness_round3 --evaluate # cached events only
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
PREREG = os.path.join(HERE, "PREREGISTRATION_ROUND3.md")
RESULT = os.path.join(HERE, "result_round3_2026-10-29.json")
CACHE = os.path.join(R.CACHE, "round3")
BOX_SIDE_M = 4000.0
MODULES = ("pluvial", "flash_flood", "waterlogging")
EXCLUDED = {"waterlogging": {
    "jakarta_gfd_3280": "GFD event 3280's mapped extent covers all of Java (105.1-115.9 E): "
                        "a box centred on it would not be the Jakarta event (pre-registered)"}}
# Scored in round 2 on other boxes: their AUCs were seen (diagnostic below).
SEEN_IN_ROUND2 = {"pluvial": ("milagro",), "flash_flood": ("kastelli",),
                  "waterlogging": ("nam_dinh",)}


# ── pure: the box rule ─────────────────────────────────────────────────

def flood_extent_centre(polys, extent) -> tuple | None:
    """(lat, lon): the area-weighted centroid of (union of `polys`) ∩
    `extent`, in metres (UTM of its lon/lat centroid); if that point is not
    in the flood extent, the nearest point of it. None if the extent is
    empty. lon/lat shapely geometries in, lon/lat out."""
    from pyproj import Transformer
    from shapely.ops import nearest_points, transform, unary_union
    f = unary_union([p for p in polys if p is not None and not p.is_empty])
    f = f.intersection(extent) if not f.is_empty else f
    if f.is_empty or f.area == 0:
        return None
    lon, lat = f.centroid.x, f.centroid.y
    epsg = (32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1
    fwd = Transformer.from_crs(4326, epsg, always_xy=True).transform
    back = Transformer.from_crs(epsg, 4326, always_xy=True).transform
    fm = transform(fwd, f)
    c = fm.centroid
    if not fm.covers(c):
        c = nearest_points(fm, c)[0]
    x, y = back(c.x, c.y)
    return round(y, 6), round(x, 6)


def events_for(module: str, centres: dict) -> dict:
    """Round 2's held-out EMS events of `module`, minus EXCLUDED, re-boxed
    on `centres` {name: (lat, lon) | None}."""
    out = {}
    for n, ev in H2.EVENTS[module].items():
        if ev["split"] != "held-out" or n in EXCLUDED.get(module, {}):
            continue
        assert ev["ref"][0] == "ems", (module, n)
        c = centres.get(n)
        out[n] = {**ev, "round2_centre": ev.get("centre"), "centre": c,
                  "bbox": None if c is None else R.square_bbox(*c, BOX_SIDE_M)}
    return out


def evaluate(module: str, built: dict, weights) -> dict:
    """Frozen weights, held-out only. `built`: {event: {"arrays", "meta"} or
    {"error"}}."""
    held, pooled, dropped = {}, [], {}
    for n, b in built.items():
        if "arrays" not in b:
            dropped[n] = b.get("error", "not built")
            continue
        a = b["arrays"]
        if module == "pluvial":
            score = a["score"]
        else:
            comps, combine = H2.components_for(module, a)
            score = combine(comps, weights)
        held[n] = H2.event_auc(score, a["flooded"], a["valid"], b["meta"]["block"])
        if held[n]["qualifies"]:
            pooled.append(R.cells(score, a["flooded"], a["valid"], b["meta"]["block"]))
    unseen = {n: e for n, e in held.items() if n not in SEEN_IN_ROUND2.get(module, ())}
    return {"dropped": dropped, "excluded": EXCLUDED.get(module, {}),
            "held_out_per_event": held, "held_out": H2.heldout_verdict(held),
            "pooled_held_out_auc_diagnostic": H2.pooled_auc(pooled),
            "unseen_events_mean_auc_diagnostic": {
                "events": sorted(n for n, e in unseen.items() if e["qualifies"]),
                "mean_auc": H2.mean_auc(list(unseen.values()))},
            "weights_used": weights}


def frozen_weights() -> dict:
    """Round 2's chosen weights, from the configs (asserted equal to round 2's
    result: nothing is tuned in round 3)."""
    from configs.flash_flood_constants import FLASH_FLOOD_WEIGHTS
    from configs.waterlogging_constants import WATERLOGGING_WEIGHTS
    with open(H2.RESULT) as fh:
        r2 = json.load(fh)["modules"]
    w = {"pluvial": None, "flash_flood": dict(FLASH_FLOOD_WEIGHTS),
         "waterlogging": dict(WATERLOGGING_WEIGHTS)}
    for m in ("flash_flood", "waterlogging"):
        assert w[m] == r2[m]["weights_used"], (m, w[m], r2[m]["weights_used"])
    return w


# ── fetching ───────────────────────────────────────────────────────────

def centre_of(ev: dict):
    _, code, aoi, mon = ev["ref"]
    product = R.ems_product(code, aoi, mon)
    polys, _, _ = R.ems_polygons(product)
    return flood_extent_centre(polys, product["extent"])


def _path(module, name):
    return os.path.join(CACHE, f"{module}__{name}.npz")


def save_event(module, name, built):
    os.makedirs(CACHE, exist_ok=True)
    np.savez_compressed(_path(module, name), **built["arrays"],
                        meta=np.array(json.dumps(built["meta"], default=str)))


def load_event(module, name):
    z = np.load(_path(module, name), allow_pickle=False)
    return {"arrays": {k: z[k] for k in z.files if k != "meta"},
            "meta": json.loads(str(z["meta"]))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluate", action="store_true", help="use cached events only")
    args = ap.parse_args(argv)
    weights = frozen_weights()
    if not args.evaluate:
        import ee
        from ingestion.gee_client import initialize_gee
        initialize_gee()
        ee.data.setDeadline(R.EE_TIMEOUT_S * 1000)
    modules = {}
    for module in MODULES:
        names = [n for n, ev in H2.EVENTS[module].items()
                 if ev["split"] == "held-out" and n not in EXCLUDED.get(module, {})]
        centres = {n: centre_of(H2.EVENTS[module][n]) for n in names}
        events = events_for(module, centres)
        built = {}
        for name, ev in events.items():
            if os.path.exists(_path(module, name)):
                built[name] = load_event(module, name)
                continue
            if ev["bbox"] is None:
                built[name] = {"error": "product has no flooded polygon"}
                continue
            if args.evaluate:
                built[name] = {"error": "not cached"}
                continue
            print(f"── build {module}/{name} centre {ev['centre']}", flush=True)
            try:
                b = H2.build_event(module, name, ev)
                b["meta"].update(centre=ev["centre"], round2_centre=ev["round2_centre"],
                                 box_rule="centred on the product's mapped flood extent")
                save_event(module, name, b)
                built[name] = b
            except Exception as e:   # noqa: BLE001 -- dropped and named
                built[name] = {"error": f"{type(e).__name__}: {e}"}
                traceback.print_exc()
        res = evaluate(module, built, weights[module])
        res["events"] = {n: b["meta"] for n, b in built.items() if "meta" in b}
        modules[module] = res
        print(module, json.dumps(res["held_out"]), flush=True)
    result = {
        "test": "item 26 follow-ups -- flood discrimination round 3 (Tier 2), "
                "boxes centred on the mapped flood extent",
        "preregistration_sha256": hashlib.sha256(open(PREREG, "rb").read()).hexdigest(),
        "run_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "bar": {"metric": "roc_auc_cells", "validated_if_auc_at_least": AUC_MIN,
                "per_pixel_modules": "mean of within-event AUCs over held-out events",
                "min_flooded_cells": MIN_FLOODED_CELLS, "min_dry_cells": MIN_DRY_CELLS,
                "min_heldout_events": H2.MIN_HELDOUT_EVENTS, "box_side_m": BOX_SIDE_M,
                "tuning": "none; round 2's weights frozen"},
        "modules": modules,
    }
    with open(RESULT, "w") as f:
        json.dump(result, f, indent=1,
                  default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print("wrote", RESULT)


if __name__ == "__main__":
    sys.exit(main())
