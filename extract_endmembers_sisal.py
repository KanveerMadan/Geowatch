"""
Minimum-volume simplex extraction (SISAL / MVSA) for the `built` endmember.

Why this family, for the record
-------------------------------
VCA and N-FINDR failed exactly as pre-registered: 0 of 44 vertices across two
AOIs, two algorithms and p=5/6 were small-structure fabric, while fabric
pixels made up 9.98% of Khayelitsha's uniform sample. The mechanism was
confirmed rather than merely suspected -- fabric pixels sit INTERIOR to the
spectral simplex and are never extreme, so any algorithm that assumes the
endmembers are present as extreme pixels cannot recover them.

Minimum-volume methods do not make that assumption. Instead of picking extreme
observed pixels, they fit the smallest simplex that ENCLOSES the observed
cloud. A class that is always mixed can therefore still be recovered as a
vertex of that simplex even though no single pixel is a pure sample of it.
That is the correct tool for the demonstrated mechanism -- not a fallback
reached for because the first attempt failed.

Formulation
-----------
Data reduced to an affine set: y_i = [1; U^T (x_i - mu)] in R^p, U the leading
(p-1) singular vectors. Seek Q (p x p) maximising |det Q| subject to
Q y_i >= 0 (non-negative abundances). Minimise

    f(Q) = -log|det Q| + LAMBDA * sum_i sum_k hinge( -(Q y_i)_k )

Endmembers are the columns of Q^-1, mapped back through U and mu. Initialised
from VCA, which is standard practice for SISAL.

PRE-REGISTERED, fixed before the first run
------------------------------------------
Sample / bands / p:
    Identical seed-42 20,000-pixel uniform sample, identical 6-band spectral
    matrix, vector bands carried for labelling only and never passed to the
    extraction. p=5 primary, p=6 sensitivity. p=7 is NOT re-run: 6 bands span
    at most 6 linearly independent endmembers, already established.

(1) "Recovered small-structure fabric":
    spectral angle from the extracted vertex to that AOI's small-fabric
    reference -- the mean of uniformly-sampled pixels satisfying
    built_cov >= 0.50 AND no footprint >= 100 m^2. Recomputed in-script from
    the same sample. Thresholds NEAR_DEG / FAR_DEG, the same angular scale
    used throughout this investigation.

(2) PASS/FAIL:
    PASS  = at least one of the p vertices is within FAR_DEG of the
            small-fabric reference AND is ANCHORED (see 3).
    FAIL  = none.
    A hit within NEAR_DEG is reported additionally as a STRONG pass.
    Both conditions are required: angle alone would be a hollow win, since a
    vertex can satisfy it while corresponding to no real surface.

(3) Anchoring, because minimum-volume vertices are NOT data points and may lie
    outside the data's convex hull (that is the mechanism, not a defect):
        support = sampled pixels within FAR_DEG of the vertex
        nearest = angle to the closest sampled pixel
    ANCHORED           support >= MIN_SUPPORT
    PURE EXTRAPOLATION support < MIN_SUPPORT AND nearest > FAR_DEG
    MIN_SUPPORT = 100 matches the VCA check (~2x endmember B's largest n,
    0.5% of the sample). The pre-committed verdict uses the strict
    anchored-required rule. The lenient angle-only reading is ALSO reported,
    because for a genuinely always-mixed class a correct vertex could
    legitimately carry low support -- that tension is real and is surfaced
    rather than hidden behind a single number.

(4) Reflectance validity bounds -- CHECKED POST-HOC, NOT ENFORCED IN-ALGORITHM.
    The minimum-volume objective is driven by the abundance non-negativity
    constraint, which is already present and implicitly restrains vertices: a
    vertex far outside the data inflates simplex volume, which the objective
    penalises. N-FINDR reached ||v||=1.205 because it SELECTS PIXELS under no
    constraint at all -- a different failure mode. Imposing a hard reflectance
    bound would change the problem so that it is no longer minimum-volume and
    risks non-convergence. Any band outside [0,1] is therefore reported and
    flagged NON-PHYSICAL rather than silently clipped; a violation is a
    finding, not something to hide.

LAMBDA is pre-committed at LAMBDA_PRIMARY, with LAMBDA_SENSITIVITY reported to
show whether the verdict is robust to that choice.

Usage:
    python extract_endmembers_sisal.py
    python extract_endmembers_sisal.py --aoi khayelitsha
"""

import argparse

import numpy as np
from scipy.optimize import minimize

import diagnose_open_buildings_aoi as diag
import diagnose_pure_pixels as pure_diag
import diagnose_pure_pixels_paved as paved_diag
import ee
import extract_endmembers_vca as vca_mod
import test_endmember_sensitivity as sens
from ingestion.sentinel2 import get_sentinel2_median_composite

