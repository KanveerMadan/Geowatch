# Flood validation — pre-registration (item 26, task 8)

**Written 2026-10-28, before the harness computed any reference or score.**
Its SHA256 is recorded in the result file. The constants in `harness.py`
match this text.

Implements the Tier 2 criterion decided 2026-09-24 (`05_BUILD_MANUAL.md`,
Part 4 mandate note): each of the five hazard calculations is validated by
**discrimination** — does its score rank observed-flooded cells above dry ones,
across many cells — against JRC Global Surface Water and Sentinel-1 flood
extents, each hazard on its own site(s), criteria fixed before the run.

## Metric and bar (every module)

- **Unit:** a 30 m cell (`HYDROLOGY_PIXEL_M`) inside the site bbox. JRC
  permanent water (occurrence ≥ 80 %, `JRC_PERMANENT_WATER_OCCURRENCE_PCT`) is
  excluded from both classes: it is not flooding.
- **Metric:** ROC AUC of the module's score over flooded (positive) vs dry
  (negative) cells. Ties count one half.
- **Bar:** AUC ≥ **0.70** → **validated**; AUC < 0.70 → **failed**.
- **Minimum reference:** ≥ 50 flooded and ≥ 50 dry cells, and for pooled
  modules ≥ 3 sites carrying both a score and a reference. Otherwise
  **not-run** (insufficient reference), reported with the counts.
- A site whose Earth Engine call errors, or whose score is `None`, is dropped
  and named. A module with no usable site is **not-run**.

Four of the five modules (fluvial, coastal, flash flood, waterlogging) emit one
AOI-wide scalar, so within a site every cell has the same score. Their cells are
**pooled across sites**: the AUC then asks whether higher-scoring sites have
more flooded cells. That also mixes event severity into the reference — a known
weakness of scoring a static scalar against events, stated here before the run.

## References

- **Sentinel-1 event extent** — the project's existing definition
  (`ingestion/inundation.py`, `configs/inundation_constants.py`): VV, IW mode,
  median of the event window minus median of the pre-event window; a 10 m pixel
  is flooded where the drop is ≤ −3 dB. A 30 m cell is flooded if ≥ half its
  10 m pixels are. Pre-event window = the 30 days before the event start; event
  window = event start + 3 days. Known blind spot, stated in advance: dense
  urban double bounce hides urban flooding from SAR.
- **JRC GSW recurrent water** — `JRC/GSW1_4/GlobalSurfaceWater` occurrence
  (1984–2021): a cell is flooded if 5 % ≤ occurrence < 80 %, dry if
  occurrence < 5 % (masked = 0).

## Modules, sites and references

| Module | Score | Reference | Sites (bbox W, S, E, N) and events |
|---|---|---|---|
| **pluvial** | per-cell map, as built in tasks 1–4 (impervious, infiltration, road conduits, DEM terrain; waterway distance and the AOI-wide scalars left out — the scalars cannot change a within-site ranking) | S1 event | Dharavi (72.836, 19.037, 72.862, 19.060), Mumbai floods **2017-08-29**. Vegetation composite 2018-01-01 → 2018-03-31 (dry season) |
| **fluvial** | `compute_fluvial_susceptibility` (MERIT HAND) | JRC recurrent water | `vector/aois.py` `BASELINE_AOIS` minus the held-out cities Lagos and Nairobi: dharavi, jakarta, hcmc, kigali, accra, dhaka, capetown, guatemala, nusantara |
| **waterlogging** | `compute_waterlogging_susceptibility` (HAND, Open Buildings built-area mean over the bbox, CHIRPS) | JRC recurrent water | same nine AOIs |
| **coastal** | `compute_coastal_susceptibility` (shoreline distance, FABDEM) | S1 event | Beira (34.83, -19.85, 34.87, -19.81), Cyclone Idai **2019-03-15**; Chennai Velachery (80.20, 12.96, 80.24, 13.00), Cyclone Michaung **2023-12-04**; Fort Myers Beach (-81.97, 26.43, -81.93, 26.47), Hurricane Ian **2022-09-28** |
| **flash flood** | `compute_flash_flood_susceptibility` (slope, MERIT catchment, CHIRPS) | S1 event | Paiporta, Valencia (-0.44, 39.41, -0.40, 39.45), DANA **2024-10-29**; Derna (22.62, 32.75, 22.66, 32.78), Storm Daniel **2023-09-11**; Bad Neuenahr-Ahrweiler (7.09, 50.53, 7.13, 50.56), **2021-07-14** |

Sites were chosen for being documented flood events of each mechanism (or, for
the JRC modules, the project's fixed AOI list), not for how they score. No
score has been looked at.

A result of **validated** applies to that module under these sites and inputs
only; module output labels are not changed by the harness.
