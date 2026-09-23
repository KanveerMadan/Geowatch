# GeoWatch — Findings Ledger

**Every finding, its evidence, and its fate under the new architecture.**

This is the triage index. Before building anything, check here — roughly a third
of the original findings are **deleted** by the architecture change rather than
fixed, and building them would be wasted work.

Companion documents: `01_DIAGNOSIS.md`, `02_ARCHITECTURE.md`, `03_EVIDENCE.md`,
`05_BUILD_MANUAL.md`; `06_UNMIXING_CEILING.md` *(unmerged)* and `07_ITEM_21.md`
for the unmixing ceiling; `08_STATE.md` for current state.

**This document is not authoritative on findings closed by unmerged work.**
Eight findings — C4, C10, C14, C20, C23, C24, C31, C32 — have working fixes on
`applicability-gating` and still carry no fate here, because assigning one is a
human triage act by this document's own rules. `08_STATE.md` lists them.

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
| CLOSED | 8 | 5 during Part 1; C34 and C35 added by item 47; C43 closed by the patch-construction investigation |
| REFUTED | 2 | Disproven |
| DELETED | 13 | Architecture change removes the code |
| CONDITIONAL (resolved → DELETED) | 4 | Gated on Decision 12; now resolved |
| SURVIVES | 22 | The irreducible cluster — real work (C40 added by the pre-push audit) |
| NEEDS FATE | 7 | C36–C38, plus C41/C42 from the reproduction work, C44 from the city-selection measurement, and C45 from the patch-construction investigation |

**This is the authoritative list for the "irreducible cluster."**
`02_ARCHITECTURE.md` §8 references this section by pointer rather than
duplicating the enumeration, specifically so the two documents cannot drift
out of agreement with each other the way they previously did.

---

## GATE RESULTS

*Not findings. Pre-registered tests whose outcome changes what gets built.
Recorded here because this is where the project looks for "what was measured
and what follows from it".*

### G1 — The learning-curve gate: more of this data does not help [E] ⛔ STOP

`09_TAXONOMY_MIGRATION_PLAN.md` §3 gated the annotation campaign behind one
cheap test — train on 25 / 50 / 75 / 100% of the existing patch set, full LOCO
at each fraction, plot mIoU against patch count. **The test returned, and it
says stop.**

**132 of 132 folds completed** — 11-fold LOCO × 4 fractions × 3 seeds
(1337, 7, 2024), stratified by (city, class), **3,200 optimizer steps at every
point** so the curve measures data and not optimisation. Seed spread is the
±, taken across the three per-seed LOCO means.

| fraction | patches | final | last5 | best\* |
|---:|---:|---|---|---|
| 25% | 353 | 0.2492 ±0.0278 | 0.2519 ±0.0267 | 0.3454 ±0.0289 |
| 50% | 707 | 0.2489 ±0.0036 | 0.2506 ±0.0020 | 0.3292 ±0.0226 |
| 75% | 1067 | 0.2497 ±0.0183 | 0.2521 ±0.0184 | 0.3243 ±0.0079 |
| **100%** | **1414** | **0.2567 ±0.0014** | **0.2566 ±0.0037** | **0.3118 ±0.0047** |

\* `best_ON_TEST` is selected on the test set and optimistically biased. It is
reported because **this is the statistic that produced 0.313**.

**All three statistics agree the curve is flat.**

| statistic | Δ(100% − 25%) | slope per doubling |
|---|---:|---:|
| final | **+0.0075** | +0.0029 |
| last5 | +0.0048 | +0.0019 |
| best\* | **−0.0335** | −0.0157 |

A 4× increase in data moves final-epoch mIoU by **+0.0075** against this
project's pre-registered detection threshold of **±0.035**. The measured slope
is **+0.0029 per doubling**, roughly **19× smaller** than the +0.055 per
doubling the annotation plan's sizing assumed. Extrapolating the measured
slope, mIoU 0.35 needs ~5.6 × 10¹² patches and 0.50 needs ~1.5 × 10²⁸. **The
data-volume axis is exhausted.**

**The harness is measuring correctly.** The 100% / `best_ON_TEST` point is
**0.3118 ±0.0047** against the shipped checkpoint's **0.313** — an independent
11-fold reproduction of the headline number, from a rebuilt patch set, landing
within 0.002. The flat curve is real, not an artifact of a broken harness.

**`best_ON_TEST` falls as data rises** (0.3454 → 0.3118). More data makes
test-set selection *worse*, which is what should happen when the selection
bias is being diluted rather than a real gain being found — further evidence
there is no real gain underneath.

**Per-class, the gains are in the classes that were already easy** (last-5,
mean over 11 cities × 3 seeds):

