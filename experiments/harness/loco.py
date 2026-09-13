"""
Paired per-fold LOCO evaluation harness.

WHY PAIRED. LOCO mIoU is 0.313 ± 0.056 across 11 folds, so the standard error
on the mean is ~0.017 and a 95% interval on the mean is ~±0.033. Comparing MEANS
between two configurations therefore cannot resolve anything smaller than about
0.035 mIoU — larger than most changes worth testing.

Fold-to-fold variance here is dominated by city difficulty, and city difficulty
is SHARED between any two configurations evaluated on the same folds. Pairing
cancels it: the test is on the 11 per-fold deltas, not on two means. That is
free sensitivity, and it is why this exists before any A/B experiment.

WHAT IT REFUSES TO DO. It never reports a mean without the per-city table. A
change that fixes Nairobi and breaks Cape Town must not be indistinguishable
from a change that does nothing, and a single number makes those identical.

Determinism: every fold seeds python/numpy/torch from `seed + fold_index`, so a
re-run reproduces and folds do not share a draw. The seed is recorded in the
output artifact.

This module contains NO training loop of its own — it takes callables, so the
same harness evaluates any configuration.
"""
from __future__ import annotations

import json
import os
import platform
import random
import time
from dataclasses import dataclass, field, asdict
from typing import Callable, Sequence

import numpy as np

# The 11 training cities define the folds. Fixed order so fold indices are
# stable across runs and comparable across experiments.
LOCO_CITIES: tuple[str, ...] = (
    "accra", "capetown", "dhaka", "dharavi", "guatemala", "hcmc",
    "jakarta", "kigali", "lagos", "nairobi", "nusantara",
)

DEFAULT_SEED = 1337


def set_determinism(seed: int) -> None:
    """Seed every RNG that can affect a fold."""
    random.seed(seed)
    np.random.seed(seed)
    try:
        import torch

        torch.manual_seed(seed)
        torch.use_deterministic_algorithms(False)  # MPS lacks deterministic kernels
    except ImportError:
        pass


def folds(cities: Sequence[str] = LOCO_CITIES):
    """Yield (index, held_out_city, train_cities) — leave-one-city-out."""
    for i, held in enumerate(cities):
        yield i, held, tuple(c for c in cities if c != held)


# ── Metrics ──────────────────────────────────────────────────────────────────

def confusion(pred: np.ndarray, target: np.ndarray, n_classes: int,
              ignore_index: int = 255) -> np.ndarray:
    """Confusion matrix over labelled pixels only. rows=truth, cols=prediction."""
    valid = target != ignore_index
    t = target[valid].astype(np.int64)
    p = pred[valid].astype(np.int64)
    keep = (t >= 0) & (t < n_classes) & (p >= 0) & (p < n_classes)
    return np.bincount(t[keep] * n_classes + p[keep],
                       minlength=n_classes ** 2).reshape(n_classes, n_classes)


def iou_from_confusion(cm: np.ndarray) -> np.ndarray:
    """
    Per-class IoU. Returns NaN for a class absent from BOTH truth and
    prediction — absent is not the same as scored-zero, and averaging a
    fabricated 0.0 into mIoU would silently penalise a fold for a class its
    held-out city does not contain.
    """
    tp = np.diag(cm).astype(np.float64)
    denom = cm.sum(1) + cm.sum(0) - tp
    with np.errstate(invalid="ignore", divide="ignore"):
        iou = np.where(denom > 0, tp / denom, np.nan)
    return iou


def miou(iou: np.ndarray) -> float:
    """Mean over classes that were present. NaN if none were."""
    return float(np.nanmean(iou)) if not np.all(np.isnan(iou)) else float("nan")


# ── Results ──────────────────────────────────────────────────────────────────

@dataclass
class FoldResult:
    fold: int
    city: str
    miou: float
    per_class_iou: dict[str, float]
    n_labeled_px: int
    seconds: float
    n_train_patches: int | None = None


@dataclass
class ArmResult:
    name: str
    seed: int
    class_names: list[str]
    folds: list[FoldResult] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    @property
    def mious(self) -> np.ndarray:
        return np.array([f.miou for f in self.folds], dtype=float)

    def summary(self) -> dict:
        m = self.mious
        return {"mean": float(np.nanmean(m)), "std": float(np.nanstd(m, ddof=1)),
                "n_folds": len(m)}

    def save(self, path: str) -> str:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {
            "name": self.name, "seed": self.seed, "class_names": self.class_names,
            "summary": self.summary(), "meta": self.meta,
            "environment": {"python": platform.python_version(),
                            "platform": platform.platform()},
            "folds": [asdict(f) for f in self.folds],
        }
        with open(path, "w") as fh:
            json.dump(payload, fh, indent=2)
        return path

    @staticmethod
    def load(path: str) -> "ArmResult":
        d = json.load(open(path))
        arm = ArmResult(d["name"], d["seed"], d["class_names"], meta=d.get("meta", {}))
        arm.folds = [FoldResult(**f) for f in d["folds"]]
        return arm


