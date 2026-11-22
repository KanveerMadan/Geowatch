# flood_round3: decisions

Numbering continues from round 2 (R1–R17, `experiments/flood_round2/DECISIONS.md`, unedited). Round 2 is the development round; round 3 is the confirmation.

## R18 (2026-11-22) Phase 0: the product ranks river and waterlogging by plain elevation
- Round 2 did not confirm the learned gain over elevation (R17). PR #1 (`build/flood-learned`, `39d31e4`) therefore replaces the learned output with `flood_ranking`: minus GLO-30 elevation, drawn as the within-AOI percentile.
- **Label: `experimental`.** In every pre-registered round elevation was the comparator, never the method under test, so it has no pass of its own. Its held-out numbers (river 0.850 / 0.897, waterlogging 0.843 / 0.707) are reported in the output, not as a pass.
- The learned entry moved to `analysis.contract.WITHDRAWN` as the record. No flood output is `validated` now.
- Round 3's passing types replace this placeholder in a later PR.

## R19 (2026-11-22) Label rules v3 and the maximum image lag per type, fixed before the reserve
**Rules:** `labels_r3.py` docstring, R3-S1-1..4 and R3-O-1..4. Each comes from how the labels are made (DIAGNOSIS.md c, d, new 1–2), none from comparing methods:
- the Sentinel-1 baseline is the 60 to 6 days before the event, on the same orbit;
- open water needs VV ≤ −15 dB as well as the −3 dB drop;
- maximum extent over every pass in the window;
- for radar labels, HAND > 15 m (GFM's rule), built-up cells and slopes > 20° are unobserved;
- permanent water is its own state.

**Maximum lag of the label image after the driver peak** (DIAGNOSIS.md b):
- **rain 1 d:** urban rain water drains within hours to a day, and no round-2 rain image was within a day;
- **flash 2 d;**
- **river 3 d** after the discharge peak at the box's reach (GEOGloWS), or after the rain peak where no flood wave is found;
- **coastal and compound 2 d** after landfall / surge peak;
- **waterlogging 14 d:** persistent by definition; the round-2 median was 8 d.

Every AUC falls about 0.02–0.03 per lag step (≤ 1, 2–3, 4–7 d), and these limits keep the label close to the event. They apply to every method, and to selection of the round-3 reserve.

**Scoring domain:**
- Round-3 verdicts are scored on FLOODED vs DRY cells under the v3 rules.
- Full-domain numbers are reported beside them: the round-2 label rules on the same units, for every method.

## R20 (2026-11-22) Data access
| service | state | consequence |
|---|---|---|
| CDS | works (ERA5, ERA5-Land) | used for soil moisture and rain checks |
| EWDS (GloFAS) | CEMS terms not accepted on the account (403) | GEOGloWS v2 used for discharge (open, CC BY 4.0; full daily series 1940–2026). GloFAS joins when the owner accepts the terms |
| Earthdata | HyP3 works | coherence labels possible |
| Earthdata → GES DISC | not authorised | IMERG V07 from Earth Engine |
| Copernicus EMS | public dashboard lists 2022+ only; older activations need an EMS account | 35 fresh (never used) flood/storm activations, 2023–2026. Older events come from MMFlood / Sen1Floods11 / Kuro Siwo (licences to check), Sentinel-1 events from reporting, and Maxar Open Data |

## R21 (2026-11-22) v3 labels on the burned units: what survives, and the power it implies
`relabel_burned.py` rebuilt all 169 burned units under R19 on their existing grids (`results/v3_burned_scores.json`). It is diagnosis on burned data only.

**Units by first tag:**

| outcome | river | waterlogging | coastal | rain | flash | compound |
|---|---|---|---|---|---|---|
| built, image in window | 31 | 17 | 15 | 7 | 5 | 2 |
| built, EMS image later than MAX_LAG | 24 | 4 | 6 | 9 | 19 | 3 |

- 12 rain units have no S1 pass within 1 d of the rain peak.
- 6 units have old reference grids that do not match their tables (dropped from v3).

**Round-2 predictions scored on v3 vs old labels.** Units are those qualifying, with ≥ 50 flooded and ≥ 50 dry; units can carry several tags.

| type | label | units | elevation | learned | gain | gain SD | units for 90 % power at Δ 0.03 |
|---|---|---|---|---|---|---|---|
| river | old | 55 | 0.818 | 0.834 | +0.013 | 0.050 | 38 |
| river | v3 | 31 | 0.796 | 0.817 | +0.017 | 0.064 | 62 |
| waterlogging | old | 22 | 0.738 | 0.742 | −0.000 | 0.071 | 77 |
| waterlogging | v3 | 18 | 0.745 | 0.742 | −0.007 | 0.084 | 109 |
| coastal | old | 21 | 0.777 | 0.737 | −0.052 | 0.101 | 154 |
| coastal | v3 | 14 | 0.754 | 0.740 | −0.017 | 0.050 | 38 |
| compound | old | 14 | 0.793 | 0.780 | −0.048 | 0.115 | 201 |
| compound | v3 | 9 | 0.801 | 0.800 | −0.006 | 0.077 | 90 |
| flash | v3 | 4 | 0.840 | 0.832 | −0.011 | 0.045 | 31 |
| rain | v3 | 3 | 0.816 | 0.838 | +0.022 | 0.026 | 11 |

**Reading:**
- v3 labels cut the learned model's losses on coastal and compound (the label noise was costing it), but they do not create a gain.
- Strict timing (R19) empties rain and flash among the existing sources. Those types need new, peak-time sources: S1 passes within a day of a rain peak, or VHR / urban labels.
- At the round-2 models' gains, no type can pass on a test of any size the fresh sources can supply. The gain must come from Phase 4. Its ceiling is the DIAGNOSIS §a headroom: ≤ +0.021 for river, +0.013 for coastal and +0.026 for compound from terrain re-weighting, even with an oracle.

## R22 (2026-11-22) Ideas tested on burned units and dropped
- **Relative-elevation model** (elevation minus the interpolated water surface): worse than elevation in every type (river −0.103).
- **Connectivity spill level** (minimax-path fill level from mapped water): −0.005 to −0.010 against elevation in every type. A blend with elevation gives ±0.004.
- Both are recorded so they are not retried. The low ground the labels miss or add is not explained by connectivity to mapped water inside the box.

## R23 (2026-11-22) The fresh-event pool is the binding constraint
- **EMS, public list (2022+):** 35 unused flood/storm activations. 10 have usable products, giving 23 AOIs. **11 AOIs pass** the size, extent and proximity rules, before the timing rule: 7 river, 4 rain.
- **MMFlood** (CC BY 4.0, Zenodo 6534637): 95 EMS activations from 2014–2021, none used before (7 within 20 km of a used unit), 465 AOI delineations. Its metadata (`activations.json`, read by HTTP range request; no imagery or labels) has no image acquisition times, so R19 timing cannot be checked from it alone.
- **Pre-2022 EMS metadata** (image times, reported extent) needs an EMS account. **Only the owner can create one.** With it, MMFlood's 95 activations, and the rest of the 2015–2021 archive, become usable under RESERVE_CRITERIA_R3.
- **Targets at Δ = 0.03 on v3 labels are 38–109 units per type.** That is several times what any open fresh source supplies with peak-time imagery.

## R24 (2026-11-22) Round-3 units are 7.98 km boxes where the source allows (test design, all methods equally)
- **Why:** DIAGNOSIS §j. A 3.99 km unit holds only ~25 blocks of 990 m. For coastal (100 %) and compound (71 %), most of the per-unit gain variance is sampling noise inside the unit, not event difference.
- **Justification:** this choice comes from the bootstrap's resolution, not from comparing methods. The bar is unchanged: within-event AUC, the 990 m block bootstrap, the same scorer.
- **Rule:**
  - A round-3 unit is a square of side 7.98 km (4× round 2's area, ~100 blocks), centred as the source's rule says (§4 / §8 of RESERVE_CRITERIA_R3).
  - Where the footprint cannot hold it, the side is the largest multiple of 0.99 km ≥ 3.99 km that fits, and the side is recorded per unit.
  - It applies to every method and every type.
- **Effects:**
  - The EMS AOI-extent floor becomes "a 3.99 km box fits" (≥ 16 km², as before). Bigger AOIs simply get bigger boxes.
  - The Phase 4 DEV CV is re-run on 7.98 km boxes around the burned units (tables rebuilt, labels by v3), so the method choice and the target n are made at the size that is tested.

## R25 (2026-11-22) R24 amended: fixed 8 km side, round 4's placement kept
This replaces R24's rule, before any round-3 candidate was listed. R24's text above stays as written.
- **Side:** a fixed 8 km square (round 4's 4 km × 2, ~70–80 blocks). R24's fallback list of sides is dropped.
  - Cells outside a product's extent are unobserved, as before, so no fallback is needed.
- **Placement:** round 4's `place()`, unchanged. The box is centred on the flood centre of the label inside the product AOI (EMS) or the 20 km Sentinel-1 search square.
  - This is the rule every earlier unit used. It is mechanical and runs at build time, after the freeze, identically for every method.
  - R24's "box on the reach" is dropped: the reach point is now only the Sentinel-1-route search point (RESERVE_CRITERIA_R3 §8.3).
- **DEV:** the Phase 4 DEV CV runs on 8 km boxes around the burned units' own round-2 centres (`build_r3.py`; round 2's feature pipeline; v3 labels). The method choice and the target n are made at the size that is tested.

## R26 (2026-11-22) Phase 0b result: the Ida compound SFINCS run does not beat the terrain baselines
`results/ida_sfincs_r3.json`. Four members, one at a time, Docker capped at 3 GB (peak ~300 MB, ~1–1.7 h each). Domain 661 km², IMERG rain (145.7 mm domain mean), NOAA gauge 8761724 surge (residual peak 1.63 m).

| member | AUC of hmax | HAND | low elevation | wet share of box |
|---|---|---|---|---|
| base | 0.639 | 0.661 | 0.646 | 0.998 |
| surge × 2 | 0.637 | 0.661 | 0.646 | 1.000 |
| datum + 0.3 m | 0.634 | 0.661 | 0.646 | 1.000 |
| 3DEP lidar DEM (e1) | 0.626 | 0.661 | 0.646 | 0.999 |

**Reading:**
- Rain-on-grid with no infiltration wets almost the whole box at the 0.1 m threshold. Ranking by peak depth then mostly rewards closed depressions, and that ranks worse than HAND.
- This is a failure of this configuration, not of physics as a feature class: no infiltration and no drainage network.
- Before the Phase 4 DEV CV, a compound/coastal physics feature needs at least:
  - infiltration (SFINCS curve-number or Horton);
  - a check that the wet share is below 1 on DEV.
- It remains a candidate feature in the anchored learner, not a stand-alone method.

## R27 (2026-11-22) Fresh-event sources settled without the EMS account
- **River:** MMFlood on the Sentinel-1 route (RESERVE_CRITERIA_R3 §8) gives 111 candidate units from 68 never-used activations (`results/r3_mmflood_candidates.json`). 90 were refused, each with its reason:
  - 52: no flood wave (return period < 1.5 y);
  - 17: no reach inside the footprint;
  - 8: no Sentinel-1 pass in the window;
  - 8: within 20 km of a burned unit.
  - The EMS 2022+ list adds 7 river and 4 rain AOIs (R23).
- **Rain:** 311 street-flooding reports (RAIN_311_DESIGN.md), NYC and Chicago: 113 reserve events (2022 onwards), plus 110 DEV events. On DEV, about 1 in 3 events puts ≥ 50 flood reports in one 8 km box.
- **Coastal and compound:** NYC 311 storm days typed by the Battery tide gauge (reserve: 5 coastal, 3 compound), plus EMS and Sentinel-1 storm candidates. These two types remain the thinnest.
- **Flash and waterlogging:** no new peak-time source yet. They are next.
