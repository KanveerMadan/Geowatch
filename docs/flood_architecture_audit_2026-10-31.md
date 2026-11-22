# GeoWatch flood architecture: feasibility audit (read-only)

**Date:** 2026-10-31. **Audited:** `master` @ `87f52cb` plus `build/flood4b` @ `bccf61d` (worktree `~/gw-flood4b`, which is master plus the round-4b pre-registration and harness).
**Nothing was changed.** No repo file was edited, no method or label changed, nothing merged, no flood score computed, and round 4b was not run. Earth Engine was queried for **asset metadata only** (no pixels). The dirty `item-21-phase-a` tree was not touched.

**Scope note.** No document in the repo is titled or described as a "flood redesign proposal". This audit therefore covers (a) every flood component built in code, and (b) everything planned in the docs: the M1–M11 taxonomy (`docs/flood_taxonomy.md`), rounds 4b, 5 and 6, `event_hazard`, and the risk/vulnerability gate (`risk/compute.py`).

---

## 1. The architecture as built

| Module | Method in the pipeline now | Spatial? | Inputs | Tested | Label |
|---|---|---|---|---|---|
| M1 fluvial | `low_hand` + `river_size`, weights 1:1 | 30 m map | MERIT Hydro `hnd`, `upa` focal max 1 km | R2 passed 0.858 (Hanoi, Kolonnawa); R4 failed 0.537 (Bihar, Assam, Sindh) | experimental + scope note (C78) |
| M2 pluvial | bluespot fill-and-spill | 30 m map | FABDEM, Open Buildings/OSM impervious stand-in (`placeholder`), CHIRPS design day | R1 failed, R3 0.613, R4 0.524 | failed |
| M3 waterlogging | **persistence only** (R4B weights) | 30 m map | JRC GSW monthly (≤2021), S1 VV < −18 dB (3 yrs before) | R4 failed 0.613 *on the 4-component method*; persistence-only is **untested** (4b registered, not run) | failed |
| M4 flash flood | valley × stream power | 30 m map | MERIT `hnd`/`upa`, FABDEM relief, IMERG p99.9 | R4 failed 0.640 | failed |
| M5 coastal | distance-to-coast + mean FABDEM elevation | **AOI-wide scalar** | sat-io shoreline, FABDEM | R2 failed, pooled 0.646 over 4 sites | failed |
| M6–M9 | not built | — | — | — | placeholder / `not_computed` |
| M10 groundwater / M11 tsunami | not measurable / out of scope | — | — | — | `not_computed` / `not_applicable` |
| `event_hazard` | susceptibility × rainfall factor | scalar | IMERG | never tested | **not wired** into `analysis/`, `api.py`, `pipeline.py` or `zonal/` (grep) |
| risk | hazard × exposure × vulnerability | — | — | — | vulnerability `not_calculated` by a hard gate (`risk/compute.py`) |

Validation rule for every round: within-event ROC AUC on 30 m cells; a 4 km box centred on the reference's flood centroid; ≥ 50 flooded and ≥ 50 dry cells per event; mean ≥ 0.70 over ≥ 2 qualifying test events. The verdict is pinned by sha256 in `analysis/contract.py`. The label precedence is worst-of (`retired > failed > placeholder > experimental > validated`). **No output in the project is `validated` today.**

---

## 2. Verified facts (checked in code, results files or live metadata this session)

