"""
Spectral endmember extraction (VCA + N-FINDR), vector data used ONLY to label
the results.

Why
---
Every endmember in this investigation so far was produced by the vector-mask
method: pick polygons you trust, pull the pixels inside them, average. That
method failed twice, in opposite ways --

  built  broad coverage, ~1-5% pixel purity, and the purity that exists is
         adversely selected toward institutional structures (700-1,057 m^2
         mean, against fabric means of 47-153 m^2)
  paved  good purity, 0.23-1.82% AOI coverage, ~all parking-lot asphalt

and the B-decomposition test could not even adjudicate its own endmember,
because that endmember inherited the same weakness (n=33-65 pixels).

This script inverts the dependency. VCA and N-FINDR search the AOI's own
spectral feature space for its extreme vertices, with no vector mask involved
in candidate generation at all. Vector data is then used post-hoc, purely to
ask "what does each extracted vertex sit on top of?".

Note on what this does and does not escape: VCA and N-FINDR both rest on the
PURE PIXEL ASSUMPTION -- they select the most extreme pixel that EXISTS, they
do not manufacture one. They escape grid-alignment and OSM-completeness. They
do not escape physical absence of pure pixels. If no pure informal-roof pixel
exists in the scene, neither algorithm can return one, and spectral extremity
is plausibly correlated with the same adverse selection (a large uniform
bright roof is extreme; a 7m shack ringed by shadowed gaps is interior).
That is precisely what the pre-registered failure condition below tests.

PRE-REGISTERED, fixed before the first run
------------------------------------------
Sample:           N_SAMPLE pixels, SEED fixed, uniform random over the AOI,
                  independent of any vector layer.
Extraction input: SPECTRAL_BANDS only. The vector/index bands are carried
                  through the sample for labelling and are NEVER seen by VCA
                  or N-FINDR.
p:                P_PRIMARY endmembers (5 classes + shadow, per Decision 13).
                  P_SENSITIVITY also reported.

"Overlaps small-structure fabric" (the failure-condition predicate):
    built_cov >= SMALL_FABRIC_MIN_COVERAGE  AND  big_cov == 0
  where big_cov is coverage by footprints >= BIG_BUILDING_M2.
  BIG_BUILDING_M2 = 100 is one 10m pixel-equivalent, the threshold used
  consistently throughout this investigation (sub-pixel classification,
  endmember B's mask, MIN_BIG_AREA_M2), and 93.5% of Khayelitsha's confident
  footprints fall below it -- so it separates the fabric from the
  institutional tail rather than being chosen to fit an outcome.
  Coverage >= 0.50 means majority-roofed. Deliberately NOT 1.0: imposing
  geometric purity in the LABELLING step would reintroduce the very filter
  this extraction exists to avoid.

Vertex support:
    counted as sampled pixels within SUPPORT_TIGHT_DEG and SUPPORT_LOOSE_DEG
    spectral angle of the vertex. A vertex with fewer than WEAK_SUPPORT_N
    pixels inside SUPPORT_LOOSE_DEG is reported as WEAKLY SUPPORTED, so a
    vertex driven by a handful of pixels -- echoing endmember B's n=33-65
    weakness -- is never presented as equally well-supported.

FAILURE CONDITION (pre-registered, unchanged from when it was proposed):
    If the extracted vertices resolve as institutional roof / shadow / water /
    vegetation / bare, with NO vertex satisfying the small-structure-fabric
    predicate above, that is this approach FAILING. The indicated next step is
    minimum-volume extraction (SISAL / MVSA) -- algorithms that drop the pure
    pixel assumption -- NOT further tuning of this approach, and NOT relaxing
    the purity notion (MESMA-style), which would reintroduce mixing under a
    new name.

Record: excluded B-decomposition cell
-------------------------------------
The CT-formal / S2-SCL-shadow nnls cell (residual 2.66%, nominally "not a
distinct material") was EXCLUDED because its fitted coefficients (0.522,
1.104) sum to 1.63 and therefore violate the convexity constraint that the
hypothesis B = alpha*A + (1-alpha)*S requires -- it is not a mixture, it is an
unconstrained fit spending an extra degree of freedom. It is excluded on that
ground alone, NOT because it disagreed with the convex fit's result. The
convex fit on identical inputs gave 8.48%, indeterminate.

Usage:
    python extract_endmembers_vca.py
    python extract_endmembers_vca.py --aoi khayelitsha
"""

import argparse
import math

import numpy as np

