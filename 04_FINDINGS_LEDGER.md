# GeoWatch — Findings Ledger

**Every finding, its evidence, and its fate under the new architecture.**

This is the triage index. Before building anything, check here — roughly a third
of the original findings are **deleted** by the architecture change rather than
fixed, and building them would be wasted work.

Confidence: **[E]** empirical · **[S]** static · **[R]** reasoned

Fate categories:
- **DELETED** — the code this describes stops existing. Do not build.
- **CONDITIONAL** — depends on Decision 12 (does SAM survive). *(Resolved:
  deleted — see below. Entries under this heading are retained for record but
  now read as DELETED.)*
- **SURVIVES** — no architecture change touches this. Real work.
- **CLOSED** — already fixed.
- **REFUTED** — disproven by evidence.
- **NEEDS FATE** — flagged during this pass; not yet triaged. See note below.

---

## Summary

| Fate | Count | Meaning |
|---|---:|---|
| CLOSED | 5 | Done during Part 1 |
| REFUTED | 2 | Disproven |
| DELETED | 13 | Architecture change removes the code |
| CONDITIONAL (resolved → DELETED) | 4 | Gated on Decision 12; now resolved |
| SURVIVES | 21 | The irreducible cluster — real work |
| NEEDS FATE | 5 | C34–C38, flagged during consolidation, not yet triaged |

**This is the authoritative list for the "irreducible cluster."**
`02_ARCHITECTURE.md` §8 references this section by pointer rather than
duplicating the enumeration, specifically so the two documents cannot drift
out of agreement with each other the way they previously did.

---

## CLOSED

### C16 — Unauthenticated path traversal via `aoi_label` [E] ✅ FIXED
`aoi_label` was unvalidated and became a filesystem path component in
`run_pipeline`. `'../../../../tmp/pwn'` normalised to `../../tmp/pwn_<timestamp>`,
escaping the data root.

**Fix applied:** whitelist validation `[a-z0-9_-]{1,64}` at the API boundary,
`HTTPException(400)`, reject-not-sanitize. 72 tests. Verified against the
*unpatched* file: 70 failed, 2 passed (the positive controls) — proving the tests
detect the bug rather than passing vacuously.

**Three placement decisions that mattered:**
- **Two sinks, not one.** `/api/analyze_inundation` takes `aoi_label` on its own
  request model and builds a run directory the same way. Fixing only `/api/analyze`
  would have left the hole open.
- **Outside the try block.** `HTTPException` is an `Exception`, so a 400 raised
  inside `except Exception → HTTPException(500)` gets swallowed and re-emitted as
  a 500.
- **`fullmatch()`, not `match()` with `$`.** In Python `$` also matches before a
  trailing newline, so `re.match(r'[a-z0-9_-]+$', 'aoi\n')` succeeds and the
  newline survives into the path.

**Behaviour change to remember:** the whitelist rejects uppercase. Nothing in the
codebase breaks, but any client sending a capitalised label now gets a 400.

**Note (consolidation pass):** C34 is the same bug class, a different sink
(`GET /api/runs/{run_id}`, read not write). See NEEDS FATE below — it should
receive the same treatment as this finding did, not remain unscheduled.

### Git initialisation ✅ DONE
Commit `2ac07d5`. 172 files. Reproducibility begins here; everything prior is
permanently unrecoverable. 37 notebooks copied from `~/Downloads` into
`notebooks/archive/`.

*Note: several archived notebooks are from other projects (`BehaviorCarbon`,
`MailShield`, `Earthquake_Prediction_API_Colab`) — swept up by the `*.ipynb`
glob. Harmless but muddies the provenance story.*

### Artifact hash manifest ✅ DONE
Commit `046dfef`. 30 SHA256 entries — SAM weights, production checkpoint, CAAT
thresholds, and 27 `annotations.json` files.

### C28 freeze ✅ DONE
Commit `46ac923`. `annotate.py` and `annotate_queue.py` refuse to run as scripts
and exit 2. Guard sits under `if __name__ == "__main__":` so
`check_segment_mask.py` can still `from annotate_queue import decode_rle`.

**Resolved by Decision 12:** SAM is deleted, so this finding is now DELETED
rather than merely frozen. See the CONDITIONAL section below.

*Found during the fix: `annotate_queue.py` inherits C28 by the same mechanism —
it builds `{segment_id: mask}` from `masks.json` and writes the same
`annotations.json`. Not merely frozen out of caution.*

