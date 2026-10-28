# Flood validation round 2 — pre-registration (item 26, Phase 1a)

**Written 2026-10-28, before any round-2 score was computed.** Its SHA256 is
recorded in the round-2 result file. The constants in `harness_round2.py` and
`configs/*_constants.py` match this text. Round 1 (`PREREGISTRATION.md`,
`result_2026-10-28.json`) is unchanged and stays the record of round 1.

**What was looked at before this was written, and nothing else:** reference
*availability* only. That covers Sentinel-1 acquisition dates per window, GFD
event IDs and flooded-pixel counts over the project AOIs, Copernicus EMS
product metadata (sensor, date, extent) and the class tallies of its
observed-event polygons, and that IMERG V07 exists. No module score, no
round-2 input value (HAND, slope, upstream area, IMERG, built area) and no
score-vs-reference comparison was computed. Task 4's diagnostic read the
Dharavi FABDEM and `drainage_disconnection` only (no reference).

## What changes from round 1

1. **Fluvial, waterlogging and flash flood are per-pixel maps** on a 30 m
   grid (`HYDROLOGY_PIXEL_M`), replacing AOI-wide scalars. Their inputs and
   formulas are below. The old 0–1 ceilings stay, as provisional constants.
2. **Better references.** Copernicus EMS rapid-mapping delineations and the
   Global Flood Database (GFD) are added alongside Sentinel-1 and JRC.
3. **Coastal gets a wider Sentinel-1 window**, 12 days instead of 3.
4. **Every module has a fixed split into tuning and held-out events.**
   Weights may be adjusted only on tuning events. **The verdict is the
   held-out result.**
5. **Metric unit.** Per-pixel modules are scored **within each event**, and
   the per-event AUCs are averaged. Round 1 pooled scalar sites, which mixed
   event severity into the reference (its stated weakness). Coastal is still
   a scalar, so it still pools.

## Metric and bar

- **Metric:** ROC AUC of the module score, flooded (positive) vs dry
  (negative) evaluation cells. Ties count one half. Same function as round 1
  (`harness.auc`).
- **Bar:** **AUC ≥ 0.70 → validated; < 0.70 → failed.** Unchanged.
- **Per-pixel modules** (pluvial, fluvial, waterlogging, flash flood): AUC is
  computed **within each event**. The module metric is the **unweighted mean
  of the per-event AUCs over held-out events**. An event counts only with
  ≥ 50 flooded **and** ≥ 50 dry evaluation cells. Otherwise it is excluded
  and named. **≥ 2 qualifying held-out events**, or the module is
  **not-run**.
- **Coastal** (still an AOI-wide scalar): round 1's pooled rule. Cells are
  pooled across held-out sites, ≥ 3 sites with both a score and a reference,
  and ≥ 50 flooded and ≥ 50 dry cells in total, or **not-run**.
- **Pooled held-out AUC** (all held-out cells together) is also reported for
  the per-pixel modules, **as a diagnostic only**. Within-event AUC cannot
  see a component that is constant across an event (IMERG and CHIRPS are 0.1°
  and 0.05°, so they are near-constant over a 4 km box). The pooled figure can.
- An event whose Earth Engine call errors or times out, or whose score map is
  empty, is dropped and named. A module with too few events left is
  **not-run**.

## Tuning protocol

- Each module that is tuned has a **finite candidate weight grid**, fixed
  here. For each candidate, the mean within-event AUC over **qualifying
  tuning events** is computed. The candidate with the highest mean is
  chosen. Ties go to the default, if it is among them, else to the first
  candidate in grid order.
- **The held-out events are evaluated once, with the chosen weights only.**
  The harness does not score held-out events under any other candidate.
- The chosen weights become the module's default constants in the same
  commit as the result, and a test pins them to the result file.
- No qualifying tuning event → the default weights are used, and the result
  says so.
