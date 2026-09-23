# GeoWatch — Current State

**Where the project actually is, across all branches, as of 2026-09-23.**

This document exists because the same facts kept being rediscovered. The branch
layout, the reason the pipeline is offline, and the state of the classifier
reproduction work were all live only in conversation, so every session paid to
re-derive them. They are written down here instead.

It is a **state** document, not a decision document. Nothing here signs off
anything. Where a finding or a decision is unsigned, it says so.

---

## Reading order

| Read | For |
|---|---|
| `01_DIAGNOSIS.md` | Why the architecture was replaced rather than repaired. The "why". |
| `02_ARCHITECTURE.md` | What the project becomes. Assumes 01. |
| `03_EVIDENCE.md` | The measurements behind the conclusions. Appendix A is the empirical record. |
| `04_FINDINGS_LEDGER.md` | Every finding and its fate. **Check before building anything** — roughly a third are deleted by the architecture change. |
| `05_BUILD_MANUAL.md` | What to build, in order. Parts 1–13. |
| `06_UNMIXING_CEILING.md` | The item 21 investigation in full. **Lives on `unmixing-ceiling-investigation`, not on `master`.** |
| `07_ITEM_21.md` | Item 21's standing summary — the ceiling result and what it does and does not license. |
| `08_STATE.md` | This document. Where everything is right now. |
| `09_TAXONOMY_MIGRATION_PLAN.md` | The 4-class migration and annotation plan. **Phase 1 is closed by the gate — see §Gate result below before reading §4.** |
| `CONTRIBUTING.md` | Branch, commit and push discipline. |

**Start here if you are new:** 01 → 02 → this document → 04. The build manual
is a reference, not a read-through.

---

## Branches

All three work branches are cut from `master` and **none is merged**.

| Branch | Head | Carries | State |
|---|---|---|---|
| `master` | `71f31fa` | Parts 1–3 complete; Part 8 items 47 and 70 | The stable line. Default branch on GitHub. |
| `applicability-gating` | `b69cd92` | Items 40, 41, 42, 43, 44, 45 | Part 7 complete. Part 8: 43, 44, 45 done; **46 remains**. |
| `merged-taxonomy-retrain` | `5a67b60` | Step 1 only — label mapping plus two blocking findings | **PAUSED.** |
| `band-mapping-verification` | `0d6e7ce` | C41, C42, the LOCO harness, the four-arm probe, the patch-builder port | Active working branch. |
| `unmixing-ceiling-investigation` | `9715c7d` | Item 21 in full, `06_UNMIXING_CEILING.md`, Decisions 11/13/14 amendments | **Awaiting human sign-off. Does not merge until signed.** |
| `part8-trust-boundaries` | `b4b410a` | Items 70 and 47 | Already merged into `master` at `42c1545`; branch retained. |

`unmixing-ceiling-investigation` is the standing example in `CONTRIBUTING.md` of
why investigation branches stay separate: it carries four unsigned decisions,
and building on it silently inherits them.

---

## Where the build manual actually stands

| Part | Status |
|---|---|
| **Part 1 — Unblock** | ✅ Complete |
| **Part 2 — Verify** | ✅ Mostly complete (item 10 partially done) |
| **Part 3 — Decide (the gate)** | ✅ Complete. All seven decisions settled — though Decision 13 was subsequently **reopened** by the item 21 investigation, on `unmixing-ceiling-investigation` and unsigned. |
| **Part 4 — Build the architecture** | 🔓 Not started. Item 21's pilot ran ahead of it as its own gate; see `07_ITEM_21.md`. |
| **Part 5 — Validation discipline** | 🔓 Not started |
| **Part 6 — Epistemic contract** | 🔓 Not started |
| **Part 7 — Gating architecture** | ✅ **Complete** on `applicability-gating` — items 40, 41, 42 all landed. Not on `master`. |
| **Part 8 — Contract enforcement** | Items 43, 44, 45 done on `applicability-gating`; 47 and 70 merged to `master`. **Only item 46 remains.** |
| **Parts 9–13** | 🔓 Not started (Part 9 deleted per Decision 12) |

**Item 46 — the remaining Part 8 item — has a decided fork:** *remove the
`primary_tile` field; do not build a full-AOI basemap.* Nothing correct exists
for `primary_tile` to point at, and the field has no live consumer. The in-code
comment claiming the projection "works unchanged regardless of how many tiles"
is false for the base image and must be corrected in the same change.

