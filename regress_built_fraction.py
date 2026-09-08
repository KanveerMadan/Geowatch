"""
Direct regression of built fraction from reflectance, using a geometric label.

Why this exists
---------------
Three independent endmember-estimation families have now failed to recover a
usable small-structure-fabric endmember at 10m / 6 bands:

  vector-mask extraction   1-5% pixel purity, adverse selection 4.66-22.45x
  VCA / N-FINDR            0 of 44 vertices were small-structure fabric
  SISAL (minimum-volume)   hollow pass; 56% non-physical, 52% pure
                           extrapolation across 66 vertices

They converge on one mechanism: this class is genuinely, always interior-mixed
at this resolution. That is a property of the data, not a method-selection
problem, so the pivot is to stop needing an endmember at all.

This script regresses six-band reflectance directly onto a GEOMETRIC label --
the footprint coverage fraction. No spectral endmember, no linear mixing
model. Geometry is the one input in this investigation that has not failed.

PRE-REGISTERED, fixed before any model was fitted
--------------------------------------------------
(1) TARGET. built_fraction_label = the coverage_fraction quantity already
    computed by sens.coverage_fraction() -- the un-thresholded core of
    diagnose_pure_pixels.pure_pixel_images() -- taken as its RAW CONTINUOUS
    value in [0,1]. NOT gt(0), NOT gte(PURE_FRACTION_MIN). This is a
    repurposing of existing geometry, not new geometry: same real S2 grid per
    AOI, same confidence >= 0.7 footprint filter, same 1m sub-cell coverage
    computation (so label granularity is 0.01).

(2) SPLIT. Leave-one-AOI-out across Dharavi, Khayelitsha and CT-formal: train
    on two, validate on the held-out third, rotate. Chosen because A.13
    (03_EVIDENCE.md:310) established that ambiguity composition is
    AOI-dependent and that conclusions from one AOI do not transfer -- so
    cross-AOI transfer is the thing that must be measured, not assumed.
    A within-AOI random split is ALSO reported, as a reference point only,
    to expose the gap between "works inside a city" and "transfers between
    cities". The verdict rests on the leave-one-AOI-out folds.

(3) MODEL. Ridge regression is PRIMARY. A small gradient-boosted model
    (max_depth=3, 200 iterations, no tuning) is secondary. Justification: for
    the generalisation question there are effectively three samples -- three
    AOIs -- against six features. Anything deep could not be validated at that
    n, and would be fitted to two cities. Ridge has one hyperparameter, chosen
    by cross-validation WITHIN THE TRAINING AOIs ONLY, never touching the
    held-out AOI. If a linear map from reflectance to coverage transfers, that
    is a strong and simple result; the boosted model is carried only to show
    whether nonlinearity buys anything. Primary is declared here so it cannot
    be retrofitted to whichever scores better.
    Predictions are clipped to [0,1], which follows from the target's
    definition rather than being a tuning choice.

(4) SUCCESS CRITERION, three-way, on the MEAN across the three held-out folds:
      WORKS            R^2 >= 0.50 AND MAE <= 0.15, and no individual fold in
                       the "does not transfer" zone
      DOES NOT TRANSFER  R^2 < 0.20 OR MAE > 0.25
      INDETERMINATE    anything between
    Anchors are this investigation's own numbers, not conventions. The
    endmember approach produced mean |delta impervious| of 0.2674 (Dharavi),
    0.1487 (Khayelitsha) and 0.0712 (CT formal) between two defensible
    endmember choices. MAE <= 0.15 therefore means the regression is more
    stable than the thing it replaces in two of three AOIs; MAE > 0.25 means
    it is no better than the worst of it. R^2 >= 0.50 means explaining half
    the variance of a quantity we have just shown to be spectrally
    near-degenerate; R^2 < 0.20 means essentially no cross-city signal.
    Reported on ALL pixels (the operational case) and, separately, on
    built_cov > 0 pixels only (the hard case).

(5) SYNTHETIC SELF-TEST, before real data is trusted, mirroring the SISAL one.
    (a) basic: four endmembers, abundances drawn so no sample is near-pure
        (max abundance < 0.80), target = the built abundance. Recovery means
        R^2 >= 0.90 AND MAE <= 0.05 on held-out synthetic data. With a known
        exact generative model and mild noise, a competent regressor must
        clear that; failing it would mean a pipeline bug and would make any
        real-data number meaningless.
    (b) cross-domain: two synthetic "cities", the second with a different
        gain and offset applied to reflectance, simulating A.13's
        different-acquisition axis. Train on one, test on the other. Same
        0.90 / 0.05 bar. This is the direct test of whether (6) works.

(6) CROSS-AOI NORMALISATION. Primary is PER-AOI STANDARDISATION: each AOI's
    bands are z-scored using that AOI's OWN feature statistics. This targets
    A.13's axis directly (per-composite offset and gain differences from
    different acquisition dates and seasons) and is legitimate at inference
    time on an unseen city, because it uses only that city's imagery -- never
    its labels. Two comparisons are reported: raw (a single scaler fitted on
    the training AOIs only) and per-pixel brightness normalisation.

Usage:
    python regress_built_fraction.py
"""

