# GeoWatch Audit — Consolidated Findings (V2)

**This is the authoritative audit document.** It supersedes the scattered
corrections in `AUDIT_FINDINGS.md`, which is retained as the full
investigation history (including a retracted verdict and its correction).
V2 is readable standalone; consult V1 only for the reasoning trail.

**Status of evidence.** Every finding carries a classification and a
confidence level:

| Classification | Meaning |
|---|---|
| **CONFIRMED BY EXECUTION** | Observed on a real run. Trust fully. |
| **STILL VALID, NOT EXECUTED** | Reasoned from code; not contradicted by anything observed; not independently confirmed. |
| **CORRECTED** | Mechanism real; magnitude, severity or framing changed by measurement. |
| **REFUTED** | Contradicted by execution. |
| **SUPERSEDED BY REFRAME** | No longer the right description of the problem. |

Confidence: **[E] empirical** (measured) · **[S] static** (code/artifact
inspection, deterministic) · **[R] reasoned** (inferred, unverified).

Runs backing this document (2026-08-20, environment unmodified, GEE
credentials already valid):

| Run | AOI | Raster | Tiles |
|---|---|---|---|
| `phase1_dharavi_20260820_125646` | 72.836,19.037→72.862,19.060 | 291×257 | 1 |
| `phase1_dharavi_20260820_125809` | identical (determinism control) | 291×257 | 1 |
| `phase1_multitile_20260820_130117` | 72.80,19.00→72.88,19.08 (~75 km²) | 892×891 | 4 |

---

## Executive summary

**The central finding of this audit has changed.**

The investigation began around a reported confusion between `paved_road` and
`dense_informal_roofing`, and V1 built an extensive case around that *pair*.
Execution shows the pair framing is **incomplete and somewhat misleading**.

`paved_road` is not one half of a symmetric confusion pair. It is a **magnet
class** — a diffuse, high-prior category that absorbs probability mass across
the entire scene:

- It is the **top-2 partner for all six other classes** (55.4%–80.9%).
- It appears in the **top-2 for 85.1%** of all pixels and the top-3 for 96.4%.
- Its **median** softmax probability is **0.3244**, versus 0.0014–0.0128 for
  every other class — it is high *everywhere*, not bimodal.
- On pixels it does *not* win, it still holds **0.1420** mean probability —
  more than double the next class (0.0681).
- It is **42.15%** of raw argmax against **17.8%** of pixel-level supervision:
  roughly **2.4× over-predicted**.

Every other class is sharp and localised: high probability where it wins, near
zero elsewhere. `paved_road` alone behaves as a default.

This reframes the system's core problem from *"two classes are confusable"* to
**"one class has been learned as a generic urban texture and is the nearest
neighbour for anything ambiguous."** The consequences ripple: `CONFUSION_PAIRS`
encodes the wrong second pair, the separation loss was aimed at a pair rather
than at a prior, the road-proximity penalty is a band-aid over a class-prior
problem, and the unknown mass is dominated by one class rather than shared.

**Three headline figures were re-derived.** One held, two did not:

| Figure | V1 claim | Measured | Outcome |
|---|---|---|---|
| Pair share of unknown mass | 72.9% | **70.1%** (production) / 72.4% (no penalties) | ✅ holds |
| Unknown-pixel rate | "~50%" | **25.73%** / **28.79%** | ❌ stale by ~2× — now **explained** |
| `paved_road` supervision share | 41.0% | **41% by patch, 17.8% by pixel** | ⚠️ patch-level only |

**The system is deterministic.** Two identical runs produced bit-identical
landcover maps (0/74,787 differing pixels) and identical scores throughout.
Non-reproducibility observed elsewhere (C27) is caused by wall-clock GEE
timeouts, not by model or pipeline nondeterminism.

---

## Root-cause investigations

### R1 — Why `paved_road` is the magnet class **[E]**

Three candidate mechanisms were tested; two are eliminated.

**Eliminated: the final classifier layer.** `decoder.classifier` bias spread is
0.0617 across all seven classes, and `paved_road`'s bias (−0.0166) is *not* the
highest (`active_construction` at +0.0134 is). `paved_road` also has the
**lowest** weight-norm (0.8548 vs up to 0.9616). The magnet effect is not in
the output layer's parameters.

**Eliminated: class weighting.** `paved_road` carries the **lowest** CE weight
(0.1707 of seven). Weighted cross-entropy is equivalent to resampling class *c*
by *w_c*, so a low weight **suppresses** predictions of that class. The
weighting is fighting the over-prediction, not causing it (see R2).

**Confirmed: a diffuse learned prior, traceable to label geometry.**

| class | mean *p* | median *p* | argmax % | mean *p* when **not** winner | rank-2 rate |
|---|---:|---:|---:|---:|---:|
| **paved_road** | **0.3757** | **0.3244** | 42.45% | **0.1420** | **42.70%** |
| dense_vegetation | 0.2099 | 0.0041 | 22.43% | 0.0255 | 5.11% |
| sparse_informal_roofing | 0.1528 | 0.0053 | 13.66% | 0.0566 | 15.44% |
| dense_informal_roofing | 0.1317 | 0.0128 | 11.36% | 0.0681 | 20.18% |
| active_construction | 0.0606 | 0.0052 | 4.98% | 0.0321 | 7.81% |
| vegetation_clearing | 0.0426 | 0.0046 | 2.83% | 0.0264 | 6.70% |
| standing_water | 0.0267 | 0.0014 | 2.29% | 0.0070 | 2.07% |

The diagnostic column is **median *p***. `dense_vegetation` has a comparable
*mean* (0.2099) but a median of 0.0041 — it is confident where it belongs and
silent elsewhere. `paved_road`'s median (0.3244) is ~25–230× higher than every
other class's, and close to its own mean: it is **uniformly elevated**, not
concentrated.

**The mechanism ties directly to C29.** `paved_road`'s supervision comes
overwhelmingly from OSM road geometry buffered to real-world width. At 10 m
GSD, every road class except `motorway` is **sub-pixel wide** (residential 5 m
= 0.50 px; service 4 m = 0.40 px). Cape Town's 192 generated road records have
a median mask area of 23.5 px — thin ribbons. A pixel labelled `paved_road` is
therefore physically a *mixture* of road and whatever abuts it, which in a
dense settlement is roof, and its spectral signature is correspondingly broad.
The model learns `paved_road` not as "asphalt" but as **"generic mixed urban
texture"** — which is, by construction, the nearest class to any ambiguous
pixel in an urban scene.

