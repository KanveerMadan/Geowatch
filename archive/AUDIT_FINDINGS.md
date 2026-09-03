# GeoWatch Audit Findings

Investigation-only audit. No source files were modified while producing this
document. Findings are organized by module; each finding is rated
**Critical / Moderate / Minor** and includes root cause, not just symptom.

---

## Flagged For Fix — Priority List

Running list of every **Critical** finding across all audited modules, in
module order. No fixes are proposed here or anywhere in this document — this
is a triage index only. Entries are never reordered or removed as modules are
added; a finding that is later disproved is struck through in place rather
than deleted, so the list stays a faithful record.

### Module 1 — Ingestion

| # | File | One-line | Full entry |
|---|---|---|---|
| C1 | `sentinel2.py` | Cloud masking relies solely on QA60, which is zero-filled for newer S2 processing baselines — clouds can enter the composite unmasked while SCL-based quality stats report normally. | `## Ingestion Module` → `ingestion/sentinel2.py` |
| C2 | `tiler.py` | No post-download validation of the exported GeoTIFF — a silently truncated/resampled export changes ground sample distance with nothing downstream aware. | `## Ingestion Module` → `ingestion/tiler.py` |
| C3 | `tiler.py` | Training-path band-count mismatch is a printed warning, not a failure — can silently corrupt training `.npy` tiles. | `## Ingestion Module` → `ingestion/tiler.py` |
| C4 | `tiler.py` | RGB band order assumed, never verified at runtime — if it drifts, R/G/B are silently swapped into both SAM and the classifier. | `## Ingestion Module` → `ingestion/tiler.py` |
| ~~C5~~ | ~~`tiler.py`~~ | ~~Train/inference contrast-stretch distribution mismatch.~~ **REFUTED** — training used the same stretched-PNG path as inference. Surviving issue is docstring drift only (Minor). | `## Training Notebook Search` → §5 |
| C6 | `osm_dem.py` | `get_osm_features()` returns `None` for both "confirmed zero roads" and "Overpass failed" — downstream cannot distinguish them. | `## Ingestion Module` → `ingestion/osm_dem.py` |
| C7 | `osm_dem.py` | Road/waterway distance maps normalized to each AOI's own max, not a physical unit — `ROAD_PROXIMITY_PENALTY_STRENGTH` has no stable real-world meaning. | `## Ingestion Module` → `ingestion/osm_dem.py` |
| C8 | `vulnerability_sources.py` | INFORM vulnerability/coping scores never validated as numeric or in-range before being returned as `status: "available"`. | `## Ingestion Module` → `ingestion/vulnerability_sources.py` |

### Module 2 — Classification

| # | File | One-line | Full entry |
|---|---|---|---|
| C9 | `segmentation.py` + `inference.py` | `segment_id` is a positional index into an area-sorted list, and post-Phase-2 `result.json` and `masks.json` use **different** id counters — measured 24/36 segments (67%) mis-joined on a real run. Silently corrupts any future annotation or CAAT recalibration. | `## Classification Module` → C9 |
| C10 | `inference.py` + `caat_thresholds.json` | Deployed CAAT thresholds carry no `source_checkpoint` and, per their own caveat, come from 11 LOCO fold models — **not** the production checkpoint. The provenance check that would catch this exists only in dead code (`resnet_classifier.py`) and never runs. | `## Classification Module` → C10 |
| C11 | `inference.py` + `recalibrate_caat.py` | Road/waterway proximity penalties are applied to probabilities *before* the CAAT comparison, but thresholds were calibrated on **unpenalized** probabilities — one-way, systematic over-rejection of `paved_road`/`standing_water`. | `## Classification Module` → C11 |
| C12 | `recalibrate_caat.py` | CAAT calibrates on correctly-predicted pixels only — a pure recall criterion with no precision term — so it is structurally incapable of suppressing confident misclassification. | `## Classification Module` → C12 |

### Module 3 — Orchestration

| # | File | One-line | Full entry |
|---|---|---|---|
| C13 | `pipeline.py` | `primary_tile` points at a single 512px tile while `tile_dimensions`, `landcover.png` and all segment bboxes are full-raster — verified on a real 4-tile run, making multi-tile AOIs spatially unrenderable with no error anywhere. | `## Orchestration Module` → C13 |
| C14 | `pipeline.py` | `applicability` is computed but gates nothing — an `out_of_distribution` landcover verdict still flows into hydrological surfaces, all five susceptibility layers, exposure and risk, each emitted with its own confident `status`. | `## Orchestration Module` → C14 |
| C15 | `pipeline.py` | `osm_available` is latched before the road distance map is built, so `result.json` can claim `road_access_scores_reliable: true` and `road_score_method: "distance_transform"` while every score is the −1.0 "unavailable" sentinel and the road-proximity penalty was silently skipped. | `## Orchestration Module` → C15 |
| C16 | `api.py` | `aoi_label` is unvalidated and becomes a filesystem path component in `run_pipeline`, giving unauthenticated directory-creation and file-write outside the data root via `../` traversal. | `## Orchestration Module` → C16 |
| C17 | `api.py` | `get_latest_run` sorts a prefix match lexicographically, so `/api/demo` permanently serves `dharavi_test_20260806_114208`; no future scheduler run can ever sort above it. The 5-day auto-refresh is inert from the consumer's view. | `## Orchestration Module` → C17 |
| C18 | `api.py` | `run_pipeline` signals failure in-band (`return {"status": "failed"}`) while the scheduler detects failure out-of-band (`except`), so a failed refresh prints "refreshed OK" and leaves an empty run directory. | `## Orchestration Module` → C18 |

### Module 4 — Downstream Analysis

| # | File | One-line | Full entry |
|---|---|---|---|
| C19 | `perception/hydrological_surfaces.py` | `impervious_fraction_pct` is deflated in direct proportion to the unknown rate (the function never receives `unknown_pct`), so the AOIs with worst classification read as *more permeable* i.e. less flood-prone. Its `limitations` list details three second-order caveats and omits this first-order one. | `## Downstream Analysis Module` → C19 |
| C20 | `perception/applicability.py` | The `urban_landcover_model: out_of_distribution` verdict never cross-references the sibling mechanisms in its own returned dict, so `pluvial: applicable` and `waterlogging: applicable` are emitted alongside it despite both depending on the landcover output just declared unreliable. | `## Downstream Analysis Module` → C20 |
| C21 | `applicability.py` + `susceptibility/waterlogging.py` | The impervious "availability" guard (`impervious_fraction_pct is not None`) is vacuous — `compute_hydrological_surfaces` has no failure path and always returns a float, so a total landcover failure scores as `0.0` = confirmed permeable. Duplicated at applicability.py:133 and waterlogging.py:57, failing open twice in one chain. | `## Downstream Analysis Module` → C21 |
| C22 | `susceptibility/pluvial.py` | `infiltration_deficit_px = 1.0 - infiltration_px` assigns the **maximum** deficit to every class not explicitly weighted — including `active_construction`, `standing_water`, and `UNKNOWN_INDEX` — so no-data pixels render as maximum susceptibility in the system's only per-pixel spatial product. | `## Downstream Analysis Module` → C22 |
| C23 | `exposure/compute.py` | `product_validation_status` (the Gate C waiver marker) is omitted from the `not_calculated` return path, so any layer whose susceptibility is unavailable — e.g. coastal for an inland AOI, a routine case — produces exposure output with no waiver marker at all. | `## Downstream Analysis Module` → C23 |
| C24 | `geowatch-ui/src/App.jsx` | The frontend never reads `product_validation_status` (0 occurrences), so exposure is surfaced to users with no "screening/experimental" label — the exact outcome PROJECT_GATES.md's waiver text was written to prevent. The susceptibility panel *does* carry such a marker, so the discipline exists in the same file and was not applied here. | `## Downstream Analysis Module` → C24 |
| C25 | `zonal/landcover_screening.py` | A ward whose pixels are all UNKNOWN yields `category_area_pct = {}` → `impervious_fraction_pct = 0.0` → a fully-computed waterlogging score. Not hypothetical: the only reusable run on disk is 55.1% unknown. | `## Downstream Analysis Module` → C25 |
| C26 | `zonal/landcover_screening.py` | No per-ward unknown fraction, valid-pixel count, or coverage flag is emitted anywhere, so a ward at 5% classified is schema-identical to one at 95%. This is the field that would make C25 detectable. | `## Downstream Analysis Module` → C26 |
| C27 | `zonal/hazard_screening.py` | A 90s GEE timeout and genuine data absence are indistinguishable in output (the `error` string is dropped at the ward-block boundary), making ward hazard tiers **non-reproducible** — two real runs of the same 24 wards on disk disagree on fluvial, coastal, and flash_flood tiers. | `## Downstream Analysis Module` → C27 |

### Module 5 — Training / Annotation Tooling *(partial coverage — see module note)*

| # | File | One-line | Full entry |
|---|---|---|---|
| C28 | `annotate.py` | The annotation tool joins `masks.json` to `result.json` **by `segment_id`** to embed `mask_rle` into each annotation record — so on any post-Phase-2 run it would bake the C9 mis-join permanently into `annotations.json`, pairing one segment's bbox with another segment's mask. | `## Training/Annotation Module` → C28 |
| C29 | `generate_osm_road_masks.py` | At 10m GSD every road class except `motorway` is **sub-pixel wide** (residential 5m = 0.50px, service 4m = 0.40px, primary 9m = 0.90px). Every `paved_road` training pixel derived from these masks is therefore spectrally mixed by construction — majority not-road. No loss function can separate classes whose training pixels are physically half the other class. | `## Training/Annotation Module` → C29 |
| C30 | `verify_masks.py` | The one tool that could detect C9 checks only that segment ids **exist** in masks.json (set membership), never that they refer to the same geometry — and its on-disk report covers 47 runs whose newest is `nusantara_20260702_165811`, i.e. **zero post-Phase-2 runs**. It also marks all 12 count-divergent runs `ok: true`. | `## Training/Annotation Module` → C30 |

### Module 6 — Frontend

| # | File | One-line | Full entry |
|---|---|---|---|
| C31 | `App.jsx` + `inference.py` | `CAT_COLORS` has drifted from `CATEGORY_COLORS_RGB` on **all 8 categories (0/8 exact matches)**, despite `inference.py`'s comment asserting they "must match ... exactly, so the frontend legend and the PNG overlay agree visually." The server-rendered map overlay and the legend swatch beside it are different colors for every class. | `## Frontend Module` → C31 |
| C32 | `App.jsx` | `applicability` is **never read as a data field** — the sole textual occurrence is an unrelated `intersection_type` string comparison. The `out_of_distribution` verdict therefore never reaches a user, in the one surface where it would matter most. | `## Frontend Module` → C32 |
| C33 | `App.jsx:331, 340-347` | The land-cover legend iterates the **hardcoded frontend palette**, not `result.landcover.categories`, so it always renders 3 OSM-only categories the model cannot produce; and `{pct ? fmtPct(pct) : '0.0%'}` renders *absent* and *measured-zero* identically as "0.0%". | `## Frontend Module` → C33 |

### Re-assessments of earlier Criticals (from Module 3's integration view)

Recorded here rather than by editing the original module sections, so each
module's findings stay as they were written.

| # | Change | Detail |
|---|---|---|
| C1 | **Amplified** | `compute_applicability()` takes no `observation_quality` argument (signature verified), so in `run_pipeline` the cloud/shadow metrics are recorded into `result.json` and gate **nothing**. A QA60 mask failure therefore has no downstream tripwire in the main path. Partial mitigation: `zonal/landcover_screening.py:231-235` *does* gate on `valid_observation_pct`, but only in the ward-screening path. |
| C2 | **Amplified** | `api.py:47` sets `MAX_AOI_AREA_KM2 = 100.0`, admitting AOIs **20× larger** than `tiler.py::export_image_local`'s documented "< 5 sq km" safe range. Since C2 means nothing validates the exported GeoTIFF afterwards, a silent downsample/truncation at that size changes effective ground sample distance undetected. |
| C3 | **Scope narrowed** | Confirmed **not in the live path**: `pipeline.py` imports only `generate_rgb_preview_tiles`, never `generate_tiles`. C3 remains a real training-data-corruption risk but can only fire if the training-tile path is re-run (e.g. via `retile_all_cities_6band.py`). |
| C6 | **Amplified** | The conflated `roads_gdf is None` boolean is promoted into `result.json` as an explicit reliability *claim* (`osm_available`, `road_access_scores_reliable`, `road_score_method`) — see C15. A consumer is actively told to trust scores that may all be sentinels. |
| C7 | **Confirmed and pinned** | `pipeline.py:220-237` builds the distance map **once against the full-AOI raster** and slices it per tile, so the normalization divisor is the AOI-wide max exactly as C7 predicted. The penalty's effective strength is therefore set by the AOI the user happens to draw. |
| C8 | **Still latent, slightly widened** | Verified `risk/compute.py` never reads `raw_score` numerically — it gates only on `status`. So no arithmetic touches an unvalidated INFORM cell. But an invalid cell still yields `status: "available"`, which flips `vulnerability_available: True` in every per-layer risk block. |
| C9 | **Mechanism located** | `pipeline.py:332-361` is where the id divergence is created: segment ids come from a counter over *surviving* segments while mask ids come from a separate counter over *all* masks. |
| C10, C11 | **Confirmed** | `pipeline.py:260` calls `load_caat_thresholds` — the weaker validator that never checks `source_checkpoint`. The stricter one remains unreachable. |

### Re-assessments from Module 4's downstream view

| # | Change | Detail |
|---|---|---|
| C14 | **Worsened** | Module 3 found applicability gates nothing *downstream*. Module 4 shows it does not even gate *itself*: C20 — the OOD verdict and `pluvial: applicable` are emitted from the same function call. And `zonal/landcover_screening.py`, the one consumer that honours applicability, is the same module carrying C25/C26. |
| Module 2 total-px denominator | **Concrete victim identified** | The `category_area_pct` total-pixel denominator (flagged in Modules 2/3 as a semantics inconsistency) now has a confirmed downstream casualty: C19. The bias direction is toward under-reporting imperviousness in high-unknown AOIs. |
| C18 | **Recurs at a second boundary** | The in-band/out-of-band error mismatch reappears at `zonal/landcover_screening.py:325-339`: a `{"status": "failed"}` pipeline return is misattributed to an imagery-quality gate failure. It fails *closed* (correct outcome) but reports the wrong cause. |
| C8 | **Re-confirmed independently** | `risk/compute.py` touches `vulnerability` only via `.get("status")`; no arithmetic reaches `raw_score`. C8 stays latent. |

---

## Ingestion Module

Scope: `ingestion/gee_client.py`, `ingestion/sentinel2.py`, `ingestion/tiler.py`,
`ingestion/osm_dem.py`, `ingestion/hydrology.py`, `ingestion/coastal.py`,
`ingestion/rainfall.py`, `ingestion/inundation.py`, `ingestion/event_hazard.py`,
`ingestion/exposure_sources.py`, `ingestion/vulnerability_sources.py`.

### Critical findings at a glance

