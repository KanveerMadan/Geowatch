r"""
Tests for the paired LOCO harness.

The harness exists to make small effects detectable: comparing MEANS across
11 folds cannot resolve below ~0.035 mIoU, while comparing per-fold DELTAS
cancels the shared city-difficulty variance. These tests verify the machinery
on synthetic data, so a real experiment is not the first time it runs.

Run:  pytest tests/test_loco_harness.py
"""
import numpy as np
import pytest

from experiments.harness.loco import (
    ArmResult, FoldResult, LOCO_CITIES, confusion, folds, format_per_class_comparison,
    holm_bonferroni, iou_from_confusion, min_achievable_wilcoxon_p, miou,
    paired_compare, paired_compare_per_class, per_city_table, per_class_table,
    run_arm, set_determinism,
)


# ── Folds ──

def test_eleven_folds_leave_one_city_out():
    f = list(folds())
    assert len(f) == 11
    for i, held, train in f:
        assert held not in train
        assert len(train) == 10
        assert set(train) | {held} == set(LOCO_CITIES)


def test_fold_order_is_stable():
    assert [h for _, h, _ in folds()] == list(LOCO_CITIES)


# ── Metrics ──

def test_perfect_prediction_gives_iou_one():
    t = np.array([0, 0, 1, 1, 2, 2])
    assert miou(iou_from_confusion(confusion(t, t, 3))) == pytest.approx(1.0)


def test_ignore_index_excluded():
    t = np.array([0, 1, 255, 255])
    p = np.array([0, 1, 2, 2])
    cm = confusion(p, t, 3)
    assert cm.sum() == 2, "ignored pixels must not enter the matrix"


def test_absent_class_is_nan_not_zero():
    """
    A class absent from a held-out city must not be scored 0.0 — that would
    penalise a fold for something its city does not contain, and quietly drag
    every mIoU down.
    """
    t = np.array([0, 0, 1, 1])
    iou = iou_from_confusion(confusion(t, t, 3))
    assert np.isnan(iou[2])
    assert miou(iou) == pytest.approx(1.0), "mIoU must average present classes only"


def test_known_iou_value():
    # truth [0,0,1,1], pred [0,1,1,1]: class0 TP1 FP0 FN1 -> 1/2; class1 TP2 FP1 FN0 -> 2/3
    iou = iou_from_confusion(confusion(np.array([0,1,1,1]), np.array([0,0,1,1]), 2))
    assert iou[0] == pytest.approx(0.5)
    assert iou[1] == pytest.approx(2/3)


# ── Running arms ──

def _fake_fold_fn(quality):
    """A fold_fn whose accuracy varies by city, mimicking real difficulty spread."""
    def fn(i, held, train):
        rng = np.random.default_rng(i)
        t = rng.integers(0, 3, size=400)
        p = t.copy()
        n_wrong = int(len(t) * (1 - quality.get(held, 0.7)))
        idx = rng.choice(len(t), n_wrong, replace=False)
        p[idx] = (p[idx] + 1) % 3
        return {"pred": p, "target": t, "n_classes": 3, "n_train_patches": 100}
    return fn


QUALITY_A = {c: 0.60 + 0.03 * i for i, c in enumerate(LOCO_CITIES)}
QUALITY_B = {c: v + 0.05 for c, v in QUALITY_A.items()}   # uniformly better


def test_run_arm_produces_one_result_per_fold():
    arm = run_arm("a", _fake_fold_fn(QUALITY_A), class_names=["x","y","z"])
    assert len(arm.folds) == 11
    assert [f.city for f in arm.folds] == list(LOCO_CITIES)
    assert arm.meta["complete"] is True


def test_limit_folds_marks_the_result_incomplete():
    """A probe must never be mistakable for a full LOCO number."""
    arm = run_arm("probe", _fake_fold_fn(QUALITY_A), limit_folds=1, class_names=["x","y","z"])
    assert len(arm.folds) == 1
    assert arm.meta["complete"] is False
    assert arm.meta["n_folds_run"] == 1


def test_determinism_same_seed_reproduces():
    a = run_arm("a", _fake_fold_fn(QUALITY_A), seed=7, class_names=["x","y","z"])
    b = run_arm("a", _fake_fold_fn(QUALITY_A), seed=7, class_names=["x","y","z"])
    assert a.mious.tolist() == b.mious.tolist()


