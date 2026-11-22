# flood_final pre-registration: one held-out test of every flood type

**Written 2026-11-19, before any RESERVED event's reference, input layer or score was read.** Branch `exp/flood-final`. The reserved events were added to the flood-core registry in commit `c6fb5b11fa3f0695b1af23afd300ba557fc674fb` (pushed before this file). This file's SHA256 and push time are in `PREREG_HASH.txt`, committed after the push.

Pinned files (SHA256 at registration):

| file | sha256 |
|---|---|
| `experiments/flood_core/registry/events.json` | `e2545ed7b0f515682fdd5cc745d7934bdee9d20efd01d3b4f0a7274b3afab0e1` |
| `experiments/flood_final/registry_units.json` | `d70583c17ea1b2aeb5f1300f76bbeb11ecb342b8398d6646f2468f4385d07249` |
| `experiments/flood_final/events_final.py` | `7d213c701e91f3753b582ddeac8fd5702ba83f7d4912d8eb534e1b6609134156` |

## 1. What is tested
For each flood type, the method chosen on DEV data by the rule in §4 is scored **once** on the RESERVED events of that type, beside the baselines in §5. Types:

| type | taxonomy | RESERVED units / activations (clusters) |
|---|---|---|
| river | M1 fluvial | 11 units, 8 clusters: 3 EMS activations x 2 AOIs (Mozambique, Lower Saxony, Guadalquivir) + 5 Sentinel-1 events (Assam, Sunamganj, Lokoja, Kelantan, Tabasco) |
| rain / urban | M2 pluvial | 5 units, 4 activations (Latvia, Réunion, Mayotte, Basilicata) |
| waterlogging | M3 | 3 units, 2 events (Albania lowlands, Niger delta) |
| flash flood | M4 | 12 units, 7 activations (Mexico, Albania, Norway x2, Sweden, Chuuk, Portugal) |
| coastal | M5 | 16 units, 8 activations (Otis, Erick, Beryl, Chido, Jude, Gezani, Fytia, Harry) |
| compound | M9 | 6 units, 3 activations (Beryl, Harry, Portugal Feb 2026) |

Units of one activation are one cluster (one storm). An event can carry two tags (e.g. coastal + compound) and is then in both groups.

## 2. RESERVED events (frozen)
Chosen from EMS product metadata (exposure 2) or from a town point and a date in general reporting (exposure 1). Selection rules and every exclusion: `events_final.py`, `DECISIONS.md` D1–D7.

