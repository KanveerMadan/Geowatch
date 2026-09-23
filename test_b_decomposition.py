"""
Is endmember B a distinct material, or just endmember A plus shadow?

Context
-------
test_endmember_sensitivity.py built two candidate `built` endmembers by the
vector-mask method:

  A  mean spectrum of pixels fully covered by buildings >= 500 m^2
     (institutional / warehouse roofing)
  B  mean spectrum of pixels fully covered by footprints but touching NO
     building >= 100 m^2 (dense small-structure fabric)

B came out uniformly darker than A and landed 1.66 deg from the `paved`
endmember in Khayelitsha. Asphalt is dark; shadow is dark. B's known main
validity threat is contamination by shadowed inter-structure gaps.

So B may be dark not because informal roofing is a dark material, but because
B is A seen through shadow. If that is true, there is no distinct informal
endmember to find, and the whole "which extraction method finds it" fork is
ill-posed -- the answer would instead be to model shadow properly, which
Decision 13 already specifies as a sixth term.

Test: fit  B ~= alpha*A + (1-alpha)*S  and measure the residual.

PRE-COMMITTED THRESHOLDS (fixed before the test was run)
--------------------------------------------------------
Metric: relative residual norm ||r|| / ||B||, and the equivalent residual
angle between B and its projection onto span{A, S}.

  <= 5%  (~2.87 deg)  ->  B is NOT a distinct material
  >= 10% (~5.74 deg)  ->  B IS a distinct material
  between             ->  INDETERMINATE, no call forced

Justification. The 5% floor sits above Sentinel-2 L2A BOA reflectance
uncertainty (~0.005 absolute, which is 1.20% of ||B||), so clearing it is not
noise-chasing. The 10% ceiling is 0.1 rad, the conventional SAM cut for "same
material" -- requiring B to be CLOSER to the A+shadow plane than that
convention makes "not distinct" a hard claim to earn rather than an easy one.
Both anchor to this investigation's own scale, where 1.66 deg read as
near-collinear and 4.5-6.6 deg as meaningfully separated. Three-way rather
than binary because forcing a call on a continuous quantity is how post-hoc
rationalisation gets in.

KNOWN LIMITATION, stated before running: with photometric shade (S = 0),
span{A,S} = span{A}, so the residual angle IS angle(A,B) = 4.54 deg for
Khayelitsha -- already inside the indeterminate band. The zero-shade variant
therefore cannot resolve this question. Its value is as a reference point; the
informative variants are the non-zero shadow references below.

Shadow references (this project has no measured BUILDING-shadow spectrum)
-------------------------------------------------------------------------
  S1  photometric shade, the zero vector -- the standard assumption and what
      Decision 13's shade term is
  S2  SCL cloud-shadow pixels (SCL == 3), which item 51 deliberately preserves
      in the composite. This is CLOUD shadow, not building shadow: same
      radiative situation (diffuse skylight only) but different geometry and
      surroundings. A proxy, and labelled as one.
  S3  dark-object: per-band 1st percentile over the AOI

Two fits are reported per reference:
  convex  alpha in [0,1], B ~= alpha*A + (1-alpha)*S -- literally the
          hypothesis as posed
  nnls    alpha, beta >= 0, B ~= alpha*A + beta*S -- strictly more permissive,
          allows overall scaling. If even this leaves a large residual, B
          being distinct is a strong conclusion.

Usage:
    python test_b_decomposition.py
"""

import argparse
import math

import numpy as np

import diagnose_pure_pixels as pure_diag
import diagnose_open_buildings_aoi as diag
import diagnose_pure_pixels_paved as paved_diag
import ee
import test_endmember_sensitivity as sens
from ingestion.sentinel2 import S2_BAND_NAMES, get_sentinel2_collection

# --- pre-committed, do not edit after seeing results ---------------------
NOT_DISTINCT_MAX = 0.05   # <= 5% relative residual -> not a distinct material
DISTINCT_MIN = 0.10       # >= 10% -> distinct material
# -------------------------------------------------------------------------