- **Not tuned:** ceilings, radii, the HAND source, the reference rules, and
  every constant below except the weights. **Pluvial and coastal have no
  weight grid.** Their weights are unchanged from master `220add1`. Their
  tuning events are reported as diagnostics only.

## Grid and evaluation cells

- **Grid:** per event, a 30 m grid in the UTM zone of the bbox centre,
  snapped to multiples of 30 m, covering the bbox. Pluvial keeps item 19's
  layer grid, as in round 1.
- **Bbox for new (EMS) events:** a **4 km × 4 km square centred on the
  town-centre coordinate listed below**, chosen without looking at the
  flood polygons. Cells outside the EMS product extent are excluded.
  Round-1 sites keep their round-1 bboxes.
- **Valid cell:** inside the bbox (and the EMS product extent), not JRC
  permanent water (occurrence ≥ 80 %), and with a finite score.
- **Evaluation cell:** the 30 m cell. **The exception is GFD events**: GFD is
  250 m MODIS, so they are evaluated on **240 m blocks (8 × 8 cells)**. A
  block is valid if ≥ half its cells are valid. Its score is the mean of its
  valid cells, and it is flooded if ≥ half its valid cells are.

## References

Each source is recorded with its resolution and date. The per-event table
gives the exact product.

| Source | Resolution | Flooded / dry rule |
|---|---|---|
| **Sentinel-1** (round-1 change rule, tightened) | 10 m → 30 m | **Event image** = all IW VV acquisitions on the **earliest date** in the event window. **Pre-event** = median of acquisitions in the 30 days before the event date, **from the same relative orbit(s) as the event image**. A 10 m pixel is flooded where event − pre ≤ −3 dB (`S1_VV_DROP_THRESHOLD_DB`). A 30 m cell is flooded if ≥ half its 10 m pixels are; otherwise it is dry. **Event window:** 3 days (event date, +1, +2) for pluvial and flash flood, as in round 1. **12 days for coastal** (see below). Round 1 used the median of the whole window and every orbit. The same-orbit rule removes look-angle differences, and the earliest-date rule keeps the image closest to peak water |
| **Copernicus EMS rapid mapping** (DEL products, `observedEventA`) | Sensor-dependent, recorded per event (VHR optical 0.3–0.7 m, VHR/HR SAR 1–10 m, PlanetScope 3 m, Sentinel-1 10 m) | Flooded = union of polygons with notation `Flooded area` **or** `Flood trace` (a trace is mapped evidence of water that has receded). A 30 m cell is flooded if ≥ half its area is covered (rasterised at 3 m). Dry = the rest of the product extent |
| **GFD** (`GLOBAL_FLOOD_DB/MODIS_EVENTS/V1`, band `flooded`) | 250 m MODIS, multi-day composite | Flooded where `flooded` = 1, sampled nearest onto the 30 m grid, then 240 m blocks as above |
| **JRC GSW recurrent water** (`JRC/GSW1_4`, round 1) | 30 m, 1984–2021 | Flooded if 5 % ≤ occurrence < 80 %. Dry if < 5 % |

**JRC permanent water is excluded from every reference.**

### The coastal window (task 3)

Round 1 used a 3-day event window. None of Beira, Chennai or Fort Myers Beach
had a Sentinel-1 image in it (C53), so coastal could not be tested. **Round 2
uses event date through event + 12 days, with the earliest acquisition in
it.**

**Why 12 days:** that is Sentinel-1's single-satellite repeat cycle. After
Sentinel-1B failed (December 2021), one satellite flies, so a 12-day window
is the shortest that guarantees at least one pass of each relative orbit over
the site. Two satellites flew before 2022 (6-day repeat), so the window holds
more than enough there.

