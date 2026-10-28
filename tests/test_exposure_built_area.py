"""
Exposure's built-up figure is footprint built area, never the retired
7-class map's category percentages (C54).
"""
import inspect

import numpy as np
import pytest

import pipeline
from exposure.compute import EvidenceLayer, compute_exposure_for_layer
from perception.applicability_gate import LANDCOVER_DERIVED
from susceptibility.inputs import surface

BUILT = surface(np.array([[0.2, 0.4], [np.nan, 0.6]]), "open_buildings_v3 footprints",
                "footprint_union_area_fraction", "placeholder")


def _layer():
    return EvidenceLayer(layer_id="pluvial_susceptibility", label="Pluvial",
                         evidence_type="long_term_screening", status="experimental",
                         mask_source="aoi_wide_scalar", threshold_or_score=0.5,
                         temporal_scope="static/contextual", limitations=[])


def test_built_up_is_footprint_area_and_placeholder():
    r = compute_exposure_for_layer(_layer(), None, population_context=None, built_area=BUILT)
    b = r["components"]["built_up"]
    assert b["built_area_pct"] == 40.0            # mean of observed 0.2, 0.4, 0.6
    assert b["method"] == "footprint_union_area_fraction"
    assert b["validation_status"] == "placeholder"
    assert "geowatch_model_builtup_pct" not in b


def test_undeclared_built_area_is_refused():
    with pytest.raises(ValueError, match="declared surface"):
        compute_exposure_for_layer(_layer(), None, population_context=None,
                                   built_area=np.zeros((2, 2)))


def test_no_built_area_is_not_calculated():
    r = compute_exposure_for_layer(_layer(), None, population_context=None)
    assert r["components"]["built_up"]["status"] == "not_calculated"


def test_exposure_takes_no_7class_percentages():
    assert "landcover_builtup_pct" not in inspect.signature(compute_exposure_for_layer).parameters
    src = inspect.getsource(pipeline.run_pipeline)
    assert "landcover_builtup_pct" not in src
    assert "exposure" not in LANDCOVER_DERIVED
