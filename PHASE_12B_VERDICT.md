# Phase 12B Verdict — per-ward pluvial / waterlogging over `datameet_mumbai_bmc_wards`

Written incrementally during the run. Each milestone is appended the moment it
happens, not reconstructed at the end.

---

## 0. Pre-flight (before launch)

Confirmed the three prior-session fixes are actually present in the working tree:

| Fix | Where | Confirmed |
|---|---|---|
| Chunked GEE export | `ingestion/tiler.py` — `_plan_export_chunks()`, `_export_image_local_chunked()`, dispatch at `export_image_local()` | yes |
| `OBSERVATION_QUALITY_SCALE_M = 60` | `ingestion/sentinel2.py:69`, used at `:127` | yes |
| 1-D/2-D shape, non-serializable `susceptibility_map`, numpy scalars in `json.dump` | `zonal/landcover_screening.py` — bbox-window crop + `PLUVIAL_UNKNOWN_INDEX`, `susceptibility_map` stripped, `_json_safe` default hook | yes |

Environment: `geowatch-env/bin/python` (3.12.13, geopandas 1.1.3, rasterio 1.5.0).
`venv/` (3.9.6) does **not** have the deps — wrong interpreter is a trap here.
GEE auth verified live before launch.

### Case 1 (reuse) must not fire — checked in advance

The brief says if Case 1 fires, something is wrong with the coverage check.
I computed the coverage of every on-disk run that has `landcover_map_full.npy`
against the Mumbai target bounds `(72.77633, 18.89396, 72.97973, 19.27018)`:

| Prior run | Coverage of Mumbai extent |
|---|---|
| `oqvalidate_dharavi_20260821_154627` | 0.78% |
| `phase1_dharavi_20260820_125646` | 0.78% |
| `phase1_dharavi_20260820_125809` | 0.78% |
| `regress_dharavi_20260821_140445` | 0.78% |
| `ward_pilot_timing_20260809_113812` | 3.12% |
| `phase1_multitile_20260820_130117` | 8.36% |

Max is 8.36%, far below `MIN_FOOTPRINT_COVERAGE_PCT = 99.0`. Case 1 correctly
will not fire; the run goes to Case 3 (fresh wide run). No coverage-check bug.

### Predicted export shape (computed offline, to be checked against the real run)

- Export grid at 10 m: **2265 x 4189 px**, 6 bands
- Single-request estimate: **271.5 MiB** vs GEE ceiling 48 MiB, chunk budget 24 MiB
  → chunking is genuinely required; this is not a no-op path
- Planned: **12 chunks** (3 cols x 4 rows), largest **755 x 1048 px**, ~22.6 MiB each
- Tile loop at `TILE_SIZE = 512`: ceil(2265/512) x ceil(4189/512) = **5 x 9 = 45 tiles**
  (brief estimated ~40)

### Date window

`WIDE_RUN_DATE_START = "2025-11-01"`, `WIDE_RUN_DATE_END = date.today().isoformat()`
= **2026-08-22**. Used as-is from `configs/zonal_constants.py`. No auto-mode dates.

Note for the record: `WIDE_RUN_DATE_END` resolving to *today* means the window is
2025-11-01 → 2026-08-22 (~9.5 months), which spans the 2026 monsoon rather than
being a post-monsoon-only window. The constant's own docstring describes the
intent as "start of typical post-monsoon clear season". Whether the end date
should be pinned rather than open-ended is a real question, but it is the
declared constant and I ran it unmodified.

---

## 1. Run launched

**Launched 2026-08-22 01:44:26 IST** (local wall clock), PID 75511, foreground-blocking.

Command:

```
geowatch-env/bin/python -u -m zonal.landcover_screening \
  --boundary-layer-id datameet_mumbai_bmc_wards \
  --storage-dir data/boundaries \
  --output data/pipeline_runs/phase12b_ward_landcover_v2.json \
  --wide-run-output-dir data/pipeline_runs
```

Output written to `phase12b_ward_landcover_v2.json` rather than overwriting
`phase12b_ward_landcover.json`, which is the record of the 2026-08-21 failure
(`raw.tif: No such file or directory` — the pre-chunked-export failure mode).

Confirmed from the live log:

- Planner chose **Case 3 (triggered)**, not Case 1. As predicted above.
- Run id: `phase12b_wide_datameet_mumbai_bmc_wards_20260822_014426`
- AOI: `(72.77633295153348, 18.89395643371942)` to `(72.97973149704592, 19.270176667777736)` — full 24-ward extent
- **Date range used: 2025-11-01 to 2026-08-22** — the `WIDE_RUN_*` constants, manual branch taken, not the 90-day auto window
- Sentinel-2: **164 images after cloud filtering**