- **F1.** Five rounds have run (1, 2, 3, 4, plus 4b registered). Every built mechanism has failed at least once, and fluvial is the only one that ever passed (R2). Per-event AUCs within one module range widely: waterlogging R4 0.406–0.766, fluvial R4 0.388–0.643.
- **F2.** **No harness computes a comparator baseline.** There is no HAND-only, JRC-occurrence, distance-to-water or published-hazard-map baseline. The bar is absolute (≥ 0.70); a grep for baseline/null/comparator in `harness_round4.py` finds nothing.
- **F3.** **References are mechanism-agnostic.** EMS `observedEventA`, UNOSAT `FloodExtent` and the S1 VV drop map water, not its cause. The same reference box scores two mechanisms: Assam for M1 and M3, Valencia EMSR773 AOI03 for M2 and M4. Typhoon Yagi (EMSR754) supplied pluvial (Hai Phong), fluvial (Hanoi) and waterlogging (Thai Binh, Nam Dinh) events.
- **F4.** **Cross-round event reuse** (disclosed in `PREREGISTRATION_ROUND4.md` §"Events with history"). Valencia AOI03 and Derna were round-2 *tuning* events and became round-4 *test* events. Round 4's tuning events are the held-out events of rounds 2 and 3. Every event from rounds 1–4 has now been seen by the developer.
- **F5.** **Only permanent water is masked.** Every reference excludes JRC occurrence ≥ 80 % and nothing else (`references.not_permanent`). The round-4 S1 baseline is January–March of the event year, so transplanted paddy and seasonal backwater count as "flood". The pre-registration states this cost.
- **F6.** Components that are constant across a 4 km box cannot move a within-event AUC: IMERG I30 (one value per 0.1°, flash flood), the CHIRPS design storm (pluvial; it only changes which hollows overflow) and coastal's whole score. Coastal's "failed" verdict comes from **pooling 4 site-level scalars**, so it ranks four numbers. That is not a test of the spatial method, and a scalar cannot be tested under the per-event rule at all.
- **F7.** Water-history inputs read only years before `ref_year` (`hydro_rasters.water_history_years`). The JRC *occurrence* mask covers 1984–2021, so for the 2018 event it includes post-event years. This affects masking only, not scores.
- **F8.** The persistence input (S1 VV < −18 dB) and several references (S1 drop for Bihar, Assam, Kerala, Dubai and Himachal; UNOSAT Noakhali, an S1 ML product; EMS Calais, S1) use **the same sensor**.
- **F9.** The pipeline runs waterlogging with `WATERLOGGING_R4B_WEIGHTS` (persistence only), while its `failed` label comes from round 4's 4-component method, and its `METHOD` string still names all four components. The label is conservative, but it describes a different configuration from the one that runs.
- **F10.** The UI shows tiers, maps and ward rankings for failed modules on purpose, styled as failed and captioned "not for decisions" (`web/src/lib/flood.js:7,81–99`). The tiers are fixed 0.2-wide breaks on an uncalibrated 0–1 score. AUC tests ranking only, so tiers, absolute values and ward-scale rankings have never been validated.
- **F11.** Earth Engine access works for every input and reference in use: MERIT Hydro v1_0_1, FABDEM, GLO30, CHIRPS daily, IMERG V07, SoilGrids clay, JRC GSW1_4 Monthly/GlobalSurfaceWater, S1_GRD, GFD, Open Buildings v3 (`ee.data.getAsset`, this session).
- **F12.** GSW1_4 ends 2021-12 (end 2022-01-01). `JRC/GSW1_5` is **not** in EE. GFD's events end 2018-12, so it cannot serve any post-2018 event.
- **F13.** Candidate assets **present** in EE: `JRC/CEMS_GLOFAS/FloodHazard/v2_1` (264 tiles; RP10–RP500 depth bands, `permanent_water_class`) and `WRI/Aqueduct_Flood_Hazard_Maps/V2` (648 images; `inuncoast` and `inunriver`, return periods 2–1000). The code comment "GloFAS is not a GEE asset" is right for discharge, but GloFAS *hazard maps* are in EE.
- **F14.** These guessed paths were **not found**: sat-io GSSR, IBTrACS, FathomDEM, hydrography90m, GFM. Only those paths were checked, so the datasets may exist under other IDs.

## 3. Target and reference mismatches

