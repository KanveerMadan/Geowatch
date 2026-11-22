# flood_round3: why round 2 failed (Phase 1 diagnosis)

**Data.** Burned units only: 169 units. That is 114 round-2 DEV units (which include round 1's test units) plus 55 built round-2 test units.
- Labels: 117 EMS, 50 our Sentinel-1 VV drop, 2 UNOSAT.
- Code: `catalog.py`, `diagnose.py`, `diagnose_ee.py`.
- Numbers: `results/diagnosis.json`, `timing_imerg.json`, `timing_discharge.json`, `label_agreement.json`.
- "Learned" means the round-2 candidate for that type (resid_lgbm, full_lr or the type model). DEV numbers are leave-region-out predictions; round-2 test numbers are the scored pass.

## Summary
| # | suspected cause | verdict | key number | fix (Phase 2–4) |
|---|---|---|---|---|
| a | information ceiling | **confirmed** | learned score vs −elevation: within-unit Spearman 0.79–0.87; elevation-type features carry 37–56 % of the correction's SHAP | event drivers: water level per reach, rain field, surge, defences |
| b | image timing | **confirmed for rain; partly for others** | rain images: median 4 d after the IMERG peak; 77 % ≥ 3 d, none ≤ 1 d. AUC falls with lag for every method (all types: 0.79 at ≤ 1 d → 0.72 at 4–7 d) | maximum lag per type; maximum-extent composites from every pass in the window |
| c | terrain masks in label sources | **no hard mask found**; a radar false-positive floor found instead | EMS: no shared cutoff (HAND p99.5 of flooded cells, IQR 2.8–7.5 m). Our S1: P(flooded) rises again above HAND 20 m (1.6 % → 2.6 %) | HAND > 15 m unobserved for radar (GFM rule) |
| d | radar shadow / layover; double bounce | **shadow/layover ruled out; built-up blindness confirmed** | slope > 20° is 0.4 % of labelled flash cells. Built-up flood rate vs open: S1 0.13×, EMS radar 0.018×, EMS optical 0.36× | built-up = unobserved for radar labels; urban-capable labels for rain |
| e | label ceiling | **confirmed: S1 VV-drop labels disagree with independent optical maps** | S1 vs EMS optical/VHR, same event: κ 0.02 (rain), 0.05 (flash, coastal), 0.20 (river); vs EMS radar: 0.56–0.82 | rain, flash, coastal and compound scored on analyst/VHR/urban labels only; S1 for rural river and waterlogging |
| f | power | **confirmed: round 2 was underpowered for the gains on offer** | per-unit gain SD 0.054–0.10. At a gain of 0.015, river needs ~400 units for 90 % power; at 0.05, 17 | reserve sized from the power table; the fixes must raise the gain, not only the AUC |
| g | compound −0.08 | **confirmed: no anchor, out of distribution, a mistyped late unit** | Francine: full_lgbm 0.32 vs elevation 0.70. EMSR663 imaged 67 d after Freddy | anchored learner (score = anchor + λ·correction); timing and type checks at selection |
| h | resolution | **confirmed for rain** | rain flooded patches: median 1 cell; 21 % of flooded cells sit in 1–2-cell patches (waterlogging 3 %, river 0.5 %) | rain labels at 10 m; subgrid DEM; urban labels |
| i | event typing | **confirmed, small** | 17 of 169 units' drivers disagree with their tag (7 river units with no flood wave at the main reach; 2 dam breaks under flash; 1 compound imaged 67 d late) | type checked against drivers at selection (RESERVE_CRITERIA_R3 §2) |
| new 1 | **S1 baseline inside the flood or the wet season** | **confirmed** | 8 of 50 S1 units: the Jan–Mar baseline of the event year contains or precedes the event in the same wet season (Beira, Auckland, Antananarivo, Durban, Nairobi, Fort Lauderdale, Khuzestan, Dubai) | baseline [t0 − 60 d, t0 − 6 d] on the same orbit |
| new 2 | **S1 rain labels mostly noise** | **confirmed** | in 7 of 12 S1 rain units with ≥ 200 labelled cells above HAND 20 m, P(flooded \| HAND > 20 m) is within 1.5× of P(flooded \| HAND < 3 m): e.g. Auckland 0.036 vs 0.032, Klang 0.032 vs 0.028, Seoul 0.007 vs 0.007 | open-water rule (VV ≤ −15 dB as well as the drop); no rain verdict from VV-drop labels alone |

## a. Information ceiling
- The learned scores rank cells almost like elevation. Within-unit Spearman with −elevation, median over DEV units:

  | model | river | rain | waterlogging | flash | coastal | compound |
  |---|---|---|---|---|---|---|
  | full_lr | 0.79 | 0.76 | 0.85 | 0.74 | 0.81 | 0.72 |
  | resid_lgbm | 0.88 | 0.88 | 0.88 | 0.85 | 0.86 | 0.84 |
  | full_lgbm | 0.86 | 0.83 | 0.83 | 0.82 | 0.83 | 0.82 |

- resid_lgbm starts from an elevation-only fit. Even in its correction, terrain features carry 37–48 % of |SHAP|; in full_lgbm they carry 43–56 %.
- The remaining features are static too (land cover, climate rain, JRC history). **No feature says how much water this event brought, or where it went.**

**Where elevation is wrong** (`part_a2`). Take elevation's top-k cells as its wet call (k = flooded count). Then:
- **Misses:** 51 % (river) to 80 % (compound) of flooded cells are missed. **85–95 % of the misses are near the river** (GLO-30 HAND < 2 m). They are flooded although higher than dry low ground elsewhere in the box, because the water surface slopes downstream and because the event's water reached them.
- **False alarms:** 16–43 % sit in closed depressions (> 0.3 m deep) that the event did not fill.
- **Near-river cells on both sides:** almost no false alarm is > 1 km from mapped water, or at HAND ≥ 2 m. Inside these floodplain boxes, low HAND alone cannot separate wet from dry. What separates them is **this event's water level along the reach, connectivity, and defences**.

**Headroom test: how much can reweighting the terrain gain?** An *oracle* picks, per event and with the labels in hand, the best linear mix of within-unit percentiles of −elevation, −GLO-30 HAND and −distance to water. No real method can do better than this with those inputs.

| type | units | elevation | oracle elev+HAND | oracle elev+HAND+distance | oracle gain |
|---|---|---|---|---|---|
| river | 58 | 0.818 | 0.825 | 0.839 | **+0.021** |
| waterlogging | 25 | 0.716 | 0.737 | 0.760 | +0.044 |
| flash | 31 | 0.765 | 0.802 | 0.828 | +0.063 |
| coastal | 26 | 0.756 | 0.763 | 0.769 | **+0.013** |
| compound | 19 | 0.760 | 0.777 | 0.786 | **+0.026** |
| rain | 31 | 0.670 | 0.692 | 0.703 | +0.034 |

- For river, coastal and compound, even the oracle gains less than the ~0.04–0.05 a test of practical size can confirm (§f).
- **So event information that only re-weights these terrain layers cannot pass those three types.** It must change the spatial pattern:
  - which low ground the water reached (connectivity from the river or sea, defences, depression filling by volume);
  - where the water surface sits along the reach;
  - for rain, ponding at street scale.
- Flash and waterlogging have room within the terrain layers themselves.

**Tested and dropped: a relative-elevation model.** Elevation minus the water surface interpolated from mapped-water cells (inverse distance, k = 16) is *worse* than elevation in every type (river −0.103; better in 16 % of units). The labelled floods reach low ground far from mapped water, where a detrended surface misleads. GLO-30 HAND fails in the same way (river 0.686 vs 0.818).

## b. Image timing
**Lag of the label image after the rain peak.** The peak is IMERG V07: the day with the largest 3-day sum over the box plus 25 km, in [event − 14 d, event + 3 d].

| type | units | median lag (d) | IQR | share ≥ 3 d |
|---|---|---|---|---|
| river | 58 | 4 | 2–8 | 0.60 |
| rain | 31 | 4 | 3–8 | 0.77 |
| waterlogging | 25 | 8 | 6–12 | 0.92 |
| flash | 31 | 4 | 3–10 | 0.77 |
| coastal | 26 | 3 | 2–5 | 0.54 |
| compound | 19 | 3 | 2–8 | 0.63 |

**Mean AUC by label lag after the registry event date (all types):**

| lag | units | elevation | HAND | learned | gain |
|---|---|---|---|---|---|
| ≤ 1 d | 63 | 0.792 | 0.687 | 0.793 | −0.001 |
| 2–3 d | 53 | 0.766 | 0.700 | 0.772 | −0.015 |
| 4–7 d | 53 | 0.724 | 0.666 | 0.725 | −0.018 |
| > 7 d | 19 | 0.713 | 0.617 | 0.728 | +0.008 |

**Reading:**
- Every method degrades as the image gets later: the map shows less of the event.
- The suspicion "late images hand elevation the win" holds for **coastal and compound**: the learned model's gain is −0.08 and −0.10 at 4–7 d.
- It does not hold for **flash**: the gain rises with lag (Spearman +0.52), probably because late flash labels keep only the wide valley-floor ponding.
- **Rain is the clear case.** No rain label image is within a day of the rain peak. Urban rain water drains within hours to a day, so the labels see leftover ponding and noise (new 2). Rain needs peak-time imagery or urban-capable references. Otherwise its labels cannot carry a pass for any method.

Discharge timing (GEOGloWS v2; river-type units) is in `timing_discharge.json`, summarised in §i.

## c. Terrain masks in the label sources
**P(flooded | MERIT HAND bin)**, pooled over units:

| HAND (m) | 0–1 | 1–2 | 2–3 | 3–5 | 5–7.5 | 7.5–10 | 10–15 | 15–20 | 20–30 | 30–50 | > 50 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| our S1 | 0.293 | 0.141 | 0.102 | 0.085 | 0.052 | 0.028 | 0.017 | 0.016 | 0.018 | 0.022 | 0.026 |
| EMS radar | 0.202 | 0.160 | 0.132 | 0.086 | 0.050 | 0.016 | 0.006 | 0.003 | 0.002 | 0.001 | 0.000 |
| EMS optical | 0.318 | 0.227 | 0.165 | 0.143 | 0.112 | 0.079 | 0.038 | 0.019 | 0.014 | 0.010 | 0.010 |

- **No hard terrain cutoff.** No source shows P = 0 above one shared threshold, and the flooded cells' HAND p99.5 varies widely between units. A pre-applied terrain mask in EMS or UNOSAT products is not supported by the data. So no "unobserved = dry" free points come from that.
- **Our S1 labels have a false-positive floor.** Above HAND ~15 m the flood rate stops falling and rises again (1.6 % → 2.6 %). Real floods do not climb hills; this is VV-drop noise (wet soil, vegetation, speckle).
- This is the reason for GFM's exclusion layer. Fix R3-O-1 (HAND > 15 m unobserved for radar labels) follows that standard practice, and it applies to every method.

## d. Radar artefacts
- **Shadow / layover.** GLO-30 slope > 20° covers 0.4 % of labelled flash-flood cells and 0 % elsewhere. Layover and shadow need slopes above ~29° (sensor-facing) or ~44° (facing away) at IW incidence. **Ruled out as a material cause.** The 20° exclusion (R3-O-3) is kept as a cheap, conservative rule.
- **Double bounce / built-up blindness.** Flood rate in built-up cells (built share ≥ 0.5) against open cells, all burned units:

  | source | built-up cells labelled | flood rate built-up | flood rate open | ratio |
  |---|---|---|---|---|
  | our S1 | 268,562 | 0.028 | 0.215 | 0.13 |
  | EMS radar | 59,197 | 0.0025 | 0.142 | 0.018 |
  | EMS optical | 122,403 | 0.073 | 0.200 | 0.36 |

  - Radar labels barely ever mark a built-up cell flooded. Their "dry" built-up cells are unobserved, not dry.
  - Rain units are where it matters most: 37 % of their labelled cells are built-up.
  - Fix R3-O-2: radar built-up cells are unobserved. Rain then needs urban-capable labels (coherence, VHR) to be assessed in cities at all.

## e. Label ceiling (independent sources on the same event)
**Method.** For 95 EMS units (2015+, EMS image and an S1 pass ≤ 3 d apart, ≥ 50 EMS-flooded cells), our S1 VV-drop label was built with the round-4 rule, unchanged, on the same grid. Agreement was measured on cells both sources observed (`label_agreement.json`; 4 units had no S1 pass). The binary S1 label used as a score for the EMS label gives an "AUC", which is the balanced accuracy.

| type | EMS made from | units | κ (median) | S1 recall of EMS flood | S1 "AUC" for EMS |
|---|---|---|---|---|---|
| river | optical / VHR | 9 | 0.20 | 0.22 | 0.59 |
| river | radar | 33 | 0.58 | 0.75 | 0.83 |
| waterlogging | optical | 5 | 0.10 | 0.31 | 0.60 |
| waterlogging | radar | 3 | 0.82 | 0.88 | 0.92 |
| flash | optical | 11 | 0.05 | 0.06 | 0.52 |
| flash | radar | 12 | 0.56 | 0.77 | 0.88 |
| rain | optical | 8 | 0.02 | 0.07 | 0.51 |
| coastal | optical | 6 | 0.05 | 0.06 | 0.52 |
| coastal | radar | 6 | 0.28 | 0.32 | 0.65 |
| compound | optical | 3 | 0.02 | 0.04 | 0.51 |
| compound | radar | 6 | 0.38 | 0.43 | 0.70 |

**Reading:**
- Against radar-made EMS maps our S1 label agrees well for river, waterlogging and flash: a shared sensor, but an independent analyst and method.
- Against **independent optical / VHR maps it agrees at chance level** for rain, flash, coastal and compound (κ ≤ 0.05, "AUC" ≈ 0.51–0.52). It agrees only weakly for river (0.20).
- The two sensors see different floods: optical sees water among buildings and vegetation, at a different time; radar sees open water.
- **Consequence:**
  - A VV-drop label cannot carry a rain, flash, coastal or compound verdict. Those types need analyst/VHR maps (EMS optical, UNOSAT, Maxar), urban coherence labels or surveyed marks.
  - S1 labels stay usable for rural river and waterlogging floods.
  - A type whose only labels are S1 VV-drop has a label ceiling too low to show a gain over elevation of the size §f needs.
  - The v3 rule (open-water test, baseline fix) is re-checked against the same EMS maps in Phase 2.

## f. Power
Per-unit gain = learned − better baseline. Units come from rounds 1 and 2 (DEV leave-region-out plus the round-2 test). The normal approximation gives lower bounds, because the cluster × block bootstrap is wider.

| type | units | mean gain | SD | needed (+30 %) at Δ 0.02 | Δ 0.03 | Δ 0.05 |
|---|---|---|---|---|---|---|
| river | 58 | +0.016 | 0.054 | 101 | 46 | 17 |
| rain | 31 | −0.030 | 0.064 | 140 | 63 | 24 |
| waterlogging | 25 | +0.016 | 0.091 | 286 | 128 | 47 |
| flash | 31 | −0.003 | 0.071 | 175 | 78 | 29 |
| coastal | 26 | −0.043 | 0.093 | 298 | 133 | 49 |
| compound | 19 | −0.037 | 0.101 | 348 | 155 | 56 |

**Reading:**
- Round 2's gains (+0.012 to +0.016) would have needed hundreds of events to confirm. **No test of practical size can confirm them.**
- A pass needs both of these:
  1. a much larger gain, about 0.04–0.05, which only event-specific information can give (a);
  2. less per-unit noise in the gain, which the label fixes (c, d, new 1–2) and the anchored learner (g) give.
- The reserve is sized from this table at the gain Phase 4's dev CV predicts. It is set in Phase 3 before any model is built, at a planning gain, and never below 5 usable units.

## g. Compound −0.08
Round-2 test, compound (5 units):

| unit | elevation | HAND | full_lgbm (chosen) | lag (d) |
|---|---|---|---|---|
| r_emsr663_aoi01 (Freddy, Malawi) | 0.984 | 0.527 | 0.933 | **67** |
| s1_helene_steinhatchee_2024 | 0.634 | 0.473 | 0.610 | 11 |
| s1_remal_satkhira_2024 | 0.752 | 0.672 | 0.788 | 4 |
| s1_francine_terrebonne_2024 | 0.697 | 0.640 | **0.320** | 6 |
| s1_dana_kendrapara_2024 | 0.663 | 0.611 | 0.672 | 3 |

- **Francine alone gives −0.38.** The box is marsh at sea level: flooded cells' median elevation is 0.04 m, dry cells' 0.20 m, NDVI −0.06 vs 0.29.
  - The unanchored full_lgbm ranked it backwards. Its 14 DEV compound units contain nothing like a whole box within 0.2 m of sea level.
  - That is **out of distribution with no anchor**. An anchored model (score = elevation + λ·correction, λ from inner CV) cannot fall far below its anchor.
- **EMSR663 was imaged 67 days after the storm.** A map made two months later shows standing water, not the compound surge-and-rain flood its tag names (mistyped by timing, §i).
- Helene was imaged 11 days after landfall: surge long gone.
- **Fixes:**
  - the anchored learner;
  - per-type maximum lag;
  - typing by drivers at selection.

## h. Resolution
| type | units | median flooded-patch size (30 m cells) | share of flooded cells in 1–2-cell patches |
|---|---|---|---|
| rain | 31 | 1 | 0.21 |
| waterlogging | 25 | 2 | 0.03 |
| river | 58 | 6 | 0.005 |

- Rain floods in the labels are single 30 m cells, the size of the speckle. Part of this is real: street-scale ponding is smaller than a cell. Part is noise (new 2).
- **Rain needs 10 m labels and a sub-grid DEM**: LiDAR where it exists (3DEP, AHN, EA, CNIG, GSI 5 m), FABDEM/GLO-30 elsewhere.

## i. Event typing (drivers vs tag)
**Drivers:**
- **Discharge:** GEOGloWS v2 daily discharge at the box's largest reach (point within the box + 0.05°; within the box only for flash floods). The peak is taken in [event − 10 d, event + 7 d], with an empirical annual-maximum return period (`timing_discharge.json`; 120 units).
- **Rain:** IMERG as in §b.

**Discharge timing, river-driven types:**

| type | units | label image − discharge peak (median, IQR) | flow at image / peak flow (median) | peak return period (median) | share with RP < 1.5 y |
|---|---|---|---|---|---|
| river | 57 | 0 d [−2, 2] | 0.65 | 4.6 y | 0.18 |
| waterlogging | 24 | 6 d [2, 12] | 0.69 | 4.7 y | 0.25 |
| flash | 26 | 2 d [1, 5] | 0.58 | 5.5 y | 0.12 |

- River labels are close to the discharge peak at the main reach (median 0 d, at 65 % of peak flow). The late images in §b are late against the rain peak, not the flood wave.
- For river, timing explains less than it does for rain.

**Units whose drivers do not match their tag:** 17 of 169 (`summarise_ei.py`).
- **7 river units** show no flood wave at the box's main reach (peak RP 1.0–1.2 y): EMSR853 AOI02/04, EMSR865 AOI01, EMSR855 AOI01, EMSR698 AOI01, EMSR684 AOI05, EMSR668 AOI02. Either a tributary or local rain flooded the box, or the largest reach in the box is the wrong river. The round-3 selection checks the reach's discharge (RESERVE_CRITERIA_R3 §2).
- **2 flash units are dam-breach floods** with < 10 mm of rain (EMSR750, Arbaat Dam). They are correctly double-tagged, but should not be scored as rain-driven flash floods.
- **1 flash unit (Baghlan 2024) shows only 15 mm in IMERG.** That is likely IMERG missing a convective storm, not a mistype; the flag stays as a data-quality note.
- **1 compound unit (EMSR663) was imaged 67 d after the storm** (§g).
- **Valencia 2024** is tagged rain, flash and compound; the Poyo ravine peaked at a 29-y discharge. That is consistent with its compound tag.

**Reading:** mistyping is real but small (≈ 10 % of units). It matters most for compound (2 of 19) and for flash (4 of 31). Round 3 types each candidate by its drivers at selection time.

## Causes not on the list
1. **S1 baseline in the flood / wet season** (table above): 8 of 50 S1 units.
2. **S1 VV-drop alone is not a water detector.** Without an absolute low-backscatter test it fires on wet soil and vegetation change. This is the main reason the rain labels carry almost no signal.
3. **Underpowered design** (f). This is not a modelling flaw. With the per-unit spread of rounds 1–2, a few dozen events can only confirm gains of ~0.04–0.05.

## j. Where the per-unit gain spread comes from (`noise_split.py`, `results/noise_split.json`)
**Method:** on burned v3 units, the paired 990 m block bootstrap gives each unit's within-unit variance of the gain (learned minus the better baseline). The rest of the spread between units is true event-to-event difference.

**Result:** a 3.99 km unit holds a median of only 25 blocks (min 9).

| type | units | gain | SD total | SD within a unit | SD between events | within share of variance |
|---|---|---|---|---|---|---|
| river | 31 | +0.017 | 0.064 | 0.036 | 0.053 | 32 % |
| waterlogging | 18 | −0.007 | 0.084 | 0.043 | 0.072 | 26 % |
| coastal | 14 | −0.017 | 0.050 | 0.059 | 0.000 | 100 % |
| compound | 9 | −0.006 | 0.077 | 0.065 | 0.041 | 71 % |
| flash | 4 | −0.011 | 0.045 | 0.029 | 0.034 | 43 % |
| rain | 3 | +0.022 | 0.026 | 0.020 | 0.017 | 59 % |

**Reading:**
- **Coastal and compound:** the spread is mostly sampling noise inside units that are too small.
  - With about 4× the blocks per unit, the within-unit SD roughly halves. Coastal's projected total SD becomes ≈ 0.03 and compound's ≈ 0.05.
  - At Δ 0.03 the units needed would drop from 38 to ≈ 13 for coastal, and from 90 to ≈ 38 for compound.
- **River and waterlogging:** the spread is mostly real difference between events.
  - Bigger units help only a little: river would need ≈ 47 units instead of 62.
  - What helps more is a method whose gain is consistent across events: the anchored learner, which can fall back to its anchor (λ → 0) where the correction does not help.
- **Assumption behind the projection:** the within-unit variance scales with 1 / blocks, and the gain itself does not change with box size. That is untested; the DEV CV in Phase 4 is re-run on bigger boxes before the freeze.
