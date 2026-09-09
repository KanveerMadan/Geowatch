"""
Item 21 Phase 0, part 2 -- co-registration check, label raster, and the
regression of S2 reflectance against a VHR-derived impervious fraction.

SITE-PARAMETERISED, like `build_vhr_impervious_label.py`: the site comes from
`vhr_sites.SITES` via GW_SITE and defaults to `oldfadama`. Read that module's
docstring for the re-run's pre-registration, and read the label builder's for
how the label is made and what its measured accuracy is.

WHAT LABEL NOISE MEANS FOR EVERY NUMBER BELOW, stated before running
---------------------------------------------------------------------
A noisy label caps what any regression can score against it. If the label
carries independent error, the best attainable R2 against the LABEL is bounded
by the share of the label's variance that is real signal rather than label
noise. So the R2 reported here is a LOWER BOUND on the true reflectance-to-
impervious relationship, not an estimate of it:

  * a PASS would be strong evidence, because it is achieved despite the noise
  * a MISS is CONFOUNDED -- it cannot distinguish "reflectance does not predict
    impervious" from "the label is too noisy to tell", and must not be reported
    as though it settles the question

This asymmetry is stated up front so a miss is not later spun as a finding. It
is also why the Accra run could not close item 21, and why the re-run's whole
point is to raise the label's own accuracy and the target's dynamic range
before re-testing. Those two de-confounding conditions are pre-registered in
`vhr_sites` as LABEL_ACC_MIN / TARGET_P50_MAX / TARGET_SD_MIN, are checked
below, and constrain the INTERPRETATION rather than the verdict.

PRE-REGISTERED BAR, unchanged from the Accra run
--------------------------------------------------
  R2 >= 0.60   -> impervious_total works, item 21 closes
  0.50 - 0.60  -> usable, ships with a prominent confidence caveat
  R2 <  0.50   -> does not work at 10 m per-pixel; go coarser or drop the
                  fraction product

SPLIT: spatially blocked, NOT random. Only one AOI is available per site, so
leave-one-AOI-out is impossible within a site; instead the scene is divided
into a coarse checkerboard of BLOCK_M-metre blocks and alternating blocks form
train/test. A random split inside one city is optimistic for exactly the reason
A.13 gives, and would inflate this number. Cross-SITE transfer is a separate
script, since two labelled sites now exist.

CO-REGISTRATION: the VHR raster is 0.05-0.30 m and the S2 grid is 10 m, so a
misalignment of one S2 cell is 33-200 VHR pixels and would decorrelate the
label from the imagery. Alignment is MEASURED, not assumed.

RECORDED DEVIATIONS FROM THE ACCRA RUN
=======================================
1. HARD TIMEOUT ON EVERY EE CALL (`ee_timeout.call`). Two composite requests
   during site recon hung for 80 minutes and returned nothing. Every EE request
   here now runs on a daemon thread with a 120 s deadline and is retried on a
   fresh thread rather than being allowed to block indefinitely.

2. THE COMPOSITE IS BUILT WITHOUT `compute_observation_quality`. That helper is
   what hung: it runs several AOI-wide `reduceRegion().getInfo()` calls across
   the whole collection. It produces REPORTING metadata that this regression
   never consumes. The composite IMAGE is assembled from the same pieces the
   library function uses -- `get_sentinel2_collection` -> `mask_s2_clouds` ->
   `.median().clip(aoi)` -- so the pixels are identical; only the provenance
   count and quality dict are skipped, and the image count is fetched
   separately under its own timeout purely for the log.

3. S2 IS FETCHED AS AN ARRAY, NOT POINT-SAMPLED. Accra point-sampled 13,090
   cells through `reduceRegions` in chunks. The Nairobi extent has ~60,000
   cells, which would be ~15 chunked round trips. `computePixels` returns the
   whole grid in one request on the SAME crs and crsTransform, so the semantics
   are identical. That claim is VERIFIED, not assumed: EQUIV_N random cells are
   re-fetched through the old `reduceRegions` path and compared against the
   array, and the run aborts if they disagree by more than EQUIV_MAX_ABS_DIFF.

Usage:
    GW_SITE=kibera python test_vhr_impervious_regression.py
"""

