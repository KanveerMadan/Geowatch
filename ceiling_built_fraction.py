"""
Information ceiling: what is the BEST POSSIBLE R^2 for built fraction, given
the measured spectral geometry of these AOIs?

Why this is the decisive experiment
------------------------------------
Five methods have failed. A sixth hypothesis (scale mismatch) was falsified by
its own self-test before touching real data: blurring SWIR to 20 m, applying
an MTF blur and a one-cell label jitter moved a synthetic R^2 only from ~1.0
to 0.939, so those mechanisms cannot explain a real ceiling of ~0.35.

Measuring the real endmembers pairwise shows what can:

                   built_in built_fa    paved     bare      veg    water
    built_inst(A)      0.00     3.35     4.70     3.86    26.19    42.76
    built_fabric(B)    3.35     0.00     1.70     3.65    24.51    45.90
    paved              4.70     1.70     0.00     3.45    23.15    46.86
    bare               3.86     3.65     3.45     0.00    23.38    44.04
    veg               26.19    24.51    23.15    23.38     0.00    60.66
    water             42.76    45.90    46.86    44.04    60.66     0.00

Every hard surface -- institutional roof, informal roof, asphalt, bare soil --
lies inside a single cone under 5 deg wide, while vegetation sits 23-26 deg
away and water 43-47 deg. Sentinel-2 L2A BOA uncertainty of ~0.005 reflectance
is ~0.7 deg at this magnitude. So the entire built/paved/bare discrimination
lives at roughly 2-7x the noise floor, whereas built-vs-vegetation lives at
~35x. That is a property of the surfaces and the sensor, not of any algorithm.

This script converts that observation into a NUMBER: simulate pixels under
conditions strictly BETTER than reality, and measure the best R^2 obtainable.

Conditions deliberately made optimistic, so the result is an upper bound:
  * labels exact -- no footprint/grid co-registration error
  * mixing exactly linear -- no nonlinear/multiple-scattering effects
  * endmembers FIXED -- no within-class spectral variability, which is
    substantial in reality and can only lower the ceiling
  * no shadow term, no atmospheric residual, no BRDF
  * random train/test split -- the cross-city transfer problem is removed
  * the model may use all six bands with no regularisation penalty for it
Reality is worse than every one of these. Whatever this returns is a bound
that no method operating on this data can exceed.

PRE-REGISTERED, fixed before any result existed
-------------------------------------------------
QUESTION: is the project's success bar (leave-one-AOI-out R^2 >= 0.50 AND
MAE <= 0.15) reachable IN PRINCIPLE on 6-band 10 m data with these surfaces?

DECISION RULE:
  ceiling R^2 <  CEILING_UNREACHABLE (0.50) at realistic noise
      -> the bar is UNREACHABLE IN PRINCIPLE. No method can clear it, the
         five observed failures are explained, and the correct move is to
         re-scope rather than to keep searching.
  ceiling R^2 >= CEILING_HEADROOM (0.70)
      -> ample headroom exists; the failures were methodological after all
         and the search should continue.
  between -> INDETERMINATE; the bar is marginal rather than impossible.

NOISE: primary NOISE_PRIMARY = 0.005 absolute reflectance, the documented
    order of Sentinel-2 L2A BOA uncertainty. Swept over NOISE_SWEEP so the
    conclusion's sensitivity to that single choice is visible rather than
    assumed. A ceiling that only fails at implausibly high noise would be a
    weak result and must be shown as such.

BLIND-SPOT AUDIT, done before running -- "what wrong answer would still pass?"
  * Understating noise inflates the ceiling. GUARD: swept, not asserted.
  * An unrealistic target distribution could inflate or deflate R^2.
    GUARD: mixture proportions are drawn so the built-fraction distribution
    matches the MEASURED real one (mean ~0.19-0.30, sd ~0.26-0.34), and the
    realised mean/sd are printed for comparison.
  * Using only well-separated classes would inflate it. GUARD: the real
    six-endmember set is used, including the confusable bare/paved.
  * A CONTROL is included: the same simulation targeting VEGETATION fraction
    instead of built. Vegetation is 23-26 deg from everything else, so if the
    pipeline cannot recover vegetation at high R^2, the simulation itself is
    broken and the built result means nothing. This is the self-test.
  * Scale-invariance blind spot (the SISAL failure): R^2 and MAE are in the
    target's own units, so a magnitude error cannot pass unnoticed.

Usage:
    python ceiling_built_fraction.py
"""