def test_seed_is_recorded(tmp_path):
    arm = run_arm("a", _fake_fold_fn(QUALITY_A), seed=99, class_names=["x","y","z"])
    p = arm.save(str(tmp_path / "sub" / "a.json"))
    import json
    assert json.load(open(p))["seed"] == 99


def test_save_load_round_trip(tmp_path):
    arm = run_arm("a", _fake_fold_fn(QUALITY_A), class_names=["x","y","z"])
    back = ArmResult.load(arm.save(str(tmp_path / "a.json")))
    assert back.mious.tolist() == arm.mious.tolist()
    assert back.class_names == arm.class_names


# ── Paired comparison ──

def test_paired_detects_a_uniform_improvement():
    a = run_arm("A", _fake_fold_fn(QUALITY_A), class_names=["x","y","z"])
    b = run_arm("B", _fake_fold_fn(QUALITY_B), class_names=["x","y","z"])
    cmp = paired_compare(a, b)
    assert cmp["median_delta"] > 0
    assert cmp["n_improved"] > cmp["n_worsened"]
    assert cmp["wilcoxon_p"] < 0.05


def test_paired_reports_no_effect_as_no_effect():
    """The negative control — an identical arm must not look like an improvement."""
    a = run_arm("A", _fake_fold_fn(QUALITY_A), class_names=["x","y","z"])
    b = run_arm("A2", _fake_fold_fn(QUALITY_A), class_names=["x","y","z"])
    cmp = paired_compare(a, b)
    assert cmp["median_delta"] == pytest.approx(0.0, abs=1e-9)


def test_pairing_refuses_mismatched_folds():
    a = run_arm("A", _fake_fold_fn(QUALITY_A), class_names=["x","y","z"])
    b = run_arm("B", _fake_fold_fn(QUALITY_B), limit_folds=3, class_names=["x","y","z"])
    with pytest.raises(ValueError, match="different folds"):
        paired_compare(a, b)


def test_paired_is_more_sensitive_than_comparing_means():
    """
    The harness's whole justification. With city difficulty dominating variance,
    an effect far smaller than the between-fold std must still be detectable
    when paired.
    """
    a = run_arm("A", _fake_fold_fn(QUALITY_A), class_names=["x","y","z"])
    small = {c: v + 0.02 for c, v in QUALITY_A.items()}
    b = run_arm("B", _fake_fold_fn(small), class_names=["x","y","z"])
    cmp = paired_compare(a, b)
    spread = a.summary()["std"]
    effect = cmp["mean_delta"]
    assert abs(effect) < spread, "precondition: the effect is smaller than fold spread"
    assert cmp["wilcoxon_p"] < 0.05, "paired test should still detect it"


# ── Reporting ──

def test_per_city_table_lists_every_city():
    a = run_arm("A", _fake_fold_fn(QUALITY_A), class_names=["x","y","z"])
    b = run_arm("B", _fake_fold_fn(QUALITY_B), class_names=["x","y","z"])
    t = per_city_table([a, b])
    for c in LOCO_CITIES:
        assert c in t, f"{c} missing from the per-city table"
    assert "mean" in t and "std" in t


def test_per_class_table_lists_every_class():
    a = run_arm("A", _fake_fold_fn(QUALITY_A), class_names=["roof", "road", "veg"])
    t = per_class_table([a])
    for c in ["roof", "road", "veg"]:
        assert c in t


def test_set_determinism_seeds_numpy():
    set_determinism(5); x = np.random.rand(3)
    set_determinism(5); y = np.random.rand(3)
    assert x.tolist() == y.tolist()


# ── Per-class paired comparison ──

def _arm_from_per_class(name, per_class_by_fold, class_names, cities=None):
    """Build an ArmResult directly from per-class IoU dicts, one per fold."""
    cities = list(cities or LOCO_CITIES)
    arm = ArmResult(name=name, seed=0, class_names=list(class_names),
                    meta={"complete": True, "n_folds_run": len(per_class_by_fold)})
    for i, pc in enumerate(per_class_by_fold):
        vals = [v for v in pc.values() if v is not None]
        arm.folds.append(FoldResult(
            fold=i, city=cities[i], miou=float(np.mean(vals)) if vals else 0.0,
            per_class_iou=dict(pc), n_labeled_px=1000, seconds=0.0))
    return arm


