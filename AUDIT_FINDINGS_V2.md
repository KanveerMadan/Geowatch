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
| Unknown-pixel rate | "~50%" | **25.74%** / **28.79%** | ❌ stale by ~2× — now **explained** |
| `paved_road` supervision share | 41.0% | **73.38% by patch, 17.81% by pixel** (both measured on the 1,345-patch pool) | ⚠️ V1's 41% is not a pool measurement — see note |

*On the `paved_road` row:* V1's **41.0%** and the pool figures are **not
commensurable and must not be read as a like-for-like correction.** 41% is
*inferred* by inverting the trained checkpoint's `class_weights`
(`models/production/geowatch_production_model.pth`; normalised 1/w gives
**40.96%**) — it is a property of the model that was trained, not a count of
anything on disk. **73.38%** and **17.81%** are both *measured* from the same
1,345-patch / 484,796-pixel pool. The by-patch figure for that pool is
**73.38%, not 41%**: `paved_road`'s patch dominance is roughly **1.8× larger**
than the V1 number suggests, not smaller. An earlier version of this row read
"41% by patch, 17.8% by pixel", which juxtaposed a checkpoint-inferred value
and a pool-measured value under one "by patch / by pixel" heading and so
understated patch dominance by nearly 2× while appearing to correct it.
Corrected 2026-08-22 after manual re-derivation. **[E]**

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
pixel-derived (0.2394) values. Both are patch statistics, and the notebook's
25/city cap on OSM sources moves the number in the right direction — but it
does **not** account for the gap quantitatively. Direct reconstruction of that
cap (all human annotations + the first 25 OSM road and 25 OSM water records per
city) yields a 637-patch pool at **44.74%** `paved_road`, against the
checkpoint-implied **40.96%**. Nor does either pool reconcile with the
checkpoint's own record of what it trained on: `n_train_patches = 1272` and
`n_monitor_patches = 141` (1,413 total) match neither the capped 637 nor the
uncapped 1,345. **The real training pool is therefore not reconstructible from
the files on disk**, and every patch/pixel figure derived here is a proxy for
training supervision rather than a reconstruction of it. The direction of the
patch-vs-pixel mismatch is unaffected; only the claim that the cap *explains*
the gap is withdrawn. **[E]**

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
segments have a bbox that disagrees with the `masks.json` entry of the same id
— ids **25–35**, contiguous. The offset is **not** constant: it **accumulates**,
ids 25–28 at **+1**, ids 29–31 at **+2**, ids 32–35 at **+3**. Every disagreeing
segment still matches *some* mask, so nothing is lost; the drift grows as
filtered-out masks accumulate. Magnitude is run-dependent
(67% on an earlier run). Root cause: `result.json` ids come from a counter over
*surviving* segments (post `w<8/h<8` filter) while `masks.json` ids come from a
counter over *all* masks. *Critical. Currently harmless for existing training
data — the eleven training runs predate Phase 2 — and irreversible the moment a
new annotation round runs (see C28).*

*Corrected 2026-08-22 after manual re-derivation:* this entry previously read
"a clean one-position shift from id 25 onward", which holds only for ids 25–28
and is false for 29–35. **The correction strengthens the finding rather than
weakening it:** a cumulative offset is precisely what two divergent counters
produce — each mask dropped by the `w<8/h<8` filter adds one to the drift —
whereas a constant shift would suggest a single one-off skip and point at a
different mechanism. It also matters operationally: **any repair keyed to a
constant +1 would fix ids 25–28 and silently corrupt ids 29–35.** The 11/36 =
30.6% figure, the contiguous 25-onward range and the root cause at
`pipeline.py:332-361` are all unchanged and were re-confirmed. **[E]**

**[CONFIRMED] C10 — Deployed CAAT thresholds have no provenance and are not checked. [E]**
Live run logged `Loaded CAAT thresholds (source_checkpoint=?, verified_sanity_check_miou=?)`.
The file's own caveat states it derives from 11 LOCO fold models, **not** the
production checkpoint. The stricter check exists in `resnet_classifier.py`
(dead code) and would reject this file. *Critical.*

**[CONFIRMED] C11 — Penalties applied post-calibration. [E]** Neither
diagnostic nor the notebook that produced the deployed CAAT applies the
proximity penalties (verified: zero references), while `run_inference` does.
Measured effect: unknown 24.45% → 25.74% (**+1.29 pp**); `standing_water`
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
Emitted `impervious_fraction_pct = 41.68` (reproduced exactly:
`25.97×1.0 + 9.58×0.9 + 11.81×0.6 = 41.6780`); recounted against a known-pixel
denominator (55,535 of 74,787 px, straight from `landcover_map_full.npy`) =
**56.13**. Understatement factor **1.347×** at 25.74% unknown. Direction is the
dangerous one: higher unknown → lower apparent imperviousness → settlement
reads as *less* flood-prone. *Critical. See CORRECTED note on magnitude.*

