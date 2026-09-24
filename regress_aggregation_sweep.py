"""
Item 21 Phase 0 -- the aggregation arm. Does a coarser REPORTING UNIT rescue
`impervious_total`?

WHY THIS ARM EXISTS
-------------------
The Nairobi re-run de-confounded the Accra miss but did not close item 21. The
failure had a specific signature: ridge R2 0.724 on a 200 m checkerboard
collapses to 0.281 on a contiguous west/east split, and on genuinely mixed
cells (0.3-0.7) the model is 45% WORSE at MAE than predicting the subset mean.
So the aggregate score is carried by homogeneous extremes -- Ngong Forest near
0, dense Kibera near 1 -- which is region classification, not fraction
estimation.

Aggregation is the one remaining thing that plausibly helps, and the mechanism
is stated in advance so the result can be read against it:

  1. coarser cells AVERAGE OUT label noise (binary accuracy 0.844 at Nairobi,
     0.711 at Accra), and
  2. they average out the per-pixel mixed-cell weakness, and
  3. a proportion over a larger area is a statistically easier quantity than a
     per-pixel fraction.

`02_ARCHITECTURE.md`'s own framing for this rebuild is "from naming pixels to
measuring areas". Every method in this investigation regressed a per-PIXEL
label, so that shift was announced but never tested. `regress_scale_sweep.py`
also left a 20/30/60/90 m arm stalled on Earth Engine with no real-data curve.

WHAT IS MEASURED
----------------
Features AND label are aggregated together to 30 m and 60 m as 3x3 and 6x6
block means of the EXISTING 10 m cells on the real S2 grid. Nothing is
resampled through Earth Engine and no new imagery is fetched -- same 6-band
composite, same labels, same classifier outputs. 10 m is reported as the
baseline row so the curve is readable; at k=1 the pipeline reduces exactly to
the published 10 m run, which is used as a self-check on the aggregation code.

The label is aggregated as a PROPORTION OVER AREA, not as a mean of fractions:
  impervious = sum(roof + hard VHR pixels in block) / sum(valid VHR pixels)
which is the quantity a coarser reporting unit would actually publish.

READING THE CURVE -- stated before running
-------------------------------------------
Aggregation MECHANICALLY shrinks target variance, and R2 is variance-
normalised. So an R2 gain accompanied by a collapse in sd is not a real gain,
and target sd/IQR is reported at every scale for exactly that reason. The
honest test of whether skill improved is MAE against the same scale's own
mean-predictor baseline, which is also reported at every scale.

SPLITS
------
The CONTIGUOUS split is primary. The prior run established that checkerboard
R2 is not comparable across scenes -- pessimistic at Accra (0.363 vs 0.532
contiguous), optimistic at Nairobi (0.724 vs 0.281). West->east is fixed in
advance as the primary contiguous split for both sites, because it was the
maximal-extrapolation orientation at 10 m at both. All four half-planes are
reported so the seam cannot be cherry-picked, and the checkerboard is reported
alongside, clearly marked as the optimistic reading.

BAR, unchanged, applied to the CONTIGUOUS split, ridge primary:
    R2 >= 0.60 -> works at that scale
    0.50-0.60  -> usable with a caveat
    <  0.50    -> does not work at that scale

Small n: at 60 m the counts fall sharply (Nairobi ~1,700, Accra ~360). A high
R2 on a few hundred cells under a contiguous split is not a result, so n is
stated at every scale and anything under MIN_CELLS_MEANINGFUL is flagged.

Usage:
    python regress_aggregation_sweep.py
"""

import json
import os

import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score

import ee
import regress_built_fraction as base
import vhr_sites

# --- pre-registered; fixed before any aggregated result existed ----------
SCALES_M = [10, 30, 60]        # 1x1, 3x3, 6x6 blocks of the real 10 m S2 grid
WORKS_R2 = 0.60
CAVEAT_R2 = 0.50
MIN_VALID_FRAC = 0.60          # VHR coverage of a coarse cell, as at 10 m
MIN_BLOCK_COVER = 0.80         # share of constituent 10 m cells that must be
                               # usable for the coarse cell to be kept
MIN_CELLS_MEANINGFUL = 500     # below this a split result is flagged, not read
CHECKER_M = 200                # checkerboard tile, as in the published runs
MIXED_LO, MIXED_HI = 0.30, 0.70   # the diagnostic that exposed the 10 m pass
PRIMARY_CONTIGUOUS = "west->east"
# -------------------------------------------------------------------------

SITES = ["kibera", "oldfadama"]


