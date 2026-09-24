"""
How many pure pixels does a `paved` endmember actually need, and how far do you
have to reach to get them?

Item 21's spec says the impervious endmember is drawn from wide unroofed OSM
polygons, and the C44 end-to-end run surfaced the problem this script measures:
Dharavi yielded 5 such polygons across 4.68 km^2. That prompted "draw from a
wider region" -- but "wider" was a guess. Two numbers were missing:

  1. THE STABILITY THRESHOLD. At what sample count does the endmember stop
     moving? Below it you are reading noise; above it you are paying for
     samples that change nothing.

  2. WHAT "BUFFERED" MEANS IN METRES. How far do you have to expand the draw
     radius before you clear that threshold -- and does the endmember drift as
     you reach further, because a parking lot 20 km away is a different
     surface?

METHOD -- and why it is bootstrap spread, not a nested sequence

The naive test walks n upward on one nested sample and watches successive
endmembers converge. That understates instability badly: endmember(n) and
endmember(n+1) share n of their pixels, so they are correlated by construction
and look stable long before they are.

The question that matters is repeatability: *if I had drawn a different n
pixels, how different would my endmember be?* So for each n this draws B
INDEPENDENT subsamples of size n, computes each one's mean spectrum, and
measures the spectral angle between independent pairs. The nested-sequence
number is reported too, purely to show how much it flatters the result.

THE STABILITY CRITERION IS NOT AN EYEBALLED ELBOW

`06_UNMIXING_CEILING.md` measured Sentinel-2 L2A BOA uncertainty at ~0.005
reflectance, which is **~0.7 degrees** of spectral angle at these magnitudes.
An endmember whose between-draw spread is under that is stable in the only
sense that matters: the remaining variation is smaller than the sensor's own
uncertainty, so no further sampling can resolve it. That is the threshold
used throughout, and it is inherited from a measurement rather than chosen.

For scale: built-vs-paved separation is 1.70 deg, i.e. 2.4x the noise floor.
An endmember carrying >=1.70 deg of sampling noise cannot support the very
distinction the fraction architecture needs, so that is flagged as a second,
harder bar.

Usage:
    python diagnose_endmember_stability.py                 # all AOIs
    python diagnose_endmember_stability.py --aoi dharavi
    python diagnose_endmember_stability.py --skip-buffer   # part A only
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

import numpy as np

from ingestion.gee_client import initialize_gee

initialize_gee()

import ee  # noqa: E402

import diagnose_open_buildings_aoi as diag        # noqa: E402
import diagnose_pure_pixels as pure_diag          # noqa: E402
import diagnose_pure_pixels_paved as paved_diag   # noqa: E402

OUT_DIR = os.path.join("experiments", "endmember_stability", "results")
BANDS = ["Blue", "Green", "Red", "NIR", "SWIR1", "SWIR2"]
S2_SRC_BANDS = ["B2", "B3", "B4", "B8", "B11", "B12"]

START_DATE, END_DATE = "2023-01-01", "2023-12-31"
CLOUD_PCT = 20

NOISE_FLOOR_DEG = 0.7     # 06_UNMIXING_CEILING.md: ~0.005 reflectance BOA uncertainty
BUILT_PAVED_DEG = 1.70    # the separation the endmember has to support

N_GRID = [3, 5, 8, 12, 15, 20, 25, 30, 40, 50, 75, 100]
N_BOOT = 300              # independent draws per n
BUFFER_KM = [0, 1, 2, 5, 10]

RNG = np.random.default_rng(1337)


# ---------------------------------------------------------------- spectra ---

def spectral_angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return float("nan")
    c = float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))
    return math.degrees(math.acos(c))


def composite_for(aoi):
    """6-band BOA reflectance median composite -- the same recipe the pipeline
    uses (SCL cloud mask, /10000), so these spectra are what unmixing sees."""
    from ingestion.sentinel2 import get_sentinel2_collection, mask_s2_clouds
    coll = get_sentinel2_collection(aoi, START_DATE, END_DATE, CLOUD_PCT)
    return coll.map(mask_s2_clouds).median().select(BANDS)


def fetch_paved_fc(region, cache_key):
    """Overpass -> ee.FeatureCollection of unroofed paved polygons over `region`."""
    b = region.bounds().coordinates().get(0).getInfo()
    lons = [p[0] for p in b]
    lats = [p[1] for p in b]
    elements, unavailable = paved_diag.overpass_paved(
        min(lons), min(lats), max(lons), max(lats), cache_key)
    fc, n_poly = paved_diag.to_feature_collection(elements)
    return fc, n_poly, unavailable


def spectra_from_fc(aoi, fc, n_poly, max_px=3000):
    """Reflectance at every pure (fully paved-covered) 10 m pixel in `aoi`."""
    if n_poly == 0:
        return np.empty((0, len(BANDS)))
    proj, proj_info = pure_diag.s2_grid_for(aoi)
    _, pure, _ = pure_diag.pure_pixel_images(fc, proj)

    img = composite_for(aoi).updateMask(pure)
    # NOT numPixels=: that draws N pixels at RANDOM from the whole region and
    # only then drops the masked ones, so at Dharavi's pure-pixel density
    # (~0.13% of the AOI) a 3,000-pixel draw returned 2 usable spectra out of
    # 62 that exist. Sampling the masked image exhaustively returns every pure
    # pixel and nothing else; the cap is applied after, not before.
    samples = img.sample(region=aoi, projection=proj, scale=10,
                         dropNulls=True, geometries=False,
                         tileScale=4).limit(max_px)
    rows = samples.toList(max_px).getInfo()
    return np.array([[r["properties"][b_] for b_ in BANDS] for r in rows
                     if all(r["properties"].get(b_) is not None for b_ in BANDS)],
                    dtype=float)


def pure_paved_spectra(aoi, cache_key, max_px=3000):
    """Convenience wrapper: fetch + extract for a single region."""
    fc, n_poly, unavailable = fetch_paved_fc(aoi, cache_key)
    return spectra_from_fc(aoi, fc, n_poly, max_px), n_poly, unavailable


# ------------------------------------------------- part A: sample stability --

def bootstrap_stability(spectra: np.ndarray):
    """For each n: spread between INDEPENDENT draws, and the (flattering)
    nested-sequence delta, both in degrees."""
    N = len(spectra)
    rows = []
    order = RNG.permutation(N)           # one fixed order for the nested arm
    prev_nested = None
    for n in N_GRID:
        if n * 2 > N:                    # need two disjoint draws of size n
            break
        angles = []
        for _ in range(N_BOOT):
            idx = RNG.permutation(N)
            a = spectra[idx[:n]].mean(axis=0)
            b = spectra[idx[n:2 * n]].mean(axis=0)
            angles.append(spectral_angle_deg(a, b))
        angles = np.array([a for a in angles if not np.isnan(a)])

        nested = spectra[order[:n]].mean(axis=0)
        nested_delta = (spectral_angle_deg(prev_nested, nested)
                        if prev_nested is not None else float("nan"))
        prev_nested = nested

        rows.append(dict(n=n,
                         median=float(np.median(angles)),
                         p90=float(np.percentile(angles, 90)),
                         mean=float(angles.mean()),
                         nested_delta=float(nested_delta)))
    return rows


def project_threshold(rows, bar, key="p90"):
    """Where the curve WOULD cross `bar`, by fitting spread ~ C * n^k.

    Sampling error on a mean falls as 1/sqrt(n), so k should come out near
    -0.5; the fit reports it so a curve that is NOT behaving like sampling
    noise is visible rather than silently extrapolated. Most AOIs run out of
    local pure pixels long before they reach the floor, so without this the
    honest answer for them is just "unknown", which is less useful than a
    projection carrying its own exponent.
    """
    pts = [(r["n"], r[key]) for r in rows if r[key] > 0]
    if len(pts) < 3:
        return None, None
    x = np.log(np.array([p[0] for p in pts], dtype=float))
    y = np.log(np.array([p[1] for p in pts], dtype=float))
    k, logC = np.polyfit(x, y, 1)
    n_hat = math.exp((math.log(bar) - logC) / k)
    return int(round(n_hat)), float(k)


def threshold_from(rows, bar=NOISE_FLOOR_DEG, key="p90"):
    """Smallest n whose spread is under `bar` and stays under it."""
    for i, r in enumerate(rows):
        if r[key] < bar and all(x[key] < bar for x in rows[i:]):
            return r["n"]
    return None


# --------------------------------------------------- part B: buffer radius --

def _save_partial(label, key, value):
    """Merge one field into this AOI's record on disk, immediately."""
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "stability.json")
    data = []
    if os.path.exists(path):
        try:
            with open(path) as fh:
                data = json.load(fh)
        except Exception:
            data = []
    rec = next((r for r in data if r["label"] == label), None)
    if rec is None:
        rec = {"label": label}
        data.append(rec)
    rec[key] = value
    with open(path, "w") as fh:
        json.dump(data, fh, indent=1)


