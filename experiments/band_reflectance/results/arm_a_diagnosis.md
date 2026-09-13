# Arm A does not reproduce the production baseline — diagnosis log

Arm A is the current production configuration (RGB + per-tile percentile
stretch). It should land near the per-fold Accra value from the documented
0.313 ± 0.056 LOCO run. It scores **0.0221**, with six of seven classes at
exactly 0.0000, and its training loss is **flat from epoch 0** — it never
learns, it does not diverge.

Arm B (RGB + absolute reflectance) differs **only in the input array** and
converges immediately, to loss 0.02.

## What production actually used, recovered from the checkpoint-producing notebook

`notebooks/archive/geowatch_water_loco_with_diagnostics (2).ipynb` — identified
by `archive/AUDIT_FINDINGS.md:689` as the notebook that produced the deployed
checkpoint — uses a **composite loss and discriminative learning rates**, none
of which the first probe had:

    CrossEntropyLoss(weight=class_weights, ignore_index=...)
      + dice_loss
      + separation_weight * separation_loss      (weight 0.5, margin 2.0)

    AdamW([{encoder: lr 1e-5}, {decoder: lr 3e-4}])
    CosineAnnealingLR(T_max=NUM_EPOCHS, eta_min=1e-6)

The probe had used a single `lr=3e-4` for all parameters — 30× too high for the
encoder — and unweighted CE.

## What was tested, and ruled out

Each run is 10 epochs, fold 0, identical patches, seed 1337.

| hypothesis | test | Arm A result | verdict |
|---|---|---|---|
| unweighted CE | `class_weights` from the checkpoint | 1.847 → 1.827 | **not it** |
| missing Dice term | weighted CE + Dice | 2.756 → 2.718 | **not it** |
| encoder LR 30× too high | encoder 1e-5 / decoder 3e-4 + cosine | 1.839 → 1.846 | **not it** |
| per-city stretch inconsistency | train on ONE city only | 1.468 → 1.401 | **not it** |
| input magnitude | ×0.27 to match B's mean | 1.839 → 1.816 | **not it** |
| input magnitude | full standardisation (0 mean, unit std) | 1.848 → 1.828 | **not it** |
| label/image misalignment | Pearson r, PNG vs raw.tif, per channel | r = 0.948–0.993 | **aligned** |
| degenerate input | NaN/Inf, distinct values, channel corr | 0 NaN, 256 levels, r≈0.96 | **clean** |

Arm B, under the same conditions, goes 0.494 → 0.021 (ten cities) and
0.188 → 0.005 (one city).

## Where that leaves it

The root cause is **not found**. What is established is that the gap is in this
reproduction rather than in the stretched input as such — production trains on
exactly this input and reaches 0.313.

The largest remaining un-replicable difference is the **training data
construction**. Production consumed a Colab-built dataset of 1,272 patches
(`/content/data/{city}/`) whose construction is not in this repository. This
probe samples patches from `tile_0_0.png` against a label canvas, requiring only
≥32 labelled pixels out of 4,096 — about 0.8% supervision density per patch.
Arm B learns from those same sparse patches, so sparsity alone is not the
explanation, but sparsity combined with the higher-variance stretched input may
be.

**Not proceeding to 11 folds.** An experiment whose control is broken cannot
attribute anything, and the most eye-catching number in the results table would
be measuring this bug rather than any real effect.