| # | File | Finding |
|---|------|---------|
| 1 | `sentinel2.py` | Cloud mask relies solely on QA60, which is known-unreliable/zero-filled for recent Sentinel-2 processing baselines — cloud-contaminated pixels can enter the composite unmasked while `observation_quality` (computed via a separate, correct SCL path) reports normally. |
| 2 | `tiler.py` | No post-download validation of the exported GeoTIFF — a silently truncated/resampled export changes effective ground sample distance with nothing downstream aware the `scale=10` assumption still holds. |
| 3 | `tiler.py` | `generate_tiles` (training-data path): band-count mismatch is a printed warning only, not an enforced failure — a partial export can silently corrupt training `.npy` tiles. |
| 4 | `tiler.py` | RGB band selection (`RGB_BAND_INDICES`) assumes on-disk band order matches `sentinel2.py`'s `S2_BAND_NAMES` — enforced only by a comment, not verified at runtime; if it ever drifts, R/G/B channels are silently swapped into both SAM and the classifier. |
| 5 | `tiler.py` | The live inference path (`generate_rgb_preview_tiles`) applies an independent per-tile 2nd/98th-percentile contrast stretch + 8-bit quantization; the training-data path (`generate_tiles`) applies none, keeping raw float32. If training patches are sourced from the un-stretched path, the production model is inferenced on a pixel-value distribution structurally different from what it trained on — a plausible root-cause contributor to systematic misclassification between visually/contrast-sensitive categories (e.g. paved road vs. informal roofing). Confirmed within this file; the training-patch-generation half needs tracing elsewhere to fully confirm end-to-end. **— SINCE REFUTED: the training notebook was later located and read; training used the same stretched-PNG path as inference. See "## Training Notebook Search". The surviving issue is docstring drift in `tiler.py`, not a distribution mismatch.** |
| 6 | `osm_dem.py` | `get_osm_features()`'s own docstring claims `None` means "request failed, not that features are absent" — false. A confirmed-zero-roads AOI (very common in informal settlements) and a total Overpass API failure both produce `result["roads"] is None`, indistinguishable downstream. This erases the one signal that would let the road-proximity penalty in `inference.py` reason differently about "confidently no roads here" vs. "we don't know." |
| 7 | `osm_dem.py` | Road/waterway distance maps are normalized by each raster's own max distance (`dist_px.max()`), not a fixed physical unit — `ROAD_PROXIMITY_PENALTY_STRENGTH = 0.3` in `inference.py` therefore has no stable real-world meaning: the same physical distance from a road yields a different penalty depending on AOI size and local road density. This directly undermines the one existing mitigation for the `paved_road`/`dense_informal_roofing` confusion pair. |
| 8 | `vulnerability_sources.py` | INFORM vulnerability/coping-capacity scores are read from Excel and returned as `status: "available"` with no check that the cell is numeric, non-null, or in `[0,10]` — INFORM composite indices commonly use placeholder markers for countries with insufficient data, and the columns that flag this (`PCT_MISSING`/`RELIABILITY`) are read but never used to gate status. Currently bounded (risk fusion isn't wired up yet), but it's a landmine for the first future consumer that does arithmetic on `raw_score`. |

---

### `ingestion/gee_client.py` (25 lines)

**Function-by-function**
- `initialize_gee()` — calls `ee.Initialize(project=os.getenv("GEE_PROJECT_ID"))`, wrapped in try/except that prints and re-raises. Loud failure, correctly implemented.
- `get_map()` — thin wrapper around `geemap.Map`, dev-only, no issues.

**[Minor] No validation that `GEE_PROJECT_ID` is actually set** (gee_client.py:14)
- What happens: `os.getenv("GEE_PROJECT_ID")` silently returns `None` if the env var is missing; `ee.Initialize(project=None)` is passed through with no explicit check.
- Root cause: No guard clause distinguishing "intentionally use default project" from "env var was never configured."
- Downstream propagation risk: Low — `ee.Initialize` will likely raise its own (less clear) error if a project is required and absent, so this fails loudly, just with a possibly-confusing message.

---

### `ingestion/sentinel2.py` (196 lines)

**Function-by-function**
- `mask_s2_clouds(image)` — masks using QA60 opaque-cloud (bit 10) + cirrus (bit 11) bits only, then `divide(10000)` and `.select(S2_BANDS, S2_BAND_NAMES)` to rename bands. Docstring correctly states it does *not* handle shadow.
- `get_sentinel2_collection(...)` — filters `COPERNICUS/S2_SR_HARMONIZED` by bounds/date/`CLOUDY_PIXEL_PERCENTAGE`, returns the **raw** (unmasked) collection, blocking on `.getInfo()` to print a count.
- `compute_observation_quality(collection, aoi)` — for each SCL code-group (valid/cloud/shadow/nodata), builds a per-pixel boolean mask image averaged across the whole collection, then `reduceRegion(mean)` over the AOI at scale=10, four separate `.getInfo()` round-trips.
- `get_sentinel2_median_composite(...)` — orchestrates the above, raises `ValueError` on zero images (good, loud), then `masked_collection.median().clip(aoi)`.
- `get_best_image` — deprecated passthrough, fine.
- `get_latest_image` — computes a 90-day lookback window and delegates.
- `aoi_from_bbox` / `aoi_from_coords` — thin `ee.Geometry` constructors, zero input validation.

**[Critical — data-dependent] Cloud mask relies solely on QA60, which is known-unreliable for recent Sentinel-2 processing baselines** (sentinel2.py:31-46)
- What happens: `mask_s2_clouds` only inspects QA60 bits 10/11. ESA has deprecated/zero-filled QA60 for scenes processed under newer baselines (post ~2022), meaning for a non-trivial fraction of imagery this band can be entirely 0 → `bitwiseAnd(...).eq(0)` is always true → the mask never rejects anything.
- Root cause: The masking function was never updated to use SCL (which the code already computes correctly, just in the separate `compute_observation_quality` path) as the actual masking source — QA60 and SCL are two independent code paths that were not kept in sync.
- Downstream propagation risk: Real and severe if triggered — cloud/haze-contaminated pixels enter the median composite unmasked, while `observation_quality.cloud_pct` (computed correctly via SCL) reports a normal-looking value, so nothing in the output signals the mismatch. Confirmed from code structure; whether it actually triggers depends on the processing baseline of the specific imagery pulled at runtime.

**[Moderate] Cloud shadow is measured but never filtered from the actual image** (sentinel2.py:35-38, 70-115)
- What happens: `compute_observation_quality` reports `cloud_shadow_pct`, but no function in this file removes shadow pixels from the composite that actually gets classified.
- Root cause: Intentional per the docstring ("shadow detection now happens separately"), but the consequence — shadow pixels darken the composite and are never excluded, only reported — is never acted on anywhere downstream (confirmed: `applicability.py`'s inputs don't include `observation_quality` at all).
- Downstream propagation risk: A heavily-shadowed AOI produces a systematically darkened composite feeding the classifier, with the shadow% number sitting inertly in result.json.

**[Moderate] `CLOUDY_PIXEL_PERCENTAGE` filter is scene-level, not AOI-level** (sentinel2.py:64)
- What happens: The threshold filters on each source scene's whole-tile cloud metadata, not cloud cover actually inside the requested AOI.
- Root cause: Using the cheap, pre-computed metadata field instead of an AOI-local computation (which would require the same expensive reduceRegion pattern used in `compute_observation_quality`).
- Downstream propagation risk: A scene with low whole-tile cloud% but a fully-clouded AOI corner would pass the filter; `compute_observation_quality`'s AOI-local stats would catch this, but only informationally.

**[Moderate] Silent None→0 coercion masks a failed quality computation** (sentinel2.py:88, 99-102)
- What happens: `result.get("mask")` can be `None` if `reduceRegion` returns no data for that geometry/band; `(valid_frac or 0)` turns that into a reported 0%, indistinguishable from a genuine "this AOI is 0% valid."
- Root cause: The `or 0` idiom used for convenience doesn't distinguish "computation failed" from "computation succeeded and the answer is zero."
- Downstream propagation risk: The four percentages (valid/cloud/shadow/nodata) are never cross-checked to sum to ~100%; a partial reduceRegion failure would produce a self-inconsistent but structurally valid-looking quality block with no error surfaced.

**[Moderate–Critical, input-dependent] No coordinate validation in `aoi_from_bbox`/`aoi_from_coords`** (sentinel2.py:184-197)
- What happens: `ee.Geometry.Rectangle([west, south, east, north])` is constructed with no check that `west < east`, `south < north`, or that values are in valid lon/lat range.
- Root cause: Validation was never added at the one place all AOI geometry construction funnels through; callers (`pipeline.py::run_pipeline`) pass raw user/API input straight through.
- Downstream propagation risk: A swapped or malformed bbox produces a degenerate/wrapped EE geometry with no exception at the source — this single geometry then drives tiling, OSM feature fetch, and every lon/lat↔pixel conversion downstream (`osm_dem.py`, `inference.py`'s proximity maps), so the failure mode is a silently-wrong AOI propagating through the entire pipeline rather than a clear early error.

**[Minor] Redundant `.getInfo()` call** (sentinel2.py:133 vs. sentinel2.py:66)
- What happens: `get_sentinel2_median_composite` re-fetches `collection.size().getInfo()` even though `get_sentinel2_collection` already computed and printed the same count.
- Root cause: Copy-paste / refactor residue, not a logic bug — just an extra blocking GEE round-trip.
- Downstream propagation risk: None (performance only).

**[Minor] Local `import datetime` shadows the module-level class import for the whole function scope** (sentinel2.py:177)
- What happens: File imports `from datetime import datetime` at module level; `get_latest_image` locally does `import datetime` (the module), which — per Python scoping rules — makes `datetime` a local name for the *entire* function body, not just from that line onward.
- Root cause: Mixing a module-level `from X import Y` with a function-local `import X` of the same name.
- Downstream propagation risk: None currently (the local import is the first statement executed), but it's a latent footgun — any future edit adding code before that import line referencing the outer class would raise `UnboundLocalError`.

---

### `ingestion/tiler.py` (231 lines)

**Function-by-function**
- `export_image_to_drive` — starts an async GEE export task to Drive, `maxPixels=1e9` fixed, returns immediately after `task.start()`.
- `export_image_local` — downloads via `geemap.ee_export_image(..., file_per_band=False)` to local GeoTIFF; docstring caveats "< 5 sq km" but nothing enforces it.
- `generate_tiles` — the documented **training-data** path: reads a multi-band GeoTIFF via rasterio, splits into `tile_size` chunks (edge tiles clamped, non-square), saves each as float32 `.npy`, channel-last, **no** stretch/quantization.
- `generate_rgb_preview_tiles` — the path actually used by `pipeline.py`: same tiling loop, but extracts R/G/B via `RGB_BAND_INDICES`, applies a 2nd/98th-percentile contrast stretch, quantizes to 8-bit PNG, and returns per-tile pixel offsets plus full-raster `raster_info` (width/height/bounds/CRS).

**[Minor] `export_image_to_drive` is fire-and-forget** (tiler.py:39-52)
- What happens: `task.start()` returns immediately; nothing polls task status or surfaces failure (including exceeding the fixed `maxPixels=1e9`).
- Root cause: No polling/callback wired up — treated purely as a manual dev utility.
- Downstream propagation risk: None in the live pipeline — this function isn't called by `pipeline.py` (which uses `export_image_local`), so it appears to be dead/dev-only code.

**[Critical, data-dependent] No post-download validation of the exported GeoTIFF** (tiler.py:74-84)
- What happens: `export_image_local` trusts `geemap.ee_export_image` to have produced a correctly-sized, correctly-banded file; nothing checks resulting dimensions, band count, or CRS against what was requested before that file is handed to the tilers.
- Root cause: The size caveat in the docstring ("< 5 sq km") is advisory-only, not code-enforced, and `geemap.ee_export_image` is known to silently downsample or produce partial output for AOIs that exceed internal pixel limits, rather than always raising.
- Downstream propagation risk: A silently truncated/resampled export would flow straight into `generate_rgb_preview_tiles`, changing the effective ground sample distance without anyone downstream (SAM, the classifier, OSM pixel-offset math) knowing the assumption `scale=10` still holds.

**[Minor] `os.makedirs(os.path.dirname(output_path), exist_ok=True)` breaks on a bare filename** (tiler.py:75)
- What happens: If `output_path` has no directory component, `os.path.dirname()` returns `""`, and `os.makedirs("", exist_ok=True)` raises `FileNotFoundError`.
- Root cause: No guard for the empty-dirname case.
- Downstream propagation risk: None currently — all real callers (`pipeline.py`) pass full paths under `run_dir`.

**[Critical, scope: training path only] Band-count mismatch is a warning, not a failure** (tiler.py:121-126)
- What happens: `generate_tiles` prints a WARNING if the source GeoTIFF has fewer bands than expected, then proceeds to save `.npy` tiles anyway with whatever bands are actually present — no metadata recording the real band count/order is attached to the saved file.
- Root cause: The check exists but has no enforcement action attached to it.
- Downstream propagation risk: Per this function's own docstring it is "the TRAINING data path." If ever re-invoked to build/extend training data, a partial export (e.g., an accidental RGB-only download) would silently produce mismatched-shape or wrong-channel `.npy` tiles with zero detectability at training time — a training-set corruption risk, though this function does not appear to be called from the live `run_pipeline`.

**[Critical] RGB band selection assumes on-disk band order matches `BAND_NAMES`, unverified at runtime** (tiler.py:10-13, 199-209)
- What happens: `RGB_BAND_INDICES` picks fixed array indices (2/1/0) out of `tile_data` assuming the GeoTIFF's band order exactly matches `["Blue","Green","Red","NIR","SWIR1","SWIR2"]`. This is enforced only by a top-of-file comment, not checked against the file's actual band descriptions/order.
- Root cause: The contract between `sentinel2.py`'s `.select(S2_BANDS, S2_BAND_NAMES)` (which does guarantee this order) and `tiler.py` is entirely implicit and cross-file; nothing in this file re-verifies it.
- Downstream propagation risk: If the exported image ever deviates from that exact band selection (different code path, raw export, reordering), R/G/B channels get silently swapped/misassigned with no error — and this exact array is what's read as "RGB" into both SAM segmentation and the production classifier.

**[Critical — high relevance to classification-quality investigations] Per-tile, independently-computed contrast stretch is the only normalization inference imagery receives, and it differs structurally from the training-tile path** (tiler.py:211-215)
- What happens: For every tile, `p2, p98 = np.percentile(rgb, (2, 98))` is computed from that tile's own pixel values alone, then used to rescale to 0-255. This means the same real-world reflectance value gets stretched differently tile-to-tile (and run-to-run, since it depends on exactly what's inside each tile's crop) — no shared/global reference stretch. This PNG (`/255`-normalized) is exactly what `ingestion/inference.py::run_inference` reads as model input. By contrast, `generate_tiles` — labeled in its own docstring as "the TRAINING data path" — deliberately performs **no** contrast stretch and no 8-bit quantization, keeping raw float32 reflectance instead.
- Root cause: Two separate tiling functions exist for two different purposes (visual QA/frontend vs. training), but the pipeline uses the visual-QA one (`generate_rgb_preview_tiles`) to feed the live classifier, while training data (per that function's own docstring) is built from the other, differently-normalized path.
- Downstream propagation risk: If confirmed against the actual training-patch generation code (not in this file — needs tracing further, e.g. wherever `GeoWatchDatasetResNet`/`build_sam_patches` sources its patches from), this would mean the model is run at inference time on imagery with a fundamentally different pixel-value distribution than what it was trained on — a plausible root-cause contributor to systematic misclassification between visually-similar, brightness/contrast-sensitive categories (e.g., paved road vs. informal roofing). Flagged here as **confirmed within this file**; the training-side half of the comparison needs verification elsewhere before treating this as fully confirmed end-to-end.

**[Moderate] Degenerate/flat/all-nodata tile falls back to an incorrectly-scaled black PNG with no flag** (tiler.py:211-215)
- What happens: When `p98 <= p2` (a perfectly flat tile — most plausibly an all-nodata tile from cloud-masking or an AOI-edge tile with mostly-empty pixels), the code does `np.clip(rgb, 0, 255).astype(np.uint8)` directly on values that are still small reflectance floats (roughly 0–1, not 0–255). This produces an essentially all-black PNG rather than any sensible fallback.
- Root cause: The `else` branch assumes `rgb` is already close to the 0-255 range; it isn't — it's still raw reflectance at that point in the flat-tile case.
- Downstream propagation risk: A fully-black, invalid tile is saved with no marker distinguishing it from a genuinely valid dark scene; it then proceeds through SAM segmentation and the classifier like any normal tile, with no per-tile validity flag surfacing in `result.json`.

**[Minor] Percentile stretch computed on flattened R+G+B combined, not per-channel** (tiler.py:211)
- What happens: `np.percentile(rgb, (2, 98))` operates on the whole 3-channel array at once (implicit flatten), so a single shared min/max is applied to all three channels rather than independently stretching each.
- Root cause: Likely a deliberate choice to preserve color balance (avoids a color-cast tint that independent per-channel stretching can introduce), but it's undocumented as an intentional decision versus an oversight.
- Downstream propagation risk: Low on its own, but compounds with the per-tile-independent stretch finding above — every tile's color balance is being computed from a different combined-channel range.

---

### `ingestion/osm_dem.py` (718 lines)

Fetches OSM vector features (roads/waterways), computes elevation stats and a
relative-elevation proxy, builds road/waterway distance-transform maps
consumed by `inference.py`'s confidence-penalty logic, computes per-segment
road-access scores, and overrides "unknown"/OSM-only-category segments via
OSM vector proximity. This module is the most directly implicated in the
`paved_road` vs. `dense_informal_roofing` confusion the user is investigating.

**[Critical] `get_osm_features()` docstring's core safety claim is false — "no roads found" and "API totally failed" produce identical output** (osm_dem.py:20-23, 107-125)
- What happens: The docstring states "`None` means the request failed, not that features are absent." But `result["roads"]` is only set to a GeoDataFrame inside `if roads:` (line 107). If the Overpass query *succeeds* but returns zero `highway`-tagged elements (a completely legitimate outcome — many informal-settlement AOIs genuinely have no mapped roads), execution falls into the `else` branch (line 113-114), which only prints "No roads found in AOI" and leaves `result["roads"]` at its initialized value of `None` (line 29). This is byte-for-byte the same value produced when all Overpass endpoints fail (line 77-80).
- Root cause: `result` is pre-initialized with `None` as the "nothing here" sentinel and never distinguishes "confirmed empty" from "unknown/failed" — the code that would make that distinction (e.g. an empty GeoDataFrame vs `None`) was never written, despite the docstring asserting it exists.
- Downstream propagation risk: Every consumer (`compute_road_distance_map`, `compute_road_access_score`, `apply_osm_vector_labels`, and — via `pipeline.py` — the `ROAD_PROXIMITY_PENALTY` in `inference.py`) treats `roads_gdf is None` as a single "unavailable" case: `road_access_score` returns `-1.0`, the distance-based confidence penalty is skipped entirely. This means an AOI with a confirmed absence of mapped roads (informal settlements are exactly this case) is scored identically to a transient Overpass outage — there's no way, from `result.json` or the code, to tell an operator "we confidently checked and there are no OSM roads here" apart from "we don't know." That ambiguity sits directly upstream of the roofing/road confusion investigation, since it erases the one signal (confirmed-zero vs. unknown road coverage) that would let downstream logic reason differently about the two cases.

**[Critical] Road/waterway distance maps are normalized against each raster's own max distance, not a physical unit — the "penalty strength" constant in inference.py has no stable real-world meaning** (osm_dem.py:435-442, 498-501)
- What happens: `compute_road_distance_map` and `compute_waterway_distance_map` compute a pixel distance transform (`distance_transform_edt`), then divide by `dist_px.max()` — the single farthest pixel *within that specific raster*. The docstring frames this as "0 = on a road, 1 = maximally far," which is true only in a relative, per-run sense.
- Root cause: There is no conversion to a fixed physical unit (e.g., meters) and no fixed reference "far" distance. `max_dist` is a function of AOI size and where the sparsest road happens to sit in that particular request. `pipeline.py` builds this map once per full-AOI raster (not per-tile), so the AOI a user draws directly determines the normalization scale.
- Downstream propagation risk: `inference.py`'s `ROAD_PROXIMITY_PENALTY_STRENGTH = 0.3` is applied to this normalized value as `penalty = 1 - 0.3*road_dist_map`. Because the map's scale is AOI-size- and road-density-dependent, the *same physical distance from a road* (say, 80m) produces a different penalty in a small tightly-cropped AOI than in a large one, or in a road-dense city (Cape Town) vs. a road-sparse informal settlement (Dharavi). This directly undermines the one existing mitigation for the `paved_road`/`dense_informal_roofing` confusion pair — its effective strength is essentially arbitrary and uncalibrated per-run, which is consistent with `check_confusion_pair.py`'s finding that this pair's confusion mass differs across pooled cities without an explained mechanism.

**[Moderate] `UNPAVED_HIGHWAY_TYPES` mislabels genuinely paved road types as `unpaved_dirt_road`, and the `surface` tag it claims to check was never captured** (osm_dem.py:598-599, 640-644 vs. `get_osm_features`:95-100)
- What happens: The `apply_osm_vector_labels` docstring says unpaved classification includes "service (unpaved surface tag)" — implying a `surface=unpaved/dirt` tag check gates the `service` (and by extension similar) highway types. No such check exists: `UNPAVED_HIGHWAY_TYPES` membership alone decides the override (line 649), and `get_osm_features` never stores a `surface` tag on road records at all (only `geometry`, `highway`, `name` are kept). `highway=unclassified` and `highway=service` are OSM road *classification* tags, not surface tags, and very commonly refer to paved minor streets, alleys, or driveways in dense urban/informal areas.
- Root cause: The function conflates OSM's functional road-class taxonomy with physical surface material, and the docstring describes a filter (`surface` tag) that was designed but never implemented/wired to actual tag capture.
- Downstream propagation risk: A confidently-paved alley or minor street tagged `highway=service`/`unclassified` in OSM, if it lands on a segment still labeled `unknown` (or already OSM-tagged), gets force-relabeled `unpaved_dirt_road` with `label_source="osm_vector"` — a confident-looking, provenance-tagged label that is simply wrong for a meaningful subset of real paved streets. This doesn't directly touch already-confident `paved_road`/`dense_informal_roofing` ML calls (OVERRIDABLE only includes `unknown` and the 3 OSM-only categories), so it's bounded rather than the root cause of the primary confusion pair, but it is a second, independent path for road/surface mislabeling in the same data.

**[Moderate] OSM geometry-intersection failures are caught, logged to stdout, and silently dropped — no visibility on the segment or in the returned data** (osm_dem.py:677-686, 691-700, 711-716)
- What happens: All three `.intersects()` checks in `apply_osm_vector_labels` are wrapped in broad `except Exception as e: print(...)` blocks. On failure (e.g., a degenerate/self-intersecting OSM way — a known real-world occurrence in Overpass exports), the loop just falls through to the next check or leaves the segment unmodified. No field like `osm_check_error` is ever set on the segment, no failure count is tallied or returned, and stdout prints are easily lost in a batch/production run.
- Root cause: Exception handling here is used purely to prevent a crash, not to record or propagate the fact that a specific segment's OSM evidence was inconclusive due to an error rather than a genuine absence of nearby features.
- Downstream propagation risk: A segment whose OSM check silently errored is functionally indistinguishable in `result.json` from a segment that was correctly checked and found to have no nearby OSM feature — both simply keep their prior label. This is a textbook "malformed input degrades to a plausible-looking answer instead of failing loudly" case.

**[Moderate] `natural=water` polygons are rasterized as boundary-only LineStrings, not filled areas — water body interiors don't register as distance 0** (osm_dem.py:88-105, `get_osm_features`)
- What happens: For every OSM way — including closed ways representing lake/pond polygons (`natural=water`) — the code unconditionally builds a `LineString` from the raw vertex list and stores it as-is. `compute_waterway_distance_map`'s rasterization only draws the vertex-to-vertex boundary edges onto the pixel grid; nothing fills the polygon interior.
- Root cause: `get_osm_features` treats all "waterway-ish" ways uniformly as lines, never checking whether the way is closed and semantically an area (`natural=water`) vs. a genuine linear waterway (`waterway=drain/canal/stream`).
- Downstream propagation risk: For any segment that lands inside a large mapped water body (a real, non-edge-case scenario), the waterway distance map reports a nonzero distance-to-water despite the pixel being water, weakening `WATERWAY_PROXIMITY_PENALTY_STRENGTH`'s intended effect on `standing_water` confidence exactly where it should be strongest. Bounded to water-body interiors; tangential to the roofing/road pair but a real, confirmed defect in the same mechanism family.

**[Minor] Undocumented, arbitrary priority order between unpaved-road and drainage-channel OSM overrides** (osm_dem.py:674-700)
- What happens: For a segment near both an unpaved road and a drainage channel (common — roads run alongside open drains in informal settlements), the unpaved-road check runs first and `continue`s on a match, so the segment is never even evaluated against the drainage check.
- Root cause: No tie-breaking logic or comment justifying why road-proximity should win; it's simply the order the `if` blocks happen to be written in.
- Downstream propagation risk: Low — both are OSM-only categories with no direct bearing on the ML-driven roofing/road confusion, but it's a real, silent, undocumented precedence decision.

**[Minor] `bbox_centroid_lonlat()` is defined but never called** (osm_dem.py:622-628)
- What happens: Dead code — a centroid-based geo conversion helper that no code path in `apply_osm_vector_labels` invokes; all actual checks use `bbox_to_geo_box` (full-bbox-with-buffer intersection) instead.
- Root cause: Likely a leftover from an earlier, centroid-based proximity design that was replaced by the buffered-bbox-intersection approach without removing the superseded helper.
- Downstream propagation risk: None functionally; purely a maintenance/clarity smell.

**[Minor] `compute_road_access_score` returns `0.0` (a valid "far from road" score) instead of a sentinel when the segment bbox is fully outside the distance map** (osm_dem.py:563-564)
- What happens: `if x2 <= x1 or y2 <= y1: return 0.0` — reachable if a segment's bbox lies entirely outside the tile's `dist_map` bounds. `0.0` is a legitimate score value elsewhere in this function (meaning "confidently far from any road"), not an error sentinel like the `-1.0` used elsewhere in the same function for "unavailable."
- Root cause: The out-of-bounds edge case wasn't given its own sentinel; it was treated as equivalent to "definitely far."
- Downstream propagation risk: Low in current practice — `pipeline.py` filters segments to `w>=8, h>=8` before calling this, and bboxes normally originate from within-tile SAM masks, so full out-of-bounds is unlikely in the current call path. Still a latent inconsistency if that invariant ever changes.

**[Minor] Dead/self-documented dead-code path in `compute_relative_elevation_proxy`** (osm_dem.py:265-271)
- What happens: `flow_dir` and `slope` are computed via GEE terrain calls but never used in the returned score — the docstring itself already discloses this explicitly.
- Root cause: Leftover from an earlier (incorrect) HAND implementation that was corrected in place without removing the now-unused computation.
- Downstream propagation risk: None beyond wasted GEE calls/latency.

**Scope note:** No CRS mismatches were found between `apply_osm_vector_labels`'s lon/lat↔pixel conversions and `compute_road_distance_map`'s (they're algebraically consistent), and the Overpass bbox parameter ordering (`s,w,n,e`) is correct. One plausible-but-unconfirmed risk noted for completeness: neither this file nor its callers assert that the AOI bbox passed into `compute_road_distance_map`/`apply_osm_vector_labels` exactly matches the true geographic extent of the GEE-exported raster (`tiler.py` territory, not this file) — any drift there would silently degrade the road mask to zero rasterized pixels (already a handled "return None" path, but for the wrong reason) rather than fail loudly.

---

### `ingestion/hydrology.py` (271 lines)

**Function-by-function**
- `_buffer_aoi` — geodesic buffer of the AOI rectangle by `buffer_km*1000` meters via `ee.Geometry.buffer()`. No issues found.
- `get_merit_hand_context` — pulls `hnd` (Height Above Nearest Drainage) and `upa` (upstream drainage area) bands from `MERIT/Hydro/v1_0_1`. `hnd` stats (mean/min/max) reduced over the raw AOI at `MERIT_HYDRO_SCALE_M`; `upa` max reduced over the *buffered* region (correctly, since upstream connectivity can originate outside the box). `river_connected` = max upstream area ≥ threshold. On any exception, returns a clearly `status: "unavailable"` dict with `error` populated.
- `get_fabdem_elevation_stats` — mosaics the FABDEM ImageCollection, clips to AOI, reduces mean/min/max at scale=30 (matches FABDEM's native ~30m resolution). Reads band as `b1_mean`/`b1_min`/`b1_max`, i.e. assumes the ingested asset's band is literally named `b1`.
- `get_slope_stats` — mosaics Copernicus DEM GLO30, explicitly reprojects to `EPSG:4326` at scale=30 before calling `ee.Terrain.slope()`, with a documented rationale (a `.mosaic()` output lacks a well-defined projection for gradient computation).

**[Moderate] Unverified band-name assumption collapses into a false "unavailable" instead of a real error** (hydrology.py:158-163)
- What happens: if `b1` is not actually the FABDEM asset's band name (not independently confirmed by this codebase — `coastal.py`'s own docstring admits its asset IDs are similarly unverified against a live GEE session), `stats.get("b1_mean")` returns `None`, which triggers the `ValueError` → caught by the broad `except` → the function reports `status: "unavailable"`, indistinguishable from "no FABDEM tile covers this AOI."
- Root cause: no explicit `.bandNames()` assertion or `.rename()` step; trusts an assumed band name silently.
- Downstream propagation risk: `flood_assessment.terrain_context` and `applicability` in `pipeline.py` would report FABDEM as legitimately unavailable for every AOI forever, and nothing distinguishes "asset broken" from "no coverage here" — this could go unnoticed indefinitely since both produce the same schema.

**[Moderate] No coverage/valid-pixel-fraction reported for any AOI-wide statistic in this file** (hydrology.py: all three functions)
- What happens: `hnd_stats`, `upa_stats`, FABDEM stats, and slope stats are all computed via `reduceRegion` over the AOI with no accompanying pixel count or coverage percentage. A mean computed from a handful of valid pixels (e.g., an AOI mostly masked by a data gap/seam) is structurally indistinguishable in the output schema from a mean computed from full, dense coverage.
- Root cause: the `reduceRegion` calls use only `mean`/`minMax`/`max` reducers, never `count()`, and the result dicts have no coverage/confidence field.
- Downstream propagation risk: susceptibility functions (`fluvial.py`, `flash_flood.py`, `waterlogging.py`) consume `mean_hnd_m`, FABDEM elevation, `mean_slope_deg` as trustworthy scalars with no way to discount a statistically thin sample — the single most consequential systemic gap in this file.

**[Minor] No NoData/sentinel-value masking check on elevation extremes** (hydrology.py:153-172)
- What happens: mean/min/max are accepted as-is with no range sanity check (e.g., a DEM nodata sentinel like -9999 or 32767 slipping through unmasked would silently corrupt `mean_elevation_m`).
- Root cause: reduceRegion trusts the source collection's own masking; no defensive validation added on top.
- Downstream propagation risk: feeds `susceptibility/coastal.py`'s `compute_coastal_susceptibility(coastal_context, fabdem_elevation)` — a corrupted mean elevation would silently bias coastal susceptibility class.

**[Minor] Reprojecting to a geographic CRS with a meter-based `scale` uses an equatorial approximation** (hydrology.py:239)
- What happens: Earth Engine's `scale` parameter for `reproject()` is always interpreted in meters and converted to degree-pixel-size assuming an equatorial ellipsoid approximation; it does not compensate per-AOI latitude. For AOIs well off the equator, actual east-west ground sampling distance implied by the reprojected grid diverges slightly from the nominal 30m.
- Root cause: inherent EE `reproject(crs=geographic, scale=meters)` semantics, not something this code corrects for.
- Downstream propagation risk: bounded — likely a small systematic bias in `mean_slope_deg`, feeding `flash_flood` susceptibility; not confirmed to be large enough to flip a class, but unverified.

---

### `ingestion/coastal.py` (168 lines)

**Function-by-function**
- `get_coastline_context` — buffers AOI by `search_radius_km`, merges three shoreline FeatureCollections (mainlands/big_islands/small_islands), pre-checks `filterBounds(buffered).size()`, then computes a masked distance raster via `FeatureCollection.distance(searchRadius, maxError)` and reduces with `min`.

**[Minor / self-documented, not currently live-impacting] `filterBounds()` pre-check over-matches for AOIs far from the coast** (coastal.py:76-77, 96-125)
- What happens: the code's own comments document a confirmed live-run finding (Delhi, far inland) where `nearby_count > 0` even though the true coastline distance vastly exceeds `search_radius_km`.
- Root cause (as diagnosed in-code and plausible on inspection): mainland shoreline features are apparently stored as large polygons per landmass; an AOI's buffered bounding box can geometrically intersect the polygon's interior/extent well before the AOI is anywhere near the actual coastline boundary, so the bbox/geometry pre-filter is not a reliable proxy for proximity.
- Downstream propagation risk: mitigated — the code does NOT rely on `nearby_count` alone; it re-derives the real answer via the masked `distance()` raster and treats `distance_m is None` as the authoritative "far inland" signal. Flagging as Minor because the fallback appears correct, but the `nearby_count==0` early-exit branch is only reachable when the polygon test also returns *zero* candidates — an inverse false-negative case (real coastline nearby but missed by `filterBounds`) is not ruled out and is unverified.

**[Minor] Redundant double `filterBounds` call** (coastal.py:76, 105)
- What happens: `nearby = merged.filterBounds(buffered)` is computed, then `distance_image = merged.filterBounds(buffered).distance(...)` recomputes the identical filter from scratch instead of reusing `nearby`.
- Root cause: leftover from iterative bugfixing (the file's own comments describe a "v3"/"v4" bugfix history); not consolidated afterward.
- Downstream propagation risk: none functionally, only redundant GEE computation cost.

**[Minor] Asset IDs are explicitly unverified against a live GEE session** (coastal.py:16-24, own module docstring)
- What happens: the module docstring states the three shoreline asset IDs were sourced from community-catalog docs, not confirmed live. If wrong, the function fails safely into `status: "unavailable"` via the broad except.
- Root cause: unverified third-party asset naming.
- Downstream propagation risk: low by design (fails visibly as "unavailable"), but see the cross-cutting exception-handling finding below — an unavailable status due to a genuinely broken asset ID is indistinguishable from empty search results in this AOI.

---

### `ingestion/rainfall.py` (59 lines)

**Function-by-function**
- `get_rainfall_climatology` — computes a 10-year lookback window, sums daily CHIRPS precipitation over the AOI, reduces with `mean` at scale=5000 (reasonable given CHIRPS's ~5.5km native resolution), divides by `lookback_years` for a mean-annual figure.

**[Minor] Leap-day date arithmetic can raise on Feb 29** (rainfall.py:17)
- What happens: `date(end.year - lookback_years, end.month, end.day)` — if `end` is Feb 29 of a leap year and `end.year - lookback_years` is not itself a leap year, this raises `ValueError: day is out of range for month`.
- Root cause: naive date subtraction without a leap-day guard.
- Downstream propagation risk: caught by the broad `except Exception`, so it degrades to `status: "unavailable"` rather than crashing — but this means the entire pluvial-susceptibility rainfall input silently disappears for any pipeline run executed on a leap day, with the true cause buried in a stored `error` string rather than surfaced.

**[Moderate — cross-cutting across hydrology.py, coastal.py, rainfall.py] Broad `except Exception` conflates real bugs with genuine data unavailability**
- What happens: every function in all three files wraps its entire body in `try / except Exception as e`, and on ANY exception — a GEE quota error, a network timeout, a wrong band/asset name, a Python `TypeError` from a code typo, the leap-day `ValueError` above — returns the identical `status: "unavailable"` shape with the exception text tucked into an `error` field.
- Root cause: a deliberate uniform "fail visibly but gracefully" pattern (consistent with the project's stated "screening/experimental, never crash the whole pipeline" philosophy), but it does not distinguish exception *classes* — a genuine software bug (e.g. a renamed GEE asset, a typo introduced in a future edit) produces the exact same downstream signature as "this AOI legitimately has no data," and nothing in `pipeline.py`'s consumption of these blocks appears to alert on or surface the `error` string differently.
- Downstream propagation risk: high in aggregate — this pattern is the shared root cause behind several of the individual findings in these three files, and means every `status: "unavailable"` in `flood_assessment`/`susceptibility` blocks downstream should be read as "either genuinely no data, or a broken integration," with no way to tell which from the output alone.

---

### `ingestion/inundation.py` (262 lines)

Provides permanent-water context (JRC Global Surface Water) and Sentinel-1
change detection for observed inundation, feeding `perception/observed_inundation.py`.

**[Moderate] Sentinel-1 composites are not filtered by orbit pass direction or relative orbit** (inundation.py:134-142, `_s1_collection`)
- What happens: `_s1_collection()` filters only by bounds, date, `instrumentMode`, and `transmitterReceiverPolarisation`. It does not filter on `orbitProperties_pass` (ascending/descending) or `relativeOrbitNumber_start`. The pre-event and event `.median()` composites can therefore each be built from a mix of ascending and descending passes with different incidence angles and look directions.
- Root cause: incidence-angle/look-geometry differences between orbit passes shift VV backscatter independent of any real surface change (standard SAR change-detection practice is to control for this). Mixing passes injects noise of a magnitude that can plausibly rival the fixed `S1_VV_DROP_THRESHOLD_DB = -3.0` threshold itself.
- Downstream propagation risk: `probable_new_inundation_pct` can be inflated or suppressed by geometry artifacts rather than real water, with no flag distinguishing this from a genuine detection — presented as "experimental" with no lower confidence for mixed-orbit AOIs.

**[Moderate] `S1_MIN_IMAGES_PER_WINDOW = 1` makes "median composite" a no-op and defeats its own noise-reduction rationale** (inundation.py:171, `configs/inundation_constants.py`:39-42)
- What happens: the guard only requires ≥1 image per window before proceeding to `.median()`. With exactly 1 image, `.median()` returns that single (still-speckled) image unchanged — no despeckling/averaging occurs, despite the code and limitations text implying a "composite."
- Root cause: the constant is set low enough to pass through cases where the stated smoothing benefit of median-compositing cannot exist. Single-image VV backscatter has substantial speckle noise, which at a -3dB threshold is easily large enough to trigger false "drop" flags in speckle-affected pixels.
- Downstream propagation risk: `status: "experimental"` is returned (not `"insufficient_evidence"`) regardless of image count, i.e. maximally noisy input receives the same status label as a run backed by multiple images, with no image-count-based confidence signal exposed downstream.

**[Moderate] S1 diff/drop reduceRegion calls are not `.unmask()`-guarded against partial data gaps** (inundation.py:190-201)
- What happens: unlike `get_permanent_water_context`'s explicit `.unmask(0)` fix (applied to fix a real, previously live-caught bug where JRC's masked `occurrence` band silently shrank the reduceRegion denominator — confirmed by an anomalous Delhi run returning `seasonal_water_pct=99.59%`), `diff` and `drop_mask` here are reduced directly with `ee.Reducer.mean()` with no unmasking. If either composite has masked/null pixels anywhere in the AOI (partial swath coverage, GRD border noise, etc.), those pixels are silently excluded from both the denominator of `mean_diff_db` and `drop_frac`.
- Root cause: same masked-band-vs-reduceRegion-denominator failure mode documented and fixed elsewhere in this very file, not applied here.
- Downstream propagation risk: `probable_new_inundation_pct` could be computed over a shrunk, non-obvious sub-area of the AOI (e.g. only the portion actually swath-covered) while being reported and consumed as an AOI-wide fraction, with nothing in the returned dict indicating a discrepancy.

**[Minor / informational] JRC denominator bug already fixed, noted for context** (inundation.py:73-84)
- What happens: `.unmask(0)` is applied and explicitly commented as a fix for the real bug described above. Current code is correct as written.
- Root cause: not applicable — already remediated. Included only because the pattern (masked-band + unmasked reducer silently shrinking the denominator) is a known repeat failure mode in this codebase and directly explains the finding immediately above.

---

### `ingestion/event_hazard.py` (160 lines)

Provides event-specific rainfall and a discharge proxy, feeding
`susceptibility/event_hazard.py`.

**[Moderate, self-documented by project] Rainfall normalization ceiling not scaled to event-window length** (`configs/event_hazard_constants.py`:9-21, consumed by `susceptibility/event_hazard.py`)
- What happens: `EVENT_RAINFALL_NORMALIZATION_MAX_MM` (800mm) and `DISCHARGE_PROXY_RAINFALL_NORMALIZATION_MAX_MM` (1800mm) are fixed constants regardless of whether `event_start`/`event_end` spans 3 days or 31 days. The comment records that a real monsoon-month run (Dharavi, July 2026) returned 1506.8mm and instantly saturated the (then-800mm) ceiling to 1.0, making the "event conditioning" step a no-op.
- Root cause: normalization is keyed to an assumed single-storm event duration; nothing in `get_event_rainfall()`/`get_discharge_proxy()` computes or passes along the window length in days, so any consumer normalizing against these fixed ceilings cannot adapt to window length even if it wanted to.
- Downstream propagation risk: for short (multi-day) events the ceiling may now be too high (raised specifically to fix the monthly case), understating hazard for genuinely short intense storms; for long windows it may again saturate. This is a live, acknowledged-but-unresolved bug, not merely a historical note — the raised constants are described in the comment itself as still provisional/unvalidated.

**[Moderate] `get_discharge_proxy()`'s buffer is a symmetric radial buffer, not a directional "upstream" catchment, despite docstring framing** (event_hazard.py:91-105)
- What happens: `aoi.buffer(buffer_km * 1000.0)` expands the AOI rectangle uniformly in all directions (upstream, downstream, and lateral alike) by 3km (`DISCHARGE_PROXY_BUFFER_KM`). It also fully contains the original AOI, so the AOI's own local rainfall is included in (not distinguished from) the "catchment" total.
- Root cause: there is no flow-direction/drainage-network input anywhere in this function to determine which side of the AOI is actually "upstream" — a symmetric buffer is used as a stand-in, but the docstring's "upstream of this AOI" framing overstates what a symmetric buffer can represent.
- Downstream propagation risk: `catchment_rainfall_mm` is presented as a discharge-relevant upstream signal, but a storm entirely downstream or lateral of the AOI contributes to this number identically to a storm actually upstream — the value can be systematically uninformative or misleading as a discharge proxy in exactly the directional sense its own docstring claims to approximate.

**[Minor] Discharge proxy buffer size is likely smaller than the native resolution of its own input data for small AOIs** (event_hazard.py:105, 120; `configs/event_hazard_constants.py`:37)
- What happens: `buffer_km=3.0` is applied to AOIs on the order of ~2.5-2.6km per side (per `configs/ingestion.yaml`'s Dharavi test AOI), while IMERG's native grid resolution is ~10-11km and the reduction is run at `scale=10000`. For AOIs this small, the buffered "catchment" geometry is smaller than a single native IMERG pixel.
- Root cause: `buffer_km` was reused from Phase 5's fluvial HAND buffer distance (per the code comment) rather than chosen relative to IMERG's native resolution or an actual watershed scale.
- Downstream propagation risk: `catchment_rainfall_mm` will often be numerically identical or nearly identical to `event_total_mm` for small AOIs at IMERG's coarse resolution, silently defeating the purpose of computing a distinct "catchment context" signal — two supposedly independent outputs collapse to the same underlying data point without any indication in the returned dicts.

**[Minor, positive note] `get_event_rainfall()` is implemented as documented**
- The IMERG rate→accumulation conversion (`sum().multiply(0.5)` for half-hourly mm/hr images) is standard and correctly explained; `status`/`error` handling is consistent with the rest of the project's discipline (explicit failure, no fabricated fallback value). No issues found; noted only as a positive contrast to the discharge-proxy function's overstated framing above.

---

### `ingestion/exposure_sources.py` (361 lines)

Provides population context (WorldPop), builtup reference, OSM road length,
and OSM facilities context, feeding `exposure/compute.py`. Note:
`PROJECT_GATES.md` documents a real, previously-fixed WorldPop scale bug —
population/density scaling logic was scrutinized accordingly.

**[Moderate] Cross-border AOI population undercount not surfaced to output** (exposure_sources.py:38-42, 53-62)
- What happens: `get_population_context()` filters WorldPop to a single country's per-country raster when `country_iso3` is supplied. If the AOI rectangle actually straddles a national border, the neighboring country's population pixels are excluded entirely (WorldPop country products are boundary-clipped), so `exposure/compute.py`'s zonal sum silently covers only the portion of the AOI inside the queried country — with no partial-coverage flag.
- Root cause: the function's `limitations` list (returned to callers/result.json) contains only 3 generic caveats (modeled estimate, 2020 cap, coarse resolution) — the cross-border caveat is discussed in the docstring/comments but was never added to the actual returned `limitations` array, so it never reaches `result.json` or the frontend.
- Downstream propagation risk: `exposure/compute.py` and eventually `risk/compute.py` would report a population figure with `status: "available"` that is quietly partial for any AOI near an international border, with no honesty label attached (contrary to this project's own stated "honest limitation labeling" standard in `PROJECT_GATES.md`).

**[Minor] `population_year` / image selection assumes exactly one image per (country, year)** (exposure_sources.py:89-92)
- What happens: `.filter(ee.Filter.eq("year", latest_year)).first()` silently picks an arbitrary image if WorldPop ever published more than one product per country/year; no count check like the one used for the initial `collection.size()==0` case.
- Root cause: no uniqueness assertion after the year filter, only after the initial bounds/country filter.
- Downstream propagation risk: low — WorldPop's per-country-per-year structure is normally 1:1, but this is asserted nowhere in code, only assumed.

**[Minor] `osm_completeness` is a hardcoded string, not a computed value** (exposure_sources.py:196, 233, 273, 330, 360)
- What happens: every returned dict sets `"osm_completeness": "unknown"` unconditionally — it is a static label, not derived from any actual completeness check.
- Root cause: this is arguably a deliberate, honest placeholder, but the field name reads as if it's a computed signal, which could mislead a future maintainer into treating it as meaningful telemetry rather than a constant.

---

### `ingestion/vulnerability_sources.py` (283 lines)

Resolves country ISO3 for an AOI and fetches INFORM Risk Index vulnerability
context from `data/external/INFORM_Risk_2026_v072.xlsx`, feeding
`risk/compute.py`.

**[Critical] INFORM Risk vulnerability/coping-capacity scores are never validated as numeric or in-range** (vulnerability_sources.py:236-245)
- What happens: `vulnerability_score` and `coping_capacity_score` are read directly from the Excel cells and placed into the returned dict under `"scale": "0-10"` with `"status": "available"`, with no check that the value is actually a number, non-null, or within `[0,10]`. INFORM-style composite indices commonly use placeholder markers (`"x"`, `"-"`, blank) for countries with insufficient underlying indicator data — `INFORM_COL_PCT_MISSING`/`INFORM_COL_RELIABILITY` columns exist specifically to flag this, but their *values* are also passed through unchecked and are not used to gate `status`.
- Root cause: the function assumes any matched row has clean numeric data because the *columns* were live-verified to exist — but column-existence verification (done once, for header names) was conflated with cell-value validation (never done, per-row, every call). The docstring's confidence ("column names... confirmed directly against the real downloaded file") does not extend to a claim about cell contents, but the code behaves as if it does.
- Downstream propagation risk: currently bounded — `risk/compute.py` does not yet read `dimensions.vulnerability.raw_score` numerically (`risk_block.status` is hardcoded `"not_calculated"` in `pipeline.py`, confirming vulnerability isn't fused into risk yet). But the moment a future risk-fusion implementation does arithmetic on `raw_score` for a country whose INFORM cell is `"x"` or blank, it will either crash on a `TypeError` (best case) or, if any silent numeric coercion is added later, corrupt a risk score — with the current code offering no earlier warning of that landmine. Rated Critical because it's a data-integrity gap on a field the module explicitly claims is a validated numeric scale.

**[Moderate] Cross-border AOI ambiguity is documented but has no field to be reported in** (vulnerability_sources.py:63-66 vs. 80-140)
- What happens: the docstring states plainly "This is a real, stated limitation for genuinely cross-border AOIs" — but the function's return schema (`status, iso3, country_name, source, error`) has no `limitations` key at all, unlike every function in the sibling `exposure_sources.py`. The caveat is therefore stated only in a comment a human reading the source might see, never in anything `result.json` or the frontend consumes.
- Root cause: schema inconsistency across the ingestion layer — some fetchers carry a `limitations` list forward; this one's successful-path centroid resolution does not (the early-return branches for missing ISO3/file do have `limitations`).
- Downstream propagation risk: a country lookup for a genuinely cross-border AOI returns `status: "available"` with a single confident ISO3/country_name and no hint that the result is centroid-based and could be wrong for that AOI shape — this then silently selects the *wrong country's* INFORM vulnerability scores for the whole AOI with no flag anywhere in the output.

**[Minor] First-match-wins row selection with no duplicate-ISO3 check** (vulnerability_sources.py:221-225)
- What happens: `for row in ws.iter_rows(...): if row[iso3_col]==iso3: matched_row=row; break` takes the first row matching the ISO3 code and stops. If the INFORM workbook ever contains more than one row for the same ISO3 (e.g. a regional/territory footnote row, or a stale duplicate from a manual edit), the function silently uses whichever comes first with no warning that a duplicate existed.
- Root cause: no uniqueness assertion after the match loop, mirroring the same pattern-class issue as the WorldPop year-filter finding above.
- Downstream propagation risk: low under current file structure (INFORM's real files are one-row-per-country), but nothing in the code enforces or checks this assumption.

**[Minor] Docstring overstates failure behavior as "fails loudly"** (vulnerability_sources.py:150-153 vs. 278-284)
- What happens: the docstring says a structural change to the INFORM file "fails loudly with a real error, not a silent wrong answer." In fact the `except Exception as e` at the bottom catches *everything*, including the deliberately raised `KeyError` for missing columns, and converts it into a normal `status: "unavailable"` return dict (with a `print()` to console) — it never raises/crashes the caller.
- Root cause: "loudly" is used to mean "not silently wrong," which is true (the error message is real and specific, and it does print to stdout), but the wording invites a reader to expect an actual raised exception / hard failure, which does not happen — this is consistent with, not an exception to, this module's overall fail-soft convention.
- Downstream propagation risk: none functionally — a documentation-precision issue, not a behavioral bug.

---

## Training/Inference Consistency Check

Follow-up to the `tiler.py` findings above. Question: does the production
checkpoint (`models/production/geowatch_production_model.pth`) actually
train on data from a different pixel-value pipeline than the one
`ingestion/inference.py` feeds it at inference time?

> **Note — read this before the evidence below.** This section reached the
> wrong conclusion. It was written while the training notebook was believed
> to be unavailable, so the training data source had to be inferred
> indirectly from file timestamps. That inference was **post hoc ergo propter
> hoc**: `retile_all_cities_6band.py` did run (producing raw `.npy` tiles)
> ~14 hours before the checkpoint was saved, but running first is not the
> same as feeding training. The notebook was subsequently located on disk
> and read directly, and it shows training actually loaded a **different,
> PNG-based path** — the `.npy` files were an abandoned 6-band experiment.
>
> The evidence items below are individually accurate as stated (the `.npy`
> files exist, their pixel statistics are raw reflectance, the timestamps
> are real); only the causal chain drawn from them is wrong. They are kept
> intact so the reasoning — and where it went wrong — stays auditable.
> **See "## Training Notebook Search" below for the correct account.**

### Verdict: **REFUTED — later disproved by direct inspection of the training notebook.** This section originally read "CONFIRMED — real train/inference distribution mismatch"; that verdict is retracted. Training and inference in fact share the same PNG-based preprocessing path. See "## Training Notebook Search" below.

### Evidence trail (retained as originally written — see the note above)

**1. No training notebook or dataset class lives in this repo.**
A repo-wide search for `*.ipynb`, `GeoWatchDatasetResNet`, and
`build_sam_patches` found zero notebook files and zero class definitions —
those names appear only in *comments* inside `ingestion/inference.py`
(lines 16-23, 182, 1669-of-context-dump) and `ingestion/resnet_classifier.py`,
never as real code. This means the actual training data pipeline cannot be
read directly; it has to be reconstructed from (a) what data-prep scripts
in this repo produced and consumed, (b) file timestamps, and (c) the
checkpoint's own stored metadata. All three converge on the same answer
below.

**2. `ingestion/tiler.py` itself documents a migration away from the stretched path.**
`generate_tiles()`'s docstring (tiler.py:87-100) states explicitly:
> "IMPORTANT: this is the TRAINING data path. Tiles are saved as .npy
> arrays holding all available bands ... as float32 surface reflectance,
> with NO contrast stretch and NO 8-bit quantization... If you need
> human-viewable RGB previews ... use `generate_rgb_preview_tiles()`
> instead/in addition — that path still does the percentile stretch + 8-bit
> PNG save, but it is **explicitly NOT the training data source anymore**."

The word "anymore" is the tell: at some point training *did* consume the
stretched RGB path, and the codebase was deliberately changed to stop
that. `generate_rgb_preview_tiles()` (tiler.py:151-232) is unchanged and
still applies a per-tile 2nd/98th-percentile stretch to 8-bit
(tiler.py:211-215) — and it is this exact function that `pipeline.py`
calls for the live/production tiling path (`from ingestion.tiler import
export_image_local, generate_rgb_preview_tiles`, used in Step 2 of
`run_pipeline()`), whose PNG output is what `ingestion/inference.py::run_inference()`
reads at line 390 (`image = Image.open(tile_path).convert("RGB")`).

**3. A repo script confirms `generate_tiles()` (the unstretched path) was actually run against every training city, one day before the checkpoint was saved.**
`retile_all_cities_6band.py` (repo root) does exactly one thing: it calls
`generate_tiles()` (imported directly from `ingestion.tiler`) against each
of 11 named cities' `raw.tif`, to "re-tile all 11 cities' raw.tif (already
confirmed 6-band) into tile_0_0.npy." On disk, every one of those 11
cities' `data/pipeline_runs/<city>_*/tiles/tile_0_0.npy` files carries an
identical `Jul 14 11:55` mtime — confirming the script was actually
executed, not just written. The production checkpoint
(`models/production/geowatch_production_model.pth`) has an mtime of
`Jul 15 01:38`, ~14 hours later, and `caat_thresholds.json` (which must be
recomputed against a specific checkpoint per its own provenance-check logic
in `ingestion/inference.py::load_caat_thresholds`) is dated `Jul 15 01:37` —
i.e. training + threshold calibration both completed the day immediately
following the 6-band unstretched retile.

**4. The checkpoint's own stored metadata confirms it was trained on exactly those 11 cities.**
Loading the checkpoint directly (`torch.load(..., map_location="cpu")`) and
inspecting its non-tensor keys:
```
training_cities: ['accra', 'capetown', 'dhaka', 'dharavi', 'guatemala',
                   'hcmc', 'jakarta', 'kigali', 'lagos', 'nairobi', 'nusantara']
n_train_patches: 1272
architecture: 'GeoWatchResNetSeg (ResNet50 SSL4EO-S12 MoCo + DeepLabV3+,
               paved_road/dense_informal_roofing separation loss)'
```
This is the identical 11-city list `retile_all_cities_6band.py` hardcodes
in its `CITY_MAP`. (Side note, not this check's primary question but
directly relevant to the user's broader investigation: the checkpoint's
own `architecture` string states it already includes a dedicated
"paved_road/dense_informal_roofing separation loss" term — i.e. a previous
attempt to specifically address this confusion pair already exists inside
the current production model. No trace of that loss function's
implementation exists anywhere in this repo — it lives only in the
notebook.)

**5. Direct inspection of the actual `.npy` training tile confirms raw, unstretched reflectance — not 8-bit-stretched RGB.**
Loaded `data/pipeline_runs/dharavi_20260702_163012/tiles/tile_0_0.npy`
(one of the 11 training cities) directly with NumPy:
```
shape: (257, 291, 6)  dtype: float32
band 0 (Blue):  min=0.0076  max=0.6528  mean=0.0855
band 1 (Green): min=0.0240  max=0.6411  mean=0.1069
band 2 (Red):   min=0.0214  max=0.6226  mean=0.1184
band 3 (NIR):   min=0.0323  max=0.5938  mean=0.1911
band 4 (SWIR1): min=0.0392  max=0.5950  mean=0.1916
band 5 (SWIR2): min=0.0316  max=0.6779  mean=0.1601
```
This is genuine Sentinel-2 surface-reflectance data (already `/10000`'d in
`sentinel2.py::mask_s2_clouds`), 6 bands, values clustered in a narrow
~0.01–0.68 band — nothing resembling a per-tile 2nd/98th-percentile stretch
that fills the 0–1 (or 0–255) range. It is exactly what `generate_tiles()`'s
docstring says it produces, and structurally incompatible with what
`generate_rgb_preview_tiles()` produces for the same source raster (an
8-bit image deliberately rescaled so its 2nd/98th percentile hit 0/255).

**6. The model's actual input layer confirms 3 channels — so *some* band-selection step (not present anywhere in this repo) reduces 6→3 before training, but nothing in the repo evidence suggests it also re-introduces a stretch.**
`encoder.conv1.weight` in the checkpoint's `model_state_dict` has shape
`(64, 3, 7, 7)` — a standard ResNet50 stem for 3-channel input, consistent
with `resnet_model.py`'s docstring ("ResNet50 ... Sentinel-2 **RGB**
pretrained") and `GeoWatchResNetSeg`'s `encoder = resnet50(weights=ResNet50_Weights.SENTINEL2_RGB_MOCO)`.
Since the on-disk training tiles are 6-band, a band-selection step must
happen inside the (absent-from-repo) training notebook. That step is
unverifiable directly, but nothing in this codebase implements or
references a second, independent percentile-stretch routine outside
`tiler.py` — the only stretch logic that exists anywhere in this repo is
the one already confirmed to be excluded from the training path (finding
#2/#5 above).

**7. Inference-side preprocessing is a single, unconditional `/255.0` on already-quantized 8-bit pixels — and its inline comment claiming a match to training is very likely stale.**
`ingestion/inference.py:391`:
```python
img_arr = np.array(image, dtype=np.float32) / 255.0  # matches GeoWatchDatasetResNet: /255 only, no mean/std
```
`image` here is `Image.open(tile_path).convert("RGB")` where `tile_path`
is a PNG produced by `generate_rgb_preview_tiles()` — i.e., already
per-tile contrast-stretched to fill 0–255 and quantized to 8-bit
(tiler.py:211-215), *then* divided by 255 back down to roughly 0–1. This
produces a fundamentally different value distribution than the raw
reflectance the checkpoint was actually trained on (finding #5): inference
pixels are stretched-then-renormalized so each tile independently uses close
to the full dynamic range, while training pixels are raw, unstretched
reflectance clustered far below 1.0 with per-band means around 0.09–0.19 and
no per-tile renormalization at all. The comment's claim that this "matches
GeoWatchDatasetResNet: /255 only" is only internally consistent if
`GeoWatchDatasetResNet` itself reads from 8-bit-quantized 0-255 source
imagery — which is precisely what `generate_tiles()`'s docstring (finding
#2) says training tiles are *not*. The most likely explanation, given the
codebase's own "anymore" language, is that this comment was accurate for
an earlier version of the pipeline (when training *did* consume the
stretched RGB preview path) and was never updated when the training data
source was migrated to raw 6-band `.npy` tiles produced by
`retile_all_cities_6band.py`.

### What remains genuinely unconfirmed *(as written at the time — since resolved)*

> **Resolved.** The open question below was closed by locating the notebook
> outside the repo, in `~/Downloads`. The answer turned out to be the
> possibility this paragraph raises and then dismisses: training did not
> consume the `.npy` files at all. See "## Training Notebook Search".

The training notebook itself is not in this repository, so the exact
in-notebook transform from "6-band raw reflectance `.npy`" to "3-channel
tensor fed to `GeoWatchResNetSeg`" cannot be read directly. It is
theoretically possible the notebook re-implements its own percentile
stretch or other rescaling on the 3 selected bands that happens to land
close to what `generate_rgb_preview_tiles()` produces at inference time —
in which case the mismatch would be smaller than it appears from this repo
alone. However, nothing in this codebase suggests that: no such logic
exists anywhere outside `tiler.py`, the file `retile_all_cities_6band.py`
that prepared this exact checkpoint's input data was written specifically
*to avoid* the stretch (that is its entire stated purpose), and the raw
pixel statistics pulled directly from a real training city's tile
(finding #5) are inconsistent with any full-range stretch having been
applied before or after that `.npy` was written.

### Bottom line *(RETRACTED — see "## Training Notebook Search")*

> **This finding is withdrawn.** It is preserved verbatim below only to show
> what was concluded and on what basis. It was superseded by direct notebook
> inspection, which established that training and inference share the same
> preprocessing path. The replacement findings — including the downgraded
> `tiler.py` docstring issue that caused this error — are in
> "## Training Notebook Search → 5. Corrected findings".

**~~[Critical, now confirmed rather than speculative]~~ [RETRACTED — NOT A REAL FINDING] Training and inference feed the production model structurally different pixel-value distributions.**
- What happens: the checkpoint currently in production (`models/production/geowatch_production_model.pth`, trained on the 11 cities listed in its own metadata) was very likely trained on raw, unstretched, per-band Sentinel-2 reflectance (`generate_tiles()` output, confirmed via direct `.npy` inspection), while `ingestion/inference.py::run_inference()` — the function `pipeline.py` actually calls in production — feeds it 8-bit, per-tile-percentile-stretched RGB (`generate_rgb_preview_tiles()` output) divided by 255.
- Root cause: the codebase was migrated (per `tiler.py`'s own docstring language) from a stretched-RGB training source to a raw-reflectance training source, but the inference-side preprocessing in `ingestion/inference.py` — and the comment justifying it — were not updated to match. The two tiling functions in `tiler.py` now serve genuinely different consumers (training vs. visual QA/frontend/live inference) that used to be the same consumer, and nothing in the pipeline re-synchronizes them.
- Downstream propagation risk: every pixel the production model sees at inference time has already been transformed by a per-tile contrast stretch it never saw during training. This is a plausible, and now evidence-backed, root-cause contributor to systematic misclassification for any class pair whose separation depends on absolute brightness/contrast rather than pure hue — including, but not limited to, `paved_road` vs. `dense_informal_roofing`, the exact confusion pair the checkpoint's own `architecture` string says it already has a dedicated loss term trying to fix. A dedicated loss term fighting a confusion pair cannot succeed if the pixel statistics that loss term was trained against never recur at inference time.

---

## Training Notebook Search

Follow-up to the section above, which could not close its question because
the training notebook was not in this repository. This section locates that
notebook on disk, reads its data-loading and preprocessing cells directly,
and settles the question.

### Verdict: **REFUTED — the hypothesized pixel-distribution mismatch does not exist.**

Training and inference both consume the **same** per-tile
percentile-stretched 8-bit PNG (`generate_rgb_preview_tiles()` output),
and both normalize with `/255.0` only, with no ImageNet mean/std. The raw
6-band `.npy` path (`generate_tiles()` + `retile_all_cities_6band.py`) was
an experiment that was **abandoned before the production checkpoint was
trained**.

### 1. Where the notebook was found

`/Users/kanveermadan/Downloads/` contains **28 GeoWatch training notebooks**
(Colab downloads, various versions). Locations searched:

| Location | Result |
|---|---|
| `/Users/kanveermadan/Downloads` | **28 geowatch `*.ipynb` found** |
| `/Users/kanveermadan/Desktop`, `/Users/kanveermadan/Documents` | no geowatch notebooks (only a matplotlib test nb in a venv) |
| `/Users/kanveermadan/Library/CloudStorage/GoogleDrive-kanveermadan@gmail.com` (= `~/Google Drive` symlink) | no `.ipynb` present locally (Drive contents are cloud-streamed, not synced to disk) |
| Repo git state | `/Users/kanveermadan/geowatch` is **not a git repository** — no `.git`, no `.gitignore`, no remotes/branches to check |
| Other repos under `~` (maxdepth 3) | 12 unrelated git repos; `~/Documents/Geo AI/.git` exists but has **zero commits and no remotes** (empty repo) |
| Whole-home `*.ipynb` sweep (excluding venvs/node_modules/caches) | only the Downloads set above + unrelated projects |

### 2. Which notebook produced the production checkpoint

**`/Users/kanveermadan/Downloads/geowatch_water_loco_with_diagnostics (2).ipynb`**
(mtime `Jul 15 00:40:56 2026`) — the most recent notebook preceding
`models/production/geowatch_production_model.pth` (mtime `Jul 15 01:38:13 2026`),
a 57-minute gap consistent with its final cell calling
`files.download(local_path)` after training completes.

Fingerprint match against the checkpoint's stored metadata — all four independent:

| Checkpoint metadata | Notebook (cell 39, production training cell) |
|---|---|
| `training_cities` = 11 cities (accra…nusantara) | `CITIES` / `CITY_MAP` = the same 11 cities, same `run_id`s that exist in `data/pipeline_runs/` |
| `architecture` = "…paved_road/dense_informal_roofing **separation loss**" | `CombinedLoss(..., separation_weight=0.25, class_a_idx=CATEGORIES.index('paved_road'), class_b_idx=CATEGORIES.index('dense_informal_roofing'))` |
| `n_train_patches`=1272, `n_monitor_patches`=141 | `PROD_VAL_FRACTION = 0.10` → 141/(1272+141) = **9.98%** |
| `num_classes`=7, `ignore_index`=255 | `NUM_CLASSES`=7, `IGNORE_INDEX`=255 |

(The exact `monitor_miou_at_save` value 0.6158893… appears in no notebook,
because Colab outputs were cleared before download — so the match above is
established by configuration, not by stored output.)

### 3. What the notebook actually loads and how it preprocesses

**Image source — the stretched PNG, NOT the raw `.npy`:**
- Cell 4 copies, for each of the 11 cities, `{run_id}/tiles/tile_0_0.png`
  from Drive into `/content/data/{city}/tile_0_0.png`. These are the exact
  run directories present in this repo — i.e. literally the
  `generate_rgb_preview_tiles()` PNG output (per-tile 2nd/98th-percentile
  stretch, 8-bit, `tiler.py:211-215`).
- Every patch-building function reads that PNG:
  `build_sam_patches` (cell 11), `build_osm_patches`,
  `build_osm_generated_patches`, `build_osm_generated_water_patches`,
  `build_sliding_window_patches` — all via
  `Image.open(f'/content/data/{city}/tile_0_0.png').convert('RGB')`,
  then `np.array(..., dtype=np.uint8)`.
- **The notebook contains ZERO occurrences of `.npy` and ZERO of `np.load`**
  (verified programmatically over all code cells). `tile_0_0.png` appears
  15 times.

**Normalization — `/255` only, no mean/std:**
- Cell 21 defines `GeoWatchDataset`, which does `/255.0` **and then applies
  ImageNet mean/std** (`0.485/0.456/0.406`, `0.229/0.224/0.225`). This is the
  **superseded SegFormer-era** dataset class.
- Cell 24 defines the class actually used:
  ```python
  class GeoWatchDatasetResNet(GeoWatchDataset):
      """Same as GeoWatchDataset, but skips ImageNet mean/std normalization
      (see note above) -- only scales to [0,1], matching production tiles."""
      def __getitem__(self, idx):
          image = torch.from_numpy(item['image']).permute(2, 0, 1).float() / 255.0
  ```
- Cell 39 (production training) builds **both** its train and val
  `DataLoader`s from `GeoWatchDatasetResNet(...)`, not `GeoWatchDataset`.

**No percentile stretch is applied inside the notebook** — the only stretch
in the whole chain is the one `tiler.py` already applied when writing the
PNG, which inference reproduces identically.

**Sliding-window geometry also matches inference:**
`build_sliding_window_patches(patch_size=64, stride=32)` slices native-resolution
64×64 windows at stride 32 directly from the same PNG — the identical
configuration `ingestion/inference.py::run_inference()` uses (`PATCH_SIZE=64`,
`stride = patch_size // 2`).

### 4. Why the `.npy` / 6-band trail was a false lead

`retile_all_cities_6band.py` and `geowatch_segformer_finetune_CLEAN_6band.ipynb`
(mtime `Jul 14 11:33`, uses `np.load`) were a genuine 6-band experiment run
the day before — which is why the `.npy` files exist on disk with
`Jul 14 11:55` timestamps. But it was **abandoned**: the two later notebook
generations (`geowatch_water_loco_with_diagnostics (1)`, `Jul 14 17:01`, and
`(2)`, `Jul 15 00:40`) both dropped `.npy` entirely and reverted to the PNG.
This is corroborated by the checkpoint itself — its
`encoder.conv1.weight` has shape **`(64, 3, 7, 7)`**, a 3-channel stem, which
could not consume 6-band input at all.

The earlier section's timestamp-based inference ("the retile ran ~14h before
the checkpoint, therefore it fed the checkpoint") was **post hoc ergo propter
hoc** — the retile did run first, but its output was not what training
consumed. That is the root cause of the earlier incorrect verdict:
`tiler.py`'s docstring asserts `generate_tiles()` "is the TRAINING data path"
and that the preview path "is explicitly NOT the training data source
anymore," and that claim was taken at face value. **The docstring is wrong /
aspirational** — it describes an intended migration that the training code
never actually adopted.

### 5. Corrected findings

**[Minor — docstring drift, replaces the earlier Critical] `tiler.py`'s `generate_tiles()` docstring misstates which function is the training data path** (tiler.py:87-100)
- What happens: the docstring declares itself "the TRAINING data path" and
  states `generate_rgb_preview_tiles()` "is explicitly NOT the training data
  source anymore." The production checkpoint was in fact trained entirely
  from `generate_rgb_preview_tiles()`'s PNG output; `generate_tiles()`'s
  `.npy` output fed only an abandoned 6-band experiment.
- Root cause: the docstring was written when the 6-band `.npy` migration was
  planned/underway (Jul 14), and was never reverted when the notebook rolled
  back to the PNG path later the same day. Nothing in the repo records the
  rollback — the notebook lives only in `~/Downloads`.
- Downstream propagation risk: documentation-only for model correctness, but
  it actively misleads exactly the kind of investigation conducted in the
  previous section — it caused a Critical mismatch to be reported that does
  not exist.

**[Minor — accuracy note] `inference.py:391`'s comment is correct.**
`# matches GeoWatchDatasetResNet: /255 only, no mean/std` is verified
accurate against cell 24's class definition. The earlier section's suspicion
that this comment was stale is **withdrawn**.

**[Minor — genuine, unrelated to distribution] Patch-scale heterogeneity between two of the five training sources and inference.**
`build_sam_patches` (and the OSM patch builders) crop a variable-size
annotation bbox and `resize((64,64), Image.BILINEAR)`, so those patches carry
resampled, non-native ground sample distance. Inference never resizes — it
reads native-resolution 64×64 windows. `build_sliding_window_patches` does
match inference natively, so the training set is a mix. This is a
scale/resampling difference, **not** a pixel-value distribution mismatch, and
may function partly as scale augmentation; flagged only for completeness and
not confirmed to be harmful.

### 6. Bearing on the paved_road / dense_informal_roofing investigation

The train/inference pipeline is **not** the explanation for that confusion
pair. Notably, the notebook shows the confusion was already known and
directly targeted in training: `CombinedLoss` carries a dedicated
`separation_weight=0.25` term (`separation_margin=2.0`) explicitly
parameterized on `paved_road` vs `dense_informal_roofing`, with an inline
note that it was "lowered from 0.5 -- see LOCO cell docstring." The pair
remained confused despite that term, and with the preprocessing hypothesis
now eliminated, the remaining candidate causes are label quality, class
balance/weighting, the 10m resolution limit itself, and the
`osm_dem.py` distance-map normalization issues recorded in the Ingestion
Module section above.

---

## Classification Module

Scope: `ingestion/segmentation.py` (SAM), `ingestion/classifier.py` (RemoteCLIP
Path A scaffold), `ingestion/inference.py` (live production path),
`ingestion/resnet_classifier.py` + `ingestion/resnet_model.py`, and the CAAT
tooling (`recalibrate_caat.py`, `validate_recalibration.py`,
`caat_diagnostic.py`, plus the deployed `models/production/caat_thresholds.json`).

### Reachability map (determines severity caps)

| File | Status |
|---|---|
| `segmentation.py` | **LIVE** — `pipeline.py` imports `load_sam`, `segment_tile`, `encode_mask_rle`; `decode_mask_rle` used by 4 other modules. `save_masks`/`visualize_masks` are unused by the pipeline. |
| `inference.py` | **LIVE** — the entire production inference path. |
| `classifier.py` | **DEAD** — only importer is `test_classifier.py`. All findings capped at Moderate. |
| `resnet_classifier.py` | **DEAD** — zero imports repo-wide. Capped at Moderate, except where reading it exposed a gap in the live path (C10). |
| `resnet_model.py` | **Transitively dead** — only importer is `resnet_classifier.py`, via a function-local import. |
| `recalibrate_caat.py` | Dev tool; **its output was never deployed** (`caat_thresholds_recalibrated.json` does not exist on disk). |
| `validate_recalibration.py` | **Cannot run** — points at the nonexistent recalibrated file. |

### Deployed `caat_thresholds.json` — actual contents

mtime `Jul 15 01:37:49 2026`, 24 seconds before the production checkpoint.

| Category | Threshold | Pooled "correct" px |
|---|---:|---:|
| dense_informal_roofing | **0.4893** | 104,061 |
| sparse_informal_roofing | 0.5154 | **14,285** |
| paved_road | **0.5969** | **420,754** |
| standing_water | **0.8265** | 342,787 |
| vegetation_clearing | 0.4988 | 60,030 |
| active_construction | 0.3712 | 42,128 |
| dense_vegetation | 0.5825 | 332,050 |

Present: `calibration_method: "pooled_loco_unseen_city_folds"`, `percentile: 10.0`,
`floor: 0.15`, `n_loco_folds_pooled: 11`, `pooled_sample_counts`, `caveat`.
**Absent: `source_checkpoint`, `methodology`, `cities_pooled`.**
No threshold sits at the 0.15 floor or the 0.50 zero-sample fallback — neither fired.

---

### Critical findings

**[Critical] C9 — `segment_id` is an unstable join key, and is already broken between `result.json` and `masks.json` on current runs** (segmentation.py:34, 93; inference.py:700; pipeline.py:332-361)
- What happens: two independent defects compound. (a) `segment_tile()` re-sorts SAM masks by area descending, then every serializer assigns `segment_id = i` — the *rank in that sorted order*, not a content-derived key. Any regeneration (different SAM checkpoint, changed params, area ties, different tile PNG) renumbers everything. (b) Post-Phase-2, `pipeline.py` assigns `result.json` segment ids from a counter over *surviving* segments (after the `w<8 or h<8` filter) while `masks.json` ids come from a separate counter over *all* masks. Verified empirically on `dharavi_phase11_postfix_20260807_125913`: 36 segments (ids 0–35) vs 49 masks (ids 0–48), with **24 of 36 segments (67%) having a `segment_id` whose bbox does not match the `masks.json` entry of the same id**. Older training-era runs (e.g. `dharavi_20260702_163012`) are *not* affected — their ids still index directly into the mask list, so existing training data is intact.
- Root cause: `segment_id` encodes list position rather than identity, and the Phase 2 multi-tile change introduced globally-unique segment ids for the frontend without recognizing that `masks.json` is keyed on a separate unfiltered counter and that consumers join the two by id. Nothing records which SAM run produced a given id set, so a mismatch is undetectable after the fact.
- Downstream propagation risk: forward-looking and severe. `recalibrate_caat.py::build_label_canvas` builds `mask_by_segment = {m["segment_id"]: m for m in masks}` and joins it against `annotations.json` ids (derived from `result.json`). Any new annotation round or CAAT recalibration performed on a post-Phase-2 run would paint the **wrong mask** for roughly two-thirds of labels — producing a corrupted label canvas, corrupted thresholds, and no error. A mis-join is indistinguishable from legitimate data.

**[Critical] C10 — Deployed CAAT thresholds were calibrated on 11 different models than the one they gate, and the check that would catch this lives in dead code** (inference.py:254-294; resnet_classifier.py:42-60; caat_thresholds.json)
- What happens: the deployed threshold file has **no `source_checkpoint` key**, and its own `caveat` field states the thresholds are *"Derived from 11 separate LOCO fold models (each missing one city), NOT from the production checkpoint trained on all 11 cities. Approximation of unseen-city confidence behavior, not an exact calibration of the deployed model. Re-validate against a live test."* Each fold model saw ~10/11 of the data and has its own confidence scale; their pooled confidences set the gate for a 12th, differently-trained network. The live loader `inference.py::load_caat_thresholds` validates only that category *names* match — it reads `data.get('source_checkpoint', '?')` purely to print it, so a file with no provenance loads clean and logs `source_checkpoint=?`. Meanwhile `resnet_classifier.py::load_production_model` implements exactly the missing check (raises on missing `source_checkpoint` and on basename mismatch) with the comment *"This was a real bug caught during development; don't skip this check."* That module is dead. **The deployed file would be rejected outright by the codebase's own validator.**
- Root cause: two divergent loaders were written for the same artifact, each enforcing a different half of the needed validation — provenance vs. category-completeness. The stricter provenance half landed in the module that was subsequently abandoned; the surviving module was never brought to parity. The caveat survives only as data, in a field no code reads.
- Downstream propagation risk: every known/unknown decision in production — and therefore `unknown_pct`, `category_area_pct`, `landcover_builtup_pct`, and every exposure figure derived from them — rests on a calibration the file itself disclaims. The caveat is not propagated into `result.json`'s `landcover` block, so no downstream consumer or frontend ever sees it.

**[Critical] C11 — Proximity penalties break the probability simplex and are tested against thresholds calibrated without them** (inference.py:459-479 vs. recalibrate_caat.py:120-178)
- What happens: after softmax averaging, `mean_probs[road_idx] *= (1.0 - 0.3*road_dist_map)` and `mean_probs[water_idx] *= (1.0 - 0.2*waterway_dist_map)`. Only one channel is scaled, so the per-pixel vector no longer sums to 1. `predicted_conf` is then taken from this non-normalized vector and compared against `caat_thresholds[predicted_idx]`. Neither `recalibrate_caat.py::sliding_window_mean_probs` (no penalty parameters exist in its signature) nor the notebook cell that actually produced the deployed file applies any penalty — the notebook contains **zero** occurrences of `road_dist`, `dist_map`, `ROAD_PROXIMITY`, `waterway_dist`, or `penalty` across all code cells. Confirmed for the artifact actually in production, not merely for the unused script.
- Root cause: the penalty was inserted into the decision path (deliberately "BEFORE argmax so it can actually change the winning class") without re-deriving the thresholds the penalized values are then tested against. Two independently-reasonable mechanisms compose into an unvalidated one.
- Downstream propagation risk: the penalty is multiplicative and ≤ 1, so error direction is one-way and predictable. At maximum distance the factor is 0.7 for `paved_road` and 0.8 for `standing_water`. A pixel therefore needs unpenalized confidence ≈ **0.853** to clear paved_road's 0.5969 gate, and ≈ **1.033 — unreachable** — to clear standing_water's 0.8265 gate. **Far-from-mapped-water pixels cannot be labeled `standing_water` at all under the deployed thresholds, regardless of model output.** Both classes are systematically over-rejected into `unknown`, and the effect is strongest exactly where OSM coverage is sparsest — informal settlements. Compounded by C7 (the distance map is normalized to each AOI's own max), so `d≈1` is common in road-sparse AOIs.

**[Critical] C12 — CAAT has no false-positive term and is structurally unable to suppress confident misclassification** (recalibrate_caat.py:232-242, 267-268)
- What happens: the threshold is the 10th percentile of confidence among **correctly predicted** pixels only (`correct_mask = labeled_mask & (pred_idx == canvas)`). Wrongly-predicted pixels are excluded from the calibration set entirely, no matter how confident. The rule reduces to "keep ~90% of what we already get right" — a pure recall criterion with no precision term. A confident false positive (e.g. `paved_road` at 0.75 on a roofing pixel) sits far above the 0.5969 gate and passes untouched, and never entered the statistic that set that gate.
- Root cause: the calibration objective optimizes true-positive retention and is blind to the error mode it is being asked to mitigate. CAAT gates on the winning class's **absolute confidence after argmax**; it never inspects the runner-up or the top1−top2 margin, so "confidently wrong" and "confidently right" are indistinguishable to it.
- Downstream propagation risk: the only confusion CAAT removes is the *low-confidence* kind, which is silently converted to `unknown`, while *confidently wrong* pixels are promoted to a clean-looking label. That asymmetry makes pair confusion **less visible in output without making it less real**. See the separation-loss analysis below.
- Honest counter-observation, stated to avoid overclaiming: a naive "the argmax loser gets a higher gate" prediction is **not** borne out — `dense_informal_roofing` (0.4893) is *lower* than `paved_road` (0.5969). The structural no-precision-term defect is confirmed from code; a specific directional asymmetry from that mechanism alone is not.

---

### Why the targeted separation loss failed to separate the pair

The user's open question from Module 1. Evidence assembled from the training
notebook (`geowatch_water_loco_with_diagnostics (2).ipynb`, cells 11/13/26/39),
the checkpoint's stored tensors, and the live inference/CAAT code. Five
mechanisms, each independently sufficient to blunt the loss term; together they
explain the outcome without needing any of them to be the sole cause.

**1. The loss optimizes a logit margin; inference decides on softmax confidence.**
`CombinedLoss.separation_loss` (cell 26) computes, on ground-truth-A pixels,
`F.relu(margin - (logit_a - logit_b)).mean()` with `separation_margin=2.0`. It
constrains only the **difference** between two logits. It says nothing about
the winner's absolute softmax probability, which is what CAAT gates on. A model
can fully satisfy the margin (`logit_a - logit_b ≥ 2.0`) while both classes sit
low relative to the other five, leaving `max(softmax)` below the class's CAAT
threshold. The loss can therefore succeed at its own objective and still have
every affected pixel demoted to `unknown` — which matches
`check_confusion_pair.py`'s recorded finding that this pair accounts for
**72.9% of all unknown-pixel mass** pooled across Cape Town + Dharavi, and
`breakdown_unknown_class.py`'s "~50% unknown mass" framing.

**2. `paved_road` labels are machine-generated from OSM vector geometry, and the class dominates the training set.**
Two of the five patch sources produce `paved_road` labels from OSM road
geometry rather than human annotation: `build_osm_patches` (rasterizes traced
road centerlines with `road_buffer_px=2`, PAVED_TYPES only) and
`build_osm_generated_patches` (buffered geometry masks for all road types
including residential/service, capped 25/city). Deriving the implied class
distribution from the checkpoint's stored `class_weights` (inverse-frequency,
normalized to sum to `NUM_CLASSES`):

| Class | Share of training patches | CE weight |
|---|---:|---:|
| **paved_road** | **41.0%** | 0.1707 |
| dense_vegetation | 19.2% | 0.3646 |
| standing_water | 14.2% | 0.4915 |
| **dense_informal_roofing** | **11.4%** | 0.6135 |
| active_construction | 6.7% | 1.0466 |
| vegetation_clearing | 5.2% | 1.3479 |
| sparse_informal_roofing | 2.4% | 2.9653 |

`paved_road` is **3.59×** `dense_informal_roofing`. The notebook's own docstring
anticipated this: *"if paved_road ends up disproportionately larger than every
other class, lower max_per_city here rather than assuming it's fine."* At 10m
resolution in dense informal settlements, a 2px (≈20m) buffer around an
imprecise OSM centerline will frequently overlay actual rooftops — so a
meaningful share of `paved_road` ground truth is painted **over roofing
pixels**. A separation loss cannot resolve a confusion that is present in the
labels themselves; it forces the model to confidently learn contradictory
supervision.

**3. The separation term sees only a sparse subset of pixels.**
Labels are painted only inside real SAM mask shapes; everything else is
`IGNORE_INDEX`. `separation_loss` further restricts to pixels whose ground
truth is exactly one of the two classes, and averages over whatever few
qualify in each batch — a low-signal, high-variance term. Weighted at 0.25
against `0.5*CE + 0.5*Dice`, its gradient contribution is small, and neither
CE (weighted at 0.1707 for `paved_road`, the *lowest* of seven) nor Dice
(unweighted) reinforces it.

**4. Inference then actively fights the trained behavior.**
The road-proximity penalty exists to suppress `paved_road` over-prediction —
a band-aid over mechanism 2. It multiplies `paved_road`'s probability by up to
0.7 wherever OSM shows no nearby road. But OSM road coverage in informal
settlements is known-incomplete (C6), and the distance map is normalized
per-AOI (C7), so `d≈1` is common precisely in road-sparse AOIs. A real road
absent from OSM has its correctly-separated `paved_road` probability pushed
back down — recreating the exact confusion the loss was trained to prevent.
Two arithmetic failure modes on the deployed numbers:
  - *Suppression:* `paved_road` at 0.75, `d=1.0` → 0.525, below its 0.5969 gate → `UNKNOWN`.
  - *Flip:* `paved_road` 0.45 vs `dense_informal_roofing` 0.50 → penalized road 0.315 → argmax flips to roofing, which clears its **lower** 0.4893 gate and is emitted as a confident roofing label.

**5. CAAT can neither correct nor reveal the residue (C12), and is asymmetric across the pair.**
Because CAAT has no precision term, the confidently-wrong pixels mechanism 4
produces pass through as clean labels. The gates are also unequal on exactly
this pair — `paved_road` 0.5969 vs `dense_informal_roofing` 0.4893 — so at
identical confidence a road pixel is demoted while a roofing pixel is retained.
And per C10 those gates were calibrated on 11 *different* models, and per C11
on *unpenalized* probabilities that inference no longer produces.

**Net:** the separation loss was a training-time fix for a problem whose roots
are (a) in the labels and class balance, and (b) re-introduced at inference by
a penalty-plus-threshold stack that did not exist at training time and was
never jointly validated with it. The pair's mass ends up mostly in `unknown`
rather than correctly separated. Nothing here required the loss term to be
implemented incorrectly — reading it, `separation_loss` does what it says.

**Not investigated / genuinely open:** whether the label noise in hypothesis 2
is large enough to be the dominant cause versus a contributing one. Settling
that needs a human audit of OSM-derived `paved_road` patches against imagery —
which is exactly what `audit_roofing_labels.py` was built for and, on the
evidence in the repo, has not yet been run to completion.

---

### `ingestion/segmentation.py` (LIVE)

**Verified NOT a bug (negative result).** The hand-rolled RLE codec is correct
and lossless. Executed against six cases (all-False, all-True, first-pixel-True,
random square, random non-square, single-pixel) — all six round-tripped exactly.
The COCO leading-zero convention *is* handled (`prev=0, count=0` emits a leading
`0` when the first pixel is True: `all_true → [0,35]`), the decoder's
`val=False` start correctly mirrors it, and `mask.T.flatten()` ↔
`flat.reshape(w,h).T` is a correct column-major inverse pair including
non-square masks. This was the highest-stakes claim to check and it holds.

**[Moderate] `decode_mask_rle` silently accepts malformed RLE and returns a partially-empty mask** (segmentation.py:63-75)
- What happens: no validation that `sum(counts) == h*w`. Tested both directions — truncated counts: original 212 True pixels, decoded **97**, no exception (the unwritten tail stays `False` because `flat` is pre-allocated). Oversized counts: numpy slice assignment clamps rather than raising, so it also passes silently. `reshape` always succeeds because `flat` is exactly `h*w` long.
- Root cause: the decoder pre-allocates to the *declared* size and writes by slicing, so declared size and actual counts are never cross-checked; numpy's clamping slice semantics remove the one place an error would naturally surface.
- Downstream propagation risk: used by `inference.py` (segment landcover aggregation), `recalibrate_caat.py` (label rasterization), `audit_boundary_labels.py`. A truncated mask silently shrinks a segment, shifting its `dominant_landcover_category` majority vote and `landcover_purity_pct` toward whatever occupies the surviving region.

**[Moderate] `encode_mask_rle` is a pure-Python per-pixel loop, ~111× slower than vectorized** (segmentation.py:49-59)
- What happens: measured 51.2 ms on one 512×512 mask, vs 0.462 ms for the vectorized `np.flatnonzero(np.diff(flat))` equivalent. Called for every SAM mask on every tile — extrapolates to ~2.6 s/tile at 50 masks, ~7.7 s/tile at 150.
- Root cause: `for val in flat` scalar-iterates a numpy array with a per-pixel `int()` conversion. The docstring's "no pycocotools dependency needed" justifies avoiding the dependency but not the implementation cost.
- Downstream propagation risk: none to correctness (output verified exact); wall-clock only, scaling with tile count.

**[Moderate] Two divergent serializers write the same `masks.json` format** (segmentation.py:78-107 vs pipeline.py:347-361)
- What happens: `save_masks()` writes `{segment_id, area, bbox, predicted_iou, stability_score, mask_rle}`; `pipeline.py` does not call it and inlines its own writer adding `source_tile`, `tile_col_off`, `tile_row_off` and globally-offset bboxes.
- Root cause: Phase 2 mosaicking added offset tracking to the pipeline's inline path but left `save_masks()` at the old single-tile contract instead of extending and calling it.
- Downstream propagation risk: `pipeline.py`'s own comment notes `mask_rle` stays *tile-local* while `bbox` is *global*, requiring the offset fields to reconcile. A `masks.json` from `save_masks()` lacks them entirely, so a consumer applying that logic mis-places masks with no error.

**[Minor] A test monkeypatches `pipeline.save_masks`, which does not exist** (tests/test_flood_flag_combination.py:33)
- What happens: `monkeypatch.setattr("pipeline.save_masks", ...)` without `raising=False`. `pipeline.py` contains zero occurrences of `save_masks`, so pytest raises `AttributeError` at setup.
- Root cause: written against an earlier `pipeline.py`; not updated when the pipeline switched to inline serialization. Breaks loudly rather than corrupting data, but means this test provides no coverage.

**[Minor] `visualize_masks` draws bounding boxes, not masks** (segmentation.py:110-124)
- What happens: iterates `mask["bbox"]` and calls `draw.rectangle` with an unseeded random color; never touches `mask["segmentation"]`.
- Root cause: predates the RLE work — whose own docstring celebrates recovering "the real segment shape, not just its rectangle" — and was never updated. Unseeded `random` also makes output non-reproducible.

**[Minor] Hardcoded CPU device and global dtype mutation from library code** (segmentation.py:9-10, 18, 32)
- What happens: `get_device()` returns `"cpu"` unconditionally with no CUDA/MPS check. `torch.set_default_dtype(torch.float32)` is called in both `load_sam` and `segment_tile` — a process-global mutation from a library function.
- Root cause: a deliberate M3/MPS float64 workaround, applied unconditionally rather than platform-gated. Currently benign, but `pipeline.py` loads SAM and the production ResNet in one process, making global-state mutation a latent cross-contamination path.

**[Minor] `os.makedirs(os.path.dirname(path), exist_ok=True)` fails on a bare filename** (segmentation.py:89) — same defect class already recorded for `tiler.py:75`.

---

### `ingestion/classifier.py` (DEAD — all findings capped at Moderate)

**[Moderate] The assigned `category` is crop-level, contradicting the docstring, the adjacent comment, and the function's stated design** (classifier.py:196-199, 281-283)
- What happens: the docstring says *"Classifies the full tile once, assigns that scene-level label to all segments."* The inline comment at line 281 says `# Primary: tile-level label`. The very next line assigns `"category": crop_top_category if crop_top_score >= UNKNOWN_THRESHOLD else "unknown"` — the **crop** label. `tile_category` never reaches the `category` field; it is used only for printing and for the `annotation_priority` comparison.
- Root cause: refactored from tile-level to crop-level labeling without updating the docstring or the comment now sitting directly above the line that falsifies it.
- Downstream propagation risk: none currently. Historically: any Path A `result.json` carries crop-level labels while its `label_source` field says `"tile_level"` — recorded provenance is wrong for every Path A segment ever written.

**[Moderate] `all_scores`/`softmax_probs` are tile-level but stored per-segment** (classifier.py:292-299) — identical across all segments, while `category` comes from `crop_raw`. A consumer reading `all_scores` to justify `category` gets a vector whose argmax frequently disagrees with the assigned label. Same incomplete refactor.

**[Moderate] `load_state_dict(..., strict=False)` discards its result, so a total weight-load failure is silent** (classifier.py:144)
- What happens: `missing_keys`/`unexpected_keys` are ignored. With `pretrained=None` (deliberate, per the docstring), a key-name mismatch — e.g. the `module.` strip not matching the checkpoint layout — would load **nothing**, leaving the model randomly initialized while printing "RemoteCLIP ViT-L-14 loaded with satellite weights" and emitting confident-looking noise.
- Root cause: `strict=False` was needed for benign head mismatches, but no post-load assertion distinguishes "a few expected keys skipped" from "nothing matched." The success `print()` is unconditional. This is the same failure shape the project was later burned by in the CAAT provenance bug; this file predates that discipline.

**[Minor] `annotation_priority` is `True` for every segment when the tile is unclassifiable** (classifier.py:310) — `crop_top_category` is a raw argmax and can never be `"unknown"`, while `tile_category` can, making the comparison unconditionally true and destroying the flag's triage value on exactly the hardest tiles. Root cause: comparing a thresholded value against an unthresholded one.

**[Minor] `load_remoteclip`'s `model_name` parameter is ignored** (classifier.py:110, 130, 133) — `"ViT-L-14"` is hardcoded in all three uses; passing anything else silently has no effect.

**[Minor] `UNKNOWN_THRESHOLD = 0.20` is an unvalidated absolute cutoff on raw cosine similarity** (classifier.py:100) — sits inside CLIP's live similarity band (~0.15–0.35) and is highly prompt-sensitive, with no derivation recorded. Appropriately superseded by per-class CAAT.

**[Minor, informational] `softmax_probs` over raw cosines is near-uniform by construction** — not a defect (the docstring warns it "tends to flatten, never used for selection"), flagged only because the values are persisted to JSON where a consumer could mistake them for calibrated confidences.

---

### `ingestion/inference.py` (LIVE)

Criticals C10 and C11 above are the headline findings for this file.

**[Moderate] Ambiguity flagging has zero effect on any output pixel, contradicting the comment that justifies it** (inference.py:184-194, 504-508, 529-568)
- What happens: `ambiguity_map` is computed *after* `landcover_map` is finalized and never modifies it. `save_landcover_outputs` reads only `landcover_map` and `confidence_map`, so ambiguous pixels are painted with the identical full-saturation category color as confident ones. The map is consumed only by `compute_area_stats` (reporting) and `build_segments_with_landcover` (two advisory fields). The block comment states these pixels *"get flagged as ambiguous rather than silently painted with one confident-looking color"* — the code does exactly what the comment says it avoids.
- Root cause: implemented as a reporting layer while its justifying comment describes a rendering behavior that was never built.
- Downstream propagation risk: no visual signal distinguishes a 0.90-confidence pixel from a coin-flip between the confused pair. `AMBIGUITY_MARGIN = 0.15` is additionally applied to the **penalized, non-normalized** vector (per C11), so the margin's meaning varies with road proximity — the inline "Tunable, not yet validated empirically" is accurate but understates this.

**[Moderate] `category_area_pct` uses a total-pixel denominator, systematically deflating `landcover_builtup_pct` into the exposure chain** (inference.py:314-317)
- What happens: `100*cat_px/total_px`, so classes sum with `unknown_pct` to 100% — internally consistent and correctly documented, with a sum-check warning. But `pipeline.py` sums the two roofing classes plus `paved_road` from these percentages to form `landcover_builtup_pct` and feeds it to `exposure/compute.py`. Since the unknown mass is dominated by exactly those classes (72.9%), a high unknown rate silently deflates built-up area.
- Root cause: a denominator right for a self-consistent area breakdown is reused as a physical built-up fraction, where unknown should arguably be excluded or propagated as uncertainty. `resnet_classifier.py:213` uses the **opposite** denominator for the same field name.
- Downstream propagation risk: exposure biased low precisely in AOIs where classification is least reliable, with no uncertainty band. C10 and C11 both raise the unknown rate, compounding this.

**[Moderate] Duplicated `GeoWatchResNetSeg` with divergent weight initialization, plus a dead parallel implementation of the whole inference path** (inference.py:123-161 vs resnet_model.py:114-169) — both must stay byte-compatible with the checkpoint or `load_state_dict` silently mismatches. No live impact today; any future edit to one copy silently diverges.

**[Minor] `landcover_purity_pct` mixes a known-only numerator with an all-pixel denominator** (inference.py:695-698) — a segment that is 95% unknown and 5% uniformly `paved_road` reports `purity = 5.0` despite being 100% pure among classified pixels. Conflates purity with coverage; monotonically confounded with unknown rate, so unusable for ranking segments by confidence — its apparent purpose.

**[Minor] Duplicate window origin when a tile is smaller than the patch; sliver tiles classified from near-entirely zero-padded input** (inference.py:407-412, 433-436)
- What happens: `ys[-1] != H - patch_size` compares against an **unclamped** value, so for `H < patch_size` it appends a duplicate `0`, processing that window twice. **Numerically harmless** — `prob_accum` and `count_accum` both double, and the model is deterministic in `eval()` — cost is duplicated compute (up to 4× if both axes duplicate). Separately, a 1-pixel-tall edge tile is classified from a 64×64 patch that is ~98% zeros, and such tiles are reachable via `tiler.py`'s edge clamping.
- Root cause: the `max(..., 0)` clamp is applied to the appended *value* but not to the *comparison*.

**[Minor] Assorted defensive gaps, and two verified-safe patterns**
- `num_classes = checkpoint.get("num_classes", len(categories))` is never cross-checked against `len(categories)`; a mismatch would misalign the CAAT array against model channels. Benign for the current checkpoint (both 7, verified).
- `ambiguous_between` resolves an exact tie via `np.argmax` to the lower-numbered pair, silently favoring `{paved_road, dense_informal_roofing}`.
- **Verified safe:** `list(frozenset)` iteration order is non-deterministic across processes, but every consumer normalizes it — `pair_lookup` inserts both orderings, `compute_area_stats` uses `"|".join(sorted(names))`, `build_segments_with_landcover` uses `sorted(list(...))`, and `pair_num` derives from `enumerate` over a list. No ordering bug exists.
- **Verified safe:** `build_segments_with_landcover` receives tile-local masks and a tile-local `landcover_map`; `pipeline.py` offsets bboxes to global space only afterward. Coordinate spaces are consistent.

---

### `ingestion/resnet_classifier.py` + `resnet_model.py` (DEAD / transitively dead)

**[Moderate] Two `load_production_model` functions with the same name, incompatible signatures, and incompatible return types in one package** (resnet_classifier.py:10 vs inference.py:203) — dict vs 3-tuple, `(path, caat_path, device)` vs `(path, device)`. Six live call sites unpack the tuple form; swapping the import is a one-token edit producing either a `TypeError` or a silent mis-unpack. Root cause: superseded by copy-paste rather than replacement, with no `__all__`, deprecation shim, or removal.

**[Moderate] `category_area_pct` uses a different denominator than `inference.py`'s identically-named output** (resnet_classifier.py:209-213) — `known_px` vs `total_px`, differing by `1/(1−unknown_fraction)`. Both are self-documented, but the key name and type are identical. At a realistic 30–50% unknown rate a module swap would inflate impervious fraction by ~1.4–2× while every key stayed valid.

**[Moderate] Missing CAAT category silently defaults to a 0.5 threshold** (resnet_classifier.py:200) — `caat_thresholds.get(cat_name, 0.5)` does silent policy work inside the inference loop, where `inference.py` instead raises eagerly at load time on both missing and extra categories.

**[Moderate] Swapping this module in would silently drop the OSM proximity penalties and the ambiguity map** (resnet_classifier.py:107-225) — `pipeline.py` would `KeyError` on `ambiguity_map` (loud), but the missing road penalty would degrade silently.

**[Moderate] `resnet_model.py` downloads pretrained SSL4EO-S12 weights at construction; `inference.py`'s duplicate does not** (resnet_model.py:129 vs inference.py:134) — **correctness is unaffected** (`load_state_dict` is strict and the checkpoint carries all 376 keys including every `encoder.*` parameter). The exposure is availability: on a cold cache without network, construction raises before the checkpoint is consulted.

**[Moderate] Hook-populated `self._features` is never cleared, so a non-firing hook yields silently stale features** (resnet_model.py:137-138, 158-169) — `forward()` runs the encoder for side-effects then unconditionally reads `_features['low']/['high']`. Entries are only overwritten, never invalidated: a hook that fails to fire makes the decoder consume the *previous* call's activations and return a confident, well-formed, wrong prediction (first call would `KeyError` loudly; every subsequent one is silent). Also a latent thread-safety hazard if one instance were shared across concurrent FastAPI requests. **Confirmed not currently triggered** — `pipeline.py:259` constructs a fresh model per `run_pipeline()` call.

**[Moderate] The "never change this file" warning sits on the copy that isn't in production** (resnet_model.py:2-23) — the docstring warns that edits will break the checkpoint's `state_dict` load, but production loads into `inference.py:123`'s duplicate. The two already differ. Drift risk runs in the more dangerous direction: editing the file that *says* it is architecture-critical changes nothing, and editing the live copy carries no warning.

**[Minor] Negative window coordinates for tiles narrower than `patch_size`** (resnet_classifier.py:162-167) — crashes loudly on `np.stack`; unreachable at `TILE_SIZE=512`.

**[Minor] `forward()`'s discarded conditional expression is correct** (resnet_model.py:165-166) — **verified empirically**: torchgeo's `resnet50` is a `timm` ResNet, `hasattr(m,'forward_features')` is `True`, and timm's `forward_features` calls `layer1`…`layer3` explicitly so both hooks fire; the `else` branch also fires both. Latent edge: timm's `forward_features` switches to `checkpoint_seq(...)` when `grad_checkpointing` is enabled, which iterates the layers' *children* — neither hook would fire, producing the stale-feature corruption above. Not currently reachable (`grad_checkpointing` defaults `False`, nothing calls `set_grad_checkpointing()`).

**[Minor] Verified negative results** — `pred_class.astype(np.uint8)` cannot alias onto 255 below 256 classes; `list(set(coords))` de-duplication is sound and order-independent; `np.maximum(coverage_count,1)` correctly prevents div-by-zero. Separately noted: `resnet_classifier.py`'s coordinate builder never appends the bottom-right corner `(tile_w-patch, tile_h-patch)`, leaving corner pixels at `count==0` → silently `unknown` when both dimensions are non-divisible. Dead code; recorded for the record.

**[Minor] The `/255.0` normalization comment is accurate** (resnet_classifier.py:146-149) — matches `GeoWatchDatasetResNet` per the training notebook. No mismatch.

---

### CAAT tooling

Criticals C10, C11, C12 above are the headline findings.

**[Moderate] `validate_recalibration.py` cannot run, and judges success by a metric that improves whenever thresholds are lowered** (validate_recalibration.py:34, 57, 98-106)
- What happens: `NEW_CAAT_PATH` points at `caat_thresholds_recalibrated.json`, which does not exist — line 57 raises `FileNotFoundError` before any inference. Beyond that, the only reported metric is `unknown_pct`, framed such that a drop "confirms the recalibration does what it's supposed to do." Unknown% falls monotonically as thresholds fall; no accuracy, mIoU, or precision is measured, so it cannot distinguish recovered-correct pixels from admitted-confidently-wrong ones.
- Root cause: the acceptance criterion was inherited from the framing of the complaint (a "~50% unknown rate") rather than from what thresholds are for. The script concedes its tiles are the same ones used for calibration ("a consistency check, not independent held-out validation") but still presents the delta as validation.
- Downstream propagation risk: none live (dead), but it is a documented-but-unsound acceptance test that could be used to justify lowering thresholds — the change that would most increase confident false positives in the confused pair.

**[Moderate] Calibration set is a few percent of pixels, selected by annotator attention, then applied to every pixel** (recalibrate_caat.py:54-117, 225-242)
- Root cause: annotated segments are the ones a human found salient and unambiguous; SAM proposals further bias toward well-delineated objects. Ambiguous transition zones and mixed pixels — precisely where the roofing/road confusion lives — are systematically under-represented in the statistic that sets the gate.
- Downstream propagation risk: thresholds are optimistically calibrated; real-world unknown rate exceeds what calibration predicted, indistinguishable from genuine model uncertainty.

**[Moderate] `sparse_informal_roofing`'s threshold rests on a 29×-thinner sample than `paved_road`'s, with no variance guard** (caat_thresholds.json) — 14,285 vs 420,754 pooled pixels. A 10th-percentile estimate from 14k spatially-autocorrelated pixels (likely few distinct segments) carries far wider uncertainty, yet both are written as bare floats. `pooled_sample_counts` is recorded for transparency but never used to qualify, widen, or reject a threshold.

**[Moderate] The zero-correct-prediction fallback makes a failing class nearly unreachable rather than loudly broken** (recalibrate_caat.py:262-265) — "conservative" is applied in the direction of suppressing output. The class quietly vanishes from `category_area_pct` (~0%), reading as "not present in this AOI" rather than "the model cannot predict this class." Latent — no deployed threshold equals 0.50.

**[Minor] `caat_diagnostic.py`'s stated threshold range contradicts the deployed file** (caat_diagnostic.py:156) — comment says "0.595-0.992 per class"; deployed range is 0.371–0.827, and the 0.30–0.70 sweep grid brackets it poorly. Confirms at least three distinct CAAT generations have existed.

**[Minor] Distance-to-threshold histogram substitutes the cross-class mean threshold for each pixel's own** (caat_diagnostic.py:172-174) — with a 0.456 spread across classes, "distance to threshold" is off by up to ±0.23. Root cause: `run_inference()` returns the post-CAAT map and winning confidence but not `predicted_idx`, so the diagnostic cannot recover each pixel's own gate. Honestly commented as "coarse," but the histogram is still offered as evidence for clustering just below threshold — the conclusion the approximation is least able to support.

**[Minor] Hypothesis A/B verdicts hinge on undocumented magic constants** (caat_diagnostic.py:110-119, 137-142) — `delta > 5` and `pct_recovered > 30` trigger printed conclusions like "Strong support for Hypothesis A," with neither constant justified.

**[Minor] Single-tile assumption in the recalibration corpus** (recalibrate_caat.py:40, 208) — only `tiles/tile_0_0.png` is read per city; multi-tile AOIs (Jakarta, Cape Town) contribute only their first tile. Predates Phase 2 mosaicking.

---

### Cross-module note

`verify_masks.py:40-52` defines a **fallback duplicate** of `decode_mask_rle`
inside an `except ImportError`, with a printed warning "Verify this matches
your actual encoder." Compared line-by-line: it is currently identical, but it
is a second copy of a format-critical codec that will not track future changes
to the original.

---

## Orchestration Module

Scope: `pipeline.py` (935 lines) and `api.py` (285 lines) — the integration
layer that wires Modules 1 and 2 together and exposes them over HTTP.

### Entry points and reachability

| Entry point | Status |
|---|---|
| `run_pipeline()` | **LIVE** — CLI `--mode landcover`, and `api.py` `/api/analyze`, `/api/demo` refresh path |
| `run_inundation_analysis()` | **LIVE** — CLI `--mode inundation`, `api.py` `/api/analyze_inundation` |
| `run_event_hazard_analysis()` | **DEAD** — the only occurrence of the name repo-wide is its own `def`; `--mode` accepts only `{landcover, inundation}` and `api.py` never calls it |
| `refresh_all_watched_aois()` | **LIVE** — APScheduler `interval` job, 5 days, started at module import |

---

### Critical findings

**[Critical] C13 — `primary_tile` is a single 512px tile while everything else is full-raster; multi-tile AOIs are spatially unrenderable** (pipeline.py:532-533, 612)
- What happens: `tile_width, tile_height = full_width, full_height` but `primary_tile = tiles[0]["path"]`. Verified on the real 4-tile run `phase2_multitile_check_20260724_151518`: `tile_dimensions` is 669×635, `landcover.png` is 669×635, and segment bboxes reach x=668/y=634 — while `primary_tile` resolves to `tile_0_0.png`, actually **512×512**. A consumer using `primary_tile` as the basemap and `tile_dimensions` for the lon/lat projection has an irreconcilable mismatch: segments from `source_tile` 1–3 fall outside the displayed image, which covers only ~59% of AOI width and ~66% of height.
- Root cause: the Phase 2 mosaicking change promoted `tile_dimensions`, the landcover raster, and segment coordinates to full-AOI space but left `primary_tile` on the pre-Phase-2 "one tile = whole AOI" assumption. **No full-AOI RGB basemap is ever written**, so there is nothing correct for `primary_tile` to point at. The in-code comment at 327-331 claiming the frontend projection "works unchanged regardless of how many tiles were actually processed" is false for the base image.
- Downstream propagation risk: silent spatial corruption in any consumer — nothing errors, the JSON is well-formed, every field is individually valid. Compounded by the "UNVERIFIED for multi-tile" warning at 203-209 being a *comment only*: no guard, assertion, or output flag enforces it, and `total_tiles` is emitted with no reliability caveat.

**[Critical] C14 — `applicability` is computed but gates nothing; an out-of-distribution verdict still flows into every downstream layer** (pipeline.py:412-420)
- What happens: `compute_applicability()` returns `urban_landcover_model.status = "out_of_distribution"` when `unknown_pct > 45.0` (`configs/applicability_constants.py:19`), meaning "semantic model output is unreliable for this scene." But `hydrological_surfaces` is computed on line **412**, *before* applicability on 413, and nothing re-checks the verdict afterwards. Confirmed by signature inspection: none of `compute_pluvial/fluvial/coastal/flash_flood/waterlogging_susceptibility` accepts an applicability argument. Within `pipeline.py`, `applicability` is only written into `result.json` and printed. Its sole real consumer anywhere is `zonal/landcover_screening.py:240`, reading it back off disk.
- Root cause: applicability was designed as a **router** — its own module docstring frames it as "should we even try, and how much should we trust the inputs" — but wired in as a **report**. It is positioned after the computation it is meant to govern, and the downstream functions expose no parameter through which it could be honoured.
- Downstream propagation risk: this is precisely the failure mode the module exists to prevent. Module 2 established that the `paved_road`/`dense_informal_roofing` confusion drives the unknown rate; at >45% the pipeline flags the landcover untrustworthy and then still derives `impervious_fraction_pct`, pluvial and waterlogging susceptibility, `landcover_builtup_pct`, and every exposure figure from that same untrusted map — each emitted with its own confident-looking `status`. The dishonesty is structural, not textual.

**[Critical] C15 — `osm_available` is latched before the distance map is built, so `result.json` claims road scores are reliable when every score is the −1.0 sentinel** (pipeline.py:218-227, 316-319, 659-660)
- What happens: `osm_available = roads_gdf is not None` at line 218. `compute_road_distance_map` then returns `None` in a case unrelated to `roads_gdf` being None — `road_px_count == 0`, which it warns about as "AOI extent mismatch?" (`osm_dem.py:426-429`). In that case `full_dist_map` is `None`, so every `tile_dist_map` is `None`, so `compute_road_access_score(bbox, roads_gdf, dist_map=None)` takes its fallback branch, finds `west/south/east/north/img_width/img_height` unset (pipeline never passes them), and returns **−1.0** for every segment (`osm_dem.py:542-548`). Meanwhile `osm_available` is still `True`, so `result.json` reports `road_access_scores_reliable: true`, `road_score_method: "distance_transform"`, and a nonzero `road_segments` count.
- Root cause: one boolean answers two different questions — "did OSM return road geometry?" and "did that geometry rasterize into a usable distance map?" — and it is latched before the second is knowable.
- Downstream propagation risk: two compounding silent effects. `run_inference` receives `road_dist_map=None` and **skips the road-proximity penalty entirely** with no record in the output, and every `road_access_score` is a sentinel a consumer has been explicitly told to trust. Amplifies C6 (the conflated `None`) by promoting it into an affirmative reliability claim.

**[Critical] C16 — Unauthenticated path traversal on write via `aoi_label`** (api.py:127, 194, 223)
- What happens: `aoi_label` is an unvalidated free-form string flowing straight into `run_pipeline`, where `run_id = f"{aoi_label}_{timestamp}"` and `run_dir = os.path.join(output_dir, run_id)` followed by `os.makedirs(run_dir, exist_ok=True)` (pipeline.py:133-135; same pattern at 747-749 and 816-818). A POST with `aoi_label: "../../../../tmp/pwn"` creates directories and writes `result.json`, `raw.tif`, tiles, and `.npy` arrays outside the data root. No endpoint has authentication.
- Root cause: `aoi_label` is treated as a display label at the API boundary and as a filesystem path component at the pipeline boundary; neither side sanitises it because each assumes the other did. The Pydantic model type-checks it as `str` and stops.
- Downstream propagation risk: arbitrary-directory creation and file write as the server user. CORS restricts browser origins but is irrelevant to `curl`. Exposure is bounded by deployment (localhost-only today), but nothing in code enforces that.

**[Critical] C17 — `/api/demo` permanently serves a stale test run; the scheduler's output can never surface** (api.py:83-86, 163)
- What happens: `get_latest_run` selects by **lexicographic** sort over a **prefix** match. Replicating the exact expression against live data: 37 directories match `startswith("dharavi")`, and the selected one is **`dharavi_test_20260806_114208`**. Because `'2' (0x32) < 't' (0x74)`, any future run named `dharavi_20260819_...` sorts *before* `dharavi_test_*` and can never be chosen while that directory exists. The 5-day auto-refresh therefore cannot ever change what `/api/demo` returns.
- Root cause: run IDs embed a free-form label followed by a timestamp, so lexicographic order equals chronological order only when the label is byte-identical. `startswith` additionally sweeps in variants never intended as demo candidates (`dharavi_test_*`, `dharavi_phase*`, `dharavi_gate_b_*`). Sorting a *mixed* label space by name conflates two different orderings.
- Downstream propagation risk: the product's primary demo surface silently serves a test artefact with no staleness indicator, while `scheduler_status` continues reporting healthy.

**[Critical] C18 — A failed pipeline run is reported as success and leaves no artefact** (api.py:102-110; pipeline.py:195-198)
- What happens: `run_pipeline` handles its no-tiles case by **returning** `{"status": "failed", "error": ...}` rather than raising, and returns *before* `result.json` is written. The scheduler's `except Exception` therefore never fires and it prints `"[Scheduler] {label} refreshed OK."` The run directory was already created at pipeline.py:135, so the filesystem is left with an empty directory and no result.
- Root cause: two incompatible error conventions across the boundary — the pipeline signals failure **in-band** via a status field, the scheduler detects failure **out-of-band** via exceptions. Neither inspects the other's channel.
- Downstream propagation risk: compounds C17. Empty run directories accumulate; `get_latest_run` returns `None` if such a directory sorts last (making `/api/demo` 404 despite valid earlier runs existing), and operators reading scheduler output see uniform success.

---

### `pipeline.py` — Moderate and Minor

**[Moderate] The OSM label shim leaves `landcover_purity_pct` and the ambiguity fields describing the pre-override category** (pipeline.py:85-97, 396-400)
- What happens: `apply_osm_vector_labels` may rewrite `category` from `"unknown"` to `unpaved_dirt_road`/`open_drainage_channel`/`open_waste` — categories absent from the model's 7-class `landcover_map`. `landcover_purity_pct`, `ambiguous_pct`, and `ambiguous_between` were computed earlier against the model's map and are never recomputed. Verified on `dharavi_phase11_postfix_20260807_125913`: 2 segments carry `dominant_landcover_category: "unpaved_dirt_road"`, `label_source: "osm_vector"`, and `landcover_purity_pct: 0.0` — that 0.0 describes the vanished "unknown" state, indistinguishable in the schema from a genuine 0% purity.
- Root cause: the shim renames one field across the boundary, but the segment's other fields are *derived from* that field's old value. Its docstring reasons carefully about `label_source`/`osm_feature_type` provenance and about what "unknown" means, but never considers the derived statistics.
- Downstream propagation risk: purity is the schema's only per-segment confidence signal. For OSM-labelled segments it is silently meaningless — and always misleadingly *low*, so a consumer ranking by purity systematically buries exactly the segments whose labels came from a different, arguably more reliable evidence source.

**[Moderate] `risk.status` and its `reason` contradict the block's own contents and the vulnerability block** (pipeline.py:525-531)
- What happens: `risk_block` is hardcoded `status: "not_calculated"` with `reason: "...vulnerability has not been calculated (see vulnerability block)."` On a real run, `vulnerability.status` is `"available"`, `by_evidence_layer` holds five computed entries, and each per-layer reason correctly states "Hazard, exposure, and vulnerability are **all now available** ... but a fusion METHODOLOGY has not yet been defined." The top-level reason asserts the opposite of the layer-level reason directly beneath it.
- Root cause: the Phase 10B change moved vulnerability resolution before the loop and threaded it into `compute_risk()` (the comment at 451-455 documents fixing a `NameError` there), but the surrounding static `risk_block` literal was written pre-10B and never revised.
- Downstream propagation risk: a consumer reading only the top level is told vulnerability is missing when it is present, and is given the wrong reason for why risk is unavailable — masking the real, deliberate blocker (the Gate E methodology decision) behind a false data-availability claim.

**[Moderate] The documented SCHEMA v2.0 contract is stale — one claimed key absent, ten emitted keys undocumented** (pipeline.py:118-123)
- What happens: the docstring enumerates the v2.0 contract and warns "do not change without updating all consumers: App.jsx." Against real output: **`relative_elevation_proxy` is documented but not emitted** (it lives at `terrain_context.relative_elevation_proxy`), and ten emitted top-level keys are undocumented — `applicability`, `exposure`, `hydrological_surfaces`, `imagery_acquisition_date`, `observed_inundation`, `rainfall_climatology`, `risk`, `susceptibility`, `terrain_context`, `vulnerability`.
- Root cause: Phases 3–10B each added top-level blocks to `result.update()` without touching the contract docstring, while `relative_elevation_proxy` was demoted into `terrain_context` without removing it from the contract. `schema_version` stayed `"2.0"` throughout, so the version number cannot distinguish these shapes.
- Downstream propagation risk: confirmed live — see the `api.py` finding below where `/api/runs` emits `null` for all 130 runs because it was written against this docstring.

**[Moderate] `summary.dominant_category` ignores unknown and can name a 0.0% category** (pipeline.py:623-625)
- What happens: `max(category_area_pct.items(), key=lambda kv: kv[1])[0]`. `category_area_pct` holds only the 7 model classes (unknown is a separate key) and its denominator is *total* pixels — so on the verified run `dominant_category: "paved_road"` at 32.07% while 23.07% of the raster is unknown. If the model rejects everything, all seven values are 0.0 and `max` returns the first by insertion order, reporting a confident-sounding dominant category at 0% coverage. The `if category_area_pct` guard catches only an *empty* dict, never an all-zeros one.
- Root cause: "dominant" is an argmax over a partial distribution with no floor, tie-break, or comparison against `unknown_pct`.

**[Moderate] `summary.unknown_segments` is counted after the OSM override, under-reporting model uncertainty** (pipeline.py:622, 626-629)
- What happens: the count runs on post-override segments, so any segment the model marked unknown that OSM then relabelled is no longer counted. Verified: the run reporting `unknown_segments: 0` contains 2 segments overridden to `unpaved_dirt_road`, against `unknown_pct: 23.07`. Separately `standing_water_segment_count` sums `standing_water` (model-derived) and `open_drainage_channel` (obtainable *only* via OSM override), merging two evidence sources into one count.
- Root cause: summary statistics are computed against the final mutated segment list with no distinction by `label_source`, even though that field exists precisely to separate the two provenances.

**[Moderate] The 139MB checkpoint is loaded a second time purely for provenance, and any failure silently yields empty provenance** (pipeline.py:575-587)
- What happens: after inference completes, `torch.load(PRODUCTION_MODEL_PATH, map_location="cpu")` re-reads the full 139MB checkpoint for four metadata fields. A bare `except Exception` prints and leaves `training_cities=[]`, `loco_mean_miou=None`, `loco_std_miou=None`, `loco_n_folds=None`, which are then written into `landcover.model_provenance` as if genuine.
- Root cause: `load_production_model()` already parses this checkpoint and *prints* these fields, but returns only `(model, categories, num_classes)`, so the metadata is discarded and must be re-read. The defaults are indistinguishable from genuine absence.
- Downstream propagation risk: empty `training_cities` and null mIoU read as "this model has no recorded validation" when it may be a transient read failure. With C10, this is the second place model provenance degrades silently rather than loudly.

**[Minor] `run_event_hazard_analysis` is unreachable from every entry point** (pipeline.py:801, 901-904) — the only occurrence of the name repo-wide is its own `def`; `--mode` accepts only `{landcover, inundation}` and `api.py` never calls it. The whole Phase 9 path is dead unless imported manually.

**[Minor] `get_osm_features`'s GeoJSON writes sit outside all exception handling** (osm_dem.py:107-121, called at pipeline.py:215) — network calls are individually wrapped but `gpd.GeoDataFrame(...)` / `.to_file(...)` are not, and there is no top-level `try`. A driver/permission/disk failure aborts `run_pipeline` *after* the Sentinel-2 download and tiling have already run. Root cause: the defensive posture covers the expected failure (Overpass down) but not local IO on the success path.

**[Minor] No AOI bbox validation at any entry point** (pipeline.py:100-110, 891-894) — `west/south/east/north` pass straight from argparse into `aoi_from_bbox`, into `ee.Geometry.Rectangle` at line 465, and into every lon/lat↔pixel conversion. Module 1 established `sentinel2.py:184-197` does not validate either, so **no layer owns it** (see also the `api.py` finding below).

#### Explicit negative results — `pipeline.py`

- **Mosaic placement math is correct.** `tiler.py`'s `range(0, height, tile_size)` with `min(row+tile_size, height)` clamping produces non-overlapping tiles that exactly tile the raster; `landcover_map_full[row_off:row_off+t_h, col_off:col_off+t_w] = ...` is exactly right, edge tiles included. The comment at 300-303 is accurate.
- **Distance-map slicing shapes are correct.** `compute_road_distance_map` returns `(img_height, img_width)` and is called positionally as `(..., full_width, full_height)` matching its parameter order, so each slice is exactly `(t_h, t_w)`. `run_inference`'s shape-mismatch warning path cannot trigger from this call site.
- **Road-access scores use the correct coordinate space.** Scores are computed with tile-local bboxes against the tile-local slice *before* bboxes are offset to global space — correct ordering. `_apply_osm_labels_to_segments` is then called with already-global bboxes and full dimensions, also correct.
- **None-propagation into pluvial is handled properly.** `compute_pluvial_susceptibility` guards each of `relative_elevation_score`, `rainfall_mean_annual_mm`, and `waterway_dist_map` for `None`, excluding the component and recording it in `components_excluded` rather than doing arithmetic on `None`.
- **The direct-index accesses are safe.** `applicability['urban_landcover_model']['status']`, `hydrological_surfaces['impervious_fraction_pct']`, and `vulnerability_block['status']` are guaranteed by their producers; the `['dimensions'][...]` access at 712-713 is correctly guarded by a `status == "available"` check.
- **The shim's `pop` is safe on the current call path.** `build_segments_with_landcover` unconditionally sets `dominant_landcover_category`, and `apply_osm_vector_labels` returns the same list object it was given (including on its early-return path), so the round-trip cannot lose segments or raise `KeyError`.

---

### `api.py` — Moderate and Minor

**[Moderate] Scheduler starts at import time with defaults that make a 5-day job unlikely to ever fire** (api.py:114-117)
- What happens: `scheduler.start()` runs on module import, not in a startup event. The documented launch command is `uvicorn api:app --reload`; every reload re-imports and restarts the scheduler, resetting `next_run_time` to now+5 days. api.py overrides **none** of APScheduler's job defaults — confirmed in the installed 3.11.2 source (`schedulers/base.py::_configure`): `misfire_grace_time=1` **second**, `coalesce=True`, `max_instances=1`. On a laptop that sleeps — the documented target environment — a fire time missed by more than one second is a misfire, silently skipped for another full interval.
- Root cause: the job is configured for a 5-day cadence but inherits grace/instance defaults designed for sub-minute jobs, and its lifecycle is bound to import rather than to the application lifespan.
- Downstream propagation risk: under `--workers N` each worker imports the module and starts its **own** scheduler, so N concurrent `refresh_all_watched_aois` runs would write into the same output tree. Any test or tool that imports `api` also silently spawns a scheduler thread capable of launching pipelines.

**[Moderate] `trigger_refresh` is unauthenticated, returns success unconditionally, and is silently dropped if a job is already running** (api.py:276-280) — an unauthenticated POST launches three full pipeline runs. With `max_instances=1`, a trigger issued mid-run is refused by APScheduler, which logs a warning through the `apscheduler` logger that api.py never configures, while the endpoint still returns `{"status": "refresh triggered"}` with HTTP 200. Root cause: the handler reports the *scheduling call's* success rather than the job's admission, and no logging is configured, so the only failure signal is discarded.

**[Moderate] `MAX_AOI_AREA_KM2 = 100.0` permits AOIs 20× larger than the download path documents as safe** (api.py:47) — see the C2 re-assessment in the priority list. Root cause: the limit was chosen against an earlier degree-based intent without reference to `tiler.py`'s stated constraint; the two were never reconciled.

**[Moderate] No coordinate-range validation anywhere, and api.py is the last line of defence** (api.py:120-147, 174, 205) — both handlers check only ordering (`west >= east`, `south >= north`). Nothing constrains latitude to [-90, 90] or longitude to [-180, 180]. Root cause: validation was assumed to sit in the Pydantic layer, but the models declare bare `float` with no `Field(ge=..., le=...)` and no validators. A degenerate or wrapped EE geometry then propagates into tiling, OSM fetch, and every lon/lat↔pixel conversion, surfacing as an opaque GEE error rather than a 400.

**[Moderate] `/api/runs` reports `relative_elevation_proxy_score` as `null` for every run** (api.py:251)
- What happens: the handler reads `data.get("relative_elevation_proxy", {}).get("score")`. Verified against `dharavi_test_20260806_114208/result.json`: there is no top-level `relative_elevation_proxy` key; the value lives at `terrain_context.relative_elevation_proxy.score` (real value `0.4481`). The endpoint emits `None` for all 130 runs.
- Root cause: api.py was written against `run_pipeline`'s **docstring** contract, which lists `relative_elevation_proxy` as top-level (pipeline.py:117-123) — but the code writes it nested. The consumer trusted documentation the producer had drifted from. This is the stale-schema finding above, confirmed causing real breakage.

**[Moderate] `/runs` static mount exposes the entire pipeline output tree, contradicting its own comment** (api.py:26-32) — the comment says it serves "landcover.png, landcover_confidence.png, etc."; it mounts the whole directory. Actual served inventory: 468 `.json`, 437 `.png`, 237 `.geojson`, 142 `.tif`, 76 `.npy` — including `raw.tif` source imagery, `annotations.json` (human labels), `masks.json`, and OSM geojson. Root cause: the mount is directory-granular while the intent was file-type-granular.

**[Moderate] `/api/runs` re-reads and re-parses every run on every request** (api.py:231-253) — 130 `result.json` files totalling ~5.1 MB opened and `json.load`ed synchronously per call, to project 9 scalar fields. Cost grows unbounded with run count.

**[Moderate] Relative paths make behaviour depend on the server's working directory** (api.py:31-32, 82, 233, 258) — `"data/pipeline_runs"` is relative in the static mount, `get_latest_run`, `list_runs`, and `get_run`. Launching uvicorn from another directory silently creates and serves an empty tree. Root cause: no anchor to `Path(__file__).parent`.

**[Minor] `analyze` returns HTTP 200 for a failed pipeline** (api.py:196) — `result` is returned verbatim, so the in-band `status: "failed"` case reaches clients as success. Same root cause as C18.

**[Minor] 500 responses leak raw internal exception text** (api.py:198, 228) — `HTTPException(500, detail=str(e))` forwards GEE errors and filesystem paths to the client.

**[Minor] `root()` will 500 if the job is missing, while `scheduler_status()` guards for it** (api.py:151 vs 271) — inconsistent defensiveness against the same condition.

**[Minor] `str = None` / `float = None` annotations misdeclare optionality** (api.py:125-126, 147) — omitting the field yields `None`, but explicitly sending `"start_date": null` fails validation with a 422. `Optional[str]` was intended.

**[Minor] `get_run` allows limited traversal** (api.py:258) — Starlette's default `str` path convertor excludes `/`, blocking multi-segment traversal, but `run_id=".."` resolves to `data/result.json`. Constrained to files literally named `result.json`.

**[Minor] No date-format validation** (api.py:125-126, 140-143) — date strings pass unchecked to GEE, surfacing as 500s.

#### Explicit negative results — `api.py`

- **The event loop is not blocked.** Every handler is `def`, not `async def`, so FastAPI runs them in the anyio worker threadpool. The obvious hypothesis does not hold. (Residual minor: long runs occupy threadpool workers, default 40.)
- **There is no remote-kill endpoint.** `shutdown` (283-285) is `@app.on_event("shutdown")`, a lifecycle hook — not a route. It calls `scheduler.shutdown()` cleanly.
- **`compute_aoi_geodesics` math is correct.** `pyproj.Geod(ellps="WGS84")`, `polygon_area_perimeter` returns m² (correctly `abs()`-ed and ÷1e6), and `geod.inv` returns `(az12, az21, dist_m)` with the third element correctly unpacked as metres. No degree/radian or earth-radius error. Inherent nuance: constant-latitude edges are not geodesics, so polygon area marginally understates a true lat/lon box — negligible at ≤100 km².
- **One AOI's failure does not kill the refresh loop.** The `try/except` is correctly scoped *inside* the `for`.
- **No unguarded shared mutable state in api.py.** `WATCHED_AOIS` is read-only; `get_demo` mutates a freshly-parsed dict per call. The scheduler thread and request handlers share no mutable structure.

---

### Cross-module observation: no layer owns validation or error convention

Two structural patterns account for a disproportionate share of this module's
findings, and both are boundary problems rather than defects in any one file.

**1. Validation is assumed to live in the adjacent layer, by both layers.**
`api.py`'s Pydantic models type-check floats and stop; `pipeline.py` passes
coordinates straight through; `sentinel2.py::aoi_from_bbox` (Module 1) does no
validation either. The same holds for `aoi_label` (C16): a display label to the
API, a path component to the pipeline, sanitised by neither.

**2. Errors are signalled in-band and detected out-of-band.**
Modules 1 and 2 established that ingestion functions return
`{"status": "unavailable", ...}` on any exception rather than raising.
`run_pipeline` follows the same convention for its own failure (C18), while its
*callers* — the scheduler, and `analyze`'s `try/except` — detect failure by
exception. The result is that a failure at any stage is representable in the
output schema but invisible to the control flow, which is why so many findings
across all three modules take the form "a plausible-looking value reaches
`result.json` with a confident `status` field." C14 is the sharpest instance:
the one component built specifically to detect and gate on untrustworthy input
emits its verdict into the same in-band channel, where nothing reads it.

---

## Downstream Analysis Module

Scope: `susceptibility/` (6 files + 6 constants files), `exposure/compute.py`,
`risk/compute.py`, `perception/` (3 files), `zonal/` (2 files +
`zonal_constants.py`), `boundaries/ingestion.py`. This layer is explicitly
gated per `PROJECT_GATES.md` (Gate C waived, Gates D/E not started) and
labeled "screening/experimental".

### Reachability

| File | Status |
|---|---|
| `susceptibility/{pluvial,fluvial,coastal,flash_flood,waterlogging}.py` | **LIVE** |
| `susceptibility/event_hazard.py` | **DEAD** — only reachable via `run_event_hazard_analysis`, which Module 3 confirmed is unreachable from every entry point. Severities capped. |
| `exposure/compute.py`, `risk/compute.py`, `perception/*`, `zonal/*`, `boundaries/ingestion.py` | **LIVE** |

### The central question: is "unavailable" silently treated as a valid zero?

The answer is **mixed, and the split is instructive**. Modules whose upstream
returns a `status` field handle unavailability correctly and often
exemplarily. Modules whose upstream has *no* status field cannot, and that is
where every Critical in this module clusters.

| Consumer | Upstream carries `status`? | Handling |
|---|---|---|
| `fluvial.py` ← `hand_context` | Yes | **Correct** — gates on status, propagates the error string |
| `coastal.py` ← `coastal_context` | Yes | **Exemplary** — distinguishes unavailable / not-applicable / low |
| `flash_flood.py` ← 3 contexts | Yes | **Correct** — double-guards status *and* value |
| `exposure/compute.py` ← population | Yes | **Correct** — `None`, never a fabricated 0 |
| `waterlogging.py` ← `hydrological_surfaces` | **No** | **Broken** (C21) — cannot detect failure |
| `applicability.py` ← `hydrological_surfaces` | **No** | **Broken** (C21) — same vacuous guard |
| `zonal` ← `category_area_pct` | **No** | **Broken** (C25) — empty dict → 0.0 |

The root cause is one design gap, not seven bugs:
`perception/hydrological_surfaces.py` is the only module in the analysis chain
with **no `status` field and no failure path**. Every consumer downstream of it
inherits an undetectable failure mode.

---

### Critical findings

**[Critical] C19 — `impervious_fraction_pct` is deflated in proportion to the unknown rate, biasing informal settlements toward looking less flood-prone** (perception/hydrological_surfaces.py:21, 33-45)
- What happens: confirmed by signature — the function receives *only* `category_area_pct` and never `unknown_pct`. Modules 2/3 established that dict uses a **total-pixel** denominator (summing with `unknown_pct` to 100%). Worked concretely: an AOI 60% roofing / 20% paved over *classified* pixels, at 50% unknown, yields `category_area_pct` of ~30%/~10%, giving `impervious_fraction_pct ≈ 0.9(30) + 1.0(10) = 37.0` instead of ~74.0 — a factor-of-two understatement. The function cannot compensate even in principle; the information is not passed to it.
- Root cause: the input contract is a percentage dict whose **denominator convention is invisible at the call site**. `pipeline.py:412` passes `inference_result["category_area_pct"]` with no indication its denominator includes rejected pixels, and the docstring never states which convention it assumes. Module 2 recorded that `resnet_classifier.py` computes the identically-named field over *known* pixels — so two conventions coexist in the codebase under one key name, and this consumer silently inherits whichever it is handed.
- Downstream propagation risk: the error direction is the dangerous one. Higher unknown → lower reported imperviousness → an informal settlement reads as **more permeable, i.e. less flood-prone**. Module 2 established the `paved_road`/`dense_informal_roofing` confusion is the dominant driver of unknown mass, so the bias is worst exactly in the dense informal settlements the product targets. Flows to `susceptibility/waterlogging.py:79` as a direct score input and into `result.json` with no uncertainty band; recomputed on the same basis at `zonal/landcover_screening.py:492`, so ward screening inherits it.
- **Compounding disclosure failure (folded into this entry rather than listed separately):** the returned `limitations` list carries three real caveats — uncalibrated weights, aggregate-vs-per-pixel coarseness, deliberate exclusion of `active_construction` — and omits this, the largest error source. The limitations were written against the *method* rather than the *input's properties*. Given this project's stated honesty discipline, detailed-but-materially-incomplete labelling is worse than none, because it signals the caveats have been enumerated.

**[Critical] C20 — The OOD verdict does not gate the sibling mechanisms in its own returned dict** (perception/applicability.py:44-60, 133-143, 150-154)
- What happens: `landcover_status` can be `out_of_distribution` ("semantic model output is unreliable for this scene") while, **in the same returned dict**, `pluvial.status` is `applicable` and `waterlogging.status` is `applicable`. Both consume `hydrological_surfaces`, derived entirely from the landcover output just declared unreliable. Confirmed by reading: `landcover_status` is assigned at 44-60 and never referenced again.
- Root cause: the six mechanism blocks are computed as independent branches over their own input availability, with no dependency graph. The module is organised "one block per mechanism" rather than "one block per evidence chain," so the fact that pluvial and waterlogging *transitively depend on* the landcover model is represented nowhere.
- Downstream propagation risk: the second-order form of C14. Even a consumer that *does* honour applicability — `zonal/landcover_screening.py:240` attempts to — reads `waterlogging: applicable` and proceeds, because the OOD flag sits in a sibling key it has no reason to consult.

**[Critical] C21 — The impervious availability guard is vacuous, so a failed landcover model reads as confirmed permeable terrain** (perception/applicability.py:133-137 and susceptibility/waterlogging.py:55-58, 78-81)
- What happens: both sites guard on `hydrological_surfaces.get("impervious_fraction_pct") is not None`. But `compute_hydrological_surfaces` **always** returns a float — `impervious_total` initialises to `0.0` and `round(0.0, 2)` is `0.0`, never `None`; there is no code path returning `None` and no `status` field. `pipeline.py:412-420` computes and passes it unconditionally. Therefore `waterlogging_status` is **unconditionally `"applicable"`** in every production run, `impervious_available` is unconditionally `True`, and both modules' `insufficient_evidence` branches are dead code. A total landcover failure scores as `impervious_score = 0.0`, dragging waterlogging susceptibility **down** as though the AOI were confirmed permeable.
- Root cause: an `is not None` check applied to a value the producer guarantees is always present. The guard was written as if `compute_hydrological_surfaces` had a failure mode returning `None`; it has no failure mode at all. Two modules written to different assumptions about the same contract — and the identical defective guard is duplicated, so the chain **fails open twice**.
- Downstream propagation risk: the clearest instance in this module of unavailability becoming a real number. Compounds C14 (OOD gates nothing) and C19 (denominator deflation): the mechanism most sensitive to imperviousness is biased downward exactly where classification is least reliable, reporting `status: "experimental"` throughout.

**[Critical] C22 — Infiltration deficit assigns the maximum value to no-data and deliberately-unweighted classes** (susceptibility/pluvial.py:48-52)
- What happens: `infiltration_px` is zero-initialised and only `dense_vegetation` (1.0) and `vegetation_clearing` (0.3) are populated. `infiltration_deficit_px = 1.0 - infiltration_px` therefore assigns **1.0, the maximum deficit**, to every other value — `paved_road`, `standing_water`, `active_construction`, both roofing classes, *and* `UNKNOWN_INDEX` (255), which is not in `cat_to_idx` at all. For `paved_road` this is physically right; for `active_construction` and no-data it is not. `configs/applicability_constants.py:60-63` states active_construction is "deliberately excluded... guessing a fixed weight would be worse than omitting it" — but omission on the *inverted* surface is not neutrality, it is a worst-case assumption.
- Root cause: one zero-initialised default serves two surfaces of **opposite polarity**. On the impervious surface, 0 means "contributes nothing" (conservative, matching stated intent). On the infiltration surface, the `1.0 - x` inversion flips that same default into "contributes maximally to susceptibility." The constants file reasons carefully about the first case and never notices the inversion.
- Downstream propagation risk: `susceptibility_map` is the **only per-pixel spatial susceptibility product in the entire system** and is written to PNG for display. Every no-data pixel renders as maximum pluvial susceptibility, visually indistinguishable from genuine high risk. Since unknown mass is driven by the roofing/road confusion, the pixels the model is *least* certain about are painted the *most* alarming. Partial mitigation: `aoi_mean_score` excludes unknown pixels, so the scalar is protected — but `active_construction` and `standing_water` are valid indices and *are* included at deficit 1.0.

**[Critical] C23 — `product_validation_status` is omitted from exposure's `not_calculated` return path** (exposure/compute.py:118-125)
- What happens: the module docstring states every caller "MUST propagate the `product_validation_status` field... so the waiver cannot silently disappear." The early return emits only `layer_id`, `label`, `status`, `reason` — the field is absent. A consumer doing `result["product_validation_status"]` raises `KeyError`; one doing `.get()` receives `None`, indistinguishable from "Gate C passed / no waiver applies."
- Root cause: the Gate C constant is injected while constructing the *success* dict (line 143) rather than attached to every exit path. The guard clause predates the field and was never revisited — so the one path meaning "we could not compute this" is also the one that loses the honesty label.
- Downstream propagation risk: any layer whose susceptibility status is `not_calculated` — e.g. coastal for an inland AOI, a routine case — produces an exposure entry with no waiver marker.

**[Critical] C24 — The frontend surfaces exposure with no Gate C / screening label at all** (geowatch-ui/src/App.jsx:463-549)
- What happens: verified by grep, `product_validation_status` occurs **0 times** in `App.jsx`. `SecExposure` renders population, built-up, roads, and facilities with per-component status badges and a `CaveatList` of `layer.limitations`, but never reads or displays the Gate C field. PROJECT_GATES.md states: *"Until Gate C is actually passed: exposure output must continue to be labeled 'screening/experimental' everywhere it's surfaced (frontend, result.json, any report)."* The headline metric renders as "Estimated people" with an `available` badge and no gate qualifier. The *susceptibility* panel does carry an experimental marker (App.jsx:446), so the discipline exists in the same file and simply was not applied here.
- Root cause: the requirement is enforced only by prose in a Python docstring and a Markdown gate file. Nothing in the data path makes the field hard to ignore — it is one optional key among a dozen, and the frontend was written by selecting the keys it wanted. A contract depending on every future consumer reading a docstring fails at the first consumer written without it, which is what happened.
- Downstream propagation risk: precisely the outcome the waiver text was written to prevent — Gate C's waiver disappearing as layers are built on exposure. Mitigating: `result.json` **does** carry the field on the success path, so the data is present and recoverable; only the surfaced product omits it.

**[Critical] C25 — A ward with no classified pixels yields `impervious_fraction_pct = 0.0` and a fully-computed susceptibility score** (zonal/landcover_screening.py:484-492)
- What happens: `category_area_pct` is built from `np.unique(ward_landcover)` keeping only `0 <= idx < len(categories)` — index 255 correctly excluded — but the *denominator* is `ward_landcover.size`, all pixels. A 100%-UNKNOWN ward produces `category_area_pct = {}`. `pixel_count > 0`, so the zero-pixel guard at line 439 does not fire. `compute_hydrological_surfaces({})` uses `.get(cat, 0.0)` throughout and returns `impervious_fraction_pct: 0.0` with no status field, which then feeds `compute_waterlogging_susceptibility` as if measured. **Not hypothetical**: the only reusable run on disk is 55.1% UNKNOWN, so partially- and wholly-unknown wards are the expected case.
- Root cause: "absence of evidence" and "evidence of absence" are collapsed at dict construction. An unknown pixel contributes to the denominator but to no key, so heavy unknown coverage is arithmetically indistinguishable from genuinely low impervious cover. `compute_hydrological_surfaces` compounds it by defaulting every missing category to `0.0`.
- Downstream propagation risk: for a dense urban ward, `impervious_fraction_pct = 0.0` does not merely lose precision — it **inverts the physical reality** and drives waterlogging susceptibility toward the safe end.

**[Critical] C26 — No per-ward unknown fraction is reported anywhere in the output** (zonal/landcover_screening.py:514-541)
- What happens: the ward dict contains `pixel_count`, `category_area_pct`, `hydrological_surfaces`, `pluvial`, `waterlogging`, `shared_aoi_context`, `source_observation_quality`, `source_run_id` — but **no `unknown_pct`, no valid-pixel count, no minimum-coverage flag**. The only way to infer unknown coverage is to notice `category_area_pct` sums to well under 100 and subtract — an inference no consumer is told to make. A ward at 5% classified is schema-identical to one at 95%.
- Root cause: `category_area_pct` was modelled on `inference.py`'s AOI-level output, which pairs it with a sibling `unknown_pct`. The per-ward re-derivation reproduced the percentage dict but not its companion field, so the total-pixel denominator convention arrived without the context that makes it interpretable.
- Downstream propagation risk: this is the field that would make C25 visible. Its absence converts a detectable data-quality problem into an invisible one, and directly contradicts the module's own stated principle of surfacing limitations "explicitly ... so a reviewer isn't misled" (line 480).

**[Critical] C27 — A GEE timeout and genuine data absence are indistinguishable, making ward hazard tiers non-reproducible** (zonal/hazard_screening.py:284-339)
- What happens: on timeout, `_timed_out_context` returns `{"status": "unavailable", "error": "GEE call timed out after 90s."}`. That reaches `compute_*_susceptibility`, which returns `insufficient_evidence`. The ward block is then assembled from the *susceptibility result only* — `status`, `score`, `tier`, `method`, `source` — so the `error` string identifying the timeout is **never propagated**. Comparing two real outputs of the same 24 wards on disk: `phase12a_ward_screening.json` has fluvial `{experimental: 24}` and coastal `{experimental: 24}`; `_v3.json` has fluvial `{experimental: 23, insufficient_evidence: 1}` and coastal `{experimental: 21, insufficient_evidence: 3}`. Tier distributions shift too (coastal `very_high` 4→3, `high` 8→7; flash_flood `high` 5→6). **Same wards, same deterministic inputs, different answers.**
- Root cause: the timeout is correctly converted into a status-carrying dict (good), but the ward-block constructors read only the susceptibility function's return value, discarding the context dict's provenance. The docstring says a timeout is "surfaced as status=unavailable with an honest reason, never silently skipped" — the status survives the boundary, the reason does not.
- Downstream propagation risk: a reviewer cannot tell whether a ward is `insufficient_evidence` because MERIT Hydro lacks coverage there or because a wall-clock ceiling fired on a slow network. Because the boundary is wall-clock rather than data-dependent, ward hazard tiers are not reproducible — serious for output feeding "screening/experimental" decision support.

---

### Moderate and Minor — by file

#### `susceptibility/pluvial.py`
- **[Moderate] The `insufficient_evidence` branch is unreachable; pluvial always returns a score** (pluvial.py:105-108) — `impervious` (w=1.0,q=0.7) and `infiltration_deficit` (w=0.8,q=0.7) are added **unconditionally** at 71-79, so `denominator ≥ 1.26` always. Pluvial returns `status: "experimental"` with a real score even when rainfall, relative elevation, *and* drainage distance are all unavailable — a score from land cover alone. Root cause: the two landcover components have no availability guard because `landcover_map` is a required positional arg assumed valid; C14 established "the map exists" ≠ "the map is trustworthy."
- **[Moderate] The evidence basis changes silently while status, class breaks, and output shape do not** (pluvial.py:105-122) — renormalisation preserves *scale* but not *evidential weight*; a 0.6 from two components and from five map to the identical `"high"` label. Only signal is the free-text `components_excluded`.
- **[Minor] Availability is inferred from `is not None`, never `status`** (pluvial.py:54-64) — safe today because pipeline extracts scalars whose unavailable forms are `None`, but nothing enforces the contract.
- **[Minor] Amplifies C7** (pluvial.py:83) — `drainage_px` is the per-AOI-max-normalised waterway distance map.

#### `susceptibility/fluvial.py`
- **[Moderate] A MERIT `upa` data gap is reported as a physical finding about the AOI** (fluvial.py:58-64) — `river_connected = max_upstream_area_km2 is not None and >= threshold`, so a `None` from a data gap collapses to `False` identically to genuine low upstream area, and the module then appends "this AOI may not be meaningfully river-connected." Root cause: a three-state input (no data / below / above) collapsed to a boolean at the producer, with the consumer's prose interpreting `False` as the physical case only.

#### `susceptibility/coastal.py`
- **[Moderate] Losing FABDEM halves the evidence base with no change to status or class semantics** (coastal.py:93) — `sum(scores)/len(scores)` over one or two entries, still `status: "experimental"` with `method: "distance_and_elevation_unweighted_average"` naming a component that was not used.
- **[Minor] Error interpolation assumes an `error` key exists** (coastal.py:52-53).

#### `susceptibility/flash_flood.py`
- **[Moderate] A slope-only score is presented identically to a three-component one** (flash_flood.py:101) — same rebasing plus a static `method` string naming absent components.
- **[Moderate] Three "independent" mechanisms are driven by two shared inputs** — the same `hand_context` supplies fluvial (mean HAND), flash_flood (upstream area) and waterlogging (mean HAND, inverted); the same CHIRPS `mean_annual_mm` supplies pluvial, flash_flood and waterlogging, each normalised by a **different** provisional ceiling (4500/2500/2500 mm). The dual HAND interpretation is documented and defensible; the shared-rainfall coupling is documented nowhere. Root cause: mechanisms added phase-by-phase, each reusing already-fetched context "for free," with no cross-mechanism independence review. Downstream: `pipeline.py` treats each as a separate evidence layer, so agreement between layers is partly an artefact of shared inputs — a reader seeing four of five score "high" may read convergent evidence where there is one number re-expressed.

#### `susceptibility/waterlogging.py`
- **[Moderate] The `insufficient_evidence` guard is unreachable** (waterlogging.py:60-64) — cannot be true given C21.
- **[Minor] A "shared" constant is physically duplicated** (configs/waterlogging_constants.py:30-33) — `FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM = 2500.0` re-declared as a literal with a comment claiming it is shared; tuning one silently diverges the two mechanisms.

#### `susceptibility/event_hazard.py` (dead — capped)
- **[Moderate] Ceiling saturation makes event conditioning a silent no-op** (event_hazard.py:51,58) — `min(1.0, rainfall_mm/800.0)`; the constants file records a real Dharavi run at 1506.8 mm saturating to exactly 1.0, so `hazard_score == susc_score` identically while `method` still implies conditioning occurred. No field records the ceiling was hit.
- **[Minor] `compute_coastal_event_hazard` accepts an argument it never reads** (event_hazard.py:136).
- **[Minor] Reason text overstates the pluvial stub case** (event_hazard.py:44).

#### Module-wide (susceptibility)
- **[Moderate] `_classify` is duplicated six times and its fallback fails toward alarm** — a score outside all breaks returns `"very_high"`. Latent (every module clamps), but six copies means any change must be applied six times.
- **[Moderate] All five mechanisms use byte-identical class breaks** (0.2/0.4/0.6/0.8) despite different inputs, component counts, normalisation ceilings, and physical meanings — implying a cross-mechanism comparability the scores do not support. Every constants file is candid that its numbers are provisional and unvalidated, which is why this is Moderate rather than Critical.

#### `exposure/compute.py`
- **[Moderate] An unavailable facilities context yields `count: 0` while population and roads correctly yield `None`** (exposure/compute.py:243-247) — "0 hospitals, clinics and schools" is a substantive finding; `None` is not. Root cause: the failure branch mirrors the *type* of `len(...)` rather than its epistemic status. **Currently contained** — `SecFacilities` renders only when `status === 'available'` (App.jsx:538-546).
- **[Moderate] The known-model-confusion caveat is attached to the wrong branch** (exposure/compute.py:197-211) — when GHSL is *unavailable*, a note warns the built-up figure "reflects GeoWatch's own model only, which has known... limitations (see the documented paved_road/roofing confusion)." When GHSL *is* available, the code records `agreement_status: "not_yet_compared"` — no comparison ran — and the caveat is dropped, while the frontend renders "cross-checked against an independent global dataset... though the two haven't been formally compared yet." Root cause: the caveat was written to explain *why the reference is missing* rather than as a property of the GeoWatch figure, which is equally unvalidated in both branches. The presence of an uncompared reference reads as corroboration.
- **[Moderate] `built_up` limitations land in a nested key no consumer merges** (exposure/compute.py:202) — assignment to `components.built_up.limitations` while population's are `extend`ed into the top-level list the frontend actually renders.
- **[Minor] `EvidenceLayer` validates nothing** (exposure/compute.py:49-69) — the real protection against merging is the *function signature* taking exactly one layer, not this class.

#### `risk/compute.py`
- **[Moderate] `exposure_product_validation_status` is emitted only on the final return; all three gate returns drop it** (risk/compute.py:56-79 vs 100) — same structural cause as C23. Low impact today since every gate return means no risk number exists, but it establishes the pattern in the layer the docstring calls the most consequential output.

#### `perception/`
- **[Moderate] Empty/missing input yields `0.0` with no status field** (hydrological_surfaces.py:34,42,48-50) — `{}` returns `0.0`/`0.0` with `validated: False` and no error indication, unlike essentially every other module in the codebase.
- **[Moderate] `pluvial` applicability is a hardcoded `"applicable"`** (applicability.py:150-154) — no input influences it; the reason string is honest that no exclusion criteria exist, but `status` encodes a placeholder in the same vocabulary as a computed result.
- **[Moderate] `in_distribution` is returned with `reason: None` at up to 44.9% unknown** (applicability.py:44-60) — both constants are self-documented as "NOT empirically validated yet -- provisional," and production values sit near this cliff.
- **[Moderate] `observed_inundation` returns `status: "experimental"` when only the JRC historical baseline is available** (observed_inundation.py:30-33) — i.e. when there is no event-specific evidence at all. Partially mitigated: `probable_new_inundation_pct` is honestly `None` and `components_excluded` records the reason.
- **[Minor]** docstring/`Args` omissions (applicability.py:29-40); `None`-comparison without guard (44,51, latent); `"None"` rendered in exclusion text (observed_inundation.py:38,66); `or 0.0` conflating falsy-zero with absent (observed_inundation.py:74,84, latent).

#### `zonal/`
- **[Moderate] Coverage is checked against `result["aoi"]` but wards are rasterized against `raster_info["bounds"]`** (landcover_screening.py:183 vs 407) — measured on the real candidate run these differ by up to 8.7e-05° against a pixel size of 8.98e-05°/px, i.e. **~0.97 pixel**, in inconsistent directions per edge. Sub-pixel today, but the coverage gate validates a rectangle that is not the one being sampled.
- **[Moderate] `landcover_screening.py` hardcodes `gid`/`name` while `hazard_screening.py` reads them from the manifest** (landcover_screening.py:564-565 vs hazard_screening.py:394-395) — the boundary layer's manifest indirection is honoured in 12A and bypassed in 12B.
- **[Moderate] A timed-out wide run is abandoned but keeps writing into the reuse directory** (landcover_screening.py:89-96) — the daemon thread is not cancellable and continues writing; if it later completes it becomes a Case 1 candidate having never been quality-gated. Explains the `113543` artefact (arrays present, `result.json` absent).
- **[Moderate] An in-band pipeline failure is reported as a quality-gate failure** (landcover_screening.py:325-339) — fails closed (correct) but misattributes the cause. See the C18 re-assessment.
- **[Moderate] Ward-loop exceptions are unhandled, unlike the sibling module** (landcover_screening.py:607-616) — `hazard_screening.py:413-431` degrades one ward to `status: "failed"`; here a shape mismatch aborts the entire screening. No assertion that `.npy` shape equals `raster_info` dimensions (it matched on real data).
- **[Moderate] `manifest.json` opened without the existence check applied to its sibling** (hazard_screening.py:161-169).
- **[Minor]** "Case 1/2/3 planner" documented but no Case 2 exists (landcover_screening.py:14-16); stale `ASSUMPTION:` blocks contradicting `CONFIRMED` annotations in the same file (29-34, 573-579); `categories is None` degrading to an empty result (483,488); `_tier_from_score` dead (hazard_screening.py:212-232); `run_ward_hazard_screening` returns `status: "available"` unconditionally even if all 24 wards failed (437); `WIDE_RUN_DATE_END` bound at import time despite a comment requiring call-time resolution (zonal_constants.py:57).

#### `boundaries/ingestion.py`
- **[Moderate] A boundary layer from a different city returns `status: "available"` with zero intersecting units and no warning** (boundaries/ingestion.py:299-321) — structurally identical to a legitimate empty result. Nothing prevents a wrong-city layer being used silently, though it produces an empty rather than a wrong result.
- **[Moderate] Registry `expected_feature_count`/`expected_geometry_type`/`expected_crs` are never compared against the ingested file** (197-240) — recorded into the manifest but never asserted.
- **[Moderate] A hash mismatch still stores the layer and returns `status: "available"`** (210-260) — the docstring's "Does NOT proceed to save anything if validation fails" is literally true (mismatch is not part of `validation`) but misleading. `declared_hash is None` also makes the check vacuous for custom manifests.
- **[Moderate] The overlap scan mixes label-based and positional indices** (108-127) — `iterrows()` yields labels, `sindex.intersection` yields positions, compared directly. **Benign today** (GeoJSON read yields a clean `RangeIndex`), wrong the moment the frame is filtered or re-indexed.
- **[Minor]** geometry type recorded but never constrained to polygonal (63,142-148); `manifest.json` opened without existence check (282-289); null IDs double-counted as duplicates (87,91 — verdict still correct, only diagnostics misleading).

---

### On the "never auto-merged" exposure rule

**The rule holds — nothing merges the layers — but the separation is largely nominal, and the frontend's framing overstates it.**

Verified across the code path and empirically on real output:
- `exposure/compute.py` accepts exactly one `EvidenceLayer` and never sums, maxes, or reduces across layers. The protection is the **function signature**, not the `EvidenceLayer` class (which validates nothing).
- `risk/compute.py` sees one hazard and one exposure at a time.
- `zonal/*` never touches exposure; `hazard_screening.py:447` explicitly lists exposure, vulnerability and risk in `not_calculated_in_this_phase`.
- The frontend uses a **layer picker** (`activeLayer`), not an aggregate.

However, on `ward_pilot_timing_20260809_113812`:

```
5 layers: pluvial, fluvial, coastal, flash_flood, waterlogging
distinct 'components' blocks across the 5 layers: 1
distinct 'limitations' tuples:                    5
```

All five layers carry **identical** component values (`pop = 427459` in every
one), because every layer uses the same AOI-wide scalar footprint rather than a
per-hazard spatial mask. The separation is real in *labelling* (5 distinct
limitations) and absent in *values*.

**[Moderate] The frontend's layer picker implies per-hazard exposure counts that do not differ** (App.jsx:481)
- What happens: the explanatory text reads *"Pick a flood type below to see the count relevant to that specific risk."* Toggling layers shows the identical population, built-up, roads and facilities figures every time. The per-layer `limitations` do disclose this ("Exposure computed against the FULL AOI, not a spatial hazard footprint"), but the interaction affordance asserts a per-hazard specificity the data does not have.
- Root cause: the UI was built against the *schema* (five sibling layers implying five distinct results) rather than against the values, which are five copies distinguished only by caveat text.
- Downstream propagation risk: a user toggling five layers and seeing the same number may read it as five independent corroborating estimates rather than one estimate shown five times.

**[Minor] `mask_source` and `threshold_or_score` are passed by `pipeline.py` but absent from the emitted layer** — verified: `pipeline.py` constructs `EvidenceLayer(..., mask_source="aoi_wide_scalar", threshold_or_score=susc_result.get("aoi_mean_score"))`, but the output dict contains neither key (both read back as `None`). `intersection_type` is derived from `mask_source` and *is* emitted, so the information is partially preserved — but the hazard score the exposure was computed against is not recorded in the exposure block.

---

### Explicit negative results

These are as important as the findings — several are places where the project's
stated discipline is genuinely implemented rather than merely documented.

- **`GATE_C_STATUS` is in sync.** `exposure/compute.py:27` reads exactly `"waived_pending_real_user_validation"`, matching PROJECT_GATES.md line 35. The two have not drifted — the failure is in *propagation to the frontend* (C24), not in the constant.
- **Population is correctly `None`, never 0.** The dangerous "0 people exposed" failure mode **does not exist**: the unavailable branch sets `None`, and the success path guards `round(float(pop)) if pop is not None else None`.
- **The WorldPop scale bug fix is correctly implemented.** `reduceRegion` uses the image's own `crs`/`crsTransform` with `bestEffort=False` and passes **no** `scale=`, exactly as `exposure_constants.py:38-45` mandates. `WORLDPOP_NOMINAL_SCALE_M` is display metadata only. The bug PROJECT_GATES.md records as found-and-fixed stays fixed.
- **`risk/compute.py`'s restraint is load-bearing, not decorative.** It refuses a `V=1.0` fallback, refuses imagery-derived vulnerability proxies, and returns `not_calculated` **even when all three inputs are available** rather than inventing a fusion formula. That is why Gate E's absence cannot leak a fabricated risk score.
- **`coastal.py` is the module's best unavailability handling** — it distinguishes *unavailable*, *not applicable*, and *low* as three separate states, with an explicit comment refusing to "guess a near-zero score."
- **`fluvial.py`'s direct index is provably safe** — `hydrology.py:80-81` raises if `mean_hnd` is `None`, so `status == "available"` guarantees a value.
- **`flash_flood.py` double-guards** all three inputs on both status and value, and correctly refuses to score on rainfall alone.
- **`observed_inundation.py` genuinely does not fuse its sources** and correctly distinguishes "could not check" (`None` + `components_excluded`) from "no new water" (a number).
- **Category-index drift in the `.npy` reuse path is not a live risk** — `categories` is read from the *same* `result.json` that accompanies the array, so the index→name mapping is internally consistent by construction even if the checkpoint's ordering later changes.
- **Ward rasterisation has no off-by-one or flipped-Y error** — `rasterio.transform.from_bounds` + `geometry_mask(invert=True)` is the correct north-up convention, and a ward wholly outside the raster is correctly returned as `not_calculated`.
- **The zonal quality gate works as designed** — the sole reusable run on disk is correctly rejected on `valid_observation_pct` (50.84 < 60.0), `out_of_distribution`, *and* footprint coverage (3.12% < 99%). **Case 1 reuse cannot currently fire at all**; every invocation falls through to a fresh run.
- **`boundaries/ingestion.py`'s validation is real, not rubber-stamped** — it genuinely refuses to store an invalid layer, checks CRS without silently reprojecting, stores geometry unclipped as documented, and labels degree-based areas honestly.

---

## Training/Annotation Module

Scope as requested: the training/annotation tooling outside the live pipeline.

> **⚠ COVERAGE NOTE — THIS MODULE IS PARTIAL.** Four parallel audits were
> launched for this module and **all four terminated early on an account
> session limit**, returning no completed reports. Everything below was
> audited directly and is either a full read or a targeted read plus
> empirical verification against data on disk; nothing here is carried over
> from the terminated agents. The files **not** audited are listed explicitly
> at the end of this section — they are gaps, not clean bills of health.

### Files actually audited in this module

| File | Depth |
|---|---|
| `run_all_cities.py` | full read |
| `verify_masks.py` | targeted read of the verification logic + its on-disk report |
| `annotate.py` | targeted read: segment/id sourcing, mask join, label write path |
| `annotate_queue.py` | targeted read: label input path |
| `generate_osm_road_masks.py` | targeted read: buffering, width table, tag exclusions |
| all `annotations.json`, `batch_run_log.json`, `mask_verification_report.json`, `osm_generated_annotations*.json` on disk | empirical inspection |

---

### Artifact-completeness sweep

Unlike `audit_roofing_labels.py` (never run, per the prior check), the
training-data generation tooling **did** run to completion. All 11 training
cities have every expected artifact:

```
city        ann  masks  tile.png  tile.npy  osm_road.json  osm_road_dir  osm_water.json  osm_water_dir
TOTAL/11     11     11        11        11             11            11              11             11
```

Label-volume balance across those 11 cities:

| Source | Count |
|---|---:|
| Human-annotated (`annotations.json`) | **331** |
| Machine-generated roads (`osm_generated_annotations.json`) | **976** |
| Machine-generated water (`osm_generated_annotations_water.json`) | **101** |
| **machine : human ratio** | **3.25×** |

Cape Town alone contributes 192 generated road records — matching the training
notebook's own comment that the underlying road mask "can have 100+ real
segments per city (up to 192 in Cape Town)".

---

### Critical findings

**[Critical] C28 — `annotate.py` joins masks to segments by `segment_id`, so it would bake the C9 mis-join permanently into `annotations.json`** (annotate.py:83-90, 98, 436, 549)
- What happens: `load_run()` reads `result.json` and takes `run_data["segments"]` (line 98); every annotation is keyed by that list's `segment_id`. Separately, line 90 builds `{str(m["segment_id"]): m.get("mask_rle") for m in raw if "mask_rle" in m}` from **masks.json**, and the resulting `mask_rle` is embedded into each saved annotation record. So an annotation's `bbox` comes from `result.json` while its `mask_rle` comes from `masks.json`, **paired by an id that Module 2 measured as 67% mis-joined on post-Phase-2 runs** (36 segments ids 0–35 vs 49 masks ids 0–48 on `dharavi_phase11_postfix_20260807_125913`).
- Root cause: the tool treats `segment_id` as a stable cross-file primary key. Module 2's C9 established it is a positional index into an area-sorted list, assigned by two different counters post-Phase-2. `annotate.py` predates that divergence and was never revisited.
- Downstream propagation risk: this answers the module's central question — **annotations.json does not add a third id scheme; it inherits `result.json`'s ids.** But it is worse than a third scheme: it *materializes* the broken join into a durable artifact. The training notebook's `build_sam_patches` reads `ann['bbox']` and `ann.get('mask_rle')` from the *same record*, so a future annotation round on a post-Phase-2 run would crop imagery from segment A while painting the label mask of segment B — silently corrupted training patches, with no error and no way to detect it after the fact. **Existing training data is not affected**: the 11 training-era runs (`*_20260702_*`) predate Phase 2 and their ids align.

**[Critical] C29 — Machine-generated `paved_road` labels are sub-pixel wide at 10m GSD, so every such training pixel is spectrally mixed by construction** (generate_osm_road_masks.py:70-89, 210-221)
- What happens: the script buffers each OSM way by a real-world width from `HIGHWAY_WIDTH_M`, correctly reprojected into a local UTM CRS (meter-accurate, not degrees). But at Sentinel-2's 10m ground sample distance:

  | highway tag | width | pixels wide |
  |---|---:|---:|
  | motorway | 12 m | 1.20 |
  | primary | 9 m | **0.90** |
  | secondary | 8 m | **0.80** |
  | tertiary | 7 m | **0.70** |
  | residential / unclassified | 5 m | **0.50** |
  | service | 4 m | **0.40** |

  Only `motorway` exceeds one pixel. Empirically, Cape Town's 192 generated road records have a **median mask area of 23.5 pixels** — thin ribbons. A pixel labeled `paved_road` from a 5m residential street is physically ~50% road and ~50% whatever abuts it; in a dense informal settlement, that is rooftop.
- Root cause: **not** a coding error — the script's own comment shows the author identified the correct risk and chose narrowness deliberately, to avoid "bleeding into adjacent rooftops/vegetation and mislabeling THOSE pixels as paved_road... which would reintroduce exactly the kind of contamination we're trying to avoid." The reasoning is sound; the resolution is not. At 10m GSD, narrowing the buffer does not avoid mixing — it converts "some wholly-wrong pixels" into "all mixed pixels". The failure is a physical limit of the sensor against the feature size, and it cannot be tuned away by buffer width.
- Downstream propagation risk: **this is the deepest root cause yet identified for the `paved_road`/`dense_informal_roofing` confusion.** Module 2 established that `paved_road` is 41.0% of training patches (3.59× `dense_informal_roofing`) and that a dedicated `separation_weight` loss term failed to resolve the confusion. A margin loss cannot separate two classes when one class's training pixels are, in physical fact, roughly half composed of the other. This reframes the confusion from "the model is undertrained" to "a substantial share of the supervision is unlearnable at this resolution."
- Honest scope limit: this quantifies the *geometry*. I did **not** measure the actual spectral composition of labeled pixels against imagery, so the "≈50% rooftop" figure is a geometric inference, not a measured mixing fraction.

**[Critical] C30 — The one tool that could detect C9 checks id *existence*, not id *correspondence* — and has never been run on an affected run** (verify_masks.py:104-112, 169-175; data/pipeline_runs/mask_verification_report.json)
- What happens: three separate failures compound. (a) The cross-file check is `segment_ids - mask_ids` (line 169-175) — pure set membership. Under C9 the segment ids (0–35) are a *subset* of the mask ids (0–48), so the check **passes** while 67% of the pairings point at the wrong geometry. There is no comparison of `bbox` or `area` across the two files. (b) When `n_masks > n_segments` the tool adds an issue string but **does not set `ok = False`** (line 110-112, contrast line 104-106 which does for the reverse case), and rationalizes it in the report text as "expected -- likely sub-8px segments filtered by classify_tile(); not an error". All **12** count-divergent runs in the report are marked `ok: true`. (c) The on-disk report covers 47 runs whose newest `run_id` is `nusantara_20260702_165811` — it was last run 2026-07-02, i.e. **three weeks before Phase 2** introduced the divergence. **Zero post-Phase-2 runs have ever been verified.**
- Root cause: the tool was written against the pre-Phase-2 invariant where `masks.json` was a superset of `result.json` segments by construction (the `w<8/h<8` filter). Under that invariant, count excess genuinely *was* expected and id membership genuinely *did* imply correspondence. Phase 2 broke the invariant; the verifier still encodes the old one, and its rationalizing message now actively reassures a reader about the exact symptom of the bug.
- Downstream propagation risk: the safety net that would catch C28 before it corrupted a training round is both incapable of detecting it and not deployed against the runs where it matters.
- **Positive note:** `verify_masks.py` *does* validate `sum(rle["counts"]) == h * w` (line ~135) — the exact check that Module 2 found missing from `ingestion/segmentation.py::decode_mask_rle` itself. That validation is correct and worth preserving.

---

### Moderate and Minor

**[Moderate] `annotate_queue.py` accepts arbitrary free text as a category label, with no validation — two corrupt labels confirmed on disk** (annotate_queue.py:187, 197, 203)
- What happens: `choice = input("Label [p=paved_road / type another label / s=skip / q=quit]: ")` then `label = "paved_road" if choice.lower() == "p" else choice`, written straight to `"human_label"`. **Any** typed string becomes a category. Scanning every `annotations.json` on disk found **2 invalid `human_label` values, both in accra** (`accra_20260702_163854`):
  ```
  1x  'data/annotation_queues/_current_candidate_preview.png'
  1x  'python annotate_queue.py capetown'
  ```
  These are a file path and a shell command — terminal input captured verbatim as ground-truth labels.
- Root cause: the prompt's `else choice` branch has no membership test against the 10-category taxonomy, unlike `annotate.py` which constrains input via `KEY_MAP = {str(i): CATEGORIES[i] for i in range(10)}` (keys `0`–`9` only). The two annotation entry points enforce different contracts on the same file.
- Downstream propagation risk: **contained but silent.** Both the training notebook (`if ann['human_label'] not in CAT2IDX: excluded += 1; continue`) and `recalibrate_caat.py::build_label_canvas` (`n_skipped_bad_label`) drop unrecognised labels — so the corruption never reached the model. But it silently removed 2 of accra's 27 annotations from training with no warning surfaced, and the same mechanism would silently discard any typo'd label (`dense_informal_roofin`) identically. Rated Moderate rather than Critical because the model is unaffected and the loss is 2/331 (0.6%).

**[Moderate] `batch_run_log.json` is truncated by every subsequent invocation, destroying batch history** (run_all_cities.py:50, 112-114)
- What happens: `LOG_PATH` is a fixed path opened with `"w"` and rewritten with the current invocation's `results_log` after each city. Within one run this is genuinely crash-safe (the comment's claim is accurate). Across runs it is destructive: the on-disk log contains **exactly one entry** (`nusantara`, started `2026-07-02T16:58:11`), despite all 11 cities demonstrably having been run that afternoon (run_ids span 16:36–16:58). A later single-city invocation overwrote the 11-city history.
- Root cause: the log's scope is one invocation but its filename is global and fixed, with no run id, timestamp, or append mode. The "crash-safe" reasoning addressed mid-run interruption and never considered inter-run persistence.
- Downstream propagation risk: no data corruption, but the durable record of which cities succeeded, how long they took, and what errors occurred is gone — the same class of lost-provenance issue flagged in Modules 1–4 where failures print to stdout and vanish.

**[Minor] `verify_masks.py` carries a fallback duplicate of `decode_mask_rle`** (verify_masks.py:40-52) — defined inside an `except ImportError` with the comment "Verify this matches your actual encoder." Module 2 confirmed it is currently byte-identical to the real one, but it is a second copy of a format-critical codec that will not track future changes. (Carried forward from Module 2's cross-module note; re-confirmed here.)

---

### Cross-check against C10 / C11 / C12 — would running `recalibrate_caat.py` fix them?

The CAAT trio was assigned to one of the terminated audits, so I did **not**
re-read those files this module. From Module 2's completed audit of them plus
the on-disk artifacts, a partial answer is supportable:

- **C10 (missing provenance): would be improved.** `recalibrate_caat.py` writes
  `source_checkpoint`, `methodology`, `cities_pooled`, `percentile`, and
  `min_threshold_floor` — the deployed file has none of these. A file it
  produced would carry provenance the current one lacks.
- **C11 (penalty/calibration mismatch): would NOT be fixed.** Module 2
  established `sliding_window_mean_probs()` in `recalibrate_caat.py` has no
  road/waterway penalty parameters in its signature and applies none. Thresholds
  would again be calibrated on unpenalized probabilities and applied to
  penalized ones.
- **C12 (no precision term): would NOT be fixed.** The methodology is the same
  10th-percentile-of-correct-predictions rule (`PERCENTILE = 10.0`,
  `MIN_THRESHOLD = 0.15`), which is what C12 identifies as structurally unable
  to suppress confident misclassification.
- **New risk introduced by C28/C30:** `find_annotated_run_dir()` selects
  `candidates[-1]` by name sort among runs having `tiles/tile_0_0.png` +
  `annotations.json` + `masks.json`. If a post-Phase-2 run for a city ever
  satisfies that, its broken `segment_id` join would silently corrupt
  `build_label_canvas`'s label raster — and per C30 nothing would detect it.

**Not verified this module** (would need the terminated audit): whether
`recalibrate_caat.py` has additional bugs of its own, exactly which run dirs
qualify today, and whether `caat_thresholds_recalibrated.json`'s absence has
any cause beyond the script simply never having been run.

---

### Gaps — files in scope that were NOT audited

These were assigned to the four terminated agents and remain unaudited. They
are **not** cleared:

- `recalibrate_caat.py`, `validate_recalibration.py`, `caat_diagnostic.py`
  (partially covered in Module 2; the deeper "would it reproduce the problem"
  read was not completed — see the partial answer above)
- `check_confusion_pair.py`, `breakdown_unknown_class.py` — **notable gap**:
  these produce the headline `72.9%` and `~50% unknown` figures cited
  throughout this audit. Whether those numbers were computed under production
  conditions (correct stride, penalties applied) is **unverified**. One
  terminated agent was specifically tasked with this and did not report.
- `generate_osm_water_masks.py`, `merge_osm_road_masks.py`,
  `merge_osm_water_masks.py`, `find_paved_road_candidates.py`,
  `check_generated_road_mask.py`, `check_generated_water_mask.py`
- `audit_boundary_labels.py`, `check_gt_format.py`, `check_new_city_labels.py`,
  `check_segment_mask.py`, `check_tiles.py`, `check_waterways_coverage.py`
- `push_water_annotations_to_drive.py` (uploads data — worth auditing before
  it is next run), `patch_checkpoint_provenance.py` (mutates a checkpoint)
- `annotate.py` in full — the GUI event handling and, in particular, whether
  its `annotations.json` save is **atomic** (a non-atomic write interrupted
  mid-save would truncate the file) were not examined.

---

## Frontend Module

Scope: `geowatch-ui/` — a single 934-line `src/App.jsx` (plus a 10-line
`main.jsx` and CSS). Audited in full, directly. Focus is on how `result.json`
is consumed and rendered, not UI polish.

### Component inventory

`statusMeta`/`StatusPill` (status→label/color), `landcoverImageUrl`,
`fmtNum`/`fmtPct`; map helpers `DragToggle`, `MapRecenter`, `AOIDrawer`,
`LandcoverOverlay`, `OSMVectorLayer`, `SegmentOverlays`; primitives `Explain`,
`Small`, `Metric`, `Disclosure`, `CaveatList`, `ReportCard`; report sections
`SecOverview`, `SecLandcover`, `SecHazard`, `SecExposure`, `SecVulnerability`,
`SecRisk`; `SegmentDetail` popover; `ReportMode` page shell; `App` root.

---

### Critical findings

**[Critical] C31 — The category palette has drifted from the backend on every single class** (App.jsx:69-74 vs ingestion/inference.py:165-178)
- What happens: `inference.py` renders `landcover.png` **server-side** using `CATEGORY_COLORS_RGB`, and the frontend displays that PNG as a Leaflet `ImageOverlay` while drawing its legend swatches and segment outlines from its own `CAT_COLORS`. Measured diff:

  | category | backend PNG | frontend swatch | ΔRGB |
  |---|---|---|---|
  | dense_informal_roofing | (224, 60, 60) | (224, 98, 90) | (0, +38, +30) |
  | sparse_informal_roofing | (240, 140, 80) | (232, 163, 90) | (−8, +23, +10) |
  | paved_road | (120, 120, 180) | (136, 136, 200) | (+16, +16, +20) |
  | standing_water | (40, 100, 200) | (74, 144, 226) | (+34, +44, +26) |
  | vegetation_clearing | (210, 200, 80) | (216, 200, 90) | (+6, 0, +10) |
  | active_construction | (200, 80, 200) | (200, 120, 208) | (0, +40, +8) |
  | dense_vegetation | (60, 180, 80) | (94, 217, 155) | (+34, +37, +75) |
  | unknown | (96, 96, 128) | (113, 111, 160) | (+17, +15, +32) |

  **Exact matches: 0/8.** The worst is `dense_vegetation` — a forest green in the PNG against a mint green in the legend.
- Root cause: `inference.py:165-168` states the palette "must match App.jsx's `CAT_COLORS` for the 7 ML-resolvable categories exactly." That is a comment in one language asserting a constraint about a constant in another, with no shared source, no generated file, and no test. It is the same unenforced cross-language contract pattern as Module 4's C24 (`product_validation_status`) — a rule enforced only by prose fails at the first edit that does not read the prose.
- Downstream propagation risk: a user matching an overlay color against the legend is reading two different palettes. The deltas are small enough to look like rendering/opacity variation rather than a defect — and the overlay is displayed at a user-adjustable 0.2–1.0 opacity over satellite imagery, which makes the mismatch nearly impossible to notice while making misidentification easy. Nothing errors.

**[Critical] C32 — The `applicability` block is never rendered, so the out-of-distribution verdict is invisible to users** (App.jsx, whole file)
- What happens: `applicability` appears exactly once in the entire frontend — at line 493, as `layer.intersection_type === 'aoi_total_given_layer_applicability'`, a string comparison on an unrelated field. `result.applicability` is **never read**. So when `unknown_pct > 45` and the pipeline flags `urban_landcover_model: out_of_distribution` ("semantic model output is unreliable for this scene"), the user sees the land-cover percentages, the impervious/infiltration metrics, and the pluvial and waterlogging hazard cards rendered exactly as they would be for a clean scene.
- Root cause: `applicability` was added to `result.json` in a later phase and no frontend section was added to consume it. `NAV_SECTIONS` (line 674-681) has six entries — overview, landcover, hazard, exposure, vulnerability, risk — and applicability is not among them; there is no place in the information architecture where it would appear.
- Downstream propagation risk: this is the terminal link in the C14 → C20 chain. Module 3 found applicability gates nothing downstream; Module 4 found it does not even gate its own sibling mechanisms; this module finds it is also never shown to the human who is the last possible check. The one signal designed to say "do not trust this scene" is computed, serialized, and then discarded at every consumer.

**[Critical] C33 — The legend is driven by a hardcoded frontend palette, and absent categories render identically to measured zeros** (App.jsx:331, 340-347)
- What happens: two defects compound in the land-cover legend. (a) `const entries = Object.entries(CAT_COLORS).filter(([k]) => k !== 'unknown')` iterates the **frontend's 10-category constant**, not `result.landcover.categories` (the checkpoint's actual 7). So `unpaved_dirt_road`, `open_drainage_channel`, and `open_waste` — the three OSM-only categories the per-pixel model *cannot emit into `category_area_pct`* — are always rendered as legend rows. (b) The value is `{pct ? fmtPct(pct) : '0.0%'}`, a truthiness test: `undefined` (category not in the dict at all) and a genuine `0` both render the literal string **"0.0%"**.
- Root cause: the legend was built against a static design list rather than against the run's own declared `categories` array, which `result.json` provides precisely so consumers need not hardcode it. The `pct ?` idiom then conflates three distinct states — measured-zero, absent-from-schema, and `null` — into one rendering.
- Downstream propagation risk: every run's report shows three phantom categories reporting "0.0%", which asserts they were measured and found absent when they were never measurable. This is the frontend instance of the exact "unavailable rendered as zero" pattern catalogued in Modules 1–4, and it is the more misleading direction: "0.0% open waste" reads as a positive finding about the area.

---

### Moderate

**[Moderate] Every UI-initiated analysis is silently pinned to a fixed Q1-2024 imagery window** (App.jsx:796)
- What happens: `analyze()` posts `start_date: '2024-01-01', end_date: '2024-03-31'` as hard-coded literals, alongside `aoi_label: 'aoi'`. There is no date control anywhere in the sidebar. `run_pipeline`'s auto mode (latest 90 days, used by the scheduler) is therefore unreachable from the UI, and every user-drawn AOI is analysed against a fixed two-year-old quarter.
- Root cause: development-time constants left in the request body; the sidebar exposes bbox controls only, so the date was never surfaced as a user-facing parameter.
- Downstream propagation risk: partially mitigated — `SecOverview` does render `result.imagery.requested_period.start/end`, so the window is disclosed after the fact. But a user analysing flood risk on a UI with a "Draw an AOI, then click Analyze" affordance has no indication before or during the run that they are not looking at current conditions. It also explains the large number of `aoi_2026*` run directories: every UI run is labeled `'aoi'`.

**[Moderate] Segment projection falls back to one specific city's raster dimensions** (App.jsx:901)
- What happens: `tileWidth={result.tile_dimensions?.width ?? 291} tileHeight={result.tile_dimensions?.height ?? 257}`. Verified: **291×257 is exactly `dharavi_20260702_163012`'s `tile_dimensions`**. If `tile_dimensions` were ever missing, every segment in any AOI worldwide would be projected through Dharavi's pixel grid and silently mis-placed on the map.
- Root cause: a debugging default captured from whichever run was open at the time, left in as an optional-chaining fallback. The `??` operator makes the failure silent by design — the map renders, just wrongly.

**[Moderate] The segment tooltip's definition of "purity" contradicts what the backend computes** (App.jsx:664, 652)
- What happens: the popover states "Purity is the share of pixels inside it that agree with the label shown." Module 2 established `landcover_purity_pct` uses `counts[top_idx] / len(px_vals)` — a **known-only numerator over an all-pixel denominator**, so a segment that is 95% unknown and 5% uniformly `paved_road` reports 5.0. Under the tooltip's stated definition that would mean 5% agreement; in fact agreement among classified pixels is 100%.
- Root cause: the UI copy describes the metric's intended meaning, while the backend implements coverage-confounded purity. Neither side's docstring defines the denominator, so the two drifted independently.

**[Moderate] INFORM vulnerability scores are rendered with no type or range guard** (App.jsx:568, 572)
- What happens: `<Metric value={v.dimensions?.vulnerability?.raw_score} unit="/ 10" ... />` passes the raw value straight into JSX — no `fmtNum`, no numeric coercion, no range check. Verified on real output the values are floats (4.4, 4.2), so this has not fired. But Module 1's C8 established `ingestion/vulnerability_sources.py` never validates that cell is numeric, and INFORM uses placeholder markers (`"x"`, `"-"`, blank) for countries with insufficient data.
- Root cause: `Metric` renders `{value}` verbatim; every other numeric call site wraps in `fmtNum`/`fmtPct`, these two do not.
- Downstream propagation risk: **this changes C8's assessment.** Module 3 confirmed `risk/compute.py` does no arithmetic on `raw_score`, so C8 was rated latent. It is not fully latent — the unvalidated value is rendered directly to the user as `x / 10`.

**[Moderate] AOI-level ambiguity is computed, serialized, and never displayed** (App.jsx:655-659)
- What happens: `SegmentDetail` does surface `ambiguous_between`/`ambiguous_pct` per segment — genuinely good, and the only place the confusion pair is ever named to a user. But `landcover.ambiguous_pct` and `landcover.ambiguous_pct_by_pair` (the AOI-wide figures `run_inference` computes) appear nowhere. The headline "N% of this AOI is torn between paved road and dense informal roofing" is never shown.
- Root cause: ambiguity was wired into the segment popover, which is per-object, without a corresponding scene-level card in `SecLandcover`.

**[Moderate] `CaveatList` silently truncates to five items** (App.jsx:242)
- What happens: `items.slice(0, 5)` with no "+N more" indicator. Verified on real output every exposure layer currently carries **exactly 5** limitations — precisely at the cap. A sixth would vanish with no trace.
- Root cause: a layout constraint implemented as data truncation. In a product whose stated discipline is honest limitation labelling, the component that renders limitations is the one silently dropping them.

**[Moderate] Two unknown-rate thresholds disagree across the stack** (App.jsx:282 vs configs/applicability_constants.py:19)
- What happens: the overview metric turns coral when `landcover.unknown_pct > 15`; the backend declares `out_of_distribution` at `> 45`. A scene at 30% unknown is visually alarming in the UI while formally "in distribution" server-side; a scene at 50% is alarming in the UI and formally unreliable — but per C32 the user cannot tell those two states apart.
- Root cause: a UI styling threshold invented independently of the backend constant, with no shared source.

**[Moderate] The risk status pill is hardcoded rather than read from the data** (App.jsx:607)
- What happens: `<StatusPill status="not_calculated" size="md" />` is a literal, not `risk.status`. It is correct today (the backend always returns `not_calculated`), but the displayed status is decoupled from the value it claims to show.
- Root cause: the surrounding copy explains *why* risk is unscored, so the pill was written as part of that static explanation rather than as a data binding.

**[Moderate] Raw server exception text is surfaced to the user** (App.jsx:798, 803, 867) — `throw new Error(await res.text())` → `setError(e.message)` renders whatever the API returned. Module 3 found `api.py` returns `HTTPException(500, detail=str(e))`, forwarding GEE errors and filesystem paths. The two combine to put internal paths in the sidebar.

---

### Minor

- **No client-side bbox ordering or range validation** (App.jsx:785) — `Object.values(b).some(isNaN)` catches only unparseable input; `west >= east` or out-of-range latitudes are submitted and rejected server-side as a 400. Module 3 established `api.py` checks ordering but not ranges, and `sentinel2.py` checks neither — so an out-of-range coordinate passes all three layers.
- **`informalCount` is recomputed client-side** (App.jsx:269) — the frontend filters `result.segments` to count roofing segments rather than reading a backend-provided aggregate, duplicating classification logic across the boundary. Small, but it is the pattern the "single source of truth" question asks about, and it would silently disagree with any backend count computed on a different basis (e.g. before vs after the OSM override, which Module 3's C-series showed changes segment categories).
- **`result.aoi` dereferenced without optional chaining in `ReportMode`** (App.jsx:725, 727) — `result.aoi.south` etc. would throw on a result lacking `aoi`. Not reachable in practice; every `result.json` carries it.
- **`OSMVectorLayer` swallows fetch failures** (App.jsx:163-164) — `.catch(() => setRoads(null))` means a failed roads.geojson fetch renders identically to an AOI with no roads. Mirrors Module 1's C6 (`None` conflating "absent" and "failed") at the presentation layer.

---

### Explicit negative results

Several of the specific risks this module was asked to check **do not** occur, and two backend Criticals turn out not to reach the UI:

- **The frontend is immune to C13.** `primary_tile` is referenced **0 times**. `LandcoverOverlay` uses `landcover.map_path` — the full-AOI mosaic PNG — bounded by `result.aoi`, and `SegmentOverlays` projects global bboxes through `tile_dimensions` (also full-raster). Both are internally consistent. C13's multi-tile mis-render therefore affects *other* consumers of `primary_tile`, not this one.
- **C9 does not mirror client-side.** `segment_id` appears three times: as a React `key`, as selection identity (`selected?.segment_id === seg.segment_id`), and as display text. **Nothing joins by it across files** — segments carry their own `bbox`, `area`, `landcover_purity_pct`, and `ambiguous_between` inline. The 67% mis-join is a server-side artifact and is not reproduced here.
- **Unavailability is genuinely shown, not blanked, for the gated modules.** `SecHazard` renders `s.reason` when a susceptibility layer is not `available`/`experimental`; `SecExposure` gates each of population, built-up, roads, and facilities on `status === 'available'` and otherwise renders `.error`; `SecVulnerability` and `SecRisk` render `.reason`. `STATUS_META` maps `unavailable`, `insufficient_evidence`, `not_calculated`, and `not_applicable` to distinct labels and colors. This is the correct pattern and is why Module 4's `facilities count: 0` defect is contained.
- **The `road_access_score` sentinel is handled** (App.jsx:653) — `seg.road_access_score === -1 ? 'N/A'` correctly distinguishes the unavailable sentinel from a real score, rather than rendering `-1`.
- **The AOI-wide exposure caveat fires correctly.** Verified on real output that all five layers carry `intersection_type: 'aoi_total_given_layer_applicability'`, exactly matching the string App.jsx:493 tests, so the "totals for the whole area, not just the flood-prone parts" caveat does display.
- **The exposure layer picker does not merge layers** — confirmed again here; it selects one layer at a time. (The separate finding that all five layers carry *identical* values, and that the picker's copy overstates per-hazard specificity, is recorded in Module 4.)

---

## Phase 1: Observed vs Predicted

The pipeline was executed end-to-end. Everything below is **observed behaviour
on real runs**, not static analysis. No audited source file's logic was
modified; the only changes to the machine were running the code.

**Runs executed (2026-08-20):**

| Run | AOI | Raster | Tiles | Status |
|---|---|---|---|---|
| `phase1_dharavi_20260820_125646` | 72.836,19.037 → 72.862,19.060 | 291×257 | 1 | complete |
| `phase1_dharavi_20260820_125809` | same (repeat) | 291×257 | 1 | complete |
| `phase1_multitile_20260820_130117` | 72.80,19.00 → 72.88,19.08 (~75 km²) | **892×891** | **4** | complete |

Imagery window 2024-01-01→2024-03-31 (the window the frontend hardcodes).
Environment was already functional: GEE credentials valid, all dependencies
present, `.env` loaded via `python-dotenv` in `gee_client.py`. **No setup
fixes were required.**

---

### ⚠ Corrected headline figures

Three numbers cited throughout this document were re-derived under the real
production configuration. **One holds, two do not.**

| Figure | As cited in this document | Measured under production config | Verdict |
|---|---|---|---|
| Confusion-pair share of unknown mass | **72.9%** | **70.1%** (with penalties) / **72.4%** (without) | ✅ **HOLDS** |
| Unknown-pixel rate | **"~50%"** | **25.74%** Dharavi / **28.79%** multi-tile | ❌ **NOT REPRODUCED — roughly half the cited value** |
| `paved_road` share of training supervision | **41.0%** | **41%/73% by patch — but 17.8% by pixel** | ⚠️ **PATCH-LEVEL ONLY** |


> **Note (2026-08-22, manual re-derivation):** the unknown-pixel rate was
> corrected **25.73% → 25.74%** at all four occurrences in this file, and the
> penalty delta from **+1.28 pp → +1.29 pp** to follow from its own inputs
> (24.45% → 25.74%). `100 × 19,252 / 74,787 = 25.742442`, and the run's
> `result.json` records `25.74`; 25.73 is not derivable from the data. A
> transcription slip, corrected in place rather than annotated, since no
> reasoning attached to it. The 28.79% multi-tile figure was re-derived and is
> unchanged. See `AUDIT_FINDINGS_V2.md` → "Addendum 3 — manual re-verification
> of two headline figures". *Caveat: the 24.45% no-penalty baseline was **not**
> independently re-measured; the delta is corrected only for internal
> consistency with the two rounded values as stated.*

**On 72.9%** — my stated concern that the diagnostics omitted the proximity
penalties was **correct as a fact but immaterial as an effect**. Confirmed:
`check_confusion_pair.py` and `breakdown_unknown_class.py` contain zero
references to `road_dist`/`dist_map`/`PROXIMITY`/`penalty`, while
`run_inference` applies both. Measured on the same tile, adding the penalties
moves the pair share from 72.4% → 70.1% (−2.3 pp) and the unknown rate from
24.45% → 25.74% (+1.29 pp). **The 72.9% figure is sound and the audit's
reliance on it was justified.** I flagged this as the document's weakest
foundation; that was over-cautious.

**On "~50% unknown"** — not reproduced anywhere. Real production unknown rate
is **25.74%** (Dharavi) and **28.79%** (multi-tile). Any argument in this
document that leaned on a ~50% unknown rate (notably C19's severity framing
and parts of the C14 narrative) is **overstated by roughly a factor of two**.
The direction of every such finding is unchanged; the magnitude is not.

**On 41%** — the figure is a **patch count**, not a pixel count, and the
distinction is large. Measured across all 11 cities' on-disk label pool
(annotations + OSM-generated, `mask_rle` decoded):

| class | patches | patch % | pixels | pixel % |
|---|---:|---:|---:|---:|
| paved_road | 987 | **73.4%** | 86,349 | **17.8%** |
| standing_water | 133 | 9.9% | 238,265 | **49.1%** |
| dense_vegetation | 94 | 7.0% | 82,695 | 17.1% |
| dense_informal_roofing | 53 | 3.9% | 43,230 | 8.9% |
| active_construction | 25 | 1.9% | 14,360 | 3.0% |
| vegetation_clearing | 38 | 2.8% | 12,723 | 2.6% |
| sparse_informal_roofing | 15 | 1.1% | 7,174 | 1.5% |

`paved_road : dense_informal_roofing` is **18.62× by patch but only 2.00× by
pixel.** The raw pool is 73.4% paved_road by patch; the notebook's 25/city caps
reduce that to the checkpoint's implied 41%. Both are patch statistics.
**At pixel level `paved_road` is 17.8% and `standing_water` is the dominant
class at 49.1%** — because OSM road masks are thin ribbons (median 23.5 px,
per C29) while water polygons are filled areas.

*Caveat:* this pool is a proxy, not identical to what training saw — the
notebook caps OSM sources and adds sliding-window patches not represented here.

**A new, related finding:** `CLASS_WEIGHTS` are computed as inverse **patch**
frequency (`Counter(p['label'] for p in train_patches)`) and then applied to a
**per-pixel** `CrossEntropyLoss`. The weighting statistic and the loss domain
do not match. I have **not** established the directional effect of this and do
not claim one; it is flagged as an open question.

---

### ⚠ The bias check overturned the audit's framing

I proposed testing whether the roofing/road findings were a general pattern or
an artefact of being pointed at that pair. **They were partly an artefact.**

Full top1→top2 structure, production config, Dharavi (row % of each class's pixels):

| top1 ↓ / top2 → | d_inf_roof | sp_inf_roof | paved_road | standing_w | veg_clear | act_constr | dense_veg |
|---|---:|---:|---:|---:|---:|---:|---:|
| dense_informal_roofing | — | 19.4 | **63.0** | 0.0 | 6.7 | 10.4 | 0.6 |
| sparse_informal_roofing | 7.6 | — | **80.9** | 0.0 | 0.8 | 2.2 | 8.6 |
| paved_road | **41.4** | 28.2 | — | 0.5 | 10.6 | 13.5 | 5.9 |
| standing_water | 0.0 | 0.0 | **72.5** | — | 5.2 | 0.0 | 22.3 |
| vegetation_clearing | 23.1 | 0.6 | **55.4** | 1.4 | — | 8.0 | 11.5 |
| active_construction | 19.5 | 5.6 | **60.6** | 0.0 | 5.4 | — | 9.0 |
| dense_vegetation | 0.1 | 4.6 | **79.4** | 9.3 | 4.8 | 1.9 | — |

**`paved_road` is the top-2 partner for all six other classes (55.4%–80.9%).**
It is 42.15% of raw argmax before CAAT, against 17.8% of pixel-level
supervision — roughly **2.4× over-predicted**.

Three consequences for this audit:

1. **The "paved_road / dense_informal_roofing confusion pair" framing is
   incomplete.** This is not a symmetric pair; it is one class attracting
   everything. My findings about the pair are real but are an instance of a
   broader pathology I would have missed had I only looked where directed.
2. **`CONFUSION_PAIRS`' second entry is empirically wrong.** `inference.py`
   declares `{dense_vegetation, standing_water}`, but `dense_vegetation`'s
   actual top-2 is `paved_road` (79.4%, vs 9.3% for standing_water) and
   `standing_water`'s is `paved_road` (72.5%, vs 22.3%). The ambiguity map
   therefore flags a pair that barely exists: measured
   `ambiguous_pct_by_pair` on Dharavi is **5.25 pp** for roofing|road vs
   **0.03 pp** for vegetation|water.
3. **`check_confusion_pair.py`'s own decision rule is not met.** It declares a
   confirmed pair only when both directions exceed 40%. Measured:
   paved→roofing **36.7%**, roofing→paved 52.4%. By its own criterion the
   script would print *"NOT a clean confusion pair — more consistent with each
   class independently being undertrained or having noisy ground truth"* —
   which points at the label-quality hypothesis, not the pair hypothesis.

---

### Observed vs predicted — per finding

| # | Predicted | Observed | Verdict |
|---|---|---|---|
| **C9** | `segment_id` mis-joins between `result.json` and `masks.json` on post-Phase-2 runs | Fresh run: 36 segments (ids 0–35) vs 44 masks (ids 0–43); **11/36 = 30.6%** bbox mismatch, with a clean one-position shift from id 25 onward | ✅ **CONFIRMED** (magnitude run-dependent: 30.6% here vs 67% previously) — ⚠️ *shift pattern corrected, see †C9 below* |
| **C10** | Loader accepts a CAAT file with no `source_checkpoint` and merely prints it | Live run logged: `Loaded CAAT thresholds (source_checkpoint=?, verified_sanity_check_miou=?)` | ✅ **CONFIRMED** |
| **C13** | `primary_tile` is one 512px tile while everything else is full-raster | 4 tiles, `tile_dimensions` 892×891, `landcover.png` 892×891, **`primary_tile` actually 512×512**; segment bboxes reach x=891,y=890; **102/116 segments (87.9%) fall outside `primary_tile`**, which covers 57.4% of width | ✅ **CONFIRMED — worse than predicted** |
| **C14/C20** | OOD verdict emitted alongside `applicable` siblings | At `unknown_pct=60`: `urban_landcover_model: out_of_distribution` with `pluvial: applicable`, `waterlogging: applicable` in the same dict | ✅ **CONFIRMED** |
| **C15** | `road_access_scores_reliable: true` while all scores are −1.0 sentinels | Both runs: **0 sentinels**; real scores 0.162–0.985 (mean 0.831). OSM returned 1,694 roads and 15,912 road pixels rasterized, so the `road_px_count==0` precondition never fired | ⚠️ **NOT TRIGGERED** — conditional bug, precondition absent on these AOIs. Not refuted; not observed |
| **C16** | `aoi_label` escapes the data root | `'../../../../tmp/pwn'` → `run_dir` normalizes to `../../tmp/pwn_...` (verified by path arithmetic; **nothing was created**) | ✅ **CONFIRMED** |
| **C17** | `/api/demo` permanently serves `dharavi_test_*` | 37 dirs match `startswith('dharavi')`; lexicographic last is still **`dharavi_test_20260806_114208`**, while newest-by-mtime is `dharavi_phase11_postfix_20260807_125913`. The two new `phase1_dharavi_*` runs also sort below it | ✅ **CONFIRMED** |
| **C18** | Failed run reported as success, empty dir left | **Not observed** — every run this session completed successfully. Would require forcing a no-tiles failure | ⬜ **NOT OBSERVED** |
| **C19** | Imperviousness deflated in proportion to unknown rate | Emitted `impervious_fraction_pct = 41.68`; recomputed with known-pixel denominator = **56.12**. **Understatement factor 1.347× at 25.74% unknown** — exactly `1/(1−0.2574)` | ✅ **CONFIRMED AND QUANTIFIED** — ⚠️ *two numbers corrected, see †C19 below* |
| **C21** | Total landcover failure scores as 0.0 = permeable | `compute_hydrological_surfaces({})` → `impervious 0.0`, `infiltration 0.0`, **no `status` key**. Fed to `compute_waterlogging_susceptibility` with HAND unavailable → **`status: "experimental"`, `score: 0.0`, `class: "very_low"`** | ✅ **CONFIRMED — worse than predicted** (emits a confident *"very_low"* hazard class) |
| **C22** | No-data pixels render as **maximum** pluvial susceptibility | Real `pluvial_susceptibility.png`: unknown pixels **mean 125.4, median 124**, range 118–153. Known pixels mean **149.1**, range 63–220. `paved_road` pixels mean 197.9. **0.0% of unknown pixels sit at the PNG maximum** | ❌ **PARTIALLY REFUTED** — mechanism real (no-data does receive maximum *infiltration deficit*, same as `active_construction` at 125.8), but the **consequence claim is wrong**: unknown renders mid-range, *below* the known-pixel mean, not alarming |
| **C23** | `product_validation_status` dropped on the `not_calculated` path | Forced that path: returns exactly `['label','layer_id','reason','status']`. **Field absent**; `.get()` → `None` | ✅ **CONFIRMED** (all five layers on the real runs took the success path and *did* carry it — the defect needs an inland AOI to surface naturally) |
| **C25** | All-unknown ward → `impervious 0.0` with a real score | Reproduced zonal's construction: all-unknown 40×40 ward → `category_area_pct = {}` → `impervious_fraction_pct 0.0`; **zero-pixel guard does not fire** (`pixel_count=1600`). A 50%-unknown ward reports `impervious 50.0` where known-pixel truth is 100.0 | ✅ **CONFIRMED** |
| **C26** | No per-ward unknown fraction emitted | Confirmed: no field carries it; a 100%-unknown and a 50%-unknown ward differ only by an inference from the `category_area_pct` sum that no consumer is instructed to make | ✅ **CONFIRMED** |
| **C31/C33** | Palette drift; legend hardcoded | Unchanged from the static measurement (0/8 colour matches; legend iterates the frontend constant). Not re-tested — these are static constants | ✅ **CONFIRMED** (static) |
| **C11** | Penalties over-reject `paved_road`/`standing_water` into unknown | Measured: penalties raise unknown 24.45%→25.74% (**+1.29 pp**). `standing_water` unknown count 564→1111 (**+97%**), `paved_road` 11,899→12,098 (+1.7%) | ✅ **CONFIRMED in mechanism and direction, bounded in magnitude** — the effect on `standing_water` is large proportionally but small absolutely (3.1%→5.8% of unknown mass) |
| **OSM-override purity** (Moderate) | Purity describes the pre-override category | Segment 25: `dominant_landcover_category: unpaved_dirt_road`, `label_source: osm_vector`, **`landcover_purity_pct: 0.0`** | ✅ **CONFIRMED** |
| **`summary.unknown_segments`** (Moderate) | Under-reports because counted post-override | `unknown_segments: 0` while `unknown_pct: 25.74` and one segment was OSM-overridden | ✅ **CONFIRMED** |
| **`dominant_category`** (Moderate) | Argmax over a partial distribution | `dominant_category: "paved_road"` at 25.97% while 25.74% of the raster is unknown — the "dominant" class barely exceeds the unclassified fraction | ✅ **CONFIRMED** |
| **C1** (cloud mask) | QA60 may be zero-filled | **Not tested** — requires inspecting QA60 band contents per scene | ⬜ **NOT OBSERVED** |
| **C2/C3/C4** (tiler) | Export/band validation gaps | **Not triggered** — the 75 km² multi-tile AOI (15× the documented 5 km² limit) exported and tiled correctly at 892×891, so no silent truncation occurred at this size | ⬜ **NOT TRIGGERED** |
| **C27** | Ward tiers non-reproducible | **Not re-tested this session** — rests on the two disagreeing ward-screening JSONs already on disk | ✅ (prior empirical evidence stands) |
| **C24/C32** | Frontend omits Gate C / applicability | Static, unchanged | ✅ **CONFIRMED** (static) |



> **† C9 — the shift pattern is misdescribed. The row above is preserved
> verbatim; the finding itself stands, and is strengthened.** See
> `AUDIT_FINDINGS_V2.md` → "Addendum 4 — targeted spot-check of 10
> weight-bearing findings", and the corrected C9 entry in V2's "Confirmed by
> execution".
>
> Re-measured by hand from `phase1_dharavi_20260820_125646` on 2026-08-22.
> "A clean one-position shift from id 25 onward" holds only for ids 25–28 and
> is false for 29–35. **The offset accumulates:**
>
> | ids | offset |
> |---|---|
> | 25–28 | **+1** |
> | 29–31 | **+2** |
> | 32–35 | **+3** |
>
> Every disagreeing segment still matches *some* mask, so nothing is lost — the
> drift simply grows as filtered-out masks accumulate.
>
> **This strengthens the finding rather than weakening it.** A cumulative offset
> is precisely what two divergent counters produce: each mask dropped by the
> `w<8/h<8` filter adds one to the drift. A constant shift would instead suggest
> a single one-off skip and point at a different mechanism, so the corrected
> pattern is better evidence for the stated root cause, not worse. It also
> matters operationally: **any repair keyed to a constant +1 would fix ids 25–28
> and silently corrupt ids 29–35.**
>
> **Unchanged:** 36 segments vs 44 masks, **11/36 = 30.6%**, the contiguous
> 25-onward range, the run-dependent magnitude, and the root cause at
> `pipeline.py:332-361` — all re-confirmed. The verdict stays CONFIRMED.

> **† C19 — two numbers corrected. The row above is preserved verbatim; the
> finding itself stands.** See `AUDIT_FINDINGS_V2.md` → "Addendum 4 — targeted
> spot-check of 10 weight-bearing findings", and the corrected C19 entry in V2's
> "Confirmed by execution".
>
> Re-derived by hand from `phase1_dharavi_20260820_125646` on 2026-08-22:
>
> - **`56.12` → `56.13`.** A genuine known-pixel recount (55,535 of 74,787 px,
>   counted straight from `landcover_map_full.npy`) gives **56.1273 → 56.13**.
>   The stated 56.12 is reproducible *only* by rescaling the emitted value
>   (`41.678 / (1 − 0.2574) = 56.1244`), which is not the operation the row
>   describes.
> - **"exactly `1/(1−0.2574)`" — withdrawn.** Because 56.12 was produced *by
>   dividing by* `1 − 0.2574`, that identity was **true by construction, not an
>   independent confirmation of the mechanism.** It reads here as corroborating
>   evidence and is not. On a real recount the ratio is **1.346689** against
>   `1/(1−0.2574) = 1.346620` — agreeing to four significant figures, not
>   identically.
>
> **Unchanged:** the emitted `41.68` (reproduced exactly from
> `25.97×1.0 + 9.58×0.9 + 11.81×0.6 = 41.6780`), the mechanism, the direction,
> the severity, and the **1.347×** factor — both values round to it. The
> verdict stays CONFIRMED.

---

### Severity re-rating implied by observation

- **Downgrade C22** from Critical. The polarity defect is real, but no-data pixels render *less* alarming than classified ones. The original claim — "painted the most alarming" — is refuted. Appropriate rating: **Moderate**.
- **Downgrade C15** to conditional. It did not fire on either AOI; its precondition (`road_px_count == 0`) requires an AOI/CRS mismatch that did not occur. Real but **latent**.
- **Upgrade C13** in confidence. 87.9% of segments outside the basemap is worse than the ~40% I inferred from the older run.
- **Upgrade C21.** It does not merely produce `0.0`; it produces `class: "very_low"` with `status: "experimental"` — an affirmatively reassuring output from a total input failure.
- **C2/C3/C4 remain unobserved.** A 75 km² AOI — fifteen times `tiler.py`'s documented safe limit — produced a correctly-sized raster, so the feared silent truncation has no demonstrated trigger.

---

### What Phase 1 did not settle

- **C18** was never observed; no run failed. Forcing it needs a deliberately imagery-less AOI.
- **C1** (QA60) needs per-scene band inspection, not a pipeline run.
- **C27** was not re-run; the existing on-disk disagreement remains the only evidence.
- **The `~50%` unknown figure's origin is unexplained.** It is cited in
  `breakdown_unknown_class.py`'s own docstring but is not reproducible with the
  current checkpoint and CAAT file on these AOIs. It may derive from a
  different checkpoint, a different CAAT generation (the audit found evidence
  of at least three), or different tiles. **Until that is resolved, treat any
  argument in this document conditioned on a ~50% unknown rate as unsupported.**
- **The pixel-count table is a proxy** for training supervision, not a
  reconstruction of it. Settling it exactly requires instrumenting the
  notebook's patch assembly.
- **No ground truth was consulted.** Everything here measures what the system
  *does*, not whether it is *right*. The independent gold set proposed in the
  plan remains the missing piece.
