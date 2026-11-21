# M9 compound: limits

- Compound units overlap heavily with coastal (same storms: Beryl, Harry) and with flash flood (Portugal 2026); the groups are not independent.
- 5 reserved units in 3 clusters; the Δ-vs-HAND interval spans -0.26 to +0.10.
- Valencia 2024 SFINCS (rain + river, DEV): every ensemble member beats HAND on max depth (DEV evidence only).

## Shared by every flood type

- **Plain elevation is as good or better.** Negated GLO-30 elevation (`neg_elev_glo30`, lowest ground first) was reported beside every verdict but was not a pre-registered candidate. On RESERVED it beats the learned model on 4 of 6 types, including both that passed. The data do **not** show that the learned model adds skill over low-ground ranking (D21).
- **Urban blind spot.** The learned model learned from references that cannot see flooding among buildings. At Weihui (UrbanSARFloods, CC BY 4.0) it ranks flooded urban cells below dry cells (AUC 0.12–0.36). Cells with built-up share >= 0.5 must be shown as 'not assessed' (D20).
- **Land cover drives the model.** Removing WorldCover costs 0.04–0.13 DEV AUC on every type; with the urban blind spot, part of this signal is a reference artefact.
- **References.** Copernicus EMS delineations (and Sentinel-1 VV-drop extents) at their acquisition time, not peak extent; unobserved cells are excluded, never treated as dry; JRC occurrence >= 80 % excluded; accra, capetown, dhaka, hcmc and nusantara never used as labels (JRC-circular).
- **Within-event ranking only.** AUC measures whether flooded cells rank above dry cells in the same 4 km box. It says nothing about absolute depth, return period or between-place comparison.
- **Missing data.** 2 reserved units failed to build (an Earth Engine projection error, not fixed after the freeze) and 4 had no flood in the product; 7 did not reach 50 flooded cells. They are listed in `data_manifest.csv`, never scored as zero.
