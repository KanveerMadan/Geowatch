# flood_round2: pre-registration

Written 2026-11-21, before any reference, input or score of any unit below has been read. The units were added to the registry as `reserved` in commit `0d569a1`, before this file. Once this file is committed and pushed, its SHA256 and push time are recorded in `PREREG_HASH_ROUND2.txt`. Nothing here changes after that.

## 1. What is tested
For each flood type, the method chosen on DEV by the rule in §4 is scored **once** on the RESERVED units of that type (§2). It is scored beside both baselines, every other candidate, and the production modules (§5).

Reserved units per type (an event can carry two tags; units of one storm are one cluster):

| type | units | clusters |
|---|---|---|
| fluvial | 20 | 12 |
| pluvial | 3 | 3 |
| waterlogging | 4 | 4 |
| flash_flood | 9 | 5 |
| coastal | 5 | 5 |
| compound | 5 | 5 |
| snowmelt | 3 | 2 |
| glof | 2 | 1 |
| dam_breach | 2 | 1 |


Tags snowmelt (M8), glof (M6) and dam_breach (M7) are recorded and reported, but they are not scored as types this round. Their units are scored under their first tag.

## 2. Reserved units (fixed)
Chosen from Copernicus EMS activation text and product metadata (exposure 2), or from a town point and date in general reporting (Sentinel-1 units, exposure 1). Rules: `experiments/flood_round2/DECISIONS.md` R7, R8.

