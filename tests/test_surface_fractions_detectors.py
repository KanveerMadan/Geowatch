"""Item 21 Phase A, part 3 — detectors: UNSET handling, predicate logic,
sub-typing. Predicate tests use TEST-ONLY threshold values, never the config."""
import copy
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from surface_fractions import detectors
from surface_fractions.config import load_config

LEGEND = load_config()["detectors"]["mixed_water_vegetation"]["sub_typing"]["glwd_legend"]


def _bands(g, swir1, nir, var):
    a = lambda v: np.array([v], dtype=np.float32)
    return {"cvs_Green": a(g), "cvs_SWIR1": a(swir1), "cvs_NIR": a(nir), "tv_NDVI_stddev": a(var)}


def _cfg_with_snow_thresholds():
    cfg = copy.deepcopy(load_config())
    t = cfg["detectors"]["snow_ice"]["thresholds"]
    t["variance_band"] = {"value": "NDVI_stddev", "source": "TEST ONLY", "status": "UNVALIDATED"}
    t["variance_max"] = {"value": 0.05, "source": "TEST ONLY", "status": "UNVALIDATED"}
    return cfg


def test_shipped_config_spectral_detectors_not_computed_mwv_from_datasets():
    cfg = load_config()
    known = np.ones(1, dtype=bool)
    out = detectors.run_detectors(cfg, _bands([.5], [.1], [.3], [.01]) | {
        "gmw_cov": np.zeros(1), "glwd_class": np.zeros(1)}, known)
    for name in ("snow_ice", "solar"):
        assert out[name]["status"] == "not_computed" and out[name]["fraction"] is None
    assert "variance_max" in out["snow_ice"]["reason"]
    # R2: GLWD all Dryland -> non-mangrove excluded -> class computed from GMW.
    assert out["mixed_water_vegetation"]["status"] == "computed"
    assert out["mixed_water_vegetation"]["sub_type"]["status"] == "computed"


def test_every_set_threshold_carries_a_source():
    for name, spec in load_config()["detectors"].items():
        for k, t in spec["thresholds"].items():
            assert t["status"] in ("UNSET", "UNVALIDATED"), (name, k)
            if t["value"] is not None:
                assert t["source"], f"{name}.{k} has a value but no source"
            else:
                assert t["status"] == "UNSET", f"{name}.{k} is null but not UNSET"


def test_snow_predicate_needs_all_three_conditions():
    cfg = _cfg_with_snow_thresholds()
    known = np.ones((4,), dtype=bool)
    b = {"cvs_Green": np.array([.6, .6, .6, .2], dtype=np.float32),
         "cvs_SWIR1": np.array([.1, .1, .1, .1], dtype=np.float32),
         "cvs_NIR": np.array([.5, .05, .5, .5], dtype=np.float32),
         "tv_NDVI_stddev": np.array([.01, .01, .2, .01], dtype=np.float32)}
    # all pass | NIR too low (water) | variance too high (seasonal) | NDSI too low
    out = detectors.run_detector("snow_ice", cfg, b, known)
    assert out["status"] == "computed"
    assert out["fraction"].tolist() == [1.0, 0.0, 0.0, 0.0]


def test_detected_pixel_is_fraction_one_and_unknown_is_nan():
    cfg = _cfg_with_snow_thresholds()
    b = _bands([.6], [.1], [.5], [.01])
    assert detectors.run_detector("snow_ice", cfg, b, np.array([True]))["fraction"][0] == 1.0
    assert np.isnan(detectors.run_detector("snow_ice", cfg, b, np.array([False]))["fraction"][0])


def test_unknown_variance_band_is_refused():
    cfg = _cfg_with_snow_thresholds()
    cfg["detectors"]["snow_ice"]["thresholds"]["variance_band"]["value"] = "nope"
    with pytest.raises(KeyError):
        detectors.run_detector("snow_ice", cfg, _bands([.6], [.1], [.5], [.01]), np.array([True]))


def test_setting_thresholds_without_a_predicate_is_refused():
    cfg = copy.deepcopy(load_config())
    for t in cfg["detectors"]["solar"]["thresholds"].values():
        t.update(value=1, source="TEST ONLY", status="UNVALIDATED")
    with pytest.raises(NotImplementedError):
        detectors.run_detector("solar", cfg, {}, np.array([True]))


def test_sub_type_gmw_first_then_glwd_then_unattributed():
    detected = np.array([1, 1, 1, 1, 0], dtype=np.float32)
    gmw = np.array([0.4, 0.0, 0.0, 0.0, 0.9])
    glwd = np.array([31, 28, 0, 17, 28])
    st = detectors.sub_type(detected, gmw, glwd, LEGEND)
    assert st["labels"].tolist() == ["gmw:mangrove", "glwd:Mangrove", "unattributed",
                                     "glwd:Palustrine, regularly flooded, non-forested", None]
    assert sum(st["counts"].values()) == 4


