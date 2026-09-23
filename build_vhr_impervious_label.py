"""
Item 21 Phase 0 — a real impervious-fraction label from free VHR imagery.

SITE-PARAMETERISED. This script originally hard-coded Old Fadama / Agbogbloshie
(Accra). It now takes its site from `vhr_sites.SITES`, selected by the GW_SITE
environment variable and DEFAULTING TO `oldfadama`, so running it with no
arguments reproduces the Phase 0 result unchanged. The per-site configuration
and the hand-assigned patch labels both live in `vhr_sites.py`; the method
below -- features, patch-level accuracy protocol, refit -- is identical for
every site. See `vhr_sites.py` for the re-run's pre-registration.

Why
---
06_UNMIXING_CEILING.md establishes that `impervious_total` has a simulated
ceiling of R2 0.822, versus 0.490 for `built` alone. That number has never been
tested on real data because no real impervious label exists: the only available
paved source, unroofed OSM polygons, covers 0.23-1.82% of the pilot AOIs
against a built mean of 19-30%, which is why Direction C returned null.

This script builds the missing label from centimetre-scale UAV imagery.

SOURCE, verified live rather than trusted from 03_EVIDENCE.md C.1
------------------------------------------------------------------
OpenAerialMap, queried 2026-09-09. C.1's record of three settlements was
re-checked against the live API; all three resolve. Chosen scene:

  "Oldfadama Agbogloshie_combined_high_compression"
  Old Fadama / Agbogbloshie, Accra
  acquired 2024-08-26, GSD 0.049998 m, 145 MB
  bbox  -0.225852, 5.541892, -0.214147, 5.556530
  EPSG:32630, 32281 x 25811, 3-band uint8 RGB

Verified on open: CRS, band count, dtype and bounds all match the API record.
~36% of the rectangle is nodata (the mosaic footprint is irregular), leaving
roughly 1.33 km2 usable, about 13,000 10 m cells.

TEMPORAL MATCHING. The UAV is 2024-08. The S2 composite used elsewhere in this
investigation is 2026-04 to 2026-07. A two-year gap in an informal settlement
would corrupt the label, so the composite here is rebuilt over 2024-06-01 to
2024-11-30 (13 images) to bracket the UAV acquisition.

METHOD -- a supervised classifier, stated plainly
--------------------------------------------------
The label is MODEL-GENERATED, not hand-digitised wall-to-wall. Its own error
therefore caps everything measured against it, and its accuracy is reported
below rather than assumed.

  1. 100 random 5 m x 5 m patches were rendered as contact sheets and each was
     visually assigned a class by inspection. Patches spanning more than one
     class were discarded rather than forced.
  2. Random sampling under-hit water and hard-unroofed, so a second targeted
     round sampled the lagoon, the highway/apron area and the vegetated block.
     Those hints were treated as candidates only -- every patch was still
     assigned by looking at it.
  3. A random forest is trained at WORKING_RES_M on colour plus texture.
     Colour alone provably cannot work here: rust roofs match bare soil and
     teal roofs match vegetation. Roofs are smooth and planar, bare is mottled,
     vegetation is highly textured -- so local standard deviation at two scales
     carries the discrimination.
  4. Accuracy is measured on a PATCH-LEVEL held-out split, never a pixel-level
     one. Pixels inside a 5 m patch are near-identical; a random pixel split
     would report ~99% and mean nothing. This is the same spatial-leakage trap
     A.13 warns about, one level down.

CLASSES: roof, hard_unroofed, vegetation, bare, water.
  impervious = roof + hard_unroofed.
Roof and hard_unroofed are stored SEPARATELY even though the target is their
sum, so the built/paved split can be checked empirically later at no extra cost
now.

OUTPUT: continuous impervious fraction per 10 m cell on the REAL Sentinel-2
grid, obtained from `diagnose_pure_pixels.s2_grid_for` rather than re-derived.
The UAV is EPSG:32630 and the S2 grid over Accra is the same UTM zone, so
aggregation is an exact block reduction with no reprojection of the label.

Usage:
    python build_vhr_impervious_label.py
"""

import json
import os

