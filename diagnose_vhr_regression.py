"""
Supplementary diagnostics for the item 21 Phase 0 re-run.

The pre-registered verdict is whatever `test_vhr_impervious_regression.py`
reports at BLOCK_M=200; nothing here replaces it. These are the checks a
LARGE PASS deserves before it is believed, and they are written before their
results exist.

Nairobi returned ridge R2 = 0.724 against a 0.60 bar, up from Accra's 0.363.
Three things could inflate that, and each gets a test:

(A) SPATIAL LEAKAGE. Accra was uniformly saturated, so a 200 m checkerboard
    cost it little. Nairobi's dynamic range comes from KILOMETRE-scale regions
    -- Ngong Forest at ~0, Kibera at ~1 -- and against structure that coarse, a
    200 m checkerboard puts every test block within 200 m of a training block.
    That is exactly the leakage A.13 warns about, one scale up. Swept over
    block size, and against a contiguous halves split, which is the strictest
    within-site split available.

(B) THE EASY CONTRAST DOING THE WORK. Vegetation sits 23-26 degrees from every
    hard surface, water 43-47 (06_UNMIXING_CEILING.md Part 2). A scene
    containing forest and a dam can score well on impervious fraction without
    ever resolving the boundary that actually matters, which is impervious vs
    BARE at 3.45 degrees -- the weakest remaining boundary per Part 3.1. So R2
    is recomputed on the low-vegetation subset, where impervious-vs-bare is the
    operative distinction, and on genuinely MIXED cells, which is what a
    fraction product claims to estimate at all.

(C) SINGLE-SITE / SINGLE-SENSOR. Item 21's revised acceptance asks for
    validation against a HELD-OUT AOI, not a same-AOI split. Two labelled sites
    now exist, so leave-one-site-out is reported. No bar is pre-registered for
    it -- two sites on two continents with two sensors is too thin a base to set
    one honestly -- so it is reported as an observation.

PRE-REGISTERED READING OF THE LEAKAGE SWEEP, fixed before running
------------------------------------------------------------------
Judged on the STRICTEST split (contiguous halves), primary model ridge:
    >= 0.60  -> the pass is robust to leakage; it stands as reported
    0.50-0.60 -> the pass DOWNGRADES to "usable with a prominent caveat"
    <  0.50  -> the 200 m result is leakage-inflated and must NOT be
                reported as WORKS; the headline becomes the strict number
This is a rule about what may be CLAIMED, not a re-run of the verdict.

Usage:
    python diagnose_vhr_regression.py
"""

import json
import os

import numpy as np
from sklearn.metrics import r2_score

import ee
import regress_built_fraction as base
import vhr_sites

# --- pre-registered, fixed before results existed ------------------------
BLOCK_SWEEP_M = [200, 400, 800, 1600]
STRICT_ROBUST_R2 = 0.60      # strict-split value at/above which the pass holds
STRICT_CAVEAT_R2 = 0.50      # below this the 200 m number is leakage-inflated
LOW_VEG_MAX = 0.20           # "hard subset": vegetation fraction below this
MIXED_LO, MIXED_HI = 0.20, 0.80   # genuinely sub-pixel-mixed cells
# -------------------------------------------------------------------------

SITES = ["kibera", "oldfadama"]


def load_site(key):
    """Label fractions + S2 stack for one site, reusing what has been built."""
    os.environ["GW_SITE"] = key
    import importlib
    import build_vhr_impervious_label as B
    importlib.reload(vhr_sites)
    importlib.reload(B)
    import test_vhr_impervious_regression as T
    importlib.reload(T)

    aoi = ee.Geometry.Rectangle(B.AOI_BBOX)
    _, info = T.ee_call(lambda: T.s2_grid(aoi), label=f"{key} grid")
    tr = info["transform"]
    lab = T.build_label_raster(tr)
    counts, valid = lab["counts"], lab["valid"]
    total = lab["total"]
    r_lo, c_lo = int(lab["r_lo"][0]), int(lab["c_lo"][0])
    nR, nC = valid.shape

    cache = os.path.join(B.SCRATCH, f"vhr_s2_stack_{key}.npz")
    if os.path.exists(cache):
        d = np.load(cache)
        stack, s2mask = d["stack"], d["mask"]
    else:
        image, _ = T.build_composite(aoi)
        stack, s2mask = T.fetch_s2_array(image, info["crs"], tr,
                                         r_lo, c_lo, nR, nC)
        np.savez_compressed(cache, stack=stack, mask=s2mask)

    frac_valid = valid / np.maximum(total, 1)
    usable = (frac_valid >= T.MIN_VALID_FRAC) & (valid > 0)
    denom = np.maximum(valid, 1)
    fr = {c: counts[i] / denom for i, c in enumerate(B.CLASSES)}
    ok = usable & s2mask & np.isfinite(stack).all(-1)
    rr, cc = np.where(ok)
    return dict(key=key, label=vhr_sites.site(key)["label"],
                X=stack[rr, cc],
                y=(fr["roof"] + fr["hard_unroofed"])[rr, cc],
                veg=fr["vegetation"][rr, cc],
                water=fr["water"][rr, cc],
                R=rr, C=cc)


def fit(Xtr, ytr, Xte, yte, model):
    Xtr_n, Xte_n = base.normalize("per_aoi", [Xtr], Xte)
    yhat = base.fit_predict(model, Xtr_n, ytr, Xte_n)
    return r2_score(yte, yhat)