# --- pre-registered; do not edit after seeing results --------------------
P_PRIMARY = 5
P_SENSITIVITY = [6]

NEAR_DEG = 2.87
FAR_DEG = 5.74
MIN_SUPPORT = 100

# DEVIATION FROM PRE-REGISTRATION, recorded: lambda was pre-committed at 10.0.
# That value is wrong for THIS objective's normalisation (mean softplus over
# all abundance entries) rather than SISAL's tau convention, and the solver
# failed its synthetic self-test at 10.0 -- recovering known endmembers only to
# within 35.8 deg. Lambda was recalibrated against SYNTHETIC GROUND TRUTH ONLY,
# before any real-data result was inspected: the sweep 1..1e6 recovers known
# endmembers to 1.22 deg at 1e4. This is solver calibration, not outcome
# fitting; every other pre-registered item (pass/fail rule, angular
# thresholds, support minimum, reflectance policy) is unchanged.
LAMBDA_PRIMARY = 1e4
LAMBDA_SENSITIVITY = [1e3, 1e5]

REFLECTANCE_MIN = 0.0
REFLECTANCE_MAX = 1.0
# -------------------------------------------------------------------------


def affine_reduce(X, p):
    """X: (N, L) -> homogeneous reduced coords Y: (p, N), plus mu, U."""
    mu = X.mean(axis=0)
    Xc = X - mu
    U = np.linalg.svd(Xc.T @ Xc / len(X))[0][:, :p - 1]   # (L, p-1)
    Z = (Xc @ U).T                                        # (p-1, N)
    Y = np.vstack([np.ones((1, Z.shape[1])), Z])          # (p, N)
    return Y, mu, U


def _sisal_reduced(Y, p, lam, V0, maxiter=500):
    """Minimum-volume simplex in reduced homogeneous coords.

    Parameterised by the vertex coordinates V ((p-1) x p) directly, with M's
    homogeneous first row PINNED to ones. Optimising Q = M^-1 freely instead
    (the obvious formulation) has a scale degeneracy: nothing forces M's first
    row to stay at 1, the affine structure collapses, and de-homogenising
    divides by a near-zero leading coordinate. Pinning the row removes that
    degeneracy and makes the vertices the parameters.

        minimise   log|det M|            (simplex volume)
        penalty  + lam * mean hinge(-(M^-1 Y))   (data outside the simplex)
    """
    N = Y.shape[1]

    def build(v):
        V = v.reshape(p - 1, p)
        return np.vstack([np.ones((1, p)), V])

    # Smooth (softplus) rather than hinge: the objective is minimised with
    # numerical gradients, and a hinge's kink makes those unreliable exactly
    # where the constraint binds.
    eps = 1e-3

    def softplus(x):
        # eps*log(1+exp(x/eps)), evaluated stably
        z = x / eps
        return eps * np.logaddexp(0.0, z)

    def fun(v):
        M = build(v)
        sign, logdet = np.linalg.slogdet(M)
        if sign == 0 or not np.isfinite(logdet):
            return 1e12
        try:
            S = np.linalg.solve(M, Y)
        except np.linalg.LinAlgError:
            return 1e12
        pen = softplus(-S).mean()
        return logdet + lam * pen

    res = minimize(fun, V0.ravel(), method="L-BFGS-B",
                   options={"maxiter": maxiter})
    return build(res.x), res


def feasible_init(Y, idx, tol=1e-6):
    """A starting simplex that CONTAINS the data.

    Minimum-volume fitting shrinks a containing simplex onto the cloud. VCA
    vertices are data points, so a simplex built on them starts with much of
    the data OUTSIDE it -- the optimiser then begins deep in the penalty
    region, which is the wrong regime and was one of two reasons the first
    implementation failed its self-test. Expand the VCA simplex about the data
    centroid until (near-)all abundances are non-negative.
    """
    V = Y[1:, idx]
    c = Y[1:].mean(axis=1, keepdims=True)
    p = Y.shape[0]
    for gamma in (1.0, 1.25, 1.5, 2.0, 3.0, 5.0, 8.0, 12.0):
        Vg = c + gamma * (V - c)
        M = np.vstack([np.ones((1, p)), Vg])
        try:
            S = np.linalg.solve(M, Y)
        except np.linalg.LinAlgError:
            continue
        if S.min() > -tol:
            return Vg, gamma
    return c + 12.0 * (V - c), 12.0