---

## RETIRED — the 7-class pipeline, and the CAAT blocker with it

**Status: closed 2026-09-23. Not deprioritised — dropped.**

> **The old per-pixel 7-class pipeline is retired.** The learning-curve gate
> (**G1**) showed its data axis is exhausted, the patch-construction
> investigation (**C43**) showed its construction axis is exhausted, and the
> architecture that replaces it produces continuous fractions with no argmax.
>
> **The CAAT blocker is dropped, not solved.** CAAT is a per-class
> confidence-threshold mechanism applied to a discrete argmax. There is no
> argmax in the fraction architecture, so there is nothing left to threshold:
> the deployed-vs-recalibrated threshold decision, the 45.0 OOD gate
> re-derivation, and **C11** (penalties applied at inference but not during
> calibration) all evaporate with the mechanism. None of them needs a human
> decision any more.
>
> **Two things from it are carried forward, because they are about
> methodology, not about CAAT:**
>
> 1. **Calibrating on annotator-selected segments does not transfer to the
>    full raster.** Those segments cover 4.8%–68.4% of the raster and are
>    biased toward easy pixels; a 10th-percentile threshold learned there
>    over-rejects everywhere else, and stratified pooling recovered only 10.5
>    of the 34 pp gap. **The fraction validation set must be drawn from the
>    full raster, not from annotated segments.** This is the same selection
>    bias the C43 scarcity work measured from the other direction.
> 2. **Applicability gating replaces confidence thresholding as the
>    out-of-distribution mechanism** — items 40–42, now merged to `master`
>    (`a98b529`). That is a per-AOI gate on whether output is trustworthy at
>    all, which is what CAAT was being asked to do and was the wrong tool for.
>
> **The deployed artifacts** — `geowatch_production_model.pth`,
> `caat_thresholds.json` — are **retired inputs, not reference data.** Do not
> recalibrate them, and do not quote 0.313 as a current capability number
> (see C43 for what it measures).

#### Original entry, retained as the record

**Status: unresolved. Awaiting a decision.**

Item 45 added checkpoint-provenance enforcement (C10): the loader refuses
threshold files whose `source_checkpoint` does not match the loaded model. The
deployed `models/production/caat_thresholds.json` has **no `source_checkpoint`
at all**, so it is correctly refused. The enforcement is working as designed;
the artifact predates it.

Recalibration was run. **It was not deployed**, because the new thresholds are
worse in a way that trips the project's own pre-registered gate:

- unknown% **16% → 48%** — roughly tripled
- **4 of 6 cities** flip past the pre-registered OOD gate of 45.0

**Diagnosed root cause.** The calibration set is drawn from annotator-selected
segments, which cover **4.8%–68.4%** of the raster per city and are biased
toward easy, clear pixels. A 10th-percentile threshold learned on that subset
over-rejects when applied to the full raster. Stratified per-city pooling was
tried and recovers only **10.5 of the 34 pp gap** — it is a real improvement and
nowhere near a fix.

**Also open, and independent of the above: C11.** Proximity penalties are
applied at inference (`inference.py:616-624`) but *not* during calibration.
Both threshold sets — deployed and recalibrated — are therefore measurably
wrong regardless of which is chosen. C11 is filed under **DELETED** in the
ledger because the new architecture removes the penalty, but the penalty is
still live in the current pipeline, so the defect is live too.

**What this means practically:** deciding between the two threshold sets is
choosing between two known-wrong artifacts. The decision is a human call and has
not been made.

---

## Findings

### Fixed in code but never triaged

Eight findings have working fixes on `applicability-gating` and **still carry no
fate in `04_FINDINGS_LEDGER.md`**:

> **C4, C10, C14, C20, C23, C24, C31, C32**

They were closed by items 40–45. Assigning a fate is a human call and has not
been made, so the ledger and the code disagree until it is. Do not read the
ledger as authoritative on these eight.

Separately, the frontend **X-API-Key header is wired** (`618b64b`, item 43).
Earlier notes describing this as live breakage are stale — the API perimeter
(item 70) and its client are both in place.

### New, under NEEDS FATE

Filed on `band-mapping-verification` and untriaged. **C43 is no longer here —
it was investigated to completion and moved to CLOSED (see §Gate result and
§The patch-construction investigation below). C45 replaced it.**