---

## 2. Chunked GEE export — COMPLETED, matched prediction exactly

This is the fix that the 2026-08-21 run died on. It worked at full Mumbai scale.

```
Export grid: 2265x4189px x 6 bands -> est. GEE request size 271.5 MiB (ceiling 48 MiB)
AOI exceeds GEE's single-request ceiling -- chunking into 12 sub-requests
  (~22.6 MiB each, largest chunk 755x1048px).
```

**Chunk count and sizes actually used: 12 chunks, in a 3-col x 4-row grid.**

| Chunk | Size (px) | Offset (col, row) |
|---|---|---|
| 1 | 755 x 1048 | (0, 0) |
| 2 | 755 x 1048 | (755, 0) |
| 3 | 755 x 1048 | (1510, 0) |
| 4 | 755 x 1048 | (0, 1048) |
| 5 | 755 x 1048 | (755, 1048) |
| 6 | 755 x 1048 | (1510, 1048) |
| 7 | 755 x 1048 | (0, 2096) |
| 8 | 755 x 1048 | (755, 2096) |
| 9 | 755 x 1048 | (1510, 2096) |
| 10 | 755 x 1045 | (0, 3144) |
| 11 | 755 x 1045 | (755, 3144) |
| 12 | 755 x 1045 | (1510, 3144) |

Bottom row is 1045 px rather than 1048 — the `min(off + step, extent)` clamp
absorbing 4189 = 3 x 1048 + 1045. Columns tile 2265 = 3 x 755 exactly.

`Stitched 12 chunks -> 2265x4189px GeoTIFF.` — stitched dimensions equal the
planned grid exactly, so no chunk was dropped, duplicated, or misplaced.
All 12 chunks succeeded on the first attempt; no network retries were needed.

Downstream of the export:

- **45 RGB preview tiles** generated (5 x 9 at `TILE_SIZE = 512`) — brief estimated ~40.
- OSM: 63,065 road segments, 1,397 waterway features.
  Road mask 820,273 px; waterway mask 90,995 px, both rasterized onto the
  2265x4189 grid. So `waterway_dist_map_full` is genuinely populated —
  the "no OSM waterways" degenerate path is not in play here.

**Elapsed at this milestone: ~10 min** (export + tiling + OSM + distance maps
done; SAM/inference over 45 tiles still to come).

---

## 3. Observation quality / quality gate — PASSED

```
Composite: 164 source images, 2025-11-01 to 2026-08-22
Observation quality: valid=93.08%, cloud=6.36%, shadow=0.56%
```

| Gate condition | Threshold | Actual | Result |
|---|---|---|---|
| `observation_quality.valid_observation_pct` | >= 60.0 (`MIN_VALID_OBSERVATION_PCT`) | **93.08%** | PASS, 33.08 pp of headroom |
| `applicability.urban_landcover_model.status` != `out_of_distribution` | required (`REQUIRE_LANDCOVER_IN_DISTRIBUTION = True`) | pending — computed after inference | see §4 |

For contrast, the `pilot_3ward` auto-mode run the brief warns about came back at
**50.84% valid / `out_of_distribution`** and would have failed. The wide
`WIDE_RUN_DATE_*` window produced **93.08%**. The post-monsoon window being
load-bearing is confirmed by real numbers, not assumed.

No threshold was lowered. `MIN_VALID_OBSERVATION_PCT` is still 60.0 and
`REQUIRE_LANDCOVER_IN_DISTRIBUTION` is still `True`.

Applicability, read off the completed run's `result.json`:

```
applicability.urban_landcover_model.status = "in_distribution"
```

So the second gate condition passed too. **Quality gate: PASSED on both conditions.**

Full observation-quality block as recorded:

```json
{ "status": "available", "method": "scl_fraction_across_collection",
  "reduction_scale_m": 60, "valid_observation_pct": 93.08,
  "cloud_pct": 6.36, "cloud_shadow_pct": 0.56, "no_data_pct": 0, "error": null }
```

`reduction_scale_m: 60` confirms the `OBSERVATION_QUALITY_SCALE_M` fix is what
actually ran — this is the change that took Mumbai from stalling >84 min to
completing, and it did not stall.

---

