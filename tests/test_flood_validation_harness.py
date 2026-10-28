"""Item 26, task 8: the flood harness's AUC and pre-registered verdicts."""
import pytest

from experiments.flood_validation.harness import AUC_MIN, auc, verdict


def test_perfect_and_inverted_ranking():
    assert auc([1, 2], [0, 10], [10, 0]) == 1.0
    assert auc([1, 2], [10, 0], [0, 10]) == 0.0


def test_ties_count_half():
    # one scalar site: every cell tied, so no discrimination at all
    assert auc([0.7], [30], [70]) == 0.5


def test_pooled_counts_match_pairwise_definition():
    # sites (score, flooded, dry): pairs flooded>dry / total pairs, ties 1/2
    groups = [(0.2, 1, 3), (0.5, 2, 2), (0.9, 3, 1)]
    P, N = 6, 6
    wins = sum(f1 * d2 * (1.0 if s1 > s2 else 0.5 if s1 == s2 else 0.0)
               for s1, f1, _ in groups for s2, _, d2 in groups)
    assert auc(*zip(*groups)) == pytest.approx(wins / (P * N))


def test_bar_and_minimums():
    assert AUC_MIN == 0.70
    ok = [(0.1, 0, 60), (0.5, 20, 20), (0.9, 60, 0)]
    assert verdict(ok, 3, pooled=True)["verdict"] == "validated"
    bad = [(0.9, 0, 60), (0.5, 20, 20), (0.1, 60, 0)]
    assert verdict(bad, 3, pooled=True)["verdict"] == "failed"
    assert verdict(ok[:2], 2, pooled=True)["verdict"] == "not-run"     # < 3 sites
    assert verdict([(0.1, 10, 900), (0.9, 10, 900)], 2, pooled=False)["verdict"] == "not-run"