def test_min_achievable_p_floor_below_six_folds():
    """Under six pairs the Wilcoxon cannot reach 0.05 however consistent the effect."""
    assert min_achievable_wilcoxon_p(5) == pytest.approx(0.0625)
    assert min_achievable_wilcoxon_p(6) == pytest.approx(0.03125)
    assert min_achievable_wilcoxon_p(11) == pytest.approx(0.0009765625)
    assert min_achievable_wilcoxon_p(5) > 0.05
    assert min_achievable_wilcoxon_p(6) < 0.05


def test_a_class_absent_from_a_fold_drops_only_that_class():
    names = ["x", "y"]
    a = _arm_from_per_class("A", [{"x": 0.5, "y": None if i < 4 else 0.4}
                                  for i in range(11)], names)
    b = _arm_from_per_class("B", [{"x": 0.6, "y": None if i < 4 else 0.5}
                                  for i in range(11)], names)
    cmp = paired_compare_per_class(a, b)
    assert cmp["per_class"]["x"]["n_folds"] == 11
    assert cmp["per_class"]["y"]["n_folds"] == 7
    assert "accra" not in cmp["per_class"]["y"]["cities"]


def test_underpowered_class_is_flagged_not_called_null():
    """A class present in only five folds must be marked, never read as no-effect."""
    names = ["thin"]
    a = _arm_from_per_class("A", [{"thin": 0.2 if i < 5 else None} for i in range(11)], names)
    b = _arm_from_per_class("B", [{"thin": 0.9 if i < 5 else None} for i in range(11)], names)
    cmp = paired_compare_per_class(a, b)
    e = cmp["per_class"]["thin"]
    assert e["n_folds"] == 5
    assert e["underpowered"] is True
    assert e["mean_delta"] == pytest.approx(0.7)      # a huge, perfectly consistent effect
    assert not e["significant_after_holm"]            # and still not significant


def test_offsetting_per_class_movements_cancel_in_the_mean():
    """The measurement-design case: mIoU still, classes moving hard in opposite directions."""
    names = ["up", "down"]
    a = _arm_from_per_class("A", [{"up": 0.30, "down": 0.70} for _ in range(11)], names)
    b = _arm_from_per_class("B", [{"up": 0.70, "down": 0.30} for _ in range(11)], names)
    assert paired_compare(a, b)["mean_delta"] == pytest.approx(0.0, abs=1e-9)
    cmp = paired_compare_per_class(a, b)
    assert cmp["per_class"]["up"]["mean_delta"] == pytest.approx(+0.4)
    assert cmp["per_class"]["down"]["mean_delta"] == pytest.approx(-0.4)


def test_holm_is_stricter_than_raw_p():
    raw = {"a": 0.01, "b": 0.02, "c": 0.04}
    out = holm_bonferroni(raw, alpha=0.05)
    assert out["a"]["adjusted"] >= raw["a"]
    assert out["c"]["adjusted"] >= raw["c"]
    assert out["a"]["adjusted"] == pytest.approx(0.03)     # 3 * 0.01
    assert out["b"]["adjusted"] == pytest.approx(0.04)     # 2 * 0.02
    assert out["c"]["adjusted"] == pytest.approx(0.04)     # monotone, held up by b


def test_holm_is_monotone_and_handles_missing_p():
    out = holm_bonferroni({"a": 0.001, "b": None, "c": 0.5}, alpha=0.05)
    assert out["b"]["adjusted"] is None and out["b"]["reject"] is False
    assert out["a"]["adjusted"] <= out["c"]["adjusted"]


def test_per_class_pairing_refuses_mismatched_class_names():
    a = _arm_from_per_class("A", [{"x": 0.5} for _ in range(11)], ["x"])
    b = _arm_from_per_class("B", [{"z": 0.5} for _ in range(11)], ["z"])
    with pytest.raises(ValueError, match="different class names"):
        paired_compare_per_class(a, b)


def test_format_per_class_comparison_marks_underpowered():
    names = ["thin"]
    a = _arm_from_per_class("A", [{"thin": 0.2 if i < 5 else None} for i in range(11)], names)
    b = _arm_from_per_class("B", [{"thin": 0.9 if i < 5 else None} for i in range(11)], names)
    txt = format_per_class_comparison(paired_compare_per_class(a, b))
    assert "UNDERPOWERED" in txt
    assert "thin" in txt
