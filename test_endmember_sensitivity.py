"""
Sensitivity test: does `built` endmember misspecification propagate into
`impervious_total`?

Why this test exists
--------------------
02_ARCHITECTURE.md (~L169) argues the built/paved weakness is safe:

    "Misallocation between `built` and `paved` leaves `impervious_total`
     unchanged -- the flood model, the primary consumer, is unaffected."

That argument is valid for a SWAP between two classes -- zero-sum, cancels in
the sum. But diagnose_pure_pixels.py measured a different failure: the only
buildings supplying pure 10m pixels are 4.66x-22.45x larger than the local
building population (Khayelitsha: 200 of 93,409, mean 1,057 m^2 vs 47.1 m^2).
So the endmember would be estimated from warehouse/institutional roofing and
applied to corrugated-metal shacks. That is an ABSOLUTE error in `built`, not
a swap, and `impervious_total = built + paved` would inherit it.

This script tests whether it actually does, by unmixing the same AOI and the
same composite twice, changing ONLY the `built` endmember:

  A  "institutional"  -- pure pixels inside LARGE buildings. This is what
                         Decision 13's spec, applied literally, produces.
  B  "informal proxy" -- high-coverage pixels that overlap NO building above
                         MIN_BIG_AREA_M2, i.e. pixels roofed entirely by
                         small adjacent structures. Dense informal roofing.

Both endmembers are extracted from the same image, on the same grid, by the
same reducer. The other four endmembers are held byte-identical across the two
runs, so every difference in output is attributable to `built` alone.

Control that makes the result interpretable
-------------------------------------------
If A and B are nearly the same spectrum, "impervious_total is stable" would be
trivially true and would prove nothing. So the spectral separation between A
and B (angle + Euclidean distance) is reported FIRST. A small separation
invalidates the test rather than passing it.

Scope note: shadow is not solved as a sixth term here. Decision 13 requires
that in the real product, but this is a difference test -- adding a free
photometric-shade term introduces a second thing that can absorb variation and
muddies attribution. A shade-included variant is reported as a robustness
check; the 5-endmember run is primary.

Usage:
    python test_endmember_sensitivity.py
    python test_endmember_sensitivity.py --aoi khayelitsha
"""

import argparse
import math

import diagnose_open_buildings_aoi as diag
import diagnose_pure_pixels as pure_diag
import diagnose_pure_pixels_paved as paved_diag
import ee
from ingestion.sentinel2 import S2_BAND_NAMES, get_sentinel2_median_composite

# The window the existing capetown_20260702_164022 run used, per its
# result.json date_range. Applied to all AOIs so that within each AOI both
# unmixing runs see byte-identical imagery.
START_DATE = "2026-04-03"
END_DATE = "2026-07-02"

# Endmember A: "large enough to be institutional/warehouse".
MIN_LARGE_AREA_M2 = 500
# Endmember B: pixels touching nothing bigger than this are informal-roofed.
MIN_BIG_AREA_M2 = 100

# Coverage thresholds tried in order when isolating informal-roof pixels.
# 1.0 is ideal; dense informal fabric may not supply enough, so fall back
# rather than compute an endmember from a handful of pixels.
INFORMAL_COVERAGE_STEPS = [0.999, 0.95, 0.90, 0.80]
MIN_ENDMEMBER_PIXELS = 30

FRACTION_NAMES = ["built", "paved", "vegetation", "water", "bare"]


def _reduce_kwargs(aoi, proj_info):
    return dict(geometry=aoi, crs=proj_info["crs"],
                crsTransform=proj_info["transform"], maxPixels=1e10)


def coverage_fraction(fc, proj):
    """Per-10m-pixel covered fraction for a polygon collection, on the real
    S2 grid. Same machinery as diagnose_pure_pixels, exposed as a fraction
    rather than thresholded."""
    fine = proj.atScale(pure_diag.SUBPIXEL_M)
    mask = ee.Image(0).byte().paint(fc, 1).reproject(fine)
    subcells = int((10 / pure_diag.SUBPIXEL_M) ** 2)
    return (mask.reduceResolution(ee.Reducer.mean(), maxPixels=subcells + 16)
                .reproject(proj))


