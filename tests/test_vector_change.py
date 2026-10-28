"""
Build item 25 — change over time, built / vegetation / water only.

The pure detection logic is tested here on synthetic unit values. The live
two-epoch run is recorded in 05_BUILD_MANUAL.md item 25.

Run from the repo root:  pytest tests/test_vector_change.py
"""
import numpy as np
import pytest

from vector import change


def _arr(*v):
    return np.array(v, dtype=float)


def test_change_beyond_k_noise_is_named_and_signed():
    va = _arr(0.20, 0.50, 0.30, 0.40)
    vb = _arr(0.21, 0.20, 0.70, 0.40)
    cov = np.ones(4)
    r = change.detect("vegetation", va, vb, cov, cov, noise=0.02)
    st = [u["status"] for u in r["units"]]
    assert st == ["no_detectable_change", "decrease", "increase", "no_detectable_change"]
    assert all(u["fraction"] == "vegetation" for u in r["units"])
    assert r["threshold"] == pytest.approx(change.K_NOISE * 0.02)


def test_change_just_inside_k_noise_is_not_reported():
    va, vb = _arr(0.0), _arr(change.K_NOISE * 0.05 * 0.99)
    r = change.detect("water", va, vb, np.ones(1), np.ones(1), noise=0.05)
    assert r["units"][0]["status"] == "no_detectable_change"


def test_poorly_observed_unit_cannot_masquerade_as_change():
    va, vb = _arr(0.6), _arr(0.0)                     # looks like total vegetation loss
    r = change.detect("vegetation", va, vb, np.ones(1), _arr(0.5), noise=0.01)
    assert r["units"][0]["status"] == "insufficient_observation"


def test_cloudy_epoch_makes_every_unit_unreliable():
    va, vb = _arr(0.6, 0.1), _arr(0.0, 0.9)
    r = change.detect("vegetation", va, vb, np.ones(2), np.ones(2), noise=0.01,
                      epoch_ok=(True, False))
    assert {u["status"] for u in r["units"]} == {"epoch_unreliable"}
    assert r["counts"]["increase"] == r["counts"]["decrease"] == 0


def test_noise_uses_only_well_observed_units():
    va, vb = _arr(0.1, 0.2, 0.3, 0.9), _arr(0.1, 0.2, 0.31, 0.0)
    cov = _arr(1, 1, 1, 0.1)                        # the wild unit is excluded
    assert change.noise_from_pair(va, vb, cov, cov) == pytest.approx(np.std([0, 0, -0.01], ddof=1))


def test_noise_refuses_to_estimate_from_too_few_units():
    with pytest.raises(ValueError):
        change.noise_from_pair(_arr(0.1), _arr(0.2), np.ones(1), np.ones(1))


def test_impervious_paved_bare_are_not_computed():
    nc = change.not_computed_block()
    assert set(nc) == {"impervious_total", "paved", "bare"}
    assert all(v["status"] == "not_computed" for v in nc.values())
    assert set(change.CHANGE_FRACTIONS) == {"built", "vegetation", "water"}


def test_preregistration_is_fixed_in_code():
    assert change.K_NOISE == 3.0
    (a, b) = change.EPOCHS["s2"]
    # same season: same month-day window in both years
    assert a[0][4:] == b[0][4:] and a[1][4:] == b[1][4:]
    assert a[0][:4] != b[0][:4]
    assert change.CHANGE_AOI["expectation"]


def test_unit_values_aggregate_like_item_22():
    from shapely.geometry import box
    from rasterio.transform import from_origin
    tr = from_origin(0, 20, 10, 10)
    raster = np.array([[1.0, 0.0], [np.nan, 0.0]], dtype=np.float32)
    observed = np.isfinite(raster)
    polys = [box(0, 0, 10, 20), box(10, 0, 20, 20)]
    v, c = change.unit_values(polys, raster, observed, tr, (2, 2))
    assert v[0] == pytest.approx(1.0) and c[0] == pytest.approx(0.5)
    assert v[1] == pytest.approx(0.0) and c[1] == pytest.approx(1.0)