## 4. Wide run + per-ward loop — COMPLETED

`Case 3 (triggered): fresh wide run passed quality gate.`
`Phase 12B complete: 24/24 wards with usable pluvial/waterlogging screening.`

### Wall-clock time

| Stage | Duration |
|---|---|
| Sentinel-2 ingestion + **12-chunk export** + stitch | 598 s (9 m 58 s) |
| Tiling (45 tiles), OSM fetch, distance maps, SAM + sliding-window inference over 45 tiles, elevation/exposure/vulnerability | 690 s (11 m 30 s) |
| **Per-ward loop (24 wards: rasterize + slice + pluvial + waterlogging)** | **~1 s** |
| **TOTAL** | **1288 s = 21 m 28 s** |

Started 01:44:23, finished 02:05:51 (2026-08-22, local).

**`WIDE_RUN_TIMEOUT_SECONDS = 3600` is comfortably adequate** — the run used 36%
of it. The brief flagged this constant as never tested at scale and extrapolated
from a 2-tile pilot; it is now measured at full 45-tile scale with 2.8x headroom.
The extrapolation was conservative in the right direction.

Worth noting the per-ward loop is ~1 second for all 24 wards. All the cost is in
the single shared wide run, which is exactly what the Case 1/2/3 planner exists
to amortize. The bbox-window crop in `compute_ward_landcover_screening()` (the
fix for the 1-D/2-D shape bug) keeps this O(ward) rather than O(full raster) —
that shows up here as the loop being effectively free.

Artifacts on disk (Option A persistence confirmed working at scale):

- `raw.tif` — 227.7 MB, 2265x4189 px, 6 bands
- `landcover_map_full.npy` — 9,488,213 B (= 2265 x 4189 uint8 + 128 B header, exact)
- `waterway_dist_map_full.npy` — 37,952,468 B (float32, populated — not the None case)
- `raster_info.json` — 140 B

### Bugs fixed this session: NONE

The run completed end-to-end on the first attempt with no code changes. Every
failure mode the previous three sessions hit was already fixed and the fixes
held at full scale. I want to be plain about this rather than manufacture a
finding: I changed no code, and nothing broke that needed fixing.

The only deviation from a default was writing to
`phase12b_ward_landcover_v2.json` to preserve the prior failure record.

---

## 5. Per-ward results — 24 of 24 wards produced usable output

Every ward returned `status: "experimental"` for both hazards. Zero wards hit
the `not_calculated` / zero-pixel path.

| Ward | Pixels | Pluvial | Class | Waterlogging | Class | Impervious % | Infiltration % |
|---|---|---|---|---|---|---|---|
| C | 20,319 | **0.7643** | high | 0.6667 | high | 91.25 | 1.96 |
| H/W | 95,999 | 0.7586 | high | 0.6667 | high | 82.64 | 1.94 |
| E | 77,284 | 0.7446 | high | 0.6667 | high | 72.24 | 4.05 |
| B | 28,238 | 0.7425 | high | 0.6667 | high | 72.97 | 2.19 |
| K/E | 254,856 | 0.7231 | high | 0.6667 | high | 71.45 | 5.24 |
| D | 87,377 | 0.7190 | high | 0.6667 | high | 73.83 | 9.02 |
| L | 166,738 | 0.7115 | high | 0.6210 | high | 60.42 | 4.48 |
| G/N | 93,159 | 0.7062 | high | 0.6605 | high | 68.70 | 8.34 |
| G/S | 98,801 | 0.7051 | high | 0.6316 | high | 62.64 | 6.45 |
| F/S | 103,987 | 0.6996 | high | 0.6101 | high | 58.13 | 9.00 |
| K/W | 261,141 | 0.6844 | high | 0.6362 | high | 63.60 | 10.85 |
| A | 119,066 | 0.6761 | high | 0.5754 | moderate | 50.84 | 7.45 |
| H/E | 132,039 | 0.6593 | high | 0.5989 | moderate | 55.76 | 13.66 |
| F/N | 130,577 | 0.6415 | high | 0.5700 | moderate | 49.69 | 13.57 |
| M/W | 185,004 | 0.6307 | high | 0.5810 | moderate | 52.01 | 19.21 |
| R/S | 194,836 | 0.5875 | moderate | 0.5381 | moderate | 43.01 | 23.04 |
| R/N | 150,912 | 0.5827 | moderate | 0.5395 | moderate | 43.30 | 25.34 |
| S | 316,435 | 0.5409 | moderate | 0.4914 | moderate | 33.19 | 26.94 |
| M/E | 351,712 | 0.5392 | moderate | 0.4925 | moderate | 33.42 | 28.86 |
| P/S | 267,948 | 0.5215 | moderate | 0.4948 | moderate | 33.91 | 33.75 |
| N | 273,166 | 0.5108 | moderate | 0.4891 | moderate | 32.71 | 36.10 |
| P/N | 497,042 | 0.4849 | moderate | 0.4530 | moderate | 25.14 | 35.72 |
| T | 456,160 | 0.4405 | moderate | 0.4134 | moderate | 16.82 | 40.56 |
| R/C | 511,124 | **0.4400** | moderate | **0.4364** | moderate | 21.64 | 48.50 |