def sisal(X, p, lam, init_idx, seed=42):
    """Minimum-volume simplex. Returns endmembers (p, L) in reflectance space."""
    Y, mu, U = affine_reduce(X, p)

    # Initialise from VCA vertices, expanded to a containing simplex.
    V0, gamma = feasible_init(Y, init_idx)
    M, res = _sisal_reduced(Y, p, lam, V0)
    res.init_gamma = gamma

    # Back to reflectance space: rows 1.. are the reduced coords already,
    # since the homogeneous row is pinned to 1.
    ems = [mu + U @ M[1:, k] for k in range(p)]
    return np.array(ems), res


def selftest(seed=0, n=5000, verbose=True):
    """Validate the solver on synthetic data with NO pure pixels.

    Four known endmembers, abundances drawn so that max abundance stays below
    a cap -- i.e. every sample is genuinely mixed, the exact regime where
    VCA/N-FINDR fail and minimum-volume is supposed to succeed. If the solver
    cannot recover known endmembers here, any verdict it produces on real data
    is meaningless.
    """
    rng = np.random.default_rng(seed)
    true_em = np.array([
        [0.18, 0.21, 0.23, 0.27, 0.31, 0.30],   # bright roof
        [0.11, 0.13, 0.15, 0.18, 0.22, 0.21],   # dark fabric
        [0.03, 0.06, 0.05, 0.24, 0.18, 0.12],   # vegetation
        [0.14, 0.17, 0.13, 0.07, 0.02, 0.02],   # water
    ])
    p = len(true_em)

    A = rng.dirichlet(np.ones(p) * 3.0, size=n)   # concentrated -> mixed
    cap = 0.80
    A = A[A.max(axis=1) < cap]                    # remove any near-pure sample
    X = A @ true_em
    X += rng.normal(scale=0.002, size=X.shape)    # mild sensor noise

    init = vca_mod.vca(X.T, p)
    ems, res = sisal(X, p, LAMBDA_PRIMARY, init)

    # Match recovered to true by best angle
    angs = []
    for t in true_em:
        angs.append(min(angle_between(t, e) for e in ems))

    ok = max(angs) <= FAR_DEG
    if verbose:
        print(f"  SELF-TEST: {len(X)} synthetic mixtures, max abundance "
              f"< {cap} (no pure pixels)")
        print(f"    per-endmember recovery angle: "
              f"{[round(a, 2) for a in angs]} deg")
        print(f"    worst {max(angs):.2f} deg vs {FAR_DEG} deg threshold -> "
              f"{'SOLVER OK' if ok else 'SOLVER FAILS -- results not usable'}")
    return ok, angs


def angles_to(v, X):
    v = np.asarray(v, float)
    nv = np.linalg.norm(v)
    nx = np.linalg.norm(X, axis=1)
    cos = (X @ v) / (nx * nv + 1e-12)
    return np.degrees(np.arccos(np.clip(cos, -1, 1)))


