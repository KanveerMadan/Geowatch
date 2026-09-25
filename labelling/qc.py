"""
Blind re-label comparison (LABELLING_GUIDE.md §7), per class, at two levels:

  polygon level   IoU of the two labellings on the 1 m sub-cell label map
  fraction level  agreement of the 10 m fractions -- the quantity the model
                  is scored on: MAE and R^2 over cells both labellings score

Two separate verdicts, both None until their numbers exist:

  meets_agreement_bar  the §7 per-class agreement bar -- the §9.4 open number
                       (UNSET). A bar must name its metric (polygon_iou,
                       fraction_mae or fraction_r2) and value; the metric
                       choice is part of setting it.
  label_limited        §7: label agreement worse than the MODEL's pass bar
                       for that class. Model bars exist only for
                       impervious_total (item 21), which is not a hand label,
                       so no per-class verdict can be formed yet.
"""

from __future__ import annotations

import numpy as np

from labelling.fractions import parse_features, subcell_label_map, tile_fractions

WORSE_IF = {"polygon_iou": "lower", "fraction_mae": "higher", "fraction_r2": "lower"}


def _r2(a, b):
    if a.size < 2 or np.var(a) == 0:
        return None
    return float(1 - np.sum((a - b) ** 2) / np.sum((a - a.mean()) ** 2))


def compare(features_a: list, features_b: list, grid, cfg: dict) -> dict:
    labels = cfg["labels"]["scored"] + cfg["labels"]["excluded"]
    map_a, _, _ = subcell_label_map(parse_features(features_a, cfg), grid, cfg)
    map_b, _, _ = subcell_label_map(parse_features(features_b, cfg), grid, cfg)
    fa = tile_fractions(features_a, grid, cfg)
    fb = tile_fractions(features_b, grid, cfg)
    both = (1 - fa["excluded_share"] > 0) & (1 - fb["excluded_share"] > 0)

    bars = cfg["open"]["agreement_bars"]
    bars_set = bars.get("status") != "UNSET"
    per_class = {}
    for i, label in enumerate(labels, start=1):
        a, b = map_a == i, map_b == i
        union = int((a | b).sum())
        rec = {"polygon_iou": float((a & b).sum()) / union if union else None,
               "present_in": {"a": bool(a.any()), "b": bool(b.any())}}
        if label in cfg["labels"]["scored"]:
            x, y = fa["fractions"][label][both], fb["fractions"][label][both]
            rec.update({"fraction_mae": float(np.abs(x - y).mean()) if x.size else None,
                        "fraction_r2": _r2(x, y), "cells_compared": int(both.sum())})
        rec["meets_agreement_bar"] = None
        if bars_set and label in bars["per_class"]:
            bar = bars["per_class"][label]
            got = rec.get(bar["metric"])
            if bar["metric"] not in WORSE_IF:
                raise ValueError(f"agreement bar metric {bar['metric']!r} not in {list(WORSE_IF)}")
            if got is not None:
                worse = got < bar["value"] if WORSE_IF[bar["metric"]] == "lower" else got > bar["value"]
                rec["meets_agreement_bar"] = not worse
        rec["label_limited"] = None
        per_class[label] = rec
    return {"per_class": per_class,
            "agreement_bars": "set" if bars_set else "UNSET (guide §9.4): no verdict",
            "label_limited_note": "needs a model pass bar per class; only "
                                  "impervious_total has one (item 21) and it is "
                                  "not a hand-labelled class"}