### WorldPop framing ✅ CORRECTED
See C36–C38 below and `03_EVIDENCE.md` §C.4. The 2020 cap is a property of the
GEE mirror, not of WorldPop — and GHS-POP does not help, since its newest
*observation* epoch is also 2020.

---

## REFUTED

### C5 — Train/inference distribution mismatch [E] ❌ REFUTED
Claimed the production checkpoint trained on raw unstretched reflectance while
inference fed per-tile percentile-stretched 8-bit. Disproven by locating the
training notebook and reading its data-loading cells: training used the same
PNG-based path as inference. `GeoWatchDatasetResNet` does `/255.0` only, no
ImageNet normalisation, matching `inference.py:391`'s comment exactly.

**Preserved in V1 as a documented wrong turn.** The surviving issue is docstring
drift only (Minor): `tiler.py`'s docstring asserts `generate_tiles()` "is the
TRAINING data path" and the preview path "is explicitly NOT the training data
source anymore" — aspirational and wrong, describing a migration the training
code never adopted.

**Relevant to the float32 reflectance path (Decision 13 — REOPENED BY EVIDENCE):**
the 6-band float32 tiler is a prerequisite for item 21, not a retired path — the
dual-stem classifier that consumed it is dead, but the tiler itself produces
exactly the physical-reflectance input the new architecture requires. This holds
independent of how item 21's re-scope resolves: both the original unmixing solve
and the proposed `impervious_total` regression read the float32 multi-band tile,
never the stretched 8-bit preview.

### C22's consequence claim [E] ❌ REFUTED
Predicted no-data pixels would render as *maximum* susceptibility. Measured: mean
125.4, median 124, range 118–153, **0.0% at the PNG maximum** — below the
known-pixel mean of 149.1.

`UNKNOWN` is absent from both class dictionaries, so it is simultaneously
**minimum on the impervious surface** (weight 0.70) and **maximum on the deficit
surface** (weight 0.56). The two cancel, slightly favouring the low side. Only
`paved_road` is maximum on both.

**The surviving defect is different:** no-data scores *identically* to
`standing_water` and `active_construction` (all three: imperv 0, deficit 1.0). A
pixel the model could not classify is indistinguishable from two real classes.
**A collision, not an alarm.** Severity Critical → Moderate.

---

## DELETED by the architecture change

### C29 — Sub-pixel road labels [E/S] → **BECOMES THE FINDING**
Not a defect to fix. The central evidence for the architecture change. See
`01_DIAGNOSIS.md` §5.

### C7 — Road distance maps normalized per-AOI [E]
`compute_road_distance_map` divides by `dist_px.max()` — the farthest pixel
*within that raster*. `pipeline.py:220-237` builds it **once against the
full-AOI raster** and slices per tile, so the divisor is AOI-wide.

`ROAD_PROXIMITY_PENALTY_STRENGTH = 0.3` therefore has no stable physical meaning:
the same real distance produces a different penalty depending on the bounding box
the user drew.

**Deleted** — the road-proximity penalty ceases to exist.

### C11 — Penalties applied post-calibration [E]
Neither the diagnostic nor the notebook that produced the deployed CAAT applies
proximity penalties (verified: zero references), while `run_inference` does.
Measured: unknown 24.45% → 25.74% (+1.29 pp); `standing_water` unknown count
564 → 1111 (**+97%**); `paved_road` 11,899 → 12,098 (+1.7%).

*Direction confirmed, magnitude bounded — the original "systematic
over-rejection" framing overstated the aggregate effect. Severity Critical →
Moderate before deletion.*

**Deleted** with the penalty.

### C12 — CAAT has no precision term [S/R]
10th percentile of correctly-predicted confidence — pure recall, structurally
incapable of suppressing confident misclassification.

**Deleted** — replaced by risk-coverage curves (Part 5, item 28).

### CONFUSION_PAIRS second entry [E]
`inference.py` declares `{dense_vegetation, standing_water}`. Measured:
`dense_vegetation`'s top-2 is `paved_road` (79.4% vs 9.3%); `standing_water`'s
top-2 is `paved_road` (72.5% vs 22.3%). The ambiguity map flags a pair that
barely exists (0.03 pp on Dharavi).

**Deleted** — no pairwise confusion logic remains.

