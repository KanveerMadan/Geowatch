# 09 — Taxonomy Migration and Annotation Plan

**Moving from the 7-class taxonomy to a 4-class one, and deciding whether an
annotation campaign is worth running.**

Written 2026-09-14. Companion to `08_STATE.md` (current state), `05_BUILD_MANUAL.md`
(item list), `04_FINDINGS_LEDGER.md` (C41/C42/C45 qualify everything below).

---

> ## ⛔ STATUS 2026-09-18 — THE GATE RAN. PHASE 1 IS CLOSED.
>
> **§3's gate returned on 2026-09-17 and the answer is "flattening": stop.**
> 132/132 folds. A 4× increase in data moved final-epoch LOCO mIoU by
> **+0.0075** against a ±0.035 detection threshold; slope **+0.0029 per
> doubling**, ~19× below the +0.055 this document's §4.1 sizing assumed.
> Full numbers: `04_FINDINGS_LEDGER.md` → **G1**.
>
> **§4 (Phase 1 — annotation campaign) does not proceed as written.** Its
> sizing, breadth-over-depth rule and cost estimate were all derived from a
> slope that does not exist. Read §4 as *record*, not as *plan*.
>
> **§3.2 predicted this outcome and named the follow-up** — "the bottleneck is
> label quality or construction, not volume... re-annotate a small set densely
> and correctly rather than annotate a large set the same way." **The first
> half of that follow-up has now been tested and failed.** Four
> patch-construction corrections were built and measured (C43, arms B/C/D/E),
> including a full native multi-class rebuild that took single-class from
> 85.4% to 47.7% — it was **significantly worse**, −0.1041 mIoU, p=0.013,
> because removing bbox magnification cost 31% of the supervised pixel budget.
>
> **So construction is eliminated too, and what §3.2 called "re-annotate a
> small set densely" is the only surviving form of the idea.** See §8.
>
> **§§1–2 (the taxonomy and the migration) are RETIRED as of 2026-09-23** —
> not by the gate, but by the architecture pivot. The 7→4 discrete merge is
> superseded by the five continuous fractions; see §1. Item 30 (logit
> adjustment), the last build item that assumed a discrete argmax anywhere,
> is **deleted** rather than held conditional.
>
> **This document is now wholly historical.** It is retained because the gate
> reasoning in §3 is reusable and because §8 records what survives.

---

---

## 0. The decision this plan serves

The classifier's failure is cross-city generalisation: LOCO mIoU 0.313 against
a within-city 0.6159. Three independent lines of evidence now point at **data
volume** as the binding constraint rather than architecture, band count, or
imagery resolution:

- Six bands add ≈0 over RGB at peak (+0.0002), measured three times independently.
- Six-band arms reach their generalisation peak at epoch 5–16 and then decay
  (−0.117 to −0.137), where RGB peaks at 24–37 and holds. More input channels
  overfit 1,272 patches faster. That is a capacity-versus-data statement.
- The architecture audit found the entire measured gap between the best
  geospatial foundation model and a from-scratch U-Net is 0.77–2.0 mIoU points
  — below this project's detection threshold of ±0.035.

So the lever with headroom is more supervision. This plan sizes that, and gates
it behind a cheap test that could invalidate the whole thing.

**It does not attempt to recover built-vs-paved.** That is closed: merged into
one impervious class, per Decision on record. Nothing below revisits it.

---

## 1. The new taxonomy ❌ RETIRED 2026-09-23

> **RETIRED, not conditional.** This 4-class *discrete* taxonomy is superseded
> by the **five continuous fractions** of Decision 11 (`02_ARCHITECTURE.md` §3).
> Those fractions are not a finer-grained version of this scheme — they are a
> different kind of output. A fraction vector has no argmax and assigns no
> pixel to one class, so "every pixel gets exactly one, or `IGNORE`" is not a
> rule the new architecture can express.
>
> **What carried over, and what did not:**
>
> | this scheme | fraction architecture |
> |---|---|
> | `impervious` (one class) | `impervious_total` — **measured spectrally**, the quantity the flood model consumes |
> | `vegetation`, `water`, `bare` | the same three, as continuous fractions from a global library |
> | — | `built` (footprint-derived) and `paved` (derived by difference) |
> | `IGNORE` | replaced by Decision 14's separated observability fields |
>
> The §1.1 warning that `impervious`-vs-`bare` would be the hardest boundary
> was **right, and is now handled structurally rather than by classification**:
> `bare` is the residual, so the impervious/bare confusion lands where it is
> visible instead of being baked into a hard class assignment.
>
> Sections 1–2 are kept as the record of the migration that was planned.
> **Do not build against them.**