**C45 — the OSM patch builders overwrite human labels with their own class.**
[E] `osm_generated` paints `paved_road` over 7,715 px the annotator called
`dense_informal_roofing` (60.2% of its overwrites); `osm_generated_water`
paints `standing_water` over 32,553 px the annotator called `dense_vegetation`
(92.3% of its overwrites, 4× more than it agrees). 369 of 1,414 patches come
from these builders; 63 patches / 48,101 px carry a real conflict. **Four
correction arms were built and none improved mIoU**, but a builder that
silently overwrites ground truth is a defect regardless — it corrupts what
every future experiment reads. Fixing it costs `paved_road` and
`standing_water` supervision, so it is not free.

**C41 — the classifier is RGB-only, on tile-relative values.** [E]
`SENTINEL2_RGB_MOCO`, `in_chans=3`, `bands=['B4','B3','B2']`. NIR, SWIR1 and
SWIR2 are exported to `raw.tif` and written to `.npy`, then discarded before
inference, which reads an 8-bit RGB PNG. Separately, the model consumes a
**per-tile 2nd/98th percentile stretch**, not absolute reflectance — Dharavi
0.089 → 0.212, Accra 0.124 → 0.389 — even though `raw.tif` is already on the
scale the checkpoint's own `Normalize(mean=[0], std=[10000])` expects.

This qualifies **every prior conclusion about spectral separability in the
classifier**, including the `paved_road` magnet-class behaviour and the failure
of the paved/roofing separation loss. All were observed in RGB. The 0.313 LOCO
baseline is an RGB-only, tile-relative number.

**C42 — the checkpoint's training source is ambiguous, and the code cites the
wrong notebook.** [E] There are two notebooks and both citations are true of
something:

| Notebook | Role | Builders | Separation loss | LOCO loop |
|---|---|---:|---|---|
| `..._UPDATED.ipynb` | **Architecture** source — ResNet50 encoder swap | 3 | none | no |
| `..._water_loco_with_diagnostics.ipynb` | **Training** source — produced the checkpoint | 5 | present | yes, behind 0.313 |

`ingestion/resnet_model.py` cites the first. The checkpoint's own `architecture`
string names a separation loss that only the second implements. **Nothing in the
repository records the split.** The 5-builder family adds
`build_osm_generated_patches` and `build_osm_generated_water_patches`.

Both notebooks are recoverable from history at `ecfe370`; `notebooks/archive/`
was deleted from the working tree at `faed0f2` (it was the source of a committed
credential).

### Still untriaged from earlier passes

**C36, C37, C38** — flagged during the Part 3 consolidation, never given a fate.

---

## The classifier-baseline investigation

The goal is a **trustworthy classifier baseline**, so band and reflectance arms
can be compared against something real. It is not there yet.

### Checkpoint metadata, read directly from the `.pth`

```
num_classes            7
ignore_index           255
class_weights          [0.6135, 2.9653, 0.1707, 0.4915, 1.3479, 1.0466, 0.3646]
n_train_patches        1272
n_monitor_patches      141
loco_mean_miou         0.313
loco_std_miou          0.0564
loco_n_folds           11
monitor_miou_at_save   0.6159   (epoch 31)
```

### The four-arm probe, and why it is not usable yet

Arms: **A** RGB + stretch (the control, = production), **B** RGB + absolute,
**C** 6-band + stretch, **D** 6-band + absolute. One fold, Accra.

**Arm A — the control — collapsed to 0.0221, six of seven classes at exactly
zero, training loss flat from epoch 0.** An experiment whose control is broken
cannot attribute anything, so it was stopped rather than extended to 11 folds.

Ruled out, each tested: class weights, Dice term, discriminative learning rates,
gradient clipping, label/image alignment, input magnitude, full standardisation,
cross-city stretch inconsistency, and plumbing (Arm A overfits a single patch
cleanly, and label tensors are byte-identical across arms).

**Root cause identified: patch construction.** Production patches are
single-class, bbox-cropped, resized to 64×64, and 100% labelled. The probe used
native-resolution sliding windows over sparse multi-class canvases — a
materially harder task, and not the task the 0.313 figure describes.

### The one surviving signal

**D (0.2299) vs B (0.2302)** — at absolute reflectance, six bands add nothing
over RGB. Both arms trained normally, so the comparison is internally valid.
But it is **n=1 fold, n=1 seed, on Accra**, which is not representative. If it
holds at 11 folds it is the consequential result of this whole line of work: it
points the bottleneck at **data volume**, not spectral information.

