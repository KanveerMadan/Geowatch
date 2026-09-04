 GeoWatch — Diagnosis

**What the project was trying to do, what broke, and why.**

This is the "why" document. It explains the reasoning that led to replacing the
architecture rather than repairing it. Read this before the build manual — the
build manual assumes you accept the conclusions reached here.

Companion documents:
- `02_ARCHITECTURE.md` — what the project becomes
- `03_EVIDENCE.md` — the research and verification behind these conclusions
- `04_FINDINGS_LEDGER.md` — every finding and its fate
- `05_BUILD_MANUAL.md` — what to build, in order

---

## 1. What GeoWatch was

A per-pixel land-cover classifier for satellite imagery, with flood risk derived
from the classified output.

**The pipeline:** Sentinel-2 imagery (10 m ground sample distance) → SAM
segmentation into class-agnostic regions → a ResNet50 (SSL4EO-S12 pretrained)
+ DeepLabV3+ model assigning one of 7 classes per pixel → CAAT per-class
confidence thresholds rejecting uncertain pixels as "unknown" → downstream
modules computing hydrological surfaces, susceptibility, exposure, and risk.

**The taxonomy** reveals what it was really attempting:
paved_road open_drainage_channel dense_vegetation
dense_informal_roofing standing_water open_waste
sparse_informal_roofing vegetation_clearing unknown
unpaved_dirt_road active_construction

That is a fine-grained morphological description of informal settlement
interiors. It wanted to distinguish a footpath from a rooftop, a drain from a
puddle, dense informal roofing from sparse.

**The implicit claim underneath the architecture:** *if every pixel is named
correctly, everything downstream follows.*

That claim is what failed.

---

## 2. The symptom that started the investigation

Persistent confusion between `paved_road` and `dense_informal_roofing`,
surviving a dedicated intervention. The production checkpoint's own metadata
records:architecture: 'GeoWatchResNetSeg (ResNet50 SSL4EO-S12 MoCo + DeepLabV3+,
paved_road/dense_informal_roofing separation loss)'


A loss term had already been added specifically to separate this pair —
`separation_weight = 0.25`, deliberately lowered from 0.5. It did not work. The
confusion persisted, and this pair accounted for a large majority of all
unknown-pixel mass.

Mean leave-one-city-out (LOCO) mIoU across 11 Global South cities: **0.313**.
The model is right about a third of the time on a city it has not seen.

---

## 3. The audit

Six read-only module audits (ingestion, classification, orchestration,
downstream analysis, training/annotation tooling, frontend), producing 33
Critical findings plus a large body of Moderate and Minor ones, then a further
water-mask audit adding W1–W4, then four new findings (C34–C37) during
remediation, then C38–C39.

Two things about the audit matter more than its output.

**It got something wrong and caught it.** An early finding was upgraded to
"CONFIRMED — real train/inference distribution mismatch" on the strength of
file timestamps, checkpoint metadata, and a docstring. The reasoning was *post
hoc ergo propter hoc*: a retiling script ran ~14 hours before the checkpoint was
saved, so it was assumed to have fed training. The training notebook was later
located outside the repository and read directly — training had actually used a
different, PNG-based path. The `.npy` files were an abandoned experiment.

The error's shape is instructive: it treated a docstring as evidence of
behaviour, in an audit whose most repeated theme was *docstrings in this
codebase lie*. It identified the pattern across five modules and then fell for it.

**It had never run the system.** Every finding was static analysis or inspection
of existing artifacts. Not one had been confirmed by executing the pipeline and
observing wrong output. That gap was closed later (§6) and changed several
conclusions.

---

## 4. Four structural causes behind 33 findings

The findings are not 33 independent defects. Grouped by mechanism:

### S1 — The system cannot represent "we don't know" (~11 findings)

Three distinct epistemic states — *measured value*, *measured absence*, *failed
to measure* — collapsed into two or one, at every boundary.

- `roads_gdf is None` means both "no roads here" and "Overpass died" (C6)
- `impervious_fraction_pct = 0.0` means both "paved nothing" and "classified
  nothing" (C21)
- A GEE timeout and a genuine data gap produce identical ward output (C27)
- `{pct ? fmtPct(pct) : '0.0%'}` renders absent and zero identically (C33)