### CLASS_WEIGHTS patch/pixel mismatch [E]
Inverse *patch* frequency applied to a *per-pixel* loss. See `03_EVIDENCE.md`
§A.6 — protects `paved_road`, inflates `standing_water` 5.7×.

**Deleted** under Decision 11 — fractions replace discrete classification, so
this mismatch has no target to apply to. *If any discrete classification step
ever survives downstream of the fraction pipeline, this returns — see item 30.*

### W1 — 48.7% of OSM water pixels are not water [E]
Human annotations: 98.6%. Guatemala at 0.6% is worse than its own 3.5% tile
baseline. Cause: `way["waterway"]` queried with no filtering — a mapped drain is
a channel, not water in it.

**Deleted** — water becomes a fraction under Decision 11 and the OSM water-mask
generator is retired.

### W2 — Sub-pixel water features [S]
drain 0.20 px, ditch 0.15 px, stream 0.30 px. C29's pathology, second instance.

**Deleted** with the generator.

### W3 — Unfiltered `waterway` query [S]
Same mechanism as W1, semantic half.

**Deleted** with the generator.

### W4 — `check_generated_water_mask.py` cannot detect W1 [E]
It **ran** — overlay PNGs exist for 10 of 11 cities — and passed a mask that is
half wrong, because it is purely visual with no metric or gate. **Structurally
identical to C30.**

**Deleted** with the generator — *but the pattern must be carried forward.* See
"Patterns to carry" below.

### C3 — Training-path band-count mismatch [S]
Warns but does not fail. Confirmed **not in the live path** — `pipeline.py`
imports only `generate_rgb_preview_tiles`. Can only fire if
`retile_all_cities_6band.py` is re-run.

**Deleted** — the training path is being rebuilt. **Correction from
consolidation pass:** the 6-band float32 tiler itself is not being retired —
it is a prerequisite for item 21, which requires the float32 reflectance path
rather than the stretched-preview path. What is deleted is the dual-stem
classifier that used to consume the tiler's output, not the tiler. Decision 13
is now REOPENED BY EVIDENCE and item 21's re-scope is awaiting decision, but
this correction is unaffected: the re-scope's `impervious_total` regression
needs the same float32 path, and C3's fate stays DELETED either way.

### C6 — `get_osm_features` returns `None` for both "no roads" and "API failed" [S]
The docstring claims `None` means the request failed; false. A confirmed-zero AOI
and a total Overpass failure produce identical output.

**Reshaped, not deleted.** The requirement becomes the per-area completeness
score (Part 4, item 20) — a positive measurement rather than a None-vs-empty
distinction.

### `audit_roofing_labels.py` repair
Needs four fixes (dict unwrap, field names, bbox cropping, custom RLE decoder)
before it runs at all, then 35–70 minutes of manual review across 68 patches.

**Do not repair.** It audits roofing labels for a class scheme being replaced.

---

## RESOLVED by Decision 12 (formerly CONDITIONAL)

*Decision 12 settled: SAM is deleted. These four findings are DELETED, not
conditional. Retained under their own heading for record, since they were
tracked as a group throughout the audit.*

### C9 — `segment_id` mis-join [E] → DELETED
30.6% (11/36) on a fresh run; 67% on an earlier one. **The offset accumulates**
— ids 25–28 at +1, 29–31 at +2, 32–35 at +3. Every disagreeing segment still
matches *some* mask, so nothing is lost, but drift grows as dropped masks
accumulate.

*A repair keyed to a constant +1 would fix 25–28 and silently corrupt 29–35.*

Root cause at `pipeline.py:332-361`: `next_segment_id` increments over
`tile_segments` (post `w<8/h<8` filter), `next_mask_id` over all raw masks.

**Deleted with SAM.** The genuine future need this partially pointed at —
object-level tracking of non-building features such as water bodies — is
answered instead by connected-component labeling on thresholded unmixing
rasters, named as a deferred, unbuilt forward reference in Decision 12. Not
SAM, not this mechanism.

### C30 — `verify_masks.py` checks existence, not correspondence [S] → DELETED
It checks `segment_ids - mask_ids` (set membership). Under C9 the segments are a
*subset* of the masks, so it **passes while every pairing is wrong.** It also
marks all 12 count-divergent runs `ok: true`, rationalising the exact symptom as
"expected… not an error."

Its on-disk report covers 47 runs whose newest is `nusantara_20260702_165811` —
**zero post-Phase-2 runs ever verified.**