import json
import os
import pickle
import time

import numpy as np
import rasterio
from rasterio.windows import Window
from sklearn.metrics import mean_absolute_error, r2_score

import build_vhr_impervious_label as B
import diagnose_pure_pixels as pure_diag
import ee
import regress_built_fraction as base
import vhr_sites
from ee_timeout import call as ee_call
from ingestion.sentinel2 import (S2_BAND_NAMES, get_sentinel2_collection,
                                 mask_s2_clouds)

# --- pre-registered; not edited after seeing results ---------------------
WORKS_R2 = 0.60
CAVEAT_R2 = 0.50
BLOCK_M = 200          # checkerboard block size for the spatial split
MAX_SHIFT = 4          # +/- cells searched in the co-registration check
MIN_VALID_FRAC = 0.60  # a 10 m cell needs this much valid VHR coverage
# equivalence of the computePixels path against the Accra reduceRegions path
EQUIV_N = 300              # cells re-fetched the old way
EQUIV_MAX_ABS_DIFF = 1e-4  # in reflectance units; larger => abort
# Resource limits -- NOT results parameters. The first Nairobi attempt drove the
# machine into swap (13.3 GB of 14.3 GB) and stalled in uninterruptible I/O
# after 2 of 8 blocks. These bound peak memory; they change runtime only.
LABEL_BLOCK_ROWS = 256     # rows of working-res imagery per block
RF_PREDICT_JOBS = 4        # joblib workers for the label classifier
# -------------------------------------------------------------------------

SITE = B.SITE
SCRATCH = B.SCRATCH
EE_TIMEOUT = 120


def s2_grid(aoi):
    proj, info = pure_diag.s2_grid_for(aoi)
    return proj, info


def build_composite(aoi):
    """The S2 median composite, without the AOI-wide quality reductions.

    Deviation 2 in the module docstring: identical pixels to
    `get_sentinel2_median_composite`, minus the metadata that hung.
    """
    coll = ee_call(lambda: get_sentinel2_collection(aoi, SITE["s2_start"],
                                                    SITE["s2_end"]),
                   timeout=EE_TIMEOUT, label="s2 collection")
    image = coll.map(mask_s2_clouds).median().clip(aoi)
    try:
        n = ee_call(lambda: coll.size().getInfo(), timeout=EE_TIMEOUT,
                    retries=2, label="s2 image count")
    except Exception as e:                                   # noqa: BLE001
        n = f"unavailable ({type(e).__name__})"
    return image, n


