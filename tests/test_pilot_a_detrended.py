"""Change-test fix decided 2026-09-29: de-trend by the site-wide median per
metric, k = 3, drop a tile above 10 % changed cells."""
import pathlib
import sys

import numpy as np
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "experiments" / "item21_sites"))

import pilot_a_detrended as pd_


def test_decided_constants():
    assert (pd_.K, pd_.DROP_ABOVE, pd_.STOP_IF_SITE_DROPS_ABOVE) == (3, 0.10, 0.30)


def test_uniform_shift_is_removed_by_detrending():
    met = {"angle_deg": np.full((4, 4), 5.0), "mean_refl_diff": np.full((4, 4), 0.06)}
    met["angle_deg"][0, 0] = 20.0                           # one real change on top of the shift
    cells = np.ones((4, 4), bool)
    detr, med = pd_.detrend(met, cells)
    assert med == {"angle_deg": 5.0, "mean_refl_diff": 0.06}
    ch = pd_.changed(detr, {"angle_deg": 1.0, "mean_refl_diff": 0.01}, 3)
    assert ch.sum() == 1 and ch[0, 0] == 1                  # the shift alone flags nothing


def test_median_is_over_eligible_evaluable_cells_only():
    v = np.array([[1.0, 2.0, 3.0, 100.0]])
    cells = np.array([[True, True, True, False]])
    _, med = pd_.detrend({"angle_deg": v, "mean_refl_diff": v}, cells)
    assert med["angle_deg"] == 2.0
    v[0, 1] = np.nan
    _, med = pd_.detrend({"angle_deg": v, "mean_refl_diff": v}, cells)
    assert med["angle_deg"] == 2.0                          # median of 1 and 3


def test_drop_is_strictly_above_ten_percent():
    ch = np.zeros((20, 20))
    ch.flat[:40] = 1                                        # exactly 10 %
    t = [{"tile_id": "a", "stratum": "formal", "r0": 0, "c0": 0}]
    assert pd_.tile_decisions(ch, t)[0]["dropped"] is False
    ch.flat[40] = 1
    assert pd_.tile_decisions(ch, t)[0]["dropped"] is True


def test_signed_brightness_sees_change_against_the_trend():
    before = np.full((6, 1, 3), 0.10)
    after = before + 0.05                                   # site brightens by 0.05
    after[:, 0, 2] = 0.05                                   # this cell darkens by 0.05
    d = pd_.signed_brightness(before, after)
    assert d.ravel().tolist() == pytest.approx([0.05, 0.05, -0.05])
    unsigned = np.abs(d) - np.median(np.abs(d))             # the rule's metric, de-trended
    signed = np.abs(d - np.median(d))
    assert unsigned[0, 2] == pytest.approx(0) and signed[0, 2] == pytest.approx(0.10)
