# A learned flood model vs HAND and the current modules: batch 0 (29 cached events)

**Branch:** `exp/flood-learned` (fast-forwarded onto `origin/exp/flood-baselines` @ `d1894e4` first, so the cached-input code is here). **Experiments only:** no production code, label, reference, pre-registration or UI was changed. Every event passed the flood-core registry gate (`flood_baselines.events.gate`), so no reserved event was read. All numbers below come from `results/learned.json`; `results/tables.md` has the full set: every run, every group, the reliability bins and the setting tags.

**This is the checkpoint the brief asked for: results on the 29 cached events, before the event set is expanded.** Nothing was downloaded for new events.

---

## 0. Summary

1. **Held out by event cluster, the learned model beats HAND on average.**
   - Leave-cluster-out (LCO), LightGBM: mean within-event AUC **0.711** against HAND's **0.637** over the 29 events.
   - The difference is **+0.074 [+0.019, +0.133]** (cluster × block 95% CI).
   - Per event: it is above HAND on 17 of 29. It is clearly above (paired 95% interval above 0) on **10** and clearly below on **4**.
2. **It also beats every current module on the mean (LCO):**

   | module | model − module |
   |---|---|
   | fluvial | +0.056 [+0.004, +0.117] |
   | waterlogging | +0.074 [+0.024, +0.123] |
   | flash flood | +0.117 [+0.052, +0.173] |
   | pluvial | +0.142 |

3. **It does not clearly beat the best baseline picked after seeing each event:** +0.020 [−0.024, +0.075].
4. **Held out by region, the LightGBM edge over HAND is not clear:** leave-region-out (LRO) +0.035 [−0.040, +0.104].
   - Logistic regression transfers better here: **+0.056 [+0.004, +0.106]** LRO.
   - The model mostly learned what floods *within* regions it has seen.
5. **The whole gain comes from land cover, mostly WorldCover cropland share.**
   - Without the WorldCover classes, the model is level with HAND: **+0.007** (LCO and LRO alike).
   - With terrain, hydrography and water history only, it is −0.007.
   - Cropland is the top feature by gain (32 %) and by held-out permutation drop (−0.043 AUC).
   - I cannot tell from these references whether that is physics (floodplains are farmed) or the references' blind spots (water is visible on fields, not between buildings; paddies count as flood, audit F5/MM5). See §4.
6. **By flood type (LCO, Δ vs HAND):**

   | type | events | Δ vs HAND | what it means |
   |---|---|---|---|
   | fluvial | 7 | **+0.172 [+0.082, +0.294]** | clear; it also beats the fluvial module, +0.097 [+0.007, +0.176] |
   | waterlogging | 6 | +0.102 [−0.034, +0.245] | not clear (logistic regression: +0.128 [+0.011, +0.214]) |
   | rain / pluvial | 6 | +0.031 [−0.055, +0.141] | no |
   | flash flood | 8 | −0.015 [−0.079, +0.080] | no; LRO −0.091 |

   **So the brief's goal is not met for rain or flash floods.** The learned model is no better than HAND on them. It is much better than the pluvial and flash-flood recipes, but those are worse than HAND already.
7. **By setting:** it helps in urban boxes, +0.117 [+0.007, +0.212] (13 events). It does not help in arid boxes (6 events: −0.023 LCO, −0.116 LRO), on the one mountain event, or in Europe / Mediterranean under LRO (−0.107). Its worst single event is **Derna 2023**: 0.662 against HAND 0.961 (LCO), and 0.251 (LRO).
8. **Output: a score, not a probability.**
   - Held-out calibration slope 0.59 [0.43, 0.88]: predictions are too extreme.
   - Mean predicted vs observed flooded share per event correlates only weakly across events (Spearman +0.26).
   - None of the six headline runs is even weakly calibrated (intercept 0 and slope 1 both inside their intervals).
9. **What would most improve it.**
   - **More events of new kinds and in new regions:** the learning curve flattens after about 13 training events, while the region gap stays.
   - **A reference that can see water among buildings**, to settle whether the land-cover signal is real.
   - **Not more rain data:** rain features add nothing within a 4 km box (−0.004 when permuted).
   - **Better terrain:** a small effect. FABDEM → GLO-30 costs 0.016 AUC, and the fully open model (no FABDEM, no MERIT) keeps +0.063 of the +0.074. GEDTM30 could not be read (server fault).

**Recommendation before expanding:** the next batch should be chosen to test point 5. It should include urban and peri-urban events with VHR/optical references, arid and mountain flash floods, and a pre-registered held-out set of new events never used for development (§8).

---

## 1. Data

### 1.1 Events (batch 0)
- **The 29 clean cached development events.** These are flood_baselines' 34 qualifying units (≥ 50 flooded and ≥ 50 dry evaluation cells) minus accra, capetown, dhaka, hcmc and nusantara.
  - Those five were dropped because their reference is JRC occurrence itself (flood_baselines A3), so using them would put the label into a feature.
  - hcmc's missing pluvial inputs are therefore moot.
- **29 events, 18 registry link clusters, 5 regions**, all with 30 m evaluation cells.
- **References:**
  - 17 Copernicus EMS delineations;
  - 10 Sentinel-1 VV-drop maps;
  - 2 UNOSAT products (Sindh, Sylhet).