def run_arm(name: str, fold_fn: Callable[[int, str, tuple], dict],
            cities: Sequence[str] = LOCO_CITIES, seed: int = DEFAULT_SEED,
            class_names: Sequence[str] | None = None, meta: dict | None = None,
            limit_folds: int | None = None) -> ArmResult:
    """
    Run one configuration across the folds.

    `fold_fn(fold_index, held_out_city, train_cities)` must return
    {"pred", "target", "n_classes"} and may add "n_train_patches".

    `limit_folds` runs only the first N — for a feasibility probe. A result with
    fewer than all folds records that in `meta`, so it can never be mistaken for
    a full LOCO number later.
    """
    arm = ArmResult(name=name, seed=seed, class_names=list(class_names or []),
                    meta=dict(meta or {}))
    for i, held, train in folds(cities):
        if limit_folds is not None and i >= limit_folds:
            break
        set_determinism(seed + i)
        t0 = time.time()
        out = fold_fn(i, held, train)
        cm = confusion(out["pred"], out["target"], out["n_classes"])
        iou = iou_from_confusion(cm)
        if not arm.class_names:
            arm.class_names = [f"class_{j}" for j in range(out["n_classes"])]
        arm.folds.append(FoldResult(
            fold=i, city=held, miou=miou(iou),
            per_class_iou={c: (None if np.isnan(v) else float(v))
                           for c, v in zip(arm.class_names, iou)},
            n_labeled_px=int((out["target"] != 255).sum()),
            seconds=time.time() - t0,
            n_train_patches=out.get("n_train_patches"),
        ))
    arm.meta["complete"] = (limit_folds is None or limit_folds >= len(cities))
    arm.meta["n_folds_run"] = len(arm.folds)
    return arm


# ── Paired comparison ────────────────────────────────────────────────────────

def paired_compare(a: ArmResult, b: ArmResult) -> dict:
    """
    Compare two arms on their per-fold deltas (b − a).

    Wilcoxon signed-rank is primary: n=11 is far too small to assert normality,
    and a t-test that assumes it can be confidently wrong. The paired t-test is
    reported alongside as a secondary read, not as the decision.
    """
    cities_a = [f.city for f in a.folds]
    cities_b = [f.city for f in b.folds]
    if cities_a != cities_b:
        raise ValueError(
            f"arms evaluated on different folds — pairing is invalid.\n"
            f"  {a.name}: {cities_a}\n  {b.name}: {cities_b}"
        )

    deltas = b.mious - a.mious
    out = {
        "arm_a": a.name, "arm_b": b.name,
        "cities": cities_a,
        "a_per_fold": a.mious.tolist(), "b_per_fold": b.mious.tolist(),
        "deltas": deltas.tolist(),
        "median_delta": float(np.median(deltas)),
        "mean_delta": float(np.mean(deltas)),
        "n_improved": int((deltas > 0).sum()),
        "n_worsened": int((deltas < 0).sum()),
        "a_summary": a.summary(), "b_summary": b.summary(),
        "complete": bool(a.meta.get("complete") and b.meta.get("complete")),
    }
    try:
        from scipy import stats

        if len(deltas) >= 5 and np.any(deltas != 0):
            out["wilcoxon_p"] = float(stats.wilcoxon(deltas).pvalue)
        out["ttest_p"] = float(stats.ttest_rel(b.mious, a.mious).pvalue)
    except ImportError:
        out["note"] = "scipy unavailable — p-values omitted"
    return out


# ── Reporting ────────────────────────────────────────────────────────────────

def per_city_table(arms: Sequence[ArmResult]) -> str:
    """Per-city mIoU for every arm, plus deltas against the first. Never a bare mean."""
    lines = []
    head = f"  {'city':<12}" + "".join(f"{a.name:>14}" for a in arms)
    if len(arms) > 1:
        head += "".join(f"{'Δ '+a.name:>14}" for a in arms[1:])
    lines += [head, "  " + "-" * (len(head) - 2)]
    base = arms[0]
    for i, f in enumerate(base.folds):
        row = f"  {f.city:<12}" + "".join(f"{a.folds[i].miou:14.4f}" for a in arms)
        if len(arms) > 1:
            row += "".join(f"{a.folds[i].miou - f.miou:+14.4f}" for a in arms[1:])
        lines.append(row)
    lines.append("  " + "-" * (len(head) - 2))
    summ = f"  {'mean':<12}" + "".join(f"{a.summary()['mean']:14.4f}" for a in arms)
    lines.append(summ)
    lines.append(f"  {'std':<12}" + "".join(f"{a.summary()['std']:14.4f}" for a in arms))
    return "\n".join(lines)


def per_class_table(arms: Sequence[ArmResult]) -> str:
    """Per-class IoU averaged over folds. Class movement is what explains a change."""
    names = arms[0].class_names
    lines = [f"  {'class':<26}" + "".join(f"{a.name:>14}" for a in arms)]
    lines.append("  " + "-" * (len(lines[0]) - 2))
    for c in names:
        vals = []
        for a in arms:
            v = [f.per_class_iou.get(c) for f in a.folds]
            v = [x for x in v if x is not None]
            vals.append(np.mean(v) if v else float("nan"))
        lines.append(f"  {c:<26}" + "".join(f"{v:14.4f}" for v in vals))
    return "\n".join(lines)


def format_comparison(cmp: dict) -> str:
    lines = [
        f"  paired comparison: {cmp['arm_b']} vs {cmp['arm_a']}",
        f"    folds            : {len(cmp['deltas'])}"
        + ("" if cmp["complete"] else "   *** PARTIAL — not a LOCO result ***"),
        f"    median delta     : {cmp['median_delta']:+.4f}",
        f"    mean delta       : {cmp['mean_delta']:+.4f}",
        f"    improved/worsened: {cmp['n_improved']}/{cmp['n_worsened']}",
    ]
    if "wilcoxon_p" in cmp:
        lines.append(f"    Wilcoxon p       : {cmp['wilcoxon_p']:.4f}  (primary)")
    if "ttest_p" in cmp:
        lines.append(f"    paired t-test p  : {cmp['ttest_p']:.4f}  (secondary)")
    return "\n".join(lines)
