"""Round-3 unit tests: label states, anchored learner, choice rule. No network."""
import numpy as np
import pytest

from experiments.flood_round3 import labels_r3 as L
from experiments.flood_round3 import model_r3 as M


def _obs(shape, **kw):
    o = {"hand": np.zeros(shape), "slope": np.zeros(shape), "wc_built": np.zeros(shape),
         "ghsl_built": np.zeros(shape), "occ": np.zeros(shape)}
    o.update(kw)
    return o


def test_states_radar_rules_mark_unobserved_never_dry():
    sh = (4, 4)
    hand = np.zeros(sh); hand[0, 0] = 20.0
    slope = np.zeros(sh); slope[0, 1] = 25.0
    built = np.zeros(sh); built[0, 2] = 0.6
    occ = np.zeros(sh); occ[0, 3] = 90.0
    fl = np.zeros(sh, bool); fl[1, 1] = True
    y = L.apply_states(fl, np.ones(sh, bool), _obs(sh, hand=hand, slope=slope, wc_built=built, occ=occ), radar=True)
    assert y[0, 0] == y[0, 1] == y[0, 2] == L.UNOBSERVED
    assert y[0, 3] == L.PERMANENT
    assert y[1, 1] == L.FLOODED and y[2, 2] == L.DRY


def test_states_optical_keeps_built_and_high_ground():
    sh = (2, 2)
    hand = np.full(sh, 30.0)
    built = np.full(sh, 0.9)
    y = L.apply_states(np.zeros(sh, bool), np.ones(sh, bool), _obs(sh, hand=hand, wc_built=built), radar=False)
    assert (y == L.DRY).all()


def test_unobserved_source_cells_stay_unobserved():
    sh = (2, 2)
    obs = np.array([[True, False], [True, True]])
    y = L.apply_states(np.zeros(sh, bool), obs, _obs(sh), radar=False)
    assert y[0, 1] == L.UNOBSERVED


def test_is_radar():
    assert L.is_radar(["Sentinel-1"]) and L.is_radar(["COSMO-SkyMed"]) and not L.is_radar(["WorldView-3", "Pleiades"])


def _table(rng, n=900, shift=0.0):
    side = 30
    elev = rng.normal(5, 2, n)
    f2 = rng.normal(0, 1, n)
    p = 1 / (1 + np.exp(elev - 5 - 1.5 * f2 + shift))
    y = (rng.random(n) < p).astype(np.int8)
    X = np.stack([elev, f2], axis=1).astype(np.float32)
    return {"X": X, "C": -elev[:, None].astype(np.float32), "y": y, "F": ["elev_glo30", "f2"], "ev": {},
            "shape": (side, side)}


def test_lambda_zero_is_the_anchor_ranking():
    rng = np.random.default_rng(0)
    tabs = {f"u{i}": _table(rng) for i in range(4)}
    m = M.fit_anchored(tabs, list(tabs), ["elev_glo30", "f2"], "elev",
                       {"n_estimators": 30, "learning_rate": 0.1, "num_leaves": 7})
    t = tabs["u0"]
    s0 = M.predict(m, t, 0.0)
    assert M.within_auc(s0, t["y"]) == pytest.approx(M.within_auc(-t["X"][:, 0].astype(float), t["y"]), abs=1e-9)


def test_inner_cv_picks_a_positive_lambda_when_the_correction_helps():
    rng = np.random.default_rng(1)
    tabs = {f"u{i}": _table(rng) for i in range(6)}
    region = {n: f"r{i % 3}" for i, n in enumerate(tabs)}
    lam, mean = M.choose_lambda(tabs, list(tabs), region, ["elev_glo30", "f2"], "elev",
                                {"n_estimators": 60, "learning_rate": 0.1, "num_leaves": 7})
    assert lam > 0 and mean[lam] > mean[0.0]


def test_choice_rule_ties_go_to_the_earlier_candidate():
    res = {"elev_hand_lr": {"ci": [0.010, 0.05]}, "anc_elev_lgbm": {"ci": [0.013, 0.07]}, "physics": {"ci": [-0.02, 0.1]}}
    assert M.choose(res, ["physics", "elev_hand_lr", "anc_elev_lgbm"]) == "elev_hand_lr"
    res["anc_elev_lgbm"]["ci"][0] = 0.02
    assert M.choose(res, ["physics", "elev_hand_lr", "anc_elev_lgbm"]) == "anc_elev_lgbm"
