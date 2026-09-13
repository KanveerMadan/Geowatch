# GeoWatch — Current State

**Where the project actually is, across all branches, as of 2026-09-13.**

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

## BLOCKING — the pipeline is offline

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

Both were filed on `band-mapping-verification` and are untriaged.

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

Ordered. Items 1 and 2 are the live thread; 3 and 4 are blocked on human
decisions and do not move on their own.

**1. Port the 5-builder `water_loco_with_diagnostics` notebook**
(recoverable at `ecfe370`), not `_UPDATED`. It carries
`build_osm_generated_patches`, `build_osm_generated_water_patches`, the
separation loss, and the LOCO loop behind 0.313.

> **Gate before any training.** Recompute class weights from the rebuilt patch
> set using the notebook's own formula. **Pass** = the checkpoint weights above,
> with a total near 1413. If either misses, report and stop — do not train on a
> set that does not reconstruct.
>
> Investigate the `paved_road` over-generation separately, per the stride/tile-
> size suspicion above. If it lands on a data-availability gap, say so plainly.

**2. If the gate passes, two runs, in this order:**
   1. **Fidelity run** — Arm A **with** the separation loss, one fold. This
      exists only to validate the rebuild against 0.313.
   2. **Comparison runs** — all four arms **without** the separation loss,
      uniformly. It targets the exact paved/roofing pair the 6-band arms test,
      so leaving it in would mask the effect. Separating the two runs means
      fidelity and clean comparison do not have to trade against each other.

**3. Decide the CAAT threshold question** (human). The pipeline stays offline
until then. Note that C11 makes both candidate threshold sets wrong, so the
decision is between two known-wrong artifacts, not between right and wrong.

**4. Triage the eight code-fixed findings and the five under NEEDS FATE**
(human). C4, C10, C14, C20, C23, C24, C31, C32; plus C36, C37, C38, C41, C42.

**Also open, unscheduled:** item 46 (remove `primary_tile`), the item 21
sign-off that gates `unmixing-ceiling-investigation`, and the `loco.py`
harness validation run.