import diagnose_open_buildings_aoi as diag
import diagnose_pure_pixels as pure_diag
import diagnose_pure_pixels_paved as paved_diag
import ee
import test_endmember_sensitivity as sens
from ingestion.sentinel2 import S2_BAND_NAMES, get_sentinel2_median_composite

# --- pre-registered constants; do not edit after seeing results ----------
N_SAMPLE = 20000
SEED = 42
P_PRIMARY = 6
P_SENSITIVITY = [5, 7]

BIG_BUILDING_M2 = 100
SMALL_FABRIC_MIN_COVERAGE = 0.50

SUPPORT_TIGHT_DEG = 2.87
SUPPORT_LOOSE_DEG = 5.74
WEAK_SUPPORT_N = 100
# -------------------------------------------------------------------------

SPECTRAL_BANDS = list(S2_BAND_NAMES)          # seen by the algorithms
LABEL_BANDS = ["built_cov", "big_cov", "paved_cov", "ndvi", "mndwi"]  # never seen


def build_sample_image(composite, aoi, proj, confident, paved_fc):
    """Spectral bands plus label-only bands, as one image to sample once.

    The label bands ride along so that labelling needs no per-point vector
    query, but they are dropped before extraction. Sampling itself is uniform
    over the AOI and conditioned on nothing.
    """
    built_cov = sens.coverage_fraction(confident, proj).rename("built_cov")
    big = confident.filter(ee.Filter.gte("area_in_meters", BIG_BUILDING_M2))
    big_cov = sens.coverage_fraction(big, proj).rename("big_cov")
    paved_cov = (sens.coverage_fraction(paved_fc, proj) if paved_fc is not None
                 else ee.Image(0)).rename("paved_cov")

    ndvi = composite.normalizedDifference(["NIR", "Red"]).rename("ndvi")
    mndwi = composite.normalizedDifference(["Green", "SWIR1"]).rename("mndwi")

    return composite.addBands([built_cov, big_cov, paved_cov, ndvi, mndwi])


def sample_pixels(image, aoi, proj_info):
    fc = image.sample(
        region=aoi,
        numPixels=N_SAMPLE,
        seed=SEED,
        projection=ee.Projection(proj_info["crs"]).translate(0, 0),
        scale=10,
        dropNulls=True,
        geometries=False,
    )
    # getInfo() aborts a FeatureCollection past 5000 elements; computeFeatures
    # paginates, so the pre-registered N_SAMPLE is honoured rather than
    # quietly truncated.
    rows = []
    params = {"expression": fc, "fileFormat": "GEOPANDAS_GEODATAFRAME"}
    try:
        df = ee.data.computeFeatures(params)
        rows = df.drop(columns=["geometry"], errors="ignore").to_dict("records")
    except Exception:
        page_token = None
        while True:
            p = {"expression": fc, "fileFormat": "PANDAS_DATAFRAME"}
            if page_token:
                p["pageToken"] = page_token
            resp = ee.data.computeFeatures(p)
            rows.extend(resp.to_dict("records"))
            page_token = getattr(resp, "_page_token", None)
            if not page_token:
                break
    spec = np.array([[r[b] for b in SPECTRAL_BANDS] for r in rows], float)
    lab = {b: np.array([r.get(b, np.nan) for r in rows], float)
           for b in LABEL_BANDS}
    return spec, lab


def vca(Y, p, seed=SEED):
    """Vertex Component Analysis (Nascimento & Dias 2005).

    Y: (bands, N) non-negative reflectance. Returns indices of the p vertices.
    """
    rng = np.random.default_rng(seed)
    L, N = Y.shape

    # Signal subspace via SVD without mean removal (high-SNR branch).
    Ud = np.linalg.svd(Y @ Y.T / N)[0][:, :p]
    x = Ud.T @ Y

    # Projective projection onto the simplex-carrying hyperplane.
    u = x.mean(axis=1)
    denom = u @ x
    denom[np.abs(denom) < 1e-12] = 1e-12
    y = x / denom

    indices = np.zeros(p, dtype=int)
    E = np.zeros((p, p))
    for i in range(p):
        w = rng.normal(size=(p, 1))
        f = w - E @ np.linalg.pinv(E) @ w
        f = f / (np.linalg.norm(f) + 1e-12)
        v = (f.T @ y).ravel()
        idx = int(np.argmax(np.abs(v)))
        indices[i] = idx
        E[:, i] = y[:, idx]
    return indices


