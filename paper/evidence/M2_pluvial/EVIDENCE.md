# M2 pluvial (rain / urban): evidence

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

**FAILED** (pre-registered). Learned `open__lgbm` on 4 reserved units (3 clusters): mean AUC 0.703, Δ vs HAND +0.039 [-0.035, +0.112]. Plain low elevation scored 0.798 on the same cells — higher than the learned model.

| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |
|---|---|---|---|
| learned `open__lgbm` (pre-registered) | 0.703 [0.524, 0.857] | +0.039 [-0.035, +0.112] | 4 |
| learned, isotonic-calibrated output | 0.694 [0.489, 0.857] | +0.030 [-0.036, +0.104] | 4 |
| HAND | 0.664 [0.447, 0.890] | — | 4 |
| low elevation (GLO-30), not pre-registered | 0.798 [0.424, 0.959] | +0.134 [-0.066, +0.296] | 4 |
| JRC occurrence | 0.496 [0.489, 0.502] | -0.168 [-0.388, +0.043] | 4 |
| distance to mapped water | 0.757 [0.552, 0.865] | +0.094 [-0.101, +0.234] | 4 |
| production module `pluvial` | 0.654 [0.449, 0.793] | -0.010 [-0.316, +0.142] | 4 |
| learned `open__logreg` (not chosen) | 0.695 [0.482, 0.838] | +0.031 [-0.053, +0.109] | 4 |

Per reserved unit (raw-score AUC):

| unit | region | flooded / dry | learned | HAND | low elevation |
|---|---|---|---|---|---|
| r_emsr742_aoi01 | europe_mediterranean | 187 / 17,538 | 0.923 | 0.696 | 0.946 |
| r_emsr742_aoi03 | europe_mediterranean | 248 / 17,591 | 0.507 | 0.626 | 0.969 |
| r_emsr790_aoi02 | africa | 283 / 16,949 | 0.866 | 0.896 | 0.862 |
| r_emsr780_aoi08 | africa | 1,524 / 10,392 | 0.514 | 0.436 | 0.414 |

Not scored: see `data_manifest.csv` (`heldout_status`).

## 3. DEV (leave-region-out, out-of-fold; method choice)

9 clusters, 11 units.

| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |
|---|---|---|---|
| learned `open__lgbm` (chosen) | 0.675 [0.583, 0.741] | +0.013 [-0.083, +0.080] | 11 |
| learned `open__logreg` | 0.644 [0.526, 0.724] | -0.018 [-0.176, +0.092] | 11 |
| learned without land cover | 0.658 [0.579, 0.737] | -0.004 [-0.094, +0.086] | 11 |
| HAND | 0.662 [0.594, 0.733] | — | 11 |
| low elevation (GLO-30) | 0.705 [0.594, 0.800] | +0.042 [-0.070, +0.148] | 11 |
| module `pluvial` | 0.586 [0.492, 0.698] | -0.090 [-0.184, +0.020] | 6 |

Figures: `figures/fig_dev_per_event_auc.png`, `figures/fig_heldout_per_event_auc.png`.
