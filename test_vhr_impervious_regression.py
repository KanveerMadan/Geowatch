"""
Item 21 Phase 0, part 2 — co-registration check, label raster, and the
regression of S2 reflectance against a VHR-derived impervious fraction.

Depends on build_vhr_impervious_label.py, which trained the label classifier
and reported its accuracy. Read that file's docstring first; in particular the
label is MODEL-GENERATED and its measured binary accuracy is 0.711
(precision 0.629, recall 0.863 for impervious vs not).

WHAT THAT MEANS FOR EVERY NUMBER BELOW, stated before running
---------------------------------------------------------------
A noisy label caps what any regression can score against it. If the label
carries independent error, the best attainable R2 against the LABEL is bounded
by the share of the label's variance that is real signal rather than label
noise. So the R2 reported here is a LOWER BOUND on the true reflectance-to-
impervious relationship, not an estimate of it:

  * a PASS would be strong evidence, because it is achieved despite the noise
  * a MISS is CONFOUNDED -- it cannot distinguish "reflectance does not predict
    impervious" from "the label is too noisy to tell", and must not be reported
    as though it settles the question

This asymmetry is stated up front so a miss is not later spun as a finding.

PRE-REGISTERED BAR, unchanged from the task specification
-----------------------------------------------------------
  R2 >= 0.60   -> impervious_total works, item 21 closes
  0.50 - 0.60  -> usable, ships with a prominent confidence caveat
  R2 <  0.50   -> does not work at 10 m per-pixel; go coarser or drop the
                  fraction product

SPLIT: spatially blocked, NOT random. Only one AOI is available, so
leave-one-AOI-out is impossible; instead the scene is divided into a coarse
checkerboard of BLOCK_M-metre blocks and alternating blocks form train/test.
A random split inside one city is optimistic for exactly the reason A.13
gives, and would inflate this number.

CO-REGISTRATION: the UAV is 5 cm and the S2 grid is 10 m, so a misalignment of
one S2 cell is 200 UAV pixels and would decorrelate the label from the imagery.
Alignment is MEASURED, not assumed: the UAV is aggregated to the S2 grid and
cross-correlated against the S2 composite over a range of integer cell shifts,
and the best offset is reported. Both rasters are EPSG:32630, so no
reprojection of the label is involved.

Usage:
    python test_vhr_impervious_regression.py
"""

import os
import pickle

import numpy as np
import rasterio
from rasterio.windows import Window
from sklearn.metrics import mean_absolute_error, r2_score

import build_vhr_impervious_label as B
import diagnose_pure_pixels as pure_diag
import ee
import regress_built_fraction as base
from ingestion.sentinel2 import S2_BAND_NAMES, get_sentinel2_median_composite

# --- pre-registered; not edited after seeing results ---------------------
WORKS_R2 = 0.60
CAVEAT_R2 = 0.50
BLOCK_M = 200          # checkerboard block size for the spatial split
MAX_SHIFT = 4          # +/- cells searched in the co-registration check
MIN_VALID_FRAC = 0.60  # a 10 m cell needs this much valid UAV coverage
# -------------------------------------------------------------------------

SCRATCH = B.SCRATCH


def s2_grid(aoi):
    proj, info = pure_diag.s2_grid_for(aoi)
    return proj, info