Spread:

| Metric | Min | Max | Spread | Mean | SD | Distinct values |
|---|---|---|---|---|---|---|
| Pluvial | 0.4400 | 0.7643 | 0.3243 | 0.6339 | 0.1010 | **24 / 24** |
| Waterlogging | 0.4134 | 0.6667 | 0.2533 | 0.5764 | 0.0814 | **19 / 24** |
| Impervious % | 16.82 | 91.25 | 74.43 | 52.89 | 19.64 | 24 / 24 |

### Do the values vary plausibly across wards? Yes — and they match Mumbai's real geography

This is the part I most expected to be disappointing, and it is not.

- The **top of the pluvial ranking is the Island City core**: C (Fort/Kalbadevi,
  91.25% impervious — the densest built fabric in the city), H/W (Bandra West),
  B, D, E. These are the wards a Mumbai resident would name first for street
  flooding.
- The **bottom is the wards containing Sanjay Gandhi National Park**: R/C
  (Borivali, 48.50% infiltration proxy) and T (Mulund, 16.82% impervious — the
  lowest in the city). Both are large, hilly, heavily vegetated. Getting these
  two as the least pluvial-susceptible is a strong sanity signal.
- **Pixel counts track true ward areas.** I cross-checked every ward's mask
  against its polygon area in UTM 43N: the ratio is 1.062–1.064 for all 24 wards
  — a *constant* factor, not per-ward scatter. That constant is the geometry of a
  10 m-nominal EPSG:4326 pixel at 19°N (~9.45 m x 10 m, so ~94.5 m² not 100 m²),
  i.e. an artifact of *my* km² conversion, not of the pipeline. Phase 12B itself
  only ever uses pixel *fractions* (`category_area_pct`), which are ratios and
  immune to it. The true-polygon rasterization is correct.
- Ward polygons cover 51.4% of the raster bounding box — expected for Mumbai's
  peninsular shape inside a rectangular extent, and the reason the true-polygon
  masking in 12B is a genuine improvement over 12A's bbox surrogate.

So the ward-to-ward ordering is defensible. **But see the two caveats below
before treating it as a ranking.**

---

## 6. Findings that qualify the result

### 6.1 Waterlogging saturates for 6 of 24 wards — reported, not fixed

Waterlogging has only 19 distinct values across 24 wards. Six wards — B, C, D,
E, K/E, H/W — return *exactly* 0.6667. Reading
`configs/waterlogging_constants.py` against the run's actual inputs explains it
completely:

- `WATERLOGGING_HAND_NORMALIZATION_MAX_M = 15.0`, actual `mean_hnd_m = 17.646`
  → the relief component is pinned at **0** for every ward.
- `FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM = 2500.0`, actual
  `rainfall_mean_annual_mm = 3269.2` → the rainfall component clips at **1.0**
  for every ward.
- `WATERLOGGING_IMPERVIOUS_NORMALIZATION_MAX_PCT = 70.0` → any ward at or above
  70% impervious clips at **1.0**.

The method is an unweighted average of the three. So in this run waterlogging
reduces to `(0 + min(impervious/70, 1) + 1) / 3` — a linear rescale of
imperviousness alone, mathematically confined to **[0.333, 0.667]**, and it can
never be classed `high` above 0.6667 or reach `very_high` at all. It also
collapses C ward (91.25% impervious) onto E ward (72.24%) as identical.

I did not change any constant or formula. Retuning normalization ceilings is a
methodology decision, not a coding fix, and doing it mid-run to make output look
better is exactly the move this track's rules prohibit. Flagging it for the
project owner: **the waterlogging ceilings are miscalibrated for Mumbai's
rainfall and relief regime**, and its per-ward output is currently a monotone
function of imperviousness with a hard ceiling. Pluvial does not have this
problem (24 distinct values).