| # | Mismatch | Effect |
|---|---|---|
| MM1 | **Mechanism.** The modules claim one mechanism each; the references show water from any cause (F3) | A pass cannot show that a module discriminates *its* mechanism. Five maps may be one "inundation propensity" map under five names. The R3 waterlogging AUCs on Yagi (0.277, 0.442) beside fluvial's Hanoi 0.916 look like this |
| MM2 | **Susceptibility vs one snapshot.** The product claims long-run propensity; the reference is one event at one image time (Dubai +8 d, Kerala +5 d, Calais +17 d) | "Dry" cells in one event may be flood-prone. Even a perfect susceptibility map has an AUC ceiling below 1, and the 0.70 bar is not tied to that ceiling |
| MM3 | **Seasonal water as flood** (F5) | Persistence and low-HAND get credit for predicting *normal* wet-season water. For 4b, Redon (marsh) and Calais (polder) are places that are wet by definition, which the pre-registration itself calls circular |
| MM4 | **AOI-constant forcing** (F6) | The rainfall components and coastal cannot be tested by the rule, so a new M5 must be per-pixel to be testable |
| MM5 | **Sensor blindness where the mechanism lives.** SAR misses water among buildings, and GFD is 250 m | Pluvial (urban ponding) has never had a pluvial test event (C79), and SAR references undercount exactly there |
| MM6 | **Output scale.** Validation is on 30 m cells in a 4 km box; the product serves tiers and ward rankings (F10) | Ward-level claims are an untested cross-scale extrapolation |

## 4. Leakage and validity risks

| # | Risk | Severity | Status |
|---|---|---|---|
| L1 | Cross-round reuse of seen events (F4) | medium | disclosed, but the R1–R4 pool is now **burned** for testing |
| L2 | **Forking paths.** Methods redesigned after each failure, some choices from post-hoc component AUCs on test events (C80 led to 4b) | high in aggregate | each round is registered; the sequence is not corrected for multiplicity |
| L3 | **Selection on mechanism.** The 4b events were chosen *because* they are standing-water places | medium | not label leakage, but optimistic for a persistence score |
| L4 | **Shared sensor** between input and reference (F8): smooth surfaces and radar shadow read as water in both | medium (4b: 2 of 3 events) | the pre-registration notes S1 smooth-surface error, not input/reference coupling |
| L5 | **Reference-conditioned box** (C72): centred on the flood, so prevalence is high and the box can drift into another mechanism | low–medium | known |
| L6 | **Small n.** 2–3 events per verdict with no confidence interval; fluvial passed on 2 and failed on 3 | high | none |
| L7 | **No baseline** (F2): a module can pass and still add nothing over HAND or JRC occurrence | high | none |
| L8 | Temporal: occurrence mask includes post-event years (F7); Open Buildings v3 postdates 2018 events | low | — |

## 5. Data access and licensing

The licence entries are from web sources found this session, except where marked *assumed*.