*Corrected 2026-08-22 after manual re-derivation:* this entry previously read
**56.12** and described the factor as **exactly** `1/(1−0.2574)`. Neither
survives a genuine recount. 56.12 is reproducible only by *rescaling* the
emitted value (`41.678 / (1 − 0.2574) = 56.1244`), not by recounting pixels; a
true known-pixel recount gives **56.1273 → 56.13**. And because 56.12 was
produced *by dividing by* `1−0.2574`, the stated identity was **true by
construction, not an independent confirmation of the mechanism** — it read as
corroborating evidence and was not. On a real recount the ratio is
**1.346689** against `1/(1−0.2574) = 1.346620`: agreeing to four significant
figures, not identically. **The mechanism, the direction, the severity and the
1.347× figure (both values round to it) all stand unchanged.** **[E]**

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
(R3). Real rate 25.74%/28.79%. **Every V1 argument conditioned on ~50% is
overstated by roughly a factor of two** — notably C19's severity framing and
parts of the C14 narrative. Directions unchanged; magnitudes not.

**[CORRECTED] The "41% `paved_road`" figure. [E]** A **patch** statistic. At
pixel level `paved_road` is **17.8%** and `standing_water` dominates at
**49.1%**. Ratio to `dense_informal_roofing`: **18.62× by patch, 2.00× by
pixel**. Raw pool is 73.4% paved_road by patch. The checkpoint's implied 41%
(40.96%, from inverting its `class_weights`) is lower, and the notebook's
25/city OSM cap is the reason it moves in that direction — but the cap does not
reproduce the number: reconstructing it directly gives 44.74%. See the withdrawn
"cap explains the gap" note under R2.

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

---

## Addendum 2 — 2026-08-22: population data-year investigation

Triggered by a challenge to the "WorldPop caps at 2020" framing. Investigation
only; **no code was changed**. All GEE queries below are read-only.

### Corrected

**[CORRECTED] "Population caps at 2020" is a property of the GEE mirror this
project chose, not a limitation of WorldPop. [E]**

The *observation* is correct and reconfirmed live. The *diagnosis* is wrong.

Confirmed by execution against `WorldPop/GP/100m/pop`:

| Query | Result |
|---|---|
| Collection size | 5,221 images |
| Distinct `year` (global) | 2000–2020, contiguous |
| `country=IND` images / years | 21 / 2000–2020 |
| Dharavi AOI + `IND`, `aggregate_max("year")` | **2020** |

So that asset genuinely stops at 2020. What does not follow is the conclusion
the code draws from it — that "no fresher WorldPop release exists." WorldPop's
current release is R2025A (September 2025), covering 2015–2030 including
projections. *This release fact is reported by the project owner and was not
independently verified here;* what was verified is that it is **not reachable
through the asset this project uses**. Probing `WorldPop/GP/100m/pop/R2025A`
and `WorldPop/R2025A/POP` returned `asset not found` for both. **[E]** (Two
plausible paths, not an exhaustive catalog search — absence of a mirrored
R2025A asset in GEE is likely but not proven by these two probes alone.)

**Consequence for how this is recorded:** the cap belongs in the "ingestion
channel we selected" category, alongside decisions like MERIT Hydro's bbox-only
API, not in the "external data does not exist" category, alongside genuine
gaps. Reaching R2025A would require a **non-GEE ingestion path** (direct
WorldPop download or their API) — real work, not a constant edit. That is a
materially different backlog item from "nothing can be done," which is what the
current wording implies.

**Neither audit challenged this.** V2 mentions population twice (the 282,983
Dharavi figure at line 256; "Population is `None`, never a fabricated 0" at
line 499) and never interrogates the cap's cause. The framing was inherited
from the code's own docstrings and comments and accepted at face value. Logged
here so the inheritance is visible.

**[CONFIRMED-GOOD, worth recording] The WorldPop *selection logic* has no
hardcoded year at all. [S]**
`ingestion/exposure_sources.py:89-92` resolves the epoch dynamically —
`aggregate_max("year")` then `Filter.eq("year", latest_year)`. No `filterDate`,
no literal year, no cap anywhere in the population path; the call site
(`pipeline.py:470`) likewise resolves ISO3 dynamically rather than pinning
`"IND"`. If a fresher epoch ever appeared in that collection, the code would
select it automatically and report it correctly in `population_year`. This is
the opposite of the defect one would expect from the docstring, and it is why
C37 below matters.

### New findings

**[NEW] C36 — `GHSL_BUILTUP_ASSET` hardcodes the epoch inside the asset string,
while 2025 and 2030 sit in the same collection. [E]**
`configs/exposure_constants.py:58` —
`GHSL_BUILTUP_ASSET = "JRC/GHSL/P2023A/GHS_BUILT_S/2020"`. Consumed at
`ingestion/exposure_sources.py:159` as `ee.Image(GHSL_BUILTUP_ASSET)`: a single
image load, with no collection query, no `aggregate_max`, and no dynamic
selection of any kind. Unlike the WorldPop path, this **cannot** pick up a
newer epoch without editing the constant.

Verified live: the parent collection `JRC/GHSL/P2023A/GHS_BUILT_S` holds **12
epochs — 1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025,
2030**. `.../GHS_BUILT_S/2025` and `.../GHS_BUILT_S/2030` both load and both
return **identical bands** to the pinned 2020 image:
`['built_surface', 'built_surface_nres']`. So the newer epochs are drop-in
compatible at the band level — the only thing preventing their use is the
literal `2020` in the string. *Severity: low in isolation (built-up is a
cross-check, not a primary), but it is the only true hardcoded year in the
exposure path and it is invisible as a year because it is spelled as part of an
asset ID.*

