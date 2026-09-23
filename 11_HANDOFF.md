# 11 — Handoff

**Read this first. `10_SESSION_RECORD.md` is the evidence behind it.**

State as of 2026-09-14. Written so a new session can pick up without
re-deriving anything.

---

## 1. Where the project actually is, in five sentences

The classifier gets **LOCO mIoU 0.313** on unseen cities against **0.6159**
within-city. That ~49% drop is normal for the field (47–66% across every model
audited), so this is an unsolved hard problem, not a defect. The bottleneck has
been identified as **data volume**, confirmed three independent ways, and neither
architecture, band count, nor imagery resolution moves it. **The pipeline is
currently offline** on an unrelated blocker (CAAT provenance). The open decision
is whether to commit months to an annotation campaign — and the test that answers
that is **running right now**.

---

## 2. Blocking issues

### 2.1 ~~The pipeline is offline — CAAT~~ ❌ DROPPED 2026-09-23

> **No longer a blocker: the pipeline it blocks is retired.** CAAT is a
> per-class confidence-threshold mechanism for discrete 7-class inference, and
> the fraction architecture has no argmax to threshold. The recalibration
> question, the 45.0 OOD gate re-derivation, and **C11** are all dropped with
> it rather than deprioritised — there is nothing left for them to gate. See
> `08_STATE.md`. The reasoning below is kept only as the record of why
> calibrating on annotator-selected segments fails, which is a lesson the
> fraction validation set must not repeat.

#### Original entry

Item 45's provenance enforcement correctly rejects the deployed
`models/production/caat_thresholds.json` (no `source_checkpoint`; derived from 11
LOCO fold models, not the production checkpoint). Recalibration was run but **not
deployed** — it triples unknown% (19% → 53%) and pushes 9 of 11 cities past the
pre-registered 45.0 OOD gate. Stratified per-city pooling recovers only 10.5 of
the 34pp gap.

**Root cause diagnosed:** the calibration set is drawn from annotator-selected
segments (4.8–68.4% raster coverage), so a 10th-percentile threshold from the
easy fraction over-rejects on the full raster. Stratification can't touch this —
the defect is *within* each city's calibration set.

**Three options, none taken:**
1. Re-derive the 45.0 gate — needs explicit sign-off, since it moves a
   pre-registered threshold after seeing results.
2. Accept that the model genuinely is OOD on most scenes and let the flags stand.
3. Fix the calibration set to sample the full raster — the only route addressing
   the root cause.

**Fix C11 first regardless.** Penalties are applied at inference
(`inference.py:616-624`) but not during calibration, so every threshold set is
measurably wrong until that's resolved. The ledger claims C11 was "deleted with
the penalty"; the penalty is still live. That ledger entry is wrong.

Also: `validate_recalibration.py` judges success by `unknown_pct` alone, so it
would call a threshold-lowering a success. It measures no accuracy or precision.

### 2.2 Item 46 — the last of Part 8

Remove the `primary_tile` field. Fork already decided: remove it, don't build a
basemap. Confirmed no consumer reads it. Also fix the in-code comment claiming
the frontend projection "works unchanged regardless of how many tiles" — false
for the base image.

---

## 3. Branches

| branch | state |
|---|---|
| `master` | has `06`, `07`, `08` docs + 01–05 cross-references (`6844b65`, `ca7fdd5`, `fc07596`) |
| `applicability-gating` | items 40–45, **6 commits, unmerged** |
| `band-mapping-verification` | C41/C42/C43/C44, patch rebuild, harness, all experiments |
| `merged-taxonomy-retrain` | Step 1 only (`5a67b60`), **paused — superseded by the plan below** |
| `unmixing-ceiling-investigation` | item 21, deliberately unmerged, 4 decisions awaiting sign-off |

**Merge `applicability-gating` when convenient.** Six clean commits, each
independently demonstrated pre/post, 369 tests passing. Carrying it unmerged
indefinitely is its own risk.

---

## 4. Findings awaiting human triage

Nine fixed in code but untriaged: **C4, C10, C14, C20, C23, C24, C31, C32** —
all have working fixes on `applicability-gating` and no fate assigned, because
assigning one is a human act by the ledger's own rules.

Four new, all **NEEDS FATE**: **C41** (RGB-only + tile-relative values), **C42**
(two-notebook provenance split), **C43** (0.313 measured on an easier task),
**C44** (dead Overpass endpoints + status codes not logged).

**One still unfiled:** `best_miou` selection in LOCO is selection on the test
set, and the training notebook does exactly this — so **0.313 is a
max-over-epochs-on-test figure.** Needs a C-number. All three of C41, C43 and
this should be cross-referenced: anyone quoting 0.313 needs all three at once.

