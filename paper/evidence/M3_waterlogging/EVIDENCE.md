# M3 waterlogging: evidence

Every number is in `tables/` with its source file and commit.

## 1. Criteria fixed before scoring
- `experiments/flood_final/PREREGISTRATION.md`, sha256 `e49bca3f99380867f0a8c7a4b36b62c0c806479a356f20ab6366fb11067db9a4`.
- Companion record (`PREREG_HASH.txt`):

```
file:            experiments/flood_final/PREREGISTRATION.md
sha256:          e49bca3f99380867f0a8c7a4b36b62c0c806479a356f20ab6366fb11067db9a4
commit:          eed20fea6f9c3f03e7f47fd191139f7b267bd506 (branch exp/flood-final)
pushed (UTC):    2026-11-19T07:37:07Z  (origin/exp/flood-final == eed20fe at that time, checked with git ls-remote)
registry commit: c6fb5b11fa3f0695b1af23afd300ba557fc674fb (reserved units added; pushed before the pre-registration)
reserved data read before this push: none (references, input layers and scores of RESERVED units untouched)
check:           shasum -a 256 experiments/flood_final/PREREGISTRATION.md
```

- Freeze tag `flood-final-heldout-freeze` = `81ff7b1` (code, method_choice.json and final-model hashes). The held-out run checked both before reading any reserved data; run 2026-11-20T14:14:08Z.

## 2. Held-out verdict: PASSED

**PASSED** (pre-registered). Learned `open__logreg` on 3 reserved units (2 clusters): mean AUC 0.791, Δ vs HAND +0.167 [+0.118, +0.226]. Plain low elevation scored 0.843 on the same cells — higher than the learned model.

| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |
|---|---|---|---|
| learned `open__logreg` (pre-registered) | 0.791 [0.715, 0.842] | +0.167 [+0.118, +0.226] | 3 |
| learned, isotonic-calibrated output | 0.788 [0.715, 0.836] | +0.164 [+0.117, +0.223] | 3 |
| HAND | 0.624 [0.520, 0.696] | — | 3 |
| low elevation (GLO-30), not pre-registered | 0.843 [0.597, 0.965] | +0.219 [+0.052, +0.343] | 3 |
| JRC occurrence | 0.509 [0.502, 0.523] | -0.115 [-0.189, -0.007] | 3 |
| distance to mapped water | 0.533 [0.441, 0.645] | -0.090 [-0.238, +0.089] | 3 |
| production module `waterlogging` | 0.679 [0.545, 0.765] | +0.055 [+0.002, +0.099] | 3 |
| learned `open__lgbm` (not chosen) | 0.746 [0.693, 0.803] | +0.122 [+0.053, +0.199] | 3 |

Per reserved unit (raw-score AUC):

| unit | region | flooded / dry | learned | HAND | low elevation |
|---|---|---|---|---|---|
| r_emsr856_aoi01 | europe_mediterranean | 3,340 / 14,440 | 0.813 | 0.622 | 0.915 |
| r_emsr856_aoi02 | europe_mediterranean | 1,554 / 12,340 | 0.823 | 0.696 | 0.981 |
| s1_yenagoa_2022 | africa | 2,773 / 14,959 | 0.736 | 0.554 | 0.633 |

Not scored: see `data_manifest.csv` (`heldout_status`).

## 3. DEV (leave-region-out, out-of-fold; method choice)

6 clusters, 12 units.

| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |
|---|---|---|---|
| learned `open__logreg` (chosen) | 0.727 [0.657, 0.804] | +0.131 [+0.048, +0.221] | 12 |
| learned `open__lgbm` | 0.700 [0.598, 0.804] | +0.103 [+0.029, +0.171] | 12 |
| learned without land cover | 0.596 [0.496, 0.693] | -0.001 [-0.041, +0.045] | 12 |
| HAND | 0.596 [0.475, 0.696] | — | 12 |
| low elevation (GLO-30) | 0.693 [0.540, 0.804] | +0.096 [+0.009, +0.178] | 12 |
| module `waterlogging` | 0.591 [0.539, 0.659] | -0.005 [-0.098, +0.095] | 12 |

Figures: `figures/fig_dev_per_event_auc.png`, `figures/fig_heldout_per_event_auc.png`.
