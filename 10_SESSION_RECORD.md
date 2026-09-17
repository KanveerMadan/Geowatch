# 10 — Session Record

**Everything found, tested, failed and corrected in the session of 2026-09-11 → 09-14.**

This is the evidence document. `11_HANDOFF.md` is the "what to do next" document —
read that one first if you only read one.

Nothing here is a plan. Every number traces to something measured during this
session or to a document already in the repo.

---

## Part 1 — What was built (items 40–45)

All on branch `applicability-gating`, off `master`, **unmerged**.

| commit | item | what |
|---|---|---|
| `3e073ca` | 40 | applicability gates downstream computation (C14/C20) |
| `687ba77` | 41 | render applicability banner (C32) |
| `c90ff95` | 42 | Gate C waiver on all output paths (C23/C24) |
| `618b64b` | 43 | single-source palette + wire X-API-Key header (C31) |
| `8f02b10` | 44 | assert band order at runtime (C4) |
| `b69cd92` | 45 | enforce source_checkpoint provenance (C10) |

**Part 7 complete.** Part 8: 43, 44, 45, 47, 70 done; **item 46 remains** (remove
`primary_tile`, fork already decided: remove the field, don't build a basemap).

Notable during this work:

- **Item 40** — `compute_applicability()` genuinely read `hydrological_surfaces`,
  so the reorder was a real cycle, not a mis-ordering. Split into two stages,
  proven behaviour-preserving across all 192 input combinations before landing.
  Only pluvial/waterlogging/exposure inherit OOD; fluvial/coastal/flash_flood use
  independent data sources and deliberately do not.
- **Item 42** — widened scope: `risk/compute.py` had the identical defect one
  level up, four return paths, only the last carrying the field. Measured
  pre-fix, 3 of 4 returned `None`, and those three are the ones that fire in
  Phase 10A.
- **Item 45** — upgraded from the dead validator's `basename` comparison to a
  sha256 hash comparison. Basename passes for any file sharing a name, including
  a retrained checkpoint written to the same path.

---

## Part 2 — The CAAT blocker (pipeline is offline)

**Item 45's provenance enforcement correctly rejects the deployed
`models/production/caat_thresholds.json`.** That file has no `source_checkpoint`
key at all; its own caveat records that it derived from 11 LOCO fold models, not
from the production checkpoint. It has never had provenance.

**Recalibration was run but not deployed.** Results:

| | mean unknown% | cities over the 45.0 OOD gate |
|---|---|---|
| old (deployed) | 19.25% | 0 / 11 |
| pooled-new | 53.25% | 9 / 11 |
| stratified per-city | 42.78% | 6 / 11 |

Every threshold rose, mean +0.229. The direction is explained and correct — the
old file was computed on isolated 64×64 forward passes while production uses
sliding-window averaging, which sharpens confidence.

**Diagnosed root cause, and stratification does not fix it.** The calibration set
is drawn from annotator-selected segments (4.8–68.4% raster coverage per city),
biased toward clear, segmentable pixels. A 10th-percentile threshold derived from
the easy fraction and applied to the whole raster necessarily rejects far more
than 10%. Stratification reweights *between* cities; the defect is *within* each
city's calibration set. That is why it recovers only 10.5 of the 34pp gap.

**Also still live: C11.** Confidence penalties are applied to probabilities before
the CAAT comparison at inference (`inference.py:616-624`), but thresholds are
calibrated on unpenalised probabilities. The ledger says "Deleted with the
penalty" — the penalty is still there. Both threshold sets inherit this, so any
threshold set is measurably wrong for `paved_road` and `standing_water` until
it's fixed.

**And `validate_recalibration.py` judges success by `unknown_pct`**, which
improves whenever thresholds drop. It would call a threshold-lowering a success.
It measures no accuracy or precision.

**One claim I passed on that turned out to be unsupported:** I said two prior
CAAT recalibration attempts had both worsened unknown%. No commit message,
tracked file, or scratch file references them, and `archive/AUDIT_FINDINGS.md:838`
says the opposite — the script's output was *never deployed*. Treat that memory
as wrong.

---

## Part 3 — The four new findings

### C41 — the classifier is RGB-only, on tile-relative values

The largest finding of the session.

- `ResNet50_Weights.SENTINEL2_RGB_MOCO`, `in_chans: 3`, bands `['B4','B3','B2']`.
  `conv1.weight` is `(64, 3, 7, 7)` in both a fresh load and the deployed
  checkpoint. **No slicing code exists anywhere** — the 13-band premise I gave it
  was wrong, and the off-by-one confound it was built to catch cannot exist.
- **NIR, SWIR1 and SWIR2 are exported into `raw.tif`, written to `.npy`, and then
  discarded before inference.** `run_inference()` reads an 8-bit RGB PNG.
- The checkpoint's own transform is `Normalize(mean=[0], std=[10000])` — it
  expects absolute reflectance. `raw.tif` is already on exactly that scale. But
  the model consumes a **per-tile 2nd/98th percentile stretch** instead:

| city | raw reflectance mean | what the model gets | inflation |
|---|---|---|---|
| dharavi | 0.089 | 0.212 | 2.4× |
| accra | 0.124 | 0.389 | 3.1× |
| jakarta | — | — | 1.1× |
| capetown | — | — | 2.3× |

  The same physical surface yields different model input depending on what else
  shares its tile. Training and inference apply the identical transform, so this
  is **not** train/serve skew — it is a pretraining-transfer and cross-city
  generalisation concern, which is exactly what LOCO measures.

**Why this matters beyond itself:** item 21's 1.70° built/paved separation, its
~0.7° noise floor and its R² ceilings were all computed in **6-band** space. The
classifier does not operate in that space. Neither result bounds the other, and
treating one as evidence about the other overstates both.

### C42 — the production checkpoint's training source is ambiguous

**Both citations are true, and nothing in the repo records the split:**

| notebook | role | builders | separation loss |
|---|---|---|---|
| `geowatch_segformer_finetune_UPDATED` (cited by `resnet_model.py`) | **architecture** source — does the ResNet50 encoder swap, cell 25 | 3 | none (cell 27 is CE + Dice) |
| `geowatch_water_loco_with_diagnostics` (`AUDIT_FINDINGS.md:689`) | **training** source | 5 — adds `osm_generated`, `osm_generated_water` | present |

Following the code's own pointer rebuilds the wrong pipeline, which is exactly
what happened. Same class as C5 and C10/item 45.

**`PAVED_ROAD_CAP_PER_CITY` is 180 in `_UPDATED` and 25 in the training
notebook.** That, not `sample_stride`, explains the 2.75× `paved_road`
over-generation in the first rebuild attempt — the cap binds in all 11 cities
before stride can matter. (My `sample_stride` hypothesis was wrong; the
tile-size observation is separately true — `lon_per_px` runs 89.3e-6 to 195.3e-6,
so HCMC, Jakarta, Nusantara and Cape Town are coarser representations of larger
AOIs — but it would only have mattered had the cap not bound first.)

### C43 — 0.313 was measured on a materially easier task than the pipeline runs

Measured on the reconstructed 1,414-patch set:

| source | n | labelled px | single-class | what it is |
|---|---:|---:|---:|---|
| `sam` | 268 | 72.1% | **100%** | one segment, bbox-cropped, resized to 64×64 |
| `osm` | 275 | 25.7% | **100%** | centreline buffered 2 px, rest IGNORE |
| `osm_generated` | 274 | 24.4% | **100%** | one road's geometry, bbox-cropped, resized |
| `osm_generated_water` | 95 | 43.7% | **100%** | one water body, same construction |
| `sliding_window` | 502 | 29.4% | 58.8% | window off the label canvas, dominant label |
| **all** | **1414** | **36.7%** | **85.4%** | |

Four of five builders are single-class **by construction**. The SAM and
OSM-generated builders **bbox-crop and resize to 64×64**, normalising scale away.
The OSM builders label only road/water pixels — the hard part, deciding what the
surrounding fabric is, is marked IGNORE and never scored.

**Inference** (`inference.py:335-469`) slides 64×64 at stride 32 across the whole
raster at native resolution, averages softmax across overlapping windows, and
argmaxes **every** pixel. No bbox, no resize, no IGNORE, no dominant-label
shortcut. The neighbouring-class decisions training marked IGNORE are exactly the
ones producing the confusion the project has been chasing.

Validation is scored on the held-out city's *patches*, built the same easy way,
so both sides of the measurement share the simplification.

### C44 — two of three Overpass endpoints are dead, and failures are logged without status codes

| endpoint | result |
|---|---|
| `overpass-api.de` | HTTP 200, healthy, `Rate limit: 2` |
| `overpass.kumi.systems` | ReadTimeout |
| `overpass.openstreetmap.ru` | ConnectTimeout |

Two patterns, **not** equally affected:

- **Round-robin** — `generate_osm_road_masks.py:110`, `generate_osm_water_masks.py:103`.
  `URLS[attempt % 3]` with `retries=4` → de, kumi, ru, de. **Two of every four
  attempts go to dead hosts**, paying 15/30/45 s backoff each.
- **Nested fallback** — `ingestion/exposure_sources.py:296`, `ingestion/osm_dem.py:45`.
  Dead host reached only after the live one fails three times. Cost only on a
  path already failing. (My "two-thirds wasted on every real run" framing was
  overstated for these two.)

**The logging half matters more.** All four callers catch bare `Exception` and
never log `response.status_code`. What looked like a uniform wall of `HTTPError`
turned out to be **HTTP 504 carrying `runtime error: open64: 0 Success
/osm3s_osm_base Dispatcher_Client::req`** — a transient Overpass *dispatcher*
fault, not a query timeout. An unchanged retry 10 s later succeeded every time.
The remedies diverge sharply: 429 needs long backoff, a genuine timeout 504 needs
the query split, a dispatcher 504 needs only a short retry. **My instruction to
split the queries was the wrong remedy**, and the error body ruled it out.

Filed, not fixed — endpoint liveness is environment- and time-dependent, so
hardcoding today's list into production would encode current network conditions
as permanent fact.

### Pending, not yet given a C-number

**`best_miou` selection in LOCO is selection on the test set.** The held-out city
is both validation and test, and the training notebook selects the best epoch on
it. So **0.313 is itself a max-over-epochs-on-test figure.** This is a third
qualification on the headline number alongside C41 and C43, and all three should
be cross-referenced — anyone quoting 0.313 needs all three at once.

---

## Part 4 — Checkpoint metadata (read directly from the .pth)

```
num_classes            7
ignore_index           255
class_weights          [0.6135, 2.9653, 0.1707, 0.4915, 1.3479, 1.0466, 0.3646]
n_train_patches        1272
n_monitor_patches      141
loco_mean_miou         0.313
loco_std_miou          0.0564
loco_n_folds           11
monitor_miou_at_save   0.6159 @ epoch 31
architecture string    "GeoWatchResNetSeg (ResNet50 SSL4EO-S12 MoCo + DeepLabV3+,
                        paved_road/dense_informal_roofing separation loss)"
training_cities        all 11
```

`monitor_miou_at_save` 0.6159 vs LOCO 0.313 is a **~49% cross-region drop** —
squarely inside the 47–66% range the architecture audit found is normal across
every model in the field.

**The weights are TRAIN-split weights, not `all_patches` weights.** Inverting the
formula: at a total of 1,272 the implied counts are integral to within 0.09; at
1,413 they are integral nowhere. That matches cell 39
(`full_counts = Counter(p['label'] for p in train_patches)`), which overrides
cell 18's earlier all_patches version.

---

## Part 5 — The Arm A collapse, and what it took to explain it

A four-arm probe (A: RGB+stretch, B: RGB+absolute, C: 6-band+stretch,
D: 6-band+absolute) was run to test whether the C41 findings mattered. **Arm A —
the control, meant to reproduce production — collapsed to 0.0221 with six of
seven classes at exactly zero, loss flat from epoch 0.**

**Ruled out, in order:**

| hypothesis | test | result |
|---|---|---|
| class weights | checkpoint's own weights | flat 1.847 → 1.827 |
| + Dice | weighted CE + Dice | flat 2.756 → 2.718 |
| learning rate | encoder 1e-5 / decoder 3e-4 + cosine | flat 1.839 → 1.846 |
| gradient clipping | `clip_grad_norm_(1.0)` | flat, pre-clip norms still 1.3×10⁵ |
| cross-city stretch | single city only | flat 1.468 → 1.401 |
| input magnitude | rescaled ×0.27 to B's mean | flat 1.839 → 1.816 |
| input magnitude | full standardisation (0 mean, unit std) | flat 1.848 → 1.828 |
| misalignment | Pearson r, PNG vs raw.tif | r = 0.948–0.993, aligned |
| degenerate input | NaN/Inf, distinct values, channel corr | clean, 256 levels |
| plumbing | overfit a single patch | **overfits fine**, 1.67 → 0.02 in 200 steps |
| plumbing | label tensors across arms | byte-identical |

Arm B under identical conditions: 0.494 → 0.021.

**Root cause: patch construction.** The probe used native-resolution sliding
windows over sparse multi-class canvases. Production uses the five single-class
builders described in C43. That is a materially harder task, and the 1.1×10⁵
gradient norm was a symptom of it, not the cause.

**Correction on the record:** I reported supervision density as ~0.8%. That was
the ≥32-pixel *acceptance threshold*, not a measurement. Measured, the probe's own
sampler gives **44.77% mean / 37.08% median**. And production's is **36.7% —
lower**. Density was never the difference; **single-class construction was.**

### The rebuild that fixed it

Ported the 5-builder notebook. **Gate passed:**

```
rebuilt total          1414   vs checkpoint 1413 (1272 + 141)
per-class              every class reachable, all |z| <= 1.85
best of 20,000 draws   max |delta| 0.0083 against the stored weights
```

**Fidelity run** (Arm A + separation loss, Accra): **0.3925, all seven classes
non-zero**, against the broken probe's 0.0221 with six at zero. The earned claim
is that the reconstruction reproduces the training behaviour 0.313 describes —
not that it reproduces that run. (Accra may be an easy fold; n=1 fold, n=1 seed;
the patch set is one patch over and that +1 is unexplained.)

---

## Part 6 — The four-arm results

**Fixed budget, 40 epochs, no early stopping, 3 seeds, held-out Accra, production
patch geometry, separation loss excluded uniformly.**

| arm | bands | scaling | plateau (last 5) | best | peak epoch | decay |
|---|---|---|---|---|---|---|
| A | RGB | stretch | 0.3503 ±0.0305 | 0.3808 ±0.0137 | 37 / 27 | +0.012 / +0.034 |
| B | RGB | absolute | 0.3642 ±0.0368 | 0.4122 ±0.0227 | 24 | +0.025 |
| C | 6-band | stretch | **0.3708 ±0.0144** | 0.4444 ±0.0348 | 16 | +0.117 |
| D | 6-band | absolute | 0.2902 ±0.0102 | **0.4513 ±0.0200** | 5 | +0.137 |

**D − B depends entirely on the selection rule:**

| rule | D − B | consistency |
|---|---|---|
| plateau | **−0.0740** | all 3 seeds negative (−0.112, −0.058, −0.052) |
| best epoch | **+0.0391** | — |

Seed sd is 0.010–0.037, so D−B at plateau is real. B−A (+0.0140) is inside seed
noise and should not be claimed.

**The decay column is the most informative result.** It orders cleanly by channel
count: 6-band arms reach their generalisation peak **3–7× earlier** and then
overfit hard. That is a capacity-versus-data-volume statement, measured directly.

**Per-class movement, which the mean completely hides:**

| class | A | B | C | D |
|---|---|---|---|---|
| `standing_water` | 0.26 | 0.34 | **0.61** | **0.61** |
| `vegetation_clearing` | 0.4496 | 0.4563 | 0.3587 | **0.0009** (sd 0.001) |
| `dense_informal_roofing` | 0.22 | — | 0.03–0.08 | 0.03–0.08 |

`standing_water` roughly doubles under 6 bands — exactly what NIR/SWIR should do.
`vegetation_clearing` is driven to zero in all three seeds — **reproducible model
behaviour, not thin-class noise**. But it is still measured on Accra's single
`vegetation_clearing` patch (4,177 px, the thinnest fold for that class; 3 cities
have none at all), so what's stable is *this fold*.

**Earlier broken-control probe, for the record only:** A 0.0221, B 0.2302,
C 0.2060, D 0.2299, D−B = −0.0003. The "six bands add nothing" reading came from
here and from the peak-rule reading. It was partly an artefact of where runs were
stopped.

**Power floors, computed for the 11-fold design:**

| class | folds with the class | min achievable two-sided p |
|---|---|---|
| `dense_informal_roofing`, `paved_road`, `dense_vegetation` | 11 | 0.0010 |
| `standing_water` | 10 | 0.0020 |
| `vegetation_clearing`, `active_construction` | 8 | 0.0078 |
| `sparse_informal_roofing` | **5** | **0.0625** |

`sparse_informal_roofing` **cannot reach p<0.05** regardless of effect
consistency. Without that floor printed beside it, a null reads as evidence of no
effect.

---

## Part 7 — External audits

### OpenAerialMap — verdict: validation reference only

21,359 scenes, **98.2% at ≤2 m GSD** — resolution is not the problem. **Usable
coverage is ~0.03–0.22% of global land**, and it is a lottery.

- **Dharavi returns zero.** So do Delhi, Karachi, Cairo and Khartoum, metro-wide.
- Of 47 named informal settlements: **19** Tier A (dedicated ≤15 cm), **8** Tier B
  (satellite mosaic only), **20** nothing usable.
- North America holds 29.2% of the catalogue; Sub-Saharan Africa and South Asia
  together hold 11.0%.
- **The Brazil trap:** 3,501 scenes nationally, but Rocinha, Complexo do Alemão
  and Paraisópolis each return **zero**. It's precision-agriculture drone work in
  the rural interior. Country-level counts mislead completely.
- India ~42 scenes, Pakistan 8, Nigeria 13, Egypt 7 — ~70 between four countries
  holding a very large share of the world's informal-settlement population.
- **Tier B is Maxar/Vantor**, likely CC BY-NC under a waiver scoped to OSM
  tracing, not model training. Treat as restricted until verified per scene.
- Genuinely comparable multi-date same-sensor sequences exist at **4–5 sites
  worldwide**.

**The recommended use, and it is a good one:** downsample the ~19 Tier A sites'
5 cm orthophotos to 10 m and measure classification error **as a function of alley
width**. That produces an error budget for the resolution ceiling — turning "10 m
cannot resolve this" from an argument into a curve. Needs no new data, unblocked
today.

### Architecture audit — verdict: the bottleneck is not architecture

- **Cross-region drops of 47–66% are universal** — foundation models and plain
  U-Nets alike. 0.313 against a within-city 0.6159 is on the field's curve, not
  off it.
- **Two SSL4EO-S12 variants were the worst two under domain shift.** A real
  negative signal about the current pretraining.
- The measured gap between the best geospatial foundation model and a
  from-scratch U-Net is **0.77–2.0 mIoU points** — below this project's detection
  threshold of ±0.035.
- Recommended: **keep ResNet50** (a bigger backbone on 1,345 patches makes
  generalisation worse), **replace DeepLabV3+ with a U-Net decoder**, **delete
  SAM**, add strong geometric augmentation. Expected gain **+0.01 to +0.04** —
  possibly inside the noise band.
- The one interesting alternative: **Prithvi-EO-2.0-300M-TL + LoRA**. Its six
  bands are exactly the project's six (no stem surgery), and LoRA is the only
  published mechanism directly targeting this failure mode — it cut geographic
  hold-out drop from −8.06pp to −2.47pp on Sen1Floods11. Catch: pretrained at
  30 m, inference at 10 m, a 3× mismatch that is unverified.
- **Its answer to "what moves 0.313 most" is not an architecture change** — it's
  the taxonomy change, because that stops asking the model to do something the
  data can't support. It explicitly declines to give an expected number, since
  removing a class changes mIoU for three entangled reasons and **the result is
  not comparable to 0.313 at all.**

### Evaluation-design findings that came out of this

- **SE on the mean is 0.017**, so a 95% interval of ~±0.033. Comparing *means*
  cannot detect anything under ~0.035 mIoU. **Paired per-fold comparison**
  (Wilcoxon on 11 deltas) cancels fold-to-fold variance and roughly triples
  sensitivity. The harness now does this — `experiments/harness/loco.py`, 26 tests.
- **The 7-class unweighted mIoU can hide large, physically-predicted, offsetting
  per-class movements.** The Accra result is the standing demonstration. This
  affects how every arm comparison in this project should be read.
- **Thin classes make the mean hostage.** `vegetation_clearing`: 70 patches
  across 11 cities, 3 with none, and on Accra a single patch drove a −0.51 class
  delta.

---

## Part 8 — City selection measurement

39 sites (28 candidates + the existing 11 as baseline), **identical 5×5 km,
25 km² boxes**. The existing AOIs range 6.8 km² (Kigali) to 123.2 km² (HCMC), so
using them as-is would have made the distance matrix partly a measure of AOI size.

**Cloud gate: drops nobody.** All four flagged risks clear comfortably — Monrovia
65 clear dates, Freetown 69, Kinshasa 44, Lima 75.

> **This depends entirely on measuring the AOI rather than the granule.**
> Monrovia reads **11** by `CLOUDY_PIXEL_PERCENTAGE` and **65** measured directly
> from SCL over the box. A granule is ~110×110 km; the AOI is 0.2% of one. On the
> literal metadata test, Manila, Caracas and Bogotá would all have looked
> marginal at 5. **My "Monrovia and Freetown are too wet" warning was wrong.**

**Open Buildings gate: drops Amman and Casablanca** (zero polygons). Footprints
are the vector half of merged `impervious`, so zero breaks it.

**MENA is fillable, by exactly one city.** Cairo returns 73,858 polygons — Open
Buildings covers Egypt, contrary to my assumption that MENA is outside its
extent. If Cairo is rejected, MENA cannot be filled from this list. Cairo has no
OAM validation imagery.

**Two premises the measurement corrected:**

1. **The existing 11 are not uniformly flat.** Kigali is 8.61°, Guatemala 6.49°.
   The gap is the steep end **above 10°**, not hillside terrain altogether.
2. **OSM building completeness does not predict road completeness.** I passed on
   the published ~9% South Asia buildings figure. Karachi has the **densest road
   network of all 39 sites** (38.5 km/km²); Delhi 28.9, Kolkata 25.7, against an
   existing median of 23.1. Candidate median 23.8 is indistinguishable from
   existing. Applying the buildings figure to roads would have wrongly demoted the
   whole region.

**Ranked on `d_nearest`, not `d_centroid`** — the centroid of eleven different
cities isn't a real place, so a candidate can sit far from it while duplicating a
city already held. That's what catches Maputo (0.76, nearest Accra), Mexico City
(0.78) and Addis Ababa (0.87).

---

## Part 9 — Things I got wrong, collected

Worth reading as a set, because several came from me and cost real time.

1. **"Two prior CAAT recalibration attempts worsened unknown%"** — unsupported.
   The repo audit says the output was never deployed.
2. **"The checkpoint is 13-band and gets sliced to 6"** — wrong. It's a 3-band RGB
   checkpoint and no slicing code exists.
3. **"The model is 6-band multispectral"** — wrong, and it invalidated the premise
   of the first merged-taxonomy prompt and much of the architecture audit's §3.
4. **"Five builders in `_UPDATED`"** — I read cell 11's markdown, which describes
   five; the code implements three. Sent the rebuild down the wrong path.
5. **"`sample_stride` interacting with tile size over-generated `paved_road`"** —
   wrong. It's `PAVED_ROAD_CAP_PER_CITY`, 180 vs 25.
6. **"Split the Overpass queries if 504s persist"** — wrong remedy. The error body
   showed a dispatcher fault; splitting treats query weight.
7. **"Two-thirds of retry attempts wasted on every real run"** — overstated. True
   for the two `generate_osm_*` scripts, not for the two `ingestion/` modules.
8. **"Monrovia and Freetown are too cloudy"** — wrong, from using granule metadata
   instead of AOI-level measurement.
9. **"MENA has no Open Buildings coverage"** — wrong. Cairo has 73,858.
10. **"Supervision density is ~0.8%"** — I passed on a threshold as a measurement.
    Actual 44.77%; production 36.7%.
11. **"Six bands add nothing"** — stated three times, and it was partly an
    artefact of where runs were stopped. The honest version is in Part 6.
12. **The learning-curve budget** — 1,600 equal steps undertrained the 100% point
    and would have flattened the curve toward "don't annotate". Caught by a check,
    fixed to 3,200.
