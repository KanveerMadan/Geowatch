"""
Ceiling checks for the three rare fractions: solar, snow_ice,
mixed_water_vegetation.

Why this exists
---------------
Decision 11 (amended 2026-09-24) added three fractions to the taxonomy, each
with its own producer and validation case. Nobody has asked whether 10 m /
6-band Sentinel-2 can recover them at all. 06_UNMIXING_CEILING.md showed that
question has a computable answer: built/paved, which looked like a reasonable
class split, has a ceiling of 0.490 and is unidentifiable in principle. This
script asks the same question, by the same method, before anyone spends
labelling time on the three new classes.

Method -- the one in ceiling_built_fraction.py and ceiling_impervious_bare.py,
reused rather than reinvented:
  * Dirichlet mixtures of measured endmembers, exactly linear, plus Gaussian
    sensor noise; 40,000 pixels; seed 42; random 50/50 split.
  * Ridge (primary) and gradient-boosted trees on six raw-scaled bands, the
    same model settings as regress_built_fraction.py.
  * The six base endmembers are the measured Khayelitsha set, unchanged, and
    the base mixture proportions are unchanged, so these numbers sit on the
    same scale as 0.490 / 0.822.
  * Each rare fraction enters as a seventh mixture component whose spectrum is
    one of that fraction's measured site endmembers (measure_rare_endmembers.py),
    chosen per pixel. The target is that component's share.
Those helpers live in modules that initialise Earth Engine on import, so the
small pieces are restated here; CONTROLS below prove the restatement matches
the original by reproducing its published numbers exactly.

Conditions are optimistic by construction, as before: exact labels, exactly
linear mixing, fixed endmembers, no shadow, no atmospheric residual, no BRDF,
no cross-site transfer. Each ceiling is an UPPER BOUND. "Recoverable" means
"not ruled out by physics", never "will work".

PRE-REGISTERED, fixed before any real-data result existed
----------------------------------------------------------
QUESTION: for each rare fraction, is its per-pixel share recoverable in
principle from 10 m / 6-band Sentinel-2?

DECISION RULE (primary: ridge, noise NOISE_PRIMARY, the "realistic" scene):
  ceiling R^2 >= RECOVERABLE_MIN (0.70)     -> LABEL IT       (recoverable)
  ceiling R^2 <  UNIDENTIFIABLE_MAX (0.50)  -> DON'T LABEL IT (unidentifiable)
  between                                   -> INDETERMINATE

NOISE: primary 0.005 reflectance (documented S2 L2A BOA order); 0.010 and
  0.020 reported beside it, and the full sweep printed.

REALISTIC SCENE: base alphas as in 06 (ALPHA_BASE) plus the rare component at
  RARE_ALPHA = 0.35, the same weight as paved, so the rare target has a
  paved-like distribution. Realised mean/sd printed.

SOLAR PANEL SHARE (rooftop panels are sub-pixel): every pixel carries solar at
  share ~ U(0, s_max), the rest a base mixture; s_max swept over
  SOLAR_SHARE_SWEEP. A rooftop sub-verdict applies the same rule at
  ROOFTOP_SHARE_PRIMARY = 0.25 using the rooftop endmember(s): a residential
  array of 10-20 panels is 20-40 m^2, at most 0.2-0.4 of a 100 m^2 cell, and
  real arrays straddle cells, so U(0, 0.25) is generous. If no rooftop site
  measured OK, all solar sites are used and that is said.

CONTROLS, run first; any failure aborts:
  1. vegetation, base-only, exact 06 conditions -> must reproduce 0.974
  2. built, base-only, exact 06 conditions      -> must reproduce 0.490
     (1 and 2 within CONTROL_TOL; they prove this restatement is the method)
  3. in every rare scene, vegetation must still clear SCENE_VEG_MIN_R2 (0.90)

DIAGNOSTICS, reported but carrying no verdict:
  * Pairwise spectral angles in the 06 table format, class-mean rare spectra.
  * Per site: nearest base angle, angle to its local surround, and the
    residual after the best convex fit by the six base endmembers. A spectrum
    INSIDE the base simplex is a mixture of other fractions and cannot be
    unmixed as its own, however large its angles look. In units of the noise
    vector norm (0.005 * sqrt(6)).
  * Within-class spread: the largest angle between two sites of one class.
  * "All-rare" stress scene: base + all three rare fractions at once.

BLIND-SPOT AUDIT, before running -- "what wrong answer would still pass?"
  * A spectrally selected endmember would be separable by construction.
    GUARD: sites come from mapped references only (measure_rare_endmembers.py).
  * Large angles can hide a mixture (a wetland is partly water, partly plant).
    GUARD: the convex-hull residual, reported for every site.
  * Absolute noise understates noise on bright snow (radiometric error grows
    with signal). NOT GUARDED; stated as a limit, and it inflates snow_ice.
  * Site-to-site variability is modelled as a few discrete endmembers the
    regressor gets to see, the same generosity 06 gave built_fabric/inst.
    Real variability is continuous and only lowers the ceiling.
  * The Khayelitsha base set is not each site's local background (desert sand
    at Bhadla, moraine at Aletsch). GUARD, partial: the surround angle shows
    how close the local background really is.

Usage:
    python ceiling_rare_fractions.py
"""