| class | 25% | 100% | Δ | slope/dbl |
|---|---:|---:|---:|---:|
| dense_vegetation | 0.381 | 0.442 | +0.060 | +0.0262 |
| active_construction | 0.043 | 0.085 | +0.042 | +0.0165 |
| paved_road | 0.477 | 0.506 | +0.029 | +0.0142 |
| vegetation_clearing | 0.181 | 0.193 | +0.011 | +0.0071 |
| sparse_informal_roofing | 0.040 | 0.030 | −0.010 | +0.0012 |
| standing_water | 0.311 | 0.299 | −0.012 | −0.0073 |
| dense_informal_roofing | 0.227 | 0.195 | −0.032 | −0.0170 |

**None of these per-class movements is significant.** Paired by (city, seed),
n=33: `dense_informal_roofing` p=0.47, `dense_vegetation` p=0.15,
`active_construction` p=0.17. Per-fold standard deviation is 0.12–0.26 against
deltas of 0.03–0.06, and `dense_informal_roofing` is *better* in 18 of 33
pairs despite its negative mean. The apparent "roofing regresses, vegetation
improves" split does not survive pairing and must not be built on.
`sparse_informal_roofing` is 0.0 in 23 of 31 folds — it is effectively never
predicted.

**Verdict: STOP the annotation campaign as originally scoped.** This is the
"flattening" branch of the plan's own decision table, and per §3.2 that is the
plan working, not failing — a gate that cost hours of compute instead of weeks
of labelling. What follows is **not** "annotate more of the same"; see **C43**
for what was tested instead, and §6 of this entry's companion note in
`09_TAXONOMY_MIGRATION_PLAN.md` for what is left.

*Raw: `experiments/band_reflectance/results/learning_curve/raw.json` (132
folds, full trajectories). Runner: `experiments/band_reflectance/learning_curve.py`.
Budget justified by `budget_probe.py` — 1,600 steps undertrains the 100% point
by 0.0368, which would have biased the slope upward.*

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
(`GET /api/runs/{run_id}`, read not write). **It did receive the same treatment**
— scheduled as `05_BUILD_MANUAL.md` item 47, built, and now CLOSED below. Its
entry also records the empirical result that this one could not: C16's traversal
was demonstrated by path arithmetic, while C34's was measured against the live
router, which turned out to refuse the POSIX payloads before the handler ever
ran. Same bug class, very different reachability.

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

### C34 — `GET /api/runs/{run_id}` builds a path from an unvalidated parameter [S] ✅ FIXED
`api.py` constructed `Path(f"data/pipeline_runs/{run_id}/result.json")` from an
unvalidated path parameter. Same bug class as C16, a **read** sink rather than a
write sink, so the impact shape is disclosure rather than directory creation.

**Fix applied** (`05_BUILD_MANUAL.md` item 47): whitelist validation
`[a-z0-9_-]{1,128}` with `re.fullmatch`, `HTTPException(400)`,
reject-not-sanitize, placed before any path is constructed and outside any try
block. Backed by `resolve_within_data_root()`, which resolves the full candidate
path and re-checks containment, so `..`, absolute components and symlinks are
normalised away before comparison rather than pattern-matched beforehand. 115
tests; verified against the unpatched endpoint first — **58 failed, 57 passed.**

**What the testing established — this entry previously read "likely weaker, but
untested", and that guess was both confirmed and, in an important respect,
wrong.** Measured against the unpatched endpoint by recording the exact string
the handler passed to `Path()`:

- **POSIX traversal never reached the handler.** `../`, `../../../etc/passwd`,
  `%2e%2e%2f`, double-encoded variants and `/etc/passwd` were all normalised or
  rejected by **Starlette before routing** — the handler did not run. For this
  class the "likely weaker" guess was right, and C34 was **not exploitable**.
