"""
Fluvial, coastal and flash flood carry a validation_status on every output,
and it follows item 26 task 8's stored Tier 2 verdict: failed -> "failed",
not-run -> "experimental" (nothing validated means nothing claims it).
"""
import json
import pathlib

import numpy as np
import pytest

from susceptibility.coastal import compute_coastal_susceptibility
from susceptibility.flash_flood import compute_flash_flood_susceptibility
from susceptibility.fluvial import compute_fluvial_susceptibility
from susceptibility.inputs import surface

RESULT = (pathlib.Path(__file__).resolve().parent.parent
          / "experiments/flood_validation/result_2026-10-28.json")
VERDICT_TO_LABEL = {"validated": "validated", "failed": "failed", "not-run": "experimental"}

HAND = {"status": "available", "mean_hnd_m": 4.0, "min_hnd_m": 0.5, "max_hnd_m": 20.0,
        "river_connectivity": True, "max_upstream_area_km2": 120.0, "buffer_km": 2}
SLOPE = {"status": "available", "mean_slope_deg": 3.2}
RAIN = {"status": "available", "mean_annual_mm": 1800.0}
COAST = {"status": "available", "distance_km": 2.0, "coastal_connectivity": True,
         "search_radius_km": 50}

# Item 26 Phase 1a: fluvial and flash flood are per-pixel; their inputs are
# rasters on one grid.
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
}


def _expected(module):
    verdict = json.loads(RESULT.read_text())["modules"][module]["verdict"]
    return VERDICT_TO_LABEL[verdict]


def test_task8_verdicts_are_what_the_labels_encode():
    assert {m: _expected(m) for m in PATHS} == {
        "fluvial": "failed", "flash_flood": "failed", "coastal": "experimental"}


@pytest.mark.parametrize("module", sorted(PATHS))
def test_every_path_carries_the_verdict_label(module):
    statuses = set()
    for call in PATHS[module]:
        r = call()
        statuses.add(r["status"])
        assert r["validation_status"] == _expected(module), (module, r["status"])
    assert len(statuses) == len(PATHS[module]), f"{module}: a path was not exercised"