**Known cost, stated in advance:** surge water drains within hours to days,
so an image several days late will undercount flooding (Beira's first image
is at +4 days, Fort Myers Beach's at +4). Chennai's first post-event image
falls outside even 12 days (+20 or later). Chennai is therefore dropped from
coastal: it would be not-run by construction, and its December 2023 flooding
was mostly rain anyway.

## Per-pixel module definitions (fixed constants)

Each component is clipped to [0, 1]. A module's score is the weighted mean of
its available components. A component whose input is unavailable for an
event is excluded from that event and recorded.

**Inputs**, sampled per event on the 30 m grid through one Earth Engine
`computePixels` call:

- `hand_m`: MERIT Hydro `hnd`, 90 m, bilinear. Chosen over FABDEM-derived
  HAND: MERIT's is hydrologically routed by its authors, round 1 already
  used it, and deriving HAND from FABDEM needs a stream network this project
  does not have.
- `upa_near_km2`: MERIT Hydro `upa` (upstream area, km²), focal **maximum
  within 1000 m**, in MERIT's native projection, then nearest. It is the
  upstream area of the largest drainage line near the cell. A cell's own
  `upa` is near zero on every hillslope, which says nothing about the stream
  that floods it.
- `slope_deg`: `ee.Terrain.slope` of FABDEM (30 m), bilinear.
- `relief_slope_deg`: the same slope, focal **mean within 1000 m**.
- `built`: Open Buildings v3 footprint union area fraction per cell (painted
  at 2 m, area-averaged). This is the same producer as item 26 task 1, and
  it stays `placeholder`. It is used for waterlogging only. An event box
  with zero Open Buildings footprints has this component excluded.
- `rain_intensity_mm_h`: **99.9th percentile** of IMERG V07 half-hourly
  `precipitation` (mm/h) over the **10 calendar years before the event
  year**, at 0.1°, nearest. It is used for flash flood. In production it
  covers the 10 years before the run year.
- `rain_annual_mm`: CHIRPS mean annual total, as in round 1 (the 10 years
  before the event year), at 0.05°, nearest. It is used for waterlogging.

**Fluvial** (`configs/fluvial_constants.py`):

| Component | Formula |
|---|---|
| `low_hand` | 1 − `hand_m` / 30 (`HAND_NORMALIZATION_MAX_M`, unchanged) |
| `river_size` | log10(1 + `upa_near_km2`) / log10(1 + 10 000) (`FLUVIAL_UPSTREAM_AREA_NORMALIZATION_MAX_KM2`, new) |

The default weights are `low_hand` 1, `river_size` 0, i.e. round 1's
HAND-only method, now per pixel. **Grid:** `low_hand` 1, `river_size` ∈
{0, 0.25, 0.5, 1}.

**Flash flood** (`configs/flash_flood_constants.py`):

| Component | Formula |
|---|---|
| `valley_floor` | 1 − `hand_m` / 10 (`FLASH_FLOOD_HAND_NORMALIZATION_MAX_M`, new) |
| `steep_surroundings` | `relief_slope_deg` / 15 (`FLASH_FLOOD_SLOPE_NORMALIZATION_MAX_DEG`, unchanged) |
| `small_catchment` | 1 − `upa_near_km2` / 50 (`FLASH_FLOOD_SMALL_CATCHMENT_MAX_KM2`, unchanged) |
| `rainfall_intensity` | `rain_intensity_mm_h` / 20 (`FLASH_FLOOD_INTENSITY_NORMALIZATION_MAX_MM_H`, new, fixed before any IMERG value was read) |

Steepness is the **surrounding** relief, not the cell's own slope. Flash
floods inundate flat valley floors under steep ground, so scoring a cell's
own slope would rank hillsides above the valley floors that flood. That
would break the physical meaning, so it is defined this way here, before any
run.

The default weights are all 1 (round 1 was an unweighted mean). **Grid:**
`valley_floor` ∈ {0.5, 1}, `steep_surroundings` ∈ {0, 0.5, 1},
`small_catchment` ∈ {0, 0.5, 1}, and `rainfall_intensity` fixed at 1.

**Waterlogging** (`configs/waterlogging_constants.py`):

| Component | Formula |
|---|---|
| `low_relief` | 1 − `hand_m` / 15 (`WATERLOGGING_HAND_NORMALIZATION_MAX_M`, unchanged) |
| `impervious` | `built` / 0.70 (`WATERLOGGING_IMPERVIOUS_NORMALIZATION_MAX_PCT`, unchanged) |
| `flatness` | 1 − `slope_deg` / 5 (`WATERLOGGING_SLOPE_NORMALIZATION_MAX_DEG`, new, equal to pluvial's) |
| `rainfall_climatology` | `rain_annual_mm` / 2500 (`FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM`, unchanged) |

The default weights are all 1. **Grid:** `low_relief`, `impervious` and
`flatness` each ∈ {0, 0.5, 1}, not all zero, and `rainfall_climatology`
fixed at 1.

**Pluvial:** item 26 tasks 1–4 as built (master `220add1`), weights
unchanged, **not tuned**. `drainage_disconnection` is as it stands after
task 4.

**Coastal:** round 1's AOI-wide scalar (`compute_coastal_susceptibility`),
unchanged, **not tuned**. Making it per-pixel is out of this phase's scope.

## Events and the split

The mechanism assignments are judgments, made from the event's documented
cause. The EMS polygon class (`obj_desc`) is recorded but not relied on: EMS
labels Sittwe's cyclone surge "Flash flood" and Hanoi's river flood "Coastal
flood". **Round-1 sites go to tuning** wherever a module has them, so that
held-out events are ones no round of this project has scored.

**Pluvial** (S2 vegetation window = dry season, 3 months)

| Split | Event | Reference (sensor, date) | Bbox / centre | Veg window |
|---|---|---|---|---|
| tuning | dharavi, Mumbai 2017-08-29 | S1 (round 1) | round-1 bbox | 2018-01-01 → 2018-03-31 |
| held-out | hai_phong, Typhoon Yagi 2024-09-07 | EMSR754 AOI05 DEL m0, WorldView-2, 2024-09-14 | 20.8449, 106.6881 | 2024-11-01 → 2025-01-31 |
| held-out | milagro, Ecuador rains 2025 | EMSR796 AOI06 DEL m0, ICEYE, 2025-04-05 | −2.1347, −79.5872 | 2024-07-01 → 2024-09-30 |
| held-out | belize_city, Tropical Storm Sara 2024-11-15 | EMSR777 AOI01 DEL m0, COSMO-SkyMed SG, 2024-11-17 | 17.5046, −88.1962 | 2024-03-01 → 2024-05-31 |

**Fluvial**

| Split | Event | Reference (sensor, date) | Centre |
|---|---|---|---|
| tuning | faenza, Lamone 2023-05-02 | EMSR659 AOI02 DEL m0, Pléiades, 2023-05-04 | 44.2856, 11.8833 |
| tuning | encantado, Taquari 2024-05-02 | EMSR720 AOI02 DEL m0, RADARSAT-2, 2024-05-04 | −29.2360, −51.8700 |
| held-out | hanoi, Red River (Yagi) 2024-09-09 | EMSR754 AOI03 DEL m0, WorldView-3, 2024-09-14 | 21.0285, 105.8542 |
| held-out | kolonnawa, Kelani Ganga (Colombo) 2025-11-30 | EMSR851 AOI02 DEL m0, PlanetScope, 2025-11-30 | 6.9333, 79.8833 |
| held-out | nysa, Nysa Kłodzka 2024-09-14 | EMSR756 AOI03 DEL m0, Sentinel-1, 2024-09-15 | 50.4747, 17.3337 |
| held-out | hue, Perfume River 2025-10-29 | EMSR848 AOI06 DEL m0, GeoEye-1, 2025-11-09 | 16.4637, 107.5909 |

**Flash flood**

| Split | Event | Reference (sensor, date) | Bbox / centre |
|---|---|---|---|
| tuning | paiporta, Valencia DANA 2024-10-29 | EMSR773 AOI03 DEL m0, WorldView-2 / GeoEye-1, 2024-10-31 | 39.4280, −0.4177 |
| tuning | derna, Storm Daniel 2023-09-11 | S1, 3-day window | round-1 bbox |
| tuning | bad_neuenahr, Ahr 2021-07-14 | S1, 3-day window | round-1 bbox |
| held-out | volos, Storm Daniel 2023-09-05 | EMSR692 AOI01 DEL m3, WorldView-3, 2023-09-09 | 39.3622, 22.9420 |
| held-out | kastelli, Crete 2026-10-01 | EMSR933 AOI01 DEL m1, Legion, 2026-10-06 | 35.2131, 25.3381 |
| held-out | choloma, Tropical Storm Sara 2024-11-16 | EMSR778 AOI10 DEL m0, COSMO-SkyMed, 2024-11-22 | 15.6133, −87.9531 |

**Coastal** (scalar, pooled; the tuning event is a diagnostic only)

| Split | Event | Reference (sensor, date) | Bbox / centre |
|---|---|---|---|
| tuning | kyaukpyu, Cyclone Mocha 2023-05-14 | EMSR661 AOI02 DEL m0, COSMO-SkyMed, 2023-05-14 | 19.4290, 93.5494 |
| held-out | beira, Cyclone Idai 2019-03-15 | S1, 12-day window (first image +4 d) | round-1 bbox |
| held-out | fort_myers_beach, Hurricane Ian 2022-09-28 | S1, 12-day window (first image +4 d) | round-1 bbox |
| held-out | sittwe, Cyclone Mocha 2023-05-14 | EMSR661 AOI01 DEL m0, COSMO-SkyMed, 2023-05-15 | 20.1462, 92.8983 |
| held-out | black_river, Hurricane Melissa 2025-10-28 | EMSR847 AOI15 DEL m0, RADARSAT-2, 2025-10-28 | 18.0264, −77.8487 |

**Waterlogging**

| Split | Event | Reference (sensor, date) | Bbox / centre |
|---|---|---|---|
| tuning | 8 round-1 AOIs: dharavi, hcmc, kigali, accra, dhaka, capetown, guatemala, nusantara | JRC recurrent water | round-1 bboxes |
| held-out | thai_binh, Yagi 2024-09-09 | EMSR754 AOI06 DEL m0, WorldView-2, 2024-09-20 | 20.4463, 106.3366 |
| held-out | nam_dinh, Yagi 2024-09-09 | EMSR754 AOI07 DEL m0, WorldView-2, 2024-09-14 | 20.4200, 106.1683 |
| held-out | jakarta_gfd_3280, 2008-03-01 → 2008-04-03 | GFD event 3280, MODIS 250 m | round-1 jakarta bbox |

Jakarta is removed from waterlogging's JRC tuning AOIs, so that one site is
not on both sides of the split. The held-out cities Lagos, Nairobi and Rio
(item 27's firewall) are not used anywhere.

**Weaknesses stated in advance:**

- SAR misses flooding among dense buildings (double bounce).
- Late images undercount (Hue +11 days, Thai Binh +11, coastal S1 +4).
- The two Crete and two Myanmar events are separate towns struck by one
  storm, so they are not independent.
- GFD's 250 m blocks are coarse for a 4–7 km box.
- The `built` and pluvial inputs are placeholders.

A fail is still a fail against the bar.

## Labels

A module's `validation_status` becomes **`validated` only if its held-out
verdict is validated**. It becomes `failed` if the held-out verdict is
failed. A not-run module keeps its current label. Pluvial and waterlogging
take their weakest input's label (`placeholder`) whatever the verdict, as in
round 1, and the result is recorded beside it. A `validated` verdict applies
to that module under these events and inputs only.