This is a single coherent explanation linking label geometry → learned class
breadth → magnet behaviour → unknown-mass dominance.

*Not fully established:* the model's actual feature-space geometry was not
inspected (no embedding analysis), and the sliding-window patch source is
absent from the pixel-count table. The causal chain is strongly supported but
one link — that spectral mixing specifically produces the broad prior — remains
inference rather than measurement.

### R2 — The CLASS_WEIGHTS patch/pixel mismatch: resolved **[E]**

V1 flagged that `CLASS_WEIGHTS` are computed as inverse **patch** frequency
(`Counter(p['label'] for p in train_patches)`) and applied to a **per-pixel**
`CrossEntropyLoss`, without establishing the direction of the effect. Resolved:

| class | actual (checkpoint) | patch-derived | pixel-derived | pixel/actual |
|---|---:|---:|---:|---:|
| paved_road | **0.1707** | 0.0415 | **0.2394** | **1.40×** |
| standing_water | 0.4915 | 0.3077 | **0.0868** | **0.18×** |
| dense_informal_roofing | 0.6135 | 0.7723 | 0.4782 | 0.78× |
| dense_vegetation | 0.3646 | 0.4354 | 0.2500 | 0.69× |
| sparse_informal_roofing | 2.9653 | 2.7287 | 2.8814 | 0.97× |
| vegetation_clearing | 1.3479 | 1.0771 | 1.6247 | 1.21× |
| active_construction | 1.0466 | 1.6372 | 1.4395 | 1.38× |

**Answer: the mismatch makes `paved_road` over-prediction *less* bad than
pixel-frequency weighting would have.** Pixel weighting would raise
`paved_road`'s weight 1.40× (0.1707 → 0.2394), pushing the model to predict it
*more*. The patch-derived weighting suppresses it harder, because `paved_road`
is patch-abundant (73.4% of the raw pool) but pixel-sparse (17.8%).

The mismatch is nonetheless a real defect, and its damage lands elsewhere:
**`standing_water`'s weight is inflated 5.7×** relative to pixel weighting
(0.4915 vs 0.0868), because water is patch-rare but pixel-dominant (49.1% of
labelled pixels — large filled polygons vs thin road ribbons). The weighting
statistic and the loss domain disagree in opposite directions for the two
classes whose label *geometry* differs most.

*Note:* the checkpoint's actual weights sit between raw-patch (0.0415) and
pixel-derived (0.2394) values because the notebook caps OSM sources at 25/city
before computing them. Both are patch statistics; the cap explains the gap.

### R3 — The origin of "~50% unknown": found **[E]**

Not a transcription error, not a different AOI. It describes a **superseded
system state**.

The trail, reconstructed from the code's own comments:

1. `caat_diagnostic.py`'s docstring records the original hypothesis verbatim:
   *"CAAT thresholds were computed from isolated single-patch forward passes,
   but production inference does sliding-window overlapping-window
   softmax-averaged inference, which systematically lowers confidence."*
2. It refers throughout to *"the ~50% unknown rate"* as the condition being
   diagnosed (lines 118, 181).
3. `recalibrate_caat.py`'s methodology string records the outcome: the new
   CAAT *"supersedes the original CAAT which was computed from isolated 64x64
   patch forward passes — see caat_diagnostic.py for the confirmed **+22pp
   unknown-rate gap** this was causing."*
4. `breakdown_unknown_class.py`'s docstring still cites "~50%" and **was never
   updated** after the thresholds were replaced.

**Measured confirmation of the mechanism** (current deployed CAAT, same tile):

| mode | stride | unknown | mean top-1 confidence |
|---|---:|---:|---:|
| production | 32 | 24.45% | **0.7264** |
| isolated | 64 | 11.33% | **0.8174** |

Sliding-window averaging lowers mean confidence by **0.091**. Thresholds
calibrated on isolated-patch confidences (~0.82) applied to production
confidences (~0.73) over-reject massively — the documented +22 pp.

**Arithmetic closes it:** 24.45% (current, production-calibrated CAAT) + 22 pp
= **46.4% ≈ "~50%"**.

The sign of my experiment (−13.12 pp, isolated has *fewer* unknowns) is the
same phenomenon seen from the opposite threshold regime: with today's
production-calibrated (lower) thresholds, isolated mode's higher confidences
clear them more easily. Both observations describe one mechanism.

**Conclusion: "~50%" is a stale pre-fix number describing the second of at
least three CAAT generations. The current real rate is 25.7%–28.8%. Any
argument in V1 conditioned on ~50% is overstated by roughly 2×.**

### R4 — Why C22's predicted effect does not occur **[E]**

V1 predicted no-data pixels would render as **maximum** pluvial susceptibility.
Observed: they render **mid-range**, *below* the known-pixel mean. The
correction is now understood, not merely observed.

The score is a quality-weighted mean over five components. Two are per-class:

- `impervious_px` — populated only for `paved_road` (1.0), `dense_informal_roofing` (0.9), `sparse_informal_roofing` (0.6). Component weight **0.70**.
- `infiltration_deficit_px = 1.0 − infiltration_px`, where `infiltration_px` is populated only for `dense_vegetation` (1.0) and `vegetation_clearing` (0.3). Component weight **0.56**.

`UNKNOWN` (255) is absent from **both** dictionaries. V1 reasoned about only
the second one and concluded "maximum deficit → maximum susceptibility." In
fact `UNKNOWN` is simultaneously **minimum on the impervious surface** (0.0)
and **maximum on the deficit surface** (1.0) — and the impervious component
carries the *larger* weight. The two omissions cancel, slightly favouring the
low side.

Analytic reconstruction versus the real PNG:

| class | imperv | deficit | predicted PNG (drain 0→1) | observed mean |
|---|---:|---:|---:|---:|
| paved_road | 1.00 | 1.00 | 188 → 223 | **197.9** |
| dense_informal_roofing | 0.90 | 1.00 | 181 → 216 | 186.1 |
| sparse_informal_roofing | 0.60 | 1.00 | 160 → 195 | 169.2 |
| **UNKNOWN (255)** | **0.00** | **1.00** | **119 → 153** | **125.4** |
| standing_water | 0.00 | 1.00 | 119 → 153 | 141.4 |
| active_construction | 0.00 | 1.00 | 119 → 153 | 125.8 |
| vegetation_clearing | 0.00 | 0.70 | 102 → 137 | 108.6 |
| dense_vegetation | 0.00 | 0.00 | 63 → 98 | 64.2 |