def buffer_sweep(aoi, cache_key, label, n_star, local_endmember):
    """Expand the draw radius; report sample count and drift from AOI-local.

    Overpass is queried ONCE, at the widest radius, and each smaller radius is
    a server-side subset of that one collection. The first version re-queried
    every radius from scratch -- up to 7 radii x 7 tag clauses per AOI, all
    re-fetching polygons already in hand, against endpoints that rate-limit.
    """
    widest = max(BUFFER_KM)
    outer = aoi.buffer(widest * 1000)
    print(f"    fetching paved polygons once at {widest} km ...", flush=True)
    try:
        fc_all, n_all, _ = fetch_paved_fc(outer, f"{cache_key}__buf{widest}km")
    except Exception as e:
        print(f"    outer fetch FAILED ({type(e).__name__}: {str(e)[:70]})")
        return []
    print(f"    {n_all} polygons in the {widest} km envelope", flush=True)

    out = []
    for km in BUFFER_KM:
        region = aoi if km == 0 else aoi.buffer(km * 1000)
        try:
            sub = fc_all.filterBounds(region)
            n_poly = sub.size().getInfo()
            spec = spectra_from_fc(region, sub, n_poly)
        except Exception as e:
            print(f"    buffer {km:>4} km: FAILED ({type(e).__name__}: {str(e)[:60]})")
            out.append(dict(km=km, n_pure=None, n_poly=None, drift=None))
            continue
        drift = (spectral_angle_deg(local_endmember, spec.mean(axis=0))
                 if len(spec) and local_endmember is not None else float("nan"))
        clears = (n_star is not None and len(spec) >= n_star)
        print(f"    buffer {km:>4} km: {n_poly:>5} polys, {len(spec):>5} pure px, "
              f"drift {drift:5.2f} deg  {'<- CLEARS n*' if clears else ''}", flush=True)
        out.append(dict(km=km, n_pure=int(len(spec)), n_poly=int(n_poly),
                        drift=None if np.isnan(drift) else float(drift)))
        _save_partial(label, "buffer", out)     # survive an interrupted run
    return out