import argparse

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score

import diagnose_open_buildings_aoi as diag
import diagnose_pure_pixels as pure_diag
import diagnose_pure_pixels_paved as paved_diag
import ee
import extract_endmembers_vca as vca_mod
import test_endmember_sensitivity as sens
from ingestion.sentinel2 import get_sentinel2_median_composite

# --- pre-registered; not edited after seeing results ---------------------
WORKS_R2, WORKS_MAE = 0.50, 0.15
FAIL_R2, FAIL_MAE = 0.20, 0.25

SELFTEST_R2, SELFTEST_MAE = 0.90, 0.05

RIDGE_ALPHAS = np.logspace(-3, 3, 13)
GBT_KW = dict(max_depth=3, max_iter=200, learning_rate=0.1,
              early_stopping=False, random_state=0)

PRIMARY_MODEL = "ridge"
PRIMARY_NORM = "per_aoi"
# -------------------------------------------------------------------------

AOI_KEYS = {
    "Dharavi": "dharavi",
    "Khayelitsha (capetown run)": "khayelitsha",
    "Cape Town formal suburbs": "ct_formal",
}


def verdict(r2, mae):
    if r2 < FAIL_R2 or mae > FAIL_MAE:
        return "DOES NOT TRANSFER"
    if r2 >= WORKS_R2 and mae <= WORKS_MAE:
        return "WORKS"
    return "INDETERMINATE"


# ---------------------------------------------------------------- models

def fit_predict(model_name, Xtr, ytr, Xte):
    if model_name == "ridge":
        m = RidgeCV(alphas=RIDGE_ALPHAS)      # CV inside training data only
    else:
        m = HistGradientBoostingRegressor(**GBT_KW)
    m.fit(Xtr, ytr)
    return np.clip(m.predict(Xte), 0.0, 1.0)


def normalize(norm, Xs_train, Xs_test):
    """Xs_train: list of per-AOI arrays; Xs_test: one array."""
    if norm == "per_aoi":
        # Each AOI standardised by its OWN statistics -- uses the held-out
        # AOI's features but never its labels, which is available in practice.
        def z(a):
            mu, sd = a.mean(0), a.std(0)
            sd[sd == 0] = 1.0
            return (a - mu) / sd
        return np.vstack([z(a) for a in Xs_train]), z(Xs_test)

    if norm == "brightness":
        def bn(a):
            n = np.linalg.norm(a, axis=1, keepdims=True)
            n[n == 0] = 1.0
            return a / n
        tr = np.vstack([bn(a) for a in Xs_train])
        te = bn(Xs_test)
        mu, sd = tr.mean(0), tr.std(0)
        sd[sd == 0] = 1.0
        return (tr - mu) / sd, (te - mu) / sd

    # raw: single scaler fitted on training AOIs only
    tr = np.vstack(Xs_train)
    mu, sd = tr.mean(0), tr.std(0)
    sd[sd == 0] = 1.0
    return (tr - mu) / sd, (Xs_test - mu) / sd


def score(y, yhat):
    return r2_score(y, yhat), mean_absolute_error(y, yhat)


# ------------------------------------------------------------ self-tests