Predictions match observation within a few units (residual is the per-pixel
drainage term). Only `paved_road` is maximum on both surfaces, so only
`paved_road` sits at the top of the scale.

**The surviving defect is different from the one claimed:** no-data scores
*identically* to `standing_water` and `active_construction` (all three:
imperv 0, deficit 1.0). A pixel the model could not classify is indistinguishable
in the output raster from two real classes. That is a genuine problem — but it
is a **collision**, not an alarm.

### R5 — Other results that warranted explanation

**Determinism is exact. [E]** Two identical-parameter runs produced
byte-identical `landcover_map_full.npy` (0/74,787 differing pixels) and
identical values for every susceptibility score, the impervious fraction, the
segment count, and the exposure population (282,983). This matters because it
**isolates C27**: ward-screening non-reproducibility is not model
nondeterminism — it is the 90-second wall-clock GEE timeout, exactly as C27
diagnosed.

**Ambiguity composition is AOI-dependent. [E]**

| AOI | roofing\|road | veg\|water | unknown |
|---|---:|---:|---:|
| Dharavi | 5.25 pp | 0.03 pp | 25.74% |
| Dharavi (rerun) | 5.25 pp | 0.03 pp | 25.74% |
| multi-tile (75 km²) | 2.42 pp | 0.89 pp | 28.79% |

The wider AOI contains more water, so the vegetation/water pair becomes
non-trivial (0.89 pp) where in Dharavi it is negligible (0.03 pp). The
roofing/road pair more than halves. Conclusions drawn from a single small AOI
do not transfer cleanly — a caution that applies to much of V1.

**`check_confusion_pair.py`'s own criterion is not met. [E]** The script
declares a confirmed pair only when *both* directions exceed 40%. Measured:
paved→roofing **36.7%**, roofing→paved 52.4%. By its own rule it would print
*"NOT a clean confusion pair … more consistent with each class independently
being undertrained or having noisy/inconsistent ground truth labels"* — which
points at label quality, consistent with R1.

**A methodological note.** An early run appeared dead (empty log, no matching
process) yet had completed successfully; output was buffered and the process
check raced. No finding rests on that observation, but it is recorded because
it briefly produced a false "C18 confirmed" impression that was withdrawn.

---

## Findings

### Reframed (supersedes V1's central narrative)

**[SUPERSEDED BY REFRAME] F1 — `paved_road` is a magnet class, not half of a pair. [E]**
See R1. V1's extensive "confusion pair" analysis remains factually accurate in
its particulars but describes a symptom of a broader pathology. All V1 material
framed as pairwise should be read through this lens.

**[SUPERSEDED BY REFRAME] F2 — `CONFUSION_PAIRS`' second entry is empirically wrong. [E]**
`inference.py` declares `{dense_vegetation, standing_water}`. Measured:
`dense_vegetation`'s top-2 is `paved_road` (79.4%, vs 9.3% standing_water);
`standing_water`'s top-2 is `paved_road` (72.5%, vs 22.3% dense_vegetation).
The ambiguity map therefore flags a pair that barely exists (0.03 pp on
Dharavi). *Severity: Moderate.*

**[SUPERSEDED BY REFRAME] F3 — The separation loss was aimed at the wrong target. [R]**
A margin loss between two classes cannot fix a class that is over-broad against
all six others. This does not contradict V1's five-mechanism analysis of why
the loss failed; it adds a sixth and more fundamental reason.

### Confirmed by execution

**[CONFIRMED] C9 — `segment_id` mis-joins `result.json` and `masks.json`. [E]**
Fresh run: 36 segments (ids 0–35) vs 44 masks (ids 0–43); **11/36 = 30.6%** of
segments have a bbox that disagrees with the `masks.json` entry of the same id,
with a clean one-position shift from id 25 onward. Magnitude is run-dependent
(67% on an earlier run). Root cause: `result.json` ids come from a counter over
*surviving* segments (post `w<8/h<8` filter) while `masks.json` ids come from a
counter over *all* masks. *Critical. Currently harmless for existing training
data — the eleven training runs predate Phase 2 — and irreversible the moment a
new annotation round runs (see C28).*

**[CONFIRMED] C10 — Deployed CAAT thresholds have no provenance and are not checked. [E]**
Live run logged `Loaded CAAT thresholds (source_checkpoint=?, verified_sanity_check_miou=?)`.
The file's own caveat states it derives from 11 LOCO fold models, **not** the
production checkpoint. The stricter check exists in `resnet_classifier.py`
(dead code) and would reject this file. *Critical.*

**[CONFIRMED] C11 — Penalties applied post-calibration. [E]** Neither
diagnostic nor the notebook that produced the deployed CAAT applies the
proximity penalties (verified: zero references), while `run_inference` does.
Measured effect: unknown 24.45% → 25.73% (**+1.28 pp**); `standing_water`
unknown count 564 → 1111 (**+97%**); `paved_road` 11,899 → 12,098 (+1.7%).
*Mechanism and direction confirmed; magnitude bounded — V1's "systematic
over-rejection" framing overstated the aggregate effect.* **Severity: Critical → Moderate.**

**[CONFIRMED] C13 — `primary_tile` is spatially wrong for multi-tile AOIs. [E]**
4 tiles; `tile_dimensions` 892×891; `landcover.png` 892×891; **`primary_tile`
actually 512×512**. Segment bboxes reach x=891, y=890. **102/116 segments
(87.9%) fall outside `primary_tile`**, which covers 57.4% of AOI width and
57.5% of height. No full-AOI RGB basemap is ever written. *Critical — worse
than V1 estimated. The live frontend is immune (it never reads `primary_tile`);
any other consumer is not.*

**[CONFIRMED] C14 / C20 — The out-of-distribution verdict gates nothing. [E]**
At `unknown_pct = 60`: `urban_landcover_model: out_of_distribution` returned in
the same dict as `pluvial: applicable` and `waterlogging: applicable`. No
susceptibility function accepts an applicability argument. *Critical.*

**[CONFIRMED] C16 — Unauthenticated path traversal via `aoi_label`. [E]**
`'../../../../tmp/pwn'` normalises to `../../tmp/pwn_<timestamp>`, escaping the
data root. Verified by path arithmetic only — **nothing was created**. *Critical.*