**[NEW] C37 — `exposure_sources.py`'s `limitations` list is constructed before
the GEE query, so a fresher epoch would emit a self-contradicting record. [S]**
`ingestion/exposure_sources.py:53-62` builds the `limitations` list — including
the literal string *"Population data caps at year 2020 -- no fresher WorldPop
release exists as of this verification"* — at line 53. The GEE query that
actually determines the epoch does not run until line 63, and the resolved
`population_year` is not read until line 89. The caveat is therefore a
**hardcoded assertion, not a derived statement**, and it is returned verbatim on
every success path regardless of which year was selected.

If the collection were ever updated, a single returned dict would carry
`population_year: 2025` alongside `"Population data caps at year 2020"`, and
`exposure/compute.py:177` would propagate both into `result.json` — the year via
`population_source.population_year`, the contradicting text via
`result["limitations"]`. The same stale claim appears in the function docstring
(`:46`), the constants comment (`configs/exposure_constants.py:18`), and
`exposure/compute.py:41`.

*Not currently observable* — the collection has not moved, so no run has yet
produced the contradiction; the finding is the construction order, which is
static and certain. **[S]** The consequence is **[R]**, contingent on an
upstream update this project does not control.

This inverts the project's rule 4.7 (*degradation is always visible, never
silent*): the failure mode is not a hidden caveat on degraded data, but a stale
caveat welded onto fresh data — understating currency rather than overstating
it. Both mislead; this direction is merely the less dangerous one.

**[NEW] C38 — `GHSL_BUILTUP_ASSET`'s `UNVERIFIED` label is stale. [E]**
The asset is labelled unverified in three places — `configs/exposure_constants.py:55-58`,
the `get_builtup_reference()` docstring (`ingestion/exposure_sources.py:132-138`),
and a per-run stdout line (`pipeline.py:704`, *"GHSL built-up reference:
status=available (UNVERIFIED asset ID)"*) — and the warning is also injected
into that component's user-facing `limitations` list
(`exposure_sources.py:145-148`), so it reaches `result.json` on every run.

`JRC/GHSL/P2023A/GHS_BUILT_S/2020` resolves live and returns bands
`['built_surface', 'built_surface_nres']`. Existence, band names and load
behaviour are confirmed. *What remains genuinely unverified is narrower than
the label implies:* no pixel-level agreement comparison against GeoWatch's own
built-up estimate has been done (`exposure/compute.py:198` still carries
`agreement_status: "not_yet_compared"`), and licence/resolution were not
re-checked here. The label should be narrowed to what is actually outstanding
rather than left as a blanket "unverified," which currently costs the reader
trust in a component that does load correctly. *Minor.*

### Context for a decision not yet made — GHS-POP

Recorded as evidence, **not** as a recommendation. Switching population source
is a methodology decision of the same class as Gate E, and it has not been made.

`JRC/GHSL/P2023A/GHS_POP` is already present in GEE — same P2023A family the
project already depends on for built-up — with **12 epochs, 1975 through 2030**
(1975, 1980, 1985, 1990, 1995, 2000, 2005, 2010, 2015, 2020, 2025, 2030). It is
not used as a population source anywhere in the codebase. **[E]**

Zonal sums over the canonical Dharavi AOI, computed with the image's own
`crs`/`crsTransform` (the same method `exposure/compute.py:151-158` uses, not a
`scale=` argument — see the scale bug documented at
`configs/exposure_constants.py:26-45`): **[E]**

| Source | Estimated population | Note |
|---|---|---|
| GHS_POP 2015 | 248,492 | observation-based |
| GHS_POP 2020 | 261,569 | observation-based |
| GHS_POP 2025 | 279,331 | **projection** |
| GHS_POP 2030 | 309,591 | **projection** |
| WorldPop 2020 | 282,983 | current source |

The WorldPop figure reproduces `282,983.025` as recorded at
`configs/exposure_constants.py:35` exactly, confirming the query method matches
the code's rather than measuring something else.

Three things any such decision must confront, none of them resolved here:

1. **GHS_POP 2025 and 2030 are projections, not observations.** Adopting them
   changes the epistemic status of the exposure number. On a track that returns
   `not_calculated` rather than fabricate a fusion formula, silently swapping a
   modelled-observation for a modelled-projection would be inconsistent, unless
   labelled at least as explicitly as `contextual_screening` is under rule 4.6.
2. **GHS_POP and WorldPop disagree by ~7.6% at the same epoch** over the same
   AOI (261,569 vs 282,983 at 2020). They are different models, so this is not a
   like-for-like substitution and would break comparability with every existing
   Phase 10A/12A output.
3. **Neither addresses the actual freshness gap.** GHS_POP's newest
   *observation* epoch is 2020 — the same year WorldPop stops. Moving to
   GHS_POP buys projections, not newer measurements. Only a non-GEE WorldPop
   R2025A path would buy genuinely fresher observed data, and even R2025A's
   post-2020 years are themselves projections.

**Net:** the "2020 cap" is real, but it is a cap on *observed* global gridded
population in the GEE catalogue generally — not a WorldPop-specific dead end,
and not something a constant edit fixes. C36 and C37 are cheap and worth doing
independently of any source decision; the source decision itself is not a
coding task.

---

## Verified Dead Ends

Questions that have been investigated and **closed**. Each entry records what
was checked, how, and what the limits of the check were — so the same
investigation is not repeated. A dead end is not a defect; it is a path that
was examined and found not to exist. Reopen an entry only if new evidence
contradicts the "how verified" column, not on a hunch that the answer might
have changed.

### DE1 — Google Open Buildings does not publish a public ROAD layer. **[E/S]**

**Closed 2026-08-22. Answer: no such layer exists.** Investigation only; no
code was written or changed.

**Why it was asked.** Sirko et al., *High-Resolution Building and Road
Detection from Sentinel-2* (arXiv:2310.11622) demonstrates road detection from
Sentinel-2 via a high-resolution teacher — the same method behind Open
Buildings. Since the project's `paved_road` class is its weakest (over-predicted
~2.4x, the top-2 confusion partner for all six other classes — see R1 and §5.4
of the flood-track brief), an authoritative external road vector would be
valuable. The question was whether roads ever shipped the way footprints did.

