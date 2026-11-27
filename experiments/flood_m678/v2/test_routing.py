"""Step 3 synthetic terrain tests (BUILD_PLAN step 3), before any fitting."""
import importlib.util
import os

import numpy as np
import pytest

HERE = os.path.dirname(__file__)


def _load(n):
    spec = importlib.util.spec_from_file_location(n, os.path.join(HERE, f"{n}.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


R = _load("routing")
F = _load("forcing")


def valley(n=41, river=20, slope=0.5):
    c = np.arange(n)[None, :].repeat(n, 0)
    return 100.0 + slope * np.abs(c - river).astype(float)


def river_cells(n=41, river=20):
    return (np.arange(n), np.full(n, river))


def test_zero_release_and_level_below_bed_flood_nothing():
    z = valley()
    assert R.connected_depth(z, [river_cells()], [99.0]).sum() == 0
    lv, d = R.volume_limited(z, river_cells(), 105.0, 0.0, 900.0)
    assert d.sum() == 0


def test_disconnected_basin_stays_dry():
    z = valley()
    z[5:10, 2:6] = 98.0                       # a hollow behind a ridge, lower than the river
    z[4:11, 1:7] = np.maximum(z[4:11, 1:7], 120.0)
    z[5:10, 2:6] = 98.0
    d = R.connected_depth(z, [river_cells()], [102.0])
    assert (d[5:10, 2:6] == 0).all()          # elevation would rank it wettest; connectivity does not
    assert d[:, 18:23].sum() > 0


def test_intact_levee_protects_breach_opens():
    z = valley(slope=0.05)                     # flat floodplain
    bar = np.zeros_like(z)
    bar[:, 25] = 5.0                           # levee crest 5 m on the right bank
    intact = R.connected_depth(z, [river_cells()], [100.8], barrier=bar)
    assert (intact[:, 26:] == 0).all() and intact[:, 21:25].sum() > 0
    gap = np.zeros_like(z, bool)
    gap[18:22, 25] = True                      # mapped breach
    breached = R.connected_depth(z, [river_cells()], [100.8], barrier=bar, breach=gap)
    assert breached[:, 26:].sum() > 0          # protected side floods only in the breached scenario


def test_opposite_bank_and_tributary_use_their_own_levels():
    z = valley()
    left = (np.arange(41), np.full(41, 5))     # a tributary channel at column 5
    z[:, 5] = 101.0
    d = R.connected_depth(z, [river_cells(), left], [101.5, 100.5])
    assert d[:, 5].sum() == 0                  # tributary level below its bed stays dry


def test_finite_volume_conserved_and_bounded():
    z = valley(slope=0.1)
    lv, d = R.volume_limited(z, river_cells(), 104.0, 2.0e5, 900.0)
    assert abs(d.sum() * 900.0 - 2.0e5) / 2.0e5 < 0.02
    full = R.connected_depth(z, [river_cells()], [104.0])
    assert d.sum() <= full.sum() and lv < 104.0


def test_datum_shift_does_not_change_ranks():
    z = valley()
    d1 = R.connected_depth(z, [river_cells()], [102.0])
    d2 = R.connected_depth(z + 37.5, [river_cells()], [139.5])
    assert np.allclose(d1, d2)


def test_backwater_raises_upstream_reach_only():
    z = valley()
    up = (np.arange(0, 20), np.full(20, 20))
    dn = (np.arange(20, 41), np.full(21, 20))
    jam_bar = np.zeros_like(z)
    jam_bar[19, :] = 6.0                       # the jam: an obstruction across row 19 (channel included)
    base = R.connected_depth(z, [up, dn], [101.0, 101.0], barrier=jam_bar)
    jam = R.connected_depth(z, [up, dn], [103.0, 101.0], barrier=jam_bar)   # surcharge upstream only
    assert jam[:19].sum() > base[:19].sum()
    assert np.allclose(jam[21:], base[21:])


def test_unknown_terrain_is_impassable():
    z = valley()
    z[:, 22] = np.nan
    d = R.connected_depth(z, [river_cells()], [103.0])
    assert (d[:, 23:] == 0).all() and np.isfinite(d).all()


def test_rating_curve_monotone_and_invertible():
    hand = np.repeat(np.linspace(0, 10, 50), 20)
    ys, Q = F.rating(hand, 0.02, 900.0, 600.0, 0.001)
    assert (np.diff(Q) >= 0).all() and Q[-1] > 0
    y = F.stage_for(Q[150], ys, Q)
    assert abs(y - ys[150]) < 0.06
    assert F.stage_for(-1, ys, Q) == ys[0]


def test_discharge_scaling():
    assert F.scale_discharge(100.0, 1000.0, 1000.0) == 100.0
    assert F.scale_discharge(100.0, 1000.0, 500.0) == pytest.approx(100 * 0.5 ** 0.8)


def test_physics_score_is_depth_when_connected_and_margin_behind_ridge():
    z = valley()
    z[:, 30] = 110.0                            # ridge at column 30
    s = R.physics_score(z, [river_cells()], [102.0])
    assert s[5, 20] == pytest.approx(2.0)       # depth in the channel
    assert s[5, 22] == pytest.approx(1.0)       # 1 m deep on the bank
    assert s[5, 32] == pytest.approx(102.0 - 110.0)   # behind the ridge: needs 8 m more
    assert np.isfinite(s).all()
    assert s[5, 26] > s[5, 32]                  # same terrain height class, but connected beats blocked