def angle_between(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    cos = (a @ b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12)
    return float(np.degrees(np.arccos(np.clip(cos, -1, 1))))


def evaluate(ems, spec, ref, ref_n, tag):
    print(f"\n  --- {tag} ---")
    passed_strict = False
    passed_lenient = False
    strong = False

    for k, v in enumerate(ems):
        ang_ref = angle_between(v, ref)
        d = angles_to(v, spec)
        support = int((d <= FAR_DEG).sum())
        nearest = float(d.min())
        anchored = support >= MIN_SUPPORT
        extrapolation = (not anchored) and (nearest > FAR_DEG)

        lo, hi = float(v.min()), float(v.max())
        nonphys = (lo < REFLECTANCE_MIN) or (hi > REFLECTANCE_MAX)

        near_ref = ang_ref <= FAR_DEG
        if near_ref:
            passed_lenient = True
            if anchored:
                passed_strict = True
                if ang_ref <= NEAR_DEG:
                    strong = True

        marks = []
        if anchored:
            marks.append("ANCHORED")
        else:
            marks.append("unanchored")
        if extrapolation:
            marks.append("*** PURE EXTRAPOLATION ***")
        if nonphys:
            marks.append(f"*** NON-PHYSICAL (range {lo:.3f}..{hi:.3f}) ***")
        if near_ref:
            marks.append("<= FAR of small-fabric ref")

        print(f"    v{k}: {[round(float(x), 4) for x in v]}")
        print(f"        angle to small-fabric ref : {ang_ref:.2f} deg")
        print(f"        support {support} @{FAR_DEG}deg "
              f"({100*support/len(spec):.2f}%), nearest pixel {nearest:.2f} deg")
        print(f"        {'  |  '.join(marks)}")

    return passed_strict, passed_lenient, strong


def run_aoi(label, aoi, cache_key):
    print(f"\n{'=' * 78}")
    print(f"[{label}]")
    print(f"{'=' * 78}")

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
    if n_paved == 0:
        paved_fc = None

    img = vca_mod.build_sample_image(composite, aoi, proj, confident, paved_fc)
    print(f"  sampling {vca_mod.N_SAMPLE} pixels (seed {vca_mod.SEED})...",
          flush=True)
    spec, lab = vca_mod.sample_pixels(img, aoi, proj_info)
    print(f"  got {len(spec)} valid pixels x {spec.shape[1]} bands "
          f"(label bands excluded from extraction)")

    small_mask = ((lab["built_cov"] >= vca_mod.SMALL_FABRIC_MIN_COVERAGE)
                  & (lab["big_cov"] == 0))
    ref_n = int(small_mask.sum())
    if ref_n == 0:
        print("  no small-fabric pixels in sample -- cannot evaluate")
        return None
    ref = spec[small_mask].mean(axis=0)
    print(f"  small-fabric reference (n={ref_n}): "
          f"{[round(float(x), 4) for x in ref]}")
    if ref_n < MIN_SUPPORT:
        print(f"    *** reference itself is weakly supported (n={ref_n} < "
              f"{MIN_SUPPORT}) -- treat this AOI's verdict with caution")

    results = {}
    n_bands = spec.shape[1]
    for p in [P_PRIMARY] + P_SENSITIVITY:
        tag = "PRIMARY" if p == P_PRIMARY else "sensitivity"
        print(f"\n  ===== p={p} ({tag}) =====")
        if p > n_bands:
            print(f"    SKIPPED -- exceeds {n_bands}-band ceiling")
            continue

        init_idx = vca_mod.vca(spec.T, p)
        for lam in [LAMBDA_PRIMARY] + LAMBDA_SENSITIVITY:
            ems, res = sisal(spec, p, lam, init_idx)
            ltag = "PRIMARY" if lam == LAMBDA_PRIMARY else "sens"
            strict, lenient, strong = evaluate(
                ems, spec, ref, ref_n,
                f"SISAL p={p} lambda={lam} ({ltag})  "
                f"[converged={res.success}, {res.nit} iters]")
            results[(p, lam)] = (strict, lenient, strong)

    print(f"\n  PRE-REGISTERED VERDICT (p={P_PRIMARY}, "
          f"lambda={LAMBDA_PRIMARY}):")
    key = (P_PRIMARY, LAMBDA_PRIMARY)
    if key in results:
        strict, lenient, strong = results[key]
        print(f"    strict (angle <= {FAR_DEG} AND anchored) : "
              f"{'PASS' if strict else 'FAIL'}"
              + ("  [STRONG, <= %.2f deg]" % NEAR_DEG if strong else ""))
        print(f"    lenient (angle only)                 : "
              f"{'pass' if lenient else 'fail'}")
    return {"label": label, "results": results, "ref_n": ref_n}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", choices=["khayelitsha", "formal"])
    args = parser.parse_args()

    print(f"PRE-REGISTERED: p={P_PRIMARY} primary, "
          f"PASS = a vertex within {FAR_DEG}deg of small-fabric ref AND "
          f"support >= {MIN_SUPPORT}; reflectance checked post-hoc, not clipped")
    print(f"lambda={LAMBDA_PRIMARY:g} (recalibrated from the pre-committed 10.0 "
          f"on SYNTHETIC ground truth only -- see module docstring)")
    print("\nSolver validation before any real-data result is read:")
    ok, angs = selftest()
    if not ok:
        print("  ABORT -- solver does not recover known endmembers; "
              "no real-data verdict would be meaningful.")
        return

    cache_keys = {
        "Khayelitsha (capetown run)": "khayelitsha",
        "Cape Town formal suburbs": "ct_formal",
    }
    wanted = ({"khayelitsha": "Khayelitsha (capetown run)",
               "formal": "Cape Town formal suburbs"}.get(args.aoi)
              if args.aoi else None)

    rows = []
    for lbl, aoi in pure_diag.build_aois():
        if lbl not in cache_keys or (wanted and lbl != wanted):
            continue
        r = run_aoi(lbl, aoi, cache_keys[lbl])
        if r:
            rows.append(r)

    if len(rows) > 1:
        print("\n" + "=" * 88)
        print(f"SISAL VERDICT SUMMARY (p={P_PRIMARY}, lambda={LAMBDA_PRIMARY})")
        print("=" * 88)
        for r in rows:
            strict, lenient, strong = r["results"].get(
                (P_PRIMARY, LAMBDA_PRIMARY), (False, False, False))
            print(f"  {r['label']:<30} strict={'PASS' if strict else 'FAIL'}  "
                  f"lenient={'pass' if lenient else 'fail'}  "
                  f"(ref n={r['ref_n']})")
        print("=" * 88)


if __name__ == "__main__":
    main()
