"""Item 21 §9 pilot A (redesign ruled 2026-09-28): the pure parts of the
change test -- window, splits, composite, metrics, noise unit, drop table."""
import pathlib
import sys
from datetime import date

import numpy as np
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "experiments" / "item21_sites"))

import pilot_a_change_test as pa


def test_ruled_constants():
    assert (pa.HALF_WINDOW_D, pa.MIN_SCENES, pa.N_SPLITS, pa.NOISE_UNIT_PCT) == (90, 3, 20, 95)
    assert pa.KS == (2, 3, 5) and pa.DROP_AT == (0.05, 0.10, 0.20)


def test_window_single_date_and_range():
    assert pa.window(("2022-03-29",)) == (date(2021, 12, 29), date(2022, 6, 27))
    # a range is extended by 90 d on each side (scenes inside it included)
    assert pa.window(("2024-01-01", "2024-06-30")) == (date(2023, 10, 3), date(2024, 9, 28))


def test_random_halves_seeded_partition():
    for n in (3, 4, 9):
        a, b = pa.random_halves(n, 7)
        assert sorted(np.concatenate([a, b]).tolist()) == list(range(n))
        assert len(a) == -(-n // 2) and len(b) == n // 2
        assert (a == pa.random_halves(n, 7)[0]).all()
    assert any((pa.random_halves(9, s)[0] != pa.random_halves(9, 0)[0]).any() for s in range(1, 5))


def test_chrono_halves_middle_goes_earlier():
    a, b = pa.chrono_halves(5)
    assert a.tolist() == [0, 1, 2] and b.tolist() == [3, 4]
    a, b = pa.chrono_halves(4)
    assert a.tolist() == [0, 1] and b.tolist() == [2, 3]


def test_composite_is_nan_median():
    s = np.full((3, 6, 1, 2), np.nan, np.float32)
    s[:, :, 0, 0] = np.array([0.1, 0.3, 0.2])[:, None]
    s[0, :, 0, 1] = 0.5                                        # one valid obs
    c = pa.composite(s)
    assert np.allclose(c[:, 0, 0], 0.2) and np.allclose(c[:, 0, 1], 0.5)
    s[:, :, 0, 1] = np.nan
    assert np.isnan(pa.composite(s)[:, 0, 1]).all()            # no obs -> NaN, not 0


def test_cell_metrics_angle_and_brightness():
    a = np.ones((6, 1, 3)) * 0.1
    b = a.copy()
    b[:, 0, 1] *= 2                                             # same shape, twice as bright
    b[:, 0, 2] = np.nan                                         # not evaluable
    m = pa.cell_metrics(a, b)
    assert m["angle_deg"][0, 0] == pytest.approx(0, abs=1e-5)
    assert m["angle_deg"][0, 1] == pytest.approx(0, abs=1e-5)   # angle blind to magnitude ...
    assert m["mean_refl_diff"][0, 1] == pytest.approx(0.1)      # ... brightness catches it
    assert np.isnan(m["angle_deg"][0, 2]) and np.isnan(m["mean_refl_diff"][0, 2])
    c = a.copy()
    c[3] = 0.4                                                  # a shape change
    assert pa.cell_metrics(a, c)["angle_deg"][0, 0] > 1


def test_noise_unit_is_median_over_splits_of_p95():
    rng = np.random.default_rng(0)
    stack = (0.1 + rng.normal(0, 0.005, (6, 6, 8, 8))).astype(np.float32)
    cells = np.ones((8, 8), bool)
    nz = pa.noise(stack, cells, n_splits=5)
    for m in pa.METRICS:
        assert len(nz[m]["p95_per_split"]) == 5
        assert nz[m]["unit"] == pytest.approx(np.median(nz[m]["p95_per_split"]))
        assert nz[m]["p50_median_over_splits"] <= nz[m]["unit"] <= nz[m]["p99_median_over_splits"]


def test_changed_either_metric_and_not_evaluable():
    met = {"angle_deg": np.array([[0.5, 3.1, 0.1, np.nan]]),
           "mean_refl_diff": np.array([[0.001, 0.0, 0.05, 0.0]])}
    ch = pa.changed_cells(met, {"angle_deg": 1.0, "mean_refl_diff": 0.01}, 3)
    assert ch[0, :3].tolist() == [0.0, 1.0, 1.0] and np.isnan(ch[0, 3])


def test_tile_share_and_drop_table():
    ch = np.zeros((20, 40))
    ch[:4, :] = 1                                               # 20% of the left tile, 20% of the right
    ch[:, 20:22] = np.nan                                       # right tile: 40 cells not evaluable
    left, right = pa.tile_share(ch, 0, 0), pa.tile_share(ch, 0, 20)
    assert left == {"evaluable": 400, "changed": 80, "share": 0.2}
    assert right["evaluable"] == 360 and right["share"] == pytest.approx(72 / 360)
    rows = [{"stratum": "formal", "shares": {str(k): s for k in pa.KS}} for s in (0.2, 0.07, 0.0)]
    rows.append({"stratum": "mixed", "shares": {str(k): None for k in pa.KS}})
    t = pa.drop_table(rows)
    assert t["formal"]["k3"] == {"5pct": pytest.approx(2 / 3, abs=1e-4), "10pct": pytest.approx(1 / 3, abs=1e-4),
                                 "20pct": pytest.approx(1 / 3, abs=1e-4)}
    assert t["mixed"] == {"n": 1, "no_evaluable": 1, "k2": {"5pct": None, "10pct": None, "20pct": None},
                          "k3": {"5pct": None, "10pct": None, "20pct": None},
                          "k5": {"5pct": None, "10pct": None, "20pct": None}}
    assert t["all"]["n"] == 4 and t["all"]["no_evaluable"] == 1


def test_granules_of_keeps_a_dates_granules_together():
    groups = [[0], [1, 2], [3]]
    assert pa.granules_of(groups, [1, 2]).tolist() == [1, 2, 3]
    rng = np.random.default_rng(1)
    stack = (0.1 + rng.normal(0, 0.005, (4, 6, 5, 5))).astype(np.float32)
    nz = pa.noise(stack, np.ones((5, 5), bool), n_splits=3, groups=groups)
    assert len(nz["angle_deg"]["p95_per_split"]) == 3