# ------------------------------------------------------------------- main ---

def run_aoi(label, aoi, cache_key, skip_buffer=False):
    print(f"\n{'='*92}\n[{label}]\n{'='*92}")
    area = aoi.area(1).getInfo() / 1e6
    spec, n_poly, unavailable = pure_paved_spectra(aoi, cache_key)
    print(f"  AOI {area:.2f} km^2 | {n_poly} paved polygons | {len(spec)} pure pixels"
          + (f" | {len(unavailable)} tag(s) unavailable" if unavailable else ""))
    if len(spec) < 6:
        print("  too few pure pixels to test stability locally -- buffer is mandatory here")
        rows, n_star, local_em = [], None, (spec.mean(axis=0) if len(spec) else None)
    else:
        rows = bootstrap_stability(spec)
        n_star = threshold_from(rows)
        n_hard = threshold_from(rows, bar=BUILT_PAVED_DEG)
        local_em = spec.mean(axis=0)
        print(f"\n  {'n':>5}{'median':>9}{'p90':>9}{'mean':>9}{'nested d':>10}   (degrees)")
        for r in rows:
            flag = ""
            if r["p90"] < NOISE_FLOOR_DEG: flag = " <- under noise floor"
            elif r["p90"] < BUILT_PAVED_DEG: flag = " <- under built/paved sep"
            nd = "-" if np.isnan(r["nested_delta"]) else f"{r['nested_delta']:.2f}"
            print(f"  {r['n']:>5}{r['median']:>9.2f}{r['p90']:>9.2f}"
                  f"{r['mean']:>9.2f}{nd:>10}{flag}")
        proj_floor, k = project_threshold(rows, NOISE_FLOOR_DEG)
        proj_sep, _ = project_threshold(rows, BUILT_PAVED_DEG)
        print(f"\n  n* (p90 < {NOISE_FLOOR_DEG} deg noise floor)      : "
              f"{n_star if n_star else f'NOT REACHED locally -- projected ~{proj_floor}'}")
        print(f"  n  (p90 < {BUILT_PAVED_DEG} deg built/paved sep) : "
              f"{n_hard if n_hard else f'NOT REACHED locally -- projected ~{proj_sep}'}")
        print(f"  fitted exponent k = {k:.2f}  (-0.50 = pure sampling noise)")
        n_star = n_star or proj_floor
        _save_partial(label, "curve", rows)
        _save_partial(label, "n_star", n_star)
        _save_partial(label, "fit_k", k)
        _save_partial(label, "n_pure", int(len(spec)))
        _save_partial(label, "n_poly", int(n_poly))
        _save_partial(label, "local_endmember", local_em.tolist())

    buf = []
    if not skip_buffer:
        print(f"\n  buffer sweep (target n* = {n_star}):")
        buf = buffer_sweep(aoi, cache_key, label, n_star, local_em)

    return dict(label=label, area_km2=area, n_poly=n_poly, n_pure=int(len(spec)),
                curve=rows, n_star=n_star,
                n_star_observed=threshold_from(rows) if rows else None,
                fit_k=(project_threshold(rows, NOISE_FLOOR_DEG)[1] if rows else None),
                buffer=buf,
                local_endmember=(local_em.tolist() if local_em is not None else None))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aoi", choices=["dharavi", "khayelitsha", "formal", "jakarta"])
    ap.add_argument("--skip-buffer", action="store_true")
    args = ap.parse_args()

    targets = []
    if args.aoi in (None, "dharavi"):
        targets.append(("Dharavi (sparse informal)",
                        ee.Geometry.Rectangle(diag.DHARAVI_BOUNDS), "dharavi"))
    if args.aoi in (None, "khayelitsha"):
        ct_bounds, _ = diag.aoi_bounds_from_run("capetown")
        targets.append(("Khayelitsha (informal)",
                        ee.Geometry.Rectangle(list(ct_bounds)), "khayelitsha"))
    if args.aoi in (None, "formal"):
        targets.append(("Cape Town formal (suburban)",
                        ee.Geometry.Rectangle(pure_diag.FORMAL_CT_BBOX), "ct_formal"))
    if args.aoi in (None, "jakarta"):
        jk_bounds, _ = diag.aoi_bounds_from_run("jakarta")
        targets.append(("Jakarta (dense mixed urban)",
                        ee.Geometry.Rectangle(list(jk_bounds)), "jakarta"))

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "stability.json")
    results = []
    if os.path.exists(out_path):
        with open(out_path) as fh:
            results = json.load(fh)
    done = {r["label"] for r in results if r.get("buffer")}
    for label, aoi, key in targets:
        if label in done:
            print(f"[{label}] cached -- skipping")
            continue
        try:
            results.append(run_aoi(label, aoi, key, args.skip_buffer))
        except Exception as e:
            print(f"  [{label}] FAILED: {type(e).__name__}: {str(e)[:160]}")
        seen=set(); dedup=[]
        for r in reversed(results):
            if r["label"] in seen: continue
            seen.add(r["label"]); dedup.append(r)
        with open(out_path, "w") as fh:
            json.dump(list(reversed(dedup)), fh, indent=1)
    print(f"\nwrote {OUT_DIR}/stability.json ({len(results)} AOIs)")


if __name__ == "__main__":
    main()