**Deleted with SAM.** The general lesson survives independent of SAM — "does the
check FAIL against a known-broken input" — and is carried forward in "Patterns
to carry" below.

### C28 — `annotate.py` would bake C9 in permanently [S] → DELETED
Line 90 builds `{segment_id: mask_rle}` from `masks.json` and embeds it into each
annotation, while `bbox` comes from `result.json`. On post-Phase-2 runs those ids
are mis-joined, so an annotation carries segment A's bbox with segment B's mask —
and the notebook reads both from the same record.

*Existing training data is safe — the 11 training runs predate Phase 2.*

**Deleted with SAM.** Annotation moves to stratified points (item 31)
regardless of SAM's fate, so this cost was never solely attributable to the
SAM decision — but it is deleted alongside it.

### C39 — Two corrupted `accra` annotations [E] → DELETED
`segment_id` 18 holds `data/annotation_queues/_current_candidate_preview.png`;
`segment_id` 26 holds `python annotate_queue.py capetown`. Terminal input
captured as ground truth.

Root cause: `annotate_queue.py:197` accepts any typed string with no membership
test against `CATEGORIES`, unlike `annotate.py` which constrains to keys 0–9.

**Impact was already nil** — both fall outside the 7 model classes, so they were
excluded from every figure and from training. **Deleted with SAM** — the
annotation tooling this finding lives in no longer exists.

---

## SURVIVES — the irreducible cluster

*No architecture change touches these. This is the real work, and the fact that
it survived the rebuild is the strongest argument that it is real — at the level
of pattern. At the level of specific field spec, several of these (the
epistemic-contract cluster below) are rewritten by Decision 14, not merely
carried forward unchanged. See the Part 6 translation note at the end of this
section.*

### The epistemic contract (Decision 14 — SETTLED, reasoning intact; ⚠️ amendment PROPOSED, awaiting sign-off)

*The core of Decision 14 — known-pixel denominator, mandatory `observed_fraction`
sibling, and the rule that distinct causes are never merged — is settled and, per
the item 21 pilot, strengthened. What is proposed (not settled) is four
field-spec changes that follow from the Decision 13 reopen: a standalone shadow
estimator (the sixth-endmember mechanism it delegated to no longer exists);
renaming "low unmixing confidence" to a regression prediction interval; splitting
the three fields into an observability group (shadow, cloud/nodata — define the
denominator) and an estimate-quality group (per-fraction confidence — never
touches it); and carrying the impervious/bare boundary as a confidence marker on
`impervious_total`. See `05_BUILD_MANUAL.md` Decision 14 and `06_UNMIXING_CEILING.md`.
None of this changes the fate of the findings below — they SURVIVE regardless.*

**C19 — Imperviousness deflated by the unknown rate** [E]
Emitted 41.68; recomputed with known-pixel denominator **56.13**. Factor
1.346689 vs 1/(1−0.2574) = 1.346620 — four significant figures, not identical.
**The direction is the dangerous one:** higher unknown → lower apparent
imperviousness → the settlement reads as *less* flood-prone.

**Under Decision 14:** resolved via known-pixel denominator, with a mandatory
`observed_fraction` companion field. The old single "unknown" concept is
replaced by three separately-reported fields (shadow, cloud/nodata,
low-confidence unmixing) — see item 33.

**C21 — Total landcover failure emits a confident "very_low"** [E]
`compute_hydrological_surfaces({})` returns `impervious 0.0`, `infiltration 0.0`,
**no `status` key**. Fed to `compute_waterlogging_susceptibility` with HAND
unavailable: **`status: "experimental"`, `score: 0.0`, `class: "very_low"`** — an
affirmatively reassuring hazard class.

The guard `impervious_fraction_pct is not None` is **vacuous** because the
producer has no failure path. Duplicated at `applicability.py:133` and
`waterlogging.py:57` — **the chain fails open twice.**

**C25 — All-unknown ward scores 0.0 imperviousness** [E]
A 40×40 all-unknown ward yields `category_area_pct = {}` → `impervious 0.0`, and
the zero-pixel guard **does not fire** (`pixel_count = 1600`). A 50%-unknown ward
reports `impervious 50.0` where known-pixel truth is 100.0.

**C26 — No per-ward unknown fraction emitted** [E]
No field carries it. A 100%-unknown and a 50%-unknown ward differ only by an
inference from the `category_area_pct` sum that no consumer is instructed to
make. **This is the field that would make C25 detectable.**