def test_sub_type_not_computed_when_detector_not_computed():
    st = detectors.sub_type(None, np.zeros(2), np.zeros(2), LEGEND)
    assert st["status"] == "not_computed" and st["labels"] is None


def test_glwd_legend_is_complete():
    assert sorted(int(k) for k in LEGEND) == list(range(34))
    assert LEGEND[28] == "Mangrove" and LEGEND[0] == "Dryland"


def test_dataset_context_reports_shares():
    ctx = detectors.dataset_context({"gmw_cov": np.array([0.0, 0.5]),
                                     "glwd_class": np.array([0, 28])}, LEGEND)
    assert ctx["gmw_mangrove_coverage_mean"] == pytest.approx(0.25)
    assert ctx["glwd_class_pixel_share"] == {"Dryland": 0.5, "Mangrove": 0.5}


# ── ruling 2026-09-25 (second round): "excluded" ────────────────────────────

EXCLUDED = {"excluded": True, "datasets": {"GLIMS/current": {"present": False}}}
PRESENT = {"excluded": False, "datasets": {"GLIMS/current": {"present": True}}}


def test_excluded_detector_is_zero_on_known_nan_elsewhere_with_provenance():
    cfg = load_config()
    out = detectors.run_detector("snow_ice", cfg, {}, np.array([True, False]), EXCLUDED)
    assert out["status"] == "excluded"
    assert out["fraction"][0] == 0.0 and np.isnan(out["fraction"][1])
    assert out["provenance"] == "excluded:GLIMS/current+MODIS/061/MCD12Q1"


def test_present_in_dataset_falls_through_to_thresholds():
    out = detectors.run_detector("snow_ice", load_config(), {}, np.array([True]), PRESENT)
    assert out["status"] == "not_computed" and out["exclusion"] == PRESENT


def test_solar_exclusion_uses_both_inventories_and_carries_caveat():
    spec = load_config()["detectors"]["solar"]
    assert len(spec["exclusion"]) == 2 and "small" in spec["exclusion_caveat"]
    assert detectors.exclusion_provenance(spec).count("+") == 1


def test_mixed_water_vegetation_has_no_exclusion():
    assert not load_config()["detectors"]["mixed_water_vegetation"].get("exclusion")


# ── R2 (2026-09-25, third round): mixed_water_vegetation from datasets ──────

def _mwv_bands(gmw, glwd):
    return {"gmw_cov": np.asarray(gmw, np.float32), "glwd_class": np.asarray(glwd, np.float32)}


def test_mwv_all_dryland_cells_is_computed_mangrove_continuous():
    out = detectors.mixed_water_vegetation(load_config(), _mwv_bands([0.3, 0.0], [0, 0]),
                                           np.array([True, True]))
    assert out["status"] == "computed"
    assert out["fraction"].tolist() == pytest.approx([0.3, 0.0])      # continuous, no 1.0
    assert out["glwd_evidence"]["blocked_pixel_share"] == 0.0
    assert "excluded_per_cell" in out["provenance"]


def test_mwv_blocks_only_pixels_inside_wetland_cells():
    # R2 amended 2026-09-25: per GLWD cell, not per AOI.
    out = detectors.mixed_water_vegetation(load_config(), _mwv_bands([0.3, 0.4], [0, 17]),
                                           np.array([True, True]))
    assert out["status"] == "partial"
    assert out["fraction"][0] == pytest.approx(0.3)                   # Dryland cell: computed
    assert np.isnan(out["fraction"][1])                               # wetland cell: blocked
    assert out["mangrove_fraction"].tolist() == pytest.approx([0.3, 0.4])   # GMW everywhere
    assert out["glwd_evidence"]["blocked_pixel_share"] == pytest.approx(0.5)


def test_mwv_all_wetland_cells_is_not_computed():
    out = detectors.mixed_water_vegetation(load_config(), _mwv_bands([0.3], [28]), np.array([True]))
    assert out["status"] == "not_computed" and np.isnan(out["fraction"][0])


def test_open_water_classes_block_exclusion_for_hyacinth():
    # GLWD 1-7 are lakes/rivers; water hyacinth grows there, so they block too.
    out = detectors.mixed_water_vegetation(load_config(), _mwv_bands([0.0], [1]), np.array([True]))
    assert out["status"] == "not_computed"


def test_mangrove_nan_on_unknown_pixels():
    out = detectors.mixed_water_vegetation(load_config(), _mwv_bands([0.5], [0]), np.array([False]))
    assert np.isnan(out["fraction"][0])
