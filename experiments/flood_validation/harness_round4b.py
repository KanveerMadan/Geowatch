"""
Flood validation round 4b (flood taxonomy M3, waterlogging = historical
standing-water persistence ONLY). Pre-registered in PREREGISTRATION_ROUND4B.md;
the events, method, rule and bar below match it. Nothing is tuned: each event
is built and scored once.

    python -m experiments.flood_validation.harness_round4b            # fetch + evaluate
    python -m experiments.flood_validation.harness_round4b --evaluate # cached events only

References, box rule, grids and caching are round 4's (harness_round4).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys

from experiments.flood_validation import harness_round2 as H2
from experiments.flood_validation import harness_round4 as H4
from experiments.flood_validation import references as R
from experiments.flood_validation.harness import AUC_MIN, MIN_DRY_CELLS, MIN_FLOODED_CELLS

HERE = os.path.dirname(os.path.abspath(__file__))
PREREG = os.path.join(HERE, "PREREGISTRATION_ROUND4B.md")
RESULT = os.path.join(HERE, "result_round4b_2026-10-31.json")
SPLIT = "test4b"

EVENTS = {
    "noakhali_2024": H4._unosat("FL20240825BGD_S1_20240828_20240904", "2024-08-25"),
    "calais_2023": H4._ems("EMSR706", 1, 0, "2023-11-07"),
    "redon_2025": H4._ems("EMSR788", 6, 4, "2025-01-30"),
}


def weights() -> dict:
    from configs.waterlogging_constants import WATERLOGGING_R4B_WEIGHTS
    return dict(WATERLOGGING_R4B_WEIGHTS)


def earlier_event_names() -> set:
    """Every event name any earlier round used, in any role."""
    names = set()
    for evs in H2.EVENTS.values():
        names |= set(evs)
    for evs in H4.TEST_EVENTS.values():
        names |= set(evs)
    for evs in H4.TUNING_EVENTS.values():
        names |= set(evs)
    from experiments.flood_validation.harness import (COASTAL_SITES, FLASH_SITES, JRC_SITES,
                                                      PLUVIAL_SITES)
    names |= set(JRC_SITES) | set(PLUVIAL_SITES) | set(COASTAL_SITES) | set(FLASH_SITES)
    return names


def check_new(events: dict) -> None:
    """Pre-registered: every round-4b event is new."""
    seen = set(events) & earlier_event_names()
    if seen:
        raise ValueError(f"round-4b events used in an earlier round: {seen}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--evaluate", action="store_true", help="use cached events only")
    args = ap.parse_args(argv)
    check_new(EVENTS)
    if not args.evaluate:
        import ee
        from ingestion.gee_client import initialize_gee
        initialize_gee()
        ee.data.setDeadline(R.EE_TIMEOUT_S * 1000)
    w = weights()
    built = H4.build_all(SPLIT, "waterlogging", EVENTS, args.evaluate)
    res = H4.evaluate_test("waterlogging", built, w)
    res["events"] = {n: b["meta"] for n, b in built.items() if "meta" in b}
    res["tuning"] = {"chosen": "none: persistence only, pre-registered"}
    print("waterlogging", json.dumps(res["held_out"]), flush=True)
    result = {
        "test": "flood round 4b -- M3 waterlogging, historical standing-water persistence only, "
                "new events (Tier 2 discrimination)",
        "preregistration_sha256": hashlib.sha256(open(PREREG, "rb").read()).hexdigest(),
        "run_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "bar": {"metric": "roc_auc_cells", "validated_if_auc_at_least": AUC_MIN,
                "per_module": "mean of within-event AUCs over qualifying events",
                "min_flooded_cells": MIN_FLOODED_CELLS, "min_dry_cells": MIN_DRY_CELLS,
                "min_events": H2.MIN_HELDOUT_EVENTS, "box_side_m": H4.BOX_SIDE_M},
        "modules": {"waterlogging": res},
    }
    with open(RESULT, "w") as f:
        json.dump(result, f, indent=1,
                  default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print("wrote", RESULT)


if __name__ == "__main__":
    sys.exit(main())
