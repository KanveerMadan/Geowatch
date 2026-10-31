"""Flood round 4b (PREREGISTRATION_ROUND4B.md): waterlogging = historical
standing-water persistence only, on new events, untuned. No Earth Engine."""
import numpy as np
import pytest

from configs.waterlogging_constants import WATERLOGGING_R4B_WEIGHTS
from experiments.flood_validation import harness_round4b as H4B
from susceptibility import waterlogging as WL
from susceptibility.hydro_rasters import SOURCES
from susceptibility.inputs import surface


def _rasters(**vals):
    shape = next(iter(vals.values())).shape
    return {"status": "available", "shape": shape, "errors": {},
            "layers": {k: surface(v, *SOURCES[k], "experimental") for k, v in vals.items()}}


def test_every_round4b_event_is_new():
    H4B.check_new(H4B.EVENTS)
    assert len(H4B.EVENTS) >= 2
    with pytest.raises(ValueError, match="earlier round"):
        H4B.check_new({"kerala_2018": {}, "noakhali_2024": {}})


def test_the_method_is_persistence_only_and_untuned():
    assert WATERLOGGING_R4B_WEIGHTS == {"persistence": 1.0, "clay": 0.0, "low_relief": 0.0,
                                        "backwater": 0.0}
    assert H4B.weights() == WATERLOGGING_R4B_WEIGHTS
    assert WL.DEFAULT_WEIGHTS == WATERLOGGING_R4B_WEIGHTS       # what the pipeline runs


def test_the_score_is_the_persistence_component_exactly():
    jrc = np.array([[0.0, 0.2, 0.6]])
    s1 = np.array([[0.0, 0.4, np.nan]])
    r = _rasters(jrc_water_freq=jrc, s1_water_freq=s1, hand_m=np.array([[0.1, 50.0, 3.0]]),
                 clay_pct=np.array([[60.0, 0.0, 10.0]]), upa_near_km2=np.full((1, 3), 5e4))
    m = WL.compute_waterlogging_susceptibility(r)
    assert np.allclose(m["susceptibility_map"], WL.persistence(jrc, s1))
    assert m["components_used"] == ["persistence"]
    assert set(m["inputs"]) == {"jrc_water_freq", "s1_water_freq"}   # only what it reads
