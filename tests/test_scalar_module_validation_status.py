"""
Fluvial, coastal, flash flood and waterlogging carry a validation_status on
every output, and it follows the latest stored held-out verdict: round 3
(result_round3_2026-10-29.json) where it gave one, else round 2 (item 26
Phase 1a, experiments/flood_validation/result_round2_2026-10-28.json):
validated -> "validated", failed -> "failed", not-run -> "experimental"
(the decided meaning: a real method, not yet validated). The tuned weights
in configs are the ones round 2 chose on its tuning events.
"""
import json
import pathlib

import numpy as np
import pytest

from configs import flash_flood_constants as ffc, fluvial_constants as fc
from configs import waterlogging_constants as wc
from susceptibility.coastal import compute_coastal_susceptibility
from susceptibility.retired_methods.flash_flood_round2 import compute_flash_flood_susceptibility
from susceptibility.fluvial import compute_fluvial_susceptibility
from susceptibility.inputs import surface
from susceptibility.retired_methods.waterlogging_round2 import compute_waterlogging_susceptibility

RESULT = (pathlib.Path(__file__).resolve().parent.parent
          / "experiments/flood_validation/result_round2_2026-10-28.json")
RESULT3 = RESULT.with_name("result_round3_2026-10-29.json")
VERDICT_TO_LABEL = {"validated": "validated", "failed": "failed", "not-run": "experimental"}

HAND = {"status": "available", "mean_hnd_m": 4.0, "min_hnd_m": 0.5, "max_hnd_m": 20.0,
        "river_connectivity": True, "max_upstream_area_km2": 120.0, "buffer_km": 2}
COAST = {"status": "available", "distance_km": 2.0, "coastal_connectivity": True,
         "search_radius_km": 50}
RASTERS = {"status": "available", "shape": (1, 2), "errors": {}, "layers": {
    k: surface(np.array([[v, v * 2]]), "test", "test", "experimental")
    for k, v in (("hand_m", 4.0), ("upa_near_km2", 120.0), ("relief_slope_deg", 3.2),
                 ("rain_intensity_mm_h", 10.0))}}

PATHS = {
    "fluvial": [lambda: compute_fluvial_susceptibility(RASTERS, HAND),
                lambda: compute_fluvial_susceptibility(None, {"status": "unavailable"})],
    "flash_flood": [lambda: compute_flash_flood_susceptibility(RASTERS),
                    lambda: compute_flash_flood_susceptibility(None)],
    "coastal": [lambda: compute_coastal_susceptibility(COAST, {"status": "available",
                                                               "mean_elevation_m": 4.0}),
                lambda: compute_coastal_susceptibility({"status": "available",
                                                        "distance_km": None,
                                                        "search_radius_km": 50}),
                lambda: compute_coastal_susceptibility(None)],
    "waterlogging": [lambda: compute_waterlogging_susceptibility(RASTERS),
                     lambda: compute_waterlogging_susceptibility(None)],
}


def _result():
    return json.loads(RESULT.read_text())["modules"]


def _expected(module):
    v3 = json.loads(RESULT3.read_text())["modules"].get(module, {}).get("held_out", {})
    v = v3.get("verdict")
    if not v or v == "not-run":
        v = _result()[module]["held_out"]["verdict"]
    return VERDICT_TO_LABEL[v]


def test_latest_verdicts_are_what_the_labels_encode():
    assert {m: _expected(m) for m in PATHS} == {
        "fluvial": "validated", "flash_flood": "failed", "coastal": "failed",
        "waterlogging": "failed"}


@pytest.mark.parametrize("module", sorted(PATHS))
def test_every_path_carries_the_verdict_label(module):
    statuses = set()
    for call in PATHS[module]:
        r = call()
        statuses.add(r["status"])
        assert r["validation_status"] == _expected(module), (module, r["status"])
    assert len(statuses) == len(PATHS[module]), f"{module}: a path was not exercised"


def test_validated_is_claimed_only_with_a_passing_heldout_run():
    res = _result()
    assert res["fluvial"]["held_out"]["verdict"] == "validated"
    assert res["fluvial"]["held_out"]["auc"] >= 0.70
    assert res["fluvial"]["held_out"]["qualifying_events"] >= 2
    r = compute_fluvial_susceptibility(RASTERS, HAND)
    assert r["validated"] is True
    assert compute_flash_flood_susceptibility(RASTERS)["validated"] is False


@pytest.mark.parametrize("module,weights", [
    ("fluvial", fc.FLUVIAL_WEIGHTS), ("flash_flood", ffc.FLASH_FLOOD_WEIGHTS),
    ("waterlogging", wc.WATERLOGGING_WEIGHTS)])
def test_config_weights_are_the_ones_tuning_chose(module, weights):
    t = _result()[module]["tuning"]
    assert weights == t["chosen"]
    grid = {"fluvial": fc.FLUVIAL_WEIGHT_GRID, "flash_flood": ffc.FLASH_FLOOD_WEIGHT_GRID,
            "waterlogging": wc.WATERLOGGING_WEIGHT_GRID}[module]
    assert weights in grid
    # chosen on tuning events only: the tuning table never names a held-out event
    held = set(_result()[module]["held_out_per_event"])
    assert all(not (set(row["per_event"]) & held) for row in t["table"])
