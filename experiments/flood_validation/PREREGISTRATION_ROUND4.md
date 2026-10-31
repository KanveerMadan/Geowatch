# Flood validation round 4 — pre-registration (M1–M4)

**Written 2026-10-30, and committed before any round-4 box, cell count,
module input or score was computed, and before the three new methods were
built.** Its SHA256 is recorded in the round-4 result file. Rounds 1–3 and
their result files are unchanged, and they stay the record of those rounds.
The flood taxonomy (M1–M11) is `docs/flood_taxonomy.md`.

**Modules:** M1 fluvial (method unchanged), and new methods for M2 pluvial,
M3 waterlogging and M4 flash flood. Coastal (M5) is not in this round.

## What was looked at before this was written, and nothing else

- **Event facts**, from news and agency reports (dates, places, rivers).
  Bihar: by 11–23 Sep 2026 the Kosi was above danger at Baltara and Kursela
  and the Ganga at Kahalgaon, with about 49 lakh people affected in 15
  districts. Assam: a cloudburst in Mon, Nagaland on 19 Jul 2026 flooded
  upper Assam. The Dikhow at Sivasagar was 1.86 m above danger on 24 Jul and
  falling. Sivasagar/Nazira, Charaideo, Jorhat and Golaghat were worst hit.
- **Reference availability only.** The Copernicus EMS public activation
  list (EMSR656 onward; older activations, e.g. Pakistan 2022's EMSR629,
  need a login). HDX listings of UNOSAT products, and the attribute tables,
  sensor dates and analysis-extent areas of the two UNOSAT products used.
  The EMS product list and layer names of EMSR773 and EMSR696, and the
  notation counts of EMSR696 AOI01's `observedEventA` layer (7 `Flooded
  area`, 19 `Flood trace`). Sentinel-1 IW VV acquisition dates and relative
  orbits at one point per S1 event, from 30 days before to 21 days after.
- **Input availability.** SoilGrids clay band names, and that its value is
  null at one point in Sylhet. The date ranges of JRC GSW monthly history
  and CHIRPS daily.
- **Round 3's result file**, for its tuning-event box centres. It also holds
  the round-3 AUCs of the retired methods on those events, which are
  irrelevant to the new methods.

No round-4 box, centroid, flooded cell, module input value or score was
computed.

## The bar (unchanged from rounds 2 and 3)

- **Metric:** ROC AUC of the module score, flooded vs dry 30 m cells, ties
  count one half (`harness.auc`), **within each event**.
- **Qualifying event:** ≥ 50 flooded **and** ≥ 50 dry valid cells in its box.
  Otherwise the event is **not-run** and is named.
- **Verdict:** the **unweighted mean of per-event AUCs over qualifying test
  events**. **≥ 0.70 → validated; < 0.70 → failed.** Fewer than **2
  qualifying test events → not-run**.
- **Valid cell:** inside the 4 km box and the reference extent, not JRC
  permanent water (occurrence ≥ 80 %), finite score.
- **Diagnostics only, no verdict:** pooled AUC over all qualifying test
  cells, per module.
- Each module is run **once** on its test events. No second attempt in this
  phase.

## The box rule (round 3's, unchanged)

For each event, using **only the reference** (no score, no module input):

1. **Flood extent F** = the reference's flooded area inside its extent.
2. **Centre** = the area-weighted centroid of F, computed in the UTM zone of
   F's lon/lat centroid. If that point is not in F, the centre is **the
   nearest point of F**.
3. **Box** = a **4 km × 4 km** square centred there (`square_bbox`).
4. No box is moved, resized or replaced after any count or score is seen.
   An event whose reference has no flooded area is not-run and is named.

The **reference extent** is the product's extent (EMS `extent`, UNOSAT
`AnalysisExtent`). For a Sentinel-1 reference there is no product, so the
extent is a pre-registered **20 km × 20 km search square** centred on the
named place in the events table. That is about one EMS AOI. F is the S1
flooded 30 m cells in the square, excluding JRC permanent water.

## References

| Kind | Flooded | Valid (before box and permanent water) |
|---|---|---|
| **Copernicus EMS** (DEL, or GRA where no DEL exists) | `observedEventA` `Flooded area` ∪ `Flood trace` covering ≥ half the cell (rasterised at 3 m) | ≥ half the cell in the product extent |
| **UNOSAT** (official UN satellite analysis) | `FloodExtent` polygons (`Water_Clas` = `Flood Water`; UNOSAT already removes reference water) covering ≥ half the cell | ≥ half the cell in `AnalysisExtent` |
| **Sentinel-1** (where neither exists) | ≥ half of the cell's 10 m pixels have VV(event) − VV(baseline) ≤ −3 dB | finite S1 value |

**Sentinel-1 method, stated:** `COPERNICUS/S1_GRD`, IW, VV. The event image
is the **earliest acquisition date in the 13 days from the event date**
(day 0 to day 12, the single-satellite repeat; round 2's coastal window).
The **baseline** is the median of the **same relative orbit(s)** over **1
January to 31 March of the event year**, the dry season at every S1 event
here. It is *not* round 2's 30 days before the event. In a monsoon
floodplain (Bihar, Assam, Kerala) those 30 days are already flooded, and
cells flooded both before and during would read dry. Stated cost: any water
present at the event and absent in Q1 counts as flood. That includes
transplanted paddy, and in Kerala the backwaters' seasonal rise.

## Events

### Test events (never used for tuning or method choice)

| Module | Event | Event date | Reference | S1 search-square centre | Note |
|---|---|---|---|---|---|
| M1 fluvial | **bihar_2026** (Kosi/Ganga) | 2026-09-11 | Sentinel-1 (first image +1 d, 2026-09-12, orbit 121) | Kursela, Katihar (25.45 N, 87.25 E): the Kosi gauge at the Kosi–Ganga confluence | no EMS or UNOSAT product |
| M1 fluvial | **assam_2026** (Dikhow) | 2026-07-20 | Sentinel-1 (+2 d, 2026-07-22, orbit 70) | Nazira, Sivasagar (26.917 N, 94.733 E) | no EMS or UNOSAT product |
| M1 fluvial | **pakistan_2022** (Sindh) | 2022-08-31 | UNOSAT FL20220808PAK, Sentinel-2 2022-08-31, Sindh (`S2_20220831_FloodExtent_Sindh`, `..._AnalysisExtent_Sindh`, 25,520 km²) | — | EMSR629 not public |
| M2 pluvial | **chennai_2023** (Cyclone Michaung) | 2023-12-04 | **none usable** | — | **not-run, named:** no S1 image from day 0 to +21 (next after 2023-11-30 is later), no EMS or UNOSAT product. NRSC's RISAT-1A map of 7 Dec 2023 exists only as a PDF |
| M2 pluvial | **dubai_2024** | 2024-04-16 | Sentinel-1 (+8 d, 2024-04-24, orbit 130; the 2024-04-15 pass is the day before the rain) | Dubai (25.2048 N, 55.2708 E) | |
| M2 pluvial | **valencia_2024** (DANA) | 2024-10-29 | EMS EMSR773 AOI03 Horta Sud, DEL monitoring 0 (WorldView-2, GeoEye-1, 2024-10-31) | — | same box as M4 |
| M3 waterlogging | **assam_2026** | 2026-07-20 | as M1 | as M1 | same box as M1 |
| M3 waterlogging | **sylhet_2022** | 2022-06-18 | UNOSAT FL20220525BGD, RCM-1 2022-06-18, Sylhet and Sunamganj (`RCM1_20220618_FloodExtent_Sylhet`, `..._AnalysisExtent_Sylhet`, 1,325 km²) | — | |
| M3 waterlogging | **kerala_2018** (Kuttanad) | 2018-08-16 | Sentinel-1 (+5 d, 2018-08-21, orbits 165 and 173) | Mankombu, Kuttanad (9.417 N, 76.433 E): the below-sea-level backwater district | |
| M4 flash flood | **valencia_2024** | 2024-10-29 | as M2 | — | |
| M4 flash flood | **himachal_2023** (Beas) | 2023-07-10 | Sentinel-1 (+1 d, 2023-07-11, orbit 129) | Kullu (31.958 N, 77.110 E) on the Beas | |
| M4 flash flood | **derna_2023** (Storm Daniel) | 2023-09-11 | EMS EMSR696 AOI01 Derna, **GRA** monitoring 0 (Pléiades 2023-09-13). No DEL exists; its `observedEventA` holds `Flooded area` and `Flood trace` | — | |

Chennai is the brief's third pluvial event. It is not-run before any score,
because it has no usable reference. Pluvial therefore has two test events,
and **both must qualify** for a verdict.

### Tuning events (parameter fitting only, never test events)

Round 3's flood-centred boxes, re-used **exactly** (centres from
`result_round3_2026-10-29.json`), with the same EMS references:

| Module | Tuning events |
|---|---|
| M2 pluvial | hai_phong (EMSR754 AOI05), milagro (EMSR796 AOI06), belize_city (EMSR777 AOI01) |
| M3 waterlogging | thai_binh (EMSR754 AOI06), nam_dinh (EMSR754 AOI07) |
| M4 flash flood | volos (EMSR692 AOI01 m3), kastelli (EMSR933 AOI01 m1), choloma (EMSR778 AOI10) |
| M1 fluvial | none: its validated configuration is fixed |

Round 3 found that Milagro (28 flooded cells) and Kastelli (45) do not
qualify. They are listed anyway and count only if they qualify, which they
cannot. **Choice rule (round 2's):** the grid point with the highest mean
within-event AUC over qualifying tuning events wins. A tie goes to the
default if the default is among the tied, else to the first in grid order.
With no qualifying tuning event, the default is kept.

### Events with history in this project, stated

- **Valencia EMSR773 AOI03** was a round-2 **tuning** event for the retired
  flash-flood method, on a town-centred box at Paiporta. **Derna** was a
  round-1 test and round-2 tuning event for that method (S1). **Chennai**
  was a round-1 coastal site. The new methods take no parameter from any of
  them: methods, constants and grids are fixed here, and tuning uses only
  the events above.
- **Assam** is a test event for both M1 and M3, and **Valencia** for both
  M2 and M4. The box depends only on the reference, so the two modules
  score the same box.

## M1 fluvial — unchanged

Exactly the validated configuration (`analysis.contract.VALIDATED_CONFIGS`
"fluvial"): `low_hand` (1 − HAND/30 m) and `river_size` (log10(1+upa)/log10(1
+ 10,000 km²)), weights 1 : 1, on MERIT Hydro v1_0_1 `hnd` (bilinear) and
`upa` focal max r = 1 km (nearest). Nothing is tuned.

## M2 pluvial — NEW: bluespots, fill-and-spill

On a 30 m UTM grid covering the 4 km box **plus a 1 km margin** on every
side (contributing area outside the box; the margin is never evaluated):

1. **DEM** z: FABDEM, bilinear. No-data cells are outside the domain.
2. **Fill and route:** priority-flood (Barnes et al. 2014) from the grid
   edge and from cells next to no-data. Each cell gets its filled level F
   and a receiver (the cell it was flooded from). Every cell then drains to
   the edge, through depressions and across flats.
3. **Bluespots:** 8-connected components of cells with F − z > 0 whose
   maximum depth is **≥ 0.10 m** (`PLUVIAL_BLUESPOT_MIN_DEPTH_M`). Shallower
   hollows are DEM noise (C51: median pit 1.9 cm). Storage V = Σ (F − z) ×
   cell area.
4. **Local catchment** of a bluespot: the cells whose route reaches it before
   any other bluespot (itself included). **Downstream bluespot:** the first
   bluespot on the route out of its pour point, or the grid edge.
5. **Runoff:** design-storm depth P (mm) × runoff coefficient C per cell,
   C = C_perv + (C_imp − C_perv) × imp, with **C_imp = 0.90** and **C_perv =
   0.30** (default). Here imp = min(1, built + road), from the **current
   stand-ins**: Open Buildings (or OSM where it has none) footprint area,
   plus item 19's OSM road space. Both are labelled `placeholder` and
   `experimental` as now. Vegetation is not used. **P = the mean annual
   maximum 1-day rainfall**, CHIRPS daily over the 10 calendar years before
   the event year, on its 0.05° grid, nearest.
6. **Fill and spill**, upstream first: inflow = local runoff volume + the
   spill of every bluespot upstream; stored = min(inflow, V); spill =
   inflow − stored passes downstream. The water level in each bluespot
   holds exactly `stored` (cells filled from the lowest up), and the
   **ponding depth** w is that level minus z.
7. **Components** (0–1):
   - `ponding` = min(1, w / 1.0 m), and 0 outside bluespots;
   - `runoff_path` = log(1 + runoff-weighted upstream cells) / log(1 +
     cells in the grid), along the routing. Each upstream cell weighs its C.
8. **Score** = weighted mean of `ponding` and `runoff_path`.

**Tuning grid** (12 points): `runoff_path` weight ∈ {0, 0.25, 0.5, 1.0} ×
C_perv ∈ {0.15, 0.30, 0.50}, with `ponding` weight 1. **Default:** 0.5,
0.30.

**Re-test required:** imp is a stand-in. Pluvial must be re-tested when
item 21's `impervious_total` exists. A validated configuration names the
stand-in, so a swapped input is a different configuration (C70).

## M3 waterlogging — NEW: persistence, clay, low relief, backwater

On the 4 km box's 30 m UTM grid. Components, each 0–1:

- `persistence`, the mean of the available of:
  - JRC GSW **monthly history**: water months / observed months, January
    1984 to December of min(event year − 1, 2021);
  - Sentinel-1: the share of IW VV acquisitions with VV < **−18 dB**
    (open water) over the **3 calendar years before the event year**.

  Only years before the event are read.
- `clay` = min(1, clay % / 40), SoilGrids 2.0 `clay_mean` (g/kg ÷ 10),
  thickness-weighted 0–30 cm (0–5, 5–15, 15–30 cm). Where SoilGrids has no
  value (it masks built-up land and water), the focal mean within 1 km is
  used; still none → NaN.
- `low_relief` = 1 − HAND / 15 m (MERIT `hnd`, as before).
- `backwater` = (1 − HAND / 5 m) × log10(upa_near / 100 km²) / 2, each
  factor clipped to 0–1, with upa_near the MERIT `upa` focal max r = 1 km.
  It is low land beside a large river: 0 below 100 km², 1 at ≥ 10,000 km².
  The stage is not observed; river size stands in for a river that runs
  high in the wet season.
- **Score** = weighted mean (`weighted_map`).

**Tuning grid** (36 points): persistence ∈ {1, 2} × clay ∈ {0, 0.5, 1} ×
low_relief ∈ {0.5, 1} × backwater ∈ {0, 0.5, 1}. **Default:** 1, 1, 1, 1
(clay 1, backwater 1, low_relief 1, persistence 1).

## M4 flash flood — NEW: intensity, response time, stream power

On the 4 km box's 30 m UTM grid, from MERIT Hydro, FABDEM and IMERG:

- A = MERIT `upa` focal max within **300 m** (km², floor 0.01): the
  drainage line the cell sits on or beside.
- S = tan(FABDEM slope focal mean within 1 km), floor 0.001.
- Channel length L = 1.273 × A^0.6 km (Hack's law, metric).
- **Response time** t_c = 0.0195 × L_m^0.77 × S^−0.385 minutes (Kirpich), in
  hours.
- **Intensity at that duration:** i = I30 × (max(t_c, 0.5 h) / 0.5 h)^−0.6,
  with I30 the IMERG V07 p99.9 half-hourly rate over the 10 years before
  the event year (the existing layer). If IMERG is unavailable (C73), I30
  = 20 mm/h is used and recorded. I30 is one value per 0.1°, so within a
  box this changes nothing.
- **Peak discharge** Q = C i A / 3.6 m³/s, with C = 0.5 (rational method).
- **Unit stream power** ω = 9810 × Q × S / (3.0 × Q^0.5) W/m², the
  hydraulic-geometry width 3 Q^0.5.
- `power` = log10(1 + ω) / log10(1 + 10,000), clipped to 0–1.
- `valley` = 1 − HAND / H_max, clipped to 0–1 (MERIT `hnd`).
- **Score = valley × power^k.** A hillside (HAND ≥ H_max) scores 0 whatever
  is above it. Channels and valley floors below steep, fast catchments
  score highest.

**Tuning grid** (9 points): H_max ∈ {5, 10, 20} m × k ∈ {0.5, 1, 2}.
**Default:** 10 m, 1.

## Grids and inputs

Every module grid is `utm_grid` at 30 m. M2's adds the 1 km margin.
Rainfall layers are computed on their native grid and mapped nearest, as in
round 2. Every Earth Engine request runs under `ee_timeout.call` with an
explicit timeout (600 s per request, 1,200 s for 10-year rainfall
statistics, 1,800 s per event build), and the run is under `caffeinate -i`
on mains power.

## Weaknesses stated in advance

- Sentinel-1 references: SAR misses water among buildings (double bounce)
  and under vegetation. Mountain valleys (Kullu) have layover and shadow.
  Dubai's first image is 8 days after the rain, so it undercounts heavily.
  The Q1 baseline counts seasonal water as flood (paddy, Kerala's
  backwaters).
- UNOSAT products are "preliminary, not field validated" (their wording).
  The Pakistan product is Sentinel-2 optical at the flood's peak. Its 25,520
  km² extent is far larger than an EMS AOI, so the centroid can land far
  from any town (C72's issue).
- Pluvial's imperviousness is a stand-in. CHIRPS design storm and IMERG are
  one value per box, so they shape the fill-and-spill (which hollows
  overflow), not the per-cell weighting. FABDEM has metre-scale vertical
  error, and urban hollows are often below it.
- Flash flood's Hack and Kirpich formulas are regional empiricisms applied
  everywhere. S is hillslope relief, not channel gradient. MERIT `upa` at
  90 m misses gullies.
- Waterlogging's S1 persistence reads smooth surfaces (tarmac, sand) as
  water. Before 2017 (Kerala), S1 history over India is sparse. JRC monthly
  history ends in 2021. Backwater has no river-stage input.
- Two test events per module (fluvial three) is the minimum. Assam serves
  two modules; Valencia serves two.

A fail is still a fail against the bar.

## Labels (what each outcome does)

- **M2/M3/M4 validated:** the module's own label becomes `validated` only
  through the C70 rule. The exact configuration that ran (method, chosen
  parameters, ceilings, input sources and methods) and its scope (these
  test events, regions, input versions) go into
  `analysis/contract.VALIDATED_CONFIGS`. Any other configuration falls back
  to the worst-of-inputs rule, which caps pluvial at `placeholder` while its
  imperviousness is the stand-in.
- **M2/M3/M4 failed:** label `failed`.
- **M2/M3/M4 not-run:** label `experimental`: a real method, not yet
  validated (the decided meaning, C69). Rounds 1–3's verdicts were on
  methods that no longer exist, and they do not carry over.
- **M1 fluvial:** its label is decided by the C70 rule exactly as now (round
  2's verdict). Round 4 changes only its **scope note**:
  - validated (mean ≥ 0.70): the qualifying round-4 events and regions are
    **added** to the scope, each with its AUC;
  - failed: the scope note is **narrowed**. The round-4 events and regions
    are recorded as not covered, with their AUCs, and the note says the
    validation does not extend to them;
  - not-run: the scope is unchanged.

  Whether a failed round 4 should also change fluvial's label is a question
  for a person, not for this harness. It would go to NEEDS FATE.