- **All inputs reused from the flood_baselines cache:** MERIT HAND/upa, FABDEM slope, CHIRPS, IMERG, SoilGrids clay, JRC occurrence and the pre-event JRC/S1 water history, distance to water, and the four modules' inputs. Nothing was rebuilt.

### 1.2 Labels per 30 m cell (`events.labels`)
- **1 flooded / 0 dry:** the cached reference's valid cells.
- **−1 unobserved:** the reference's invalid cells, and also any cell with JRC occurrence ≥ 80 % (`JRC_PERMANENT_WATER_OCCURRENCE_PCT`, the project's existing permanent-water rule).
- **Unobserved cells are never used as dry or as anything else:** they are not in training and not in scoring. A test enforces this (`test_labels_unobserved_never_dry_and_permanent_water_excluded`).
- **Training uses all labelled cells; scoring uses the common cells** (labelled, and every comparator defined), exactly flood_baselines' cells. Check: every comparator AUC reproduces `baselines.json` on all 29 events, apart from pluvial on 7 events, which differs by ≤ 0.0003. That comes from storing comparator scores as float32, which adds a few ties.

### 1.3 Layers fetched for this experiment (`fetch.py`)
- **Grid and cache.** Each event's cached box grid, grown by 67 cells (2 km, flood_baselines' distance margin), so window derivatives are not truncated at the box edge. One event at a time, cached and resumable: 29 events in about 12 min, 60 GB free throughout.
- **Terrain:** Copernicus DEM GLO-30 `2024_1` and FABDEM. GEDTM30 v1.2 was attempted on every event and **failed**:
  - The OpenGeoHub server answers byte-range requests with truncated bodies (16,376 of 16,384 bytes, later 0).
  - GDAL cannot open the COG from either environment. The prototype read the same URL on 2026-10-31.
  - `fetch --redo-step gedtm30` retries it, and the `full_gedtm30` variant runs automatically once it reads.
