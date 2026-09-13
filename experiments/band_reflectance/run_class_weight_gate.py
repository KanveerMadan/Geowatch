"""
The gate that has to pass before any training on the rebuilt patch set.

Rebuild from the five production builders, recompute class weights with the
notebook's own formula, and compare against the deployed checkpoint. Training
on a set that does not reconstruct produces another uninterpretable control,
which is how the last probe was wasted.

THE TARGET IS SHARPER THAN "THE WEIGHTS MATCH".

A weight vector is scale-free -- it pins the class RATIOS and says nothing
about the total. But the formula inverts: counts are proportional to 1/weight,
so the checkpoint's stored weights plus an assumed total recover the per-class
counts they were computed from. Doing that says which total they came from:

    total 1413  ->  161.06, 33.32, 578.85, 201.04, 73.31, 94.41, 271.01
    total 1272  ->  145.00, 30.00, 521.09, 180.98, 65.99, 84.99, 243.97

The 1272 column is integral to within 0.09; the 1413 column is integral
nowhere. So the deployed weights were computed on the 1272-patch TRAIN split,
not on all 1413. That matches cell 39, the production cell, which does
`full_counts = Counter(p['label'] for p in train_patches)` and overrides cell
18's earlier all_patches version. Feeding [145, 30, 521, 181, 66, 85, 244] back
through the formula returns the checkpoint's weights to max |delta| 5e-5.

WHICH MEANS THE NAIVE COMPARISON IS CONFOUNDED. Weights recomputed on the
rebuilt `all_patches` are not the same statistic as weights computed on a
random, unstratified 90% draw from it. On a class with 30 members a +/-3 swing
in the draw moves that class's inverse-frequency weight by 5%, which is most of
any residual. So the gate asks the question that is actually decidable:

    is the checkpoint's train split a plausible draw from this rebuild?

Monte Carlo over the draw answers it, and per-class hypergeometric tails say
which class fails if one does. A rebuild that is right but shuffled differently
puts the checkpoint inside the simulated cloud. A rebuild genuinely short of
patches pins a class out in the tail however the split falls.
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.band_reflectance.production_patches_v2 import (  # noqa: E402
    CATEGORIES, NUM_CLASSES, build_all_patches, class_weights_from, implied_counts,
)

CKPT_WEIGHTS = np.array([0.6135, 2.9653, 0.1707, 0.4915, 1.3479, 1.0466, 0.3646])
CKPT_N_TRAIN = 1272
CKPT_N_MONITOR = 141
CKPT_TOTAL = CKPT_N_TRAIN + CKPT_N_MONITOR       # 1413

TOTAL_TOL = 30          # absolute, on the rebuilt all_patches total
Z_TOL = 3.0             # per-class, on the hypergeometric draw
BEST_DRAW_TOL = 0.05    # max |delta weight| achievable by some split
N_SIM = 20000
SIM_SEED = 1337


def weights_from_counts(counts) -> np.ndarray:
    c = np.maximum(np.asarray(counts, dtype=np.float64), 1.0)
    w = 1.0 / c
    return w / w.sum() * NUM_CLASSES


def main() -> int:
    print("=" * 76)
    print("CLASS-WEIGHT GATE -- 5-builder rebuild vs the deployed checkpoint")
    print("=" * 76)

    train_implied = implied_counts(CKPT_WEIGHTS, CKPT_N_TRAIN)
    all_implied = implied_counts(CKPT_WEIGHTS, CKPT_TOTAL)
    required_train = np.round(train_implied).astype(int)

    print("\n1. Inverting the checkpoint's own weights to per-class counts")
    print(f"   {'class':<26} {'train(1272)':>12} {'all(1413)':>11}")
    for c, t, a in zip(CATEGORIES, train_implied, all_implied):
        print(f"   {c:<26} {t:12.2f} {a:11.2f}")
    print(f"   {'max residual from integer':<26} "
          f"{np.abs(train_implied - np.round(train_implied)).max():12.3f} "
          f"{np.abs(all_implied - np.round(all_implied)).max():11.3f}")
    rt = weights_from_counts(required_train)
    print(f"\n   round-trip of the 1272 counts -> max |delta| vs checkpoint: "
          f"{np.abs(rt - CKPT_WEIGHTS).max():.6f}")
    print("   => the deployed weights are TRAIN-split weights (cell 39), not "
          "all_patches weights.")

    print("\n" + "-" * 76)
    print("2. Rebuilding from the five production builders")
    print("-" * 76)
    patches = build_all_patches(verbose=True)
    print("-" * 76)

    total = len(patches)
    counts = Counter(p["label"] for p in patches)
    src = Counter(p["source"] for p in patches)
    all_counts = np.array([counts.get(c, 0) for c in CATEGORIES], dtype=np.int64)
    weights = class_weights_from(patches)

    print("\n   Source distribution:")
    for s, n in sorted(src.items(), key=lambda kv: -kv[1]):
        print(f"     {s:<22} {n:>5}")
    print(f"\n   Rebuilt total {total}   checkpoint {CKPT_TOTAL}   "
          f"delta {total - CKPT_TOTAL:+d}")

    print("\n   Per-class counts vs the 1413-scaled target:")
    print(f"     {'class':<26} {'rebuilt':>8} {'target':>8} {'delta':>7}")
    for c, got, want in zip(CATEGORIES, all_counts, all_implied):
        print(f"     {c:<26} {int(got):8d} {want:8.1f} {got - want:+7.1f}")

    print("\n   Weights on all_patches (the CONFOUNDED comparison, for reference):")
    print(f"     {'class':<26} {'rebuilt':>9} {'checkpoint':>11} {'delta':>9}")
    for c, w, k in zip(CATEGORIES, weights, CKPT_WEIGHTS):
        print(f"     {c:<26} {w:9.4f} {k:11.4f} {w - k:+9.4f}")
    print(f"     max |delta| {np.abs(weights - CKPT_WEIGHTS).max():.4f}   "
          f"correlation {np.corrcoef(weights, CKPT_WEIGHTS)[0, 1]:.4f}")

    # --- 3. the decidable question ------------------------------------------
    print("\n" + "-" * 76)
    print("3. Is the checkpoint's train split a plausible draw from this rebuild?")
    print("-" * 76)

    n_val = max(1, int(total * 0.10))
    print(f"\n   With total {total}, cell 39's PROD_VAL_FRACTION=0.10 gives "
          f"n_val {n_val}, n_train {total - n_val}.")
    print(f"   The checkpoint recorded n_train {CKPT_N_TRAIN}, so its all_patches "
          f"was exactly {CKPT_TOTAL}.")

    rng = np.random.default_rng(SIM_SEED)
    labels = np.array([CATEGORIES.index(p["label"]) for p in patches])
    draw = min(CKPT_N_TRAIN, total)
    sims = np.empty((N_SIM, NUM_CLASSES))
    for i in range(N_SIM):
        idx = rng.choice(total, size=draw, replace=False)
        sims[i] = weights_from_counts(np.bincount(labels[idx], minlength=NUM_CLASSES))

    max_dev = np.abs(sims - CKPT_WEIGHTS).max(axis=1)
    best_draw = float(max_dev.min())
    print(f"\n   {N_SIM} random {draw}-of-{total} draws, max |delta| vs checkpoint:")
    print(f"     best    {best_draw:.4f}")
    print(f"     median  {np.median(max_dev):.4f}")

    print("\n   Per-class: is the required train count reachable?")
    print(f"     {'class':<26} {'need':>6} {'have':>6} {'E[draw]':>8} {'sd':>6} {'z':>7}")
    p = draw / total
    fails = []
    for j, c in enumerate(CATEGORIES):
        have, need = int(all_counts[j]), int(required_train[j])
        mean = have * p
        var = have * p * (1 - p) * (total - have) / (total - 1)
        sd = float(np.sqrt(max(var, 1e-12)))
        z = (need - mean) / sd
        if need > have or abs(z) > Z_TOL:
            fails.append(c)
        print(f"     {c:<26} {need:6d} {have:6d} {mean:8.1f} {sd:6.1f} {z:+7.2f}"
              + ("  IMPOSSIBLE" if need > have else "" if abs(z) <= Z_TOL else "  OUT"))

    total_ok = abs(total - CKPT_TOTAL) <= TOTAL_TOL
    counts_ok = not fails
    draw_ok = best_draw <= BEST_DRAW_TOL

    print("\n" + "=" * 76)
    print(f"   total       |{total} - {CKPT_TOTAL}| = {abs(total - CKPT_TOTAL)} "
          f"<= {TOTAL_TOL}                {'PASS' if total_ok else 'FAIL'}")
    print(f"   per-class   every class reachable, |z| <= {Z_TOL}        "
          f"{'PASS' if counts_ok else 'FAIL'}"
          + (f"  ({', '.join(fails)})" if fails else ""))
    print(f"   weights     some split reaches max |delta| {best_draw:.4f} "
          f"<= {BEST_DRAW_TOL}   {'PASS' if draw_ok else 'FAIL'}")
    verdict = total_ok and counts_ok and draw_ok
    print(f"\n   GATE: {'PASS -- proceed to the fidelity run' if verdict else 'FAIL -- do not train'}")
    print("=" * 76)
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
