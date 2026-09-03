# GeoWatch Flood-Risk Track — Handoff Brief

**Read this file in full before doing any work on the flood-risk track.**

This document exists because every session starts cold. The decisions
below were made deliberately, over many sessions, often after a wrong
approach was tried and rejected. Re-deriving them from scratch will
produce different answers, and the different answers will be worse.

---

## 1. What this track is

A flood-risk screening system over administrative units (Mumbai BMC
wards), built on Sentinel-2 land cover, terrain/hydrology data (MERIT
Hydro, FABDEM, Copernicus DEM), rainfall (CHIRPS, GPM IMERG), OSM
vectors, WorldPop population, and INFORM Risk vulnerability.

**Product framing:** long-term susceptibility screening and
prioritization — "look here first." It is explicitly NOT flood
forecasting, flood-depth estimation, or expected-loss modelling. No
user-facing text derived from this system may imply otherwise.

---

## 2. Phase status

| Phase | Scope | Status |
|---|---|---|
| 0-9 | Safety fixes, cloud masking, multi-tile mosaicking, applicability router, 5 hazard tracks, observed inundation, event hazard | DONE, live-verified |
| 10 | Exposure / vulnerability / risk at AOI level | DONE (risk deliberately `not_calculated`, see §4) |
| 11 | Boundary ingestion (24 Mumbai BMC wards) | DONE, live-verified |
| 12A | Per-ward fluvial / coastal / flash_flood | DONE, live-verified, hardened |
| **12B** | **Per-ward pluvial / waterlogging** | **IN PROGRESS — code written, NEVER successfully executed** |
| 12C | Per-ward exposure / vulnerability | NOT STARTED |
| 13 | Portfolio comparison + ranking | NOT STARTED, blocked on 12C and an open decision (§6) |
| 14 | Contextual risk tiers | NOT STARTED, blocked on 13 AND on Gate E (§4) |

---

## 3. The five hazards and their dependency split

This split is the single most important architectural fact on this
track. It is why 12A was cheap and 12B is not.

**Geometry-only hazards** — computed from bbox + GEE scalar queries.
No imagery, no SAM, no inference:
- `fluvial` — MERIT Hydro HAND + FABDEM elevation
- `coastal` — sat-io Global Shoreline Dataset + FABDEM
- `flash_flood` — Copernicus DEM slope + HAND + CHIRPS rainfall

**Landcover-dependent hazards** — genuinely require per-pixel
Sentinel-2 classification (SAM + ResNet inference). No bbox shortcut
exists:
- `pluvial` — needs `landcover_map` + `waterway_dist_map` (real arrays)
- `waterlogging` — needs `hydrological_surfaces`, derived from real
  classified pixels via `category_area_pct`

**Confirmed real signatures** (these were guessed wrong once — do not
guess again, read the call sites in `pipeline.py`):

```python
compute_pluvial_susceptibility(
    landcover_map, categories, waterway_dist_map,
    relative_elevation_score, rainfall_mean_annual_mm,
)
compute_waterlogging_susceptibility(
    hand_context, hydrological_surfaces, rainfall_climatology,
)
```

---

## 4. LOCKED RULES — do not violate, do not "improve"

Each of these was arrived at deliberately. Several were adopted after
a shortcut was proposed and explicitly rejected.

**4.1 No fused cross-hazard risk score. Ever, under current scope.**
Pluvial, fluvial, flash-flood, coastal, and waterlogging risk stay
separate products. There is no "overall flood risk" number.