**The paper itself says they did not. [S]** §7: *"Our evaluations focus on the
building detection task and **we do not report metrics for the road detection
and image super-resolution tasks.**"* On release it states only that
***buildings*** data is publicly available. No road download URL appears
anywhere in the paper.

**Earth Engine namespace enumeration. [E]** Run live via
`ee.data.listAssets` rather than by guessing asset names:

```
GOOGLE/Research/open-buildings/v1  -> polygons, polygons_FeatureView
GOOGLE/Research/open-buildings/v2  -> polygons, polygons_FeatureView
GOOGLE/Research/open-buildings/v3  -> polygons, polygons_FeatureView
```

Three folders, building tables only. Feature properties on `v3/polygons` are
`['area_in_meters', 'confidence', 'full_plus_code', 'longitude_latitude']` —
no road field. Open Buildings Temporal v1 bands, read live off
`bd_EPSG_32720_2023_06_30`, are exactly
`['building_fractional_count', 'building_height', 'building_presence']` —
three bands, all buildings. The paper's road head is absent from the released
product. Seven plausible road asset IDs were also probed
(`.../v3/roads`, `.../v3/road_polygons`, `GOOGLE/Research/open-roads/v1`,
`open-roads/v1/polylines`, `open_roads/v1`, `open-buildings-roads/v1`,
`GOOGLE/Research/roads/v1`) — all returned `not found`. **[E]**

**Distribution mirrors carry buildings only. [S]**
`source.coop/cholmes/google-open-buildings` holds 1.8 billion building
detections as PMTiles / GeoParquet (S2 and by-country) / FlatGeobuf / STAC,
with per-feature attributes footprint, confidence, Plus Code, country ISO,
quadkey, area. No linear features. Adjacent repos
(`cholmes/google-buildings-tools`, `opengeos/open-buildings`) are
format-conversion tooling over the same building data.
`sites.research.google/gr/open-buildings` does not mention roads at all; its
downloads are building polygons (178 GB), building points (48 GB), score
thresholds, and tile metadata. On both that page and the temporal sub-page the
**only** occurrence of the word "road" is inside the citation of the Sirko
paper's title.

**Honest limit on the search. [R]** Earth Engine's API has no server-side
wildcard search. The check is therefore **exhaustive within the
`open-buildings` namespace** (via `listAssets`, which enumerates rather than
guesses) but **name-probing only outside it**. A Google road asset under some
unrelated catalog path cannot be fully excluded by this method. Nothing in
Google's own documentation, the paper, or the distribution mirrors points to
one, so the residual probability is low — but it is not zero, and this is the
one line of the entry that would justify reopening it.

**Net:** the method is real and Google ran it at continental scale; they
released one head of a multi-head model. The project's `paved_road` weakness
gets no help from this source.

### What IS available from Open Buildings — relevant to the vector-layer plan

Recorded alongside DE1 because the negative answer above is likely to prompt
"what about the buildings, then?", and the licence/coverage facts are the ones
that decision needs.

