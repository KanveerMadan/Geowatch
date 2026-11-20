# M5 coastal: evidence

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

**FAILED** (pre-registered). Learned `open__lgbm` on 13 reserved units (8 clusters): mean AUC 0.795, Δ vs HAND +0.042 [-0.028, +0.098]. Plain low elevation scored 0.806 on the same cells — higher than the learned model.

| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |
|---|---|---|---|
| learned `open__lgbm` (pre-registered) | 0.795 [0.717, 0.869] | +0.042 [-0.028, +0.098] | 13 |
| learned, isotonic-calibrated output | 0.787 [0.707, 0.864] | +0.034 [-0.042, +0.091] | 13 |
| HAND | 0.752 [0.678, 0.827] | — | 13 |
| low elevation (GLO-30), not pre-registered | 0.806 [0.721, 0.889] | +0.054 [-0.009, +0.111] | 13 |
| JRC occurrence | 0.538 [0.503, 0.575] | -0.215 [-0.285, -0.144] | 13 |
| distance to mapped water | 0.649 [0.528, 0.760] | -0.103 [-0.235, -0.010] | 13 |
| learned `open__logreg` (not chosen) | 0.820 [0.740, 0.888] | +0.068 [+0.020, +0.110] | 13 |

Per reserved unit (raw-score AUC):

| unit | region | flooded / dry | learned | HAND | low elevation |
|---|---|---|---|---|---|
| r_emsr703_aoi01 | americas | 1,287 / 12,951 | 0.799 | 0.693 | 0.833 |
| r_emsr703_aoi02 | americas | 3,331 / 10,729 | 0.629 | 0.625 | 0.661 |
| r_emsr805_aoi01 | americas | 184 / 6,316 | 0.679 | 0.656 | 0.655 |
| r_emsr805_aoi03 | americas | 83 / 17,611 | 0.798 | 0.733 | 0.725 |
| r_emsr734_aoi17 | americas | 250 / 12,415 | 0.617 | 0.900 | 0.690 |
| r_emsr781_aoi01 | africa | 105 / 10,901 | 0.935 | 0.767 | 0.949 |
| r_emsr793_aoi01 | africa | 1,310 / 16,360 | 0.956 | 0.859 | 0.961 |
| r_emsr793_aoi02 | africa | 775 / 16,921 | 0.907 | 0.947 | 0.934 |
| r_emsr867_aoi01 | africa | 212 / 11,601 | 0.629 | 0.504 | 0.608 |
| r_emsr867_aoi03 | africa | 1,535 / 16,190 | 0.799 | 0.799 | 0.783 |
| r_emsr863_aoi02 | africa | 2,811 / 13,507 | 0.860 | 0.762 | 0.881 |
| r_emsr858_aoi08 | europe_mediterranean | 618 / 17,124 | 0.892 | 0.750 | 0.891 |
| r_emsr858_aoi10 | europe_mediterranean | 805 / 16,962 | 0.830 | 0.788 | 0.913 |

Not scored: see `data_manifest.csv` (`heldout_status`).

## 3. DEV (leave-region-out, out-of-fold; method choice)

4 clusters, 5 units.

| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |
|---|---|---|---|
| learned `open__lgbm` (chosen) | 0.763 [0.587, 0.880] | +0.084 [-0.034, +0.190] | 5 |
| learned `open__logreg` | 0.725 [0.576, 0.843] | +0.046 [-0.097, +0.175] | 5 |
| learned without land cover | 0.700 [0.497, 0.831] | +0.021 [-0.097, +0.113] | 5 |
| HAND | 0.679 [0.558, 0.749] | — | 5 |
| low elevation (GLO-30) | 0.778 [0.624, 0.863] | +0.099 [+0.039, +0.164] | 5 |

Figures: `figures/fig_dev_per_event_auc.png`, `figures/fig_heldout_per_event_auc.png`.