def _synth(n, rng, gain=1.0, offset=0.0, cap=0.80):
    em = np.array([
        [0.18, 0.21, 0.23, 0.27, 0.31, 0.30],
        [0.11, 0.13, 0.15, 0.18, 0.22, 0.21],
        [0.03, 0.06, 0.05, 0.24, 0.18, 0.12],
        [0.14, 0.17, 0.13, 0.07, 0.02, 0.02],
    ])
    A = rng.dirichlet(np.ones(len(em)) * 3.0, size=n)
    A = A[A.max(axis=1) < cap]
    X = A @ em
    X = X * gain + offset
    X += rng.normal(scale=0.002, size=X.shape)
    y = A[:, 0] + A[:, 1]          # "built" = first two endmembers
    return X, y


def selftest_basic(verbose=True):
    rng = np.random.default_rng(0)
    X, y = _synth(8000, rng)
    k = len(X) // 2
    Xtr, ytr, Xte, yte = X[:k], y[:k], X[k:], y[k:]
    Xtr_n, Xte_n = normalize(PRIMARY_NORM, [Xtr], Xte)
    yhat = fit_predict(PRIMARY_MODEL, Xtr_n, ytr, Xte_n)
    r2, mae = score(yte, yhat)
    ok = (r2 >= SELFTEST_R2) and (mae <= SELFTEST_MAE)
    if verbose:
        print(f"  (a) basic: n={len(X)} always-mixed synthetic samples")
        print(f"      R2={r2:.3f} MAE={mae:.4f} vs bar R2>={SELFTEST_R2} "
              f"MAE<={SELFTEST_MAE} -> {'OK' if ok else 'FAILS'}")
    return ok


def selftest_crossdomain(verbose=True):
    rng = np.random.default_rng(1)
    Xa, ya = _synth(8000, rng)
    Xb, yb = _synth(8000, rng, gain=1.25, offset=0.02)   # different acquisition
    out = {}
    for norm in ("per_aoi", "raw"):
        Xtr_n, Xte_n = normalize(norm, [Xa], Xb)
        yhat = fit_predict(PRIMARY_MODEL, Xtr_n, ya, Xte_n)
        out[norm] = score(yb, yhat)
    ok = (out[PRIMARY_NORM][0] >= SELFTEST_R2) and (out[PRIMARY_NORM][1] <= SELFTEST_MAE)
    if verbose:
        print(f"  (b) cross-domain: train city A, test city B "
              f"(gain 1.25, offset +0.02)")
        for norm, (r2, mae) in out.items():
            print(f"      {norm:<9} R2={r2:.3f} MAE={mae:.4f}"
                  + ("   <- PRIMARY" if norm == PRIMARY_NORM else ""))
        print(f"      -> {'OK' if ok else 'FAILS'} "
              f"(bar R2>={SELFTEST_R2}, MAE<={SELFTEST_MAE})")
    return ok


# ----------------------------------------------------------------- data

