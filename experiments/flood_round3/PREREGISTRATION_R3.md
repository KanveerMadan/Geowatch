# Round 3 pre-registration: the one-shot held-out test

Written after the reserve seal (`RESERVE_HASH_R3.txt`, commit 1aae79a, tag `r3-reserve-seal`) and before any reserve label, feature table or score exists. The freeze (`FREEZE_R3.txt`, tag `r3-freeze`) hashes this file with the code and the frozen models. After the freeze nothing changes before the single scoring run.

## 1. The bar (unchanged from rounds 1–2)
- **Score:** within-unit AUC, from the flood_baselines scorer, with a paired 990 m block × cluster bootstrap (`model_r3.gain_lower_bound`).
- **Gain:** the method's mean AUC minus that of the **stronger of elevation and HAND** on the same units (R35: a baseline cannot pass).
- **A type passes only if all hold:**
  - the 95 % lower bound of the gain is > 0;
  - the method's mean AUC is ≥ 0.70;
  - there are ≥ 5 usable units, each with ≥ 50 flooded and ≥ 50 dry cells.
- **No power gate (owner, 2026-11-28):** a type is tested at whatever size the seal gave, and its achieved power is reported.

## 2. Method per type (DEV rule, `results/dev_cv_r3.json`; R35 / R36)

| type | method | can it pass? | test units |
|---|---|---|---|
| waterlogging | `anc_elev_lgbm_wl` (flood family + ponding history, soil moisture, canals) | yes | 40 plains units (S1v3); no public EMS waterlogging AOI passed |
| rain | `anc_elev_lgbm_fine` (flood family + 311 history, 3DEP 10 m, drainage, drainage-loss SFINCS) | yes | 12 FloodNet storms (verdict); no public EMS rain AOI passed, so no secondary |
| flash | `anc_elev_lgbm_mrms` | not testable: no login-free reserve unit with an accepted label (criteria §12) | none |
| river | elevation (DEV: no learned method cleared the bound) | no (R35) | 2 public EMS AOIs (EMSR771 AOI05, AOI07), informational |
| coastal | elevation | no (R35) | none in the seal |
| compound | elevation | no (R35) | none in the seal |

## 3. Frozen models (`freeze_r3.py`)
- One final model per learned method with test units, waterlogging and rain, trained on **all DEV units**: the same pool, rows, weights, seed and LightGBM settings as the DEV comparison.
- **λ:** the rule of `model_r3.choose_lambda` on all DEV units (leave-region-out, the best mean within-unit AUC, ties to the smaller).
- The models and their SHA256 are in `results/frozen_r3.json` and `FREEZE_R3.txt`.

## 4. Labels (criteria §3–§5, §10, §12), read only after the freeze
- **Plains (S1v3):** `build_r3.s1route_ref`. The box is placed by round 4's `place()` on the 20 km Sentinel-1 search square, and the v3 Sentinel-1 label is built in [peak − 1 d, peak + 14 d].
- **Public EMS (EMS):** round 4's `place()` on the product (flood centre, 8 km box), then the EMS map through `labels_r3.apply_states` (radar rules when the product's sensor is radar).
- **FloodNet:** `FLOODNET_TEST_DESIGN.md` rules 5 and 7.
  - Event timestamps are taken as America/New_York local time (the dataset's timestamps are local), converted to the UTC window.
  - A sensor is wet if any event in the window reaches ≥ 1.0 in, dry if it has no event, and excluded if its events are all < 1.0 in.
  - Cells holding disagreeing sensors are excluded.

## 5. Features (the DEV builders, unchanged)
- Round-2 tables (`build_r3._features`) for every unit, and for every NYC lattice box that holds a sensor active at one of the 12 storms (FLOODNET rule 10, criteria §12).
- **Waterlogging:** `wl_feats.one`.
- **Rain on FloodNet:** per storm × box holding a sensor active at that storm:
  - `fine_feats.extras_311` (311 history before 2022 and 3DEP 10 m);
  - `fine_feats.drainage_311`;
  - `sfincs_drain.run_unit` (storm IMERG).
- **Rain on EMS AOIs:** the fine features are NaN, as for every non-311 DEV unit.
- **Missing pieces:** a unit or box whose labels or features fail after 3 tries is a dropout, reported with its error. A FloodNet sensor cell whose box has no features is unscored, and that is reported. Nothing is back-filled.

## 6. Scoring (`heldout_r3.py score`, run once)
- **Clusters:** the joined events of the seal (§11).
- **Waterlogging's verdict:** all usable units.
- **Rain's verdict:** usable FloodNet storms (≥ 5 needed, otherwise "not testable with FloodNet in round 3"). Each storm is one unit on the city-wide NYC 30 m grid, scored over its labelled sensor cells.
- **Also reported, deciding nothing:**
  - per label family;
  - units away from DEV places (`near_dev_unit_20km` false);
  - flat and hilly (criteria §9; per sensor cell's box for FloodNet);
  - the informational baseline types;
  - the rain secondary on public EMS rain AOIs.
- **Output:** results go to `results/test_r3.json` and, in plain words, to STATUS.md. A failed type is reported as failed, with no rerun and no change.

## 7. Running it (compute only; no effect on any number)
- `heldout_r3.py build units`, `build boxes` and `build fn <shard> 3` run as an unattended, resumable chain.
  - Three FloodNet shards are split by box.
  - A memory guard pauses work when free memory drops below 15 %.
- `heldout_r3.py score` then runs once, and the chain writes STATUS.md, commits and pushes.