**C33 — Legend renders phantom categories; absent renders as zero** [S]
The legend iterates the hardcoded frontend palette, not
`result.landcover.categories`, so it always renders 3 OSM-only categories the
model cannot produce. And `{pct ? fmtPct(pct) : '0.0%'}` renders absent and
measured-zero identically — every report asserts "0.0% open waste" as if it were
a finding.

**C15 — `osm_available` latched before the distance map is built** [E]
`result.json` can claim `road_access_scores_reliable: true` and
`road_score_method: "distance_transform"` while every score is the `-1.0`
sentinel and the penalty was silently skipped.

*Not triggered on either run — real scores 0.162–0.985, zero sentinels.*
**Under Decision 15's strong-severity-bar:** this does NOT qualify for
downgrade — "not triggered" is not the same as "confirmed unreachable." Stays
at original severity. **The principle survives: a reliability claim must be
derived from the actual outcome, never latched beforehand.**

**C27 — Ward hazard tiers non-reproducible** [E prior]
A 90-second GEE timeout and genuine data absence are indistinguishable — the
`error` string is dropped at the ward-block boundary. Two real runs of the same
24 wards disagree on fluvial, coastal, and flash_flood tiers.

*The determinism result (§A.12) **strengthens** this by eliminating model
nondeterminism as an alternative explanation.*

### The gating architecture

**C14 — `applicability` gates nothing downstream** [E]
Confirmed by execution at `unknown_pct = 60`: `urban_landcover_model:
out_of_distribution` returned in the same dict as `pluvial: applicable` and
`waterlogging: applicable`. All 8 `compute_*` functions in `susceptibility/` and
`perception/` enumerated via AST — **none takes an applicability argument.**

`pipeline.py:412` computes `hydrological_surfaces`; `:413` computes
`applicability` — **after.** Designed as a router, wired as a report.

**C20 — It does not gate its own siblings either** [E]

**C32 — The frontend never renders it** [E]
`applicability` appears **exactly once** in all of `geowatch-ui/src/`, at
`App.jsx:493`, as `layer.intersection_type === 'aoi_total_given_layer_applicability'`
— an unrelated string comparison. `result.applicability` is never read. Not in
`NAV_SECTIONS` (six entries, lines 674-681).

*C14 → C20 → C32 is **one signal dying three times.***

**C23 — Gate C waiver dropped on the `not_calculated` path** [E]
Forced that path: returns exactly `['label','layer_id','reason','status']`.
`product_validation_status` absent; `.get()` → `None`, indistinguishable from
"Gate C passed." *All five layers took the success path on the real runs and did
carry it — surfacing this naturally needs an inland AOI.*

**C24 — Frontend never reads `product_validation_status`** [S]
Zero occurrences in `App.jsx`, so exposure is surfaced with no
screening/experimental marker — the exact outcome the Gate C waiver text was
written to prevent. **The susceptibility panel does carry such a marker, in the
same file** — so the discipline exists; it just was not applied here.

*Relevant to Decision 17: Gate C's formal closure (via advisor review against
D.7's five requirements) does not resolve C23/C24 — those are implementation
defects in how the waiver status propagates, independent of how Gate C itself
is validated.*

### Contract enforcement

**C31 — Palette drifted on all 8 categories** [E]
**0/8 exact matches.** Worst: `dense_vegetation`, Δ(34, 37, 75) — forest green in
the server-rendered PNG vs mint green in the legend beside it. The deltas are
small enough to read as opacity variation, which is what makes misidentification
easy.

*The quick fix is copying values across. **The correct fix is a single source of
truth** — emit the palette into `result.json` and have the frontend read it, so
drift becomes structurally impossible.*

**C4 — RGB band order assumed, unverified at runtime** [S]
`RGB_BAND_INDICES` picks fixed indices (2/1/0) assuming the GeoTIFF's band order
matches `["Blue","Green","Red","NIR","SWIR1","SWIR2"]`. Enforced only by a
top-of-file comment. If it drifts, R/G/B are silently swapped into both SAM and
the classifier.

**Under Decision 15:** does not qualify for downgrade — never observed firing
is not confirmed unreachability. Stays at original severity.