| Dataset | Role | Access | Licence | Implication |
|---|---|---|---|---|
| FABDEM | pluvial DEM, flash relief, coastal elevation | EE ✓ | **CC BY-NC-SA 4.0**; commercial use via Fathom ([GEE community catalog](https://gee-community-catalog.org/projects/fabdem/), [Fathom](https://www.fathom.global/academic-licenses/)) | non-commercial and share-alike. **A blocker if GeoWatch has any commercial use**, and derived maps inherit SA |
| MERIT Hydro v1.0.1 | HAND and upa in M1, M3, M4 | EE ✓ | **CC BY-NC 4.0 or ODbL 1.0** (dual) ([U-Tokyo](https://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_Hydro), [EE catalog](https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1)) | commercial use requires ODbL, so derived hazard maps must be published under ODbL |
| JRC GSW 1.4 | persistence input, permanent-water mask | EE ✓ | Copernicus, free; "Source: EC JRC/Google" ([EE](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_Metadata)) | ends 2021, so recent years come from S1 only |
| Sentinel-1 GRD | input and reference | EE ✓ | Copernicus open (*assumed*, standard) | shared-sensor issue (L4) |
| Copernicus EMS | main reference | public API ✓ (repo: public from EMSR656 on) | free under the CEMS terms, information purposes only ([terms](https://mapping.emergency.copernicus.eu/terms-and-conditions/)) | fine for validation, with attribution |
| UNOSAT (Sindh, Sylhet, Noakhali) | reference | downloaded ✓ | **varies by product**: CC BY-SA and CC BY-NC-SA both seen ([HDX/UNOSAT examples](https://geo.btaa.org/catalog/587faab1-d1ea-485c-811a-a5508bdaa1ae), [UNOSAT map](https://www.themimu.info/sites/themimu.info/files/documents/Hazard_Map_Flood_waters_over_Kyautaw_Area_Rakine_UNOSAT_19Aug2015.pdf)) | **unrecorded** for the three products used |
| GFD v1 | R2 reference | EE ✓ | **CC BY-NC 4.0** ([EE](https://developers.google.com/earth-engine/datasets/catalog/GLOBAL_FLOOD_DB_MODIS_EVENTS_V1)) | ends 2018 (F12) |
| CHIRPS, IMERG V07, SoilGrids, Open Buildings v3, OSM | inputs | EE ✓ / Overpass | open, CC BY 4.0 or ODbL (*assumed*, not checked this session) | OSM/Open Buildings ODbL share-alike applies to derived DBs |
| **Candidate:** GloFAS flood hazard v2.1 | fluvial baseline / comparator | EE ✓ (F13) | CEMS-FLOODS licence, free with conditions ([EWDS](https://ewds.climate.copernicus.eu/licences/cems-floods)); v2.1's own EE terms not confirmed | usable as a **comparator**; it is a model, so not a reference |
| **Candidate:** Aqueduct Floods V2 | riverine and coastal baseline | EE ✓ (F13) | free, attribution to WRI ([EE](https://developers.google.com/earth-engine/datasets/catalog/WRI_Aqueduct_Flood_Hazard_Maps_V2)); CC BY 4.0 per [UN-SPIDER](https://un-spider.org/links-and-resources/data-sources/aqueduct-global-flood-risk-maps-0), not confirmed on WRI's page | the only per-pixel **coastal** prior found in EE (~1 km) |
| **Candidate:** Copernicus GFM | S1 flood extents, global, 2015– | REST/STAC API ([GFM PDD](https://extwiki.eodc.eu/GFM/PDD/Introduction)); not in EE | "free and open" per 2021 slides; data licence **not found** | a large reference pool, but it is S1, so it worsens L4 |
| **Candidate:** Kuro Siwo | SAR flood labels, 43 events 2015–2022 | HF/GitHub | **CC BY** ([HF](https://huggingface.co/datasets/orion-ai-lab/Kuro-Siwo-Webdataset)) | dev-set reference; SAR |
| Maxar Open Data | (item 21 VHR) | — | CC BY-NC 4.0 (repo `08_STATE.md`) | non-commercial |

## 6. Assumptions (not verified)

- **A1.** GeoWatch is non-commercial research. This decides whether FABDEM, MERIT (NC), GFD and Maxar are usable.
- **A2.** "Flood susceptibility" means a long-run per-cell ranking, not an event forecast or an observed extent.
- **A3.** The licences for CHIRPS, IMERG, SoilGrids, Open Buildings and S1 are the standard open ones.
- **A4.** EMS delineations exclude normal water. UNOSAT says so ("already removes reference water"); for EMS this is not checked per product.

## 7. Unresolved questions (yours to decide)

1. **Is there a written redesign proposal** outside the repo? If so, this audit should be re-run against it.
2. **Commercial intent?** (A1) It decides whether the DEM and hydrography stack has to be replaced.
3. **Is per-mechanism attribution (five maps) a product requirement,** or would one validated inundation-propensity layer plus mechanism context do? MM1 means the current references cannot validate the five-way split.
4. **Round 4b:** run as registered; add pre-registered baselines and a seasonal-water diagnostic first, as a committed amendment before any score; or hold? Editing the committed file is not an option.
5. **The UNOSAT licences** of FL20220808PAK, FL20220525BGD and FL20240825BGD.
6. **Do ward rankings need validation at ward scale,** or are they explicitly descriptive?

## 8. Bounded development experiments (dev events only, no held-out evaluation)

**Ground rule.** Every R1–R4 event (about 30) is declared a permanent **development** event. The 4b events and any future candidates stay **unseen**. None of these experiments computes a score on them.

| # | Question | Procedure | Success | Stop |
|---|---|---|---|---|
| **E0** | Can test events be kept clean? | Write a hashed registry: dev = R1–R4 events; reserved = 4b plus future candidates, with only metadata recorded. A harness refuses reserved names outside a registered run (4b's harness already refuses earlier names) | registry committed, and a test enforces it | — (prerequisite) |
| **E1** | Do the modules beat trivial baselines? | On dev events, within-event AUC for HAND-only, JRC occurrence, distance to JRC/OSM water, box-relative elevation, GloFAS RP100 depth, and Aqueduct riverine RP100, beside each module. Per-event bootstrap CI | a module beats the **best** baseline by ≥ 0.05 mean AUC on ≥ ⅔ of its mechanism's dev events | if no module beats HAND-only or JRC occurrence, **stop** method work on that mechanism |
| **E2** | How much AUC is normal seasonal water? | Re-score dev events with a stricter normal-water mask (JRC occurrence ≥ 5 %, or Q1 S1 water) as a sensitivity only, with the reference rules unchanged | report the ΔAUC per module | if persistence falls below 0.60 with seasonal water removed, it predicts seasonality, not waterlogging. Do not adopt it as M3 |
| **E3** | Are the mechanisms distinguishable? | A module × event AUC matrix on dev events grouped by documented mechanism | diagonal: own-mechanism AUC exceeds the other modules' by ≥ 0.05 | no diagonal structure, so the 5-way taxonomy is unsupportable with these references (Q3) |
| **E4** | What is the reference noise ceiling and power? | Where two references exist for one event (Derna S1 vs EMS GRA; Valencia EMS vs S1), AUC of one against the other, and the n needed for a CI half-width ≤ 0.05 | a ceiling and an n per module, used to set the next bar | inter-reference AUC < 0.80 means the 0.70 bar is near the noise floor. Re-examine the bar before any new round |
| **E5** | Is per-pixel coastal testable? | Metadata only: count post-2023 public EMS coastal activations meeting ≥ 50/50 under the box rule, and check Aqueduct `inuncoast` coverage | ≥ 4 candidate events | < 4: M5 stays failed, nothing built |
| **E6** | Can pluvial be tested at all (C79)? | Metadata only: count urban ponding events with optical/VHR delineations | ≥ 3 events | < 3: pluvial stays untested until item 21 **and** a reference exists |

Budget: E0 and E5–E6 are about a day without heavy compute. E1–E4 reuse the cached dev-event inputs and boxes, with no new references.

## 9. Recommendation: the smallest defensible first scope

**Build evaluation infrastructure, not new hazard methods.** Concretely:

1. **E0** registry plus guard test.
2. **A comparator-baseline harness (E1) and a mechanism matrix (E3)**, scoped to **M1 fluvial and M3 waterlogging only**. They have the most dev events, share MERIT HAND, and are where seasonal water (MM3) and mechanism confusion (MM1) bite hardest. Report per-event AUCs with bootstrap CIs.
3. **A proposed amended bar for future rounds**, written but not applied: beat the best trivial baseline by a margin **and** reach ≥ 0.70, with **≥ 3** qualifying events, the seasonal-water sensitivity reported, and a sensor-independent reference for at least one event.

**Explicitly out of the first scope:** new methods for M2 (blocked on item 21 and C79), M4, M5, M6–M9, `event_hazard` (dormant and scalar), risk/vulnerability (gated), any label or UI change, and running 4b. 4b is yours to decide (Q4).

**Why this is the smallest defensible scope.** Every recent round failed or passed against an absolute bar with 2–3 events, no baseline, and references that cannot see mechanism. Another method round under the same rules cannot produce a trustworthy `validated`, and a pass would still be uninterpretable (L6, L7, MM1). The first increment that changes what can be claimed is the ability to say "better than HAND", "better than past water" and "specific to its mechanism", measured on events that are already burned.