import argparse
import datetime as dt
import json
import math
import os

import numpy as np
from scipy.optimize import nnls
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.metrics import mean_absolute_error, r2_score

# --- pre-registered; not edited after seeing results ---------------------
RECOVERABLE_MIN = 0.70
UNIDENTIFIABLE_MAX = 0.50

NOISE_PRIMARY = 0.005
NOISE_REPORTED = [0.005, 0.010, 0.020]
NOISE_SWEEP = [0.0, 0.002, 0.005, 0.010, 0.020]

N_PIXELS = 40000
SEED = 42

RARE_ALPHA = 0.35
SOLAR_SHARE_SWEEP = [0.05, 0.10, 0.25, 0.50, 1.00]
ROOFTOP_SHARE_PRIMARY = 0.25

CONTROL_VEG_R2 = 0.974          # 06_UNMIXING_CEILING.md Part 3
CONTROL_BUILT_R2 = 0.490        # 06_UNMIXING_CEILING.md Part 3
CONTROL_TOL = 0.005
SCENE_VEG_MIN_R2 = 0.90
# -------------------------------------------------------------------------

# Same settings as regress_built_fraction.py (RIDGE_ALPHAS, GBT_KW).
RIDGE_ALPHAS = np.logspace(-3, 3, 13)
GBT_KW = dict(max_depth=3, max_iter=200, learning_rate=0.1,
              early_stopping=False, random_state=0)
PRIMARY_MODEL = "ridge"

# Measured Khayelitsha endmembers, verbatim from ceiling_built_fraction.EM.
EM_BASE = {
    "built_fabric": [0.1108, 0.1296, 0.1479, 0.1791, 0.2216, 0.2082],
    "built_inst":   [0.1847, 0.2063, 0.2235, 0.2625, 0.3047, 0.2966],
    "paved":        [0.1068, 0.1299, 0.1517, 0.1905, 0.2349, 0.2103],
    "bare":         [0.1523, 0.1891, 0.2199, 0.2710, 0.3024, 0.2652],
    "veg":          [0.0318, 0.0575, 0.0546, 0.2373, 0.1846, 0.1224],
    "water":        [0.1350, 0.1650, 0.1268, 0.0655, 0.0230, 0.0159],
}
ORDER_BASE = ["built_fabric", "built_inst", "paved", "bare", "veg", "water"]
ALPHA_BASE = np.array([0.45, 0.12, 0.35, 0.7, 0.7, 0.08])
BUILT_IDX = [0, 1]
VEG_IDX = 4

RARE_FRACTIONS = ["solar", "snow_ice", "mixed_water_vegetation"]
ENDMEMBERS_PATH = "experiments/rare_fraction_ceilings/endmembers.json"
RESULT_DIR = "experiments/rare_fraction_ceilings"


# ---------------------------------------------------------------- geometry

