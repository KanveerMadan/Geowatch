# flood_final: report

Branch `exp/flood-final`. Judgement calls are in `DECISIONS.md` (D1–D22) and the phase log in `STATUS.md`. Evidence packs are on `paper/evidence-flood-final` (`paper/evidence/M1_fluvial/FLOOD_FINAL.md`, `M2_pluvial`, `M3_waterlogging`, `M4_flash_flood`, `M5_coastal`, `M9_compound`). Production integration: draft PR https://github.com/KanveerMadan/Geowatch/pull/1 (`build/flood-learned`), not merged.

## 1. Headline
- **One pre-registered held-out pass**, run 2026-11-20 14:14 UTC.
  - Pre-registration sha256: `e49bca3f99380867f0a8c7a4b36b62c0c806479a356f20ab6366fb11067db9a4`, pushed 2026-11-19 07:37:07 UTC.
  - Freeze tag `flood-final-heldout-freeze` = `81ff7b1`.
  - The test covered 47 reserved units, 34 of which qualified.
- **Passed:**
  - river (M1): learned `open__logreg`, mean AUC **0.791**, Δ vs HAND **+0.095 [+0.011, +0.192]**, 8 units in 7 clusters;
  - waterlogging (M3): learned `open__logreg`, **0.791**, Δ **+0.167 [+0.118, +0.226]**, 3 units in 2 clusters (the minimum allowed).
- **Failed:**
  - pluvial (M2): 0.703, Δ +0.039 [−0.035, +0.112];
  - flash flood (M4): 0.810, Δ −0.017;
  - coastal (M5): 0.795, Δ +0.042 [−0.028, +0.098];
  - compound (M9): 0.844, Δ −0.011.
  - In all four, the AUC is high but not above HAND with confidence.
- **The production fluvial module re-test failed:** 0.578, Δ −0.119 [−0.237, −0.019], on the same 8 river units.
- **Biggest caveat.** Plain low-ground ranking (negated GLO-30 elevation; reported beside every verdict, not pre-registered) scored higher than the learned model on the held-out cells:
  - river 0.850, waterlogging 0.843, pluvial 0.798, flash 0.862;
  - so it beat the learned model on 4 of 6 types.
  - The passes stand under the pre-registered bar (vs HAND). But the data do not show that the learned model adds skill over elevation. Elevation is the obvious candidate for the next pre-registered round with new reserved events.
- **Urban blind spot** (D20). The references the model learned from cannot see flooding among buildings. At Weihui (UrbanSARFloods labels) the model ranks flooded streets below dry ground (AUC 0.12–0.36). Production therefore marks built-up cells as "not assessed".

## 2. Event set (phases 1–3)
- **DEV: 67 units.**
  - 29 from batch 0 and 38 new (18 EMS activations).
  - By type: fluvial 25, flash 17, waterlogging 12, pluvial 11, compound 7, coastal 5.
- **RESERVED: 47 units** (23 EMS activations and 6 Sentinel-1 events), registered as `reserved` in `experiments/flood_core/registry/events.json` before the pre-registration (commit `c6fb5b1`).
- Counts below the brief's targets (≥ 15 DEV, ≥ 5 RESERVED per type) are reported, not padded (D18).
- River held-out units span Africa, Europe, South Asia, Southeast Asia and Central America, not only the South Asian plains.
- Never used as labels: accra, capetown, dhaka, hcmc, nusantara (JRC-circular).
- Labels are flooded / dry / unobserved. Unobserved cells are never dry, and JRC occurrence ≥ 80 % is excluded.

## 3. Model v2 and method choice (phase 5, DEV only)
- Six candidates: variants `full`, `open` and `no_landcover`, each as logistic regression and as LightGBM.
- Chosen per type by leave-region-out mean AUC (tie 0.005, logistic first, then open first). `open` was chosen everywhere.
- DEV LRO results, chosen method vs HAND:
  - fluvial 0.770 vs 0.648;
  - pluvial 0.676 vs 0.662;
  - waterlogging 0.727 vs 0.596;
  - flash 0.750 vs 0.671;
  - coastal 0.763 vs 0.679;
  - compound 0.727 vs 0.657.
- On DEV, Δ vs HAND has a CI above 0 for fluvial, waterlogging and flash, but not for pluvial, coastal or compound (`results/dev_tables.md`).
- Removing land cover costs 0.04–0.13 AUC on every type.
- Calibration (held-out, pooled, isotonic output):
  - LightGBM is weakly calibrated (intercept 0.028, slope 1.30, ECE 0.033), so its output may be called a "probability";
  - the logistic model that passed is not (slope 1.72, ECE 0.047, Brier skill 0.18), so its output is a "score".

## 4. Urban-capable reference (phase 4)
- UrbanSARFloods (Weihui, CC BY 4.0). The round-4 S1 VV-drop method marks 43 % of flooded open cells but only 1.1–7.1 % of flooded urban cells (dry: 1.8–4.8 %).
- So the S1 references used for 10 DEV and 7 RESERVED units are blind to urban flooding.
- The learned model scores flooded urban cells below chance, so the cropland signal is partly a reference artefact (D11 reading, D20).

## 5. SFINCS (phase 6, DEV only)
- **Valencia 2024:**
  - 4 members over a 1,092 km² domain (30 m, MDT05 LiDAR or GLO-30; IMERG, or IMERG scaled to the Turís gauge);
  - max-depth AUC vs the EMS AOI03 references: valencia_2024 0.75–0.83 (HAND 0.706), paiporta 0.60–0.71 (HAND 0.501);
  - every member beats HAND;
  - the gauge-scaled member over-wets the plain (62 % of the domain wet against 16 % observed).
- **Runtime:** 1.4–3.5 h per member under amd64 emulation (4.7–11.7 s per km²); disk 0.25 MB per km².
- **Coastal/compound case:** deferred (D17). It is not done in this run.

## 6. What did not work or is missing
- 2 reserved units failed to build (EMSR683: Earth Engine "bands with different projections" in the margin stack). This was not fixed after the freeze, so they are missing, not zero. The same failure can occur in production and is reported as a failed stage.
- GEDTM30 could not be read (the server truncates range requests). GLO-30 is used instead.
- Pluvial-module inputs were not built for the new DEV units (D8).
- A local path inside two error strings of `heldout.json` was pushed to the public repo in `c35c02a`, and redacted in `2b2653f` (D22). Purging it from history is the owner's call.

## 7. Licences (open variant)
- GLO-30 (Copernicus WorldDEM-30, attribution "© DLR e.V."; confirm commercial terms in the full text).
- HydroSHEDS (terms conflict between sources; confirm).
- JRC GSW, OSM (ODbL), CHIRPS / IMERG (open), SoilGrids, WorldCover, Cloud Score+, GHSL (CC BY 4.0), sat-io shoreline (confirm).
- Labels: Copernicus EMS (CEMS terms) and Sentinel-1.
- FABDEM (CC BY-NC-SA) and MERIT Hydro feed only the unchosen `full` variants. The production stack still downloads FABDEM inside the shared margin stack, but does not use it in the learned output.

## 8. Reproduce
`REPRODUCE.md` in any evidence pack lists the commands. The held-out scorer refuses to run twice, and refuses unless HEAD is the freeze tag and the pre-registration hash matches.
