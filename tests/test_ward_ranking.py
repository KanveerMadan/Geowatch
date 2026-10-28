"""Item 26, task 5: the ward-ranking verdict follows the pre-registered bar."""
from experiments.ward_ranking.c3_ward_ranking import MIN_WARDS, STABILITY_RHO_MIN, evaluate


def _vals(n=24):
    up = {w: float(w) for w in range(n)}
    return up, {w: float(n - w) for w in range(n)}


def test_bar_is_the_preregistered_one():
    assert STABILITY_RHO_MIN == 0.80 and MIN_WARDS == 20


def test_identical_order_is_stable_and_reversed_is_unstable():
    up, down = _vals()
    r = evaluate({"a": up, "b": dict(up), "c": down})
    assert r["a_vs_b"] == {"n_wards": 24, "rho": 1.0, "verdict": "stable"}
    assert r["a_vs_c"]["verdict"] == "unstable" and r["a_vs_c"]["rho"] == -1.0


def test_too_few_wards_is_not_evaluated():
    up, _ = _vals()
    sparse = {w: (v if w < 10 else None) for w, v in up.items()}
    r = evaluate({"a": up, "b": sparse, "c": up})
    assert r["a_vs_b"]["verdict"] == "not_evaluated"
    assert r["a_vs_c"]["verdict"] == "stable"