---

## 5. Decisions made this session

### 5.1 Built and paved are merged. Closed.

Not revisited. At 10 m a 4–5 m road is sub-pixel, and built vs paved sit 1.70°
apart in a 5° cone against a ~0.7° noise floor. Eight pre-registered methods
failed with a measured physical mechanism. **Do not re-litigate this.**

What merging does *not* fix: the merged `impervious_total` still failed to
transfer cross-city in the Phase 0 VHR test (within-city 0.705–0.821, **negative
R²** on an unseen city, at every scale). That is the data-volume problem, and it
is what the annotation plan addresses.

### 5.2 New taxonomy: four classes ❌ RETIRED 2026-09-23

> **Superseded by the five continuous fractions** (Decision 11,
> `02_ARCHITECTURE.md` §3). Retired, not conditional: the fraction output has
> no argmax, so a discrete per-pixel assignment is not something it can
> produce. `09_TAXONOMY_MIGRATION_PLAN.md` §1 records the mapping. The
> migration below was never run and will not be.

`impervious` (buildings + roads + all hardstanding) · `vegetation` · `water` ·
`bare`

**Migration, not re-annotation:**

```
dense_informal_roofing  ─┐
sparse_informal_roofing ─┼─→  impervious
paved_road              ─┘
dense_vegetation        ─┬─→  vegetation   (vegetation_clearing needs inspection —
vegetation_clearing     ─┘                   arguably `bare` under the new rules)
standing_water          ───→  water
active_construction     ───→  DROP (25 patches, genuinely ambiguous, already
                                    excluded from imperviousness on record)
(no source)             ───→  bare — ZERO existing supervision
```

**`impervious` vs `bare` is the new hard boundary**, and it's hydrologically
load-bearing in the opposite direction (concrete sheds, soil absorbs). Kept as a
real class deliberately — treating `bare` as residual reintroduces a known
over-calling bias. **Expect it to be the weakest class; validate it separately.**

**Labelling rules to write before anyone annotates** (build item 63):
dirt road → `bare` · construction site → `bare` if no slab, `impervious` if slab
poured · dry channel → `bare`, wet → `water` · dead vegetation over soil →
`bare` · all roofing materials incl. thatch → `impervious` · genuinely 50/50
mixed pixel → `IGNORE`, never guess · shadow → the surface beneath, or `IGNORE`.

**Caveat carried forward:** the migrated `impervious` class is ~90%
machine-derived (976 of 1,080 annotations are OSM-generated, and OSM centrelines
measure ~45% road / 55% roof at 10 m). Merging absorbs that contamination rather
than fixing it. **Fresh human labels on impervious are a quality upgrade, not
only a quantity one.**

### 5.3 The 12 new cities

**Lima · Kinshasa · Karachi · Medellín · Bogotá · Port-au-Prince · Monrovia ·
Harare · Freetown · Kathmandu · Cairo · Niterói**

8 Tier A (OAM ≤15 cm validation imagery), 1 Tier B, 3 no-OAM. Seven regions. Four
above the existing slope max, three above the existing bare max. Mean `d_nearest`
2.46 vs candidate-pool 2.08.

**Dropped on hard gates:** Amman, Casablanca (zero Open Buildings polygons).

**Three caveats not to bury:**
- **Port-au-Prince is not hillside as specified.** Its AOI is Cité Soleil,
  coastal and flat at 1.52°. It earns its slot on region and hydrology (696
  waterway features, most of any site). Hillside PAP needs a different centre.
- **Bogotá is the one Tier B pick** — CC BY-NC under an OSM-scoped waiver, fine
  for validation but restricted for training and unverified. First to swap.
- **`bare` is not solved by this list.** Only Lima, Cairo and Karachi beat the
  existing max (Cape Town 4.37%). WorldCover and the dry-season BSI screen
  **disagree by an order of magnitude** — Ouagadougou is 1.2% by WorldCover, 65%
  by screen — and which matches annotator judgement is untested.

**Americas take 5 of 12**, forced rather than preferred: every candidate above the
existing slope maximum is American except Amman, which failed the footprint gate.
To reduce the concentration, swap Niterói for Luanda (d 2.19, Africa-C) or
Antananarivo (d 1.83, Tier B) — each costs hillside coverage or validation
imagery.

### 5.4 Sizing

Target **5,000–8,000 patches** (currently 1,414), weighted toward **breadth over
depth** — ~250–350 patches per new city rather than deepening the existing 11.
Don't go below ~150–200 patches/city; below that a city adds variance rather than
signal.