| unit | tags | region | date | reference (fixed now) | basis |
|---|---|---|---|---|---|
| s1_biparjoy_jakhau_2023 | coastal | south_asia | 2023-06-16 | Sentinel-1 VV drop, 20 km search square at [68.72, 23.22] | Cyclone Biparjoy landfall and coastal flooding, Jakhau, Kutch, Gujarat |
| s1_dana_kendrapara_2024 | coastal compound | south_asia | 2024-10-25 | Sentinel-1 VV drop, 20 km search square at [86.95, 20.65] | Cyclone Dana surge and heavy rain, Kendrapara / Bhitarkanika, Odisha |
| s1_francine_terrebonne_2024 | coastal compound | americas | 2024-09-12 | Sentinel-1 VV drop, 20 km search square at [-90.66, 29.25] | Hurricane Francine surge and rain, lower Terrebonne Parish, Louisiana |
| s1_helene_steinhatchee_2024 | coastal compound | americas | 2024-09-27 | Sentinel-1 VV drop, 20 km search square at [-83.39, 29.67] | Hurricane Helene storm surge and rain, Steinhatchee / Keaton Beach, Florida Big Bend |
| s1_remal_satkhira_2024 | coastal compound | south_asia | 2024-05-27 | Sentinel-1 VV drop, 20 km search square at [89.1, 22.33] | Cyclone Remal surge and rain, Shyamnagar, Satkhira, Bangladesh |
| r_emsr663_aoi01 | compound | africa | 2023-03-12 | EMS EMSR663 AOI01 GRA monitoring 0 (Burnett) | Following Cyclone Freddy ... communities ... impacted by floods |
| r_emsr750_aoi01 | flash_flood dam_breach | africa | 2024-08-25 | EMS EMSR750 AOI01 GRA monitoring 0 (Arbaat Dam) | the collapse of Arba'at Dam ... flash flooding that affected 20 villages |
| r_emsr750_aoi02 | flash_flood dam_breach | africa | 2024-08-25 | EMS EMSR750 AOI02 GRA monitoring 0 (Khor Maluqirm) | the collapse of Arba'at Dam ... flash flooding that affected 20 villages |
| r_emsr795_aoi02 | flash_flood | europe_mediterranean | 2025-03-14 | EMS EMSR795 AOI02 DEL monitoring 0 (Sesto Fiorentino) | The Rimaggio River has flooded Sesto Fiorentino |
| r_emsr795_aoi06 | flash_flood | europe_mediterranean | 2025-03-14 | EMS EMSR795 AOI06 DEL monitoring 0 (Montelupo) | The Rimaggio River has flooded Sesto Fiorentino |
| r_emsr802_aoi01 | flash_flood | europe_mediterranean | 2025-05-26 | EMS EMSR802 AOI01 DEL monitoring 0 (Ghimbav) | a major flood is reported to have affected Covasna and Brasov counties |
| r_emsr802_aoi02 | flash_flood | europe_mediterranean | 2025-05-26 | EMS EMSR802 AOI02 DEL monitoring 0 (Lunca Marcusului) | a major flood is reported to have affected Covasna and Brasov counties |
| r_emsr927_aoi01 | flash_flood glof | south_asia | 2026-08-25 | EMS EMSR927 AOI01 GRA monitoring 0 (Syapru Besi) | a flash flood reportedly triggered by a Glacial Lake Outburst Flood (GLOF) in Nepal |
| r_emsr927_aoi02 | flash_flood glof | south_asia | 2026-08-25 | EMS EMSR927 AOI02 GRA monitoring 0 (Timure) | a flash flood reportedly triggered by a Glacial Lake Outburst Flood (GLOF) in Nepal |
| s1_baghlan_2024 | flash_flood | south_asia | 2024-05-11 | Sentinel-1 VV drop, 20 km search square at [68.7, 36.13] | flash floods in Baghlan province, Afghanistan, 10-11 May 2024 |
| r_emsr657_aoi01 | fluvial snowmelt | europe_mediterranean | 2023-03-30 | EMS EMSR657 AOI01 DEL monitoring 0 (DaugavaRiver) | flood due to melted snow and ice, as well as precipitation ... Daugava river valley |
| r_emsr668_aoi01 | fluvial snowmelt | europe_mediterranean | 2023-05-22 | EMS EMSR668 AOI01 DEL monitoring 0 (Drammen) | ongoing spring flood ... due to snow melt |
| r_emsr668_aoi02 | fluvial snowmelt | europe_mediterranean | 2023-05-22 | EMS EMSR668 AOI02 DEL monitoring 0 (Amot) | ongoing spring flood ... due to snow melt |
| r_emsr684_aoi01 | fluvial | europe_mediterranean | 2023-08-15 | EMS EMSR684 AOI01 DEL monitoring 0 (Mora) | risk of flooding in several areas of central Sweden due to heavy rainfall |
| r_emsr684_aoi05 | fluvial | europe_mediterranean | 2023-08-15 | EMS EMSR684 AOI05 DEL monitoring 0 (Marma) | risk of flooding in several areas of central Sweden due to heavy rainfall |
| r_emsr698_aoi01 | fluvial | europe_mediterranean | 2023-10-07 | EMS EMSR698 AOI01 DEL monitoring 0 (River Spey) | extensive flooding is forecast to hit Central Scotland |
| r_emsr698_aoi02 | fluvial | europe_mediterranean | 2023-10-07 | EMS EMSR698 AOI02 DEL monitoring 0 (River Tay) | extensive flooding is forecast to hit Central Scotland |
| r_emsr722_aoi01 | fluvial | europe_mediterranean | 2024-05-17 | EMS EMSR722 AOI01 DEL monitoring 0 (Blies) | flood event was reported affecting Saarland region |
| r_emsr722_aoi02 | fluvial | europe_mediterranean | 2024-05-17 | EMS EMSR722 AOI02 DEL monitoring 0 (Saar) | flood event was reported affecting Saarland region |
| r_emsr728_aoi01 | fluvial | europe_mediterranean | 2024-05-31 | EMS EMSR728 AOI01 DEL monitoring 0 (Stuttgart) | continuous rain ... Southern and Eastern Germany |
| r_emsr728_aoi03 | fluvial | europe_mediterranean | 2024-05-31 | EMS EMSR728 AOI03 DEL monitoring 1 (Regensburg) | continuous rain ... Southern and Eastern Germany |
| r_emsr783_aoi01 | fluvial | europe_mediterranean | 2024-12-30 | EMS EMSR783 AOI01 DEL monitoring 0 (Aviemore) | severe flooding is reported in North West Scotland (Western Cairngorms) |
| r_emsr783_aoi03 | fluvial | europe_mediterranean | 2024-12-30 | EMS EMSR783 AOI03 DEL monitoring 0 (Crieff) | severe flooding is reported in North West Scotland (Western Cairngorms) |
| r_emsr849_aoi01 | fluvial | europe_mediterranean | 2025-11-14 | EMS EMSR849 AOI01 DEL monitoring 0 (Athlone) | Storm Claudia affected Ireland, causing floods |
| r_emsr849_aoi02 | fluvial | europe_mediterranean | 2025-11-14 | EMS EMSR849 AOI02 DEL monitoring 0 (Mountmellick) | Storm Claudia affected Ireland, causing floods |
| r_emsr855_aoi01 | fluvial | europe_mediterranean | 2026-01-06 | EMS EMSR855 AOI01 DEL monitoring 0 (Aniene River) | Heavy rainfall ... Lazio ... the Aniene River has reached |
| r_emsr860_aoi02 | fluvial | europe_mediterranean | 2026-01-27 | EMS EMSR860 AOI02 DEL monitoring 1 (County Kilkenny) | Storm Chandra ... flooding damage ... Graiguenamanagh (County Kilkenny) |
| r_emsr866_aoi02 | fluvial | europe_mediterranean | 2026-02-12 | EMS EMSR866 AOI02 DEL monitoring 0 (Libourne) | flood event forecast to hit the Bordeaux region, the Charente river basin and the Dronne river basin |
| r_emsr871_aoi01 | fluvial | europe_mediterranean | 2026-03-31 | EMS EMSR871 AOI01 DEL monitoring 0 (Romualdi) | heavy rain ... caused a rise in river water levels |
| r_emsr871_aoi02 | fluvial | europe_mediterranean | 2026-03-31 | EMS EMSR871 AOI02 DEL monitoring 0 (Montero di Bisaccia) | heavy rain ... caused a rise in river water levels |
| r_emsr721_aoi01 | pluvial | europe_mediterranean | 2024-05-14 | EMS EMSR721 AOI01 GRA monitoring 0 (Gorgonzola) | heavy thunderstorms, in Lombardy and Milan ... difficulties in the city's secondary network |
| s1_jeddah_2022 | pluvial | africa_west_asia | 2022-11-24 | Sentinel-1 VV drop, 20 km search square at [39.2, 21.55] | torrential rain flooding in Jeddah, Saudi Arabia, 24 Nov 2022 |
| s1_kinshasa_2022 | pluvial | africa | 2022-12-13 | Sentinel-1 VV drop, 20 km search square at [15.31, -4.38] | heavy-rain flooding in Kinshasa, DR Congo, 13 Dec 2022 |
| s1_garsen_2023 | waterlogging | africa | 2023-12-01 | Sentinel-1 VV drop, 20 km search square at [40.12, -2.27] | prolonged Tana River delta flooding around Garsen, Kenya, Nov-Dec 2023 |
| s1_jowhar_2023 | waterlogging | africa | 2023-11-20 | Sentinel-1 VV drop, 20 km search square at [45.5, 2.78] | prolonged Shabelle flooding around Jowhar, Somalia, Nov 2023 (El Nino rains) |
| s1_sukhothai_2024 | waterlogging | southeast_asia | 2024-09-01 | Sentinel-1 VV drop, 20 km search square at [99.82, 17.01] | prolonged Yom River flooding at Sukhothai, Thailand, late Aug-Sep 2024 |
| s1_ubon_2022 | waterlogging | southeast_asia | 2022-10-05 | Sentinel-1 VV drop, 20 km search square at [104.87, 15.24] | prolonged Mun River flooding at Ubon Ratchathani, Oct 2022 |