- **Hydrography and water:** MERIT upa at the cell; HydroSHEDS 15″ flow accumulation; JRC GSW 1.4 recurrence; and a water mask (flood_baselines' cached OSM water OR JRC permanent water).
- **Land cover:** WorldCover class fractions (10 m → 30 m mean). The map is the latest one before the event year. Events before 2021 use the 2020 map: dharavi 2017, kerala 2018 and beira 2019 get a post-event map.
- **Vegetation:** Sentinel-2 median NDVI over the calendar year before the event (the project's water-history rule).
  - Clouds are masked with **Cloud Score+ (cs_cdf ≥ 0.60)**.
  - QA60 was the first choice but masks nothing after ESA baseline 04.00 (Jan 2022): Hanoi's NDVI came out 0.01.

### 1.4 Features (`features.py`; 26 in the primary model)

| group | features | source |
|---|---|---|
| terrain (one set per DEM) | slope; Laplacian curvature (3 × 3); TPI over 990 m; height above the minimum within 2 km; depression depth (priority-flood fill − z); **height above the nearest mapped water** (a HAND without MERIT) | FABDEM / GLO-30 |
| hydrography | MERIT HAND; log upstream area (cell, and the 1 km focal max fluvial uses); log HydroSHEDS accumulation (open model only); **the fluvial module's score** | MERIT Hydro, HydroSHEDS |
| water history | distance to water; JRC occurrence; JRC recurrence (`pre_water` variant: pre-event JRC monthly frequency instead) | JRC GSW, OSM |
| rain extremes | IMERG p99.9 intensity; CHIRPS design day; CHIRPS annual | IMERG V07, CHIRPS v2 |
| soil, land, vegetation | SoilGrids clay; WorldCover built, tree, shrub, grass, crop, bare, wetland, mangrove; NDVI | SoilGrids, WorldCover, S2 |

**WorldCover water and the box position were left out on purpose.**
- **Water class:** an annual composite's water class can contain the flood.
- **Box-relative elevation:** boxes are centred on the reference flood (C72), so "low relative to the box" would encode the box rule. Neighbourhood windows (990 m, 2 km) are used instead.

---

## 2. Model and evaluation

- **LightGBM 4.7.0** is the primary model; **logistic regression** (median imputation + missing indicators, standardised, L2 C = 1) is the sanity check.
- **Weights.** Each training event carries equal total weight; within an event every labelled cell weighs the same.
- **Hyperparameters were fixed before any held-out score and never tuned:**
  - 15 leaves, learning rate 0.05, 300 trees, row and column subsampling 0.7 / 0.8, L2 1;
  - `min_child_samples` = 33 × 33 = 1,089: a leaf must hold at least one 990 m block's worth of cells, so it cannot fit a single spatially correlated patch.
  - A smaller (7 leaves, 150 trees) and a larger (31 leaves, 600 trees) model are reported and not used to choose (§3.5).
- **Splits** (never random pixels):
  - **LCO, 18 folds:** a registry cluster is held out whole. paiporta and valencia_2024 (one EMS product), derna, derna_2023 and volos (Storm Daniel), and the four Typhoon Yagi boxes always leave together.
  - **LRO, 5 folds:** UN M49 regions, merged so no cluster spans two regions (Storm Daniel puts Libya with Southern Europe). The regions are South Asia (8), Southeast Asia (6), Europe & Mediterranean (7), Americas (6), and Africa & West Asia (2).
  - A test checks that no fold trains on a unit linked to a held-out one.
- **Scoring is flood_baselines' own:**
  - within-event ROC AUC on the common cells;
  - 33-cell (990 m) blocks, 1,000 paired replicates, the same seeds, so the comparators' intervals are the baselines' intervals;
  - means by the two-stage cluster × block bootstrap.
  - "Best baseline" = the best of HAND, JRC occurrence and distance to water **chosen after seeing the event**, which favours the baseline.
- **The comparators** are the four modules at their current config defaults, scored on the same cells. The fluvial module is also a model *input*; it is a fixed recipe, so it carries no label information.

---

## 3. Results

### 3.1 Means over the 29 events (AUC; Δ with cluster × block 95% CI)

| score | mean AUC | Δ vs HAND | above / clearly above / clearly below HAND | Δ vs best baseline (post hoc) |
|---|---|---|---|---|
| **LightGBM, LCO** | **0.711** | **+0.074 [+0.019, +0.133]** | 17 / 10 / 4 | +0.020 [−0.024, +0.075] |
| LightGBM, LRO | 0.672 | +0.035 [−0.040, +0.104] | 16 / 8 / 5 | −0.019 [−0.083, +0.049] |
| LogReg, LCO | 0.702 | +0.065 [+0.015, +0.114] | 21 / 17 / 4 | +0.011 [−0.058, +0.090] |
| **LogReg, LRO** | 0.693 | **+0.056 [+0.004, +0.106]** | 20 / 14 / 4 | +0.002 [−0.071, +0.085] |
| LightGBM open (no FABDEM/MERIT), LCO | 0.700 | +0.063 [+0.007, +0.116] | 20 / 13 / 4 | +0.009 [−0.049, +0.074] |
| LightGBM open, LRO | 0.673 | +0.036 [−0.037, +0.095] | 18 / 9 / 7 | −0.018 [−0.085, +0.047] |
| *HAND* | 0.637 | | | |
| *fluvial module* | 0.655 | | | |
| *waterlogging module* | 0.637 | | | |
| *flash-flood module* | 0.594 | | | |
| *pluvial module* | 0.569 | | | |
| *JRC occurrence / distance to water* | 0.551 / 0.558 | | | |

The comparator rows equal flood_baselines' "excl. JRC-ref" column, as they must.

**Excluding round-4 test events and their aliases** (17 events / 12 clusters; flood_baselines' "clean" set):
- LightGBM LCO: 0.755, Δ vs HAND **+0.118 [+0.024, +0.187]**;
- LRO: +0.099 [−0.009, +0.170].

### 3.2 By flood type (registry mechanism; an event can have two)

| type (events / clusters) | HAND | best module | LGBM LCO | Δ vs HAND, LCO | Δ vs HAND, LRO | LogReg LCO Δ vs HAND |
|---|---|---|---|---|---|---|
| fluvial (7 / 6) | 0.631 | fluvial 0.706 | **0.803** | **+0.172 [+0.082, +0.294]**, clear on 5/7 | **+0.154 [+0.070, +0.275]** | +0.173 [+0.084, +0.272] |
| waterlogging (6 / 4) | 0.590 | flash 0.628 | 0.691 | +0.102 [−0.034, +0.245] | +0.050 [−0.111, +0.210] | **+0.128 [+0.011, +0.214]** |
| coastal (5 / 4) | 0.679 | waterlogging 0.706 | 0.722 | +0.043 [−0.073, +0.166] | +0.056 [−0.073, +0.173] | +0.009 |
| **rain / pluvial (6 / 6)** | 0.676 | fluvial 0.626 | 0.707 | +0.031 [−0.055, +0.141], clear on 1/6 | −0.011 [−0.110, +0.098] | −0.045 |
| **flash flood (8 / 5)** | 0.645 | fluvial 0.660 | 0.631 | −0.015 [−0.079, +0.080], clear on 1/8, clearly worse on 3 | **−0.091** [−0.185, +0.052] | +0.019 |

**Reading:**
- **Fluvial:** the learned model beats HAND and the fluvial module.
- **Waterlogging:** probably ahead of HAND, but not clearly with LightGBM.
- **Rain and flash floods: no.** It replaces the pluvial and flash-flood recipes with something better than they are (+0.12 and +0.03 to +0.18 on the means), but not better than HAND alone.
- **Group sizes:** these are 6–8 events in 4–6 clusters, so every interval is wide.

### 3.3 By setting (event-level tags, rules in `events.py`, values in `tables.md`)

| setting (events) | HAND | LGBM LCO | Δ vs HAND, LCO | Δ vs HAND, LRO |
|---|---|---|---|---|
| urban, GHS-SMOD 30/23 (13) | 0.600 | 0.717 | **+0.117 [+0.007, +0.212]** | +0.095 [−0.026, +0.195] |
| peri-urban, 21/22 (8) | 0.609 | 0.640 | +0.031 [−0.036, +0.109] | −0.011 |
| rural (8) | 0.726 | 0.772 | +0.046 [−0.037, +0.159] | −0.016 |
| coastal, LECZ + 10 km (12) | 0.619 | 0.702 | +0.083 [−0.014, +0.152] | +0.066 |
| delta, Red River only (4 / **1 cluster**) | 0.515 | 0.763 | +0.247 [+0.185, +0.306] | +0.235 |
| **arid, Köppen B (6)** | 0.633 | 0.609 | −0.023 [−0.121, +0.103] | **−0.116** [−0.292, +0.078] |
| mountain, Kapos (**1**: himachal) | 0.534 | 0.485 | −0.049, clearly worse | −0.044 |
| not arid (23) | 0.638 | 0.738 | **+0.099 [+0.028, +0.168]** | +0.074 [−0.008, +0.145] |

**By region:**

| region (events / clusters) | Δ vs HAND, LCO | Δ vs HAND, LRO |
|---|---|---|
| Southeast Asia (6 / 2) | **+0.213** | **+0.214** |
| South Asia (8 / 5) | +0.061 | +0.021 |
| Americas (6 / 5) | +0.075 | +0.062 |
| Europe & Mediterranean (7 / 4) | −0.002 | **−0.107** [−0.199, +0.029] |
| Africa & West Asia (2 / 2) | −0.028 | −0.028 |

**Where it beats HAND:**
- wet-climate river floodplains and deltas: Hanoi +0.42, Nam Dinh +0.34, Thai Binh +0.25, Kolonnawa, Bihar, Faenza;
- low coastal towns: Kyaukpyu, Sittwe;
- Milagro (+0.26) and Choloma (+0.16).

**Where it doesn't:**
- **dry, steep or canyon flash floods:**
  - Derna 2023: −0.30 (HAND 0.961; model 0.662 LCO, 0.251 LRO);
  - Bad Neuenahr: −0.11;
  - Himachal: −0.05;
- **Fort Myers Beach** (−0.11, surge on a barrier island);
- **every pluvial city box:** Dubai, Hai Phong, Dharavi, Valencia and Belize City are all within ±0.03 of HAND.

**Why Derna fails.** The model's flood/dry rule is learned mostly on wet, farmed plains. In a desert wadi through a city, it inverts.

**Limits of the tags.** "Mountain" has 1 event and "delta" 1 cluster, so neither supports a conclusion. The sat-io shoreline follows estuaries and lagoons, so Nam Dinh, Thai Binh and Kerala count as coastal.

### 3.4 Per event (AUC; Δ = LGBM LCO − HAND [paired 990 m-block 95% CI]; sorted by Δ)

| event | type | region | HAND | LGBM LCO | Δ vs HAND | LGBM LRO | LogReg LCO | fluvial | pluvial | waterlog. | flash |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hanoi | fluvial | SE Asia | 0.481 | 0.900 | **+0.419 [+0.291, +0.605]** | 0.897 | 0.820 | 0.916 | 0.477 | 0.810 | 0.587 |
| nam_dinh | waterlogging | SE Asia | 0.439 | 0.780 | **+0.342 [+0.253, +0.438]** | 0.773 | 0.710 | 0.775 | 0.438 | 0.744 | 0.637 |
| milagro | pluvial | Americas | 0.698 | 0.955 | **+0.257 [+0.155, +0.356]** | 0.931 | 0.957 | 0.763 | 0.849 | 0.740 | 0.426 |
| thai_binh | waterlogging | SE Asia | 0.271 | 0.521 | **+0.251 [+0.108, +0.394]** | 0.495 | 0.486 | 0.538 | 0.323 | 0.269 | 0.771 |
| faenza | fluvial | Europe | 0.687 | 0.906 | **+0.219 [+0.082, +0.336]** | 0.783 | 0.745 | 0.787 | 0.714 | 0.731 | 0.849 |
| kolonnawa | fluvial | S Asia | 0.606 | 0.824 | **+0.219 [+0.108, +0.324]** | 0.838 | 0.837 | 0.800 | 0.751 | 0.672 | 0.595 |
| kyaukpyu | coastal | SE Asia | 0.690 | 0.861 | **+0.171 [+0.044, +0.612]** | 0.921 | 0.905 | 0.897 | 0.607 | 0.719 | 0.653 |
| bihar_2026 | fluvial | S Asia | 0.603 | 0.771 | **+0.168 [+0.103, +0.229]** | 0.722 | 0.779 | 0.642 | 0.602 | 0.673 | 0.610 |
| choloma | flash | Americas | 0.614 | 0.774 | **+0.161 [+0.024, +0.302]** | 0.780 | 0.787 | 0.489 | 0.571 | 0.573 | 0.436 |
| pakistan_2022 | fluvial | S Asia | 0.514 | 0.651 | +0.137 [−0.018, +0.304] | 0.635 | 0.773 | 0.579 | 0.531 | 0.482 | 0.494 |
| volos | flash | Europe | 0.518 | 0.655 | +0.137 [−0.006, +0.283] | 0.648 | 0.673 | 0.560 | 0.514 | 0.560 | 0.475 |
| sittwe | coastal | SE Asia | 0.806 | 0.921 | +0.115 [−0.027, +0.185] | 0.920 | 0.917 | 0.862 | 0.469 | 0.837 | 0.681 |
| paiporta | flash | Europe | 0.501 | 0.575 | +0.074 [−0.060, +0.215] | 0.559 | 0.600 | 0.686 | 0.473 | 0.504 | 0.528 |
| encantado | fluvial | Americas | 0.779 | 0.850 | **+0.071 [+0.006, +0.142]** | 0.846 | 0.869 | 0.830 | 0.489 | 0.764 | 0.734 |
| black_river | coastal | Americas | 0.719 | 0.785 | +0.066 [−0.008, +0.159] | 0.788 | 0.616 | 0.712 | 0.736 | 0.709 | 0.690 |
| kerala_2018 | waterlogging | S Asia | 0.709 | 0.740 | +0.031 [−0.051, +0.110] | 0.583 | 0.792 | 0.463 | 0.629 | 0.773 | 0.576 |
| sylhet_2022 | waterlogging | S Asia | 0.730 | 0.756 | +0.026 [−0.018, +0.094] | 0.652 | 0.885 | 0.542 | 0.650 | 0.688 | 0.632 |
| belize_city | pluvial | Americas | 0.646 | 0.645 | −0.002 [−0.193, +0.482] | 0.596 | 0.638 | 0.609 | 0.466 | 0.701 | 0.685 |
| valencia_2024 | flash, pluvial | Europe | 0.706 | 0.695 | −0.012 [−0.104, +0.082] | 0.608 | 0.681 | 0.699 | 0.553 | 0.693 | 0.741 |
| dharavi | pluvial, waterlogging | S Asia | 0.640 | 0.627 | −0.013 [−0.181, +0.117] | 0.559 | 0.625 | 0.601 | 0.525 | 0.692 | 0.648 |
| derna | flash | Europe/Med | 0.617 | 0.599 | −0.017 [−0.049, +0.014] | 0.585 | 0.619 | 0.633 | 0.525 | 0.591 | 0.607 |
| hai_phong | pluvial | SE Asia | 0.871 | 0.849 | −0.021 [−0.087, +0.026] | 0.835 | 0.377 | 0.596 | 0.630 | 0.418 | 0.161 |
| dubai_2024 | pluvial | Africa/W Asia | 0.497 | 0.474 | −0.023 [−0.076, +0.038] | 0.462 | 0.510 | 0.489 | 0.493 | 0.494 | 0.501 |
| assam_2026 | fluvial, waterlogging | S Asia | 0.750 | 0.721 | −0.028 [−0.122, +0.081] | 0.777 | 0.810 | 0.388 | 0.734 | 0.419 | 0.505 |
| beira | coastal | Africa/W Asia | 0.522 | 0.488 | −0.034 [−0.103, +0.034] | 0.500 | 0.601 | 0.466 | 0.445 | 0.583 | 0.511 |
| himachal_2023 | flash | S Asia | 0.534 | 0.485 | **−0.049 [−0.098, −0.007]** | 0.490 | 0.583 | 0.546 | 0.515 | 0.422 | 0.510 |
| fort_myers_beach | coastal | Americas | 0.658 | 0.553 | **−0.105 [−0.137, −0.058]** | 0.546 | 0.401 | 0.463 | 0.588 | 0.680 | 0.438 |
| bad_neuenahr | flash | Europe | 0.713 | 0.600 | **−0.113 [−0.218, −0.033]** | 0.517 | 0.671 | 0.692 | 0.607 | 0.696 | 0.710 |
| derna_2023 | flash | Europe/Med | 0.961 | 0.662 | **−0.298 [−0.418, −0.156]** | 0.251 | 0.700 | 0.977 | 0.595 | 0.829 | 0.833 |

**Chance level.** With 29 events, about 0.7 "clear" wins are expected by chance in each direction (2.5 % × 29; events are not fully independent). The 10 clear wins are well above that, and so are the 4 clear losses.

### 3.5 Sensitivity and ablations (LCO unless marked; all 29 events)

| run | mean AUC | Δ vs HAND [95% CI] | clear wins / losses |
|---|---|---|---|
| primary (full, FABDEM terrain) | 0.711 | +0.074 [+0.019, +0.133] | 10 / 4 |
| smaller model (7 leaves, 150 trees) | 0.696 | +0.059 [+0.002, +0.116] | 9 / 4 |
| larger model (31 leaves, 600 trees) | 0.706 | +0.069 [+0.013, +0.125] | 10 / 5 |
| DEM swap: GLO-30 for FABDEM | 0.695 | +0.058 [+0.008, +0.111] | 11 / 4 |
| **open:** GLO-30 + mapped-water HAND + HydroSHEDS, no FABDEM, no MERIT | 0.700 | +0.063 [+0.007, +0.116] | 13 / 4 |
| open, logistic regression | 0.680 | +0.043 [−0.023, +0.102] | 13 / 5 |
| no rain features | 0.713 | +0.076 [+0.020, +0.133] | 10 / 3 |
| pre-event water only (no post-event JRC years) | 0.716 | +0.079 [+0.026, +0.136] | 11 / 4 |
| HAND + fluvial score only (2 features) | 0.602 | **−0.035** [−0.074, −0.000] | 4 / 8 |
| **no land cover** (full minus WorldCover) | 0.644 | **+0.007** (CI pending) | pending |
| no land cover, LRO | 0.644 | +0.007 (CI pending) | pending |
| **terrain + hydrography + water only** | 0.631 | **−0.007** (CI pending) | pending |
| GEDTM30 terrain | not run | GEDTM30 unreadable (§1.3) | |

**Reading:**
- The result does not depend on the model size.
- It does not depend on rain data: removing rain changes nothing.
- It does not depend on post-event years in JRC.
- Removing FABDEM and MERIT entirely costs 0.011.
- **It depends entirely on land cover.**
- Pooling HAND and the fluvial score across events is *worse* than HAND alone. A tree learns absolute HAND cut-offs from other events, and those break the within-event ranking.

---

## 4. Calibration: a score, not a probability

Pooled held-out labelled cells, each event weighted equally; cluster bootstrap intervals; full reliability bins in `tables.md`.

| run | ECE | Brier skill vs constant | calibration intercept | calibration slope | per-event share ρ | call it |
|---|---|---|---|---|---|---|
| LGBM LCO | 0.082 [0.037, 0.144] | +0.044 [−0.103, +0.116] | +0.59 [−0.35, +1.34] | **0.59 [0.43, 0.88]** | +0.26 | **score** |
| LGBM LRO | 0.093 | +0.010 | +0.74 | 0.49 [0.34, 0.73] | +0.40 | score |
| LogReg LCO | 0.028 | +0.168 [−0.142, +0.304] | −0.06 | 0.65 [0.41, 0.87] | +0.53 | score |
| LogReg LRO | 0.080 | +0.021 | +0.12 | 0.44 [0.27, 0.64] | +0.32 | score |
| open LGBM LCO / LRO | 0.076 / 0.096 | +0.018 / −0.015 | | 0.50 / 0.42 | | score |

- **The rule, fixed before looking:** call it a probability only if it is *weakly calibrated* (Van Calster et al. 2016), meaning intercept 0 and slope 1 both lie inside their cluster-bootstrap 95% intervals.
- **No run passes.** Every slope is clearly below 1: high scores flood less often than they say. In the 0.5–0.9 bins of the LCO model, observed flood shares are 0.25–0.43 against predicted 0.55–0.83.
- **Brier skill is near zero.** The model ranks cells within an event, but it barely predicts how much of a box floods. That share is set by the reference and the box rule (centred on the flood, C72), not by the land. It runs from 1 % (Hai Phong) to 61 % (Volos).
- **Even recalibrated, a "probability" here would be conditional:** the chance a cell is mapped flooded *given that this event happened and the box was placed around its flood*. That is not an annual or per-event probability for an arbitrary AOI. The maps are therefore written as `flood_likelihood_score`.

---

## 5. Feature importance (LGBM full, LCO; held-out permutation within each event)

| rank | feature | AUC drop when permuted | events hurt | gain share |
|---|---|---|---|---|
| 1 | **WorldCover cropland** | **0.043** | 20 / 29 | **0.318** |
| 2 | NDVI (year before) | 0.014 | 19 | 0.030 |
| 3 | WorldCover built-up | 0.013 | 23 | 0.016 |
| 4 | height above 2 km minimum (FABDEM) | 0.013 | 19 | 0.094 |
| 5 | height above mapped water (FABDEM) | 0.013 | 24 | 0.040 |
| 6 | TPI 990 m | 0.009 | 20 | 0.017 |
| 7 | JRC recurrence | 0.009 | 16 | 0.030 |
| 8 | clay | 0.008 | 13 | 0.081 |
| 9 | fluvial score | 0.004 | 16 | 0.039 |
| … | MERIT HAND | −0.003 | 14 | 0.021 |
| | rain (3 features) | −0.002 to +0.001 | 4–7 | 0.165 together |

**By group (AUC drop):**

| group | AUC drop |
|---|---|
| land cover | 0.092 |
| FABDEM terrain | 0.043 |
| MERIT hydrography | 0.020 |
| NDVI | 0.014 |
| water history | 0.011 |
| clay | 0.007 |
| rain | −0.004 |

**Two cautions:**
1. **Rain takes 16.5 % of the gain but adds nothing held out.** CHIRPS and IMERG are one value per 5–11 km, so inside a box they act as event identifiers. The model uses them to separate events, not cells. MERIT HAND's permutation drop is ≈ 0 because the terrain windows and the mapped-water HAND carry the same information.
2. **Cropland: physics or reference?**
   - Its effect is largest where the gain over HAND is largest:
     - EMS events: mean drop 0.044, Δ vs HAND +0.128;
     - UNOSAT: 0.133, +0.082;
     - Sentinel-1 change maps: 0.024, −0.018.
   - So it is not simply SAR seeing water on fields.
   - Two readings fit the data:
     - **(a) physical:** farmed floodplains and paddies are low, flat and near rivers;
     - **(b) a reference effect:** flooded fields are easy to delineate while flooded streets are not (MM5), and standing paddy water counts as flood (F5/MM3).
   - **These 29 references cannot separate (a) from (b).** That matters most for the urban and pluvial use the brief cares about: a model that learned "fields flood, buildings don't" would be wrong in exactly that case.

---

## 6. What would most improve it

| lever | evidence here | expected value |
|---|---|---|
| **More events, chosen for diversity** | Learning curve (LCO, whole training clusters): 6.6 training events → Δ vs HAND +0.005; 12.8 → +0.060; 21.1 → +0.071; all (~27) → +0.074. It **flattens** for more of the same kinds of event. But LRO is about half of LCO, and arid, mountain and flash events fail. | **High, if the new events cover what fails:** arid and mountain flash floods, urban pluvial, more regions (Africa has 1 event, West Asia 1, mountains 1). Low if they repeat wet Asian floodplains. |
| **References that see urban water** | All of the gain rides on land cover (§3.5, §5). Pluvial boxes show no gain, and they are where SAR and EMS see least. | **Highest, for trust:** without them the land-cover signal cannot be confirmed. VHR/optical EMS urban products, item 21's traced tiles, or crowd and agency street-flood maps. |
| **Better terrain** | FABDEM → GLO-30: −0.016. Open stack: −0.011. GEDTM30 not tested (server). | **Moderate.** Mostly a licence question (§7), not a skill one. LiDAR at a few sites would measure the DEM error (flood_core B3). |
| **More rain data** | Rain features contribute nothing within a box (−0.004 permuted, +0.002 when removed). | **Low for within-event mapping.** Event rainfall could matter for predicting *whether* and *how much* a box floods (the calibration gap), which needs a different target. |
| **Calibration** | Slope 0.4–0.65, near-zero Brier skill. | Needs a target that is not box-conditioned (e.g. full-AOI references with unobserved cells kept as unobserved). Then isotonic recalibration inside the CV. |

---

## 7. Licences of every input (per the cited source pages; *assumed* = not re-checked this session)

| source | used for | licence | commercial use |
|---|---|---|---|
| **FABDEM** | primary terrain | CC BY-NC-SA 4.0 (audit §5) | **no**; derived maps inherit SA |
| **MERIT Hydro** | HAND, upa, fluvial score | CC BY-NC 4.0 **or** ODbL 1.0 (dual; audit §5) | only under ODbL (share-alike) |
| Copernicus DEM GLO-30 2024_1 | open-model terrain | Copernicus WorldDEM-30 licence: free, worldwide, unlimited in time; attribution "© DLR e.V." / "Produced using Copernicus WorldDEM-30 © DLR e.V." ([licence](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf), [EE](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30_2024_1)) | no purpose restriction found; the summary did not state commercial use explicitly, so **confirm in the full text** |
| GEDTM30 v1.2 | (not readable) | CC BY 4.0 per data.gov and OpenGeoHub ([data.gov](https://catalog.data.gov/dataset/global-ensemble-digital-terrain-model), [PeerJ](https://peerj.com/articles/19673)); Zenodo field not confirmed | yes if CC BY holds |
| HydroSHEDS v1 (15ACC) | open-model accumulation | "free for non-commercial and commercial use", restrictions in TechDoc App. A ([TechDoc v1.4](https://data.hydrosheds.org/file/technical-documentation/HydroSHEDS_TechDoc_v1_4.pdf), [terms](https://hydrosheds.org/terms-of-use)); one catalogue record says CC BY-NC 3.0 ([Stanford](https://purl.stanford.edu/zc665xv7392)) | **conflicting; confirm** |
| JRC GSW 1.4 | occurrence, recurrence, permanent water | Copernicus free; "Source: EC JRC/Google" (audit §5) | yes |
| OSM | water mask, distance | ODbL | yes, share-alike for derived DBs |
| CHIRPS v2 | rain | public domain / CC0 per the EE and NOAA listings ([EE](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY), [data.gov](https://catalog.data.gov/dataset/chirps-version-2-0-precipitation-global-0-05a-daily-1981-present)) | yes |
| IMERG V07 | rain | NASA open data (*assumed*) | yes |
| SoilGrids | clay | CC BY 4.0 (*assumed*) | yes |
| ESA WorldCover 2020/2021 | land cover | CC BY 4.0 (*assumed*) | yes |
| Sentinel-2 L1C + Cloud Score+ | NDVI | Copernicus open; Cloud Score+ CC BY 4.0 (*assumed*) | yes |
| GHSL GHS-SMOD, ERA5-Land, sat-io shoreline | setting tags only | CC BY 4.0 / Copernicus licence / per catalogue (*assumed*) | tags only |
| Copernicus EMS, UNOSAT, S1 references | labels | CEMS terms (information purposes); UNOSAT varies by product, unrecorded for FL20220808PAK and FL20220525BGD (audit §5, Q5) | validation only |

**Licence-clean model.** The `open` variant (GLO-30, mapped-water HAND, HydroSHEDS, JRC, OSM, CHIRPS, IMERG, SoilGrids, WorldCover, S2) keeps 85 % of the primary model's gain over HAND (+0.063 vs +0.074 LCO; +0.036 vs +0.035 LRO). If GeoWatch has any commercial use (audit Q2), it is the one to build on, once the GLO-30 and HydroSHEDS terms are confirmed.

---

## 8. Before expanding: what I propose, and what is yours to decide

**Proposed batch 1** (metadata screen first, then about 10 events at a time, each through the same fetch → features → model → evaluate loop; the code takes any registry dev unit with a cached reference):
1. **Urban and peri-urban pluvial events with VHR or optical EMS delineations**, so a reference can see water among buildings. Global South first.
2. **Arid and mountain flash floods with EMS products after 2018**: Libya, Oman, Yemen, Pakistan, Afghanistan, northern India, the Andes and East Africa. Today these are where the model fails.
3. **Sentinel-1 extents only where no EMS product exists.** GFD is used only to find candidate events: it is 250 m and ends in 2018.
4. **Each new event costs:**
   - about 5–12 min of baseline inputs (the pluvial step can take an hour and is only needed for the pluvial comparator);
   - about 20 s here;
   - a few MB of disk.
   - About 100 events fit in one or two overnight runs.

**Decisions I need:**
1. **A held-out test set.** All 29 events are burned (audit L1). I recommend reserving a share of the new events, about one in three and chosen by rule before any is scored, as **reserved** in the registry, and scoring them once at the end. Without that, every number in this report stays a development number.
2. **Should the registry take new units?** Adding them means editing `experiments/flood_core/registry/events.json`. That is experiment-side, not production, but it changes the gate every flood experiment uses, so I did not touch it.
3. **Commercial intent** (audit Q2): it decides between the FABDEM/MERIT model and the open model.
4. **The land-cover question:** keep WorldCover as a feature for batch 1 (and test it on urban references), or drop it now and accept a model that is level with HAND (+0.007).

---

## 9. Deviations, assumptions and every number I chose

- **LightGBM installation.** LightGBM is not in `geowatch-env`. It was installed with `pip --target` into `~/.cache/geowatch/flood_learned/pylib`, outside the repo and the env, and relinked (`install_name_tool -add_rpath @loader_path`) to the `libomp.dylib` that scikit-learn's wheel ships. It is used through `PYTHONPATH`. No Homebrew package was installed and `geowatch-env` was not changed.
- **GEDTM30 could not be read** (server fault, §1.3). The DEM comparison is FABDEM vs GLO-30 only.
- **Two ablations were added after the first look at importance:** `no_landcover` and `terrain_water`. They are labelled as post hoc in `model.py` and are reported, never used to pick a model.
- **Thresholds and settings, each with its basis:**

| value | where | basis |
|---|---|---|
| 80 % JRC occurrence = permanent water | labels, water mask | existing `JRC_PERMANENT_WATER_OCCURRENCE_PCT` |
| 67-cell (2 km) margin | fetch, `relmin2km`, mapped-water HAND | flood_baselines `DIST_MARGIN_M` (half the box side) |
| 33-cell (990 m) window and block | `tpi990`, bootstrap, `min_child_samples` = 33² | flood_baselines' measured correlation range (A2) |
| 3 × 3 curvature | `curv_*` | native-resolution Laplacian (Zevenbergen & Thorne 1987) |
| cs_cdf ≥ 0.60 | NDVI cloud mask | Cloud Score+ example code; catalogue range 0.50–0.65 |
| calendar year before the event | NDVI; WorldCover year choice | the project's water-history rule (years before `ref_year`) |
| 10 equal-width reliability bins | calibration | Niculescu-Mizil & Caruana (2005) |
| 2,000 logit bins | calibration aggregation | computational only; a test checks it matches the cell-level fit |
| intercept 0 and slope 1 inside the 95% CI → "probability" | naming | weak calibration, Van Calster et al. (2016) |
| LGBM 15 leaves / 0.05 / 300 / 0.7 / 0.8 / L2 1 | model | LightGBM's over-fitting guidance; fixed, not tuned |
| LR C = 1 | model | scikit-learn default |
| setting tags | groups | GHS-SMOD L2 classes; Kapos et al. (2000); Köppen B per Peel et al. (2007); LECZ 10 m + existing `COASTAL_APPLICABILITY_THRESHOLD_KM` (10 km); Tessler et al. (2015) deltas; UN M49 regions |
| learning-curve shares 0.25 / 0.5 / 0.75 × 3 repeats | §6 | quartiles of the training clusters; 3 repeats for a mean |

- **WorldCover for 2017–2019 events is a later map** (2020). Built-up and cropland change slowly, but this is post-event information for 3 events.
- **No model output reached the product.** The 29-event model file and the GeoTIFFs are in the cache (§10), not in `susceptibility/`.

---

## 10. Outputs and reproduce

- `results/learned.json`: everything above.
- `results/tables.md`: every run × group, per event, reliability bins, setting tags.
- `results/figures/maps.png`: reference vs held-out map vs HAND for six events.
- Cache, not committed: `~/.cache/geowatch/flood_learned/`:
  - `inputs/` (fetched layers, ~60 MB);
  - `tables/`;
  - `preds/` (held-out predictions per run);
  - `maps/<event>__lco_full_lgbm.tif` (held-out per-pixel maps, band `flood_likelihood_score`);
  - `maps/model_full_29.txt` (LightGBM fitted on all 29).

```sh
# from the repo root; GEE_PROJECT_ID in the environment (fetch only)
LIB=~/.cache/geowatch/flood_learned/pylib
~/geowatch/geowatch-env/bin/python -m pip install --target $LIB --no-deps lightgbm
cp "$(~/geowatch/geowatch-env/bin/python -c 'import sklearn,os;print(os.path.dirname(sklearn.__file__))')/.dylibs/libomp.dylib" $LIB/lightgbm/lib/
install_name_tool -add_rpath @loader_path $LIB/lightgbm/lib/lib_lightgbm.dylib
codesign -f -s - $LIB/lightgbm/lib/lib_lightgbm.dylib $LIB/lightgbm/lib/libomp.dylib
PYTHONPATH=$LIB caffeinate -i sh experiments/flood_learned/run_all.sh
PYTHONPATH=$LIB ~/geowatch/geowatch-env/bin/python -m pytest -q experiments/flood_learned/test_learned.py
```
Every step skips what it has cached. On this Mac a full run takes about 12 min for the fetch, 10 min for the models and 35 min for the evaluation.