**Cost is the number that should give pause: 15–45 weeks solo for 5,000 patches.**
Three ways to cut it, in order: reduce scope to 3,000 and treat it as a second
learning-curve point; recruit annotators; or spike semi-supervised /
pseudo-labelling on the unlabelled Sentinel-2 archive — ranked highly by the
architecture audit for this exact regime and completely untried.

---

## 6. Running right now

**The learning-curve gate.** 132 folds (4 fractions × 11 folds × 3 seeds) at
3,200 optimizer steps, **~20–22 h**, started 2026-09-14.

**This decides whether the annotation campaign happens at all.** Do not start
annotating until it returns.

Design notes that matter for reading it:
- **Equal optimizer steps, not equal epochs.** Fixed epochs would give the 100%
  point 4× the steps of the 25% point, conflating "more data" with "more
  optimization" in the direction that flatters the expensive answer.
- **1,600 steps was too few and got caught.** It undertrained the 100% point
  (0.3396 vs 0.3764 at 3,200) while the 25% point had already bottomed out (train
  loss 0.04 — memorised). The 25→100% gap read ~0.08 at 1,600 and ~0.11 at
  3,200 — **the small budget understated the slope by about a third, flattening
  the curve toward "stop"**. Restarted at 3,200.
- **Stratified by city and class**, zero of 64 (city, class) cells lost at any
  fraction. Realised fractions: 353 / 707 / 1067 / 1414 patches.
- `run_fold` returns full trajectories, so the 1,600-step curve can be re-derived
  from the 3,200-step run for free.

### How to read the result

| shape at 100% | meaning | action |
|---|---|---|
| still climbing steeply | data-limited, annotation pays | proceed; extrapolate the slope for a target |
| flattening | volume isn't the constraint | **STOP.** Re-plan around label quality/construction (C43) |
| noisy, no trend | the evaluation can't resolve it | fix that before spending weeks labelling |

**Plot against log(n), not n** — learning curves are typically linear in log
data, and a curve that looks flat on a linear axis can be perfectly healthy on a
log one. Insist on both plots.

**Check whether final-epoch, last-5 and best-epoch agree on the shape.** If all
three agree, the reading is robust. If they disagree, the protocol is dominating
and no conclusion should be drawn.

**Expect the 25% point to be low and noisy** — 353 patches may be too few to
train meaningfully. That's the expected shape, not a broken experiment.

**Sobering extrapolation, even in the best case.** If each doubling buys ~+0.055:
2,500 patches → ~0.37; 5,000 → ~0.42; 10,000 → ~0.48; 20,000 → ~0.53. A usable
production segmenter is 0.5–0.7. So even a strong curve says 5,000 patches lands
short of usable, and genuinely usable needs a campaign several times larger than
12 cities. **The gate doesn't just answer "does more data help" — it answers
"how much would you have to commit to," and that number may be larger than you
want.**

### Stopped, preserved

**11-fold LOCO** — killed at 8 of 44 folds, deliberately. Saved to
`results/loco11/`: `partial_run.log`, `partial_results.json`, `STOPPED.md`.
`run_loco_full.py` untouched for a 4-class re-run.

What survived is **provenance, not evidence**: one arm of four (nothing to
pair), 8 of 11 folds with the three missing bracketing both extremes, and the
only surviving statistic is the test-set-selected one. For the record,
0.3238 ± 0.0546 — close to 0.313, but that's unsurprising rather than
confirmatory, since both are the same optimistically-biased statistic computed
the same way.

---

## 7. Sequence from here

```
learning-curve gate                        RETURNED 2026-09-17
   │
   └── FLATTENED ──→ annotation plan STOPPED. Patch construction then
                     investigated to completion (C43) and also failed:
                     four correction arms, all zero-to-negative.
                     ──→ ARCHITECTURE PIVOT. See 08_STATE.md.

resolved 2026-09-23:
   inversion signed off        Decisions 11/13/14 + item 21
   4-class taxonomy            RETIRED (fractions supersede it)
   old 7-class pipeline        RETIRED -> CAAT blocker and C11 DROPPED
   item 46                     DONE (primary_tile removed)
   applicability-gating        MERGED to master (a98b529)
   ledger triage               CLEARED -- NEEDS FATE is empty

the live decision, unsigned:
   (a) targeted dense annotation on the four lowest-ceiling tiles
       (hcmc, guatemala, jakarta, nusantara), gated by a one-tile pilot
   (b) build Part 4 -- items 19-21, the vector/temporal architecture

blocking (a) or (b) either way:
   C44   two of three Overpass endpoints dead, statuses collapsed.
         The impervious endmember extraction imports that same list.
         Fix before item 21's extraction runs.
```