def split_checker(R, C, block_m):
    b = max(1, block_m // 10)
    ch = ((R // b) + (C // b)) % 2
    return ch == 0, ch == 1


def split_halves(R, C):
    """Contiguous halves along the wider axis -- the strictest within-site
    split: no test cell is adjacent to a training cell except along one seam."""
    if (R.max() - R.min()) >= (C.max() - C.min()):
        mid = (R.min() + R.max()) / 2
        return R <= mid, R > mid
    mid = (C.min() + C.max()) / 2
    return C <= mid, C > mid


def main():
    print("=" * 74)
    print("ITEM 21 PHASE 0 -- supplementary diagnostics")
    print("=" * 74)
    data = {k: load_site(k) for k in SITES}
    out = {}

    for k, d in data.items():
        print(f"\n{'='*74}\n{d['label']}  ({len(d['y'])} cells)\n{'='*74}")

        # ---- (A) leakage sweep ----------------------------------------
        print("\n(A) SPATIAL LEAKAGE -- does the split explain the score?")
        print(f"  {'split':<28}{'n_train':>9}{'n_test':>8}"
              f"{'ridge':>9}{'gbt':>8}")
        rows = {}
        for bm in BLOCK_SWEEP_M:
            tr_m, te_m = split_checker(d["R"], d["C"], bm)
            if tr_m.sum() < 200 or te_m.sum() < 200:
                continue
            r_ridge = fit(d["X"][tr_m], d["y"][tr_m],
                          d["X"][te_m], d["y"][te_m], "ridge")
            r_gbt = fit(d["X"][tr_m], d["y"][tr_m],
                        d["X"][te_m], d["y"][te_m], "gbt")
            rows[f"{bm} m checkerboard"] = (r_ridge, r_gbt)
            print(f"  {bm} m checkerboard{'':<11}{tr_m.sum():>9}"
                  f"{te_m.sum():>8}{r_ridge:>9.3f}{r_gbt:>8.3f}")
        tr_m, te_m = split_halves(d["R"], d["C"])
        r_ridge = fit(d["X"][tr_m], d["y"][tr_m],
                      d["X"][te_m], d["y"][te_m], "ridge")
        r_gbt = fit(d["X"][tr_m], d["y"][tr_m],
                    d["X"][te_m], d["y"][te_m], "gbt")
        rows["contiguous halves (strictest)"] = (r_ridge, r_gbt)
        print(f"  contiguous halves (strict){'':<2}{tr_m.sum():>9}"
              f"{te_m.sum():>8}{r_ridge:>9.3f}{r_gbt:>8.3f}")

        if r_ridge >= STRICT_ROBUST_R2:
            call = "ROBUST -- pass stands as reported"
        elif r_ridge >= STRICT_CAVEAT_R2:
            call = "DOWNGRADE -- usable with a prominent caveat"
        else:
            call = "LEAKAGE-INFLATED -- must not be reported as WORKS"
        print(f"  -> strict-split ridge {r_ridge:.3f}: {call}")

        # ---- (B) is the easy contrast doing the work? ------------------
        print("\n(B) WHICH BOUNDARY IS BEING RESOLVED?")
        tr_m, te_m = split_checker(d["R"], d["C"], 200)
        Xtr_n, Xte_n = base.normalize("per_aoi", [d["X"][tr_m]], d["X"][te_m])
        yhat = base.fit_predict("ridge", Xtr_n, d["y"][tr_m], Xte_n)
        yte, vte, wte = d["y"][te_m], d["veg"][te_m], d["water"][te_m]
        subs = {
            "all test cells": np.ones(len(yte), bool),
            f"low vegetation (<{LOW_VEG_MAX}) -- imperv vs BARE":
                vte < LOW_VEG_MAX,
            f"high vegetation (>={LOW_VEG_MAX})": vte >= LOW_VEG_MAX,
            f"mixed cells ({MIXED_LO}<f<{MIXED_HI})":
                (yte > MIXED_LO) & (yte < MIXED_HI),
            "no water present": wte < 0.01,
        }
        sub_out = {}
        for name, m in subs.items():
            if m.sum() < 100:
                print(f"  {name:<46} n={int(m.sum()):>6}  (too few)")
                continue
            r2 = r2_score(yte[m], yhat[m])
            sub_out[name] = r2
            print(f"  {name:<46} n={int(m.sum()):>6}  R2={r2:>7.3f}"
                  f"   sd(y)={yte[m].std():.3f}")

        out[k] = {"leakage": rows, "subsets": sub_out}

    # ---- (C) cross-site transfer ---------------------------------------
    print(f"\n{'='*74}\n(C) CROSS-SITE TRANSFER -- held-out AOI, item 21's "
          f"acceptance\n{'='*74}")
    print(f"  {'train':<22}{'test':<22}{'ridge':>9}{'gbt':>8}")
    xs = {}
    for a in SITES:
        for b in SITES:
            if a == b:
                continue
            r_ridge = fit(data[a]["X"], data[a]["y"],
                          data[b]["X"], data[b]["y"], "ridge")
            r_gbt = fit(data[a]["X"], data[a]["y"],
                        data[b]["X"], data[b]["y"], "gbt")
            xs[f"{a}->{b}"] = (r_ridge, r_gbt)
            print(f"  {a:<22}{b:<22}{r_ridge:>9.3f}{r_gbt:>8.3f}")
    out["cross_site"] = xs

    sc = os.environ.get("GW_DIAG_OUT") or vhr_sites.site("kibera")["scratch"]
    with open(os.path.join(sc, "vhr_diagnostics.json"), "w") as fh:
        json.dump(out, fh, indent=2, default=float)
    print(f"\nwrote {os.path.join(sc, 'vhr_diagnostics.json')}")


if __name__ == "__main__":
    main()
