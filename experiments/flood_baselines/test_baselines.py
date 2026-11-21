"""Pure tests for the baseline comparison (no network, no cache)."""
import numpy as np
import pytest

from experiments.flood_baselines import blocks as B
from experiments.flood_baselines import events as E
from experiments.flood_core.registry import registry as REG


def _reg():
    return REG.load()


def test_gate_refuses_every_reserved_unit():
    reg = _reg()
    reserved = [u["event_id"] for u in reg["units"] if u["role"] == "reserved"]
    assert reserved, "the registry should hold the round-4b reserved events"
    for name in reserved:
        with pytest.raises(E.ReservedEventError):
            E.gate(name, reg)


def test_gate_refuses_unknown_names_and_passes_dev():
    reg = _reg()
    with pytest.raises(KeyError):
        E.gate("not_a_registered_event", reg)
    dev = next(u["event_id"] for u in reg["units"] if u["role"] == "dev")
    assert E.gate(dev, reg)["role"] == "dev"


def test_clusters_join_linked_units():
    reg = _reg()
    c = E.clusters(["paiporta", "valencia_2024", "kerala_2018"], reg)
    assert c["paiporta"] == c["valencia_2024"]       # one EMS product (alias)
    assert c["kerala_2018"] != c["valencia_2024"]


def test_correlation_range_of_white_noise_is_one_cell():
    rng = np.random.default_rng(0)
    x = rng.random((80, 80)) < 0.3
    r, _ = B.correlation_range(x.astype(float), np.ones_like(x), 20)
    assert r == 1


def test_correlation_range_of_blocky_field_is_about_its_block():
    x = np.kron(np.random.default_rng(1).random((10, 10)) < 0.4, np.ones((8, 8))).astype(float)
    r, _ = B.correlation_range(x, np.ones_like(x, bool), 30)
    assert 4 <= r <= 10


def test_tile_ids_partition_the_grid():
    t = B.tile_ids((7, 10), 3)
    assert t.shape == (7, 10)
    assert len(np.unique(t)) == 3 * 4
    assert t[0, 0] == t[2, 2] and t[0, 0] != t[3, 0]


def test_paired_bootstrap_point_matches_auc_and_identical_scores_pair_exactly():
    rng = np.random.default_rng(2)
    f = rng.random((60, 60)) < 0.3
    s = f + rng.normal(0, 1, f.shape)
    ok = np.ones_like(f)
    out = B.paired_block_bootstrap({"a": s, "b": s.copy(), "c": -s}, f, ok, 10, 50, 0)
    assert out["tiles"] == 36
    assert out["point"]["a"] == pytest.approx(out["point"]["b"])
    assert out["point"]["a"] == pytest.approx(1 - out["point"]["c"])
    assert np.allclose(out["reps"]["a"], out["reps"]["b"])          # paired
    lo, hi = B.ci(out["reps"]["a"])
    assert lo <= out["point"]["a"] <= hi


def test_cluster_mean_bootstrap_draws_whole_clusters():
    reps = {"x": np.full(10, 0.9), "y": np.full(10, 0.9), "z": np.full(10, 0.1)}
    m = B.cluster_mean_bootstrap(reps, {"x": 0, "y": 0, "z": 1}, 400, 0)
    # a cluster of two at 0.9 and one of one at 0.1: means are 0.9, 0.1, (0.9*2+0.1)/3, ...
    assert set(np.round(np.unique(m), 4)) <= {0.9, 0.1, 0.6333, 0.3667}