def scl_shadow_spectrum(aoi, proj_info):
    """Mean spectrum of SCL cloud-shadow pixels over the same window.

    Uses the raw collection (SCL intact) rather than the masked composite,
    because mask_s2_clouds keeps shadow but the composite median mixes it with
    unshadowed observations of the same ground.
    """
    coll = get_sentinel2_collection(aoi, sens.START_DATE, sens.END_DATE)

    def shadow_only(img):
        shadow = img.select("SCL").eq(3)
        return (img.updateMask(shadow).divide(10000)
                   .select(["B2", "B3", "B4", "B8", "B11", "B12"],
                           S2_BAND_NAMES))

    shadow_composite = coll.map(shadow_only).median()
    stats = shadow_composite.reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.count(),
                                          sharedInputs=True),
        geometry=aoi, crs=proj_info["crs"],
        crsTransform=proj_info["transform"], maxPixels=1e10,
    ).getInfo()

    n = stats.get(f"{S2_BAND_NAMES[0]}_count") or 0
    vals = [stats.get(f"{b}_mean") for b in S2_BAND_NAMES]
    if not n or any(v is None for v in vals):
        return None, 0
    return vals, int(n)


def dark_object_spectrum(composite, aoi, proj_info):
    """Per-band 1st percentile over the AOI."""
    stats = composite.reduceRegion(
        reducer=ee.Reducer.percentile([1]),
        geometry=aoi, crs=proj_info["crs"],
        crsTransform=proj_info["transform"], maxPixels=1e10,
    ).getInfo()
    # With a SINGLE percentile, EE names outputs by bare band name; with
    # several it appends _pN. Accept either so this doesn't silently vanish.
    vals = [stats.get(f"{b}_p1", stats.get(b)) for b in S2_BAND_NAMES]
    if any(v is None for v in vals):
        return None
    return vals


def fit_convex(B, A, S):
    """B ~= alpha*A + (1-alpha)*S, alpha in [0,1], least squares."""
    A, S, B = map(np.asarray, (A, S, B))
    d = A - S
    denom = float(d @ d)
    if denom == 0:
        alpha = 0.0
    else:
        alpha = float((B - S) @ d / denom)
    alpha = min(1.0, max(0.0, alpha))
    fit = alpha * A + (1 - alpha) * S
    return alpha, fit


def fit_nnls(B, A, S):
    """B ~= alpha*A + beta*S, alpha,beta >= 0."""
    A, S, B = map(np.asarray, (A, S, B))
    M = np.column_stack([A, S])
    if np.allclose(S, 0):
        # Degenerate second column: reduces to scaling A.
        a = float(A @ B / (A @ A)) if A @ A else 0.0
        a = max(0.0, a)
        return (a, 0.0), a * A
    try:
        from scipy.optimize import nnls
        coef, _ = nnls(M, B)
    except Exception:
        coef, *_ = np.linalg.lstsq(M, B, rcond=None)
        coef = np.maximum(coef, 0.0)
    return (float(coef[0]), float(coef[1])), M @ coef


def residual_stats(B, fit):
    B = np.asarray(B)
    fit = np.asarray(fit)
    r = B - fit
    rn = float(np.linalg.norm(r))
    bn = float(np.linalg.norm(B))
    rel = rn / bn if bn else float("nan")
    angle = math.degrees(math.asin(min(1.0, rel)))
    return rel, angle, r


def verdict(rel):
    if rel <= NOT_DISTINCT_MAX:
        return "NOT a distinct material (B ~ A + shadow)"
    if rel >= DISTINCT_MIN:
        return "IS a distinct material"
    return "INDETERMINATE"