def spectral_angle(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    c = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def angle_table(spectra, order):
    return [[spectral_angle(spectra[i], spectra[j]) for j in order]
            for i in order]


def hull_residual(r, M, weight=1e3):
    """Best convex fit of spectrum r by the rows of M (a >= 0, sum a = 1).

    Fully-constrained least squares via the usual augmented-NNLS trick.
    Returns (residual norm in reflectance, coefficients).
    """
    M = np.asarray(M, float)
    r = np.asarray(r, float)
    A = np.vstack([M.T, weight * np.ones(len(M))])
    b = np.concatenate([r, [weight]])
    a, _ = nnls(A, b)
    return float(np.linalg.norm(M.T @ a - r)), a


def noise_units(residual, noise=NOISE_PRIMARY, bands=6):
    return residual / (noise * math.sqrt(bands))


# ---------------------------------------------------------------- simulation

def base_matrix():
    return np.array([EM_BASE[k] for k in ORDER_BASE])


def simulate_base(n, noise, rng, alpha=ALPHA_BASE):
    """ceiling_built_fraction.simulate, restated; same RNG consumption."""
    M = base_matrix()
    A = rng.dirichlet(alpha, size=n)
    X = A @ M
    if noise > 0:
        X = X + rng.normal(scale=noise, size=X.shape)
    return X, A


def simulate_rare(n, noise, rng, rare_list, rare_alpha=RARE_ALPHA,
                  alpha=ALPHA_BASE):
    """Base mixture plus one or more rare components.

    rare_list: one entry per rare fraction; each entry is a list of site
    spectra. Each pixel takes one site spectrum per fraction, uniformly.
    Returns X, base shares (n x 6), rare shares (n x len(rare_list)).
    """
    M = base_matrix()
    k = len(rare_list)
    A = rng.dirichlet(np.concatenate([alpha, [rare_alpha] * k]), size=n)
    X = A[:, :6] @ M
    for j, sites in enumerate(rare_list):
        S = np.asarray(sites, float)
        pick = rng.integers(0, len(S), size=n)
        X = X + A[:, 6 + j:7 + j] * S[pick]
    if noise > 0:
        X = X + rng.normal(scale=noise, size=X.shape)
    return X, A[:, :6], A[:, 6:]


def simulate_share(n, noise, rng, sites, s_max, alpha=ALPHA_BASE):
    """Rare share ~ U(0, s_max) in every pixel; the rest a base mixture."""
    M = base_matrix()
    S = np.asarray(sites, float)
    r = rng.uniform(0.0, s_max, size=n)
    B = rng.dirichlet(alpha, size=n) * (1.0 - r)[:, None]
    pick = rng.integers(0, len(S), size=n)
    X = B @ M + r[:, None] * S[pick]
    if noise > 0:
        X = X + rng.normal(scale=noise, size=X.shape)
    return X, B, r


# ---------------------------------------------------------------- evaluation

def fit_predict(model, Xtr, ytr, Xte):
    m = (RidgeCV(alphas=RIDGE_ALPHAS) if model == "ridge"
         else HistGradientBoostingRegressor(**GBT_KW))
    m.fit(Xtr, ytr)
    return np.clip(m.predict(Xte), 0.0, 1.0)


def evaluate(X, y, rng, models=("ridge", "gbt")):
    """Random 50/50 split, raw scaling fitted on train; as in 06."""
    idx = rng.permutation(len(X))
    h = len(idx) // 2
    tr, te = idx[:h], idx[h:]
    mu, sd = X[tr].mean(0), X[tr].std(0)
    sd[sd == 0] = 1.0
    Xtr, Xte = (X[tr] - mu) / sd, (X[te] - mu) / sd
    out = {}
    for model in models:
        yhat = fit_predict(model, Xtr, y[tr], Xte)
        out[model] = (float(r2_score(y[te], yhat)),
                      float(mean_absolute_error(y[te], yhat)))
    return out


def verdict(r2):
    if r2 >= RECOVERABLE_MIN:
        return "LABEL IT"
    if r2 < UNIDENTIFIABLE_MAX:
        return "DON'T LABEL IT"
    return "INDETERMINATE"


def run_controls(models=("ridge",)):
    """Reproduce 06's vegetation (0.974) and built (0.490) ceilings."""
    rng = np.random.default_rng(SEED)
    X, A = simulate_base(N_PIXELS, NOISE_PRIMARY, rng)
    veg = evaluate(X, A[:, VEG_IDX], rng, models)
    r = np.random.default_rng(SEED)
    X, A = simulate_base(N_PIXELS, NOISE_PRIMARY, r)
    built = evaluate(X, A[:, BUILT_IDX].sum(1), r, models)
    ok = (abs(veg["ridge"][0] - CONTROL_VEG_R2) <= CONTROL_TOL
          and abs(built["ridge"][0] - CONTROL_BUILT_R2) <= CONTROL_TOL)
    return ok, veg, built


# ---------------------------------------------------------------- data

def load_endmembers(path=ENDMEMBERS_PATH):
    with open(path) as f:
        data = json.load(f)
    groups = {k: [] for k in RARE_FRACTIONS}
    for s in data["sites"]:
        if s.get("status") == "ok" and s["fraction"] in groups:
            groups[s["fraction"]].append(s)
    return data, groups


def class_means(groups):
    return {k: np.mean([s["mean"] for s in v], axis=0).tolist()
            for k, v in groups.items() if v}


def within_class_spread(sites):
    if len(sites) < 2:
        return 0.0
    return max(spectral_angle(a["mean"], b["mean"])
               for i, a in enumerate(sites) for b in sites[i + 1:])


# ---------------------------------------------------------------- reporting

def site_diagnostics(groups):
    M = base_matrix()
    rows = []
    for frac, sites in groups.items():
        for s in sites:
            angles = {k: spectral_angle(s["mean"], EM_BASE[k])
                      for k in ORDER_BASE}
            nearest = min(angles, key=angles.get)
            res, coef = hull_residual(s["mean"], M)
            rows.append(dict(
                fraction=frac, site=s["name"], subtype=s["subtype"],
                n_pixels=s["n_pixels"], n_images=s["n_images"],
                angles=angles, nearest=nearest, nearest_angle=angles[nearest],
                surround_angle=(spectral_angle(s["mean"], s["surround_mean"])
                                if s.get("surround_mean") else None),
                hull_residual=res, hull_residual_noise_units=noise_units(res),
                hull_coefficients=dict(zip(ORDER_BASE, coef.round(3).tolist())),
            ))
    return rows


def ceiling_for(frac_sites, others=(), noise_sweep=NOISE_SWEEP):
    """Noise sweep for one rare fraction (index 0 of rare_list)."""
    out = []
    for noise in noise_sweep:
        r = np.random.default_rng(SEED)
        X, B, R = simulate_rare(N_PIXELS, noise, r,
                                [frac_sites, *others])
        y = R[:, 0]
        res = evaluate(X, y, r)
        r2 = np.random.default_rng(SEED + 1)
        veg = evaluate(X, B[:, VEG_IDX], r2, ("ridge",))["ridge"][0]
        out.append(dict(noise=noise, ridge=res["ridge"], gbt=res["gbt"],
                        y_mean=float(y.mean()), y_sd=float(y.std()),
                        veg_ridge_r2=veg))
    return out


def share_sweep(sites, noises=NOISE_REPORTED):
    out = []
    for s_max in SOLAR_SHARE_SWEEP:
        for noise in noises:
            r = np.random.default_rng(SEED)
            X, _, y = simulate_share(N_PIXELS, noise, r, sites, s_max)
            res = evaluate(X, y, r)
            out.append(dict(s_max=s_max, noise=noise, ridge=res["ridge"],
                            gbt=res["gbt"], y_mean=float(y.mean()),
                            y_sd=float(y.std())))
    return out


def build_result(controls, diag, angles, ceilings, shares, rooftop, stress,
                 spreads, verdicts, endmembers_meta):
    return dict(
        validation_status="experimental",
        note=("Simulated upper bounds under optimistic conditions. Not a "
              "validation of any producer; nothing here is `validated`."),
        computed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        rule=dict(recoverable_min=RECOVERABLE_MIN,
                  unidentifiable_max=UNIDENTIFIABLE_MAX,
                  noise_primary=NOISE_PRIMARY, primary_model=PRIMARY_MODEL,
                  rare_alpha=RARE_ALPHA,
                  rooftop_share_primary=ROOFTOP_SHARE_PRIMARY),
        endmembers=endmembers_meta,
        controls=controls, site_diagnostics=diag, angle_table=angles,
        within_class_spread_deg=spreads, ceilings=ceilings,
        solar_share_sweep=shares, rooftop=rooftop, stress_all_rare=stress,
        verdicts=verdicts,
    )


def _fmt_table(order, mat):
    w = max(len(k) for k in order)
    head = " " * (w + 1) + " ".join(f"{k[:9]:>9}" for k in order)
    lines = [head]
    for k, row in zip(order, mat):
        lines.append(f"{k:<{w}} " + " ".join(f"{v:>9.2f}" for v in row))
    return "\n".join(lines)


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()

    print("PRE-REGISTERED DECISION RULE (ridge, noise 0.005, realistic scene):")
    print(f"  R2 >= {RECOVERABLE_MIN} -> LABEL IT;  R2 < {UNIDENTIFIABLE_MAX} "
          f"-> DON'T LABEL IT;  between -> INDETERMINATE\n")

    ok, veg, built = run_controls(("ridge", "gbt"))
    print(f"CONTROL 1 vegetation: ridge R2={veg['ridge'][0]:.3f} "
          f"(must be {CONTROL_VEG_R2}±{CONTROL_TOL}), gbt {veg['gbt'][0]:.3f}")
    print(f"CONTROL 2 built:      ridge R2={built['ridge'][0]:.3f} "
          f"(must be {CONTROL_BUILT_R2}±{CONTROL_TOL}), gbt "
          f"{built['gbt'][0]:.3f}")
    if not ok:
        print("ABORT -- restated method does not reproduce 06.")
        return 1
    print("  -> OK\n")
    controls = dict(veg=veg, built=built, ok=ok)

    data, groups = load_endmembers()
    for frac in RARE_FRACTIONS:
        print(f"{frac}: {len(groups[frac])} site(s) OK: "
              f"{[s['name'] for s in groups[frac]]}")
    bad = [s["name"] for s in data["sites"] if s.get("status") != "ok"]
    if bad:
        print(f"  sites NOT used (failed/error): {bad}")

    diag = site_diagnostics(groups)
    means = class_means(groups)
    order = ["built_inst", "built_fabric", "paved", "bare", "veg", "water",
             *[k for k in RARE_FRACTIONS if k in means]]
    spectra = {**EM_BASE, **means}
    mat = angle_table(spectra, order)
    print("\nPAIRWISE SPECTRAL ANGLES (deg), rare classes = mean of sites")
    print(_fmt_table(order, mat))

    print("\nPER SITE: nearest base | surround | convex-hull residual")
    for d in diag:
        sur = (f"{d['surround_angle']:.2f}" if d["surround_angle"] is not None
               else "n/a")
        print(f"  {d['fraction']:<22} {d['site']:<15} n={d['n_pixels']:<6} "
              f"nearest {d['nearest']:<12} {d['nearest_angle']:6.2f} | "
              f"surround {sur:>6} | resid {d['hull_residual']:.4f} "
              f"({d['hull_residual_noise_units']:.1f}x noise)")
    spreads = {k: within_class_spread(v) for k, v in groups.items()}
    print(f"  within-class spread (deg): "
          f"{ {k: round(v, 2) for k, v in spreads.items()} }")

    ceilings, verdicts = {}, {}
    for frac in RARE_FRACTIONS:
        if not groups[frac]:
            verdicts[frac] = dict(verdict="NOT RUN -- no site measured OK")
            continue
        sites = [s["mean"] for s in groups[frac]]
        rows = ceiling_for(sites)
        ceilings[frac] = rows
        print(f"\nCEILING {frac}  ({len(sites)} site endmember(s))")
        print(f"{'noise':>7} {'ridge R2':>9} {'MAE':>7} {'gbt R2':>7} "
              f"{'y mean':>7} {'y sd':>6} {'veg R2':>7}")
        for r in rows:
            print(f"{r['noise']:>7.3f} {r['ridge'][0]:>9.3f} "
                  f"{r['ridge'][1]:>7.4f} {r['gbt'][0]:>7.3f} "
                  f"{r['y_mean']:>7.3f} {r['y_sd']:>6.3f} "
                  f"{r['veg_ridge_r2']:>7.3f}")
        prim = next(r for r in rows if r["noise"] == NOISE_PRIMARY)
        scene_ok = all(r["veg_ridge_r2"] >= SCENE_VEG_MIN_R2 for r in rows
                       if r["noise"] == NOISE_PRIMARY)
        v = verdict(prim["ridge"][0]) if scene_ok else "CONTROL 3 FAILED"
        verdicts[frac] = dict(
            verdict=v, ridge_r2=prim["ridge"][0], gbt_r2=prim["gbt"][0],
            r2_at={str(r["noise"]): r["ridge"][0] for r in rows
                   if r["noise"] in NOISE_REPORTED})
        print(f"  ==> {frac}: {v}  (ridge {prim['ridge'][0]:.3f})")

    shares, rooftop = [], None
    if groups["solar"]:
        all_solar = [s["mean"] for s in groups["solar"]]
        roof = [s["mean"] for s in groups["solar"] if s["subtype"] == "rooftop"]
        shares = share_sweep(all_solar)
        print("\nSOLAR vs PANEL SHARE (share ~ U(0, s_max)), all solar sites")
        print(f"{'s_max':>6} {'noise':>6} {'ridge R2':>9} {'MAE':>7} "
              f"{'gbt R2':>7}")
        for r in shares:
            print(f"{r['s_max']:>6.2f} {r['noise']:>6.3f} "
                  f"{r['ridge'][0]:>9.3f} {r['ridge'][1]:>7.4f} "
                  f"{r['gbt'][0]:>7.3f}")
        src = "rooftop site(s)" if roof else "all solar sites (no rooftop OK)"
        rr = np.random.default_rng(SEED)
        X, _, y = simulate_share(N_PIXELS, NOISE_PRIMARY, rr,
                                 roof or all_solar, ROOFTOP_SHARE_PRIMARY)
        res = evaluate(X, y, rr)
        rooftop = dict(endmembers=src, s_max=ROOFTOP_SHARE_PRIMARY,
                       ridge=res["ridge"], gbt=res["gbt"],
                       verdict=verdict(res["ridge"][0]))
        print(f"  ROOFTOP sub-verdict (s_max={ROOFTOP_SHARE_PRIMARY}, {src}): "
              f"ridge {res['ridge'][0]:.3f} -> {rooftop['verdict']}")

    stress = {}
    present = [k for k in RARE_FRACTIONS if groups[k]]
    if len(present) > 1:
        lists = [[s["mean"] for s in groups[k]] for k in present]
        r = np.random.default_rng(SEED)
        X, B, R = simulate_rare(N_PIXELS, NOISE_PRIMARY, r, lists)
        print("\nSTRESS: all rare fractions present at once (noise 0.005)")
        for j, k in enumerate(present):
            rj = np.random.default_rng(SEED + 10 + j)
            res = evaluate(X, R[:, j], rj)
            stress[k] = res
            print(f"  {k:<24} ridge {res['ridge'][0]:.3f}  "
                  f"gbt {res['gbt'][0]:.3f}")

    result = build_result(
        controls, diag, dict(order=order, degrees=mat), ceilings, shares,
        rooftop, stress, spreads, verdicts,
        dict(path=ENDMEMBERS_PATH, measured_at=data.get("measured_at"),
             not_measured=data.get("not_measured")))
    os.makedirs(RESULT_DIR, exist_ok=True)
    path = os.path.join(RESULT_DIR,
                        f"result_{dt.date.today().isoformat()}.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nVERDICTS: { {k: v['verdict'] for k, v in verdicts.items()} }")
    print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