def build_label_raster(s2_tr, force=False):
    """Per-10m-cell class fractions from the VHR classifier."""
    out = os.path.join(SCRATCH, f"vhr_label_fractions_{SITE['key']}.npz")
    if os.path.exists(out) and not force:
        d = np.load(out)
        print("  (cached label raster)")
        return {k: d[k] for k in d.files}

    with open(os.path.join(SCRATCH, f"vhr_clf_{SITE['key']}.pkl"), "rb") as fh:
        clf = pickle.load(fh)
    # The classifier was pickled with n_jobs=-1. At DS=1 a wide block is ~470 MB
    # of float32 features, and joblib fans that out to one worker per core,
    # which is what drove this machine into swap on the first attempt. Cap it.
    clf.n_jobs = RF_PREDICT_JOBS
    nclass = len(B.CLASSES)

    with rasterio.open(B.UAV) as src:
        assert str(src.crs).endswith(SITE["epsg"].split(":")[1]), src.crs
        x0, px = s2_tr[2], s2_tr[0]
        y0, py = s2_tr[5], s2_tr[4]
        ut = src.transform
        H = src.height // B.DS
        W = src.width // B.DS

        bl, bb, br, bt = src.bounds
        c_lo = int(np.floor((bl - x0) / px)) - 1
        c_hi = int(np.ceil((br - x0) / px)) + 1
        r_lo = int(np.floor((bt - y0) / py)) - 1
        r_hi = int(np.ceil((bb - y0) / py)) + 1
        nR, nC = r_hi - r_lo, c_hi - c_lo
        ncell = nR * nC
        print(f"  S2 label grid: {nR} x {nC} cells")

        counts = np.zeros((nclass, ncell), np.int64)
        valid = np.zeros(ncell, np.int64)
        total = np.zeros(ncell, np.int64)

        # Column -> S2 cell index is the same for every row, so hoist it.
        xcol = ut[2] + (np.arange(W) + 0.5) * B.DS * ut[0]
        ccol = (np.floor((xcol - x0) / px).astype(np.int32) - c_lo)

        BLK = LABEL_BLOCK_ROWS
        t_start = time.time()
        for r0 in range(0, H, BLK):
            nrows = min(BLK, H - r0)
            arr = src.read(window=Window(0, r0 * B.DS, src.width,
                                         nrows * B.DS),
                           out_shape=(3, nrows, W))
            rgb = np.transpose(arr, (1, 2, 0)).astype(np.float32)
            del arr
            good = rgb.sum(2) > 0
            F = B.features(rgb).reshape(-1, B.NFEAT)
            del rgb
            pred = np.full(len(F), -1, np.int8)
            gflat = good.reshape(-1)
            if gflat.any():
                pred[gflat] = clf.predict(F[gflat]).astype(np.int8)
            del F

            yrow = ut[5] + (r0 + np.arange(nrows) + 0.5) * B.DS * ut[4]
            rrow = (np.floor((yrow - y0) / py).astype(np.int32) - r_lo)
            rr = np.repeat(rrow, W)
            cc = np.tile(ccol, nrows)
            ok = (rr >= 0) & (rr < nR) & (cc >= 0) & (cc < nC)
            flat_idx = (rr[ok].astype(np.int64) * nC + cc[ok])
            del rr, cc

            # bincount, not np.add.at: same result, far cheaper. np.add.at is
            # an unbuffered ufunc and was a second driver of the stall.
            total += np.bincount(flat_idx, minlength=ncell)
            p = pred.reshape(-1)[ok]
            g = gflat[ok]
            valid += np.bincount(flat_idx[g], minlength=ncell)
            for k in range(nclass):
                sel = g & (p == k)
                if sel.any():
                    counts[k] += np.bincount(flat_idx[sel], minlength=ncell)
            del pred, p, g, ok, flat_idx, good, gflat

            done = min(r0 + nrows, H)
            el = time.time() - t_start
            print(f"    rows {done}/{H}  {el:.0f}s elapsed, "
                  f"~{el / done * (H - done):.0f}s left", flush=True)

    counts = counts.reshape(nclass, nR, nC).astype(np.int32)
    valid = valid.reshape(nR, nC).astype(np.int32)
    total = total.reshape(nR, nC).astype(np.int32)
    res = {"counts": counts, "valid": valid, "total": total,
           "r_lo": np.array([r_lo]), "c_lo": np.array([c_lo])}
    np.savez_compressed(out, **res)
    return res


def fetch_s2_array(image, crs, tr, r_lo, c_lo, nR, nC):
    """Whole label grid in ONE computePixels request, on the S2 grid itself."""
    bands = list(S2_BAND_NAMES)
    img = image.select(bands).addBands(
        image.select(bands[0]).mask().rename("valid_mask"))
    req = {
        "expression": img,
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {
            "dimensions": {"width": int(nC), "height": int(nR)},
            "affineTransform": {
                "scaleX": tr[0], "shearX": tr[1],
                "translateX": tr[2] + c_lo * tr[0],
                "shearY": tr[3], "scaleY": tr[4],
                "translateY": tr[5] + r_lo * tr[4],
            },
            "crsCode": crs,
        },
    }
    arr = ee_call(lambda: ee.data.computePixels(req), timeout=EE_TIMEOUT,
                  label="computePixels")
    stack = np.stack([arr[b].astype(np.float64) for b in bands], axis=-1)
    mask = arr["valid_mask"] > 0
    return stack, mask


