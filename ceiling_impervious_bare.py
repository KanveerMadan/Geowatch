"""
Dedicated ceiling for the impervious-vs-bare split.

Why this exists
---------------
06_UNMIXING_CEILING.md established a ceiling of 0.490 for `built` fraction and
0.822 for `impervious` (built + paved). From the gap between 0.822 and the
0.964 all-hard-surface figure it was INFERRED that impervious-vs-bare is "the
new weakest boundary". That was an inference from a difference of two numbers,
not a measurement of that specific split, and it was used to support a strong
claim -- "unidentifiable in principle, no remediation, ever".

0.822 is a much softer ceiling than 0.490. Those two situations warrant
different language and different downstream treatment, and only one of them is
currently earned. This script measures the split directly.

PRE-REGISTERED, fixed before any result existed
-------------------------------------------------
QUESTION: what is the ceiling R^2 for `impervious` fraction specifically when
`bare` is the confuser, under the same optimistic conditions used for the
built/paved ceiling?

DECISION RULE -- three-way, mirroring the bands already used in
ceiling_built_fraction.py so the two results are directly comparable:

  ceiling R^2 <  UNIDENTIFIABLE_MAX (0.50)
      -> "unidentifiable in principle" holds, same claim as built/paved.
         Justifies a no-remediation framing.
  ceiling R^2 >= SOFT_BOUNDARY_MIN (0.70)
      -> NOT unidentifiable. The correct framing is "the weakest remaining
         boundary, warranting its own confidence marker" -- recoverable, just
         less well than vegetation or water.
  between -> INDETERMINATE. Neither framing earned; say so.

PRIMARY SCENE: "realistic" -- all six measured endmembers, the same mixture
    proportions used for the built/paved ceiling, so the two numbers are
    comparable. Noise NOISE_PRIMARY = 0.005 (S2 L2A BOA order), swept.

STRESS SCENES, reported but NOT carrying the verdict:
  "pairwise"       impervious and bare only. Removes vegetation and water,
                   which are the easy classes, so this is strictly harder than
                   any real scene. A conservative lower bound.
  "bare_dominated" all six endmembers with bare proportion raised, standing in
                   for a dry-season arid AOI -- the WorldCover Africa failure
                   regime (47.1% built-up user's accuracy, bare compacted earth
                   called built), which is much of this project's training set.

Conditions are the same optimistic ones as the built/paved ceiling: exact
labels, exactly linear mixing, fixed endmembers with no within-class
variability, no shadow, no atmospheric residual, and a random split that
removes the transfer problem. Reality is worse on every axis, so each number
is an upper bound.

CONTROL / SELF-TEST: the same simulation targeting vegetation, which is 23-26
deg from everything. If that does not recover above CONTROL_MIN_R2 the
simulation is broken and no verdict below means anything.

BLIND-SPOT AUDIT, before running -- "what wrong answer would still pass?"
  * Too little bare in the mixture makes impervious look easy. GUARD: bare
    proportion is swept explicitly via the stress scenes, not fixed at one
    convenient value.
  * The pairwise scene removes the easy classes and could overstate difficulty,
    producing a falsely pessimistic "unidentifiable". GUARD: it is explicitly
    NOT the primary; the realistic scene carries the verdict.
  * Understating noise inflates every ceiling. GUARD: swept, not asserted.
  * R^2 and MAE are in the target's own units, so a magnitude error cannot pass
    unnoticed the way it did with SISAL's scale-invariant angle metric.
  * Realised target mean/sd are printed for every scene so a degenerate target
    distribution is visible rather than hidden.

Usage:
    python ceiling_impervious_bare.py
"""

import argparse

import numpy as np

import ceiling_built_fraction as cbf
import regress_built_fraction as base

# --- pre-registered; not edited after seeing results ---------------------
UNIDENTIFIABLE_MAX = 0.50
SOFT_BOUNDARY_MIN = 0.70

NOISE_PRIMARY = 0.005
NOISE_SWEEP = [0.0, 0.002, 0.005, 0.010, 0.020]

N_PIXELS = 40000
SEED = 42
CONTROL_MIN_R2 = 0.90
# -------------------------------------------------------------------------

ORDER = cbf.ORDER          # built_fabric, built_inst, paved, bare, veg, water
IMPERVIOUS_IDX = [0, 1, 2]
BARE_IDX = [3]
VEG_IDX = [4]