| Property | Value | Confidence |
|---|---|---|
| Licence | Dual: **CC-BY-4.0 OR ODbL v1.0** (user's choice) | [S] |
| Inference area | 58M km², Africa / South Asia / Southeast Asia / Latin America & Caribbean, 140+ countries | [S] |
| Footprints (v3) | 1.8 billion building detections; attributes: polygon, confidence, Plus Code, area_in_meters | [E] |
| Temporal v1 | 4 m effective resolution (0.5 m rasters), annual **2016–2023**, 3 building bands | [S/E] |

**All ten target countries verified live, not inferred from stated regions.**
Building counts returned by `GOOGLE/Research/open-buildings/v3/polygons` within
a ~1 km box over one urban point per country: **[E]**

| Country (point) | Buildings | Country (point) | Buildings |
|---|---|---|---|
| India (Mumbai) | 1,234 | Indonesia (Jakarta) | 3,047 |
| Kenya (Nairobi) | 913 | Rwanda (Kigali) | 3,042 |
| Nigeria (Lagos) | 2,726 | South Africa (Cape Town) | 1,384 |
| Ghana (Accra) | 1,606 | Vietnam (Ho Chi Minh City) | 2,269 |
| Bangladesh (Dhaka) | 2,575 | Guatemala (Guatemala City) | 3,642 |

Ten of ten covered with non-trivial counts. *The dual licence is worth noting
against this project's OSM dependency: ODbL matches OSM's licence, so the two
can be combined under one regime, while CC-BY-4.0 is the more permissive option
if OSM-derived data is not mixed in. That choice is a licensing decision, not a
technical one, and has not been made.*

**Not investigated here:** whether Open Buildings footprints would actually
improve the `dense_informal_roofing` / `sparse_informal_roofing` /
`paved_road` confusion, or how they would be reconciled with the existing
7-class taxonomy. Those are separate questions and remain open.

---

## Addendum 3 — 2026-08-22: manual re-verification of two headline figures

Both figures were re-derived first-hand from the run outputs, annotation files
and checkpoint on disk, because both had previously been wrong by roughly 2×.
Read-only; no code changed. Three corrections were applied in place above
(executive-summary unknown rate, executive-summary `paved_road` row, and the
class-weight cap note); this section records what was checked and one new
finding.

### What reproduced exactly

**Unknown-pixel rate. [E]** From `<run>/landcover_map_full.npy` (uint8) with
the pipeline's own denominator (`ingestion/inference.py:308-312`,
`total_px = H*W`, `UNKNOWN_INDEX = 255`):

| Run | Array | total_px | == 255 | Computation | Result |
|---|---|---:|---:|---|---:|
| `phase1_dharavi_20260820_125646` | 257×291 | 74,787 | 19,252 | 100 × 19,252 / 74,787 = 25.742442 | **25.74** |
| `phase1_dharavi_20260820_125809` | 257×291 | 74,787 | 19,252 | identical | **25.74** |
| `phase1_multitile_20260820_130117` | 891×892 | 794,772 | 228,785 | 100 × 228,785 / 794,772 = 28.786243 | **28.79** |

All three agree with the `landcover.unknown_pct` recorded in each
`result.json`. The two Dharavi runs are bit-identical down to the class
histogram, independently reconfirming the determinism claim.

**Correction applied: 25.73% → 25.74%.** There were **three** occurrences, not
two — the executive-summary table, C11's "24.45% → 25.74%", and the
`[CORRECTED] The "~50% unknown" figure` entry. `100 × 19,252 / 74,787` rounds
to 25.74 and no arithmetic on this array yields 25.73. Magnitude 0.01 pp; the
"stale by ~2×" conclusion is unaffected. The rounded range "25.7%–28.8%" in R3
was already correct and was left alone.

**Supervision-share table. [E]** All seven rows reproduce exactly, patch counts
and pixel sums alike — including `paved_road` 987 / 86,349 and
`standing_water` 133 / 238,265. Pool: `annotations.json` +
`osm_generated_annotations.json` + `osm_generated_annotations_water.json`
across the 11 training runs selected by `find_annotated_run_dir`'s rule
(newest dir per city carrying `tiles/tile_0_0.png` + `annotations.json` +
`masks.json`). Patches = record count per `human_label`; pixels = sum of each
record's `area` field. Restricted to the checkpoint's 7 `categories` —
`unpaved_dirt_road`, `open_drainage_channel`, `open_waste` and `unknown` are
outside the model taxonomy and excluded. Denominators **1,345 patches /
484,796 pixels**. Source split: human 331, OSM road 976, OSM water 101.

**Class-weight table. [E]** All 21 values — checkpoint, patch-derived,
pixel-derived — reproduce to four decimal places under
`w_i = K × (1/freq_i) / Σ(1/freq_j)`, against
`models/production/geowatch_production_model.pth`, whose `class_weights` tensor
confirms `paved_road = 0.1707` and `standing_water = 0.4915`.

### New finding

**[NEW] C39 — Two annotations in the training pool hold free text as
`human_label`. [E]**
In `data/pipeline_runs/accra_20260702_163854/annotations.json`:

| segment_id | area | `human_label` |
|---|---:|---|
| 18 | 123 | `data/annotation_queues/_current_candidate_preview.png` |
| 26 | 64 | `python annotate_queue.py capetown` |

A file path and a shell command were typed at `annotate_queue.py`'s label
prompt and stored verbatim. The tool's contract is
`<text> -> type any other real category name to label it as that instead`, with
**no validation against `CATEGORIES`** — any string the operator types becomes
a label. Both values are almost certainly mis-paste/mis-typed shell input
during an annotation session, not deliberate labels.

**Impact is currently nil**, and stated as such rather than inflated: both fall
outside the 7 model classes, so they are excluded from every patch/pixel figure
in this document and from training. The defect is that nothing rejects,
reports, or repairs them — they sit in the pool indefinitely, and any consumer
that trusts `human_label` without whitelisting against `CATEGORIES` would carry
them silently. It also bounds how much the operator's typed input can be
trusted elsewhere in the same files.