**[CONFIRMED] C17 — `/api/demo` serves a stale test artifact. [E]** 37
directories match `startswith('dharavi')`; lexicographic last remains
`dharavi_test_20260806_114208` while newest-by-mtime is
`dharavi_phase11_postfix_20260807_125913`. Both new `phase1_dharavi_*` runs
also sort below it. *Critical.*

**[CONFIRMED] C19 — Imperviousness deflated by the unknown rate. [E]**
Emitted `impervious_fraction_pct = 41.68`; recomputed with a known-pixel
denominator = **56.12**. Understatement factor **1.347×** at 25.74% unknown —
exactly `1/(1−0.2574)`. Direction is the dangerous one: higher unknown → lower
apparent imperviousness → settlement reads as *less* flood-prone. *Critical.
See CORRECTED note on magnitude.*

**[CONFIRMED] C21 — A total landcover failure emits a confident "very_low". [E]**
`compute_hydrological_surfaces({})` returns `impervious 0.0`, `infiltration 0.0`,
**no `status` key**. Fed to `compute_waterlogging_susceptibility` with HAND
unavailable: **`status: "experimental"`, `score: 0.0`, `class: "very_low"`**.
The guard `impervious_fraction_pct is not None` is vacuous because the producer
has no failure path. Duplicated at `applicability.py:133` and
`waterlogging.py:57` — the chain fails open twice. *Critical — worse than V1
predicted: it produces an affirmatively reassuring hazard class.*

**[CONFIRMED] C23 — Gate C waiver dropped on the `not_calculated` path. [E]**
Forced that path: returns exactly `['label','layer_id','reason','status']`.
`product_validation_status` absent; `.get()` → `None`, indistinguishable from
"Gate C passed". On the real runs all five layers took the success path and did
carry it — the defect needs an inland AOI (coastal `not_calculated`) to surface
naturally. *Critical.*

**[CONFIRMED] C25 — All-unknown ward scores as 0.0 imperviousness. [E]**
Reproduced zonal's construction: an all-unknown 40×40 ward yields
`category_area_pct = {}` → `impervious_fraction_pct 0.0`; the zero-pixel guard
does **not** fire (`pixel_count = 1600`). A 50%-unknown ward reports
`impervious 50.0` where the known-pixel truth is 100.0. *Critical.*

**[CONFIRMED] C26 — No per-ward unknown fraction is emitted. [E]** No field
carries it; a 100%-unknown and a 50%-unknown ward differ only by an inference
from the `category_area_pct` sum that no consumer is instructed to make. This
is the field that would render C25 detectable. *Critical.*

**[CONFIRMED, Moderate] Derived per-segment statistics survive the OSM override. [E]**
Segment 25: `dominant_landcover_category: unpaved_dirt_road`,
`label_source: osm_vector`, **`landcover_purity_pct: 0.0`** — the 0.0 describes
the vanished "unknown" state.

**[CONFIRMED, Moderate] `summary.unknown_segments` under-reports. [E]**
`unknown_segments: 0` while `unknown_pct: 25.74` and one segment was
OSM-overridden away from unknown.

**[CONFIRMED, Moderate] `dominant_category` is an argmax over a partial distribution. [E]**
`dominant_category: "paved_road"` at 25.97% while 25.74% of the raster is
unknown — the "dominant" class barely exceeds the unclassified fraction.

### Corrected

**[CORRECTED] C22 — No-data renders mid-range, not maximum. [E]**
Observed: unknown pixels mean **125.4**, median 124, range 118–153; known
pixels mean **149.1**, range 63–220; **0.0%** of unknown pixels at the PNG
maximum. Mechanism explained in R4: `UNKNOWN` is minimum on the impervious
surface *and* maximum on the deficit surface, and the two cancel. **V1's
consequence claim — "painted the most alarming" — is REFUTED.** The surviving
defect is a *collision*: no-data is indistinguishable from `standing_water` and
`active_construction`. **Severity: Critical → Moderate.**

**[CORRECTED] C15 — Real bug, precondition absent. [E]** Both runs: **zero**
−1.0 sentinels; real scores 0.162–0.985 (mean 0.831); `road_access_scores_reliable:
true` was *accurate*. OSM returned 1,694 roads and 15,912 rasterized road
pixels, so the `road_px_count == 0` precondition never fired. **Not refuted —
latent.** *Severity: Critical → Moderate (conditional).*

**[CORRECTED] The "~50% unknown" figure. [E]** Stale by ~2×; origin identified
(R3). Real rate 25.73%/28.79%. **Every V1 argument conditioned on ~50% is
overstated by roughly a factor of two** — notably C19's severity framing and
parts of the C14 narrative. Directions unchanged; magnitudes not.

**[CORRECTED] The "41% `paved_road`" figure. [E]** A **patch** statistic. At
pixel level `paved_road` is **17.8%** and `standing_water` dominates at
**49.1%**. Ratio to `dense_informal_roofing`: **18.62× by patch, 2.00× by
pixel**. Raw pool is 73.4% paved_road by patch; the notebook's 25/city caps
reduce that to the checkpoint's implied 41%.

| class | patches | patch % | pixels | pixel % |
|---|---:|---:|---:|---:|
| paved_road | 987 | 73.4% | 86,349 | 17.8% |
| standing_water | 133 | 9.9% | 238,265 | **49.1%** |
| dense_vegetation | 94 | 7.0% | 82,695 | 17.1% |
| dense_informal_roofing | 53 | 3.9% | 43,230 | 8.9% |
| active_construction | 25 | 1.9% | 14,360 | 3.0% |
| vegetation_clearing | 38 | 2.8% | 12,723 | 2.6% |
| sparse_informal_roofing | 15 | 1.1% | 7,174 | 1.5% |

*Caveat: a proxy for training supervision, not a reconstruction — the notebook
caps OSM sources and adds sliding-window patches absent from this pool.*

**[CORRECTED] C12 — CAAT's design flaw stands; its consequence is reframed. [S/R]**
The calibration remains a pure recall criterion (10th percentile of
correctly-predicted confidence, no precision term), structurally unable to
suppress confident error. But R3 shows the *unknown-rate* complaint that
motivated the CAAT work was a threshold/inference-mode mismatch, now fixed. The
precision gap is real and unaddressed; the crisis framing around it was
inherited from a resolved problem. *Critical → Moderate.*