The purest instance is `perception/hydrological_surfaces.py` — the only module
in the analysis chain with no status field and no failure path. That single
omission produces C19, C21, and C25 directly, and makes two separate guard
clauses in two separate files vacuous. **One design gap wearing nine masks.**

### S2 — Signals computed, then never consumed (5 findings)

`applicability` computes an `out_of_distribution` verdict correctly, on every
run, and it is the right call. Then:

- Nothing downstream gates on it (C14)
- It does not gate its own siblings (C20)
- The frontend never reads it — its sole textual occurrence in `App.jsx` is an
  unrelated `intersection_type` string comparison (C32)

Confirmed by execution at `unknown_pct = 60`: the pipeline returns
`urban_landcover_model: out_of_distribution` in the same dictionary as
`pluvial: applicable` and `waterlogging: applicable`.

**A system that detects its own unreliability and then discards the detection is
failing at the thing it claims to be good at.** Designed as a router, wired as a
report.

### S3 — Cross-boundary contracts enforced only by prose (~6 findings)

A Python comment asserting a JavaScript constant must match — 0 of 8 categories
actually match (C31). A provenance check, correctly written, living in dead code
that nothing imports (C10). A verifier encoding an invariant that a later phase
silently broke (C30). A band-order contract enforced by a comment (C4).

A rule enforced only by prose fails at the first edit made by someone who did
not read the prose.

### S4 — Identity derived from incidental position (~4 findings)

`segment_id` is a rank in an area-sorted list. `get_latest_run` treats
lexicographic order as chronological, so `/api/demo` permanently serves a stale
test artifact because `'2' < 't'` (C17). Both work until the incidental property
changes.

---

## 5. The physical limit: sub-pixel supervision

This is the finding that reframed everything.

**`generate_osm_road_masks.py` is well-engineered.** Meter-accurate UTM
buffering, per-highway-type widths, unpaved tags correctly excluded. The author
identified the contamination risk explicitly and chose narrow buffers to avoid
it.

At 10 m ground sample distance, that choice cannot help:

| OSM class | Real width | Pixels at 10 m |
|---|---:|---:|
| motorway | 12 m | 1.20 |
| trunk | 10 m | 1.00 |
| primary | 9 m | 0.90 |
| residential | 5 m | 0.50 |
| service | 4 m | 0.40 |

Only `motorway` exceeds one pixel. `trunk` lands exactly on one — and a feature
exactly one pixel wide is still mixed whenever it does not align to the grid.
Everything else is sub-pixel by construction.

Cape Town's 192 generated road records have a **median mask area of 23.5 px**.
Thin ribbons.

**A pixel labelled `paved_road` is therefore physically a mixture** — road plus
whatever abuts it, which in dense settlement is rooftop. Narrowing the buffer
does not avoid mixing at this resolution; it guarantees every labelled pixel is
mixed.

### The same pathology, independently, in a second generator

The water-mask audit found it again:

| OSM waterway class | Real width | Pixels at 10 m |
|---|---:|---:|
| river | 15 m | 1.50 |
| tidal_channel | 10 m | 1.00 |
| canal | 8 m | 0.80 |
| stream | 3 m | 0.30 |
| drain | 2 m | 0.20 |
| ditch | 1.5 m | 0.15 |

**This is not a road-specific problem. It is a linear-features-at-10 m problem**,
appearing wherever the taxonomy contains one.

---

## 6. What execution revealed

The pipeline was run end-to-end on Dharavi (291×257, 1 tile), a determinism
control (identical parameters), and a deliberately oversized 75 km² AOI
(892×891, 4 tiles). Environment needed no fixes.

### The reframe: `paved_road` is a magnet class, not half of a pair

The entire investigation had been framed around a *pair*. Execution showed the
pair framing is incomplete and somewhat misleading:

- `paved_road` is the **top-2 partner for all six other classes** (55.4%–80.9%)
- It appears in the **top-2 for 85.1%** of all pixels, top-3 for 96.4%
- Its **median** softmax is **0.3244**; every other class sits at 0.0014–0.0128
- On pixels it does *not* win, it still holds **0.1420** mean probability —
  more than double the next class (0.0681)
- It is **42.45%** of raw argmax against **17.81%** of pixel-level supervision:
  roughly **2.4× over-predicted**