import argparse

import numpy as np

import regress_built_fraction as base

# --- pre-registered; not edited after seeing results ---------------------
CEILING_UNREACHABLE = 0.50     # below this -> bar unreachable in principle
CEILING_HEADROOM = 0.70        # above this -> failures were methodological

NOISE_PRIMARY = 0.005          # absolute reflectance, S2 L2A BOA order
NOISE_SWEEP = [0.0, 0.001, 0.002, 0.005, 0.010, 0.020]

N_PIXELS = 40000
SEED = 42

CONTROL_MIN_R2 = 0.90          # vegetation control must clear this
# -------------------------------------------------------------------------

# Measured Khayelitsha endmembers (test_endmember_sensitivity.py, real data)
EM = {
    "built_fabric": [0.1108, 0.1296, 0.1479, 0.1791, 0.2216, 0.2082],
    "built_inst":   [0.1847, 0.2063, 0.2235, 0.2625, 0.3047, 0.2966],
    "paved":        [0.1068, 0.1299, 0.1517, 0.1905, 0.2349, 0.2103],
    "bare":         [0.1523, 0.1891, 0.2199, 0.2710, 0.3024, 0.2652],
    "veg":          [0.0318, 0.0575, 0.0546, 0.2373, 0.1846, 0.1224],
    "water":        [0.1350, 0.1650, 0.1268, 0.0655, 0.0230, 0.0159],
}
ORDER = ["built_fabric", "built_inst", "paved", "bare", "veg", "water"]
BUILT_IDX = [0, 1]          # built = fabric + institutional roofing
VEG_IDX = [4]


def simulate(n, noise, rng, alpha=None):
    """Convex mixtures of the real endmembers, plus Gaussian sensor noise."""
    M = np.array([EM[k] for k in ORDER])
    if alpha is None:
        # Tuned only to reproduce the MEASURED built-fraction distribution
        # (mean ~0.19-0.30, sd ~0.26-0.34); not tuned against any outcome.
        alpha = np.array([0.45, 0.12, 0.35, 0.7, 0.7, 0.08])
    A = rng.dirichlet(alpha, size=n)
    X = A @ M
    if noise > 0:
        X = X + rng.normal(scale=noise, size=X.shape)
    return X, A