def nfindr(Y, p, seed=SEED, iters=3):
    """N-FINDR: maximise simplex volume over actual pixels."""
    rng = np.random.default_rng(seed)
    L, N = Y.shape

    # Reduce to p-1 dims (PCA on mean-removed data).
    mu = Y.mean(axis=1, keepdims=True)
    Yc = Y - mu
    U = np.linalg.svd(Yc @ Yc.T / N)[0][:, :p - 1]
    X = U.T @ Yc  # (p-1, N)

    idx = rng.choice(N, size=p, replace=False)

    def volume(cols):
        M = np.vstack([np.ones((1, p)), X[:, cols]])
        return abs(np.linalg.det(M))

    best = volume(idx)
    for _ in range(iters):
        changed = False
        for i in range(p):
            for n in range(N):
                trial = idx.copy()
                trial[i] = n
                v = volume(trial)
                if v > best:
                    best, idx, changed = v, trial, True
        if not changed:
            break
    return idx


def spectral_angle_deg(a, B):
    """Angle between vector a and each row of B, in degrees."""
    a = np.asarray(a, float)
    B = np.asarray(B, float)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(B, axis=1)
    cos = (B @ a) / (nb * na + 1e-12)
    return np.degrees(np.arccos(np.clip(cos, -1, 1)))


def label_vertex(lab, i):
    """Post-hoc flags for one vertex. Vector data enters ONLY here."""
    built = lab["built_cov"][i]
    big = lab["big_cov"][i]
    paved = lab["paved_cov"][i]
    ndvi = lab["ndvi"][i]
    mndwi = lab["mndwi"][i]

    small_fabric = (built >= SMALL_FABRIC_MIN_COVERAGE) and (big == 0)

    flags = []
    if small_fabric:
        flags.append("SMALL-STRUCTURE FABRIC")
    if big > 0:
        flags.append("large-building")
    if paved >= 0.5:
        flags.append("paved-osm")
    if ndvi >= 0.5:
        flags.append("vegetation")
    if mndwi >= 0.3:
        flags.append("water")
    if not flags:
        flags.append("bare/other")

    return small_fabric, flags, dict(built_cov=built, big_cov=big,
                                     paved_cov=paved, ndvi=ndvi, mndwi=mndwi)


def report_vertices(name, idx, spec, lab, brightness_p5):
    print(f"\n  --- {name}: {len(idx)} vertices ---")
    any_small = False
    for rank, i in enumerate(idx):
        v = spec[i]
        angles = spectral_angle_deg(v, spec)
        n_tight = int((angles <= SUPPORT_TIGHT_DEG).sum())
        n_loose = int((angles <= SUPPORT_LOOSE_DEG).sum())
        weak = n_loose < WEAK_SUPPORT_N

        small, flags, meta = label_vertex(lab, i)
        any_small = any_small or small

        norm = float(np.linalg.norm(v))
        dark = norm <= brightness_p5

        print(f"    v{rank}: {[round(float(x),4) for x in v]}  ||v||={norm:.3f}"
              + ("  [dark/shadow-like]" if dark else ""))
        print(f"        support: {n_tight} @{SUPPORT_TIGHT_DEG}deg, "
              f"{n_loose} @{SUPPORT_LOOSE_DEG}deg "
              f"({100*n_loose/len(spec):.2f}% of sample)"
              + ("   *** WEAKLY SUPPORTED ***" if weak else ""))
        print(f"        labels : {', '.join(flags)}")
        print(f"        vector : built_cov={meta['built_cov']:.2f} "
              f"big_cov={meta['big_cov']:.2f} paved_cov={meta['paved_cov']:.2f} "
              f"ndvi={meta['ndvi']:.2f} mndwi={meta['mndwi']:.2f}")
    return any_small