### The rebuild attempt

Porting the 3-builder `_UPDATED` notebook produced **2359 patches against the
checkpoint's 1413** (1272 + 141), with class weights off by up to 0.83.
Two failures are diagnostic:

- `standing_water` **2.5× under-weighted** — explained by the missing
  `build_osm_generated_water_patches`; 101 of 133 `standing_water` annotations
  are OSM-generated water, which the cited notebook never reads.
- `paved_road` **2.75× over-weighted** — *not* explained by missing builders,
  since adding sources pushes the total further above 1413. Something
  over-generates independently. Prime suspect: `sample_stride =
  max(20, aoi_km2 * 2)` interacting with tile size — **3 of 11 local tiles are
  512-px crops of larger rasters**, which changes `lon_per_px` and therefore how
  many pixels a road traverses. If the notebook assumed full rasters that only
  exist here as crops, that is a **data-availability gap, not a porting bug**,
  and it may cap how exactly the set can ever reconstruct.

---

## Gate result — the annotation campaign is closed as originally scoped

**The learning-curve gate returned on 2026-09-17: 132/132 folds, flat curve,
STOP.** Full numbers in `04_FINDINGS_LEDGER.md` → **G1**.

A 4× increase in data moved final-epoch LOCO mIoU by **+0.0075** against a
pre-registered detection threshold of **±0.035**; measured slope **+0.0029 per
doubling**, ~19× smaller than the +0.055 the plan's sizing assumed. All three
statistics agree (final +0.0075, last5 +0.0048, best\* −0.0335). The harness
is sound: the 100% `best_ON_TEST` point is **0.3118 ±0.0047** against the
shipped checkpoint's **0.313**, an independent 11-fold reproduction from a
rebuilt patch set. Per-class gains appear only in classes that were already
easy, and **none of the per-class movements is significant** when paired by
(city, seed).

This is the "flattening" branch of `09_TAXONOMY_MIGRATION_PLAN.md` §3's own
decision table. Per §3.2 that is the plan working, not failing. **Phase 1 as
scoped there — annotate a large set the same way — does not proceed.**

---

## The patch-construction investigation — C43, closed

The gate said the bottleneck is not data volume, which pointed at label
*construction*. That was investigated to completion on 2026-09-17/18 and
**C43 is now CLOSED**. Summary; full record in `04_FINDINGS_LEDGER.md`.

**Verified structure.** 85.4% of training patches are single-class; **63.3% of
all training pixels are IGNORE**; **0.14% of scored pixels sit on a
class-to-class boundary**. 45% of patches are bbox-cropped from a median ~16 px
and magnified (crop/64 spans 123×, 93.1% upsampled, aspect stretched up to
36×), and **89.5% of those fall outside the ground-scale range inference ever
produces** — 40.3% of the whole set. There is no scale augmentation to bridge it.

**Four corrections built and measured, all negative** (paired LOCO, identical
seed/order/weights, arms differ only in pixels):

| arm | change | ΔmIoU | p |
|---|---|---:|---:|
| B | delete the bad OSM overwrites | −0.0096 | — |
| C | restore the human labels | −0.0021 | — |
| D | restore them at native scale | −0.0055 | — |
| E | full native multi-class rebuild (85.4% → **47.7%** single-class) | **−0.1041** | **0.013** |

Arms B–D are 3 cities × 1 seed at 1,600 steps; arm E is 3,200 steps, **5 of 8
planned pairs completed** (seed 1337 × 4 cities, plus dharavi seed 7 — the run
was stopped before the rest and `fix_probe3.py` will resume it). The arm E
`val_base` result reproduces across both seeds on dharavi.

Arm E is the important one: it *achieved* the construction fix and made things
significantly worse, because removing magnification cost **31% of the
supervised pixel budget** (2.13M → 1.47M px). Structure was bought by paying in
volume, and volume won.

**The decomposition that explains why.** Exact integral-image counts over every
native 64×64 window position on all 11 canvases (633,571 usable windows):
85.4% single-class splits into **≈21.9 pp construction artifact** (309 patches,
recoverable by re-cropping — this is what arm E recovered, and it backfired)
and **≈63.6 pp genuine annotation scarcity** (899 patches). Roughly **26%
artifact, 74% real**. The binding limit is that **81.3% of the imaged area
carries no label at all**, and the native-window pool is only **703 usable
windows at stride 32 across all 11 tiles** — finer strides add overlap, not
diversity.