def run_aoi(label, aoi, cache_key):
    print(f"\n{'=' * 78}")
    print(f"[{label}]")
    print(f"{'=' * 78}")

    proj, proj_info = pure_diag.s2_grid_for(aoi)
    comp = get_sentinel2_median_composite_cached(aoi)
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

    shared, _ = sens.build_endmembers(composite, aoi, proj, proj_info,
                                      confident, paved_fc)
    A, n_a, _ = shared["A"]
    B, n_b, _ = shared["B"]
    if A is None or B is None:
        print("  cannot run -- A or B empty")
        return None

    print(f"  A (n={n_a}): {[round(v,4) for v in A]}")
    print(f"  B (n={n_b}): {[round(v,4) for v in B]}")
    print(f"  ||A||={np.linalg.norm(A):.4f}  ||B||={np.linalg.norm(B):.4f}")

    refs = []
    refs.append(("S1 photometric shade (zeros)", [0.0] * len(S2_BAND_NAMES), 0))

    scl, n_scl = scl_shadow_spectrum(aoi, proj_info)
    if scl:
        refs.append(("S2 SCL cloud-shadow (proxy)", scl, n_scl))
    else:
        print("  S2 SCL cloud-shadow: no SCL==3 pixels in window")

    dark = dark_object_spectrum(composite, aoi, proj_info)
    if dark:
        refs.append(("S3 dark-object p1", dark, 0))

    rows = []
    for name, S, n in refs:
        print(f"\n  --- shadow reference: {name}"
              + (f" (n={n})" if n else "") + " ---")
        print(f"      S = {[round(v,4) for v in S]}")

        alpha, fit_c = fit_convex(B, A, S)
        rel_c, ang_c, _ = residual_stats(B, fit_c)
        print(f"      convex  alpha={alpha:.3f}  "
              f"||r||/||B||={100*rel_c:.2f}%  ({ang_c:.2f} deg)  "
              f"-> {verdict(rel_c)}")

        (a, b), fit_n = fit_nnls(B, A, S)
        rel_n, ang_n, _ = residual_stats(B, fit_n)
        print(f"      nnls    a={a:.3f} b={b:.3f}  "
              f"||r||/||B||={100*rel_n:.2f}%  ({ang_n:.2f} deg)  "
              f"-> {verdict(rel_n)}")

        rows.append((label, name, alpha, rel_c, a, b, rel_n))

    return rows


_comp_cache = {}


def get_sentinel2_median_composite_cached(aoi):
    key = str(aoi.getInfo())
    if key not in _comp_cache:
        from ingestion.sentinel2 import get_sentinel2_median_composite
        _comp_cache[key] = get_sentinel2_median_composite(
            aoi, sens.START_DATE, sens.END_DATE)
    return _comp_cache[key]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", choices=["dharavi", "khayelitsha", "formal"])
    args = parser.parse_args()

    print(f"PRE-COMMITTED: not-distinct <= {100*NOT_DISTINCT_MAX:.0f}%, "
          f"distinct >= {100*DISTINCT_MIN:.0f}%, else indeterminate")

    cache_keys = {
        "Dharavi": "dharavi",
        "Khayelitsha (capetown run)": "khayelitsha",
        "Cape Town formal suburbs": "ct_formal",
    }

    all_rows = []
    for label, aoi in pure_diag.build_aois(args.aoi):
        r = run_aoi(label, aoi, cache_keys[label])
        if r:
            all_rows.extend(r)

    if all_rows:
        print("\n" + "=" * 104)
        print("B-DECOMPOSITION SUMMARY -- is B distinct from A+shadow?")
        print("=" * 104)
        print(f"{'AOI':<26} {'shadow ref':<30} {'alpha':>7} "
              f"{'conv %':>8} {'nnls %':>8}  verdict (nnls, most permissive)")
        print("-" * 104)
        for label, name, alpha, rel_c, a, b, rel_n in all_rows:
            print(f"{label:<26} {name:<30} {alpha:>7.3f} "
                  f"{100*rel_c:>7.2f}% {100*rel_n:>7.2f}%  {verdict(rel_n)}")
        print("=" * 104)


if __name__ == "__main__":
    main()