### Still valid, not executed

These were not contradicted by anything observed, and were not independently
confirmed.

| # | Finding | Why not executed | Conf |
|---|---|---|---|
| **C1** | QA60 cloud mask may be zero-filled on newer processing baselines | Requires per-scene band inspection, not a pipeline run | [R] |
| **C2** | No post-download validation of the exported GeoTIFF | **Not triggered** — a 75 km² AOI (15× the documented 5 km² limit) exported correctly at 892×891. No demonstrated trigger. | [R] |
| **C3** | Training-path band-count mismatch warns but does not fail | Not in the live path (`pipeline.py` never imports `generate_tiles`) | [S] |
| **C4** | RGB band order assumed, unverified at runtime | Not triggered; contract held on these runs | [S] |
| **C6** | `get_osm_features` returns `None` for both "no roads" and "API failed" | Not triggered — OSM returned data on both AOIs | [S] |
| **C8** | INFORM scores never validated as numeric/in-range | Not triggered — values were floats (4.4, 4.2). **Note: the frontend renders `raw_score` with no type guard, so this is not fully latent.** | [S] |
| **C18** | In-band failure reported as success by the scheduler | **Not observed** — no run failed. Needs a deliberately imagery-less AOI. | [S] |
| **C24** | Frontend never reads `product_validation_status` (0 occurrences) | Static; verified by grep | [S] |
| **C27** | Ward hazard tiers non-reproducible via 90 s GEE timeout | Not re-run; rests on two disagreeing on-disk ward JSONs. **R5 strengthens it** by eliminating model nondeterminism as an alternative explanation. | [E prior] |
| **C28** | `annotate.py` would bake C9's mis-join into `annotations.json` | Not executed — the annotation GUI was deliberately not run | [S] |
| **C29** | Road labels sub-pixel at 10 m GSD | Geometry confirmed by arithmetic; **spectral mixing never measured**. R1 elevates this from a labelling concern to the probable root of the magnet class. | [S/R] |
| **C30** | `verify_masks.py` checks id existence, not correspondence; never run post-Phase-2 | Static + on-disk report inspection | [S] |
| **C31** | Palette drifted on all 8 categories (0/8 matches) | Static constants | [S] |
| **C32** | `applicability` never rendered by the frontend | Static | [S] |
| **C33** | Legend iterates a hardcoded list; absent renders as "0.0%" | Static | [S] |

All Moderate and Minor findings from V1 not listed above remain **STILL VALID,
NOT EXECUTED** unless contradicted here. V1 §§ Ingestion, Classification,
Orchestration, Downstream, Training/Annotation, Frontend retain the full
catalogue.

### Refuted

**[REFUTED] C22's consequence claim** — "no-data pixels render as maximum
susceptibility, visually indistinguishable from genuine high risk." Measured
mid-range, below the known-pixel mean. Mechanism retained (see CORRECTED).

No other V1 finding was outright contradicted by execution.

---

## Confirmed-good behaviour

Recorded because an audit that reports only defects misrepresents the system.

- **Determinism is exact** — bit-identical maps and scores across identical runs. **[E]**
- **The pipeline runs clean end-to-end** on both a 1-tile and a 4-tile AOI with no code changes; environment, credentials and dependencies were already correct. **[E]**
- **`GATE_C_STATUS` is in sync** with `PROJECT_GATES.md` and propagates into `result.json` on the success path (all five layers carried it). **[E]**
- **Population is `None`, never a fabricated 0**, when unavailable. **[S]**
- **The WorldPop scale-bug fix holds** — `reduceRegion` uses the image's own CRS/transform with no `scale=`. **[S]**
- **`risk/compute.py` refuses to fabricate a risk score** even when all three inputs are available, rather than inventing a fusion formula. **[S]**
- **Unavailability is genuinely rendered**, not blanked, for every gated module in the frontend. **[S]**
- **The mosaic placement math is correct** — the 4-tile run produced a coherent 892×891 canvas. **[E]**
- **The RLE codec is lossless** across six edge cases. **[S]**

---

## Open questions

1. **Does spectral mixing specifically produce the broad `paved_road` prior?**
   R1's causal chain is strongly supported but the final link is inference. A
   feature-space or per-class spectral-variance analysis would settle it.
2. **What is the correct class weighting?** R2 establishes the *direction* of
   the patch/pixel mismatch but not what should replace it. Pixel weighting
   would worsen `paved_road` and gut `standing_water`; neither statistic is
   obviously right when label geometry differs this much between classes.
3. **How much of the magnet effect survives a taxonomy merge?** If
   `paved_road` and the roofing classes merge into one built class, does the
   merged class remain diffuse, or does the breadth resolve?
4. **What is the true unknown rate across all 11 cities?** Measured on two
   Mumbai AOIs only (25.7%, 28.8%). R5 shows AOI dependence is material.
5. **Is `standing_water`'s 49.1% pixel share an artifact of the water-mask
   generator?** It is patch-rare and pixel-dominant; no audit of
   `generate_osm_water_masks.py` was completed.
6. **C18, C1, C2/C3/C4 have no demonstrated trigger.** They may be
   unreachable in practice or merely untested.
7. **Nothing here measures correctness.** Every result describes what the
   system *does*. No ground truth was consulted; the independent gold set
   remains the missing instrument.

---

## Reading guide

- **This document (V2)** — current best understanding. Build on this.
- **`AUDIT_FINDINGS.md` (V1)** — full investigation history: per-file
  catalogues, the complete Moderate/Minor lists, the retracted
  train/inference-mismatch verdict and its correction, and the Phase 1
  observed-vs-predicted table in raw form. Retained deliberately; the
  reasoning trail, including its errors, is part of the record.

---

## Water Mask Audit

Scope: `generate_osm_water_masks.py`, `merge_osm_water_masks.py`,
`check_generated_water_mask.py`, and the on-disk artifacts they produced for
all 11 training cities. Same format and confidence tagging as the module
audits in `AUDIT_FINDINGS.md`.