def run_aoi(label, aoi, cache_key):
    print(f"\n{'=' * 78}")
    print(f"[{label}]")
    print(f"{'=' * 78}")

    proj, proj_info = pure_diag.s2_grid_for(aoi)
    comp = get_sentinel2_median_composite(aoi, sens.START_DATE, sens.END_DATE)
    composite = comp["image"]

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

    img = build_sample_image(composite, aoi, proj, confident, paved_fc)
    print(f"  sampling {N_SAMPLE} pixels (seed {SEED})...", flush=True)
    spec, lab = sample_pixels(img, aoi, proj_info)
    print(f"  got {len(spec)} valid pixels x {spec.shape[1]} spectral bands")
    print(f"  (label bands {LABEL_BANDS} carried but NOT passed to extraction)")

    brightness = np.linalg.norm(spec, axis=1)
    brightness_p5 = float(np.percentile(brightness, 5))
    print(f"  brightness 5th pct ||v|| = {brightness_p5:.3f} "
          f"(used only to annotate dark vertices)")

    # CONTROL on test validity, added before reading results: if no sampled
    # pixel satisfies the small-fabric predicate, then no vertex could, and a
    # FAIL would be vacuous rather than evidence about the algorithms.
    small_mask = ((lab["built_cov"] >= SMALL_FABRIC_MIN_COVERAGE)
                  & (lab["big_cov"] == 0))
    n_small = int(small_mask.sum())
    print(f"  CONTROL: {n_small} of {len(spec)} sampled pixels satisfy the "
          f"small-fabric predicate ({100*n_small/len(spec):.2f}%)")
    if n_small == 0:
        print("    *** predicate unsatisfiable in this sample -- a FAIL below")
        print("        would be vacuous, not evidence about the algorithms")
    else:
        sm = spec[small_mask].mean(axis=0)
        print(f"    their mean spectrum: {[round(float(x),4) for x in sm]}")

    Y = spec.T  # (bands, N)

    results = {}
    n_bands = Y.shape[0]
    for p in [P_PRIMARY] + P_SENSITIVITY:
        tag = "PRIMARY" if p == P_PRIMARY else "sensitivity"
        print(f"\n  ===== p={p} ({tag}) =====")
        if p > n_bands:
            # Structural, not a tuning limit: k bands span at most k linearly
            # independent endmembers. With the pipeline's 6-band stack the
            # ceiling is 6 -- exactly Decision 13's 5 classes plus shadow, with
            # no headroom for a 7th (e.g. splitting built into two materials).
            print(f"    SKIPPED -- p={p} exceeds the {n_bands}-band ceiling; "
                  f"at most {n_bands} endmembers are separable from this stack")
            continue
        v_idx = vca(Y, p)
        small_vca = report_vertices(f"VCA p={p}", v_idx, spec, lab, brightness_p5)

        n_idx = nfindr(Y, p)
        small_nf = report_vertices(f"N-FINDR p={p}", n_idx, spec, lab,
                                   brightness_p5)

        results[p] = (small_vca, small_nf)

    small_primary = results[P_PRIMARY]
    print(f"\n  PRE-REGISTERED FAILURE CHECK (p={P_PRIMARY}):")
    print(f"    predicate: built_cov >= {SMALL_FABRIC_MIN_COVERAGE} "
          f"AND no footprint >= {BIG_BUILDING_M2} m^2")
    print(f"    VCA     : {'PASS' if small_primary[0] else 'FAIL'} "
          f"-- {'a vertex overlaps' if small_primary[0] else 'NO vertex overlaps'}"
          f" small-structure fabric")
    print(f"    N-FINDR : {'PASS' if small_primary[1] else 'FAIL'} "
          f"-- {'a vertex overlaps' if small_primary[1] else 'NO vertex overlaps'}"
          f" small-structure fabric")

    return {"label": label, "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", choices=["khayelitsha", "formal"],
                        help="default: both")
    args = parser.parse_args()

    print("PRE-REGISTERED: "
          f"N={N_SAMPLE} seed={SEED} p={P_PRIMARY} "
          f"| small-fabric = built_cov>={SMALL_FABRIC_MIN_COVERAGE} "
          f"AND no bldg >= {BIG_BUILDING_M2} m^2 "
          f"| weak support < {WEAK_SUPPORT_N} px @ {SUPPORT_LOOSE_DEG}deg")

    cache_keys = {
        "Khayelitsha (capetown run)": "khayelitsha",
        "Cape Town formal suburbs": "ct_formal",
    }

    wanted = ({"khayelitsha": "Khayelitsha (capetown run)",
               "formal": "Cape Town formal suburbs"}.get(args.aoi)
              if args.aoi else None)

    rows = []
    for lbl, aoi in pure_diag.build_aois():
        if lbl not in cache_keys:
            continue  # Dharavi not in scope for this step
        if wanted and lbl != wanted:
            continue
        rows.append(run_aoi(lbl, aoi, cache_keys[lbl]))

    if len(rows) > 1:
        print("\n" + "=" * 90)
        print(f"FAILURE-CONDITION SUMMARY (p={P_PRIMARY})")
        print("=" * 90)
        for r in rows:
            v, n = r["results"][P_PRIMARY]
            print(f"  {r['label']:<30} VCA={'PASS' if v else 'FAIL'}  "
                  f"N-FINDR={'PASS' if n else 'FAIL'}")
        print("=" * 90)


if __name__ == "__main__":
    main()