### 6.2 `shared_aoi_context` — reporting, NOT resolving (§6.1 of the brief)

This is the open decision the brief says must not be settled while coding, so I
am putting the real numbers next to it and stopping there.

Every one of the 24 wards carries an **identical** `shared_aoi_context`:

```json
{ "relative_elevation_score": 0.7768,
  "rainfall_mean_annual_mm": 3269.2,
  "hand_mean_m": 17.646,
  "note": "identical across all wards in this run -- not independently measured per ward" }
```

I verified this programmatically: serializing all 24 blocks yields **1 distinct
value**. The block is present and correct on every ward, so the caveat is
surfaced as §5.3 requires.

What the run adds to the decision: **the entire ward-to-ward spread reported in
§5 is produced by land cover alone.** `compute_pluvial_susceptibility()`'s own
limitations field says so independently — "rainfall_climatology and
relative_elevation are AOI-WIDE SCALARS applied uniformly — they shift the
overall level of the map but contribute NO spatial pattern." Concretely, of
pluvial's five components, two (rainfall, relative elevation) are constant across
all wards; only impervious/infiltration and drainage distance vary. For
waterlogging it is worse — per §6.1, two of three components are not merely
constant but pinned at their limits, so it is one variable, not three.

The decision (does HAND need to go per-ward before wards can be honestly ranked?)
is unchanged and remains the project owner's. What is now in hand is the evidence
it was waiting on: a 0.3243-wide pluvial spread that is real and geographically
sensible, but single-variable. **Phase 13 stays blocked on this.**

### 6.3 Inherited landcover-model weakness is visible in the output

Per brief §5.4 (LOCO mean mIoU 0.313; `paved_road` over-predicted ~2.4x and
acting as a magnet class). This is directly visible: `paved_road` supplies
**44.47 of A ward's 50.84** impervious points — 87% of the impervious fraction,
citywide the dominant contributor. Since impervious fraction is the *only*
genuinely varying input to both hazards here, the entire per-ward signal rests
on the one class the audit identified as most over-predicted. Per-ward unknown
fractions run 4.5%–28.6%.

Not a new problem and not one to fix in this phase — but it means the §5 ranking
should be read as "ordering by modelled imperviousness," which is what it
literally is.

---

## 7. Verdict

**Phase 12B ran successfully end-to-end for the first time. 24/24 wards produced
usable pluvial and waterlogging screening.**

| Question | Answer |
|---|---|
| Wall-clock time | **21 m 28 s** (1288 s); 36% of `WIDE_RUN_TIMEOUT_SECONDS = 3600`, which is now validated at scale |
| Chunk count / sizes for Mumbai | **12 chunks**, 3x4 grid, 755x1048 px each (bottom row 755x1045), ~22.6 MiB each; stitched to 2265x4189 px, 227.7 MB |
| Quality gate | **PASSED** — 93.08% valid observation vs 60.0% floor; `urban_landcover_model = in_distribution` |
| Wards with usable output | **24 / 24** |
| Do values vary plausibly | **Yes** — pluvial 0.4400–0.7643, 24/24 distinct, ordering matches real Mumbai geography (dense Island City high, national-park wards low). Waterlogging varies but saturates: 19/24 distinct, 6 wards pinned at 0.6667 |
| Bugs fixed | **None** — no code changes were needed; all three prior fixes held at full scale |

Constraints honoured: `WIDE_RUN_DATE_START`/`END` used (never auto-mode);
`MIN_VALID_OBSERVATION_PCT` and `REQUIRE_LANDCOVER_IN_DISTRIBUTION` untouched;
no fusion formula invented (`compute_risk()` still returns `not_calculated`);
`threading.Thread(daemon=True)` untouched; no retry layers added (none were
needed — all 12 chunks and the Overpass query succeeded first try);
`shared_aoi_context` reported and left unresolved.

**Open items for the project owner, in priority order:**

1. §6.2 — the `shared_aoi_context` decision, now with real numbers. Blocks Phase 13.
2. §6.1 — waterlogging normalization ceilings are miscalibrated for Mumbai
   (relief pinned at 0, rainfall pinned at 1, 6 wards clipped). New this session.
3. §0 — `WIDE_RUN_DATE_END = date.today()` makes the "post-monsoon" window
   open-ended and monsoon-spanning. It produced 93.08% here so it is not urgent,
   but the constant does not do what its docstring says it does.