**C10 — Deployed CAAT thresholds have no provenance** [E]
Live run logged `Loaded CAAT thresholds (source_checkpoint=?,
verified_sanity_check_miou=?)`. The file's own caveat states it derives from **11
LOCO fold models, not the production checkpoint.** The stricter validator exists
in `resnet_classifier.py` — **dead code** — and would reject this file.
`pipeline.py:260` calls the weaker `load_caat_thresholds`.

*The provenance discipline survives the architecture change: whatever calibration
artifact replaces CAAT must record its source and the loader must **refuse**
mismatches. Do not leave the strict validator in dead code again.*

**C13 — `primary_tile` spatially wrong for multi-tile AOIs** [E]
4 tiles; `tile_dimensions` 892×891; `primary_tile` **512×512**. **102/116
segments (87.9%) fall outside it**; it covers 57.4% of AOI width. No full-AOI RGB
basemap is ever written, so there is nothing correct for the field to point at.
The in-code comment claiming the frontend projection "works unchanged regardless
of how many tiles" is false for the base image.

*The live frontend is immune — it never reads `primary_tile`. Any other consumer
is not.*

**Under Decision 15: DOWNGRADED.** Confirmed no consumer (live frontend never
reads this field) — qualifies under the strong bar. **Severity downgrade does
not remove item 46** (full-AOI basemap, or remove the field) — the field still
points at nothing correct and the fix stands regardless of current risk.

### Trust boundaries

**C1 — QA60 cloud mask may be zero-filled** [R]
`mask_s2_clouds` inspects only QA60 bits 10/11. ESA has deprecated/zero-filled
QA60 for scenes under newer processing baselines, meaning the mask may reject
nothing while `observation_quality.cloud_pct` — computed correctly via a
*separate* SCL path — reports a normal-looking value.

**Amplified by C14:** `compute_applicability()` takes **no** `observation_quality`
argument, so cloud/shadow metrics gate **nothing** in the main path.
*(`zonal/landcover_screening.py:231-235` does gate on `valid_observation_pct` —
ward path only.)*

*The fix is available and already half-built: mask from SCL, which the codebase
already computes correctly in `compute_observation_quality`. Two code paths that
were never joined.*

**Sequencing note:** this fix (item 51) must precede item 18 (temporal
variance layer) — std-dev is maximally sensitive to exactly the cloud-leakage
outliers an unreliable QA60 mask would introduce.

**C2 — No post-download GeoTIFF validation** [R]
`export_image_local` trusts `geemap.ee_export_image` with no check on dimensions,
band count, or CRS. `api.py:47` sets `MAX_AOI_AREA_KM2 = 100.0` — **20× larger**
than `tiler.py`'s documented "< 5 sq km" safe range.

*Not triggered: a 75 km² AOI (15× the documented limit) exported correctly at
892×891.*

**Under Decision 15:** does not qualify for downgrade — never triggered is not
confirmed unreachable. Stays at original severity.

**C8 — INFORM scores never validated** [S]
`vulnerability_score` and `coping_capacity_score` are read from Excel and returned
under `"scale": "0-10"` with `"status": "available"`, with no check that the value
is numeric, non-null, or in range. The `PCT_MISSING`/`RELIABILITY` columns exist
to flag this and are read but never used to gate status.

*Was rated latent because `risk/compute.py` gates only on `status` and never reads
`raw_score` numerically. **Module 6 changed this:** `App.jsx:568/572` renders
`raw_score` directly with no type guard, so an invalid cell displays to the user
as `x / 10`.*

### Orchestration and hygiene

**C17 — `/api/demo` serves a stale test artifact** [E]
37 directories match `startswith('dharavi')`; lexicographic last is
`dharavi_test_20260806_114208` while newest-by-mtime is
`dharavi_phase11_postfix_20260807_125913`. `'2' < 't'`, so **no future run can
ever sort above it.** Both new `phase1_dharavi_*` runs also sort below.
**The 5-day auto-refresh is inert from the consumer's view.**

**C18 — In-band failure, out-of-band detection** [S]
`run_pipeline` signals failure by `return {"status": "failed"}`; the scheduler
detects failure via `except`. So a failed refresh prints **"refreshed OK"** and
leaves an empty run directory.

*Not observed — no run failed. Needs a deliberately imagery-less AOI to surface.*
**Under Decision 15:** does not qualify for downgrade on that basis alone.

