# Appendix: flood round 2 (development round)

In the paper, round 2 is the **development round** and round 3 is the confirmation. Round 2's records stay where they are on `exp/flood-round2`, unedited. This page only points to them.

## Records
| item | value |
|---|---|
| pre-registration | `experiments/flood_round2/PREREGISTRATION_ROUND2.md`, sha256 `7a06490cd79911568df20d823d2ee74b6d663618fe663f13caa40bb1d644b29f`, commit `9853dd6`, pushed 2026-11-21T10:07:11Z |
| hash record | `experiments/flood_round2/PREREG_HASH_ROUND2.txt` (commit `ae0022a`) |
| method choice (DEV) | `results/method_choice_r2.json`, commit `e6c2796`, sha256 `ca0c9cb6…28b0` |
| freeze tag | `flood-round2-heldout-freeze` = `50fab0a` |
| one held-out pass | `results/heldout_r2.json`, run 2026-11-22T02:39:26Z, sha256 `231710fb91a8b543e86c1532280aab4ade587b5c73a4f08e0ad47deb86580dd0` |
| reading | `experiments/flood_round2/DECISIONS.md` R17 (commit `07e9920`) |

## Result (scored once; final for round 2)
Bar: mean within-event AUC ≥ 0.70, and the lower 95 % bound of the gain over the better of {elevation, HAND} > 0, on ≥ 5 qualifying units in ≥ 3 clusters. Intervals come from a 990 m block × cluster bootstrap.

| type | chosen | mean AUC | vs | gain, mean [95 % CI] | units / clusters | verdict |
|---|---|---|---|---|---|---|
| river | resid_lgbm | 0.912 | elev | +0.015 [−0.004, +0.044] | 17 / 11 | failed |
| rain | elev | 0.611 | hand | +0.014 [−0.019, +0.048] | 16 / 16 | failed |
| waterlogging | full_lr | 0.719 | elev | +0.012 [−0.035, +0.054] | 10 / 10 | failed |
| flash | resid_lgbm | 0.825 | elev | +0.016 [−0.008, +0.043] | 7 / 4 | failed |
| coastal | elev | — | — | — | 4 / 4 | not run (< 5 units) |
| compound | full_lgbm | 0.665 | elev | −0.082 [−0.239, +0.015] | 5 / 5 | failed |

**Lost units: 8 of 63.**
- No usable Sentinel-1 pass (no baseline or event image): 3 (s1_biparjoy_jakhau_2023, s1_manila_2024, s1_bentiu_2022).
- Fewer than 50 flooded cells: 3 (r_emsr668_aoi01, r_emsr783_aoi01, r_emsr783_aoi03).
- No flood centre in the product: 2 (r_emsr927_aoi01, r_emsr927_aoi02).

## What changed afterwards
- **Product (2026-11-22, PR #1 commit `39d31e4`):**
  - the learned river/waterlogging output is withdrawn, and replaced by plain elevation ranking (`flood_ranking`, `experimental`);
  - no flood output is `validated` now.
- **Round 3 data:** every round-1 and round-2 test unit is now **burned**. Round 3 uses them freely for training and diagnosis, and never for its own test.