## 3. Labels and references (unchanged from flood_final)
- References are built by `experiments.flood_validation.harness_round4` `place()` + `reference()`, unchanged: EMS observed-event polygons, or the Sentinel-1 VV drop of ≤ −3 dB against the Jan–Mar same-orbit median of the event year, on round 4's box rule (a 4 km box, 30 m UTM grid).
- Labels are flooded / dry / unobserved. Unobserved cells are never dry, and JRC occurrence ≥ 80 % is excluded.
- A unit qualifies with ≥ 50 flooded and ≥ 50 dry labelled cells. Units that do not qualify or fail to build are listed as such, never scored as zero.
- A unit's inputs and features are built by the same code as DEV (`flood_final.build_units.build_one`, then `flood_round2.features_r2`), with up to 3 tries of 3600 s each.

## 4. Candidates and the choice rule (DEV only, fixed in code at the freeze tag)
`experiments/flood_round2/model_v3.py`, candidates in tie-break order (simplest first):
1. `elev`: −GLO-30 elevation (plain lowest-ground ranking; no fitting).
2. `hand`: −HAND (MERIT).
3. `full_lr`: logistic regression on FULL (open features + round-2 features).
4. `resid_lgbm`: LightGBM on FULL, boosted from an elevation-only logistic fit (it learns only what improves on elevation).
5. `flash_lgbm` (flash_flood only) and `coastal_lgbm` (coastal and compound only): LightGBM on type-specific features.
6. `full_lgbm`: LightGBM on FULL.

