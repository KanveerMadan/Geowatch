"""Tests for the learned flood model's data rules and pure helpers.

    python -m pytest -q experiments/flood_learned/test_learned.py
"""
import numpy as np
import pytest

from experiments.flood_learned import events as LE
from experiments.flood_learned import evaluate as EV
from experiments.flood_learned import features as FT
from experiments.flood_learned import model as M
from experiments.flood_learned import settings as ST


def test_labels_unobserved_never_dry_and_permanent_water_excluded(monkeypatch):
    flooded = np.array([[1, 0, 0], [1, 0, 0]], bool)
    valid = np.array([[1, 1, 0], [1, 1, 1]], bool)
    occ = np.array([[0, 0, 0], [85, 79.9, 90]], float)     # >= 80 % is permanent water
    monkeypatch.setattr(LE.BE, "reference", lambda e: {"flooded": flooded, "valid": valid,
                                                        "block": 1})
    lab = LE.labels({"unit": "x"}, occ)
    assert lab.tolist() == [[1, 0, -1], [-1, 0, -1]]


def test_jrc_reference_units_never_in_batch0():
    names = {c["unit"] for c in LE.batch0()}
    assert not names & set(LE.JRC_REFERENCE_UNITS)
    assert len(names) == 29


def test_no_cluster_spans_two_regions():
    names = [c["unit"] for c in LE.batch0()]
    LE.check_folds(names, LE.clusters(names))


@pytest.mark.parametrize("split", ["lco", "lro"])
def test_folds_hold_whole_clusters_out(split):
    names = [c["unit"] for c in LE.batch0()]
    cl = LE.clusters(names)
    f = M.folds(names, split, cl)
    assert sorted(n for v in f.values() for n in v) == sorted(names)
    for held in f.values():
        train = set(names) - set(held)
        assert not {cl[n] for n in held} & {cl[n] for n in train}


def test_training_rows_drop_unobserved_and_weigh_events_equally():
    t = lambda y: {"X": np.arange(len(y) * len(FT.FEATURES), dtype=np.float32)   # noqa: E731
                   .reshape(len(y), -1), "y": np.array(y, np.int8)}
    tables = {"a": t([1, 0, -1, -1]), "b": t([0] * 9 + [1])}
    X, y, w = M.training_rows(tables, ["a", "b"], [0, 1])
    assert y.size == 12                                # 2 + 10 labelled, no -1
    assert np.isclose(w[:2].sum(), w[2:].sum())


def test_terrain_helpers_on_known_surfaces():
    z = np.zeros((9, 9))
    z[4, 4] = -1.0                                     # a 1 m pit
    assert FT.depression_depth(z)[4, 4] == pytest.approx(1.0)
    assert FT.laplacian(z, 1.0)[4, 4] == pytest.approx(4.0)    # concave > 0
    plane = np.add.outer(np.arange(9.0), np.zeros(9)) * 30.0   # 1 m per m
    assert FT.slope_deg(plane)[4, 4] == pytest.approx(45.0)
    water = np.zeros((9, 9), bool)
    water[0, :] = True
    h = FT.height_above_mapped_water(plane, water)
    assert h[0, 3] == 0 and h[3, 3] == pytest.approx(90.0)
    assert np.isnan(FT.height_above_mapped_water(plane, np.zeros((9, 9), bool))).all()


def test_settings_rules():
    assert ST.kapos_mountain(2600, 0, 0)
    assert ST.kapos_mountain(500, 1, 350) and not ST.kapos_mountain(500, 1, 250)
    assert ST.settlement({"smod_code": {"30": 10, "11": 3}}) == "urban"
    hot_dry = {str(m): {"t_c": 28.0, "p_mm": 8.0} for m in range(1, 13)}
    assert ST.koppen_arid(hot_dry, 25.0)["class"] == "BW"
    wet = {str(m): {"t_c": 25.0, "p_mm": 150.0} for m in range(1, 13)}
    assert not ST.koppen_arid(wet, 10.0)["arid"]


def test_aggregated_calibration_matches_cell_level():
    rng = np.random.default_rng(1)
    p = rng.beta(0.5, 3, 30000)
    y = (rng.uniform(size=p.size) < np.clip(p * 1.3, 0, 1)).astype(float)
    w = np.full(p.size, 1 / p.size)
    Y, P, W = EV._aggregate(y, p, w)
    a1, b1 = EV._cal_fit(y, p, w)
    a2, b2 = EV._cal_fit(Y, P, W)
    assert abs(a1 - a2) < 1e-3 and abs(b1 - b2) < 1e-3
    brier_cells = np.sum(w * (p - y) ** 2)
    brier_agg = np.sum(W * ((P - Y) ** 2 + Y * (1 - Y)))
    assert abs(brier_cells - brier_agg) < 1e-4


def test_calibration_fit_recovers_ideal():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.02, 0.98, 20000)
    y = (rng.uniform(size=p.size) < p).astype(float)
    a, b = EV._cal_fit(y, p, np.full(p.size, 1 / p.size))
    assert abs(a) < 0.05 and abs(b - 1) < 0.05