def build_label_raster(s2_crs, s2_tr, force=False):
    """Per-10m-cell class fractions from the VHR classifier."""
    out = os.path.join(SCRATCH, "vhr_label_fractions.npz")
    if os.path.exists(out) and not force:
        d = np.load(out)
        print("  (cached label raster)")
        return {k: d[k] for k in d.files}

    clf = pickle.load(open(os.path.join(SCRATCH, "vhr_clf.pkl"), "rb"))
    nclass = len(B.CLASSES)

    with rasterio.open(B.UAV) as src:
        assert str(src.crs).endswith("32630"), src.crs
        # S2 cell index for a UAV pixel, both in EPSG:32630
        x0, px, _, y0, _, py = (s2_tr[2], s2_tr[0], s2_tr[1],
                                s2_tr[5], s2_tr[3], s2_tr[4])
        ut = src.transform
        H = src.height // B.DS
        W = src.width // B.DS

        # extent of the S2 grid we need
        bl, bb, br, bt = src.bounds
        c_lo = int(np.floor((bl - x0) / px)) - 1
        c_hi = int(np.ceil((br - x0) / px)) + 1
        r_lo = int(np.floor((bt - y0) / py)) - 1
        r_hi = int(np.ceil((bb - y0) / py)) + 1
        nR, nC = r_hi - r_lo, c_hi - c_lo
        print(f"  S2 label grid: {nR} x {nC} cells")

        counts = np.zeros((nclass, nR, nC), np.int32)
        valid = np.zeros((nR, nC), np.int32)
        total = np.zeros((nR, nC), np.int32)

        BLK = 1024   # rows at working res
        for r0 in range(0, H, BLK):
            nrows = min(BLK, H - r0)
            arr = src.read(window=Window(0, r0 * B.DS, src.width,
                                         nrows * B.DS),
                           out_shape=(3, nrows, W))
            rgb = np.transpose(arr, (1, 2, 0)).astype(np.float32)
            good = rgb.sum(2) > 0
            F = B.features(rgb).reshape(-1, B.NFEAT)
            pred = np.full(len(F), -1, np.int8)
            gflat = good.reshape(-1)
            if gflat.any():
                pred[gflat] = clf.predict(F[gflat]).astype(np.int8)

            yy, xx = np.mgrid[0:nrows, 0:W]
            ux = ut[2] + (xx + 0.5) * B.DS * ut[0]
            uy = ut[5] + (r0 + yy + 0.5) * B.DS * ut[4]
            cc = np.floor((ux - x0) / px).astype(int) - c_lo
            rr = np.floor((uy - y0) / py).astype(int) - r_lo
            ok = (rr >= 0) & (rr < nR) & (cc >= 0) & (cc < nC)

            flat_idx = (rr[ok] * nC + cc[ok])
            np.add.at(total.reshape(-1), flat_idx, 1)
            p = pred.reshape(nrows, W)[ok]
            g = good[ok]
            np.add.at(valid.reshape(-1), flat_idx[g], 1)
            for k in range(nclass):
                sel = g & (p == k)
                if sel.any():
                    np.add.at(counts[k].reshape(-1), flat_idx[sel], 1)
            print(f"    rows {r0}-{r0+nrows} done", flush=True)

    res = {"counts": counts, "valid": valid, "total": total,
           "r_lo": np.array([r_lo]), "c_lo": np.array([c_lo])}
    np.savez_compressed(out, **res)
    return res