Four classes. Every pixel gets exactly one, or `IGNORE`.

| class | includes | excludes | hydrological meaning |
|---|---|---|---|
| `impervious` | buildings, roofs of any material, roads, paved surfaces, concrete, asphalt, hardstanding, paved courtyards | dirt roads, unpaved alleys | sheds water |
| `vegetation` | tree canopy, grass, crops, shrubs, any green cover | dry/dead vegetation over bare soil → `bare` | absorbs, intercepts |
| `water` | standing water, rivers, ponds, tidal flats when wet, drainage channels holding water | dry channel beds → `bare` | surface water |
| `bare` | exposed soil, dirt, sand, gravel, unpaved ground, dirt roads, cleared land | anything under construction with a slab poured → `impervious` | absorbs |

### 1.1 The boundary that will hurt, and the rule for it

`impervious` vs `bare` is now the hardest boundary, and it is the same class of
problem built-vs-paved was: at 10 m, dry bare earth and weathered concrete are
both grey-brown, non-vegetated, and spectrally close.

**This boundary was chosen deliberately, not inherited.** Unlike built-vs-paved,
it is hydrologically load-bearing in the opposite direction — concrete sheds,
soil absorbs — so collapsing it (treating `bare` as residual) reintroduces the
known over-calling bias that Option C was flagged for. Keeping it as a real
class means the error is measurable rather than baked in.

**Expect `bare` to be the weakest class. Validate it separately and report its
IoU alongside the mean, never folded into it.**

### 1.2 Labelling rules that must be written before anyone annotates

These are the cases that will otherwise be labelled inconsistently across cities,
which is precisely the failure that makes cross-city transfer worse rather than
better.

1. **Dirt road → `bare`.** Permeable. Not impervious, regardless of how road-like
   it looks.
2. **Construction site → `bare` if no slab, `impervious` if a slab or foundation
   is poured.** The old `active_construction` class was excluded from
   imperviousness precisely because it is ambiguous; this rule resolves the
   ambiguity by observable state rather than by category.
3. **Dry drainage channel → `bare`.** Wet → `water`.
4. **Dry/dead vegetation over soil → `bare`.** The class is vegetation *cover*,
   not vegetation *history*.
5. **Metal, tile, thatch, tarpaulin, corrugated roofing → all `impervious`.**
   Material does not matter; the hydrological behaviour does. Thatch is the one
   genuine edge case — call it `impervious`, and record the call.
6. **Mixed pixel at any boundary → label the dominant surface, or `IGNORE` if
   genuinely 50/50.** Do not guess. `IGNORE` is cheap; a wrong label is not.
7. **Shadow → label the surface you believe is under it, or `IGNORE` if
   unreadable.** Do not create a shadow class.

Write these into `LABELING_GUIDE.md` (build item 63) *before* annotation starts,
not after. Item 63 already exists in the build manual for exactly this.

---

## 2. Migrate, do not re-annotate

**Do not delete the existing 7-class labels.** They map into the new taxonomy
without loss, and re-annotating 11 cities from scratch costs weeks and buys
nothing the mapping does not already give.

```
dense_informal_roofing   ─┐
sparse_informal_roofing  ─┼─→  impervious
paved_road               ─┘

dense_vegetation         ─┐
vegetation_clearing      ─┴─→  vegetation      (see caveat below)

standing_water           ───→  water

active_construction      ───→  DROP (25 patches; genuinely ambiguous,
                                already excluded from imperviousness on record)

(no source)              ───→  bare  — this class has NO existing supervision
```

### 2.1 Three things the migration does not fix, stated plainly

1. **`bare` starts from zero.** No existing class maps to it. Every `bare` label
   must be annotated fresh, in both old and new cities. This is the single
   largest annotation cost in the plan.