def endmember_from_mask(composite, mask, aoi, proj_info, label):
    """Mean spectrum over masked pixels, plus the pixel count behind it."""
    stats = composite.updateMask(mask).reduceRegion(
        reducer=ee.Reducer.mean().combine(ee.Reducer.count(),
                                          sharedInputs=True),
        **_reduce_kwargs(aoi, proj_info)
    ).getInfo()

    n = stats.get(f"{S2_BAND_NAMES[0]}_count") or 0
    vals = [stats.get(f"{b}_mean") for b in S2_BAND_NAMES]
    if n == 0 or any(v is None for v in vals):
        return None, 0
    return vals, int(n)


def spectral_separation(a, b):
    """(angle in degrees, Euclidean distance) between two endmembers."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    cos = max(-1.0, min(1.0, dot / (na * nb))) if na and nb else 1.0
    angle = math.degrees(math.acos(cos))
    dist = math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    return angle, dist


def build_endmembers(composite, aoi, proj, proj_info, confident, paved_fc):
    """The two `built` candidates plus the four shared endmembers."""
    ndvi = composite.normalizedDifference(["NIR", "Red"]).rename("ndvi")
    mndwi = composite.normalizedDifference(["Green", "SWIR1"]).rename("mndwi")

    built_cov = coverage_fraction(confident, proj)
    paved_cov = (coverage_fraction(paved_fc, proj) if paved_fc is not None
                 else ee.Image(0))

    big = confident.filter(ee.Filter.gte("area_in_meters", MIN_BIG_AREA_M2))
    big_cov = coverage_fraction(big, proj)
    large = confident.filter(ee.Filter.gte("area_in_meters", MIN_LARGE_AREA_M2))
    large_cov = coverage_fraction(large, proj)

    built_any = built_cov.gt(0)
    paved_any = paved_cov.gt(0)

    out = {}

    # --- A: institutional / warehouse -------------------------------------
    mask_a = large_cov.gte(pure_diag.PURE_FRACTION_MIN)
    em_a, n_a = endmember_from_mask(composite, mask_a, aoi, proj_info, "A")
    out["A"] = (em_a, n_a, f"pure pixels inside buildings >= {MIN_LARGE_AREA_M2} m^2")

    # --- B: informal roofing proxy ----------------------------------------
    # Fully-roofed pixels that touch nothing big: roofed by small structures.
    em_b, n_b, used = None, 0, None
    for thresh in INFORMAL_COVERAGE_STEPS:
        mask_b = built_cov.gte(thresh).And(big_cov.eq(0))
        em_b, n_b = endmember_from_mask(composite, mask_b, aoi, proj_info, "B")
        used = thresh
        if n_b >= MIN_ENDMEMBER_PIXELS:
            break
    out["B"] = (em_b, n_b,
                f"coverage >= {used} by small structures only "
                f"(no building >= {MIN_BIG_AREA_M2} m^2)")

    # --- shared four ------------------------------------------------------
    unbuilt = built_any.Not().And(paved_any.Not())

    em_p, n_p = endmember_from_mask(
        composite, paved_cov.gte(pure_diag.PURE_FRACTION_MIN),
        aoi, proj_info, "paved")
    out["paved"] = (em_p, n_p, "pure pixels inside unroofed OSM polygons")

    em_v, n_v = endmember_from_mask(
        composite, ndvi.gte(0.5).And(unbuilt), aoi, proj_info, "veg")
    out["vegetation"] = (em_v, n_v, "NDVI >= 0.5, outside built/paved")

    em_w, n_w = endmember_from_mask(
        composite, mndwi.gte(0.3), aoi, proj_info, "water")
    out["water"] = (em_w, n_w, "MNDWI >= 0.3")

    em_bare, n_bare = endmember_from_mask(
        composite,
        ndvi.gte(0.02).And(ndvi.lte(0.20)).And(mndwi.lt(0.0)).And(unbuilt),
        aoi, proj_info, "bare")
    out["bare"] = (em_bare, n_bare, "NDVI 0.02-0.20, not water, outside built/paved")

    return out, built_any


def unmix_with(composite, built_em, shared, with_shade):
    """Fractions using `built_em`; every other endmember identical."""
    ems = [built_em, shared["paved"][0], shared["vegetation"][0],
           shared["water"][0], shared["bare"][0]]
    names = list(FRACTION_NAMES)
    if with_shade:
        ems = ems + [[0.0] * len(S2_BAND_NAMES)]
        names = names + ["shade"]

    frac = composite.unmix(ems, True, True).rename(names)

    if with_shade:
        # Decision 13/14: renormalize the five over the illuminated portion.
        illum = ee.Image(1).subtract(frac.select("shade")).max(1e-6)
        five = frac.select(FRACTION_NAMES).divide(illum)
        frac = five.addBands(frac.select("shade"))

    return frac


def compare(composite, shared, aoi, proj_info, built_any, with_shade):
    frac_a = unmix_with(composite, shared["A"][0], shared, with_shade)
    frac_b = unmix_with(composite, shared["B"][0], shared, with_shade)

    imp_a = frac_a.select("built").add(frac_a.select("paved")).rename("imp_a")
    imp_b = frac_b.select("built").add(frac_b.select("paved")).rename("imp_b")

    stack = ee.Image.cat(
        frac_a.select("built").rename("built_a"),
        frac_b.select("built").rename("built_b"),
        frac_a.select("paved").rename("paved_a"),
        frac_b.select("paved").rename("paved_b"),
        imp_a, imp_b,
        imp_b.subtract(imp_a).rename("d_imp"),
        imp_b.subtract(imp_a).abs().rename("abs_d_imp"),
        frac_b.select("built").subtract(frac_a.select("built")).rename("d_built"),
    )

    # Separate reducers rather than one combined call: EE's combine() renames
    # outputs (band_mean / band_stdDev / band_p5), and reading those names
    # back is more fragile than just issuing the reductions independently.
    kw = _reduce_kwargs(aoi, proj_info)
    aoi_stats = stack.reduceRegion(reducer=ee.Reducer.mean(), **kw).getInfo()

    spread = stack.select(["d_imp", "d_built"])
    sd = spread.reduceRegion(reducer=ee.Reducer.stdDev(), **kw).getInfo()
    pct = spread.reduceRegion(
        reducer=ee.Reducer.percentile([5, 50, 95]), **kw).getInfo()

    aoi_stats["sd_d_imp"] = sd.get("d_imp")
    aoi_stats["sd_d_built"] = sd.get("d_built")
    for k, v in pct.items():
        aoi_stats[k] = v

    built_stats = stack.updateMask(built_any).reduceRegion(
        reducer=ee.Reducer.mean(), **kw).getInfo()

    return aoi_stats, built_stats


def run_aoi(label, aoi, cache_key):
    print(f"\n{'=' * 78}")
    print(f"[{label}]")
    print(f"{'=' * 78}")

    proj, proj_info = pure_diag.s2_grid_for(aoi)
    print(f"  S2 grid: {proj_info.get('crs')} {proj_info.get('transform')}")

    comp = get_sentinel2_median_composite(aoi, START_DATE, END_DATE)
    composite = comp["image"]
    print(f"  composite: {comp['provenance']['source_image_count']} images, "
          f"{START_DATE} to {END_DATE}, median, SCL-masked")

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

    print("  extracting endmembers...", flush=True)
    shared, built_any = build_endmembers(composite, aoi, proj, proj_info,
                                         confident, paved_fc)

    for key in ["A", "B", "paved", "vegetation", "water", "bare"]:
        em, n, how = shared[key]
        if em is None:
            print(f"    {key:<11} FAILED -- no pixels ({how})")
        else:
            print(f"    {key:<11} n={n:<7} {how}")
            print(f"                {[round(v, 4) for v in em]}")

    if shared["A"][0] is None or shared["B"][0] is None:
        print("  Cannot run: one of the two built endmembers is empty.")
        return None
    for key in ["paved", "vegetation", "water", "bare"]:
        if shared[key][0] is None:
            print(f"  Cannot run: shared endmember '{key}' is empty.")
            return None

    angle, dist = spectral_separation(shared["A"][0], shared["B"][0])
    print(f"\n  CONTROL -- separation between built endmembers A and B:")
    print(f"    spectral angle : {angle:.2f} deg")
    print(f"    euclidean dist : {dist:.4f} reflectance units")
    if angle < 2.0:
        print("    *** A and B are nearly identical. A 'stable' result below")
        print("        would be uninformative, not reassuring.")

    # How separable is each `built` candidate from `paved`? If a built
    # endmember sits nearly on top of the paved endmember, the two columns of
    # the mixing matrix are near-collinear and the built/paved split is
    # unidentifiable regardless of solver -- which is a different and worse
    # problem than the split merely being noisy.
    ang_ap, dist_ap = spectral_separation(shared["A"][0], shared["paved"][0])
    ang_bp, dist_bp = spectral_separation(shared["B"][0], shared["paved"][0])
    print(f"  CONTROL -- separation from the `paved` endmember:")
    print(f"    A vs paved : {ang_ap:.2f} deg, dist {dist_ap:.4f}")
    print(f"    B vs paved : {ang_bp:.2f} deg, dist {dist_bp:.4f}")
    if ang_bp < 1.5:
        print("    *** B and paved are near-collinear: with a realistic")
        print("        informal-roof endmember, built vs paved is not")
        print("        identifiable at all, not merely low-confidence.")

    results = {}
    for with_shade in (False, True):
        tag = "with shade" if with_shade else "5-endmember"
        print(f"\n  --- unmixing ({tag}) ---", flush=True)
        aoi_stats, built_stats = compare(composite, shared, aoi, proj_info,
                                         built_any, with_shade)
        results[tag] = (aoi_stats, built_stats)

        print(f"    AOI-level mean fractions:")
        print(f"      built       A={aoi_stats['built_a']:.4f}  "
              f"B={aoi_stats['built_b']:.4f}  "
              f"delta={aoi_stats['built_b']-aoi_stats['built_a']:+.4f}")
        print(f"      paved       A={aoi_stats['paved_a']:.4f}  "
              f"B={aoi_stats['paved_b']:.4f}  "
              f"delta={aoi_stats['paved_b']-aoi_stats['paved_a']:+.4f}")
        print(f"      impervious  A={aoi_stats['imp_a']:.4f}  "
              f"B={aoi_stats['imp_b']:.4f}  "
              f"delta={aoi_stats['d_imp']:+.4f} "
              f"({100*aoi_stats['d_imp']/max(aoi_stats['imp_a'],1e-9):+.1f}% relative)")
        print(f"    pixel-level impervious difference:")
        print(f"      mean |d|    {aoi_stats['abs_d_imp']:.4f}")
        print(f"      sd(d)       {aoi_stats['sd_d_imp']:.4f}")
        print(f"      d p5/50/95  {aoi_stats['d_imp_p5']:+.4f} / "
              f"{aoi_stats['d_imp_p50']:+.4f} / {aoi_stats['d_imp_p95']:+.4f}")
        print(f"    over built-overlapping pixels only:")
        print(f"      impervious  A={built_stats['imp_a']:.4f}  "
              f"B={built_stats['imp_b']:.4f}  "
              f"delta={built_stats['imp_b']-built_stats['imp_a']:+.4f}")

    return {"label": label, "angle": angle, "dist": dist, "results": results}


def print_summary(rows):
    print("\n" + "=" * 104)
    print("ENDMEMBER SENSITIVITY -- does built-endmember error reach "
          "impervious_total?  (5-endmember run)")
    print("=" * 104)
    print(f"{'AOI':<28} {'A-B angle':>10} {'built dA':>10} {'paved dA':>10} "
          f"{'imp delta':>11} {'imp rel':>9} {'mean|d|':>9}")
    print("-" * 104)
    for r in rows:
        s = r["results"]["5-endmember"][0]
        rel = 100 * s["d_imp"] / max(s["imp_a"], 1e-9)
        print(f"{r['label']:<28} {r['angle']:>9.2f}d "
              f"{s['built_b']-s['built_a']:>+10.4f} "
              f"{s['paved_b']-s['paved_a']:>+10.4f} "
              f"{s['d_imp']:>+11.4f} {rel:>+8.1f}% {s['abs_d_imp']:>9.4f}")
    print("=" * 104)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aoi", choices=["dharavi", "khayelitsha", "formal"])
    args = parser.parse_args()

    cache_keys = {
        "Dharavi": "dharavi",
        "Khayelitsha (capetown run)": "khayelitsha",
        "Cape Town formal suburbs": "ct_formal",
    }

    rows = []
    for label, aoi in pure_diag.build_aois(args.aoi):
        r = run_aoi(label, aoi, cache_keys[label])
        if r:
            rows.append(r)

    if len(rows) > 1:
        print_summary(rows)


if __name__ == "__main__":
    main()