| unit | tags | region | date | reference (built at scoring) | product / basis |
|---|---|---|---|---|---|
| r_emsr857_aoi01 | fluvial | africa | 2026-01-10 | EMS EMSR857 AOI01 DEL monitoring 0 (Chibabel) | Heavy rain started in December, caused several floods in Mozambique (Limpopo AOIs) |
| r_emsr857_aoi02 | fluvial | africa | 2026-01-10 | EMS EMSR857 AOI02 DEL monitoring 0 (Massiguita) | Heavy rain started in December, caused several floods in Mozambique (Limpopo AOIs) |
| r_emsr712_aoi01 | fluvial | europe_mediterranean | 2023-12-24 | EMS EMSR712 AOI01 DEL monitoring 0 (Hase River) | flood events ... Lower Saxony (AOIs: Hase, Hunte, Weser rivers) |
| r_emsr712_aoi02 | fluvial | europe_mediterranean | 2023-12-24 | EMS EMSR712 AOI02 DEL monitoring 0 (Hunte River) | flood events ... Lower Saxony (AOIs: Hase, Hunte, Weser rivers) |
| r_emsr861_aoi01 | fluvial | europe_mediterranean | 2026-01-28 | EMS EMSR861 AOI01 DEL monitoring 0 (Cordoba) | a river overflow was forecast to affect the Guadalquivir River Basin |
| r_emsr861_aoi02 | fluvial | europe_mediterranean | 2026-01-28 | EMS EMSR861 AOI02 DEL monitoring 0 (Granada) | a river overflow was forecast to affect the Guadalquivir River Basin |
| r_emsr845_aoi02 | flash_flood | americas | 2025-10-12 | EMS EMSR845 AOI02 GRA monitoring 0 (Cazones de Herrera) | heavy rains ... severe flooding and landslides ... mud and debris (Mexico) |
| r_emsr845_aoi03 | flash_flood | americas | 2025-10-12 | EMS EMSR845 AOI03 GRA monitoring 0 (Poza Rica) | heavy rains ... severe flooding and landslides ... mud and debris (Mexico) |
| r_emsr850_aoi02 | flash_flood | europe_mediterranean | 2025-11-18 | EMS EMSR850 AOI02 DEL monitoring 0 (Gjirokaster) | heavy and moderate rainfall ... localized flooding, road blockages, landslides (Albania) |
| r_emsr850_aoi03 | flash_flood | europe_mediterranean | 2025-11-18 | EMS EMSR850 AOI03 DEL monitoring 0 (Mamurras) | heavy and moderate rainfall ... localized flooding, road blockages, landslides (Albania) |
| r_emsr683_aoi01 | flash_flood | europe_mediterranean | 2023-08-08 | EMS EMSR683 AOI01 DEL monitoring 0 (Vagamo) | extreme weather Hans ... heavy rainfall will produce floods (Norwegian mountain valleys) |
| r_emsr683_aoi02 | flash_flood | europe_mediterranean | 2023-08-08 | EMS EMSR683 AOI02 DEL monitoring 0 (Selsverket) | extreme weather Hans ... heavy rainfall will produce floods (Norwegian mountain valleys) |
| r_emsr775_aoi11 | flash_flood | europe_mediterranean | 2024-10-31 | EMS EMSR775 AOI11 DEL monitoring 0 (Viksdalen) | heavy rainfall ... floods and mass movements in many places in western Norway |
| r_emsr841_aoi01 | flash_flood | europe_mediterranean | 2025-09-06 | EMS EMSR841 AOI01 DEL monitoring 0 (Gottne) | a severe rainstorm and subsequent flooding ... entire villages were cut off |
| r_emsr872_aoi01 | flash_flood | oceania | 2026-04-08 | EMS EMSR872 AOI01 GRA monitoring 0 (Parem) | heavy rains and strong winds ... landslides and flash floods (Chuuk) |
| r_emsr872_aoi02 | flash_flood | oceania | 2026-04-08 | EMS EMSR872 AOI02 GRA monitoring 0 (Udot) | heavy rains and strong winds ... landslides and flash floods (Chuuk) |
| r_emsr742_aoi01 | pluvial | europe_mediterranean | 2024-07-28 | EMS EMSR742 AOI01 DEL monitoring 1 (Jelgava) | most precipitation ... around Riga 87 mm to 193 mm ... resulting in flooded territories |
| r_emsr742_aoi03 | pluvial | europe_mediterranean | 2024-07-28 | EMS EMSR742 AOI03 DEL monitoring 0 (Bauska) | most precipitation ... around Riga 87 mm to 193 mm ... resulting in flooded territories |
| r_emsr790_aoi02 | pluvial | africa | 2025-02-27 | EMS EMSR790 AOI02 GRA monitoring 0 (Saint Denis) | Tropical Cyclone GARANCE ... La Réunion (Saint-Denis) |
| r_emsr780_aoi08 | pluvial | africa | 2024-12-14 | EMS EMSR780 AOI08 GRA monitoring 0 (Dembeni) | Tropical Cyclone CHIDO ... Mayotte (Dembeni) |
| r_emsr930_aoi01 | pluvial | europe_mediterranean | 2026-09-02 | EMS EMSR930 AOI01 GRA monitoring 0 (Policoro) | a storm ... affected the cities of Policoro and Scanzano Jonico |
| r_emsr856_aoi01 | waterlogging | europe_mediterranean | 2026-01-06 | EMS EMSR856 AOI01 DEL monitoring 0 (Velipoje) | assess the areas covered by water (Velipoje, Skadar Lake, Buna lowlands) |
| r_emsr856_aoi02 | waterlogging | europe_mediterranean | 2026-01-06 | EMS EMSR856 AOI02 DEL monitoring 0 (Spiten) | assess the areas covered by water (Velipoje, Skadar Lake, Buna lowlands) |
| r_emsr703_aoi01 | coastal | americas | 2023-10-25 | EMS EMSR703 AOI01 GRA monitoring 0 (Acapulco Coast) | TC OTIS (Cat. 5) ... landfall over ... Acapulco ... floods and landslides |
| r_emsr703_aoi02 | coastal | americas | 2023-10-25 | EMS EMSR703 AOI02 GRA monitoring 0 (Acapulco Inland) | TC OTIS (Cat. 5) ... landfall over ... Acapulco ... floods and landslides |
| r_emsr805_aoi01 | coastal | americas | 2025-06-19 | EMS EMSR805 AOI01 DEL monitoring 1 (Acapulco) | Tropical Cyclone Erick-25 ... coastal area of Guerrero |
| r_emsr805_aoi03 | coastal | americas | 2025-06-19 | EMS EMSR805 AOI03 DEL monitoring 0 (Corralero) | Tropical Cyclone Erick-25 ... coastal area of Guerrero |
| r_emsr734_aoi09 | coastal, compound | americas | 2024-07-01 | EMS EMSR734 AOI09 GRA monitoring 0 (Bequia) | very heavy rainfall, strong winds and storm surge (Beryl) |
| r_emsr734_aoi17 | coastal, compound | americas | 2024-07-01 | EMS EMSR734 AOI17 GRA monitoring 0 (Campeche) | very heavy rainfall, strong winds and storm surge (Beryl) |
| r_emsr781_aoi01 | coastal | africa | 2024-12-15 | EMS EMSR781 AOI01 DEL monitoring 0 (Pemba) | TC CHIDO ... hurricane-force winds and torrential floods (Cabo Delgado) |
| r_emsr781_aoi05 | coastal | africa | 2024-12-15 | EMS EMSR781 AOI05 GRA monitoring 0 (Mecufi) | TC CHIDO ... hurricane-force winds and torrential floods (Cabo Delgado) |
| r_emsr793_aoi01 | coastal | africa | 2025-03-10 | EMS EMSR793 AOI01 DEL monitoring 0 (Monapo) | TC Jude ... hurricane-force winds and torrential flooding (Nampula) |
| r_emsr793_aoi02 | coastal | africa | 2025-03-10 | EMS EMSR793 AOI02 DEL monitoring 0 (Mogincual) | TC Jude ... hurricane-force winds and torrential flooding (Nampula) |
| r_emsr867_aoi01 | coastal | africa | 2026-02-10 | EMS EMSR867 AOI01 GRA monitoring 0 (Toamasina) | TC Gezani ... landfall near Toamasina |
| r_emsr867_aoi03 | coastal | africa | 2026-02-10 | EMS EMSR867 AOI03 GRA monitoring 0 (Ambatondrazaka) | TC Gezani ... landfall near Toamasina |
| r_emsr863_aoi02 | coastal | africa | 2026-01-30 | EMS EMSR863 AOI02 GRA monitoring 0 (Manakambahiny) | TC Fytia ... North West Madagascar |
| r_emsr863_aoi03 | coastal | africa | 2026-01-30 | EMS EMSR863 AOI03 GRA monitoring 0 (Amboditavolo) | TC Fytia ... North West Madagascar |
| r_emsr858_aoi08 | coastal, compound | europe_mediterranean | 2026-01-20 | EMS EMSR858 AOI08 DEL monitoring 0 (Muravera) | Extremely heavy rainfall ... very high waves of up to 6 metres (cyclone Harry) |
| r_emsr858_aoi10 | coastal, compound | europe_mediterranean | 2026-01-20 | EMS EMSR858 AOI10 DEL monitoring 0 (Orosei) | Extremely heavy rainfall ... very high waves of up to 6 metres (cyclone Harry) |
| r_emsr864_aoi01 | flash_flood, compound | europe_mediterranean | 2026-02-03 | EMS EMSR864 AOI01 DEL monitoring 0 (Ermidas Sado) | heavy and persistent rainfall ... significant maritime agitation ... flash flood notificat |
| r_emsr864_aoi02 | flash_flood, compound | europe_mediterranean | 2026-02-03 | EMS EMSR864 AOI02 DEL monitoring 0 (Rio de Moinhos) | heavy and persistent rainfall ... significant maritime agitation ... flash flood notificat |
| s1_assam_morigaon_2024 | fluvial | south_asia | 2024-07-03 | Sentinel-1 VV drop, 20 km search square at [92.34, 26.25] | Brahmaputra floods, Morigaon district, early July 2024 |
| s1_sunamganj_2024 | fluvial | south_asia | 2024-06-19 | Sentinel-1 VV drop, 20 km search square at [91.40, 25.07] | Surma floods, Sunamganj, June 2024 |
| s1_lokoja_2022 | fluvial | africa | 2022-10-10 | Sentinel-1 VV drop, 20 km search square at [6.74, 7.80] | Niger-Benue floods at Lokoja, October 2022 |
| s1_kelantan_2024 | fluvial | southeast_asia | 2024-11-30 | Sentinel-1 VV drop, 20 km search square at [102.10, 6.05] | Kelantan river floods (Pasir Mas), Nov-Dec 2024 |
| s1_tabasco_2020 | fluvial | americas | 2020-11-08 | Sentinel-1 VV drop, 20 km search square at [-92.93, 17.99] | Grijalva floods at Villahermosa, Nov 2020 (rain + reservoir releases) |
| s1_yenagoa_2022 | waterlogging | africa | 2022-10-15 | Sentinel-1 VV drop, 20 km search square at [6.27, 4.93] | prolonged Niger-delta flooding around Yenagoa, Oct 2022 |