**Broad `except Exception` — cross-cutting** [S]
Every function in `hydrology.py`, `coastal.py`, `rainfall.py`, and
`vulnerability_sources.py` wraps its body in `try/except Exception`, returning an
identical `status: "unavailable"` for a GEE quota error, a network timeout, a
wrong band name, a Python typo, or a genuine data gap.

*A deliberate "fail visibly but gracefully" pattern that does not distinguish
exception **classes** — so a genuine software bug produces the exact same
downstream signature as "this AOI legitimately has no data."*

**`batch_run_log.json` truncates its own history** [E]
Each invocation truncates; the 11-city history was clobbered by a later
single-city run.

---

## NEEDS FATE — flagged during consolidation, not yet triaged

*C34–C38 were logged as "NEW findings from Part 1" in the original ledger but
never received a fate category. They now carry a summary-table row
(NEEDS FATE, 5) but still no assigned fate. Partial progress since: C34 and C35
are scheduled as `05_BUILD_MANUAL.md` item 47, and the GHS-BUILT-S audit
(commit `5331f0a`) has verified the asset that C36 and C38 concern (see those
entries). Fate assignment is still outstanding and needs the same triage
attention every other finding in this document received.*

### C34 — `GET /api/runs/{run_id}` builds a path from an unvalidated parameter [S]
`api.py:256` constructs `Path(f"data/pipeline_runs/{run_id}/result.json")` from an
unvalidated path parameter. Same bug class as C16, different sink. Starlette
normalizes some traversal in the URL path, so it is likely weaker — but untested.

*Impact shape differs from C16: a read returning file contents, so disclosure
rather than directory creation. Percent-encoded, mixed-separator, and
absolute-path variants were **not** tried.*

**Priority note:** same bug class as C16 (which got 72 tests and was verified
against the unpatched file). Now scheduled as `05_BUILD_MANUAL.md` item 47,
alongside C4/C10/C13 — same "trust boundary enforced only by convention, not
code" shape — with C35 folded into the same pass and the same
verify-against-the-unpatched-endpoint discipline required at acceptance.

### C35 — `WATCHED_AOIS` bypasses the API boundary [E]
The scheduler calls `run_pipeline` with no validation. All three configured
labels (`dharavi`, `nairobi`, `jakarta`) pass the whitelist, so **no current
exposure** — but `WATCHED_AOIS` has no enforced constraint, so a future edit
would reach path construction unimpeded, under the scheduler's privileges.

**The important implication: "validated at the API boundary" is not the same as
"validated everywhere."** Relevant to the validation-ownership decision, and
compounds C34's priority — the API boundary is not the only door.

*Scheduled with C34 as `05_BUILD_MANUAL.md` item 47 ("address C35 in the same
pass"): the boundary check must be confirmed everywhere `run_pipeline` or path
construction from a label can be reached, not only at the two known sinks.*

### C36 — `GHSL_BUILTUP_ASSET` pins the epoch in the asset string [E]
`configs/exposure_constants.py:58` hardcodes `.../GHS_BUILT_S/2020`.
`ee.Image(...)` with no collection query, no `aggregate_max`, no dynamic
selection. **Cannot reach another epoch without editing the constant** — while
2025 and 2030 sit in the same P2023A collection with identical bands.

*Contrast: the WorldPop selection logic has **no hardcoded year at all** —
`aggregate_max("year")` then filter. It would pick up newer epochs
automatically.*

**Relevant to Decision 13's validation gate (Decision 13 — REOPENED BY
EVIDENCE):** as originally specified, GHS-BUILT-S is a (weaker, non-independent)
reference for `built` fraction validation, and this finding means that reference
is pinned to a 2020 epoch regardless of the Sentinel-2 composite date — a real
temporal-mismatch caveat, distinct from the lineage-independence caveat already
noted there. **This role is conditional on the item 21 decision, awaiting
sign-off:** the proposed re-scope takes `built` from vector footprints and does
not spectrally estimate or GHS-validate it, in which case GHS-BUILT-S is an audit
target (as in commit `5331f0a`) rather than a validation reference. The
epoch-pin caveat applies wherever GHS is used as a reference under either
outcome.

*Update (commit `5331f0a`, GHS-BUILT-S audit): the collection was verified live
— twelve epochs (1975–2030 by 5) are present, at 100 m Mollweide. The pin is
real, but dynamic selection would not close the temporal gap: post-2020 epochs
are extrapolated, and GHS 2025 is bit-identical to 2020 across all 115 Accra
comparison cells (0 differing). For a recent Sentinel-2 composite the mismatch
is irreducible with this product. So the fix here is dynamic epoch selection
for pre-2020 comparisons and a projected/observed flag, not a route to a
current-date reference.*