import numpy as np
import rasterio
from rasterio.windows import Window
from scipy.ndimage import uniform_filter
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix

import diagnose_pure_pixels as pure_diag
import ee

import vhr_sites

SITE = vhr_sites.site()

SCRATCH = SITE["scratch"]
UAV = SITE["raster_path"]          # kept as `UAV` for interface stability;
                                   # note the Nairobi site is satellite, not UAV

AOI_BBOX = SITE["bbox"]
S2_START, S2_END = SITE["s2_start"], SITE["s2_end"]

WORKING_RES_M = SITE["working_res_m"]
NATIVE_RES_M = SITE["native_res_m"]
DS = SITE["ds"]                    # native -> working downsample factor
PATCH_NATIVE = SITE["patch_native"]

CLASSES = vhr_sites.CLASSES
NFEAT = vhr_sites.NFEAT
IMPERVIOUS = vhr_sites.IMPERVIOUS


def features(rgb):
    """rgb: (H,W,3) float. Returns (H,W,F) feature stack.

    Colour cannot separate these classes on its own -- rust roofs match bare
    soil, teal roofs match vegetation. Texture is what carries it.
    """
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    s = r + g + b + 1e-6
    bright = s / 3.0
    gex = (2 * g - r - b) / s          # green excess; no NIR available
    rex = (2 * r - g - b) / s

    def lstd(a, w):
        m = uniform_filter(a, w)
        m2 = uniform_filter(a * a, w)
        return np.sqrt(np.maximum(m2 - m * m, 0))

    # Structure-tensor coherence: are local gradients ALIGNED or isotropic?
    # This targets the confusion the first run exposed -- a roof panel is
    # planar with straight seams (high coherence), while rubbish and bare
    # ground are isotropically textured (low coherence). Colour cannot make
    # that distinction; this can.
    gy, gx = np.gradient(bright)
    def coh(w):
        jxx = uniform_filter(gx * gx, w)
        jyy = uniform_filter(gy * gy, w)
        jxy = uniform_filter(gx * gy, w)
        num = np.sqrt((jxx - jyy) ** 2 + 4 * jxy ** 2)
        return num / (jxx + jyy + 1e-6)

    return np.dstack([
        r, g, b, bright, gex, rex,
        lstd(bright, 3), lstd(bright, 9), lstd(bright, 21),
        lstd(gex, 9),
        uniform_filter(bright, 9),
        coh(9), coh(21),
        np.abs(gx) + np.abs(gy),
    ]).astype(np.float32)