Every other class is bimodal — confident where it belongs, near-zero elsewhere.
`paved_road`'s median is close to its mean: **uniformly elevated, not
concentrated.**

Two corollaries fell out immediately:

- `CONFUSION_PAIRS`' second entry, `{dense_vegetation, standing_water}`, is
  **empirically wrong**. Both classes' actual top-2 is `paved_road` (79.4% and
  72.5% respectively).
- `check_confusion_pair.py`'s own ≥40%-both-directions criterion is **not met**
  (paved→roofing 36.7%). By its own rule it would print *"NOT a clean confusion
  pair… more consistent with each class independently being undertrained or
  having noisy/inconsistent ground truth labels."*

### The mechanism

Three candidates were tested; two eliminated.

**Not the final classifier layer.** Bias spread across all seven classes is
0.0617, and `paved_road`'s bias is not the highest. Its weight-norm is the
*lowest* (0.8548 vs up to 0.9616).

**Not class weighting.** `paved_road` carries the **lowest** CE weight (0.1707
of seven). Weighted cross-entropy is equivalent to resampling class *c* by
*w_c*, so a low weight *suppresses* that class. The weighting was fighting the
over-prediction, not causing it.

**A diffuse learned prior, traceable to label geometry.** Sub-pixel road labels
make every `paved_road` training pixel a spectral mixture. The model therefore
learned `paved_road` not as *asphalt* but as **generic mixed urban texture** —
which is, by construction, the nearest class to any ambiguous pixel in an urban
scene.

This connects to the long-tail literature. Menon et al. (ICLR 2021) formalise
standard cross-entropy as converging to `p(y|x) ∝ π_y · f_y(x)`, where `π_y` is
the training prior. A large prior combined with a *generic* feature means the
prior term dominates globally. A prior effect is global and additive across the
whole feature space; a confusion effect is local and pairwise.

**This is why a pairwise separation loss could not work.** It attacks a local
decision boundary. The problem is a global prior.

### Three headline figures re-derived; one held, two did not

| Figure | Original claim | Measured | Outcome |
|---|---|---|---|
| Pair share of unknown mass | 72.9% | 70.1% with penalties, 72.4% without | ✅ holds |
| Unknown-pixel rate | "~50%" | **25.74%** / 28.79% | ❌ stale by ~2× |
| `paved_road` supervision share | 41.0% | 17.81% by pixel, 73.38% by patch | ⚠️ misattributed |

**The "~50%" was traced, not merely corrected.** `caat_diagnostic.py`'s
docstring records the original hypothesis; `recalibrate_caat.py` records the
outcome — CAAT thresholds computed from isolated single-patch forward passes
while production uses sliding-window averaged inference, causing a documented
**+22 pp unknown-rate gap**. Measured: sliding-window averaging lowers mean
top-1 confidence from 0.8174 to 0.7264. And the arithmetic closes:
**24.45% + 22 pp = 46.4% ≈ "~50%"**. A stale number describing a superseded CAAT
generation, in a docstring never updated after the fix.

**The 41% was a checkpoint inversion, not a count.** Obtained by inverting the
checkpoint's `class_weights`. The *measured* by-patch figure for the annotation
pool is **73.38%** — so the executive summary, pairing "41% by patch" with
"17.8% by pixel," understated patch dominance by nearly 2× while appearing to
correct it.

### Two findings downgraded by execution

**C22** predicted no-data pixels would render as *maximum* susceptibility.
Measured: they render mid-range (mean 125.4), *below* the known-pixel mean
(149.1), with 0.0% at the PNG maximum. The mechanism is real but the two
components cancel — `UNKNOWN` is minimum on the impervious surface (weight 0.70)
and maximum on the deficit surface (weight 0.56). The surviving defect is a
**collision**: no-data scores identically to `standing_water` and
`active_construction`. Not an alarm.

**C15** was not triggered. Both runs had real road-access scores (0.162–0.985,
mean 0.831), zero `-1.0` sentinels; `road_access_scores_reliable: true` was
accurate. Real bug, precondition absent. Latent, not live.

### The system is deterministic

Two identical runs produced **bit-identical** landcover maps (0 of 74,787
differing pixels) and identical scores throughout. This isolates C27:
ward-screening non-reproducibility is the 90-second wall-clock GEE timeout, not
model nondeterminism.