*Related, not the same:* `annotate.py` and `annotate_queue.py` are both frozen
as of 2026-08-22 (see DE-adjacent freeze under C28), so no new labels of any
kind can be added until that freeze lifts. C39 concerns the two records already
on disk. *Minor.*

---

## Addendum 4 — 2026-08-22: targeted spot-check of 10 weight-bearing findings

Ten findings were re-verified by hand — chosen for carrying the most weight in
the build plan or being cited elsewhere in this document. Much of Modules 1–4
came from parallel sub-agents whose line citations had never been independently
confirmed. `[E]` findings were re-measured rather than re-read; `[S]` findings
were checked against the code. Read-only; **no code was changed.**

### Result

**8 of 10 reproduced exactly**, several to the pixel. Two carried defects, both
corrected in place above (C19, C9). Two further imprecisions are recorded below
(C31, C29).

| # | Finding | Verdict |
|---|---|---|
| 1 | C14 / C20 | CONFIRMED |
| 2 | C19 | Mechanism holds; **two numbers corrected** — see the entry |
| 3 | C21 | CONFIRMED |
| 4 | C25 / C26 | CONFIRMED |
| 5 | C31 | CONFIRMED (line-range note below) |
| 6 | C32 | CONFIRMED |
| 7 | C13 | CONFIRMED |
| 8 | C29 | CONFIRMED (table note below) |
| 9 | W1 | CONFIRMED to the pixel |
| 10 | C9 | Numbers confirmed; **shift pattern corrected** — see the entry |

Highlights of what reproduced: C14/C20 — all 8 `compute_*` functions in
`susceptibility/` and `perception/` enumerated by AST, **none takes an
applicability argument**; `pipeline.py:412` (hydrological_surfaces) precedes
`:413` (applicability). C13 — `primary_tile` measured at 512×512 against
`tile_dimensions` 892×891, **102/116 = 87.9%** exact. C31 — all 8 ΔRGB values
exact, **0/8** matches. C32 — `applicability` occurs **exactly once** in the
whole frontend, at `App.jsx:493`. W1 — all 11 city rows, pooled
**16,538/33,933 = 48.7%**, and human annotations **197,637/200,428 = 98.6%**,
all exact.

### Two line-reference imprecisions (neither is a wrong citation)

**C31 — the `unknown` row's source sits one line outside the cited range.**
V1 cites `ingestion/inference.py:165-178` for `CATEGORY_COLORS_RGB`. That span
covers the comment header (164–169) and the dict (170–178), which supplies 7 of
the table's 8 rows. The 8th row, `unknown (96, 96, 128)`, comes from
`UNKNOWN_COLOR_RGB` at **`inference.py:179`** — just outside. The value and the
Δ are correct; only the citation is one line short of covering the whole claim.
**[S]**

