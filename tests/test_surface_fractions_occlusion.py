"""
Item 21 Phase A, part 2 — occlusion attribution rules (Decision 14,
Phase A rulings 2026-09-25). Pure numpy; no Earth Engine.
"""
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from surface_fractions import occlusion
from surface_fractions.config import load_config


def counts(**per_pixel):
    """Build count arrays for a 1xN strip. Each kwarg is a list over pixels;
    n_total is derived so the categories always add up."""
    n = len(next(iter(per_pixel.values())))
    out = {f"n_{c}": np.array(per_pixel.get(c, [0] * n)) for c in occlusion.COUNT_CATEGORIES}
    out["n_total"] = sum(out[f"n_{c}"] for c in occlusion.COUNT_CATEGORIES)
    return {k: v.reshape(1, n) for k, v in out.items()}


def test_pixel_with_any_valid_observation_is_known():
    r = occlusion.resolve_occlusion(counts(valid=[1], cloud=[9]), snow_ice=np.zeros((1, 1)))
    assert r["known"].all()
    assert r["fields"]["observed_fraction"] == 1.0
    assert r["fields"]["causes"]["cloud"]["pixel_share"] == 0.0
    # ...but its removed observations still show in the observation share.
    assert r["fields"]["causes"]["cloud"]["removed_observation_share"] == pytest.approx(0.9)


def test_single_cause_attribution():
    c = counts(cloud=[3, 0, 0, 0], nodata=[0, 2, 0, 0], fire=[0, 0, 1, 0], snow=[0, 0, 0, 2])
    r = occlusion.resolve_occlusion(c, snow_ice=np.zeros((1, 4)))
    px = r["pixels"]
    assert px["cloud"].tolist() == [[True, False, False, False]]
    assert px["nodata"].tolist() == [[False, True, False, False]]
    assert px["fire"].tolist() == [[False, False, True, False]]
    assert px["transient_snow"].tolist() == [[False, False, False, True]]
    assert not px["multiple_causes"].any()
    assert r["fields"]["observed_fraction"] == 0.0


def test_mixed_causes_go_to_multiple_causes_never_split():
    r = occlusion.resolve_occlusion(counts(cloud=[2], fire=[1]), snow_ice=np.zeros((1, 1)))
    assert r["pixels"]["multiple_causes"].all()
    assert not r["pixels"]["cloud"].any() and not r["pixels"]["fire"].any()


def test_every_occluded_pixel_has_exactly_one_field():
    rng = np.random.default_rng(0)
    c = {f"n_{k}": rng.integers(0, 3, size=(20, 20)) for k in occlusion.COUNT_CATEGORIES}
    c["n_total"] = sum(c.values())
    snow_ice = rng.integers(0, 2, size=(20, 20))
    r = occlusion.resolve_occlusion(c, snow_ice)
    stacked = sum(p.astype(int) for p in r["pixels"].values())
    assert (stacked == (~r["known"]).astype(int)).all()


def test_snow_on_snow_ice_pixel_is_surface_not_occlusion():
    r = occlusion.resolve_occlusion(counts(snow=[4]), snow_ice=np.ones((1, 1)))
    assert r["known"].all()
    assert r["use_snow_composite"].all()
    assert r["fields"]["causes"]["transient_snow"]["removed_observation_share"] == 0.0


def test_snow_elsewhere_is_transient_occlusion():
    r = occlusion.resolve_occlusion(counts(snow=[4], cloud=[0]), snow_ice=np.zeros((1, 1)))
    assert not r["known"].any()
    assert r["pixels"]["transient_snow"].all()


def test_snow_without_snow_ice_is_unresolved_not_guessed():
    r = occlusion.resolve_occlusion(counts(snow=[4], valid=[0]), snow_ice=None)
    f = r["fields"]["causes"]
    assert f["transient_snow"]["status"] == "not_computed"
    assert f["snow_unresolved"]["pixels"] == 1
    assert r["pixels"]["snow_unresolved"].all()


def test_no_snow_anywhere_means_transient_snow_is_a_measured_zero():
    r = occlusion.resolve_occlusion(counts(valid=[3]), snow_ice=None)
    t = r["fields"]["causes"]["transient_snow"]
    assert t["status"] == "computed" and t["pixels"] == 0
    assert "snow_unresolved" not in r["fields"]["causes"]


def test_pixel_no_scene_covered_is_nodata():
    r = occlusion.resolve_occlusion(counts(valid=[0]), snow_ice=np.zeros((1, 1)))
    assert r["pixels"]["nodata"].all()


def test_shadow_full_is_not_computed_and_scl3_is_not_an_input():
    r = occlusion.resolve_occlusion(counts(valid=[1]), snow_ice=np.zeros((1, 1)))
    assert r["fields"]["causes"]["shadow_full"]["status"] == "not_computed"
    assert "shadow" not in occlusion.COUNT_CATEGORIES
    assert 3 not in sum(load_config()["occlusion"]["scl_codes"].values(), [])


def test_smoke_and_ships_have_no_producer_and_are_named_in_the_caveat():
    r = occlusion.resolve_occlusion(counts(valid=[1]), snow_ice=np.zeros((1, 1)))
    f = r["fields"]
    assert f["causes"]["smoke"] == {"status": "no_producer"}
    assert f["causes"]["ships"] == {"status": "no_producer"}
    for c in ("shadow_full", "smoke", "ships"):
        assert c in f["denominator_caveat"]


def test_firms_gap_is_carried_as_a_caveat():
    r = occlusion.resolve_occlusion(counts(valid=[1]), snow_ice=np.zeros((1, 1)),
                                    firms_complete=False)
    assert "caveat" in r["fields"]["causes"]["fire"]


def test_observable_composite_uses_snow_median_only_on_snow_ice():
    bands = {f"cv_{b}": np.array([[0.1, 0.1, 0.1]]) for b in occlusion.S2_BAND_NAMES}
    bands.update({f"cvs_{b}": np.array([[0.9, 0.9, 0.9]]) for b in occlusion.S2_BAND_NAMES})
    occ = {"use_snow_composite": np.array([[True, False, False]]),
           "known": np.array([[True, True, False]])}
    out = occlusion.observable_composite(bands, occ)
    assert out["Blue"][0, 0] == pytest.approx(0.9)
    assert out["Blue"][0, 1] == pytest.approx(0.1)
    assert np.isnan(out["Blue"][0, 2])


def test_config_setting_an_unimplemented_criterion_is_refused():
    cfg = load_config()
    occlusion.check_config(cfg)
    cfg["occlusion"]["shadow_full"]["criterion"] = 0.1
    with pytest.raises(NotImplementedError):
        occlusion.check_config(cfg)