### C37 — `limitations` constructed before the query it describes [S/R]
`exposure_sources.py:53` builds the limitations list; `:63` runs the GEE query. If
a fresher epoch appeared, the output would carry `population_year: 2025` and the
string "Population data caps at year 2020" **in the same dict.**

*Split confidence deliberately: the construction order is static and certain
[S]; the self-contradicting output is contingent on an upstream update that has
not happened [R].*

**This inverts the usual failure:** not a hidden caveat on degraded data, but a
**stale caveat welded onto fresh data.**

### C38 — `GHSL_BUILTUP_ASSET`'s UNVERIFIED label is stale [E]
Labelled UNVERIFIED in the constant, the docstring, and a runtime print at
`pipeline.py:704`. It resolves live with bands
`['built_surface', 'built_surface_nres']`.

*Claim narrowed rather than declared verified: existence, bands, and load
behaviour confirmed; no pixel-level agreement comparison exists
(`agreement_status: "not_yet_compared"`); licence and resolution not re-checked.
The finding is that the blanket label overstates what is outstanding.*

*Update (commit `5331f0a`, GHS-BUILT-S audit): resolution is now confirmed —
100 m Mollweide, `crs_transform [100,0,-18041000,0,-100,9000000]`, and
`built_surface` is a per-cell area in m² (fraction = `built_surface/10000`),
matching the existing `GHSL_RESOLUTION_M = 100`. All twelve epochs resolve. A
pixel-level agreement comparison against VHR impervious labels now exists
(Nairobi, 567 cells: r 0.921, R² 0.394, MAE 0.178, bias −0.171 — right ranking,
systematic ~17-point under-call, worse in informal fabric). What the audit did
not do: re-check the licence, or compare GHS against the unmixing output
specifically. The residual is that `configs/exposure_constants.py:58`, its
docstring, and the `pipeline.py:704` runtime print still say `UNVERIFIED`.*

---

## Patterns to carry forward

These are not findings. They are the shapes of failure this codebase produces,
and they will recur in new code unless deliberately designed against.

**1. The safety net that cannot detect what it was built for.**
`verify_masks.py` checks set membership under a bug that preserves set
membership (C30). `check_generated_water_mask.py` produces overlays with no
metric gate and passed a mask that is half wrong (W4). `applicability` computes
the right verdict and nothing reads it (C14/C20/C32).

**The test:** does the check FAIL against a known-broken input? If it cannot, it
is decoration. This is why the C16 fix was verified against the unpatched file.

**2. A contract asserted only in prose.**
A Python comment asserting a JavaScript constant must match — 0/8 (C31). A
band-order contract in a top-of-file comment (C4). A provenance check in dead
code (C10). Comments do not fail CI.

**3. A derived number presented as a measured one.**
C19's "56.12" was reproducible only by rescaling; the "exactly 1/(1−0.2574)"
identity was true by construction. **Both would have survived a line-reference
audit.** Derived figures must name the operation that produced them.

**4. Absent, zero, and failed collapsed into one value.**
C6, C19, C21, C25, C26, C27, C33, and the broad-`except` pattern. Three epistemic
states, one representation. **Decision 14 is the direct fix for this pattern
under the new architecture** — see item 33.

**5. A claim latched before the thing it claims about.**
C15 (`osm_available` before the distance map), C37 (`limitations` before the
query). A claim must be **derived from an outcome**, never asserted ahead of it.

**6. Identity from incidental position.**
C9 (rank in a sorted list), C17 (lexicographic order as chronological). Both work
until the incidental property changes.

---

## Part 6 translation note

Items 33–39 in `05_BUILD_MANUAL.md` were originally specified in the
vocabulary of the deleted CAAT-era pipeline (`category_area_pct`,
`unknown_pct`, discrete-class language). Decision 14 replaces that vocabulary
with: known-pixel denominator, mandatory `observed_fraction` field, and three
separately-reported non-observation fields (shadow, cloud/nodata,
low-confidence unmixing) rather than one merged "unknown." Part 6's acceptance
criteria need restating against these fraction-pipeline fields before
building — the principles above (particularly Pattern 4) carry forward
unchanged; the field-level specification does not.