**C29 — the width table omits `trunk`, and the "only motorway" phrasing leans
on a strict reading.** `HIGHWAY_WIDTH_M` (`generate_osm_road_masks.py:76-82`,
inside V1's looser `:70-89` citation) also contains **`trunk: 10 m = exactly
1.00 px`**, which V1's table does not list. The claim *"Only `motorway` exceeds
one pixel"* is therefore true only because 1.00 does not strictly *exceed* 1.00.
More accurate: **`motorway` (1.20 px) is the only class wider than one pixel;
`trunk` lands exactly on one; every other class is sub-pixel.** The substantive
point — that the supervision is sub-pixel by construction — is unaffected and
arguably reinforced, since a feature exactly one pixel wide is still mixed
whenever it does not align to the pixel grid. All six listed widths, the 192
Cape Town records and the **median mask area 23.5 px** reproduced exactly.
**[S/E]**

### Methodological note — what this spot-check actually caught

Worth recording, because it bears on how the rest of Modules 1–4 should be
treated.

**The line citations held up.** Of eight distinct references resolved: **six
exact, two loose-but-containing, none pointing at the wrong construct.** The
sub-agent citation risk that motivated this check did not materialise.

**Both real defects were the same kind of error: a derived number presented as
a measured one.** C19's `56.12` was reproducible only by rescaling the emitted
value, yet was described as "recomputed with a known-pixel denominator" — and
the accompanying "exactly `1/(1−0.2574)`" was then an identity of that
derivation rather than evidence for the mechanism. C9's "clean one-position
shift" was true of the first four instances and asserted of all eleven.

**Neither would have been caught by auditing line references, and neither
changed a severity rating or a downstream argument.** Both fell out only from
re-running the measurement. The practical lesson for the remaining
un-spot-checked findings: verifying that a citation points at the right code
establishes almost nothing about whether the number attached to it was measured
or inferred. Where a figure carries weight, re-derive it; and where a derived
figure is reported, say which operation produced it, so a later reader can tell
corroboration from restatement.

---

## OSM Coverage Baseline

Groundwork for deciding how far the pipeline can rely on OSM vector geometry for
road information. Measured 2026-08-22 against live Overpass, one query per city
(`way["highway"](bbox); out geom;`), using the AOI bboxes of the same 11
training runs `find_annotated_run_dir` selects. Read-only; **no code changed.**

**Method.** Way geometries were clipped to the AOI polygon before measuring, so
lengths are *within-AOI* and density is honest. Length is geodesic
(`pyproj.Geod.line_length` on WGS84 lon/lat), not projected. AOI area is
geodesic polygon area, the same method `api.py::compute_aoi_geodesics()` uses.

**What is measured and what is inferred — the distinction matters here.**
Everything in the tables below is *measured*: way counts, clipped geodesic
lengths, densities, ratios. Everything in "Read" is *inference* from those
numbers plus the urban character of each AOI. **No completeness rate is claimed
anywhere**, because there is no reference network to measure against — no
ground-truth path inventory, no imagery-derived path extraction, nothing. "Under-
mapped" below always means *"density is low relative to peer AOIs of similar
character"*, never *"X% of paths are missing."* Establishing an actual
completeness figure needs a reference this work does not have.

### Per-city measurements

| city | AOI km² | all `highway` ways | all km | km/km² | grp-P:V | foot:V |
|---|---:|---:|---:|---:|---:|---:|
| capetown | 23.04 | 5,684 | 572.2 | 24.83 | 10.79 | 3.97 |
| dharavi | 6.97 | 1,694 | 160.4 | 23.02 | 2.01 | 0.40 |
| dhaka | 13.55 | 1,816 | 285.1 | 21.04 | 2.35 | 0.42 |
| nairobi | 14.23 | 3,096 | 300.8 | 21.14 | 4.63 | 0.62 |
| kigali | 6.79 | 608 | 96.9 | 14.27 | 3.14 | 0.58 |
| guatemala | 19.07 | 4,811 | 503.5 | 26.40 | 2.49 | 0.25 |
| accra | 12.87 | 2,587 | 269.9 | 20.98 | 3.30 | 0.28 |
| hcmc | 120.96 | 29,077 | 3,013.8 | 24.92 | 5.42 | 0.24 |
| nusantara | 40.61 | 749 | 176.5 | 4.35 | 1.99 | 0.63 |
| jakarta | 42.84 | 3,988 | 355.8 | 8.31 | 3.38 | 0.25 |
| lagos | 17.13 | 907 | 162.4 | 9.48 | 3.52 | 0.10 |

### A grouping caveat that changes the reading

The requested "pedestrian/informal" group — `footway, path, pedestrian, steps,
track, service, residential` — mixes two very different things. `service`,
`residential` and `track` are **vehicular-capable** minor roads; `footway`,
`path`, `pedestrian` and `steps` are the genuinely non-vehicular classes, and
those are the ones that stand in for alleys in dense informal fabric. Reported
both ways: **grp-P:V** uses the requested grouping, **foot:V** uses the narrow
one. The two rank cities differently — HCMC is 5.42 on the requested grouping
(second-highest) but 0.24 on the narrow one (third-lowest), because its total is
dominated by 990 km of `service` and 1,382 km of `residential`. **The narrow
measure is the one that speaks to informal-path coverage**, and the ranking
below uses it.

| city | footway km | path km | pedestrian km | steps km | **foot km** | **foot/km²** | service km | residential km |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| capetown | 87.54 | 104.70 | 0.00 | 0.18 | **192.42** | **8.35** | 25.32 | 303.32 |
| dharavi | 16.65 | 1.22 | 0.51 | 1.01 | **19.39** | **2.78** | 18.32 | 58.99 |
| dhaka | 25.56 | 1.24 | 3.68 | 0.23 | **30.71** | **2.27** | 18.48 | 123.02 |
| nairobi | 23.54 | 5.99 | 0.37 | 0.12 | **30.02** | **2.11** | 111.80 | 82.84 |
| kigali | 5.17 | 4.52 | 0.41 | 3.09 | **13.18** | **1.94** | 10.68 | 47.48 |
| guatemala | 25.58 | 1.73 | 6.19 | 1.45 | **34.95** | **1.83** | 84.47 | 225.66 |
| accra | 13.88 | 1.69 | 1.04 | 0.03 | **16.65** | **1.29** | 102.49 | 76.18 |
| hcmc | 95.46 | 8.84 | 4.32 | 0.34 | **108.96** | **0.90** | 990.76 | 1381.78 |
| nusantara | 8.90 | 14.85 | 1.65 | 0.28 | **25.68** | **0.63** | 27.62 | 27.38 |
| jakarta | 14.86 | 0.86 | 0.47 | 0.72 | **16.91** | **0.39** | 117.47 | 94.90 |
| lagos | 0.37 | 2.93 | 0.00 | 0.00 | **3.30** | **0.19** | 26.02 | 82.67 |

Arterial classes (`motorway`/`trunk`/`primary`/`secondary`/`tertiary`) total
22.8–458.9 km per AOI and are the *least* variable group — every city has a
usable arterial skeleton. Classes at or near zero: `motorway` absent in
accra/guatemala/kigali/nairobi/nusantara; `track` absent in
accra/dhaka/dharavi/guatemala; `primary` absent in nairobi/nusantara;
`pedestrian` and `steps` **both** absent in **lagos**.

### What the AOIs actually contain — this reframes the ranking

Queried `place=suburb|neighbourhood|town` nodes per AOI, because the
interpretation depends entirely on what fabric each bbox covers:

- **capetown → Khayelitsha** (Enkanini, Kuyasa, Harare, Makhaza, Ilitha Park).
  One of South Africa's largest townships — dense informal fabric, not the Table
  Mountain trail network. I checked the hiking hypothesis explicitly: only
  **3 of 1,544** `path` ways carry hiking-specific tags (`sac_scale`,
  `trail_visibility`, `mtb:scale`), and the AOI holds one small nature reserve
  (Wolfgat). The 8.35 km/km² is **real informal-settlement path mapping**.
- **nairobi → Kibera** (named directly, plus Olympic, Karanja Stage).
- **lagos → Ebute-Metta and Makoko** — Makoko being among the densest informal
  waterfront settlements anywhere.
- **jakarta →** no `place` nodes returned at all in a 42.84 km² central-Jakarta
  bbox, which is itself a mild completeness signal.

### Ranking by true pedestrian-path density, and the read

| rank | city | foot/km² | read |
|---:|---|---:|---|
| 1 | capetown (Khayelitsha) | **8.35** | dense informal fabric, densely mapped — **4.4× the next city** |
| 2 | dharavi | 2.78 | community-mapped, see caveat |
| 3 | dhaka | 2.27 | plausible |
| 4 | nairobi (Kibera) | 2.11 | community-mapped, see caveat |
| 5 | kigali | 1.94 | plausible |
| 6 | guatemala | 1.83 | plausible |
| 7 | accra | 1.29 | **suspect** |
| 8 | hcmc | 0.90 | mixed — see note |
| 9 | nusantara | 0.63 | **low, but plausibly genuine** |
| 10 | jakarta | 0.39 | **suspect** |
| 11 | lagos | 0.19 | **strongest under-mapping signal** |

**The Dharavi/Kibera caveat lands harder than expected.** Both were flagged in
advance as having had dedicated community mapping and therefore atypically good
coverage. They measure 2.78 and 2.11 km/km² — and **Khayelitsha, at 8.35, is
three times Dharavi.** So the two AOIs nominated as "atypically good" are not
the ceiling; they sit mid-table. Either Khayelitsha is exceptionally mapped even
by community-mapping standards, or Dharavi and Kibera are less complete than
their reputation implies. Both readings are consistent with the numbers and this
work cannot separate them. **Neither Dharavi nor Kibera should be used as the
representative case, and neither should be used as the optimistic bound.**

**Outliers, in order of confidence:**

- **lagos (0.19 km/km²) — the clearest signal.** 3.30 km of pedestrian way
  across 17.13 km², from **14 `footway` ways** total, with `pedestrian` and
  `steps` both at zero. The AOI contains Makoko and Ebute-Metta. Dense informal
  waterfront settlement with essentially no mapped pedestrian network is far more
  consistent with an OSM completeness gap than with an absence of paths. Note
  its arterial coverage is fine (32.0 km) — **the gap is specifically in the
  pedestrian layer, not in OSM presence generally**, which is the signature of
  partial mapping rather than an unmapped area.
- **jakarta (0.39)** — 16.91 km over 42.84 km² of central Jakarta kampung
  fabric, and no `place` nodes at all. Suspect on the same grounds as Lagos,
  slightly weaker because I did not confirm the specific neighbourhoods.
- **accra (1.29)** — mid-table but with 102 km of `service` against 13.9 km of
  `footway`, a lopsided profile suggesting vehicular-first mapping.
- **hcmc (0.90)** — genuinely ambiguous. The 120.96 km² AOI is 5–17× the others
  and likely spans periurban land, so a low *mean* density may be an averaging
  artifact rather than a mapping gap. Its 29,077 ways are the most of any city.
  **Do not treat this as under-mapped without re-measuring on a comparable
  sub-AOI.**
- **nusantara (0.63)** — lowest overall network density (4.35 km/km², half the
  next city) and missing `motorway`/`primary`/`secondary` entirely. This is the
  Indonesian new-capital greenfield site, so **sparse mapping here plausibly
  reflects sparse construction**, not a mapping gap. The one low-density city I
  would *not* flag as under-mapped.

### What this does and does not support

Measured: pedestrian-path density spans **44×** across the 11 training AOIs
(0.19 → 8.35 km/km²), while total network density spans only **6×**
(4.35 → 26.40) and arterial coverage is near-universal. **The variance is
concentrated almost entirely in the pedestrian layer.**

Inferred: for a pipeline relying on OSM road geometry, arterial and
`residential`/`service` geometry looks broadly usable across all 11 cities,
whereas **pedestrian-path geometry is not uniformly available and its
availability does not track the density of the fabric it should describe.** Any
per-AOI feature derived from footpath geometry would carry a bias that varies by
city in a way the pipeline currently has no signal for — the same class of
problem as `rainfall_spatial_treatment` in §5.2, but undeclared.

**Explicitly not established:** any completeness percentage; whether the low
cities are missing paths or genuinely have fewer; whether Khayelitsha's 8.35
represents near-complete mapping or merely better-than-peers. Settling those
needs a reference network — a hand-digitised sample from imagery over a few
km² per city would be the cheapest route, and is a separate piece of work.
