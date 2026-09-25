"""Item 21 Phase A, part 4 — built from footprints, two-source disagreement."""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from surface_fractions import built

OB_PROV = {"asset": "GOOGLE/Research/open-buildings/v3/polygons", "min_confidence": 0.7}


def test_built_is_open_buildings_coverage_exactly():
    ob = np.array([[0.0, 0.3], [1.0, 0.5]], dtype=np.float32)
    ms = np.array([[0.9, 0.9], [0.9, 0.9]], dtype=np.float32)
    out = built.compute_built({"ob_cov": ob, "ms_cov": ms}, {"microsoft_buildings": "available"}, OB_PROV)
    np.testing.assert_array_equal(out["built"], ob)  # Microsoft never leaks in
    assert out["provenance"]["measured_spectrally"] is False
    assert out["provenance"]["min_confidence"] == 0.7


def test_disagreement_measures():
    ob = np.array([1.0, 0.5, 0.0, 0.0])
    ms = np.array([1.0, 0.0, 0.5, 0.0])
    d = built.disagreement(ob, ms, "available")
    assert d["coverage_total_primary"] == pytest.approx(0.375)
    assert d["coverage_total_secondary"] == pytest.approx(0.375)
    assert d["fraction_mae"] == pytest.approx(0.25)
    assert d["weighted_jaccard"] == pytest.approx(1.0 / 2.0)
    assert d["is_confidence_score"] is False


def test_identical_sources_iou_one_mae_zero():
    a = np.array([0.2, 0.7, 1.0])
    d = built.disagreement(a, a.copy(), "available")
    assert d["weighted_jaccard"] == pytest.approx(1.0) and d["fraction_mae"] == 0


def test_no_buildings_in_either_source_iou_undefined_not_one():
    z = np.zeros(4)
    assert built.disagreement(z, z, "available")["weighted_jaccard"] is None


def test_nan_pixels_excluded_from_comparison():
    ob = np.array([1.0, np.nan])
    ms = np.array([1.0, 0.0])
    assert built.disagreement(ob, ms, "available")["pixels_compared"] == 1


def test_missing_second_source_is_unavailable_not_zero():
    ob = np.ones((2, 2), dtype=np.float32)
    out = built.compute_built({"ob_cov": ob, "ms_cov": np.full((2, 2), np.nan)},
                              {"microsoft_buildings": "unavailable"}, OB_PROV)
    assert out["disagreement"]["status"] == "unavailable"
    assert out["built_secondary_abs_diff"] is None
    np.testing.assert_array_equal(out["built"], ob)


def test_absent_secondary_is_unavailable_not_total_disagreement():
    ob = np.array([0.5, 0.2])
    d = built.disagreement(ob, np.full(2, np.nan), "absent_in_aoi")
    assert d["status"] == "unavailable" and "absent_in_aoi" in d["reason"]


def test_absent_primary_makes_built_status_absent():
    out = built.compute_built({"ob_cov": np.full((1, 2), np.nan, np.float32),
                               "ms_cov": np.array([[0.3, 0.1]], np.float32)},
                              {"open_buildings": "absent_in_aoi", "microsoft_buildings": "available"},
                              OB_PROV)
    assert out["status"] == "absent_in_aoi"
    assert out["disagreement"]["status"] == "unavailable"
    assert out["built_secondary_abs_diff"] is None