---

## 8. Working rules — carry these forward

- **Never compare a 4-class or merged-taxonomy mIoU against 0.313.** Collapsing
  classes raises mIoU by construction. *(Now mostly historical — the discrete
  taxonomy is retired — but the rule generalises: **never compare a number
  across a change in what is being measured.** It applies unchanged to
  comparing a fraction RMSE against any mIoU.)*
- **`paved` is derived, never measured.** It is `impervious_total − built` and
  must carry its derivation uncertainty everywhere it is reported. Anyone
  presenting it as a measured quantity has reintroduced the error that the
  2026-09-23 inversion exists to correct.
- **Never round a within-±0.056 result up into "it worked."**
- **Paired per-fold comparison always** — Wilcoxon on the 11 deltas, never
  comparing means. SE on the mean is 0.017, so anything under ~0.035 is invisible
  unpaired. Harness: `experiments/harness/loco.py`, 26 tests.
- **Report per-city and per-class, never just the mean.** The Accra result (mean
  −0.0033 while `standing_water` +0.27 and `vegetation_clearing` −0.51) is the
  standing demonstration that the mean is the least informative number available.
- **Print power floors beside thin classes.** `sparse_informal_roofing` appears in
  5 folds and cannot reach p<0.05 regardless of effect size. Without the floor, a
  null reads as evidence of no effect.
- **Holm-Bonferroni across the test family.** 7 classes × 4 arm pairs is 28 tests;
  reporting 28 uncorrected p-values and picking the small ones is how a null
  becomes a finding.
- **Label `best_miou` as test-set-selected wherever it appears.**
- **Don't touch `models/production/`.** Don't flip build-manual statuses for
  research experiments.
- **Findings go to `04_FINDINGS_LEDGER.md` under NEEDS FATE.** Assigning a fate is
  a human call.
- **Update `08_STATE.md` in the same commit as any item that changes its
  content** — same discipline as flipping build-manual statuses. Otherwise a
  handoff this long is needed again in three sessions.
- **Measure before inferring.** Several of this session's costliest wrong turns
  came from applying a plausible published figure or a code comment instead of
  querying the thing directly. The Karachi road density, the Monrovia cloud count
  and the Cairo footprint count all contradicted confident priors.

---

## 9. Scope boundaries, stated once

Not open problems — limits of what this architecture claims.

1. The four classes answer **land-cover proportion and imperviousness only**. Not
   land-use, vegetation type, building condition, or anything demographic. This is
   the physical land-cover layer of an urban planning system, not the system.
2. **The sensor limit stands.** Merging and vector geometry are honest
   accommodations to 10 m, not a resolution fix.
3. **No free, systematic, global sub-10 m source exists.** NICFI dead; Sentinel-1
   ruled out on resolution (IW GRDH is 20.4 × 22.5 m, and a 3 m alley is 15–20×
   below the resolution cell); super-resolution recommended against (hallucination);
   ESA Earthnet India-ineligible; ISRO Cartosat government-only; Planet E&R
   applied-for but non-publishable; OpenAerialMap ~0.1% of global land. **Continued
   searching has negative expected value.**
4. **Gate C closes only in its narrow research-audience form.** Planner
   usefulness is genuinely open, disclosed as future work.
5. **Morphological characterisation is OSM-coverage-dependent**, so it degrades
   exactly where OSM is thin — disproportionately in informal settlements, the
   target. The failure mode is correlated with the use case.
6. **Past provenance is permanently lost.** Everything before the first commit is
   unreproducible.
7. **No global independent gold set exists.** Confirmed dead end.

---

## 10. The honest confidence estimate

**~35–40%** that the annotation campaign gets you to a genuinely usable model.
**~65%** that it produces a measurable improvement worth having.

Direction is right — data volume is the diagnosed bottleneck, and more diverse
data is the standard fix for cross-city generalisation failure. Magnitude is the
uncertainty: 1,414 → 5,000 patches is 3.5×, still 1–2 orders of magnitude below
what published work reporting solid cross-region transfer typically trains on.
Landing at 0.40 — real, measurable, still not production-usable — is entirely
plausible.

What could make it fail outright: the gate flattens (C43 makes this live);
`bare` proves unlearnable at 10 m for the same reason built/paved was; new cities
dilute rather than diversify; annotation consistency degrades across 23 cities and
one annotator over months.

**And the thing to hold onto:** the ~50% within-to-cross-city drop is the field
norm. More data moves you along that curve. It does not take you off it.