def evaluate(X, y, rng):
    idx = rng.permutation(len(X))
    h = len(idx) // 2
    tr, te = idx[:h], idx[h:]
    Xtr, Xte = base.normalize("raw", [X[tr]], X[te])
    for model in ("ridge", "gbt"):
        yhat = base.fit_predict(model, Xtr, y[tr], Xte)
        r2, mae = base.score(y[te], yhat)
        yield model, r2, mae


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()

    print("PRE-REGISTERED DECISION RULE:")
    print(f"  ceiling R2 <  {CEILING_UNREACHABLE} at realistic noise "
          f"-> bar UNREACHABLE IN PRINCIPLE")
    print(f"  ceiling R2 >= {CEILING_HEADROOM} -> headroom exists, "
          f"failures were methodological")
    print(f"  between -> INDETERMINATE")
    print(f"  primary noise = {NOISE_PRIMARY} reflectance; swept over "
          f"{NOISE_SWEEP}")
    print("  Simulation is OPTIMISTIC by construction: exact labels, exactly "
          "linear mixing,\n  fixed endmembers, no shadow, no transfer "
          "problem. Reality is worse on every axis.")

    rng = np.random.default_rng(SEED)

    # ---- CONTROL / SELF-TEST: vegetation is 23-26 deg from everything -----
    print("\nCONTROL (self-test): same simulation, target = VEGETATION "
          "fraction")
    print("  Vegetation is 23-26 deg from all other classes. If this does not "
          "recover,\n  the simulation is broken and the built result is "
          "meaningless.")
    Xc, Ac = simulate(N_PIXELS, NOISE_PRIMARY, rng)
    yv = Ac[:, VEG_IDX].sum(axis=1)
    ctrl_ok = False
    for model, r2, mae in evaluate(Xc, yv, rng):
        print(f"    {model:<6} R2={r2:>6.3f} MAE={mae:.4f}")
        if model == base.PRIMARY_MODEL:
            ctrl_ok = r2 >= CONTROL_MIN_R2
    print(f"  -> {'OK' if ctrl_ok else 'FAILS'} "
          f"(bar R2 >= {CONTROL_MIN_R2})")
    if not ctrl_ok:
        print("  ABORT -- simulation cannot recover an easy, well-separated "
              "class.")
        return

    # ---- the ceiling ------------------------------------------------------
    print("\nCEILING for BUILT fraction (built_fabric + built_inst):")
    print(f"{'noise':>8} {'model':<6} {'R2':>8} {'MAE':>8} "
          f"{'y mean':>8} {'y sd':>7}")
    print("-" * 54)

    primary = {}
    for noise in NOISE_SWEEP:
        r = np.random.default_rng(SEED)
        X, A = simulate(N_PIXELS, noise, r)
        y = A[:, BUILT_IDX].sum(axis=1)
        for model, r2, mae in evaluate(X, y, r):
            print(f"{noise:>8.3f} {model:<6} {r2:>8.3f} {mae:>8.4f} "
                  f"{y.mean():>8.3f} {y.std():>7.3f}")
            if noise == NOISE_PRIMARY and model == base.PRIMARY_MODEL:
                primary = dict(r2=r2, mae=mae, mean=y.mean(), sd=y.std())
        print("-" * 54)

    r2 = primary["r2"]
    if r2 < CEILING_UNREACHABLE:
        v = "BAR UNREACHABLE IN PRINCIPLE"
    elif r2 >= CEILING_HEADROOM:
        v = "HEADROOM EXISTS -- failures were methodological"
    else:
        v = "INDETERMINATE -- bar is marginal, not impossible"

    print(f"\nPRIMARY (noise={NOISE_PRIMARY}, {base.PRIMARY_MODEL}): "
          f"R2={primary['r2']:.3f} MAE={primary['mae']:.4f}")
    print(f"  realised built distribution: mean={primary['mean']:.3f} "
          f"sd={primary['sd']:.3f}  (measured real: mean 0.19-0.30, "
          f"sd 0.26-0.34)")
    print(f"  project bar: R2 >= {base.WORKS_R2} AND MAE <= {base.WORKS_MAE}")
    print(f"  ==> {v}")

    # ---- what IS recoverable, for the re-scope decision --------------------
    print("\nFor comparison, under the SAME optimistic simulation:")
    r = np.random.default_rng(SEED)
    X, A = simulate(N_PIXELS, NOISE_PRIMARY, r)
    targets = {
        "built (fabric+inst)": A[:, BUILT_IDX].sum(axis=1),
        "impervious (built+paved)": A[:, [0, 1, 2]].sum(axis=1),
        "impervious+bare (all hard)": A[:, [0, 1, 2, 3]].sum(axis=1),
        "vegetation": A[:, 4],
        "water": A[:, 5],
    }
    print(f"{'target':<28} {'R2':>8} {'MAE':>8}")
    print("-" * 46)
    for name, y in targets.items():
        for model, rr2, mae in evaluate(X, y, r):
            if model == base.PRIMARY_MODEL:
                print(f"{name:<28} {rr2:>8.3f} {mae:>8.4f}")


if __name__ == "__main__":
    main()