def load_grids(key):
    """2D grids for one site: label counts, coverage, S2 stack, S2 mask.

    Reuses the cached label raster and S2 array built by the 10 m run; nothing
    here re-fetches or re-classifies.
    """
    os.environ["GW_SITE"] = key
    import importlib
    import build_vhr_impervious_label as B
    importlib.reload(vhr_sites)
    importlib.reload(B)

    sc = B.SCRATCH
    lab = np.load(os.path.join(sc, f"vhr_label_fractions_{key}.npz"))
    d = np.load(os.path.join(sc, f"vhr_s2_stack_{key}.npz"))
    counts, valid, total = lab["counts"], lab["valid"], lab["total"]
    imp_idx = [B.CLASSES.index(c) for c in B.IMPERVIOUS]
    return dict(key=key, label=vhr_sites.site(key)["label"],
                num=counts[imp_idx].sum(0).astype(np.float64),
                den=valid.astype(np.float64),
                tot=total.astype(np.float64),
                stack=d["stack"], mask=d["mask"])


def block_sum(a, k):
    """Sum over non-overlapping k x k blocks, cropping the ragged edge."""
    nR, nC = a.shape[:2]
    R, C = (nR // k) * k, (nC // k) * k
    a = a[:R, :C]
    if a.ndim == 2:
        return a.reshape(R // k, k, C // k, k).sum((1, 3))
    b = a.shape[2]
    return a.reshape(R // k, k, C // k, k, b).sum((1, 3))


def aggregate(g, k):
    """Aggregate label and features to k x k blocks of 10 m cells."""
    cell_ok = ((g["den"] / np.maximum(g["tot"], 1)) >= MIN_VALID_FRAC) \
        & (g["den"] > 0) & g["mask"] & np.isfinite(g["stack"]).all(-1)

    num = block_sum(g["num"] * cell_ok, k)
    den = block_sum(g["den"] * cell_ok, k)
    tot = block_sum(g["tot"] * cell_ok, k)
    cover = block_sum(cell_ok.astype(np.float64), k) / (k * k)

    # features: mean of the valid constituent cells only
    sx = block_sum(g["stack"] * cell_ok[..., None], k)
    nvalid = block_sum(cell_ok.astype(np.float64), k)

    keep = (cover >= MIN_BLOCK_COVER) & (den > 0) & (nvalid > 0) \
        & ((den / np.maximum(tot, 1)) >= MIN_VALID_FRAC)
    R, C = np.where(keep)
    y = (num[keep] / den[keep])
    X = sx[keep] / nvalid[keep][:, None]
    return X, y, R, C


def fit(Xtr, ytr, Xte, model):
    Xtr_n, Xte_n = base.normalize("per_aoi", [Xtr], Xte)
    return base.fit_predict(model, Xtr_n, ytr, Xte_n)


def contiguous(R, C, name):
    rm, cm = (R.min() + R.max()) / 2, (C.min() + C.max()) / 2
    return {"west->east": (C <= cm, C > cm),
            "east->west": (C > cm, C <= cm),
            "north->south": (R <= rm, R > rm),
            "south->north": (R > rm, R <= rm)}[name]


def checker(R, C, cell_m):
    b = max(1, CHECKER_M // cell_m)
    ch = ((R // b) + (C // b)) % 2
    return ch == 0, ch == 1


def main():
    print("=" * 78)
    print("ITEM 21 PHASE 0 -- AGGREGATION SWEEP (does a coarser unit rescue it?)")
    print("=" * 78)
    print(f"scales {SCALES_M} m | primary split {PRIMARY_CONTIGUOUS} "
          f"(contiguous) | bar {CAVEAT_R2}/{WORKS_R2} | ridge primary")
    print("R2 gains that come with a collapse in target sd are NOT real gains;")
    print("sd/IQR and MAE-vs-baseline are reported at every scale for that.\n")

    grids = {k: load_grids(k) for k in SITES}
    agg = {k: {} for k in SITES}
    out = {}

    for key, g in grids.items():
        print("=" * 78)
        print(f"{g['label']}")
        print("=" * 78)
        site_out = {}
        for m in SCALES_M:
            k = m // 10
            X, y, R, C = aggregate(g, k)
            agg[key][m] = (X, y, R, C)
            q1, q3 = np.percentile(y, [25, 75])
            print(f"\n--- {m} m cells ({k}x{k} blocks) --- n={len(y)}"
                  + ("   *** n below "
                     f"{MIN_CELLS_MEANINGFUL}: splits not meaningful ***"
                     if len(y) < MIN_CELLS_MEANINGFUL else ""))
            print(f"  target  mean={y.mean():.3f} sd={y.std():.3f} "
                  f"median={np.median(y):.3f} IQR={q3-q1:.3f} "
                  f"[{q1:.3f},{q3:.3f}]")

            rows = {}
            for split_name, get in (
                    (f"CONTIGUOUS {PRIMARY_CONTIGUOUS} (primary)",
                     lambda: contiguous(R, C, PRIMARY_CONTIGUOUS)),
                    ("contiguous east->west",
                     lambda: contiguous(R, C, "east->west")),
                    ("contiguous north->south",
                     lambda: contiguous(R, C, "north->south")),
                    ("contiguous south->north",
                     lambda: contiguous(R, C, "south->north")),
                    (f"checkerboard {CHECKER_M} m (OPTIMISTIC)",
                     lambda: checker(R, C, m))):
                tr_m, te_m = get()
                if tr_m.sum() < 20 or te_m.sum() < 20:
                    print(f"  {split_name:<40} (too few cells)")
                    continue
                res = {}
                for model in ("ridge", "gbt"):
                    yh = fit(X[tr_m], y[tr_m], X[te_m], model)
                    res[model] = (r2_score(y[te_m], yh),
                                  mean_absolute_error(y[te_m], yh))
                bmae = float(np.abs(y[te_m] - y[tr_m].mean()).mean())
                rows[split_name] = {"n_train": int(tr_m.sum()),
                                    "n_test": int(te_m.sum()),
                                    "ridge_r2": res["ridge"][0],
                                    "ridge_mae": res["ridge"][1],
                                    "gbt_r2": res["gbt"][0],
                                    "gbt_mae": res["gbt"][1],
                                    "baseline_mae": bmae}
                print(f"  {split_name:<40} "
                      f"ridge R2={res['ridge'][0]:>7.3f} MAE={res['ridge'][1]:.4f} | "
                      f"gbt R2={res['gbt'][0]:>7.3f} MAE={res['gbt'][1]:.4f} | "
                      f"base MAE={bmae:.4f}")

                if split_name.startswith("CONTIGUOUS"):
                    yh = fit(X[tr_m], y[tr_m], X[te_m], "ridge")
                    yte = y[te_m]
                    mm = (yte > MIXED_LO) & (yte < MIXED_HI)
                    if mm.sum() >= 30:
                        mae = mean_absolute_error(yte[mm], yh[mm])
                        smae = float(np.abs(yte[mm] - yte[mm].mean()).mean())
                        imp = 100 * (1 - mae / smae) if smae > 0 else float("nan")
                        print(f"    mixed cells {MIXED_LO}-{MIXED_HI}: "
                              f"n={int(mm.sum())} R2={r2_score(yte[mm], yh[mm]):>7.3f} "
                              f"MAE={mae:.4f} vs subset-mean {smae:.4f} "
                              f"-> {imp:+.1f}%")
                        rows[split_name]["mixed"] = {
                            "n": int(mm.sum()),
                            "r2": r2_score(yte[mm], yh[mm]),
                            "mae": mae, "subset_mean_mae": smae,
                            "improvement_pct": imp}
                    else:
                        print(f"    mixed cells {MIXED_LO}-{MIXED_HI}: "
                              f"n={int(mm.sum())} -- too few to read")

            pr = rows.get(f"CONTIGUOUS {PRIMARY_CONTIGUOUS} (primary)")
            if pr:
                r2 = pr["ridge_r2"]
                v = ("works at this scale" if r2 >= WORKS_R2 else
                     "usable with a caveat" if r2 >= CAVEAT_R2 else
                     "DOES NOT WORK at this scale")
                flag = ("  [n below threshold -- not readable]"
                        if len(y) < MIN_CELLS_MEANINGFUL else "")
                print(f"  => {m} m verdict (contiguous, ridge): "
                      f"R2={r2:.3f} -> {v}{flag}")
            site_out[m] = {"n": int(len(y)), "mean": float(y.mean()),
                           "sd": float(y.std()),
                           "median": float(np.median(y)),
                           "iqr": float(q3 - q1), "splits": rows}
        out[key] = site_out

    # ---- cross-site transfer at each scale ------------------------------
    print("\n" + "=" * 78)
    print("CROSS-SITE TRANSFER at each scale (item 21's acceptance criterion)")
    print("At 10 m this was negative both ways: -1.132 and -0.023.")
    print("=" * 78)
    print(f"  {'scale':<8}{'train':<12}{'test':<12}{'n_test':>8}"
          f"{'ridge':>9}{'gbt':>9}")
    xs = {}
    for m in SCALES_M:
        for a in SITES:
            for b in SITES:
                if a == b:
                    continue
                Xa, ya, _, _ = agg[a][m]
                Xb, yb, _, _ = agg[b][m]
                r = {mo: r2_score(yb, fit(Xa, ya, Xb, mo))
                     for mo in ("ridge", "gbt")}
                xs[f"{m}m {a}->{b}"] = r
                print(f"  {str(m)+' m':<8}{a:<12}{b:<12}{len(yb):>8}"
                      f"{r['ridge']:>9.3f}{r['gbt']:>9.3f}")
    out["cross_site"] = xs

    sc = vhr_sites.site("kibera")["scratch"]
    with open(os.path.join(sc, "vhr_aggregation_sweep.json"), "w") as fh:
        json.dump(out, fh, indent=2, default=float)
    print(f"\nwrote {os.path.join(sc, 'vhr_aggregation_sweep.json')}")


if __name__ == "__main__":
    main()