**Motivating question (from Open Questions #5):** is `standing_water`'s 49.1%
pixel-level dominance an artifact of the mask generator?

### ⚠ Answer: No. The generator is not the cause — but it has a separate, worse problem.

`standing_water`'s pixel dominance comes overwhelmingly from **human
annotation**, not from the OSM generator:

| Source | annotations | total px | share of all `standing_water` px |
|---|---:|---:|---:|
| **Human** (`annotations.json`) | 32 | **206,512** | **86.7%** |
| OSM-generated (`osm_generated_annotations_water.json`) | 101 | 31,753 | 13.3% |

And it is concentrated in **one city and largely one segment**:

| city | n | water px | tile px | % of tile | largest segment |
|---|---:|---:|---:|---:|---|
| **jakarta** | 3 | **163,151** | 262,144 | **62.2%** | id=0, **154,949 px**, bbox [0,0,511,446] |
| lagos | 20 | 19,864 | 173,940 | 11.4% | 4,797 px |
| accra | 3 | 10,302 | 130,650 | 7.9% | 5,566 px |
| dhaka | 3 | 5,802 | 149,410 | 3.9% | 2,484 px |
| capetown | 2 | 5,282 | 257,024 | 2.1% | 4,858 px |
| nusantara | 1 | 2,111 | 262,144 | 0.8% | 2,111 px |
| dharavi, nairobi, hcmc, kigali, guatemala | 0 | 0 | — | 0.0% | — |

**Jakarta alone supplies 68.5% of all `standing_water` supervision**, and a
single SAM segment covering 59.1% of its tile supplies 65%.

**That segment is genuinely water — the label is correct. [E]** Spectral test
on Jakarta's 6-band tile:

```
band     inside mask   outside
Blue        0.0385      0.0947
Green       0.0426      0.1072
Red         0.0284      0.1118
NIR         0.0175      0.1661     <- textbook open-water NIR absorption
SWIR1       0.0174      0.1780
SWIR2       0.0149      0.1545
NDWI        +0.425      -0.154
fraction of masked pixels with NDWI > 0:  100.0%
```

Jakarta's AOI (106.78,−6.13 → 106.85,−6.08) is coastal North Jakarta; a large
water body genuinely fills most of the frame. SAM segmented it correctly and
the annotator labelled it correctly.

**Root cause of the pixel dominance is therefore AOI selection and
pixel-weighted aggregation, not mask generation.** One of eleven AOIs happens
to be ~60% open water, and any pixel-weighted statistic over the pooled
training set inherits that. This is the mirror image of the `paved_road`
patch/pixel asymmetry: roads are many-and-thin, water is few-and-huge, and
neither statistic is meaningful without the other.

### Geometry comparison (directly answers investigation item 3) **[E]**

| source / class | n | median px | mean px | min | max | total px |
|---|---:|---:|---:|---:|---:|---:|
| HUMAN: standing_water | 32 | **874.0** | **6,453.5** | 108 | **154,949** | 206,512 |
| paved_road [OSM-gen] | 976 | **22.0** | **66.0** | 15 | 6,192 | 64,447 |
| standing_water [OSM-gen] | 101 | **60.0** | **314.4** | 15 | 9,656 | 31,753 |
| HUMAN: dense_vegetation | 94 | 272.0 | 879.7 | 69 | 27,749 | 82,695 |
| HUMAN: dense_informal_roofing | 53 | 317.0 | 815.7 | 66 | 11,820 | 43,230 |

Within the **OSM-generated** sources the asymmetry is real but modest —
water components are **2.7× larger by median, 4.8× by mean** than road
components — and roads still contribute **more total pixels** (64,447 vs
31,753). The extreme asymmetry appears only once human annotations enter:
human `standing_water` has a median area **40× larger** than generated road
components and a maximum **25× larger** than the largest generated water
component.

---

### Function-by-function

**`generate_osm_water_masks.py`**

- `find_run_dir(city)` — globs `data/pipeline_runs/{city}_*`, returns the lexicographically last match. (Same name-sort-as-recency assumption flagged elsewhere in this audit.)
- `query_overpass(query, retries=4)` — POSTs to three Overpass mirrors in rotation, 90 s timeout, backoff 15/30/45/60 s, raises `RuntimeError` after 4 failures.
- `query_overpass_waterway_lines(...)` — **Pass 1**: `way["waterway"]` within the tile bbox. All waterway sub-types, unfiltered.
- `query_overpass_water_polygons(...)` — **Pass 2**: `way["natural"="water"]` **and** `way["water"]`. Ways only; multipolygon relations explicitly not fetched.
- `get_utm_crs(lon, lat)` — standard zone arithmetic, EPSG 326xx/327xx. Verified correct for Jakarta (zone 48S → EPSG:32748).
- `main()` — reads `raw.tif` for CRS/transform and `tile_0_0.png` for extent; converts the tile window to WGS84 bounds; Pass 1 buffers each line by `WATERWAY_WIDTH_M[tag]/2` in local UTM then reprojects to raw CRS; Pass 2 keeps only **closed** rings (`coords[0] == coords[-1]`), validates with `is_valid`/`is_empty`, reprojects directly; rasterizes both onto `(tile_h, tile_w)` with `raw_transform`; unions them; writes `water_mask.npy` plus separate per-pass masks and a `meta.json` recording each pass's pixel contribution.

**`merge_osm_water_masks.py`**

- `encode_rle(mask_bool)` — hand-rolled column-major COCO-style RLE, matching `segmentation.py`'s decoder.
- `get_next_segment_id(...)` — scans `masks.json` **and** `osm_generated_annotations.json`, returns `max(max_id+1, 1000)`. Deliberately checks the road script's output too, to avoid ID collision — a genuine improvement over the road script, and correctly documented as such.
- `main()` — 8-connectivity `ndimage.label` on the union mask, drops components `< MIN_COMPONENT_AREA` (15 px), and emits one annotation per surviving component with `human_label="standing_water"`, `annotation_source="osm_water_vector"`.

**`check_generated_water_mask.py`** — renders a semi-transparent cyan overlay of the mask on the tile, warns on shape mismatch or empty mask, writes `water_mask_overlay.png`.

---

### Findings

**[Critical] W1 — Only 48.7% of OSM-generated `standing_water` pixels are spectrally water; in several cities the mask is no better than chance. [E]**
- What happens: NDWI = (Green − NIR)/(Green + NIR) computed from each city's 6-band tile, evaluated inside the generated mask versus the tile baseline:

  | city | mask px | NDWI mean | % mask NDWI>0 | % **tile** NDWI>0 | verdict |
  |---|---:|---:|---:|---:|---|
  | guatemala | 515 | −0.457 | **0.6%** | 3.5% | **worse than baseline** |
  | kigali | 191 | −0.529 | 3.1% | 0.5% | negligible |
  | dharavi | 3,108 | −0.295 | 4.5% | 2.4% | negligible |
  | nairobi | 1,383 | −0.414 | 10.1% | 0.6% | weak |
  | capetown | 901 | −0.518 | 10.8% | 4.4% | weak |
  | hcmc | 383 | −0.105 | 26.1% | 0.6% | weak |
  | nusantara | 4,070 | −0.052 | 34.9% | 2.1% | moderate |
  | accra | 1,392 | −0.052 | 36.7% | 5.9% | moderate |
  | lagos | 1,476 | −0.055 | 44.5% | 46.9% | **at baseline** |
  | dhaka | 8,583 | −0.040 | 53.0% | 4.4% | good |
  | jakarta | 11,931 | +0.193 | 74.7% | 67.2% | good |
  | **POOLED** | **33,933** | — | **48.7%** | — | — |

  For contrast, **human-annotated `standing_water` is 98.6% water-like** (197,637/200,428 px).
- Root cause: two compounding errors. (a) *Semantic* — `waterway=*` tags a **drainage channel**, not necessarily water in it. A storm drain, ditch or seasonal stream in a dry city is mapped in OSM and is dry on the imagery date. The script queries `way["waterway"]` with **no filtering whatsoever** and labels every result `standing_water`. (b) *Geometric* — see W2.
- Downstream propagation risk: roughly half of one training class's machine-generated supervision is wrong, and wrong in a spatially structured way (dry channels through dense urban fabric). This is the same failure family as C29 for `paved_road`, and it is a plausible contributor to `standing_water` behaving oddly at inference — Phase 1 measured it as the class most affected by the waterway proximity penalty (unknown count 564 → 1,111, **+97%**).

**[Critical] W2 — Every waterway class except `river` and `tidal_channel` is sub-pixel at 10 m GSD. [E/S]**
- What happens: `WATERWAY_WIDTH_M` buffers each centreline by a real-world width, correctly in local UTM. At Sentinel-2's 10 m GSD:

  | tag | width | pixels |
  |---|---:|---:|
  | river | 15 m | 1.50 |
  | tidal_channel | 10 m | 1.00 |
  | canal | 8 m | **0.80** |
  | stream | 3 m | **0.30** |
  | **DEFAULT** (untagged) | 3 m | **0.30** |
  | drain | 2 m | **0.20** |
  | ditch | 1.5 m | **0.15** |

- Root cause: identical in kind to C29 for roads — the feature is narrower than the sensor's resolving element, so every labelled pixel is a mixture dominated by whatever surrounds the channel. `DEFAULT_WIDTH_M = 3` also means any untagged or unusual `waterway` value silently gets a 0.30 px buffer.
- Downstream propagation risk: Pass-1 line pixels are the least reliable part of the mask. The per-pass NDWI split confirms it unevenly — Dhaka's lines are **0.0%** water-like while its polygons are 53.7%; Cape Town's lines 0.0% vs polygons 16.1%. In Lagos the relationship inverts (lines 45.5%, polygons 2.4%), so the failure is not consistently attributable to one pass.

**[Moderate] W3 — Pass 2 matches any `water=*` tag, including features that are not standing water. [S]**
- What happens: the query is `way["water"]` with no value restriction, unioned with `way["natural"="water"]`. Observed tag breakdown across cities includes `basin` (Dharavi 2, Dhaka 1), `reservoir` (Dharavi 1, Jakarta 2, Nusantara 19, Cape Town 1), `pond`, `lake`, `canal`, `river`.
- Root cause: `water=basin` commonly denotes a detention/retention basin that is dry except during storms; `water=reservoir` can include covered or industrial tanks. Neither is reliably standing water on an arbitrary acquisition date. The query captures tag *presence*, not semantics.
- Downstream propagation risk: contributes to W1's false-positive rate, concentrated in the dry cities where the NDWI agreement is worst (Dharavi has 30 `pond` + 2 `basin` + 1 `reservoir` polygons and only 2.0% polygon-pixel water agreement).

**[Moderate] W4 — The verification step is purely visual, was run, and passed a mask that is 48.7% non-water. [E]**
- What happens: `check_generated_water_mask.py` renders a cyan overlay and writes `water_mask_overlay.png`. It computes **no metric** and has **no pass/fail gate** — it warns only on shape mismatch or an entirely empty mask. Confirmed on disk: overlay PNGs exist for **10 of 11 cities**, so the step was executed as the generator's closing instruction demands ("NEXT STEP — do not skip").
- Root cause: the check is qualitative by design, and the features it renders are sub-pixel ribbons (W2) that are genuinely hard to adjudicate by eye at tile scale. A one-line NDWI agreement statistic would have surfaced W1 immediately; the tooling to compute it did not exist.
- Downstream propagation risk: this is the safety net for the water pipeline and it cannot detect the pipeline's main defect — structurally the same pattern as C30 for `verify_masks.py`.

**[Moderate] W5 — Rasterization uses the full-raster transform with a tile-sized output shape, which is correct only for `tile_0_0`. [S]**
- What happens: `tile_transform = raw_transform` then `rasterize(..., out_shape=(tile_h, tile_w), transform=tile_transform)`. Because tile 0,0 originates at the raster origin, the affine is correct **only** for that tile; any other tile would need an offset transform.
- Root cause: the script hardcodes `tiles/tile_0_0.png` throughout and never contemplates other tiles. It is internally consistent — the docstring says it "clips to tile_0_0.png's actual pixel extent" — but the invariant is undocumented at the rasterize call and would silently misplace the mask if the file were ever generalised.
- Downstream propagation risk: none today; latent. Note Phase 1 confirmed multi-tile AOIs are real (the 4-tile run), so this assumption is not universally safe.

**[Moderate] W6 — A `pyproj.Transformer` is constructed inside the per-polygon loop. [S]**
- What happens: `to_raw_direct = pyproj.Transformer.from_crs(...)` at lines 259-261 is rebuilt for **every** polygon, inside the loop, despite `to_utm`/`to_raw_crs` being hoisted correctly outside it.
- Root cause: Pass 2 was added later and did not reuse the existing hoisting pattern. Transformer construction is comparatively expensive.
- Downstream propagation risk: performance only; correctness unaffected.

**[Minor] W7 — `time.sleep(wait)` executes after the final retry. [S]** `query_overpass` sleeps up to 60 s after attempt 4 before raising, adding pure latency to a failure that is already terminal.

**[Minor] W8 — `natural=wetland` / `landuse=basin` are not captured, undocumented. [S]** Marsh and wetland are arguably out of scope for "standing water", but the exclusion is nowhere stated, and the docstring's framing ("actual mapped water body extents") does not signal it.

**[Minor] W9 — `MIN_COMPONENT_AREA = 15` px is inherited from the road script without water-specific justification. [S]** At 10 m GSD that is 1,500 m². Given W2's sub-pixel widths, most genuine drain/ditch traces cannot survive it, so the filter preferentially retains the polygon-derived components.

---

### Explicit negative results — things that check out

- **The multipolygon caveat did not bite. [E]** `num_skipped_unclosed_or_invalid` is **0 for all 11 cities** — no water way was dropped as an unclosed ring. The docstring's honest warning about relation-based water bodies is real in principle but had no effect on this dataset.
- **The docstring's motivating claim is exactly accurate. [E]** It states Pass-1-only produced "just 148 pixels" for Dhaka. `meta.json` records `pass1_waterway_lines.pixels = 148` and `pass2_water_polygons.pixels = 8483`. The stated problem, the fix, and the recorded outcome all agree — unusually good documentation discipline for this codebase.
- **Per-pass provenance is genuinely preserved. [E]** Separate `water_mask_pass1_lines.npy` and `water_mask_pass2_polygons.npy` are written alongside the union, and `meta.json` reports each pass's pixel count and overlap. This made W1's per-pass diagnosis possible and is exactly the provenance standard the project claims to hold.
- **Closed-ring validation is correct and conservative. [S]** Pass 2 refuses to auto-close unclosed rings, with a comment explaining that a wrongly-closed ring would produce a silently wrong polygon. Correct call.
- **Segment-ID collision avoidance is correct. [S]** `get_next_segment_id` checks both `masks.json` and the road script's output, with a floor of 1000 — genuinely better than the road script it was derived from, and correctly documented as a deliberate improvement.
- **UTM zone selection verified. [S/E]** Correct for Jakarta (zone 48, southern hemisphere → EPSG:32748).
- **Polygon pixels dominate, as intended. [E]** Pass 2 contributes **79.8%** of all OSM water pixels (28,470 of 35,661 before union overlap), confirming the extension achieved its stated purpose.

---

### Consequences for the earlier findings

- **Open Question #5 is resolved.** `standing_water`'s pixel dominance is *not* a generator artifact. It is an AOI-composition effect concentrated in Jakarta, and the underlying human labels are 98.6% spectrally correct.
- **A different, unflagged problem was found instead:** the OSM water generator's *label accuracy* is poor (48.7%), which no prior finding covered.
- **R2's class-weight analysis gains context.** `standing_water`'s inflated CE weight (0.4915 patch-derived vs 0.0868 pixel-derived, a 5.7× distortion) is driven by human mega-segments, not by the generator. The weighting statistic mismatch is real; its cause is AOI selection.
- **C29's mechanism generalises.** The sub-pixel labelling pathology now has two confirmed instances — roads (C29) and waterway lines (W2) — driven by the same 10 m GSD limit against sub-10 m linear features. This strengthens the argument that it is a systemic property of the sensor/taxonomy pairing rather than a defect specific to the road generator.

---

## Addendum — 2026-08-22: findings surfaced while fixing C16

Recorded during the C16 remediation pass (whitelist validation of `aoi_label`
at the API boundary). **Both are NEW findings, not part of C16**, and neither is
addressed by the C16 fix. They are logged here so the C16 fix's limits are not
mistaken for full coverage of this bug class in `api.py`.

For reference, what C16's fix *does* cover: `validate_aoi_label()` in `api.py`
rejects any label outside `[a-z0-9_-]{1,64}` with HTTP 400, called at the top of
both `/api/analyze` and `/api/analyze_inundation` — the two request-body sinks
that reach `run_pipeline()` / `run_inundation_analysis()`. Regression tests in
`tests/test_api_aoi_label_validation.py` (72 tests; 70 fail against the
unpatched file, 72 pass against the patched one).

**[NEW] C34 — `GET /api/runs/{run_id}` builds a filesystem path from an
unvalidated path parameter. [S]**
`api.py:256` — `get_run()` does
`Path(f"data/pipeline_runs/{run_id}/result.json")` with `run_id` taken straight
from the URL. Same bug class as C16 (unvalidated caller input becomes a path
component), **different sink**: a read on a GET route, not a directory creation
on a POST route, and it does not pass through `aoi_label` at all. The C16 fix
does not touch it.

**Untested — severity not established.** Starlette normalises some traversal
sequences in the URL path before routing, so the naive `../` payload may not
reach the handler; percent-encoded, mixed-separator, and absolute-path variants
were not attempted, and no read outside the data root was demonstrated. This is
flagged from source inspection only. It needs the same execution treatment C16
received before any severity is assigned. Note the endpoint reads and returns
file contents, so if it is reachable the impact is disclosure rather than
directory creation.

**[NEW] C35 — `WATCHED_AOIS` labels bypass the API boundary entirely. [E]**
`refresh_all_watched_aois()` (`api.py:96`) is invoked by the APScheduler job,
not by an HTTP request, and calls `run_pipeline(aoi_label=aoi["label"])`
directly — confirmed by execution that no validation sits on that path. C16's
fix is deliberately scoped to the API boundary, so scheduler-originated labels
are unvalidated by construction.

**No current exposure.** All three configured labels — `dharavi`, `nairobi`,
`jakarta` — were run through `validate_aoi_label()` and pass the whitelist, so
nothing breaks today and no traversal is currently possible via this path. The
finding is that `WATCHED_AOIS` is a hardcoded module-level constant with no
enforced constraint: a future edit adding a malformed label would reach path
construction with nothing to stop it, and would do so under the scheduler's
own privileges rather than a request's.

**Relationship to C16.** C16 is fixed and closed. C34 and C35 are the two
places `api.py` still constructs paths from input that the C16 fix does not see
— one a different sink on the same class of bug, one a different entry point
that bypasses the boundary where the fix lives. Neither was in the C16 fix's
declared scope (`api.py` + its test file, no downstream changes), and neither
was modified.