## 3. How each reserved reference and label is built (fixed)
- **EMS units:** round 4's rules unchanged (`experiments/flood_validation/harness_round4.py` `place` + `reference`). The product is the one listed (lowest monitoring number, DEL before GRA). The box is a 4 km square centred on the product's flood (`BOX_SIDE_M`). Flooded = "Flooded area" or "Flood trace" covering at least half the 30 m cell. Valid = inside the product extent and not JRC permanent water.
- **Sentinel-1 units:** round 4's S1 method unchanged. That means a 20 km search square at the listed point, the earliest IW pass in the round-4 window after the listed date, and a same-orbit VV drop of at most −3 dB vs the January–March median of the event year. The box is centred on the S1 flood.
- **Labels per cell:** 1 flooded / 0 dry / −1 unobserved (invalid, or JRC occurrence ≥ 80 %). **Unobserved is never dry.**
- **Qualifies:** at least 50 flooded and at least 50 dry labelled cells (the project's `MIN_FLOODED_CELLS` / `MIN_DRY_CELLS`). A unit that fails to build after 3 tries, or does not qualify, is reported as **missing / not qualifying**, never as zero and never as a fail.
- **Secondary labels:** if Phase 4 adopts an urban-capable flood detector, it is applied by the same fixed rule to every reserved unit. The scores against those labels are reported as a **secondary** analysis. They never replace the primary labels above, and no verdict depends on them.

## 4. Candidate methods per type, and the rule that picks one (DEV only)
- **Learned model v2.**
  - LightGBM with the hyperparameters of `experiments/flood_learned/model.py` (`LGBM_PARAMS`, unchanged).
  - Trained on **all DEV units**: the 29 clean batch-0 units plus the 38 new DEV units. Labels as §3; the 5 JRC-circular units are never labels.
  - Each training event carries equal weight.
  - Feature-set variants, all from `flood_learned/model.py` plus the coastal features added in Phase 3: `full`, `open` (no FABDEM/MERIT), `no_landcover`.
  - `open_gedtm30` (`open` with GEDTM30 terrain) is a candidate only if GEDTM30 can be read for every DEV and RESERVED unit at freeze time.
- **Logistic regression** on the same variants: a candidate on the same footing.
- **Production modules** at their current config defaults:
  - fluvial (validated config);
  - pluvial (only where its inputs build within the 1 h limit);
  - waterlogging;
  - flash flood.
- **Choice rule, per type:**
  - Compute each candidate's **leave-region-out** mean within-event AUC over the DEV units of that type (5 regions, as `flood_learned/events.py`, extended to the new regions by UN M49).
  - The candidate with the highest DEV mean is the type's method. Ties within 0.005 go to the more open-licence one: logistic before LightGBM, `open` before `full`.
  - The choice, with its DEV numbers, is written to `experiments/flood_final/results/method_choice.json` and committed **before** the reserved pass (Phase 7).
- **River (M1) has two pre-registered verdicts:**
  - (a) the **fluvial module** in its validated configuration: an independent re-test;
  - (b) the method the rule chooses, if different.
- **SFINCS is not a held-out candidate here.**
  - It needs a per-event domain, forcing and boundary set-up that cannot be built for 47 reserved units on this machine.
  - It is run on DEV cases only (Phase 6) as a diagnostic. A later pre-registration may add it.
- **Calibration.**
  - Isotonic regression is fitted on the chosen method's pooled DEV out-of-fold (leave-region-out) predictions and applied unchanged to the reserved predictions.
  - The output may be called a **probability** only if, on the reserved units, the calibration intercept 0 and slope 1 both lie inside their cluster-bootstrap 95% intervals (weak calibration, Van Calster et al. 2016). Otherwise it is called a **score**.

## 5. Baselines (on the same cells)
- **HAND:** −MERIT HAND.
- **JRC occurrence.**
- **Distance to water:** −distance to OSM water or JRC permanent water.
- **Coastal and compound only, in addition:** −GLO-30 elevation and −distance to the sat-io shoreline.
- **"Best baseline"** = the best of these **chosen after seeing each event**. This favours the baselines and is reported as secondary.

## 6. Metrics
- **Primary:** within-event ROC AUC on each unit's common cells (labelled, and every score defined).
- **Uncertainty:**
  - per unit: a paired spatial block bootstrap with 33 × 33-cell (990 m) blocks, 1,000 replicates, seed 20261114 + sha1(unit) (flood_baselines' rule);
  - means: the two-stage cluster × block bootstrap over activation clusters.
- **Secondary:**
  - average precision (PR-AUC) per unit;
  - calibration (ECE over 10 equal-width bins, intercept, slope, Brier skill vs the DEV prevalence) on pooled reserved cells, each unit weighted equally;
  - extent IoU at the threshold that makes the predicted flooded area equal the reference's flooded area within each unit (no tuned threshold);
  - per-setting groups (urban, arid, mountain, coastal, delta; rules as `flood_learned/events.py`).

## 7. Pass bar per type (basis: the project's 0.70 bar plus the audit's §9 amended bar)
A type's method **passes** if, over its qualifying reserved units, all three hold:
1. mean within-event AUC ≥ **0.70** (`harness.AUC_MIN`, every round's bar);
2. mean AUC − HAND with its cluster × block 95% interval **above 0**. HAND is the baseline flood_baselines found strongest on average; beating it, not only an absolute bar, is the audit's proposed amendment;
3. at least **3 qualifying units in at least 2 clusters** (the audit's ≥ 3 events).

- If (3) fails, the verdict is **not-run (insufficient)**, not fail.
- The South Asian basin-linked river units (D6) are in the pooled river verdict and are also reported on their own.
- **Fluvial-module verdict (a)** uses the same three conditions.

## 8. One-shot rule
- Before the reserved pass, the code is frozen by a git tag `flood-final-heldout-freeze` on a pushed commit that also holds `method_choice.json`.
- The scoring script refuses to run unless:
  - this file's SHA256 equals the one in `PREREG_HASH.txt`;
  - the tag exists;
  - no reserved result file exists yet.
- It writes `results/heldout.json` once.
- Nothing is re-run or changed after any reserved number is seen. A unit that breaks during the pass is logged and reported as missing. Fixes made after seeing reserved numbers may only appear as clearly labelled post-hoc diagnostics.
- Every number in the evidence packs (`paper/evidence/<M#_type>/`) comes from `results/heldout.json` or from DEV results committed before the freeze.
