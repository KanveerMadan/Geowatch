"""
Item 21 Phase 0 — a real impervious-fraction label from free VHR imagery.

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

SCRATCH = os.environ.get(
    "GW_SCRATCH",
    "/private/tmp/claude-501/-Users-kanveermadan-geowatch/"
    "f0fb6a5f-62d2-4c09-93c4-806575bd5530/scratchpad")
UAV = os.path.join(SCRATCH, "oldfadama.tif")

AOI_BBOX = [-0.225852, 5.541892, -0.214147, 5.556530]
S2_START, S2_END = "2024-06-01", "2024-11-30"

WORKING_RES_M = 0.20          # classify at 20 cm
NATIVE_RES_M = 0.05
DS = int(round(WORKING_RES_M / NATIVE_RES_M))   # 4x downsample
PATCH_NATIVE = 100            # 5 m patches, as rendered on the contact sheets

CLASSES = ["roof", "hard_unroofed", "vegetation", "bare", "water"]
NFEAT = 14
IMPERVIOUS = {"roof", "hard_unroofed"}

# --- hand assignments, made by viewing the rendered contact sheets ---------
#
# IMPORTANT — these are the SECOND pass. The first pass was made at 1x zoom and
# contained real errors, which a held-out run exposed: bare recall was 0.29 and
# 2412 of 4375 bare pixels were predicted roof. Re-inspecting at 2x showed the
# classifier was frequently right and the labels wrong -- patches 14 and 63 are
# flat ROOFS with visible seams, and 50 and 55 are WATER with floating rubbish,
# all four of which the first pass called bare. Every patch was therefore
# re-assigned at 2x, and anything spanning two classes was discarded rather
# than forced. Discard lists below are deliberately long for that reason.
#
# sheet 1 = 64 random patches (patch_meta.json)
SHEET1 = {
    "roof": [0, 1, 3, 4, 5, 6, 7, 8, 10, 11, 12, 14, 16, 17, 18, 19, 24, 27,
             29, 31, 33, 44, 47, 51, 52, 54, 61, 63],
    "hard_unroofed": [13, 38, 46],
    "vegetation": [20, 23, 28, 35, 48, 57, 59],
    "bare": [37, 40, 41, 53, 56, 58],
    "water": [43, 50, 55],
}
# discarded as mixed/ambiguous: 2,9,15,21,22,25,26,30,32,34,36,39,42,45,49,60,62
# sheet 2 = 36 targeted patches (patch_meta2.json)
SHEET2 = {
    "water": [0, 1, 2, 3, 4, 6, 7, 10, 11, 12],
    "hard_unroofed": [13, 14, 16, 17, 21, 23],
    "vegetation": [15, 24, 26, 28, 29, 30, 31, 32, 33, 34, 35],
    "bare": [],
    "roof": [19, 20],
}
# discarded as mixed/ambiguous: 5,8,9,18,22,25,27
# sheet 3 = 36 patches from neighbourhoods of confirmed bare/hard (patch_meta3.json)
SHEET3 = {
    "bare": [1, 2, 13, 14],
    "hard_unroofed": [4, 8, 9, 18, 19, 20, 24, 25, 26, 27, 30, 31, 32, 35],
    "roof": [7, 11, 17, 33, 34],
    "vegetation": [22],
    "water": [],
}
# discarded as mixed/ambiguous: 0,3,5,6,10,12,15,16,21,23,28,29
# sheet 4 = 40 CLASSIFIER-PROPOSED bare/hard candidates (patch_meta4.json).
# The classifier proposed; every one was still verified by eye and 15 of 40
# were rejected. Proposing candidates for a rare class is far more efficient
# than random sampling -- bare is ~10% of this scene -- and does not bias the
# label, because acceptance is a human decision made on the imagery.
SHEET4 = {
    "bare": [1, 5, 12, 20, 25, 29, 31, 32, 33, 35, 37],
    "hard_unroofed": [4, 8, 19, 22, 28, 34, 38],
    "roof": [9, 13, 14, 15, 17, 23, 27],
    "vegetation": [],
    "water": [],
}
# discarded: 0,2,3,6,7,10,11,16,18,21,24,26,30,36,39


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
    meta1 = {m["i"]: m for m in json.load(
        open(os.path.join(SCRATCH, "patch_meta.json")))}
    meta2 = {m["i"]: m for m in json.load(
        open(os.path.join(SCRATCH, "patch_meta2.json")))}
    meta3 = {m["i"]: m for m in json.load(
        open(os.path.join(SCRATCH, "patch_meta3.json")))}
    meta4 = {m["i"]: m for m in json.load(
        open(os.path.join(SCRATCH, "patch_meta4.json")))}

    X, y, pid = [], [], []
    pcount = 0
    with rasterio.open(UAV) as src:
        for sheet, meta in ((SHEET1, meta1), (SHEET2, meta2), (SHEET3, meta3),
                            (SHEET4, meta4)):
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
    return (np.vstack(X), np.concatenate(y), np.concatenate(pid), pcount)


def main():
    print("=" * 74)
    print("ITEM 21 PHASE 0 — VHR impervious label, Old Fadama / Accra")
    print("=" * 74)

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
    np.save(os.path.join(SCRATCH, "vhr_classifier_classes.npy"),
            np.array(CLASSES))
    import pickle
    with open(os.path.join(SCRATCH, "vhr_clf.pkl"), "wb") as fh:
        pickle.dump(clf_full, fh)
    print(f"\nclassifier refit on all {npatch} patches and saved")
    print(f"held-out accuracy above is the honest estimate of label quality")


if __name__ == "__main__":
    main()
