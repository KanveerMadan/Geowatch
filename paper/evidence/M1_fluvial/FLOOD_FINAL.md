# M1 fluvial: flood_final update (independent river test, 2026-11-20)

Two tests on 8 reserved river units never used before (flood_final pre-registration, sha256 `e49bca3f99380867f0a8c7a4b36b62c0c806479a356f20ab6366fb11067db9a4`; freeze `81ff7b1`):

- **Learned model:** **PASSED** (pre-registered). Learned `open__logreg` on 8 reserved units (7 clusters): mean AUC 0.791, Δ vs HAND +0.095 [+0.011, +0.192]. Plain low elevation scored 0.850 on the same cells — higher than the learned model.
- **Production fluvial module (validated configuration) re-test: FAILED.** Mean AUC 0.578, Δ vs HAND -0.119 [-0.237, -0.019].

## Held-out (RESERVED, scored once)

| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |
|---|---|---|---|
| learned `open__logreg` (pre-registered) | 0.791 [0.724, 0.864] | +0.095 [+0.011, +0.192] | 8 |
| learned, isotonic-calibrated output | 0.785 [0.717, 0.854] | +0.089 [+0.004, +0.185] | 8 |
| HAND | 0.696 [0.615, 0.770] | — | 8 |
| low elevation (GLO-30), not pre-registered | 0.850 [0.763, 0.913] | +0.154 [+0.107, +0.198] | 8 |
| JRC occurrence | 0.626 [0.541, 0.739] | -0.071 [-0.143, +0.006] | 8 |
| distance to mapped water | 0.529 [0.387, 0.654] | -0.168 [-0.314, -0.044] | 8 |
| production module `fluvial` | 0.578 [0.467, 0.673] | -0.119 [-0.237, -0.019] | 8 |
| learned `open__lgbm` (not chosen) | 0.821 [0.770, 0.873] | +0.124 [+0.053, +0.216] | 8 |

Per unit:

| unit | region | flooded / dry | learned | HAND | low elevation |
|---|---|---|---|---|---|
| r_emsr857_aoi01 | africa | 14,927 / 2,762 | 0.585 | 0.681 | 0.931 |
| r_emsr857_aoi02 | africa | 2,390 / 15,208 | 0.858 | 0.805 | 0.924 |
| r_emsr712_aoi02 | europe_mediterranean | 1,641 / 7,963 | 0.677 | 0.718 | 0.902 |
| s1_assam_morigaon_2024 | south_asia | 3,344 / 14,878 | 0.887 | 0.815 | 0.911 |
| s1_sunamganj_2024 | south_asia | 9,149 / 8,816 | 0.939 | 0.842 | 0.935 |
| s1_lokoja_2022 | africa | 10,350 / 4,099 | 0.793 | 0.568 | 0.658 |
| s1_kelantan_2024 | southeast_asia | 826 / 17,399 | 0.724 | 0.557 | 0.747 |
| s1_tabasco_2020 | americas | 4,891 / 12,903 | 0.869 | 0.584 | 0.794 |

## DEV (leave-region-out, out-of-fold)

| score | mean AUC [95% CI] | Δ vs HAND [95% CI] | units |
|---|---|---|---|
| learned `open__logreg` (chosen) | 0.770 [0.730, 0.804] | +0.122 [+0.038, +0.188] | 25 |
| learned `open__lgbm` | 0.766 [0.695, 0.835] | +0.118 [+0.071, +0.165] | 25 |
| learned without land cover | 0.719 [0.663, 0.777] | +0.071 [+0.017, +0.116] | 25 |
| HAND | 0.648 [0.571, 0.737] | — | 25 |
| low elevation (GLO-30) | 0.757 [0.669, 0.847] | +0.109 [+0.064, +0.164] | 25 |
| module `fluvial` | 0.692 [0.622, 0.768] | +0.044 [-0.023, +0.114] | 25 |

## Limits

- The current production fluvial module (validated configuration, round 2) was re-tested on the same 8 reserved units and **failed** (see EVIDENCE). Its round-2 validation now has a pre-registered failure on a broader river set beside it.
- Two reserved river events (Assam 2024, Sunamganj 2024) share a main basin with DEV units. The pre-registration accepted this exception link before any data was read (D6).
- Five reserved river references are Sentinel-1 VV-drop extents. They cannot see flooding among buildings (D20), so urban river flooding is under-represented.
- **Plain elevation is as good or better.** Negated GLO-30 elevation (`neg_elev_glo30`, lowest ground first) was reported beside every verdict but was not a pre-registered candidate. On RESERVED it beats the learned model on 4 of 6 types, including both that passed. The data do **not** show that the learned model adds skill over low-ground ranking (D21).
- **Urban blind spot.** The learned model learned from references that cannot see flooding among buildings. At Weihui (UrbanSARFloods, CC BY 4.0) it ranks flooded urban cells below dry cells (AUC 0.12–0.36). Cells with built-up share >= 0.5 must be shown as 'not assessed' (D20).
- **Land cover drives the model.** Removing WorldCover costs 0.04–0.13 DEV AUC on every type; with the urban blind spot, part of this signal is a reference artefact.
- **References.** Copernicus EMS delineations (and Sentinel-1 VV-drop extents) at their acquisition time, not peak extent; unobserved cells are excluded, never treated as dry; JRC occurrence >= 80 % excluded; accra, capetown, dhaka, hcmc and nusantara never used as labels (JRC-circular).
- **Within-event ranking only.** AUC measures whether flooded cells rank above dry cells in the same 4 km box. It says nothing about absolute depth, return period or between-place comparison.
- **Missing data.** 2 reserved units failed to build (an Earth Engine projection error, not fixed after the freeze) and 4 had no flood in the product; 7 did not reach 50 flooded cells. They are listed in `data_manifest.csv`, never scored as zero.

Tables: `tables/flood_final/`; figures: `figures/flood_final/`; manifest: `tables/data_manifest_flood_final.csv`. Method and licences: `../M2_pluvial/METHOD.md` (shared learned model). Reproduce: `../M2_pluvial/REPRODUCE.md`.