2. **`vegetation_clearing` is not obviously `vegetation`.** By the rules in §1.2
   it is arguably `bare` — cleared land with vegetation removed. Inspect a sample
   of its 70 patches before deciding; splitting it by inspection is better than
   assuming either way. Note it appears in only 8 of 11 cities and on Accra a
   single patch drove a −0.51 class delta, so it is a high-variance class however
   it is mapped.
3. **The merged `impervious` class is ~90% machine-derived.** 976 of 1,080
   impervious-mapping annotations are OSM-generated, and C29 measured OSM
   centrelines at roughly 45% road / 55% roof at 10 m. Merging *absorbs* that
   contamination rather than fixing it — which is fine for a merged class, and is
   in fact the strongest argument for the merge. But it means the migrated
   impervious supervision is mostly automated, not human. **Fresh human labels on
   impervious are a quality upgrade, not only a quantity one.**

---

## 3. Phase 0 — the gate (2–3 days, before any annotation)

**Do not start annotating until this returns.** It is a few hours of compute
against weeks of labelling, and it is the only cheap test of whether the entire
premise holds.

### 3.1 Learning-curve test

Train on 25%, 50%, 75%, 100% of the existing (migrated, 4-class) patch set.
Full LOCO at each fraction. Plot mIoU against patch count.

- Subsample **by patch, stratified by city and class**, not randomly — a random
  25% draw can drop a thin class from a city entirely and the curve then measures
  class absence rather than data volume.
- Three seeds per point. The spread matters more than the mean; a curve drawn
  through single-seed points at this noise level is not interpretable.
- Fixed epoch budget, no early stopping, and report final-epoch, last-5-average,
  and best-epoch separately — best-epoch in LOCO is selection on the test set
  (this is how 0.313 itself was produced).

**Read it like this:**

| curve shape at 100% | meaning | action |
|---|---|---|
| still climbing steeply | data-limited, annotation will pay | proceed to §4, extrapolate the slope for a target |
| flattening | something else binds | **stop.** Annotation will not rescue it. Re-plan. |
| noisy, no clear trend | the evaluation cannot resolve it | fix evaluation before spending weeks on labels |

### 3.2 What "flattening" would mean

It would mean the bottleneck is label *quality* or *construction*, not volume —
consistent with C43 (85.4% of training patches are single-class; inference
classifies every pixel). In that case the fix is different: re-annotate a small
set densely and correctly rather than annotate a large set the same way.

**That outcome is not a failure of this plan. It is the plan working — a
two-day test that prevents six weeks of wasted annotation.**

> **This is what happened.** The curve flattened, the campaign was stopped, and
> the "label quality or construction" hypothesis this section names was then
> tested directly. **Construction was eliminated** — see §8 and C43. Quality,
> in the specific sense of *denser multi-class annotation on the lowest-ceiling
> tiles*, is the only branch left standing.

---

## 4. Phase 1 — annotation campaign (only if Phase 0 says go)

> **⛔ Phase 0 said stop. This section did not trigger.** Retained as the record
> of what was planned and costed, so the decision not to run it is auditable.
> Its sizing assumed a slope of +0.055 per doubling; the measured slope is
> +0.0029. Do not cost new work from these numbers.

### 4.1 Sizing

Current: ~1,272 patches, ~485k labelled pixels, 11 cities (~116 patches/city).

**Target: 5,000–8,000 patches.** Reasoning, stated honestly as reasoning and not
as a derived number:

- 4–6× current. The smallest jump likely to produce a change detectable against
  a ±0.035 threshold.
- Remote-sensing segmentation work reporting solid cross-region transfer
  typically trains on 10k–100k patches. This target closes part of a 1–2 order-
  of-magnitude gap, not all of it.
- It is achievable by one person in a bounded time. 50k is not.

**Phase 0's slope should override this number.** If the curve is steep, aim
higher; if shallow but positive, a smaller target may be the right stopping point.

### 4.2 Breadth over depth

The failure is *cross-city* transfer specifically, so morphological diversity
buys more than depth in cities already covered.

**Prefer ~22–25 cities at ~250–350 patches each over 11 cities at ~700.**

Selection criteria for new cities, in priority order:

1. **Morphological difference from the existing 11** — South Asian and North
   African dense fabric are the notable gaps (the existing set skews East/West
   African and Southeast Asian).
2. **OSM coverage adequate for the vector layers** the rest of the pipeline needs.
3. **Cloud-free Sentinel-2 availability** in a consistent season.
4. **A validation reference exists if possible** — the ~19 OpenAerialMap Tier A
   sites are the strongest candidates here, since they give centimetre-scale
   ground truth for the same footprint.

### 4.3 Annotation protocol

- **Human labels on `impervious` and `bare` are the priority.** `vegetation` and
  `water` already have high ceilings (0.974 / 0.965) and existing supervision;
  the marginal label there is worth less.
- **Do not extend the OSM-centreline shortcut to new cities.** It produced the
  45/55 contamination. Use it, if at all, only as a pre-annotation hint a human
  corrects — never as a label source.
- **Annotate patches that resemble what inference sees.** Per C43, the existing
  set is 85.4% single-class, bbox-cropped and resized. Inference classifies every
  pixel at native resolution with no crop or resize. New patches should be
  native-resolution, multi-class windows — otherwise you scale up the same task
  mismatch.
- **Hold out a firewall set from the start** (build item 27). Annotate it, seal
  it, and do not look at it until the end. Without this, every tuning decision
  leaks.
- **Re-annotate a 5% sample blind, later** (build item 32, intra-annotator
  test-retest). Single-annotator risk is real and this is the available
  mitigation. It is not Cohen's kappa and should not be reported as though it is.

### 4.4 Cost estimate

At a realistic 5–15 minutes per native-resolution multi-class patch (slower than
single-class segment labelling, because every pixel in the window needs a call):

| target | patches to add | hours | weeks at 20h/wk |
|---|---:|---:|---:|
| 5,000 | ~3,700 | 300–900 | 15–45 |
| 8,000 | ~6,700 | 550–1,650 | 28–83 |

**This is the number that should give you pause.** It is months of work for one
person. Three ways to reduce it, in order of how much they cost elsewhere:

1. **Reduce scope to 3,000 patches** and treat it as a second learning-curve
   point rather than a final dataset. Cheapest, and it keeps the decision
   reversible.
2. **Recruit annotators.** Multiplies throughput, introduces inter-annotator
   variance — which at least becomes measurable, unlike the current
   single-annotator risk.
3. **Semi-supervised / pseudo-labelling on the abundant unlabelled Sentinel-2
   archive.** The architecture audit ranked this highly for small-data regimes
   and it is untried here. Worth a spike before committing to months of manual
   work.

---

## 5. Phase 2 — re-baseline

A 4-class mIoU **is not comparable to 0.313**. Collapsing seven classes into
four raises mIoU by construction — the confusions that cost IoU stop being
counted as errors.

So:

1. Establish a **fresh 4-class baseline on the migrated existing data**, before
   any new annotation lands. This is the number everything afterwards compares
   against.
2. Report per-class IoU always, never the mean alone. The Accra result — the
   7-class mean moving −0.0033 while `standing_water` moved +0.27 and
   `vegetation_clearing` −0.51 — is the standing demonstration that the mean is
   the least informative number available.
3. Use the paired harness (`experiments/harness/loco.py`): Wilcoxon on the 11
   paired per-fold deltas, per-city and per-class tables, power floors printed
   beside any thin class, Holm-Bonferroni across the test family.
4. **In the write-up, state the task change explicitly**: "we changed the task
   because the original task is not learnable at 10 m", supported by the spectral
   separability analysis and the before/after confusion matrix. Do not present a
   4-class number as an improvement on a 7-class one.

---

## 6. Sequence, and what blocks what

```
Phase 0   learning-curve gate                     2–3 days    ← DO THIS FIRST
   │
   ├── flattens ──→ STOP. Re-plan around label quality, not volume.
   │
   └── climbs ──→ Phase 1a  taxonomy + labelling guide       2–3 days
                     │                                   (build item 63)
                     ▼
                  Phase 1b  migrate existing labels          2–3 days
                     │      + inspect vegetation_clearing
                     ▼
                  Phase 1c  re-baseline on migrated data     1 day
                     │      (this is the new reference number)
                     ▼
                  Phase 1d  annotation campaign              weeks–months
                     │      breadth over depth, firewall sealed first
                     ▼
                  Phase 2   re-evaluate, paired, per-class   2 days
```