def load_aoi(label, aoi, cache_key):
    proj, proj_info = pure_diag.s2_grid_for(aoi)
    composite = get_sentinel2_median_composite(
        aoi, sens.START_DATE, sens.END_DATE)["image"]

    confident = (ee.FeatureCollection(diag.BUILDINGS_ASSET)
                 .filterBounds(aoi)
                 .filter(ee.Filter.gte("confidence", diag.CONFIDENCE_THRESHOLD)))

    bounds = aoi.bounds().coordinates().getInfo()[0]
    lons = [c[0] for c in bounds]
    lats = [c[1] for c in bounds]
    elements, _ = paved_diag.overpass_paved(min(lons), min(lats),
                                            max(lons), max(lats), cache_key)
    paved_fc, n_paved = paved_diag.to_feature_collection(elements)

    img = vca_mod.build_sample_image(composite, aoi, proj, confident,
                                     paved_fc if n_paved else None)
    spec, lab = vca_mod.sample_pixels(img, aoi, proj_info)

    # (1) the target: raw continuous coverage fraction, NOT thresholded
    y = lab["built_cov"].astype(float)
    keep = np.isfinite(y) & np.isfinite(spec).all(axis=1)
    return spec[keep], np.clip(y[keep], 0.0, 1.0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    print(f"PRE-REGISTERED: target = raw continuous coverage_fraction; "
          f"leave-one-AOI-out; primary model={PRIMARY_MODEL}, "
          f"norm={PRIMARY_NORM}")
    print(f"  WORKS: R2>={WORKS_R2} AND MAE<={WORKS_MAE} (mean of folds, no "
          f"fold in fail zone) | DOES NOT TRANSFER: R2<{FAIL_R2} OR "
          f"MAE>{FAIL_MAE} | else INDETERMINATE")

    print("\nSELF-TESTS (before any real data is trusted):")
    ok_a = selftest_basic()
    ok_b = selftest_crossdomain()
    if not (ok_a and ok_b):
        print("  ABORT -- regression pipeline fails synthetic recovery; "
              "real numbers would be meaningless.")
        return

    data = {}
    for lbl, aoi in pure_diag.build_aois():
        print(f"\nloading {lbl} ...", flush=True)
        X, y = load_aoi(lbl, aoi, AOI_KEYS[lbl])
        data[lbl] = (X, y)
        print(f"  {len(X)} pixels | target mean={y.mean():.3f} "
              f"sd={y.std():.3f} | frac>0 = {(y > 0).mean():.3f}")

    labels = list(data)

    print("\n" + "=" * 96)
    print("LEAVE-ONE-AOI-OUT")
    print("=" * 96)
    print(f"{'held-out AOI':<28} {'norm':<11} {'model':<6} "
          f"{'R2':>7} {'MAE':>7} {'R2>0':>7} {'MAE>0':>7} {'baseMAE':>8}")
    print("-" * 96)

    fold_primary = {}
    for held in labels:
        Xs_tr = [data[l][0] for l in labels if l != held]
        ys_tr = np.concatenate([data[l][1] for l in labels if l != held])
        Xte, yte = data[held]

        for norm in ("per_aoi", "raw", "brightness"):
            Xtr_n, Xte_n = normalize(norm, Xs_tr, Xte)
            for model in ("ridge", "gbt"):
                yhat = fit_predict(model, Xtr_n, ys_tr, Xte_n)
                r2, mae = score(yte, yhat)

                pos = yte > 0
                r2p, maep = (score(yte[pos], yhat[pos])
                             if pos.sum() > 10 else (float("nan"),) * 2)
                base = mean_absolute_error(yte, np.full_like(yte, ys_tr.mean()))

                star = ("  <-" if (norm == PRIMARY_NORM
                                   and model == PRIMARY_MODEL) else "")
                print(f"{held:<28} {norm:<11} {model:<6} "
                      f"{r2:>7.3f} {mae:>7.4f} {r2p:>7.3f} {maep:>7.4f} "
                      f"{base:>8.4f}{star}")

                if norm == PRIMARY_NORM and model == PRIMARY_MODEL:
                    fold_primary[held] = (r2, mae)

        # within-AOI reference only, never the verdict
        rng = np.random.default_rng(0)
        idx = rng.permutation(len(Xte))
        h = len(idx) // 2
        a, b = idx[:h], idx[h:]
        Xa_n, Xb_n = normalize(PRIMARY_NORM, [Xte[a]], Xte[b])
        yhat = fit_predict(PRIMARY_MODEL, Xa_n, yte[a], Xb_n)
        r2w, maew = score(yte[b], yhat)
        print(f"{'  (within-AOI reference)':<28} {'per_aoi':<11} "
              f"{'ridge':<6} {r2w:>7.3f} {maew:>7.4f}")
        print("-" * 96)

    r2s = [fold_primary[l][0] for l in labels]
    maes = [fold_primary[l][1] for l in labels]
    mean_r2, mean_mae = float(np.mean(r2s)), float(np.mean(maes))
    per_fold = [verdict(r, m) for r, m in zip(r2s, maes)]
    overall = verdict(mean_r2, mean_mae)
    if overall == "WORKS" and "DOES NOT TRANSFER" in per_fold:
        overall = "INDETERMINATE"

    print("\n" + "=" * 96)
    print(f"PRE-REGISTERED VERDICT (primary = {PRIMARY_NORM} + {PRIMARY_MODEL})")
    print("=" * 96)
    for l, r, m, v in zip(labels, r2s, maes, per_fold):
        print(f"  held-out {l:<28} R2={r:>7.3f} MAE={m:.4f}  {v}")
    print(f"  MEAN across folds              R2={mean_r2:>7.3f} "
          f"MAE={mean_mae:.4f}")
    print(f"  ==> {overall}")
    print("=" * 96)


if __name__ == "__main__":
    main()