def verify_equivalence(image, crs, tr, r_lo, c_lo, rr, cc, stack, rng):
    """Re-fetch EQUIV_N cells the Accra way and check they match the array.

    Deviation 3: this is the check that makes the faster path usable, and it
    aborts rather than warns, because a silent grid mismatch would corrupt
    every number downstream. An earlier Accra bug of exactly this shape --
    passing an ee.Projection with a crsTransform to Geometry.Point -- silently
    placed every sample outside the scene and matched 0 cells.
    """
    k = min(EQUIV_N, len(rr))
    sel = rng.choice(len(rr), k, replace=False)
    feats = []
    for i in sel:
        r, c = int(rr[i]), int(cc[i])
        x = tr[2] + (c + c_lo + 0.5) * tr[0]
        y = tr[5] + (r + r_lo + 0.5) * tr[4]
        feats.append(ee.Feature(ee.Geometry.Point([float(x), float(y)], crs),
                                {"i": int(i)}))
    samp = image.select(list(S2_BAND_NAMES)).reduceRegions(
        collection=ee.FeatureCollection(feats),
        reducer=ee.Reducer.first(), crs=crs, crsTransform=tr)
    rows = ee_call(
        lambda: ee.data.computeFeatures(
            {"expression": samp, "fileFormat": "PANDAS_DATAFRAME"}
        ).drop(columns=["geometry"], errors="ignore").to_dict("records"),
        timeout=EE_TIMEOUT, label="reduceRegions equivalence")

    diffs, n = [], 0
    for rec in rows:
        if any(rec.get(b) is None for b in S2_BAND_NAMES):
            continue
        i = int(rec["i"])
        a = np.array([rec[b] for b in S2_BAND_NAMES], float)
        diffs.append(np.abs(a - stack[rr[i], cc[i]]).max())
        n += 1
    if n == 0:
        raise SystemExit("EQUIVALENCE CHECK produced no comparable cells")
    diffs = np.array(diffs)
    print(f"  compared {n} cells re-fetched via reduceRegions")
    print(f"    max |diff| = {diffs.max():.3e}   "
          f"median = {np.median(diffs):.3e}   bar = {EQUIV_MAX_ABS_DIFF:.0e}")
    if diffs.max() > EQUIV_MAX_ABS_DIFF:
        raise SystemExit(
            f"EQUIVALENCE CHECK FAILED: computePixels disagrees with "
            f"reduceRegions by {diffs.max():.3e} > {EQUIV_MAX_ABS_DIFF:.0e}. "
            f"Falling back to the point-sampling path is required.")
    print("    -> paths agree; the array fetch is a pure speed change")