**Independent of all of the above, still outstanding:** the CAAT recalibration
blocker keeps the pipeline offline, and C11 (penalties applied at inference but
not during calibration) invalidates any threshold set until fixed. Neither is
touched by this plan, and the pipeline cannot run until they are resolved.

---

## 7. Risks, named

1. **Phase 0 says flatten.** Most likely single outcome worth preparing for.
   Response is in §3.2 — it redirects rather than ends the work.
2. **`bare` turns out unlearnable at 10 m**, for the same reason built-vs-paved
   was. Plausible. Mitigation: validate `bare` separately from the start; if its
   IoU is near zero across folds, fall back to a 3-class taxonomy and accept the
   documented over-calling bias rather than pretend the class works.
3. **The annotation cost is real and months long.** §4.4 option 1 (3,000-patch
   scope, treated as a second curve point) keeps this reversible.
4. **New cities dilute rather than help** if their morphology is too similar to
   the existing 11. Mitigated by §4.2's selection criteria, but only measurable
   after the fact — check by re-running the learning curve with new cities
   included and seeing whether the slope holds.
5. **Task mismatch is scaled up rather than fixed** if new patches are built the
   old way. §4.3 addresses this directly and it is the easiest of these risks to
   get wrong by accident.


---

## 8. What is left after the gate (added 2026-09-18)

**Both cheap explanations are now eliminated by measurement.** Data volume:
**G1** (flat curve, 132/132 folds). Patch construction: **C43** (four
corrections built, all failed; the full native multi-class rebuild was
significantly worse). What remains is annotation *density*, and the choice
between pursuing it and accepting the resolution-limit diagnosis.

### 8.1 Why "annotate more" and "annotate better-cropped" both failed

85.4% of training patches are single-class. Decomposed over 633,571 native
64×64 window positions on the 11 canvases, that splits into:

- **≈21.9 pp construction artifact** — 309 patches, recoverable by re-cropping
  existing annotation. **Arm E recovered it** (85.4% → 47.7% single-class) and
  mIoU fell 0.104. Recovering it costs 31% of the supervised pixel budget,
  because a segment at native scale occupies far fewer pixels than one
  magnified to fill the frame. **This route is closed.**
- **≈63.6 pp genuine scarcity** — 899 patches. **81.3% of the imaged area
  carries no label at all**, and the native-window pool is only 703 usable
  windows at stride 32 across all 11 tiles.

### 8.2 If annotation is pursued, this is the shape it must take

Not the §4 campaign. The measurements say breadth is worthless and coverage is
not the variable — **class mixing is**. jakarta is 68.4% labelled and still has
a 28.5% multi-class ceiling, because 90.8% of its labelled area is one class.

**Target the four lowest-ceiling tiles:**

| tile | labelled | multi-class ceiling |
|---|---:|---:|
| hcmc | 4.8% | 21.3% |
| guatemala | 5.1% | 22.8% |
| jakarta | 68.4% | 28.5% |
| nusantara | 7.1% | 29.4% |

**Dense contiguous multi-class fabric**, annotated so that adjacent classes and
their boundaries are labelled — not more isolated segments. Training scores
boundary decisions on **0.14% of its pixels** today while inference argmaxes
every pixel; that is the gap new annotation would have to close.

**Gate it the same way.** G1 rules out more of the *same kind* of data; it does
not test densely-annotated data, which has never existed here. So: **a
single-tile dense-annotation pilot, measured before the rest is funded** —
same discipline as Phase 0, and for the same reason.

### 8.3 The alternative, which has the stronger prior

**Accept the resolution-limit diagnosis and pivot to the vector / temporal
architecture** (`05_BUILD_MANUAL.md` items 19–21), which is what
`01_DIAGNOSIS.md` argues for. G1 and C43 strengthen that argument rather than
weakening it: the two cheapest competing explanations — not enough data, badly
cropped data — have now been measured and eliminated, which is exactly the
evidence a resolution-ceiling claim needs.

**Neither 8.2 nor 8.3 is signed off.** This is the live decision; see
`08_STATE.md` → *Immediate next action*.