**Rule.** For each type, the candidate with the highest leave-region-out mean within-event AUC over that type's DEV units is chosen. Any candidate within 0.005 of the best is replaced by the earliest in the order above.
- The choice and the final models (trained on all DEV units, with isotonic calibration on pooled LRO predictions) are written to `results/method_choice_r2.json`, committed and hashed before the freeze tag.
- Hyperparameters are flood_learned's, unchanged.

## 5. Metrics
- **Primary:** within-event ROC AUC of the raw score. Isotonic calibration is monotone and only adds ties (D15).
- **Uncertainty:**
  - a paired spatial block bootstrap inside each unit: 33-cell (990 m) blocks, 1,000 replicates, seed 20261114 + sha1(unit);
  - a two-stage cluster × block bootstrap of the mean over units;
  - 95 % percentile intervals.
- **Reported for every type, with no verdict attached:**
  - every candidate;
  - both baselines;
  - the production modules (fluvial, pluvial where its inputs build within 1 h, waterlogging, flash_flood);
  - average precision;
  - area-matched IoU;
  - calibration of the chosen model's isotonic output (intercept, slope, ECE, Brier skill; pooled).

## 6. Pass bar (per type)
A type **passes** when all of these hold for its chosen method on its qualifying reserved units:
1. mean AUC ≥ 0.70 (the bar of every earlier flood round);
2. the lower 95 % bound of the mean paired difference against the stronger baseline is > 0. The stronger baseline is whichever of {`hand`, `elev`} has the higher mean AUC on those same units. If the chosen method is itself one of these baselines, the comparison is against the other one.
3. at least 3 qualifying units in at least 2 clusters. Otherwise the type is "not-run (insufficient)".

Basis: the owner's round-2 brief ("beat the best of {HAND, elevation} with blocked 95% CI above 0, and AUC ≥ 0.70"), after round 1 showed plain elevation beating the learned model on held-out data.

## 7. One-shot rule
- The code, `method_choice_r2.json` and the final-model hashes are frozen under the tag `flood-round2-heldout-freeze`, pushed before any reserved reference is built.
- The scorer refuses to run unless HEAD equals the tag and this file's hash matches `PREREG_HASH_ROUND2.txt`. It writes `results/heldout_r2.json` with mode `x` and refuses to run twice.
- Failures during the build are logged, not fixed. Nothing is re-scored.

## 8. What is not tested here
- SFINCS runs only on DEV cases (Valencia, Fort Myers, a compound case and urban rain cases). It is reported as DEV evidence and offered as a labelled scenario mode, not scored on reserved units.
- No urban flood reference (Phase F) was available before this file. Built-up cells keep the "not assessed" rule in production unless a later, separately pre-registered urban test passes.

## 9. What the result decides
- A type that passes gets its chosen method in production, labelled `validated` with a scope note (the reserved units and regions, and the limits).
- A type that fails stays `experimental` (or `failed` where a production module's own verdict says so).
- River and waterlogging keep the flood_final learned output's validation only if their round-2 chosen method passes. Otherwise the report says that round 2 did not confirm round 1.