def main():
    print("=" * 74)
    print("ITEM 21 PHASE 0 part 2 — co-registration, label raster, regression")
    print("=" * 74)
    print(f"PRE-REGISTERED BAR: R2>={WORKS_R2} works | "
          f"{CAVEAT_R2}-{WORKS_R2} caveat | <{CAVEAT_R2} does not work")
    print("Label is model-generated, binary accuracy 0.711 "
          "(precision 0.629, recall 0.863).")
    print("Therefore the R2 below is a LOWER BOUND: a pass is strong, "
          "a miss is CONFOUNDED.\n")

    aoi = ee.Geometry.Rectangle(B.AOI_BBOX)
    proj, info = s2_grid(aoi)
    print(f"S2 grid: {info['crs']} {info['transform']}")
    tr = info["transform"]

    comp = get_sentinel2_median_composite(aoi, B.S2_START, B.S2_END)
    print(f"S2 composite: {comp['provenance']['source_image_count']} images, "
          f"{B.S2_START}..{B.S2_END} (brackets the 2024-08 UAV)")

    lab = build_label_raster(info["crs"], tr)
    counts, valid, total = lab["counts"], lab["valid"], lab["total"]
    r_lo, c_lo = int(lab["r_lo"][0]), int(lab["c_lo"][0])
    nR, nC = valid.shape

    frac_valid = valid / np.maximum(total, 1)
    usable = (frac_valid >= MIN_VALID_FRAC) & (valid > 0)
    print(f"\ncells with >={MIN_VALID_FRAC:.0%} valid UAV coverage: "
          f"{int(usable.sum())} of {nR*nC}")

    denom = np.maximum(valid, 1)
    fr = {c: counts[i] / denom for i, c in enumerate(B.CLASSES)}
    imperv = fr["roof"] + fr["hard_unroofed"]

    v = imperv[usable]
    print(f"\nIMPERVIOUS FRACTION distribution over {len(v)} cells:")
    print(f"  mean={v.mean():.3f} sd={v.std():.3f} "
          f"min={v.min():.3f} max={v.max():.3f}")
    for q in (5, 25, 50, 75, 95):
        print(f"  p{q:<3} {np.percentile(v, q):.3f}", end="")
    print()
    print(f"  frac exactly 0: {(v == 0).mean():.4f}   "
          f"frac exactly 1: {(v == 1).mean():.4f}")
    if v.std() < 0.05:
        print("  *** degenerate: label has almost no variance, "
              "useless for regression")

    # ---- pull S2 bands on the same grid --------------------------------
    print("\nsampling S2 composite on the label grid...", flush=True)
    xs = tr[2] + (np.arange(nC) + c_lo + 0.5) * tr[0]
    ys = tr[5] + (np.arange(nR) + r_lo + 0.5) * tr[4]
    rr, cc = np.where(usable)
    # NOTE: pass the CRS STRING, not the ee.Projection. The projection from
    # s2_grid_for carries a crsTransform, and handing that to Geometry.Point
    # makes EE reinterpret the coordinates through it -- which silently placed
    # every point outside the scene and matched 0 cells on the first run.
    pts = [ee.Feature(ee.Geometry.Point([float(xs[c]), float(ys[r])],
                                        info["crs"]),
                      {"r": int(r), "c": int(c)})
           for r, c in zip(rr[::1], cc[::1])]
    print(f"  {len(pts)} sample points")

    vals = {}
    CH = 4000
    for i in range(0, len(pts), CH):
        fc = ee.FeatureCollection(pts[i:i + CH])
        samp = comp["image"].reduceRegions(
            collection=fc, reducer=ee.Reducer.first(),
            crs=info["crs"], crsTransform=tr)
        try:
            df = ee.data.computeFeatures(
                {"expression": samp, "fileFormat": "GEOPANDAS_GEODATAFRAME"})
            rows = df.drop(columns=["geometry"], errors="ignore").to_dict("records")
        except Exception:
            rows = ee.data.computeFeatures(
                {"expression": samp, "fileFormat": "PANDAS_DATAFRAME"}
            ).to_dict("records")
        for rec in rows:
            if all(rec.get(b) is not None for b in S2_BAND_NAMES):
                vals[(rec["r"], rec["c"])] = [rec[b] for b in S2_BAND_NAMES]
        print(f"  sampled {min(i+CH, len(pts))}/{len(pts)}", flush=True)

    keys = sorted(vals)
    X = np.array([vals[k] for k in keys], float)
    y = np.array([imperv[k] for k in keys], float)
    R = np.array([k[0] for k in keys])
    C = np.array([k[1] for k in keys])
    print(f"\nmatched {len(X)} cells with both S2 and label")

    # ---- co-registration check -----------------------------------------
    print("\nCO-REGISTRATION CHECK (measured, not assumed):")
    grid_y = np.full((nR, nC), np.nan)
    grid_y[R, C] = y
    s2b = np.full((nR, nC), np.nan)
    s2b[R, C] = X[:, [0, 1, 2]].mean(1)      # S2 visible brightness
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
        print(f"  -> OFFSET DETECTED. Regression below uses the measured "
              f"shift.")
        y = np.roll(np.roll(grid_y, best[1], 0), best[2], 1)[R, C]
        ok = np.isfinite(y)
        X, y, R, C = X[ok], y[ok], R[ok], C[ok]

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
        v = "WORKS — item 21 closes"
    elif r2 >= CAVEAT_R2:
        v = "USABLE WITH PROMINENT CONFIDENCE CAVEAT"
    else:
        v = "DOES NOT WORK at 10 m per-pixel"
    print("\n" + "=" * 74)
    print(f"PRE-REGISTERED VERDICT ({base.PRIMARY_MODEL}): R2={r2:.3f} -> {v}")
    print("=" * 74)
    if r2 < CAVEAT_R2:
        print("REMINDER, stated before the run: a miss is CONFOUNDED by label")
        print("noise (binary accuracy 0.711) and does NOT settle whether")
        print("reflectance predicts impervious fraction.")


if __name__ == "__main__":
    main()