**Conclusion: every patch-construction-side fix available without new
annotation has been tested and has failed or backfired.** The remaining lever
is annotation *density*, not construction — which is the same resolution and
taxonomy-ceiling argument `01_DIAGNOSIS.md` already makes, now with the
alternative explanations measured and eliminated.

**Per-tile ceiling, for anyone scoping targeted annotation** (multi-class rate
over usable native 64×64 windows):

| tile | labelled | multi-class ceiling |
|---|---:|---:|
| dharavi | 22.8% | 87.5% |
| accra | 7.7% | 68.3% |
| kigali | 9.6% | 63.1% |
| dhaka | 7.3% | 50.4% |
| lagos | 24.4% | 41.6% |
| nairobi | 8.3% | 33.0% |
| capetown | 20.2% | 31.0% |
| **nusantara** | 7.1% | **29.4%** |
| **jakarta** | 68.4% | **28.5%** |
| **guatemala** | 5.1% | **22.8%** |
| **hcmc** | 4.8% | **21.3%** |

The four in bold are the lowest-ceiling tiles. jakarta is the instructive one:
68.4% labelled but 90.8% of that is a single class, so coverage is not the
lever — **class mixing is**.

---

## Ruled out — data sources, with reasons

This section exists so a new session does not re-propose something already
investigated and rejected. Several of these are attractive-sounding and were
proposed more than once. **Full evidence is `03_EVIDENCE.md` §C.1–C.3**; the
verdicts are consolidated here because that is where they get re-litigated.

**The governing bar** (§C.2, applied retroactively to every candidate): the
deployment scope is global, so a source must be **free, systematic, and globally
uniform** — the operating model Sentinel-2 itself provides. Under that bar,
commercial VHR fails outright (tasking-based, not standing archive) and
hyperspectral fails (opportunistic revisit). Only **Landsat thermal (TIRS)** and
**VIIRS nighttime lights** pass — and both add a new information axis rather
than fixing the sub-pixel resolution ceiling, which **no source meeting the bar
can do at any price point available to this project.**

