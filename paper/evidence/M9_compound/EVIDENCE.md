# M9 compound: evidence

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

**FAILED** (pre-registered). Learned `open__lgbm` on 5 reserved units (3 clusters): mean AUC 0.844, Δ vs HAND -0.011 [-0.259, +0.096]. Plain low elevation scored 0.874 on the same cells — higher than the learned model.

| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |
|---|---|---|---|
| learned `open__lgbm` (pre-registered) | 0.844 [0.627, 0.941] | -0.011 [-0.259, +0.096] | 5 |
| learned, isotonic-calibrated output | 0.831 [0.582, 0.937] | -0.024 [-0.304, +0.091] | 5 |
| HAND | 0.855 [0.759, 0.924] | — | 5 |
| low elevation (GLO-30), not pre-registered | 0.874 [0.684, 0.942] | +0.019 [-0.193, +0.128] | 5 |
| JRC occurrence | 0.525 [0.499, 0.563] | -0.330 [-0.393, -0.252] | 5 |
| distance to mapped water | 0.693 [0.256, 0.832] | -0.162 [-0.631, +0.022] | 5 |
| learned `open__logreg` (not chosen) | 0.906 [0.834, 0.955] | +0.051 [+0.012, +0.101] | 5 |

Per reserved unit (raw-score AUC):

| unit | region | flooded / dry | learned | HAND | low elevation |
|---|---|---|---|---|---|
| r_emsr734_aoi17 | americas | 250 / 12,415 | 0.617 | 0.900 | 0.690 |
| r_emsr858_aoi08 | europe_mediterranean | 618 / 17,124 | 0.892 | 0.750 | 0.891 |
| r_emsr858_aoi10 | europe_mediterranean | 805 / 16,962 | 0.830 | 0.788 | 0.913 |
| r_emsr864_aoi01 | europe_mediterranean | 4,179 / 13,207 | 0.924 | 0.924 | 0.955 |
| r_emsr864_aoi02 | europe_mediterranean | 3,330 / 13,545 | 0.956 | 0.912 | 0.920 |

Not scored: see `data_manifest.csv` (`heldout_status`).

## 3. DEV (leave-region-out, out-of-fold; method choice)

5 clusters, 7 units.

| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |
|---|---|---|---|
| learned `open__lgbm` (chosen) | 0.727 [0.601, 0.839] | +0.070 [-0.017, +0.157] | 7 |
| learned `open__logreg` | 0.686 [0.576, 0.805] | +0.029 [-0.064, +0.137] | 7 |
| learned without land cover | 0.639 [0.487, 0.778] | -0.018 [-0.118, +0.081] | 7 |
| HAND | 0.657 [0.563, 0.727] | — | 7 |
| low elevation (GLO-30) | 0.721 [0.599, 0.831] | +0.064 [-0.006, +0.140] | 7 |

Figures: `figures/fig_dev_per_event_auc.png`, `figures/fig_heldout_per_event_auc.png`.
