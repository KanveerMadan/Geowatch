"""Item 21 Phase A, part 5 — fraction bookkeeping and placeholder marking."""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from surface_fractions import bookkeeping as bk
from surface_fractions.config import load_config
from surface_fractions.regressors import (PLACEHOLDER, PlaceholderRegressor, Prediction,
                                          placeholder_regressors)


def regs(veg, water, share, known, provenance="regression"):
    mk = lambda v: Prediction(np.where(known, np.asarray(v, dtype=np.float32), np.nan),
                              provenance, {"status": "not_computed"})
    return {"vegetation": mk(veg), "water": mk(water), "impervious_share": mk(share)}


def dets(snow=None, solar=None, mwv=None):
    def d(a):
        if a is None:
            return {"status": "not_computed", "fraction": None}
        return {"status": "computed", "fraction": np.asarray(a, dtype=np.float32)}
    return {"snow_ice": d(snow), "solar": d(solar), "mixed_water_vegetation": d(mwv)}


ZERO = [0.0]


def run(veg, water, share, built, snow=ZERO, solar=ZERO, mwv=ZERO, known=None, smoke=False,
        provenance="regression"):
    n = len(built)
    known = np.ones(n, dtype=bool) if known is None else np.asarray(known)
    return bk.compute_fractions(
        known, np.asarray(built, dtype=np.float32),
        regs(veg, water, share, known, provenance),
        dets(None if snow is None else snow * (n // len(snow)),
             None if solar is None else solar * (n // len(solar)),
             None if mwv is None else mwv * (n // len(mwv))),
        smoke_test=smoke, detector_placeholder_value=0.0)


def test_worked_example_arithmetic():
    r = run([0.2], [0.1], [0.5], built=[0.2])
    p = r["per_pixel"]
    assert p["hard_surface_remainder"][0] == pytest.approx(0.7)
    assert p["impervious_total"][0] == pytest.approx(0.35)
    assert p["bare"][0] == pytest.approx(0.35)
    assert p["paved"][0] == pytest.approx(0.15)
    assert sum(p[n][0] for n in bk.EIGHT) == pytest.approx(1.0)
    assert not r["flags"]["paved_negative"]["pixels"]


def test_negative_paved_clamped_flagged_and_excess_emitted():
    r = run([0.2], [0.1], [0.5], built=[0.6])
    p = r["per_pixel"]
    assert p["paved_unclamped"][0] == pytest.approx(-0.25)
    assert p["paved"][0] == 0.0
    assert p["sum_excess"][0] == pytest.approx(0.25)
    assert sum(p[n][0] for n in bk.EIGHT) == pytest.approx(1.25)
    assert r["flags"]["paved_negative"]["pixels"] == 1
    assert r["fractions"]["paved"]["measured"] is False


def test_eight_sum_to_one_plus_excess_on_random_inputs():
    rng = np.random.default_rng(1)
    n = 500
    r = run(rng.random(n) * 0.5, rng.random(n) * 0.5, rng.random(n), rng.random(n),
            snow=[0.0], solar=[0.0], mwv=[0.0])
    p = r["per_pixel"]
    np.testing.assert_allclose(sum(p[k] for k in bk.EIGHT), 1 + p["sum_excess"], atol=1e-5)
    assert r["sum_check"]["max_abs_deviation_from_1_plus_excess"] < 1e-5


def test_oversubscription_flagged_never_rescaled():
    r = run([0.7], [0.6], [0.5], built=[0.0])
    p = r["per_pixel"]
    assert p["vegetation"][0] == pytest.approx(0.7) and p["water"][0] == pytest.approx(0.6)
    assert p["hard_surface_remainder"][0] == pytest.approx(-0.3)
    assert r["flags"]["nonhard_oversubscribed"]["pixels"] == 1


def test_built_exceeding_remainder_flagged():
    r = run([0.5], [0.3], [1.0], built=[0.5])
    assert r["flags"]["built_exceeds_remainder"]["pixels"] == 1


def test_detector_overrides_vegetation_and_water():
    known = np.ones(2, dtype=bool)
    r = bk.compute_fractions(known, np.zeros(2, np.float32), regs([.4, .4], [.3, .3], [.5, .5], known),
                             {"snow_ice": {"status": "computed", "fraction": np.array([0., 0.])},
                              "solar": {"status": "computed", "fraction": np.array([0., 0.])},
                              "mixed_water_vegetation": {"status": "computed",
                                                         "fraction": np.array([1., 0.])}},
                             smoke_test=False, detector_placeholder_value=0.0)
    p = r["per_pixel"]
    assert p["vegetation"].tolist() == pytest.approx([0.0, 0.4])
    assert p["water"].tolist() == pytest.approx([0.0, 0.3])
    assert p["hard_surface_remainder"][0] == pytest.approx(0.0)
    assert r["precedence"]["detected_pixels"] == 1


def test_two_detectors_on_one_pixel_flagged():
    known = np.ones(1, dtype=bool)
    r = bk.compute_fractions(known, np.zeros(1, np.float32), regs([0], [0], [0.5], known),
                             {"snow_ice": {"status": "computed", "fraction": np.array([1.])},
                              "solar": {"status": "computed", "fraction": np.array([1.])},
                              "mixed_water_vegetation": {"status": "computed",
                                                         "fraction": np.array([0.])}},
                             smoke_test=False, detector_placeholder_value=0.0)
    assert r["flags"]["detector_overlap"]["pixels"] == 1


def test_solar_is_not_added_to_impervious_total():
    known = np.ones(1, dtype=bool)
    r = bk.compute_fractions(known, np.zeros(1, np.float32), regs([0], [0], [0.0], known),
                             {"snow_ice": {"status": "computed", "fraction": np.array([0.])},
                              "solar": {"status": "computed", "fraction": np.array([1.])},
                              "mixed_water_vegetation": {"status": "computed",
                                                         "fraction": np.array([0.])}},
                             smoke_test=False, detector_placeholder_value=0.0)
    assert r["per_pixel"]["impervious_total"][0] == 0.0
    assert r["per_pixel"]["solar"][0] == 1.0


def test_occluded_pixels_are_nan_and_excluded_from_means():
    r = run([0.2, 0.9], [0.1, 0.0], [0.5, 0.5], built=[0.2, 0.0],
            snow=[0.0], solar=[0.0], mwv=[0.0], known=[True, False])
    for n in bk.EIGHT:
        assert np.isnan(r["per_pixel"][n][1])
    assert r["fractions"]["vegetation"]["aoi_mean_known_pixels"] == pytest.approx(0.2)


def test_not_computed_detector_makes_remainder_not_computed_outside_smoke():
    r = run([0.2], [0.1], [0.5], built=[0.2], snow=None)
    f = r["fractions"]
    for n in ("impervious_total", "bare", "paved", "hard_surface_remainder"):
        assert f[n]["status"] == "not_computed" and "snow_ice" in f[n]["reason"]
    assert f["snow_ice"]["status"] == "not_computed"
    assert f["built"]["status"] == "computed"
    assert r["substitutions"] == [] and r["sum_check"] is None


def test_smoke_test_substitutes_placeholder_and_marks_it():
    r = run([0.2], [0.1], [0.5], built=[0.2], snow=None, solar=None, mwv=None, smoke=True)
    f = r["fractions"]
    assert f["snow_ice"]["provenance"] == PLACEHOLDER
    assert f["paved"]["status"] == "computed"
    assert set(f["bare"]["placeholder_inputs"]) >= {"snow_ice", "solar", "mixed_water_vegetation"}
    assert len(r["substitutions"]) == 3
    assert r["contains_placeholder"]


def test_placeholder_taint_propagates_to_every_derived_quantity():
    r = run([0.2], [0.1], [0.5], built=[0.2], provenance=PLACEHOLDER)
    f = r["fractions"]
    for n in ("vegetation", "water", "impervious_total", "bare", "paved"):
        assert f[n]["placeholder_tainted"], n
    assert f["paved"]["placeholder_inputs"] == ["impervious_share", "vegetation", "water"]
    assert f["impervious_total"]["provenance"] == "placeholder:regression"
    assert f["bare"]["provenance"] == "placeholder:residual"
    assert f["paved"]["provenance"] == "placeholder:derived"
    assert f["built"]["provenance"] == "footprints"
    assert not f["built"]["placeholder_tainted"]
    assert r["contains_placeholder"]


def test_no_placeholder_means_no_banner_and_plain_provenance():
    r = run([0.2], [0.1], [0.5], built=[0.2])
    assert not r["contains_placeholder"]
    assert r["fractions"]["impervious_total"]["provenance"] == "regression"


def test_placeholder_regressor_is_constant_and_marked():
    cfg = load_config()
    known = np.array([True, False])
    for t, reg in placeholder_regressors(cfg).items():
        p = reg.predict({}, known)
        assert p.provenance == PLACEHOLDER
        assert p.value[0] == cfg["placeholders"]["regressors"][t] and np.isnan(p.value[1])
        assert p.prediction_interval["status"] == "not_computed"


def test_placeholder_regressor_rejects_out_of_range():
    with pytest.raises(ValueError):
        PlaceholderRegressor("vegetation", 1.5)