def main():
    print("=" * 74)
    print(f"ITEM 21 PHASE 0 part 2 -- {SITE['label']}")
    print("=" * 74)
    print(f"site={SITE['key']}  sensor={SITE['sensor']}  "
          f"acquired={SITE['acquired']}")
    print(f"PRE-REGISTERED BAR: R2>={WORKS_R2} works | "
          f"{CAVEAT_R2}-{WORKS_R2} caveat | <{CAVEAT_R2} does not work")

    mpath = os.path.join(SCRATCH, f"vhr_label_metrics_{SITE['key']}.json")
    lab_m = json.load(open(mpath)) if os.path.exists(mpath) else {}
    if lab_m:
        print(f"Label: binary accuracy {lab_m['binary_acc']:.3f} "
              f"(precision {lab_m['precision']:.3f}, "
              f"recall {lab_m['recall']:.3f}), "
              f"{lab_m['n_patches']} patches")
    print("Therefore the R2 below is a LOWER BOUND: a pass is strong, "
          "a miss is CONFOUNDED.\n")

    aoi = ee.Geometry.Rectangle(B.AOI_BBOX)
    proj, info = ee_call(lambda: s2_grid(aoi), timeout=EE_TIMEOUT,
                         label="s2 grid")
    tr = info["transform"]
    print(f"S2 grid: {info['crs']} {tr}")

    image, ncount = build_composite(aoi)
    print(f"S2 composite: {ncount} images, {SITE['s2_start']}.."
          f"{SITE['s2_end']} (brackets the {SITE['acquired']} acquisition)")

    lab = build_label_raster(tr)
    counts, valid, total = lab["counts"], lab["valid"], lab["total"]
    r_lo, c_lo = int(lab["r_lo"][0]), int(lab["c_lo"][0])
    nR, nC = valid.shape

    frac_valid = valid / np.maximum(total, 1)
    usable = (frac_valid >= MIN_VALID_FRAC) & (valid > 0)
    print(f"\ncells with >={MIN_VALID_FRAC:.0%} valid VHR coverage: "
          f"{int(usable.sum())} of {nR*nC}")

    denom = np.maximum(valid, 1)
    fr = {c: counts[i] / denom for i, c in enumerate(B.CLASSES)}
    imperv = fr["roof"] + fr["hard_unroofed"]

    v = imperv[usable]
    p50 = float(np.percentile(v, 50))
    sd = float(v.std())
    print(f"\nIMPERVIOUS FRACTION distribution over {len(v)} cells:")
    print(f"  mean={v.mean():.3f} sd={sd:.3f} "
          f"min={v.min():.3f} max={v.max():.3f}")
    for q in (5, 25, 50, 75, 95):
        print(f"  p{q:<3} {np.percentile(v, q):.3f}", end="")
    print()
    print(f"  frac exactly 0: {(v == 0).mean():.4f}   "
          f"frac exactly 1: {(v == 1).mean():.4f}")

    # ---- pre-registered de-confounding gates ---------------------------
    print("\nPRE-REGISTERED DE-CONFOUNDING GATES (interpretation, not verdict):")
    gates = []
    if lab_m:
        ok = lab_m["binary_acc"] > vhr_sites.LABEL_ACC_MIN
        gates.append(ok)
        print(f"  label accuracy   {lab_m['binary_acc']:.3f} > "
              f"{vhr_sites.LABEL_ACC_MIN}  -> {'PASS' if ok else 'FAIL'}")
    ok = p50 < vhr_sites.TARGET_P50_MAX
    gates.append(ok)
    print(f"  target median    {p50:.3f} < "
          f"{vhr_sites.TARGET_P50_MAX}  -> {'PASS' if ok else 'FAIL'}")
    ok = sd >= vhr_sites.TARGET_SD_MIN
    gates.append(ok)
    print(f"  target spread    {sd:.3f} >= "
          f"{vhr_sites.TARGET_SD_MIN}  -> {'PASS' if ok else 'FAIL'}")
    deconfounded = all(gates)
    print(f"  => {'DE-CONFOUNDED' if deconfounded else 'STILL CONFOUNDED'} "
          f"relative to the Accra run")

    # ---- pull S2 on exactly this grid -----------------------------------
    print("\nfetching S2 composite as an array on the label grid...", flush=True)
    stack, s2mask = fetch_s2_array(image, info["crs"], tr, r_lo, c_lo, nR, nC)
    print(f"  got {stack.shape} + mask")

    ok_cell = usable & s2mask & np.isfinite(stack).all(-1)
    rr, cc = np.where(ok_cell)
    print(f"  {len(rr)} cells with both S2 and label")

    rng = np.random.default_rng(0)
    print("\nEQUIVALENCE CHECK (computePixels vs the Accra reduceRegions path):")
    verify_equivalence(image, info["crs"], tr, r_lo, c_lo, rr, cc, stack, rng)

    X = stack[rr, cc]
    y = imperv[rr, cc]
    R, C = rr, cc

    # ---- co-registration check -----------------------------------------
    print("\nCO-REGISTRATION CHECK (measured, not assumed):")
    grid_y = np.full((nR, nC), np.nan)
    grid_y[R, C] = y
    s2b = np.full((nR, nC), np.nan)
    s2b[R, C] = X[:, [0, 1, 2]].mean(1)
    best = None
    for dr in range(-MAX_SHIFT, MAX_SHIFT + 1):
        for dc in range(-MAX_SHIFT, MAX_SHIFT + 1):
            a = np.roll(np.roll(grid_y, dr, 0), dc, 1)
            m = np.isfinite(a) & np.isfinite(s2b)
            if m.sum() < 500:
                continue
            r = abs(np.corrcoef(a[m], s2b[m])[0, 1])
            if best is None or r > best[0]:
                best = (r, dr, dc)
    print(f"  best |corr| = {best[0]:.3f} at shift (dr={best[1]}, dc={best[2]}) "
          f"cells = ({best[1]*10} m, {best[2]*10} m)")
    if best[1] == 0 and best[2] == 0:
        print("  -> aligned at 10 m; no offset correction needed")
    else:
        print("  -> OFFSET DETECTED. Regression below uses the measured shift.")
        y = np.roll(np.roll(grid_y, best[1], 0), best[2], 1)[R, C]
        keep = np.isfinite(y)
        X, y, R, C = X[keep], y[keep], R[keep], C[keep]

    # ---- spatially blocked split ---------------------------------------
    blk = BLOCK_M // 10
    checker = ((R // blk) + (C // blk)) % 2
    tr_m, te_m = checker == 0, checker == 1
    print(f"\nSPATIALLY BLOCKED SPLIT ({BLOCK_M} m checkerboard): "
          f"{tr_m.sum()} train / {te_m.sum()} test")
    print("  (NOT random -- a random split inside one city is optimistic, A.13)")

    Xtr, Xte = base.normalize("per_aoi", [X[tr_m]], X[te_m])
    out = {}
    for model in ("ridge", "gbt"):
        yhat = base.fit_predict(model, Xtr, y[tr_m], Xte)
        r2 = r2_score(y[te_m], yhat)
        mae = mean_absolute_error(y[te_m], yhat)
        out[model] = (r2, mae)
        print(f"  {model:<6} R2={r2:>7.3f}  MAE={mae:.4f}")
    base_mae = np.abs(y[te_m] - y[tr_m].mean()).mean()
    print(f"  baseline (predict train mean) MAE={base_mae:.4f}")

    r2 = out[base.PRIMARY_MODEL][0]
    if r2 >= WORKS_R2:
        verdict = "WORKS -- item 21 closes"
    elif r2 >= CAVEAT_R2:
        verdict = "USABLE WITH PROMINENT CONFIDENCE CAVEAT"
    else:
        verdict = "DOES NOT WORK at 10 m per-pixel"
    print("\n" + "=" * 74)
    print(f"PRE-REGISTERED VERDICT ({base.PRIMARY_MODEL}): "
          f"R2={r2:.3f} -> {verdict}")
    print("=" * 74)
    if r2 < CAVEAT_R2 and not deconfounded:
        print("REMINDER, stated before the run: a miss is CONFOUNDED by label")
        print("noise and/or target saturation and does NOT settle whether")
        print("reflectance predicts impervious fraction.")
    elif r2 < CAVEAT_R2 and deconfounded:
        print("NOTE: both de-confounding gates passed, so this miss is NOT")
        print("explained away by label quality or saturation on this site.")
        print("It remains a single-site result on one sensor.")

    json.dump({"site": SITE["key"], "n_cells": int(len(y)),
               "r2": {k: v[0] for k, v in out.items()},
               "mae": {k: v[1] for k, v in out.items()},
               "baseline_mae": float(base_mae),
               "target_p50": p50, "target_sd": sd,
               "label": lab_m, "deconfounded": bool(deconfounded),
               "coreg": {"corr": best[0], "dr": best[1], "dc": best[2]}},
              open(os.path.join(SCRATCH,
                                f"vhr_reg_{SITE['key']}.json"), "w"), indent=2)


if __name__ == "__main__":
    main()