def read_patch(src, r, c, size=PATCH_NATIVE):
    a = src.read(window=Window(c, r, size, size),
                 out_shape=(3, size // DS, size // DS))
    return np.transpose(a, (1, 2, 0)).astype(np.float32)


def build_training():
    """Load every hand-assigned patch for the active site.

    Sheets are (meta_filename, {class: [patch indices]}) pairs from
    `vhr_sites`. Indices absent from every list were DISCARDED as mixed or
    ambiguous rather than forced into a class.
    """
    X, y, pid = [], [], []
    pcount = 0
    with rasterio.open(UAV) as src:
        for fname, sheet in SITE["sheets"]:
            meta = {m["i"]: m for m in json.load(
                open(os.path.join(SCRATCH, fname)))}
            for cls, idxs in sheet.items():
                for i in idxs:
                    m = meta[i]
                    rgb = read_patch(src, m["r"], m["c"])
                    if (rgb.sum(2) == 0).mean() > 0.02:
                        continue
                    F = features(rgb).reshape(-1, NFEAT)
                    X.append(F)
                    y.append(np.full(len(F), CLASSES.index(cls)))
                    pid.append(np.full(len(F), pcount))
                    pcount += 1
    if not X:
        raise SystemExit(f"no labelled patches for site {SITE['key']!r}")
    return (np.vstack(X), np.concatenate(y), np.concatenate(pid), pcount)


def main():
    print("=" * 74)
    print(f"ITEM 21 PHASE 0 — VHR impervious label, {SITE['label']}")
    print("=" * 74)
    print(f"  site={SITE['key']}  sensor={SITE['sensor']}")
    print(f"  acquired={SITE['acquired']}  native={NATIVE_RES_M} m  "
          f"working={WORKING_RES_M} m  patch={SITE['patch_m']} m")
    print(f"  S2 composite window {S2_START}..{S2_END}")

    X, y, pid, npatch = build_training()
    print(f"\ntraining: {npatch} hand-assigned patches, {len(X)} pixels "
          f"at {WORKING_RES_M} m")
    for i, c in enumerate(CLASSES):
        n_p = len(np.unique(pid[y == i]))
        print(f"  {c:<14} {n_p:>3} patches  {int((y == i).sum()):>7} px")

    # PATCH-level split. A pixel-level split would leak: pixels inside one
    # 5 m patch are near-identical and would appear on both sides.
    rng = np.random.default_rng(0)
    order = rng.permutation(npatch)
    n_tr = int(npatch * 0.7)
    tr_p, te_p = set(order[:n_tr].tolist()), set(order[n_tr:].tolist())
    tr = np.isin(pid, list(tr_p))
    te = np.isin(pid, list(te_p))
    print(f"\npatch-level split: {len(tr_p)} train / {len(te_p)} test patches")
    print("  (NOT a pixel split -- that would leak and report ~99% falsely)")

    clf = RandomForestClassifier(n_estimators=200, min_samples_leaf=4,
                                 n_jobs=-1, random_state=0,
                                 class_weight="balanced")
    clf.fit(X[tr], y[tr])
    pred = clf.predict(X[te])

    print("\nHELD-OUT ACCURACY (patch-level split):")
    print(classification_report(y[te], pred, labels=range(len(CLASSES)),
                                target_names=CLASSES, zero_division=0))
    acc = float((pred == y[te]).mean())
    print(f"  overall pixel accuracy on held-out patches: {acc:.3f}")

    # The number that actually matters for the label: impervious vs not.
    imp_idx = [CLASSES.index(c) for c in IMPERVIOUS]
    yb = np.isin(y[te], imp_idx)
    pb = np.isin(pred, imp_idx)
    binacc = float((yb == pb).mean())
    tp = int((yb & pb).sum()); fp = int((~yb & pb).sum())
    fn = int((yb & ~pb).sum()); tn = int((~yb & ~pb).sum())
    print(f"\n  IMPERVIOUS vs NOT (the label's actual job): acc={binacc:.3f}")
    print(f"    TP={tp} FP={fp} FN={fn} TN={tn}")
    if tp + fp:
        print(f"    precision={tp/(tp+fp):.3f}", end="")
    if tp + fn:
        print(f"  recall={tp/(tp+fn):.3f}")
    print("\n  confusion (rows=true, cols=pred):")
    print("   ", CLASSES)
    for row, cname in zip(confusion_matrix(y[te], pred,
                                           labels=range(len(CLASSES))),
                          CLASSES):
        print(f"    {cname:<14}", row)

    # Refit on everything for the production label.
    clf_full = RandomForestClassifier(n_estimators=200, min_samples_leaf=4,
                                      n_jobs=-1, random_state=0,
                                      class_weight="balanced")
    clf_full.fit(X, y)
    np.save(os.path.join(SCRATCH, f"vhr_classes_{SITE['key']}.npy"),
            np.array(CLASSES))
    import pickle
    with open(os.path.join(SCRATCH, f"vhr_clf_{SITE['key']}.pkl"), "wb") as fh:
        pickle.dump(clf_full, fh)
    # Persist the measured label quality so the regression step reads it
    # rather than having it retyped -- the pre-registered de-confounding gate
    # in `vhr_sites` is checked against this number.
    metrics = {"site": SITE["key"], "n_patches": npatch,
               "five_class_acc": acc, "binary_acc": binacc,
               "precision": tp / (tp + fp) if tp + fp else None,
               "recall": tp / (tp + fn) if tp + fn else None}
    with open(os.path.join(SCRATCH,
                           f"vhr_label_metrics_{SITE['key']}.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)

    print(f"\nclassifier refit on all {npatch} patches and saved")
    print(f"held-out accuracy above is the honest estimate of label quality")


if __name__ == "__main__":
    main()