# Same proportions as the built/paved ceiling, so results are comparable.
ALPHA_REALISTIC = np.array([0.45, 0.12, 0.35, 0.7, 0.7, 0.08])
# Impervious and bare only.
ALPHA_PAIRWISE = np.array([0.45, 0.12, 0.35, 0.9, 0.0, 0.0])
# Dry-season arid stand-in: bare raised well above the others.
ALPHA_BARE_DOM = np.array([0.30, 0.08, 0.22, 2.4, 0.5, 0.05])

SCENES = [
    ("realistic (PRIMARY)", ALPHA_REALISTIC),
    ("pairwise imperv+bare", ALPHA_PAIRWISE),
    ("bare-dominated", ALPHA_BARE_DOM),
]


def simulate(n, noise, rng, alpha):
    M = np.array([cbf.EM[k] for k in ORDER])
    A = rng.dirichlet(alpha + 1e-9, size=n)
    X = A @ M
    if noise > 0:
        X = X + rng.normal(scale=noise, size=X.shape)
    return X, A


def verdict(r2):
    if r2 < UNIDENTIFIABLE_MAX:
        return "UNIDENTIFIABLE IN PRINCIPLE (same claim as built/paved)"
    if r2 >= SOFT_BOUNDARY_MIN:
        return "WEAKEST REMAINING BOUNDARY -- recoverable, needs a marker"
    return "INDETERMINATE -- neither framing earned"


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()

    print("PRE-REGISTERED DECISION RULE (impervious vs bare):")
    print(f"  R2 <  {UNIDENTIFIABLE_MAX} -> unidentifiable in principle")
    print(f"  R2 >= {SOFT_BOUNDARY_MIN} -> weakest remaining boundary, "
          f"not unidentifiable")
    print(f"  between -> indeterminate")
    print(f"  primary scene = realistic, noise = {NOISE_PRIMARY}")
    print("  Conditions optimistic by construction; reality is worse on every "
          "axis.\n")

    rng = np.random.default_rng(SEED)

    # ---- control -------------------------------------------------------
    Xc, Ac = simulate(N_PIXELS, NOISE_PRIMARY, rng, ALPHA_REALISTIC)
    yv = Ac[:, VEG_IDX].sum(axis=1)
    ctrl = None
    print("CONTROL (self-test): target = vegetation, 23-26 deg from all else")
    for model, r2, mae in cbf.evaluate(Xc, yv, rng):
        print(f"    {model:<6} R2={r2:>6.3f} MAE={mae:.4f}")
        if model == base.PRIMARY_MODEL:
            ctrl = r2
    if ctrl is None or ctrl < CONTROL_MIN_R2:
        print(f"  -> FAILS (bar {CONTROL_MIN_R2}). ABORT.")
        return
    print(f"  -> OK (bar {CONTROL_MIN_R2})\n")

    # ---- the measurement ------------------------------------------------
    primary_r2 = None
    for scene_name, alpha in SCENES:
        print(f"SCENE: {scene_name}")
        print(f"{'noise':>8} {'model':<6} {'R2':>8} {'MAE':>8} "
              f"{'imp mean':>9} {'imp sd':>8} {'bare mean':>10}")
        print("-" * 62)
        for noise in NOISE_SWEEP:
            r = np.random.default_rng(SEED)
            X, A = simulate(N_PIXELS, noise, r, alpha)
            y = A[:, IMPERVIOUS_IDX].sum(axis=1)
            bare = A[:, BARE_IDX].sum(axis=1)
            for model, r2, mae in cbf.evaluate(X, y, r):
                print(f"{noise:>8.3f} {model:<6} {r2:>8.3f} {mae:>8.4f} "
                      f"{y.mean():>9.3f} {y.std():>8.3f} {bare.mean():>10.3f}")
                if (noise == NOISE_PRIMARY
                        and model == base.PRIMARY_MODEL
                        and scene_name.endswith("(PRIMARY)")):
                    primary_r2 = r2
            print("-" * 62)
        print()

    print("=" * 70)
    print(f"PRE-REGISTERED VERDICT (realistic scene, noise={NOISE_PRIMARY}, "
          f"{base.PRIMARY_MODEL})")
    print("=" * 70)
    print(f"  impervious-vs-bare ceiling R2 = {primary_r2:.3f}")
    print(f"  built/paved ceiling for comparison = 0.490")
    print(f"  ==> {verdict(primary_r2)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