| Source | Verdict |
|---|---|
| **NICFI Planet basemaps** | **Dead.** [E] `EEException: not found` on every asset path (`asia`, `africa`, `americas`, and the parent), against a healthy EE session. Program phase-out began January 2025; Norway cancelled the next-phase procurement September 2025. *Honest limit: GEE returns the same error for "does not exist" and "caller lacks access," so deleted-vs-permission-gated is undetermined.* **Any note describing NICFI as live 30°N–30°S coverage is stale.** |
| **Sentinel-1 for road/alley detection** | **Ruled out on resolution, not geometry.** [X/R] IW GRDH is **20.4 × 22.5 m** — the universally quoted "10 m" is *pixel spacing*, so it is twice as coarse as Sentinel-2, not equal. A 3 m alley is **15–20× below the resolution cell in azimuth**; one cell integrates several structures, several alleys and their layover together. Layover is real (`L = h·cot θ`; break-even at θ=45°, S1 operates at ~29–46°) but is *not* the binding constraint, and the resolution framing is the defensible one. Double-bounce at 2–4 m structure height is weak and unvalidated. No published S1 road detection in informal settlements exists at all. |
| **Sentinel-2 super-resolution** | **Recommended against.** [X] GeoSR-Bench: *"improvements in traditional SR metrics often do not correlate with gains in task performance, and the correlations can be negative."* On MODIS→Landsat rivers, SR recovered ~10% of the gap to real Landsat-8 (0.68 → 0.74–0.75 vs 0.95). ESA's own OpenSR funds a dedicated **hallucination** metric, rates 0.0610–0.5963. That the field needs a dedicated instrument to police SR answers how it understands it. |
| **ESA Earthnet Third Party Mission** | **India ineligible.** [X] Would otherwise be the best option available — free PlanetScope (3.7 m) *and* SkySat (0.65 m) for non-commercial research. Restricted to ESA Member States, EC Member States, and China via Dragon. |
| **ISRO Cartosat sub-metre** | **Not free to non-government entities.** [X] Under the Indian Space Policy 2023, data finer than 5 m is free only to Government Entities; NGEs purchase commercially via NSIL. |
| **Planet Education & Research Basic** | **Applied for, non-publishable.** [X] Free, 3,000 km²/month, PlanetScope ~3 m — scale is not the constraint (a 15-city expansion is one-eighth of one month's quota). The terms are: non-commercial only, and **raw imagery cannot be made publicly accessible**. So imagery annotated under it cannot be published as half of an open benchmark — which would be a stronger contribution than another model. Sentinel-2 has no such problem. Tracked as build item 68. |
| **Google Open Buildings road layer** | **Does not exist.** [E] Namespace enumerated via `listAssets`: v1/v2/v3, each holding only `polygons` and `polygons_FeatureView`. Sirko et al. §7 states directly that road detection metrics are not reported. The word "road" appears only inside the citation of the paper title. |
| **Multi-temporal sub-pixel shift exploitation** | **Not viable.** [R] Sentinel-2's sun-synchronous orbit gives near-identical repeat geometry, so the shift diversity the technique needs is minimal to absent. What remains is compositing — better SNR, less cloud/shadow noise, genuinely useful — but not resolution recovery. |
| **Commercial VHR (Maxar/Vantor, Airbus, SkySat)** | Fails the systematic-global bar. Legitimate narrow role: a **validation ruler**, which is exactly how Phase 0 used VHR. Vantor Open Data is additionally **disaster-triggered only**, and CC BY-NC. |
| **Overture buildings** | **Not a third opinion.** Overture's own documentation states many buildings derive from Microsoft and Google Open Buildings, explicitly citing the Global South. OSM wins conflation and OSM is ~9% complete in South Asia, so in dense informal fabric it is ML output with a thin OSM veneer. |

**Bottom line, verified across every channel checked:** there is **no new free
sub-10 m source over Dharavi** — which is also the primary AOI, the demo AOI,
and the worst-covered city in the entire training set (zero across
OpenAerialMap, Umbra and Capella). Continued searching has negative expected
value against digitising OSM ground truth for the bounded area that matters.

### OpenAerialMap — audited, and it is a ruler, not a base layer

Audited as a candidate higher-resolution source. It is the best free
centimetre-scale optical archive that exists, and it still cannot be a base
layer.

| | |
|---|---|
| scenes | 21,359 |
| at ≤2 m GSD | **98.2%** |
| **usable coverage of global land** | **~0.03–0.22%** |

Coverage is the whole story. **Dharavi returns zero** — and so do Delhi,
Karachi, Cairo and Khartoum, metro-wide. Of **47 named informal settlements**
tested: **19** have dedicated ≤15 cm imagery (Tier A), **8** have satellite
mosaic only (Tier B), **20** have nothing usable.

**Verdict: validation and calibration reference only, never a base layer.** A
source covering 0.2% of land cannot underpin a globally uniform pipeline; it can
measure one.

**Licensing caution on Tier B.** The Maxar/Vantor mosaics over Kibera, Mukuru,
Ajegunle and Petare likely carry **CC BY-NC** terms under an OSM-scoped waiver.
**Treat Tier B as restricted for model training until verified per scene** — the
waiver's scope is to OSM mapping, which is not the same permission as training a
model on the pixels.

**The recommended use, and it is a good one:** downsample the ~19 Tier A sites'
5 cm orthophotos to 10 m and measure classification error **as a function of
alley width**. That yields an **error budget for the resolution ceiling** —
turning "10 m cannot resolve this" from an argument into a curve. It uses
OpenAerialMap for exactly what it is good for, needs no new data, and is
unblocked today.

---

## Scope boundaries, stated once

More than one discussion has drifted past these. They are limits of what this
architecture claims, not open problems.

1. **The five fractions answer land-cover proportion and imperviousness — and
   nothing else.** Not land-use, not vegetation type, not building condition,
   not anything demographic or administrative. A full urban planning tool needs
   those as separate layers on top. **This is the physical land-cover layer of
   such a system, not the system.**
2. **The sensor limit stands.** Fractions and vector geometry are honest
   accommodations to 10 m, not a resolution fix. If the actual need is
   street-level surface material in informal settlements, 10 m optical cannot
   deliver it — see the ruled-out table for why nothing else free can either.
3. **Gate C closes only in its narrow, research-audience form** (Decision 17,
   via advisor review against D.7). The planner-usefulness question is
   **genuinely open**, disclosed as future work — build item 64 is the protocol,
   written and deliberately unrun. Do not cite Decision 17 as though it settled
   usefulness to planners.
4. **Morphological characterisation is OSM-coverage-dependent.** Formal/informal
   rests on network geometry, so it degrades exactly where OSM is thin — which
   is disproportionately in informal settlements, the target. The failure mode
   is correlated with the use case.
5. **Past provenance is permanently lost.** Everything before the first commit
   is unreproducible. Build item 62 documents the reconstruction; it does not
   recover it. C42 is this same gap reaching the production checkpoint.
6. **No global independent gold set exists.** Confirmed dead end. The held-out
   firewall (item 27) and intra-annotator test-retest (item 32) mitigate
   single-annotator risk; **neither eliminates it**, and test-retest is not
   Cohen's kappa and does not mean the same thing.

---

## Working rules

These are not style preferences. Each exists because breaking it produced a
wrong conclusion at least once.

1. **Never report a merged-taxonomy or reduced-class mIoU against 0.313.** Not
   comparable — collapsing classes raises mIoU by construction.
2. **Do not round a within-±0.056 result up into "it worked."** That is the
   LOCO standard deviation, not a tolerance.
3. **Paired per-fold comparison — Wilcoxon on 11 deltas — never a comparison of
   means.** SE on the mean is 0.017, so anything under ~0.035 is invisible
   unpaired. Harness at `experiments/harness/loco.py`, 18 tests; its validation
   run is deliberately **not yet done**.
4. **Always report per-city and per-class, never just the mean.**
5. **Do not touch `models/production/`.**
6. **Do not flip build-manual statuses for research experiments.** Build items
   and experiments are different ledgers.
7. **Findings go in `04_FINDINGS_LEDGER.md` under NEEDS FATE.** Assigning a
   fate is a human call.
8. **One commit per build-manual item, item number in the subject** — see
   `CONTRIBUTING.md`.

---

## Immediate next action

**The classifier thread has reached a decision point, not a next task.** The
two work items that were live here (port the 5-builder notebook; run fidelity
and comparison) are **done** — the rebuild reproduces (C42), the gate ran to
132/132 folds, and C43 was investigated and closed. What remains is a human
decision and three unrelated blockers.

**1. THE DECISION (human). Targeted annotation, or the architecture pivot?**

The data-volume axis is exhausted (G1) and the construction axis is exhausted
(C43). Two options remain and they are not compatible in the near term:

> **(a) Targeted new annotation on the four lowest-ceiling tiles** — hcmc,
> guatemala, jakarta, nusantara. Not "more patches": *densely* annotated
> multi-class fabric on tiles whose current ceiling is 21–29%, aimed at class
> *mixing* rather than coverage. This is the only lever the measurements leave
> open on the current architecture. It is untested — no gate has been run on
> it, and G1 only rules out more of the *same kind* of data.
>
> **(b) Accept the resolution-limit diagnosis and pivot** to the vector /
> temporal architecture, `05_BUILD_MANUAL.md` items 19–21. This is what
> `01_DIAGNOSIS.md` argues for, and C43 + G1 strengthen it by eliminating the
> two cheapest alternative explanations.

**Neither is signed off. Do not start either without a human decision.** If (a)
is chosen it should be gated the same way Phase 0 gated the original campaign —
a small dense-annotation pilot on one tile, measured before the rest is funded.

**2. Fix C44 before item 21's extraction runs** (engineering, not a decision).
Two of three Overpass endpoints are unreachable and the handler collapses
429/502/503/504 into one `HTTPError`. `diagnose_pure_pixels_paved.py` imports
that same `OVERPASS_URLS` list, so **the impervious endmember extraction — the
highest-risk item in the plan — depends on it.** This is true under either
branch of the decision above.

**Resolved 2026-09-23, no longer open:** the CAAT threshold question and C11
(dropped with the retired pipeline, §RETIRED above); the NEEDS FATE backlog
(cleared — see `04_FINDINGS_LEDGER.md` § *Fates assigned*); item 46
(`primary_tile` removed); the item 21 / Decisions 11-13-14 sign-off, which
**unblocks `unmixing-ceiling-investigation` for merge**; and
`applicability-gating`, merged to `master` at `a98b529`.

**Also open, unscheduled:** merging `unmixing-ceiling-investigation` (now
sign-off-clear), and the `loco.py` harness validation run.