**4.2 `compute_risk()` returns `not_calculated` BY DESIGN.**
Even when hazard, exposure, and vulnerability are all available. The
hazard x exposure x vulnerability fusion formula is deliberately
undefined pending an explicit, separate methodology decision ("Gate
E"). A `V = 1.0` "reference scenario" fallback was proposed once and
rejected — multiplying by 1.0 changes nothing mathematically and
would misrepresent an exposure number as a risk number.
**Do not invent a fusion formula while coding. This is the single
most important rule in this document.**

**4.3 Exposure is a vector, never one number.**
Population, built-up area, road length, and facility count stay
separate components. Population is computed as a raster zonal SUM
(each WorldPop pixel is already a population count) — never
mean x area. Exposure is computed separately per evidence layer;
"population near pluvial susceptibility" and "population in observed
floodwater" are different claims and must never be merged.

**4.4 Critical facilities are a separate flag, never a weight.**
A hospital does not get silently folded into a weighted score. It is
surfaced as its own explicit flag.

**4.5 No percentiles or ranking outside a declared portfolio.**
A percentile is only meaningful relative to an explicit, versioned,
reproducible set of comparable units — same hazard method, same
dates, same population year, same vulnerability source. A portfolio
is NEVER implicitly assembled from whatever historical runs happen to
exist on disk. Single-AOI runs get no rank at all.

**4.6 Vulnerability must match or be coarser than the scoring unit —
and say so.** INFORM Risk is national-resolution by design (identical
for every AOI in a country — this is correct, not a bug). If
vulnerability is coarser than the unit being scored, the output must
be explicitly labelled `contextual_screening`, never presented as
decision-grade local risk. Only the VULNERABILITY and LACK OF COPING
CAPACITY dimensions are read — never HAZARD & EXPOSURE, to avoid
double-counting.

**4.7 Degradation is always visible, never silent.**
Every data-source function in this codebase returns a `status` field
and surfaces failures as `unavailable` / `not_calculated` with a real
reason. Never substitute a plausible default for missing data. (A
fake-HAND fallback and a fake 0m elevation substitute were both
removed for exactly this reason.)

**4.8 Never overload one date range with multiple meanings.**
Susceptibility uses one range; observed inundation uses a pre-event
and event pair; event hazard uses its own. This is why
`run_inundation_analysis()` and `run_event_hazard_analysis()` are
separate entry points rather than flags on `run_pipeline()`.

**4.9 Gate C is WAIVED, not passed.** No real user has validated that
exposure output is useful or correctly understood. `GATE_C_STATUS` in
`exposure/compute.py` is the single source of truth. Every consumer of
exposure output must propagate `product_validation_status` forward
into its own output so the waiver cannot silently disappear as layers
are built on top.

---

## 5. Known limitations — surface these, do not hide or "fix" them silently

**5.1 Phase 12A uses bounding boxes, not true ward polygons.**
`get_merit_hand_context()`, `get_fabdem_elevation_stats()`,
`get_slope_stats()`, and `get_coastline_context()` accept only
`(west, south, east, north)` floats — a hard API constraint, not an
oversight. Each ward's result carries `geometry_type_used:
"bounding_box"` and `bbox_area_excess_pct` so the gap is visible.

**5.2 Phase 12A reuses one rainfall value across all 24 wards.**
Deliberate: CHIRPS is ~0.05deg (~5km) and cannot resolve differences
between adjacent Mumbai wards; flash_flood here is long-term
climatological screening, not event hazard. Labelled in output as
`rainfall_spatial_treatment: "single_aoi_value_reused_across_wards"`.

**5.3 `shared_aoi_context` — 12B's biggest open caveat.**
`relative_elevation_score`, `rainfall_mean_annual_mm`, and
`hand_context` are AOI-wide scalars everywhere in this codebase. No
per-ward variant exists. So in Phase 12B, every ward shares an
IDENTICAL rainfall / elevation / HAND context — **only the landcover
component genuinely varies ward to ward.** This must be surfaced in
every ward's output (`shared_aoi_context` block), never implied as
independent per-ward measurement.

**5.4 The landcover model is weak, and pluvial/waterlogging inherit it.**
LOCO mean mIoU is 0.313 across 11 folds. A separate audit found
`paved_road` is over-predicted ~2.4x at pixel level and acts as a
"magnet class" — it is the top-2 confusion partner for all six other
classes. Pluvial and waterlogging are the ONLY two hazards that
depend on this model; the geometry-only three do not.

**5.5 Phase 9 normalization ceilings are fixed constants** regardless
of event-window length. A 3-day event and a 30-day event are judged
against the same ceiling. Known, flagged, unfixed.

**5.6 `PROJECT_GATES.md` is stale.** It still lists Gates D and E as
NOT STARTED although vulnerability shipped. Low priority; do not
treat that file as current truth.

---

## 6. Open decisions — must NOT be resolved silently while coding

**6.1 Is `shared_aoi_context` (§5.3) acceptable for 12B?**
Or does HAND need to go per-ward before wards can be honestly ranked
against each other? MERIT Hydro already accepts arbitrary bboxes, so
per-ward HAND is technically feasible. **This blocks Phase 13** —
ranking wards whose only varying input is landcover produces a
defensible-looking ranking driven by one variable. Decision belongs
to the project owner, with real 12B numbers in hand.

**6.2 Gate E — the fusion methodology.** See §4.2. This is a
methodology decision made deliberately and in writing, the same way
the vulnerability_context schema was defined before any code was
written. It is not a coding task. **Phase 14 cannot begin until it is
made.**

---

## 7. Immediate next step

**Phase 12B has never run successfully.** `zonal/landcover_screening.py`
and `configs/zonal_constants.py` exist; the "Option A" persistence
patch in `pipeline.py` (saving `landcover_map_full.npy`,
`waterway_dist_map_full.npy`, `raster_info.json`) is applied and
confirmed working.

Run it against `datameet_mumbai_bmc_wards`, full Mumbai extent.

Specific things to know going in:

- **Use `WIDE_RUN_DATE_START` / `WIDE_RUN_DATE_END` from
  `configs/zonal_constants.py`. Do NOT use auto-mode dates.** A pilot
  run using auto-mode landed mid-monsoon and came back at 50.84%
  valid observation / `out_of_distribution` — it would have failed the
  quality gate. The post-monsoon date window is load-bearing.
- **If the quality gate rejects the run, that is a real result.**
  Report it. Do NOT lower `MIN_VALID_OBSERVATION_PCT` or disable
  `REQUIRE_LANDCOVER_IN_DISTRIBUTION` to force a pass.
- **Case 1 (reuse) should not fire.** No prior run covers 99% of the
  full Mumbai extent. If it does fire, something is wrong with the
  coverage check — stop and report rather than proceeding.
- **`WIDE_RUN_TIMEOUT_SECONDS = 3600` has never been tested at scale.**
  It was extrapolated from a 2-tile pilot (2m17s wall clock, ~59s
  compute). Full Mumbai is roughly 40 tiles. Report actual wall-clock
  time — this is one of the things the run is meant to find out.

Report: actual wall-clock time, whether the quality gate passed,
per-ward pluvial/waterlogging output, and any bug that had to be fixed
to get it running.

---

## 8. Working style expected on this track

- Investigate before implementing. Read the real call sites; do not
  infer signatures from docstrings. **Docstrings in this codebase have
  been wrong before** — that was a central finding of a separate audit.
- Report findings honestly, including ones that contradict the brief.
  Every genuinely useful result on this track so far has come from
  something failing or a number not matching expectations.
- Do not widen scope. If a phase's work reveals a problem belonging to
  another phase, report it — do not fix it in the same pass.
- Prefer "this failed, here is why" over a workaround that makes
  output appear when the underlying data does not support it.