- **Backslash variants DID reach the handler, with the string intact.** `..\`,
  `..\..\windows\system32` and `C:\Windows\Temp` arrived unmodified, producing
  e.g. `Path('data/pipeline_runs/..\..\windows\system32/result.json')`. They were
  inert **only because POSIX treats a backslash as an ordinary filename
  character.** On Windows they are real traversal. Nothing in the code was
  platform-guarded.
- `x/../<real_run_id>` returned 200, but *not* because traversal succeeded: the
  URL normalised to `/api/runs/<real_run_id>` before routing and the handler
  received the clean id. An ordinary request, not an escape.

**The correction that matters more than the fix: the pre-fix mitigation was
incidental.** What protected this endpoint was Starlette's URL normalisation
plus the host operating system's filename conventions — **neither of which is a
control this codebase owns, tests, or would be told about if it changed.** The
same code deployed on Windows was exploitable. "It didn't reproduce" was
therefore never evidence the sink was safe; it was evidence that two external
accidents happened to line up. This is the same shape as Decision 15's rule
about absence-of-observation: the mechanism was real and understood, and only
the triggering conditions were absent.

*Carry forward: when a finding does not reproduce, establish **which layer**
refused it before concluding anything. Here the router's 404
(`{"detail":"Not Found"}`) and the handler's 404 (`Run <id> not found.`) are
visually identical in a status code and mean opposite things.*

### C35 — `WATCHED_AOIS` bypasses the API boundary [E] ✅ FIXED
The scheduler called `run_pipeline` with no validation. All three configured
labels (`dharavi`, `nairobi`, `jakarta`) passed the whitelist, so there was **no
current exposure** — but nothing *enforced* that, so a future edit would have
reached path construction unimpeded, under the scheduler's privileges.

**The important implication, unchanged and now enforced: "validated at the API
boundary" is not the same as "validated everywhere."**

**Fix applied** (item 47, same pass as C34): the whitelist is now a single
predicate, `_matches_label_whitelist()`, called by **both** the HTTP boundary
(raising `HTTPException(400)`) and an import-time assertion over `WATCHED_AOIS`
(raising `RuntimeError`, because an `HTTPException` outside a request is
meaningless). One predicate, two callers — so the two boundaries cannot drift
about what a valid label is, which is the divergence that let this exist.

Startup failure rather than a warning: a mistyped watched label should stop the
service, not silently drop one city's refresh and leave a five-day gap nobody
notices. The scheduler loop re-checks at call time as well, because
`WATCHED_AOIS` is a mutable module-level list and the import-time assertion
proves only that the *configured* value was good; a bad entry is skipped loudly
so one typo cannot stop the other cities refreshing. `get_latest_run()` is
validated too — traversal is not reachable through its `startswith()` directory
filter today, but *"not reachable through the current implementation"* is
precisely the reasoning that left this finding open in the first place.

---

### C43 — 0.313 was measured on a materially easier task than the pipeline runs [E] ✅ CLOSED

*Filed during the training reproduction; **closed 2026-09-18** after the
structural claim was verified, four candidate fixes were built and measured,
and the single-class rate was decomposed into its fixable and unfixable parts.
Closed as **investigated and understood**, not as repaired — see "Why this
closes" at the end.*

**The headline LOCO number does not describe dense multi-class per-pixel
segmentation.** It describes a set of mostly single-class, mostly pre-cropped
patches, and the gap between that task and the one the pipeline performs was
never stated anywhere the number is quoted.

#### 1. What a production training patch actually is

Measured on the reconstructed 1,414-patch set (the 5-builder rebuild that
reproduces the checkpoint's class weights — see **C42**):

| source | n | labelled px | single-class | what it is |
|---|---:|---:|---:|---|
| `sam` | 268 | 72.1% | **100%** | one annotated segment, bbox-cropped and resized to 64×64 |
| `osm` | 275 | 25.6% | **100%** | road centreline buffered 2 px; everything else IGNORE |
| `osm_generated` | 274 | 24.4% | **100%** | one road's real geometry, bbox-cropped and resized |
| `osm_generated_water` | 95 | 43.7% | **100%** | one water body, same construction |
| `sliding_window` | 502 | 29.4% | 58.8% | window off the label canvas, keyed by dominant label |
| **all** | **1414** | **36.7%** | **85.4%** | |

**85.4% of training patches contain exactly one class** (1,207 of 1,414; the
rest: 165 two-class, 37 three-class, 3 four-class, 2 five-class). Four of the
five builders are single-class *by construction*.

Two further numbers make the point sharper than the 85.4% does:

- **63.3% of all training pixels are IGNORE** — 3,664,219 of 5,791,744. Loss
  is computed on 36.7% of the tensor.
- **0.14% of scored pixels sit on a class-to-class boundary** — 2,874 of
  2,127,525. That is the entire boundary-decision signal in the loss. At
  inference every pixel is argmaxed, boundary or not. The neighbouring-class
  decisions that produce the `paved_road`/`dense_informal_roofing` confusion
  the project has been chasing are the ones training never scored.

Class weights compound it: they are computed from each patch's single `label`
string, so they weight by *patch* count, not supervised pixels. `paved_road`
is 41.6% of patches but 29.9% of supervised pixels; `standing_water` is 14.3%
of patches and 20.6% of pixels.

#### 2. The scale mismatch

**45.0% of patches (637/1,414) are `crop(bbox).resize((64,64), BILINEAR)`.**
The rest are native 64×64 windows.

| | min | p25 | median | p75 | p95 | max |
|---|---:|---:|---:|---:|---:|---:|
| crop side (px) | 1 | 10 | **16** | 28 | 79 | 511 |
| crop/64 | 0.061 | 0.16 | 0.24 | 0.42 | 1.10 | 7.46 |

The median crop is ~16×16 px magnified 4× to fill 64×64; `crop/64` spans
**123×** end to end, and **93.1% of resize patches are upsampled**. Forcing a
rectangular bbox into a square also stretches aspect: median 1.40×, p90 3.50×,
max 36×; 25.1% are stretched over 2×, 12.4% over 3×.

Converting to ground units with each tile's own AOI (9.0–21.4 m/px):

| one 64×64 model input covers | min | median | max |
|---|---:|---:|---:|
| train, resize builders (637) | 37 m | **174 m** | 7225 m |
| train, native windows (777) | 576 m | 636 m | 1367 m |
| **inference, every window** | **576 m** | **636 m** | **1367 m** |

`run_inference()` (`ingestion/inference.py:335-469`) slides a 64×64 window at
stride 32 at **native** resolution and argmaxes every pixel — no bbox, no
resize, no IGNORE, no dominant-label shortcut. So the median resized training
patch shows the model a scene **3.7× smaller** than the smallest thing
inference produces. **Only 8.3% of resize patches (53/637) land inside the
inference ground-scale range; 89.5% fall below it** — that is **40.3% of the
whole training set at a scale inference never generates**. Augmentation
(`run_comparison.py:120-141`) is flips, `rot90` and brightness/contrast:
**no scale jitter**, so nothing bridges the gap.

#### 3. Four corrections were built and measured. All failed.

Paired LOCO probes against the unmodified baseline — identical seed, patch
order, batch order and class weights, so arms differ only in pixels. Overall
mIoU, paired mean vs baseline:

| arm | what it changes | n folds | ΔmIoU | p |
|---|---|---:|---:|---:|
| **B** | delete the bad OSM overwrites (→ IGNORE) | 3 | −0.0096 | — |
| **C** | restore the human label on those pixels | 3 | −0.0021 | — |
| **D** | restore them, **and** re-cut those patches at native 64×64 | 3 | −0.0055 | — |
| **E** | full rebuild: all 912 non-sliding-window patches native + multi-class canvas masks | 5 | **−0.1041** | **0.013** |

- **B, C and D** (3 cities × 1 seed × 1,600 steps) all land at zero-to-slightly
  negative. `dense_informal_roofing` — the class the overwrites most directly
  steal from — is **negative in 9 of 9 arm-folds**, mean −0.0205. Arm D vs arm
  C isolates scale alone: −0.0038, p=0.81. **Fixing the scale changes nothing**,
  which rules out the obvious hypothesis that the label fix failed *because*
  the corrected pixels sat at 3.6× magnification.
- **Arm E** (4 cities × 2 seeds planned at **3,200 steps**, the gate budget;
  **5 of 8 pairs completed** — seed 1337 across all four cities plus dharavi at
  seed 7, the run having been stopped before the rest) rebuilt 912
  patches as native windows carrying the real multi-class canvas masks. The
  construction change worked exactly as designed — **85.4% → 47.7%
  single-class**, mean classes/patch 1.18 → 1.70, all 1,414 patches native
  geometry. The training result did not: **−0.1041 last5 (p=0.013), −0.1131
  best\* (p=0.006), 5 of 5 folds negative** on the gate run's own yardstick. The
  `val_base` collapse reproduces across both seeds on dharavi (−0.168, −0.141),
  so it is not seed noise; the per-class native-yardstick numbers are thin and
  should not be built on.

**Why arm E backfired, and it is not fixable by re-cropping.** Removing
magnification cost **31% of the supervised pixel budget** (2,127,525 →
1,468,791) — `paved_road` −41%, `vegetation_clearing` −59%, `standing_water`
−33% — because at native scale a segment occupies far fewer pixels of the frame
than when blown up to fill it. Arm E bought multi-class structure by paying in
supervision volume, and on this dataset volume won. Scored instead on native
multi-class masks (the yardstick arm E was built for) it gains only **+0.0185,
p=0.31**. The asymmetry is the tell: the baseline beats arm E on the baseline's
ground by **5×** more than arm E beats the baseline on its own.

Of the three classes with the most recovered context, none improves:
`active_construction` (68.0% discarded-context rate, the highest) is **worse on
both yardsticks**, 5/5 negative, p=0.050.

#### 4. How much of 85.4% is construction, and how much is scarcity

Measured on the label canvases via exact integral-image counts over **every**
native 64×64 window position at stride 1 — 633,571 usable windows across the
11 tiles, not a sample. "Usable" is the `sliding_window` builder's own test,
≥204 labelled px.

The pooled ceiling is **36.8% multi-class** against 14.6% achieved, and it
varies 4× across cities (hcmc 21.3% → dharavi 87.5%). It is **not** driven by
class count (ρ=+0.01) and only weakly by coverage (ρ=+0.40, p=0.22) — it is
driven by class *mixing*. jakarta is 68.4% labelled but 90.8% of that is one
class, so dense annotation of a monoculture.

Re-centring each bbox-crop patch as a native window on the **same object**:
**245 of 637 (38.5%)** sit inside a window that already contains ≥2 classes —
context that existed and was cropped away. `sam` is the worst offender at
53.4%. The 275 `osm` patches are already native windows and discard their
context by masking instead: the canvas in those same windows is 22.9%
multi-class, all overwritten with IGNORE.

Holding the sampling positions fixed and cutting everything native:

| builder group | n | multi now | multi if native |
|---|---:|---:|---:|
| bbox-crop+resize | 637 | 0 (0.0%) | 245 (38.5%) |
| `osm` road windows | 275 | 0 (0.0%) | 63 (22.9%) |
| `sliding_window` | 502 | 207 (41.2%) | 207 (41.2%) |
| **total** | **1414** | **206 (14.6%)** | **515 (36.4%)** |

**So the 85.4% decomposes into ≈21.9 pp construction artifact (309 patches,
recoverable by re-cropping existing annotation) and ≈63.6 pp genuine
annotation scarcity (899 patches, recoverable only by new labels).** About
**26% artifact, 74% real**.

Two hard limits on the artifact share: the native-window pool is only **703
usable windows at stride 32 across all 11 tiles**, and `sliding_window`
already draws 502 of them — finer strides give more overlapping views of the
same annotation, not more diversity (the multi-class rate is pinned at ~36.8%
at stride 32, 16, 8 and 4 alike). And **81.3% of the imaged area carries no
label at all** (371,692 of 1,984,501 px). That, not the cropping, is binding.

Single-class-ness is also largely a window-size effect, which matters only
because 64×64 is fixed by inference: multi-class rate runs 14.7% at 32×32,
36.9% at 64×64, 67.9% at 128×128, 95.0% at 256×256.

#### Why this closes

The structural claim is verified and quantified. **The 21.9 pp that was
recoverable without new annotation has been recovered — in arm E, which
achieved it and made mIoU significantly worse.** Every patch-construction-side
fix available without new labels has now been built and measured: delete the
bad overwrites, restore the human labels, restore them at the right scale, and
rebuild the whole set native and multi-class. All four failed or backfired.

**C43 remains true as a description of what 0.313 measures, and quoting that
number as the pipeline's per-pixel segmentation accuracy still overstates what
was tested.** That caveat stands permanently. What closes is the *investigation*:
there is no further construction-side experiment worth running, and the
remaining lever is annotation density — which is exactly the resolution and
taxonomy-ceiling argument `01_DIAGNOSIS.md` makes. Read with **G1** (more of
this data does not help) the two agree: the constraint is neither the amount of
this data nor the shape of the crops, it is what is annotated and at what
resolution.

**Same class of gap as C41**, and the two compound: C41 says the number was
measured on three bands after a tile-relative rescaling; C43 says it was
measured on a task the deployed pipeline does not perform.

*Measured by `experiments/band_reflectance/production_patches_v2.py` and
`experiments/band_reflectance/c43/`. Reconstruction: `results/patch_rebuild_v2.md`.
Probe raw data: `results/c43/`.*

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

**Relevant to Decision 13's reflectance precondition:** the 6-band float32
tiler is a prerequisite for unmixing (item 21), not a retired path — the
dual-stem classifier that consumed it is dead, but the tiler itself produces
exactly the physical-reflectance input the new architecture requires.

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
it is a prerequisite for Decision 13's unmixing (item 21), which requires the
float32 reflectance path rather than the stretched-preview path. What is
deleted is the dual-stem classifier that used to consume the tiler's output,
not the tiler.

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

### The epistemic contract (Decision 14 — SETTLED, spec rewritten below)

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

**C40 — The API has no authentication or authorization of any kind** [S]
`api.py` exposes 8 endpoints with **zero** auth primitives — `Depends`,
`HTTPBearer`, `HTTPBasic`, `OAuth2`, `APIKeyHeader`, `Security(` all return zero
matches across the file. Any party who can reach the port has full access to
every endpoint.

- `POST /api/scheduler/trigger` (`api.py:332`), docstringed *"Manually trigger a
  refresh of all watched AOIs (admin use)"*, calls
  `scheduler.modify_job("auto_refresh", next_run_time=datetime.now())`. One
  unauthenticated request fires `run_pipeline` across all of `WATCHED_AOIS`.
  **Amplification: one HTTP call → 3 GEE-backed pipeline runs**, billed to the
  project. "(admin use)" is a docstring, not a control.
- `POST /api/analyze` and `POST /api/analyze_inundation` run the full GEE
  pipeline on a caller-supplied bbox — unauthenticated consumption of metered
  third-party quota.
- `GET /api/runs` and `GET /api/runs/{run_id}` return all run data. The latter is
  also **C34's traversal sink**.

**The only access control present is CORS** (`api.py:22`,
`allow_origins=["http://localhost:5173", "http://localhost:3000"]`). **CORS is
browser-enforced, not server-enforced** — it is irrelevant to `curl`, a script,
or any non-browser client, and it is not an authorization mechanism. Reading the
tight origin list as though it restricted access is the specific error to avoid
here.

*Read from source, not exercised against a running server — hence [S]. No
`Dockerfile`, `Procfile`, or deploy script is tracked, and the documented launch
is `uvicorn api:app --reload --port 8000`, which defaults to binding
`127.0.0.1`.*

**Severity: Critical.** **Under Decision 15:** the localhost default is
*mitigating context, not positive evidence of unreachability*. Nothing
structurally prevents `--host 0.0.0.0` — no code path, no config assertion, no
deployment artifact constrains the bind address; it is a CLI default that any
invocation can override. Under the strong bar this does **not** qualify for a
probability downgrade, and harm if it fires is high (unauthenticated compute and
quota spend, full read of all run data, and the reachability that makes C34
exploitable by anyone). Stays Critical.

**Orthogonal to C34/C35, not duplicative.** C34 and C35 are about *what* a
caller may pass through the boundary; C40 is about *who* may reach the boundary
at all. C35's own framing — "validated at the API boundary is not the same as
validated everywhere" — names the inward axis; C40 names the outward one. The
two do not substitute for each other: **fixing item 47 does not touch C40, and
C40 is what makes C34 reachable by an anonymous caller rather than by an
authenticated one.** Both are required.

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
never received a fate category, never appeared in the summary table, and had no
corresponding build item. This is a real gap, flagged during the Part 3
consolidation pass — it does not resolve on its own and needs the same triage
attention every other finding in this document received.*

***Partially resolved.** C34 and C35 were scheduled as `05_BUILD_MANUAL.md` item
47, built, and have moved to **CLOSED** above. **C36, C37 and C38 remain
untriaged** and still need a fate.*

***C41 added** during the encoder band-mapping verification. Also untriaged.*

***C42 added** during the training-reproduction attempt. Also untriaged.*

***C44 added** during the city-selection measurement, from live probing of the
Overpass endpoints the ingestion path depends on. Also untriaged.*

### C45 — The OSM patch builders overwrite human labels with their own class [E]
Found while investigating **C43**, and unlike C43 this is a **live data defect**,
not a statement about what a number means. Two of the five patch builders paint
their own class over pixels a human annotator had already labelled as something
else, and the model is trained on the result.

Measured by aligning every OSM-builder patch footprint back to that city's SAM
label canvas, pixel for pixel (`osm_generated` and `osm_generated_water` crops
are resized to the patch frame with NEAREST so the comparison is exact):

| builder | patches | canvas-labelled px in footprint | → set to IGNORE | → **overwritten with the builder's class** |
|---|---:|---:|---:|---:|
| `osm` | 275 | 87,630 | 82.9% | 12.0% |
| `osm_generated` | 274 | 89,397 | 85.6% | 14.3% |
| `osm_generated_water` | 95 | 80,430 | 51.5% | **43.9%** |

**The overwrites are wrong labels, not merely missing ones:**

- `osm_generated` paints **`paved_road`** over **7,715 px** the annotator called
  **`dense_informal_roofing`** — **60.2%** of its overwrites.
- `osm_generated_water` paints **`standing_water`** over **32,553 px** the
  annotator called **`dense_vegetation`** — **92.3%** of its overwrites, and
  **4× more** than the 3,745 px where it agrees with the canvas.

So the buffered-geometry builders are actively teaching the exact
`paved_road`/`dense_informal_roofing` confusion the project has been chasing.

**Scope: 369 of 1,414 patches** come from the two `osm_generated*` builders;
**63 patches / 48,101 px** carry an actual overwrite conflict, which is **2.3%
of the supervised pixel budget**.

**Correcting it does not help — measured, not assumed.** Arms B, C, D and E in
**C43** all remove or repair these overwrites and all land at zero-to-negative
(−0.0096, −0.0021, −0.0055, −0.1041). `dense_informal_roofing`, the class the
overwrites most directly steal from, is negative in 9 of 9 arm-folds.

**Filed anyway, and deliberately.** A builder that silently overwrites human
annotation is a defect regardless of whether fixing it moves this particular
metric — it corrupts the ground truth every future experiment reads, and the
measured null was obtained on a 2.3% perturbation with n=3, which rules out a
large positive effect but cannot license the defect. **Untriaged: the fate call
is a human act by this document's own rules.** Note that fixing it costs
`paved_road` and `standing_water` supervision, so it is not free.

*Measured by `experiments/band_reflectance/c43/overwrite_audit.py`. Probes:
`c43/fix_build.py` (arms B/C), `c43/fix_build_d.py` (arm D), `c43/fix_build_e.py`
(arm E). Raw: `results/c43/`.*

### C44 — Two of the three Overpass endpoints are unreachable, and failures are logged without their status code [E]
Measured 2026-09-14 by `GET /api/status` against each host, one lightweight
request each:

| endpoint | result |
|---|---|
| `overpass-api.de` | **HTTP 200**, healthy, reports `Rate limit: 2` |
| `overpass.kumi.systems` | **ReadTimeout** |
| `overpass.openstreetmap.ru` | **ConnectTimeout** |

**The cost depends on which of two patterns a caller uses, and they are not
equally affected.**

*Round-robin — real waste on every retry:*
`generate_osm_road_masks.py:110` and `generate_osm_water_masks.py:103` both do
`OVERPASS_URLS[attempt % len(OVERPASS_URLS)]` over a 3-host list with
`retries=4`. The attempt sequence is therefore **de → kumi → ru → de**, so
**two of every four attempts go to hosts that cannot answer**, and the
15/30/45 s backoff is paid in full for each. A query needing two real tries
waits ~45 s in dead-host backoff to get there.

*Nested fallback — wasteful only on the failure path:*
`ingestion/exposure_sources.py:296` and `ingestion/osm_dem.py:45` loop
`for endpoint: for attempt in range(3)` over a 2-host list. The dead host is
reached only after the live one has already failed three times, so the cost is
3 dead attempts plus a 5 s inter-endpoint sleep, and only when the run was
failing anyway. **These two are not "two-thirds wasted"** — the distinction
matters for how urgent the fix is.

Both `ingestion/` callers additionally back off `2 ** attempt` = **1 s, 2 s,
4 s**, which is short against a server advertising two concurrent slots.

**The second half of the finding: the logging cannot tell failures apart.**
All four callers catch bare `Exception` and log `{e}` or the type name, never
`response.status_code`. `raise_for_status()` collapses 429, 502, 503 and 504
into one `HTTPError`. Measured consequence during this work: what looked like
a uniform wall of `HTTPError` turned out, once the status and body were
logged, to be **HTTP 504 carrying `runtime error: open64: 0 Success
/osm3s_osm_base Dispatcher_Client::req`** — a transient Overpass *dispatcher*
fault, not a query-too-heavy timeout. An unchanged retry 10 s later succeeded
every time. The remedies diverge sharply: a 429 needs a long backoff, a
genuine query-timeout 504 needs the query split, and a dispatcher 504 needs
only a short retry. Without the status code, none of those can be chosen, and
the natural reading — "504 means my query is too heavy" — is wrong here.

**Not fixed, deliberately.** Endpoint liveness is environment- and
time-dependent, so hardcoding the current list into the production path would
encode today's network conditions as a permanent fact; the right fix is
probably a liveness probe or configuration rather than a deletion, and that is
a design decision. `experiments/city_selection/test2_osm.py` works around it
locally for the measurement run only, and says so in its docstring.

*Same shape as **C6** (`get_osm_features` returning `None` for both "no roads"
and "API failed") — an external dependency whose failure modes are collapsed
into one indistinguishable signal.*

***C43 closed** by the patch-construction investigation — moved to **CLOSED**
above. **C45 added** by the same investigation, and untriaged: it is a live
data defect, not a description of what a number means.*

### C42 — The production checkpoint's training source is ambiguous, and the code cites the wrong notebook [E]
Same class of provenance gap as **C5** (a wrong conclusion drawn from not
locating the training notebook) and **C10**/item 45 (calibration artifacts with
no verifiable source). Here the artifact is the production checkpoint itself.

**Two different notebooks are cited for one checkpoint.**
`ingestion/resnet_model.py:7-8` states the architecture was "extracted directly
from the training notebook (`geowatch_segformer_finetune_UPDATED.ipynb`, the
'Encoder swap' cell)". `archive/AUDIT_FINDINGS.md:689` independently identifies
**`geowatch_water_loco_with_diagnostics (2).ipynb`** as the notebook that
produced the checkpoint, by mtime plus a four-way fingerprint match against the
checkpoint's stored metadata.

**Measured: they are not the same training pipeline.** Across the 54 archived
notebooks at `ecfe370`, the patch builders split cleanly into two families:

| notebook family | patch builders | separation loss |
|---|---:|---|
| `..._UPDATED.ipynb` (cited by `resnet_model.py`) | **3** — `sam`, `osm`, `sliding_window` | **none** |
| `..._water_loco_with_diagnostics.ipynb` | **5** — adds `osm_generated`, `osm_generated_water` | **present** |

The checkpoint's own `architecture` string reads
`"GeoWatchResNetSeg (... + paved_road/dense_informal_roofing separation loss)"`.
Only the 5-builder family implements a separation loss; the notebook
`resnet_model.py` cites has none anywhere. The 5-builder family also contains
the LOCO loop that the 0.313 ± 0.056 figure requires.

**So the evidence points to `water_loco_with_diagnostics` as the training source,
and `resnet_model.py`'s citation being architecture-only while reading as though
it were the whole provenance.** Both claims can be true at once — the encoder
swap defined in one notebook, the training run executed in another — but nothing
in the repository says so, and a reader following the code's own pointer
reconstructs the wrong pipeline.

**Cost already incurred, which is why this is a finding and not a note.** A
reconstruction built from the cited notebook produced **2,359 patches** against
the checkpoint's recorded `n_train_patches=1272 + n_monitor_patches=141 = 1413`,
and class weights recomputed from it diverge from the checkpoint's stored values
by up to 0.83 — `paved_road` 0.0666 vs 0.1707 (2.75× too many patches) and
`standing_water` 1.3261 vs 0.4915 (~2.5× too few). The `standing_water` shortfall
is directly explained by the missing `osm_generated_water` builder, which the
cited notebook does not have. The weights are a usable provenance test precisely
because the notebook computes them *from the built dataset* — a property it
documents as the fix for an earlier real bug.

*Related: `03_EVIDENCE.md` §A.14 / **C41** established what the classifier
consumes. This entry is about not being able to reconstruct how it was trained.
Between them, neither the input contract nor the training pipeline of the
deployed model was documented in a form a reader could follow.*

### C41 — The classifier is RGB-only, on tile-relative values [E]
Two measured facts about what the production model actually consumes, both
found while verifying a *different* suspected defect (a 13-band → 6-band
`conv1` slice with wrong indices). **That defect does not exist** — there is no
slicing code in the repository, and `conv1.weight` is `(64, 3, 7, 7)` in both a
fresh load and the deployed checkpoint. The verification returned a clean
negative and this finding instead.

**1. Three bands reach the model, not six.**
`resnet_model.py` loads `ResNet50_Weights.SENTINEL2_RGB_MOCO` — `in_chans=3`,
`bands=['B4','B3','B2']` (Red, Green, Blue). NIR, SWIR1 and SWIR2 are exported
into `raw.tif` and written to `.npy` by `generate_tiles()`, then **discarded
before inference**: `run_inference()` reads the 8-bit RGB PNG
(`inference.py:390`). Band order is correct; the bands are simply absent.

**2. The values are tile-relative, not absolute reflectance.**
The checkpoint's own transform is `Normalize(mean=[0], std=[10000])` — DN ÷
10,000, absolute reflectance — and `raw.tif` is already on that scale. The model
instead consumes a **per-tile 2nd/98th percentile stretch** ÷ 255:
Dharavi **0.089 → 0.212** (2.4×), Accra **0.124 → 0.389** (3.1×), Jakarta
0.187 → 0.204 (1.1×), Cape Town 0.175 → 0.400 (2.3×). The same physical surface
yields different input depending on its tile, and the distortion is
city-dependent.

*Not train/serve skew* — both paths apply `/255.0` with no mean/std, which
re-confirms **C5**'s refutation. The concern is pretraining transfer and
cross-city generalisation, which is what LOCO measures.

**What it qualifies.** The **0.313 ± 0.056 LOCO baseline** is an RGB-only,
tile-relative number, not a measurement of this architecture on Sentinel-2's
full signal. Every prior conclusion about spectral separability *in the
classifier* is bounded the same way, including `paved_road`'s magnet-class
behaviour and the failure of the paved/roofing separation loss — all observed
in RGB.

**Cross-reference to item 21 — the two are not comparable.** Item 21's
**1.70°** built/paved spectral angle, its ~0.7° noise floor, and its R² ceilings
(built 0.490, `impervious_total` 0.822, impervious+bare 0.964) were computed in
**6-band** space. **The classifier does not operate in that space.** Item 21
describes the signal available to a 6-band solver; the classifier sees three
bands after a tile-relative rescaling. Neither result predicts the other, and
treating item 21's ceilings as bounds on classifier performance — or classifier
confusion as evidence about item 21's ceilings — would overstate both.

*Full measurements in `03_EVIDENCE.md` §A.14. Enforced by
`assert_encoder_band_contract()`, which refuses a checkpoint whose bands,
channel count or order stop matching what the pipeline supplies.*

### C36 — `GHSL_BUILTUP_ASSET` pins the epoch in the asset string [E]
`configs/exposure_constants.py:58` hardcodes `.../GHS_BUILT_S/2020`.
`ee.Image(...)` with no collection query, no `aggregate_max`, no dynamic
selection. **Cannot reach another epoch without editing the constant** — while
2025 and 2030 sit in the same P2023A collection with identical bands.

*Contrast: the WorldPop selection logic has **no hardcoded year at all** —
`aggregate_max("year")` then filter. It would pick up newer epochs
automatically.*

**Relevant to Decision 13's validation gate:** GHS-BUILT-S is used there as a
(weaker, non-independent) reference for `built` fraction validation. This
finding means the reference is pinned to a 2020 epoch regardless of which
Sentinel-2 composite date the unmixing solve uses — a real, separate
temporal-mismatch caveat for that validation step, distinct from the
lineage-independence caveat already noted there.

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
