# M4 flash flood: evidence

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

## 2. Held-out verdict: FAILED

**FAILED** (pre-registered). Learned `open__lgbm` on 6 reserved units (3 clusters): mean AUC 0.810, Δ vs HAND -0.017 [-0.060, +0.026]. Plain low elevation scored 0.862 on the same cells — higher than the learned model.

| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |
|---|---|---|---|
| learned `open__lgbm` (pre-registered) | 0.810 [0.703, 0.941] | -0.017 [-0.060, +0.026] | 6 |
| learned, isotonic-calibrated output | 0.808 [0.702, 0.936] | -0.019 [-0.061, +0.023] | 6 |
| HAND | 0.826 [0.734, 0.917] | — | 6 |
| low elevation (GLO-30), not pre-registered | 0.862 [0.792, 0.936] | +0.035 [+0.004, +0.094] | 6 |
| JRC occurrence | 0.537 [0.507, 0.566] | -0.290 [-0.354, -0.199] | 6 |
| distance to mapped water | 0.697 [0.546, 0.814] | -0.130 [-0.265, +0.018] | 6 |
| production module `flash_flood` | 0.814 [0.699, 0.946] | -0.012 [-0.104, +0.064] | 6 |
| learned `open__logreg` (not chosen) | 0.776 [0.657, 0.934] | -0.050 [-0.119, +0.020] | 6 |

Per reserved unit (raw-score AUC):

| unit | region | flooded / dry | learned | HAND | low elevation |
|---|---|---|---|---|---|
| r_emsr845_aoi02 | americas | 771 / 16,955 | 0.740 | 0.771 | 0.927 |
| r_emsr845_aoi03 | americas | 1,896 / 14,615 | 0.694 | 0.707 | 0.684 |
| r_emsr850_aoi02 | europe_mediterranean | 595 / 17,159 | 0.773 | 0.847 | 0.853 |
| r_emsr850_aoi03 | europe_mediterranean | 1,305 / 16,468 | 0.771 | 0.797 | 0.831 |
| r_emsr864_aoi01 | europe_mediterranean | 4,179 / 13,207 | 0.924 | 0.924 | 0.955 |
| r_emsr864_aoi02 | europe_mediterranean | 3,330 / 13,545 | 0.956 | 0.912 | 0.920 |

Not scored: see `data_manifest.csv` (`heldout_status`).

## 3. DEV (leave-region-out, out-of-fold; method choice)

8 clusters, 17 units.

| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |
|---|---|---|---|
| learned `open__lgbm` (chosen) | 0.750 [0.664, 0.806] | +0.079 [+0.006, +0.139] | 17 |
| learned `open__logreg` | 0.701 [0.606, 0.772] | +0.030 [-0.066, +0.122] | 17 |
| learned without land cover | 0.674 [0.568, 0.740] | +0.003 [-0.084, +0.080] | 17 |
| HAND | 0.671 [0.607, 0.727] | — | 17 |
| low elevation (GLO-30) | 0.710 [0.625, 0.767] | +0.039 [-0.019, +0.084] | 17 |
| module `flash_flood` | 0.674 [0.596, 0.727] | +0.003 [-0.054, +0.061] | 17 |

Figures: `figures/fig_dev_per_event_auc.png`, `figures/fig_heldout_per_event_auc.png`.