---

## 7. Why the architecture had to change

Follow the chain:

1. Roads at 4.5 m are 0.45 pixels. Physical, not fixable by modelling.
2. Sub-pixel labels make training pixels spectrally mixed.
3. Mixed pixels teach the model a *generic* feature.
4. A generic feature plus a large prior produces global over-prediction.
5. A pairwise loss cannot fix a global prior — confirmed by its failure.
6. CAAT cannot suppress the residue — it calibrates on correctly-predicted
   pixels only, a pure recall criterion with no precision term.
7. The road-proximity penalty was a band-aid over a class-prior problem — and
   its normalization is per-AOI, so its strength is set by whatever bounding box
   the user happened to draw (C7).

Everything in that chain except step 1 was infrastructure built to prop up a
naming task the sensor cannot support.

### The field already reached this conclusion

ESA WorldCover (11 classes) and Google Dynamic World (9 classes) both operate at
exactly 10 m. Both use **one built class**. No road/roof separation. No
formal/informal distinction. Neither is an oversight — it is the considered
design decision of two well-resourced teams facing this exact constraint.

Venter et al. (2022) compared Dynamic World, WorldCover, and Esri Land Cover and
found systematic confusion concentrated specifically in built/urban classes
across all three.

WorldCover's own validation report gives built-up user's accuracy of **47.1% in
Africa** against producer's accuracy of 84.0% — it finds most real built-up but
**less than half of what it calls built-up actually is.** Massive
over-commission, in exactly the setting GeoWatch targets.

### The insight that resolves it

**`paved_road` exists as a raster class because the pipeline is raster-first, not
because roads are raster objects.**

Examine what each consumer actually needs:

| Consumer | What it needs | Right representation |
|---|---|---|
| Flood model | Roads as conduits with geometry | Vector, rasterized at hydrology resolution |
| Density metrics | Road length per unit area | Vector, aggregated |
| Access indicators | Network connectivity, distance-to-access | Vector, network analysis |
| Land-cover proportions | How much of this area is hard surface | Fraction — road/roof distinction irrelevant |
| Change over time | What shifted between t1 and t2 | Fraction deltas, not class flips |

**No consumer ever wanted a per-pixel road label.** The flood model wanted
geometry. Density wanted length. Access wanted connectivity. Land-cover wanted
proportion.

The class was serving the architecture, not the requirements.

---

## 8. The scope clarification

Two facts about the project reframed the conclusions further:

**It is global.** Must work in Paris, Beijing, Kampala, Lagos, Dharavi. No
per-city manual step survives this requirement.

**It is an urban planning analysis, with flood risk as one output** — not a
flood tool. Formal and informal fabric weighted equally.

The planning outputs are: land-cover proportions per area, density metrics,
access and service indicators, change over time, and flood risk.

**Every one of those is an aggregate over an area.** Proportions, densities,
ratios. And aggregates are precisely what survives sub-pixel mixing — a 4.5 m
road contributes its correct proportional share to a block's hard-surface
fraction even though it cannot be resolved as a discrete object.

**The information a planner needs is genuinely available at 10 m. The
information the old classifier was trying to produce is not.**

---

## 9. The one-line difference

Before, the system asked **"what is this pixel?"** — a question Sentinel-2 cannot
answer at informal-settlement scale.

Now it asks **"what are the proportions, densities, connections, and changes in
this area?"** — questions Sentinel-2 answers well, globally, for free, going back
a decade.

Same sensor. Same imagery. Different question. And the question it now asks is
the one a planner was going to ask anyway.

---

## 10. What this makes of the project's contribution

The failure is the finding.

A dedicated separation loss was applied to a confusion pair and failed. The
sub-pixel arithmetic shows why it had to. The magnet-class measurement shows the
mechanism. The field's leading 10 m products independently made the same
taxonomic retreat.

*"We identified the resolution threshold below which road/roofing separation in
dense informal settlements is not learnable, measured the mechanism by which a
targeted loss term fails against it, and designed a taxonomy, an output format,
and an abstention mechanism accordingly"* is a real contribution about a real
problem, and it generalises beyond this project.

*"Our mIoU is 0.313"* is not.

The reframe is not a retreat. It is what the evidence supports.
