# GeoWatch — Build Manual

**All 13 parts, all 68 items. What to build, how to build it, and how to know it
worked.**

Read `01_DIAGNOSIS.md` and `02_ARCHITECTURE.md` first. Check
`04_FINDINGS_LEDGER.md` before starting any item — roughly a third of the
original findings are deleted rather than fixed.

---

## How this is sequenced

**One hard gate: Part 3.** Seven decisions block twelve technical items.
Building before they are settled means building twice. **Part 3 is now
complete — all seven decisions settled.** Part 4 is unblocked.

Everything else flows in order. Parts 1–2 have no dependencies. Parts 4–13 depend
on Part 3, and on each other in sequence.

**Status key:** ✅ done · 🔓 ready · 🔒 blocked · ⚖️ decision

---

# PART 1 — Unblock ✅ COMPLETE

*Five items. All committed.*

### 1. C16 — path traversal ✅
Whitelist-validate `aoi_label` at the API boundary: `[a-z0-9_-]{1,64}`,
`HTTPException(400)`, reject-not-sanitize.

**Applied.** Both sinks (`/api/analyze` and `/api/analyze_inundation`),
validation outside the try block, `fullmatch()` not `match()` with `$`,
validation before the demo short-circuit. 72 tests; verified against the
unpatched file (70 failed, 2 passed — the positive controls).

### 2. `git init` ✅
Commit `2ac07d5`, 172 files. `.gitignore` excludes `data/` (821 MB), `models/`
(491 MB), `node_modules`, virtualenvs, context dumps. 37 notebooks copied from
`~/Downloads` into `notebooks/archive/`.

### 3. Artifact hashing ✅
Commit `046dfef`. `ARTIFACT_HASHES.txt`, 30 SHA256 entries — SAM weights,
production checkpoint, CAAT thresholds, 27 `annotations.json`.

### 4. WorldPop ceiling ✅
Investigated. **Not a hardcoded year** — selection is dynamic
(`aggregate_max("year")`). The cap is in the GEE mirror, verified live: 5,221
images, years exactly 2000–2020. Logged as C36–C38.

### 5. Freeze annotation ✅
Commit `46ac923`. Guard under `if __name__ == "__main__":` so
`check_segment_mask.py` can still import `decode_rle`.

---

# PART 2 — Verify ✅ MOSTLY COMPLETE

*Five items. Four done; one optional.*

### 6. Open Buildings road-layer check ✅
**No public road layer exists.** EE namespace enumerated via `listAssets` — only
`polygons` and `polygons_FeatureView` under v1/v2/v3. Temporal v1 bands are all
buildings. Sirko et al. §7 states directly that road metrics are not reported.

**Buildings ARE viable:** CC-BY-4.0 or ODbL, 58M km², all ten target countries,
4 m effective resolution, annual 2016–2023.

### 7. Re-verify the two off-by-2× figures ✅
Both headline figures hold. 17.81% pixel, 49.15% pixel, 28.79% unknown, and all
21 class-weight values reproduce exactly.

**Three corrections applied:** 25.73 → 25.74 (seven occurrences across both
documents); the executive summary's "41% by patch" corrected to the measured
73.38%; the "25/city cap explains the gap" claim withdrawn.

### 8. Spot-check line references ✅
Ten weight-bearing findings checked first-hand. **8/10 reproduce exactly.** Line
citations: six exact, two loose-but-containing, none wrong.

Both defects were **derived numbers presented as measured ones** — see
`04_FINDINGS_LEDGER.md` "Patterns to carry" §3.

### 9. OSM coverage baseline ✅
All 11 AOIs measured. **Pedestrian-path density spans 44×** while arterial
coverage is near-universal.

**Key correction: Dharavi (2.78) and Kibera (2.11) are not the well-mapped
ceiling — Khayelitsha is 8.35.**

### 10. Verify remaining flagged facts 🔓 *(partially done)*
Done: WorldPop R2025A, GHS-POP R2023A epochs, India census → 2027.
Outstanding: Planet E&R eligibility (3-week wait, external).

**Optional extension:** the Lagos visual check. Lagos is the clearest outlier
(0.19 km/km²) and has OpenAerialMap coverage over Makoko at 5.4 cm. Pick a few
hundred metres square, count visible alleys, compare against OSM. *"OSM has 2 of
the ~30 visible alleys"* is an adequate finding. Converts "likely under-mapped"
into a real number for one city.

*Not required — the baseline already supports the design decisions.*

---

# PART 3 ⚖️ — Decide (THE GATE) — ✅ **COMPLETE**

*Seven decisions. All settled. Twelve technical items were blocked behind
these; none of this was typing.*

### 11. Fraction taxonomy ✅ **SETTLED**
Fractions (disjoint, sum to ~1):
built — roofed structure
paved — hard surface, unroofed
vegetation
water
bare — permeable unpaved ground

Derived:
impervious_total = built + paved


Governing principle: **measure disjoint things, derive overlapping ones.** A
concrete roof is physically both a structure and an impervious surface, but it
must not count in two measured fractions — that is how sums break, how change
detection breaks, and how the built-vs-footprint cross-check dies.

Vector carries "what kind" — footprint size distribution, spacing regularity,
density, network geometry, orthogonality. **Formal vs. informal is
morphological, not spectral.**

`built` vs. `paved` is the weakest boundary of the five. Its separators are not
spectral — temporal variance (roofs are more stable than open hardstanding) and
the footprint layer as a prior (a structure has a footprint; a courtyard does
not). Must carry its own confidence marker downstream; never presented at the
same confidence as the other three.

**Known scope boundary, stated explicitly so it is never assumed away:** these
five fractions answer land-cover proportion and imperviousness. They do not
answer land-use, vegetation type, building condition, or anything
demographic/administrative. A "full" urban planning tool would need those as
separate data layers (census, cadastral, infrastructure records) — this
architecture is the physical land-cover layer of such a system, not the whole
system. See `02_ARCHITECTURE.md` §9.

---

### 12. Does SAM survive? ✅ **SETTLED — deleted**

Walked `02_ARCHITECTURE.md` §6's outputs table against item 22's three
aggregation units (grid, footprint, path-delineated). **Nothing consumes a
segment.** Proportions and densities are per-area. Access is network-based.
Morphology is vector. Change is per-area delta. Flood is `impervious_total` +
vector conduits. Every place shape genuinely matters already has a
purpose-built shape-aware unit that isn't SAM — footprints for buildings, path
segments for network.

**The one counter-case that survives stress-testing:** non-building objects
(specifically water bodies) have a plausible future need for object-level
change tracking — "this water body grew toward the settlement" is a per-object
claim a grid answers badly. This does **not** argue for SAM. It argues for
**connected-component labeling on thresholded unmixing-fraction rasters** —
threshold the `water` fraction, run connected components, get labeled,
pre-typed objects with no separate mask-vs-segment ID synchronization problem
to fail (the exact failure mode that produced C9).

**Named as a deferred, unbuilt forward reference — not scope now:** if
per-object tracking of non-building features becomes a stated requirement, the
mechanism is connected-component extraction on unmixing rasters. Not SAM. Not
built until §6's outputs table actually grows to require it.

**Deleted with SAM:** C9 (segment-ID mis-join), C28 (annotation bakes the
mis-join in permanently), C30 (verifier cannot detect it) — all three deleted
rather than fixed, per `04_FINDINGS_LEDGER.md`. Also deleted: the
segment-based annotation tooling (item 31 moves the gold set to stratified
points regardless, so this cost is not attributable to this decision alone),
RLE encoding/decoding, `masks.json`, the segment schema, and the SAM inference
step itself — slow, CPU-bound, run on every pipeline invocation for a
capability nothing currently consumes.

**Reintroduction cost, if ever needed:** low. SAM weights are already hashed
in the artifact manifest; re-integrating inference is an afternoon of
engineering, not a research problem.

---

### 13. Global endmember strategy ✅ **SETTLED — Option D, constrained**

**The split:**

| Fraction | Stability | Method |
|---|---|---|
| vegetation | High | Global library, direct |
| water | High | Global library, direct |
| bare | Moderate | Global library, direct |
| **built** | Low | Global library, extracted from footprint-prior-filtered pixels |
| **paved** | Low | Global library, extracted from wide-unroofed-area-prior-filtered pixels |
| **shadow** | Not a reported fraction | Sixth solve term — see below |

Three fractions are spectrally stable and extracted globally, directly.
`built`/`paved` are near-identical spectrally, so extraction is *constrained*
by two non-spectral priors already built into the architecture for exactly
this pair, rather than asked of spectra alone.

**`built` extraction:** pixels inside a building footprint (Open Buildings /
Microsoft / Overture, with inward margin to exclude edge-mixed pixels),
further filtered to low-temporal-variance pixels within that set (stable
roofs, not degrading or under-construction ones). Endmembers extracted from
this filtered pool per region — labeled by construction, not hand-picked.

**`paved` extraction — corrected during review, do not use road centerlines.**
A pixel on an OSM road centerline at 10 m GSD is ~45% road / 55% roof — that
is C29, the exact contamination this rebuild exists to escape. Extracting
`paved` from centerline pixels would launder the old problem into the new
endmember library. **Source instead from wide, unambiguously unroofed OSM
*polygons*** — `landuse`, `amenity=parking`, `aeroway=apron` — parking lots,
airport aprons, plazas, industrial hardstanding. Many pixels across,
spectrally pure by construction, globally available.

**Shadow — corrected during review, treated as unobserved, not
redistributed.** Under sum-to-one with no shadow term, shadow energy is forced
into the darkest available fraction — `water` — the worst possible direction
for a flood-model consumer. Solve shadow as a sixth endmember, then
**renormalize the other five to sum to 1 over the illuminated portion only.**
Shadow fraction is reported as its own coverage field. Do not redistribute
proportionally across the five — that assumes knowledge of what's under the
shadow, and not having that knowledge is what shadow means.

**Structural connection to Decision 14, carried forward:** shadow fraction and
the observability denominator are the same underlying question — what
fraction of this area could actually be observed. Decision 14 extends this
same separated-reporting logic to cloud/nodata and low-confidence unmixing.

**Reflectance precondition — tightened.** BOA surface reflectance is already
available via `COPERNICUS/S2_SR_HARMONIZED`. The precondition is not
"obtain reflectance," it is: **unmixing must read the float32 multi-band tile
path. It must never read the per-tile percentile-stretched 8-bit PNG preview.**
The reflectance exists upstream; the risk is destroying it downstream at
tiling.

**Validation gate — strengthened.** GHS-BUILT-S is itself Sentinel-2-derived;
agreement with it is not independent confirmation — both could share
WorldCover's Africa failure mode (47.1% user's accuracy: bare compacted earth
called built). **Open Buildings footprints are VHR-derived and genuinely
independent for `built`; weight this comparison more heavily.** GHS-BUILT-S
remains useful as a coarse sanity check, treated with appropriate suspicion
given shared lineage.

**Sequencing requirement:** run a 2–3 city pilot (spanning material
diversity — e.g. dense-informal, dry-soil, formal-vs-informal-in-one-AOI)
comparing `built + paved` against both references **before** committing to
the full six-week Part 4 build. This is the highest-risk item in the plan;
validate the method before scaling it.

**Two risks left explicitly open, not solved by this decision:**
1. Footprint layer quality is weakest exactly where `built`/`paved`
   separation matters most — Open Buildings' own FAQ admits degraded
   performance on small, irregular, densely-packed structures, a description
   of dense informal roofing.
2. Nothing here is confirmed until the pilot validation runs. This is a
   specification for how to build the constrained extraction, not evidence
   that it works.

---

### 14. `category_area_pct` denominator ✅ **SETTLED**

**Chosen: known-pixel denominator. Observability reported as a mandatory
companion field. Non-observation reported as three separate fields, never
merged into one "unknown" number.**

The old framing (known-pixel vs. total-pixel, where "unknown" meant
CAAT-rejected) no longer applies — CAAT is deleted, and fractions have no
per-pixel abstention class. The reformulated question: what does "not
observed" mean now, and how is it reported?

**Convention:** `category_area_pct` is computed only over pixels actually
observed — the illuminated, cloud-free, valid-data portion. **Mandatory
companion field, always emitted:** the observed fraction of the AOI. Fixing
the denominator without emitting coverage merely relocates the bias that
produced C19 (41.68% total-pixel vs. 56.13% known-pixel — 1.35× difference,
and the direction is dangerous: more unobserved area silently reads as *less*
flood-prone).

**Three components of non-observation, reported separately, never merged:**

- **Shadow** — handled by Decision 13. Solved as a sixth endmember term; five
  fractions renormalize over the illuminated portion; reported as its own
  field.
- **Cloud / nodata** — genuine gaps in the composite for the observation
  window. Requires the SCL-based masking fix (item 51, C1) to be trustworthy.
- **Low unmixing confidence** — pixels where the solve is poorly constrained
  against the endmember model. Reported as its own field, not folded into
  either the fractions or the coverage number.

Merging these three was the CAAT-era pathology — the same S1 collapse
(`01_DIAGNOSIS.md` §4) that produced nine findings from one design gap.
Keeping them separate lets a consumer reconstruct *why* coverage is low
(seasonal shadow vs. a cloudy acquisition vs. a genuinely hard-to-unmix
surface) rather than only *that* it is.

**Field-naming discipline for Part 6:** the three non-observation fields must
be structurally distinct from the five land-cover fractions, so a consumer
summing built+paved+vegetation+water+bare gets ~1 over the observed portion
and never mistakes a coverage/shadow/cloud field for a sixth land-cover class
— the same discipline already applied to `impervious_total` in Decision 11.

**What this unlocks:** C19, C21, C25, C26, C33, plus the practical harm in C6,
C15, C22, C27. Part 6 (items 33–39) is built against this spec — see the
Part 6 header note below.

---

### 15. Severity re-rating rule ✅ **SETTLED**

**Severity = probability of firing × harm if it fires.** Probability may only
be revised downward on **positive evidence of unreachability** — never on
absence of a triggering observation. "Never observed in N runs" is not
evidence a mechanism can't fire; it is evidence the triggering condition
hasn't occurred yet in the runs attempted. Treating absence-of-hit as
evidence-of-impossibility is the same error `01_DIAGNOSIS.md` §3 already
caught once, in the opposite direction (a timestamp coincidence treated as
confirmation) — the strong bar exists specifically to not repeat it.

**Qualifies for downgrade:** confirmed unreachable from the live path (**C3**
— only fires if a specific unscheduled script is re-run), confirmed no
consumer (**C13** — live frontend verified to never read `primary_tile`).

**Does not qualify:** "never observed to fire" alone (**C2**, **C4** — the
underlying mechanism is real and understood; only the triggering condition
hasn't occurred in the attempts made). Both remain at original severity.

**Severity and fix priority are separate axes.** A downgrade describes
*current risk to current consumers*, not whether the fix belongs in the build
plan. C13's downgrade does not remove item 46 — the field still points at
nothing correct, and that's worth resolving regardless of today's severity
rating. A finding can be low-risk now and still worth fixing because the
system will change, gain new consumers, or because the fix is cheap enough
that "low priority" and "not worth doing" are not the same thing.

---

### 16. Who is the planning user? ✅ **SETTLED**

**The primary user is a research audience, not a planning audience.**
Realistically reachable user classes for a solo internship project:
advisor/faculty review and self-assessment against domain literature. NGO and
municipal contacts — the users the flood/planning framing actually needs —
require institutional access and lead time this project doesn't have.

**Does not reopen Decision 12.** No reachable user has stated a need for
per-object answers; the connected-component deferral stands.

**The five planning outputs stay in the build**, reframed: *"the method
produces these outputs; here is why they should be trusted, per class and per
city"* — not *"a planner validated these as useful."* This distinction must
be explicit in the model card (item 60) and anywhere else the outputs are
described.

**What this costs, stated plainly:** the product cannot claim a planner would
find it useful — only that it is accurate (or honestly not, per city and per
class) and well-reasoned given the sensor's real limits. A narrower claim than
the flood-risk framing originally implied, and a defensible one.

---

### 17. Gate C ✅ **SETTLED — closed via advisor review**

**Gate C: CLOSED**, via structured advisor/faculty review evaluated against
D.7's five reporting requirements (full confusion matrix before the taxonomy
change; per-class producer's/user's accuracy before and after; spectral/
spatial separability analysis; explicit comparison to WorldCover/Dynamic
World; a causal mechanism tied to sensor resolution, not just "accuracy
improved"). Run the same shape as the originally-specified protocol — show
output cold, ask what it means, ask what they'd do with it, ask what they
think the caveats are without prompting — against the reachable population
established in Decision 16.

**The real-planner protocol is not deleted and not treated as satisfied by
advisor review.** Filed as its own artifact — item 64 — and disclosed
explicitly as **blocked by access, not by design choice.** Per D.7's own
ranking of validation substitutes, advisor review tells you the work is
accurate and well-reasoned; it does not tell you a planner would find it
useful. That gap is named here directly, not left implicit.

This decision exists as its own numbered item, separate from Decision 16,
specifically so a future reader auditing this project has a direct,
citable answer rather than having to infer Gate C's status from a different
decision's text.

---

## Part 3 summary

| # | Decision | Outcome |
|---|---|---|
| 11 | Fraction taxonomy | Five disjoint fractions; `impervious_total` derived; scope boundary stated |
| 12 | SAM | Deleted; connected-components on fraction rasters deferred, named, unbuilt |
| 13 | Endmembers | Option D constrained; corrected `paved` source; shadow as 6th term, renormalized |
| 14 | Denominator | Known-pixel; mandatory coverage field; shadow/cloud/low-confidence reported separately |
| 15 | Severity rule | Strong bar (confirmed unreachable/no consumer only); severity ≠ fix priority |
| 16 | Planning user | Research audience |
| 17 | Gate C | Closed via advisor review against D.7; planner protocol filed as unrun future work |

**All seven settled. Part 4 is unblocked in full**, subject to two sequencing
corrections carried out of this gate: item 51 (SCL cloud mask) must precede
item 18 (temporal variance), and item 21's endmember pilot validation must
run before the rest of Part 4, not after it per the original item 31
placement.


---

# PART 4 — Build the architecture 🔓

*Nine items. The core rebuild. Unblocked — Part 3 is complete.*

### 18. Temporal-variance layer 🔓 *(sequencing corrected — see below)*

**What:** standard deviation of spectral indices (NDVI, NDBI, and the raw bands)
across a year of Sentinel-2 composites.

**Sequencing correction:** this item must run **after** item 51 (SCL-based
cloud mask), not independently. Std-dev is maximally sensitive to exactly the
cloud-leakage outliers an unreliable QA60 mask (C1) would introduce — building
this on an unvalidated mask means rebuilding it once 51 lands.

**Why otherwise first:** needs no decision, no per-city calibration, works
identically worldwide, and gives you a real working component early. It also
feeds item 21's `built`/`paved` disambiguation, so it must exist before
unmixing anyway.

**How:** in GEE, build monthly or seasonal median composites across a 12-month
window, compute per-pixel std-dev per index, export alongside the existing
composite.

**Acceptance:** a variance layer produced for a full-year window over at least
one formal and one informal AOI; paved surfaces measurably lower-variance than
bare soil in both; the layer carries its own date range and composite count.

**Verify:** hand-check a known permanent surface (an arterial road) against a
known seasonal one (a vegetated lot) in the same AOI.

### 19. Vector road layer 🔓

**What:** OSM roads and paths as primary, building-footprint negative space where
OSM is thin.

**How:** Overpass query per AOI for `highway=*`; Open Buildings polygons from EE
or `source.coop`; derive candidate road space from footprint gaps where
pedestrian-path density falls below a threshold.

**Critical:** **one source, many representations.** Rasterization for flood,
aggregation for density, network analysis for access — all downstream of this one
layer. Do not let consumers build their own.

**Acceptance:** road vector produced for AOIs in at least three distinct
morphologies (formal European, formal Asian, dense informal); every derived
output demonstrably traces to this layer.

### 20. Per-area completeness score 🔓

**What:** a mandatory field on every AOI and every reporting unit, quantifying how
much of the road network is likely present.

**Why load-bearing:** the system must **know it is in a low-coverage regime and
say so.** This is the C14/C32 lesson applied to new code. And it is load-bearing
for **two** outputs — routing *and* morphological characterization, since
formal/informal now rests on network geometry.

**How:** pedestrian-path density relative to the measured 11-city baseline;
arterial-vs-pedestrian ratio (good arterials + near-zero pedestrian is the
signature of partial mapping); footprint-count-to-road-length ratio.

**Naming caution:** Part B of `03_EVIDENCE.md` is explicit that no
completeness *rate* is claimed — there is no reference network to measure
against. Name the emitted field accordingly (e.g. `osm_density_percentile` or
`coverage_regime_flag`), not "completeness," to avoid overclaiming what a
peer-relative density rank actually measures.

**Baseline caution:** the 11-city baseline this score is calibrated against is
Global-South, informal-heavy. Item 19's acceptance requires testing on formal
European and formal Asian AOIs too — the baseline needs formal-city anchors
before the score is emitted globally, or Paris will saturate a scale built for
Khayelitsha's 8.35 km/km².

**Acceptance:** score emitted for every AOI, **never optional, never null**; a
low-coverage AOI is visibly flagged end-to-end through to the UI; Lagos (0.19)
and Khayelitsha (8.35) produce visibly different scores.

### 21. Spectral unmixing → fractions 🔓 *(needs 11 ✅ and 13 ✅ — both settled)*

**What:** linear unmixing per 10 m pixel into the five fractions, per Decision
13's constrained-extraction spec in full.

**Precondition — tightened:** BOA surface reflectance is already available via
`COPERNICUS/S2_SR_HARMONIZED`. **Unmixing must read the float32 multi-band
tile path — never the per-tile percentile-stretched 8-bit PNG preview.** The
6-band float32 tiler is a *prerequisite* for this item, not a retired path;
only the dual-stem classifier that used to consume its output is dead.

**How:** constrained least squares (sum-to-one, non-negativity), or
`pysptools`, or Earth Engine's own unmixing. Endmembers per Decision 13:
three stable fractions from a global library directly; `built` from
footprint-prior-filtered, low-temporal-variance pixels; `paved` from wide
unroofed OSM polygons (parking, aprons, plazas) — never road centerlines.

**Shadow handling:** solve as a sixth term; renormalize the five reported
fractions over the illuminated portion only; report shadow fraction as its
own field, per Decision 14's separated-reporting convention.

**Acceptance:** fractions produced for at least one formal and one informal AOI;
sum to ~1 within tolerance over the observed portion; documented endmember
provenance for each; **a per-fraction confidence, with `built`/`paved`
explicitly lower than the others.**

**Sequencing requirement, moved forward from item 31's original placement:**
run the 2–3 city pilot validation (built+paved against Open Buildings,
weighted more heavily, and GHS-BUILT-S, weighted less, given shared
Sentinel-2 lineage) **before** committing to the rest of Part 4's six-week
build. Do not defer this to item 31 — this is the highest-risk item in the
plan and needs its own early gate.

**Verify:** compare aggregate `impervious_total` against WorldCover/Dynamic World
built-up for the same AOI. Agreement is a sanity check, **not ground truth** —
and note WorldCover's built-up user's accuracy is 47.1% in Africa, so disagreement
there is not automatically your error.

### 22. Aggregation units 🔓

**Sequence, in order:**
1. **Regular-grid blocks** — free, immediately available
2. **Building-footprint units** — individually addressable, good for risk
   communication
3. **Path-delineated segments** — most faithful to how water and people move, but
   requires item 19 to define boundaries

**Acceptance:** each unit type produces the same fraction totals over the same
area (a consistency check); every unit carries `{value, status, coverage}`.

### 23. Density metrics 🔓
Road length per unit area, footprint density, footprint size distribution,
spacing statistics, orthogonality index, `impervious_total`.

**These are the inputs to morphological characterization** — formal fabric shows
large regular footprints on a gridded network; informal shows small irregular
footprints with organic paths.

**Optional extension, not gating:** temporal variance (already computed for
item 18) can plausibly separate active-construction signatures from stable
bare/vacant ground within the `bare` fraction, at low marginal cost. Not a
gate decision — a cheap addition to consider once the core density metrics
are working.

**Acceptance:** metrics computed for a known-formal and a known-informal AOI;
they separate the two without any spectral input.

### 24. Access and service indicators 🔓
Network connectivity, distance-to-nearest-paved-access per building or per block.

**Acceptance:** computed from the vector layer alone; degradation with
coverage is reported via item 20's score, not silent.

### 25. Change over time 🔓
Fraction deltas across composites.

**Why this matters:** the one capability free 10 m imagery has that VHR does not.
For an urban planning product, *"how has this area changed over eight years"* may
be the most valuable output.

**Acceptance:** deltas computed across at least two epochs for one AOI; a change
is attributable to a specific fraction (not "something changed"); the epochs'
observation quality is carried alongside so a cloud-affected epoch cannot
masquerade as change.

### 26. Rewire flood risk 🔓
Susceptibility consumes `impervious_total` rather than a discrete class; roads
enter as rasterized vector conduits at hydrology resolution.

**Deleted in this item:** the road-proximity penalty (C7, C11) ceases to exist.

**Acceptance:** susceptibility runs end-to-end on fraction input; no reference to
`paved_road` as a class remains anywhere in the flood path.

---

# PART 5 — Validation discipline 🔓

*Six items. What keeps the new system honest.*

### 27. Held-out firewall
Split the 331 human labels. A subset **never touches training** — it exists
solely to validate.

**This is the only independent signal available**, and the architecture change
does not create one. Enforce it in code, not convention.

**Acceptance:** the split is recorded in a file, hashed, and the training path
raises if it reads a held-out record.

### 28. Risk-coverage curves (replaces CAAT)
Plot risk (error rate among *accepted* predictions) against coverage as the
threshold sweeps, per fraction per city. Select an operating point rather than
taking a recall-only percentile.

**Directly answers C12's "no precision term" critique by construction**, at
near-zero cost — the outputs already exist.

**Acceptance:** curves produced per city; a chosen operating point is documented
with its risk and coverage; the choice is reproducible from the curve.

### 29. Provenance enforced in code
Every calibration artifact records `source_checkpoint` (hash, not filename),
calibration date, and input regime. **The loader refuses mismatches.**

**Do not leave the strict validator in dead code again** — that was C10's root
cause. Delete or promote; do not maintain two.

**Acceptance:** loading a mismatched artifact raises; the current deployed CAAT
file fails this check until recalibrated.

### 30. Test logit adjustment *(conditional)*
**Only if any discrete classification step remains.** If any class has both a
large prior and a spectrally generic feature, the magnet returns. Under
Decision 11, fractions have no argmax step, so this is not expected to apply —
retained as a conditional item, not deleted, since the condition is about
future code, not current design.

If it applies: subtract `τ·log(π_y)` before softmax, tune `τ` on a held-out city.
**Check per-city prevalence first** — a single global `τ` under- or over-corrects
if cities differ substantially.

**The ablation worth running regardless:** correct the prior, then check whether
precision improves. If it does not, the residual is feature genericness — direct
evidence for the sub-pixel argument.

### 31. Build the gold set
300–500 stratified points labelled against the highest-resolution imagery
available.

**Now validates fractions, not labels** — a different task than before. A point
becomes "this 10 m cell is approximately X% built, Y% vegetation."

**Where:** Kibera, Accra, Lagos, Dhaka have free VHR. **Dharavi does not** — treat
it as a transfer target, not a training site, for anything needing high-res truth.

**Note on sequencing:** item 21 now carries its own smaller 2–3 city pilot
validation, run before the rest of Part 4. This item remains the fuller
300–500 point gold set, run after Part 4 as originally sequenced — the pilot
is a fast early gate, not a replacement for this item.

**Honest caveat to record:** basemap imagery has a different acquisition date
than the Sentinel-2 composite, introducing temporal mismatch in fast-changing
settlements. Real, must be documented, and still far better than no reference.

### 32. Intra-annotator test-retest
Relabel a random subset blind, weeks apart. Report intra-rater agreement.

**Substitutes for inter-rater reliability, weakly.** It is not Cohen's kappa and
does not mean the same thing. Say so.

---

# PART 6 — Epistemic contract 🔓 *(Decision 14 settled — see translation note)*

*Seven items. The single highest-leverage cluster — nine findings from one
convention.*

**Translation note, required reading before starting this part:** items 33–39
below were originally specified in the vocabulary of the deleted CAAT-era
pipeline (`category_area_pct`, `unknown_pct`, discrete-class language).
Decision 14 replaces that with: known-pixel denominator, mandatory
`observed_fraction` field, and three separately-reported non-observation
fields (shadow, cloud/nodata, low-confidence unmixing) rather than one merged
"unknown." Read each item below against that fraction-pipeline vocabulary,
not the classification-pipeline vocabulary the original text may still
suggest. See `04_FINDINGS_LEDGER.md`'s Part 6 translation note for the full
mapping.

### 33. C19 — denominator + `observed_fraction`
Apply Decision 14's convention. **Emit `observed_fraction` as a mandatory
sibling field** — fixing the denominator alone just moves the bias. Emit
shadow / cloud-nodata / low-confidence-unmixing as three separate fields,
never merged.

**Acceptance:** no derived physical quantity is emitted without its coverage
sibling; the three non-observation components are independently readable, not
summed into one number by the producer.

### 34. C21 — `hydrological_surfaces.py` status field and failure path
The only module in the analysis chain with neither. That single omission produces
C19, C21, and C25, and makes two separate guard clauses vacuous.

**Acceptance:** a synthetic all-unknown AOI produces `insufficient_evidence`
throughout rather than `score: 0.0, class: "very_low"`. **The two dead
`insufficient_evidence` branches at `applicability.py:133` and
`waterlogging.py:57` become reachable and are unit-tested.**

### 35. C25 / C26 — ward coverage fields
Emit per-ward `observed_fraction` and valid-pixel count, per Decision 14's
convention. C26 is what makes C25 detectable.

**Acceptance:** a 100%-unobserved and a 50%-unobserved ward are distinguishable
from the output alone, without inference.

### 36. C33 — absent ≠ measured-zero
`null`/absent and `0` must be distinguishable end to end. Absent renders as "—"
or "not measured"; zero renders as "0.0%".

**Copy the existing correct pattern** — `road_access_score === -1` → "N/A", and
the gated modules' status pills. Do not invent a new one.

### 37. C22 — no-data must not collide with real classes
The surviving defect: no-data scores identically to `standing_water` and
`active_construction`. Give it a distinct render state — never a value on the
susceptibility scale.

*Requires a nodata mask propagated from ingestion through to render, which may be
the larger part of the work.*

### 38. C27 — timeout ≠ tier
Preserve the error at the ward boundary. A timeout must produce
`status: "timeout"`, **never a tier**.

**Acceptance:** two consecutive runs of the same wards produce identical tiers,
or explicitly differing `status` fields explaining why.

### 39. C15 — derive the claim, do not latch it
Compute `osm_available` and the reliability claim **from the actual outcome**,
after the map is built.

**The general principle:** a claim must be derived from an outcome, never
asserted ahead of it. Same shape as C37.

---

# PART 7 — Gating architecture 🔓

*Three items. One signal that currently dies three times.*

### 40. C14 / C20 — `applicability` gates downstream
1. Move the computation **before** `hydrological_surfaces` (currently
   `pipeline.py:412` then `:413` — backwards)
2. Pass it into every downstream consumer — susceptibility ×5, exposure, risk
3. Each consumer decides: refuse to compute, or compute-and-flag. **Prefer
   compute-and-flag** — refusing loses information; flagging preserves it
   honestly
4. Model the dependency chain between mechanisms rather than treating them as
   independent branches

**Acceptance:** given a synthetic result with `out_of_distribution: true`, assert
**every** susceptibility/exposure/risk block contains the flag.

### 41. C32 — render it
Surface `applicability` as a prominent banner, not a buried field. Add to
`NAV_SECTIONS`.

**Acceptance:** an AOI that trips `out_of_distribution` produces a UI where the
user cannot miss it.

### 42. C23 / C24 — Gate C waiver on all paths, rendered
`product_validation_status` must be present on the `not_calculated` path too, and
the frontend must read it.

**The susceptibility panel already does this correctly, in the same file.** Copy
that pattern. Low effort, high integrity value.

**Note:** this is distinct from Decision 17's Gate C closure (advisor review
against D.7). This item fixes how the waiver *status field* propagates through
code; Decision 17 settles how Gate C itself is *validated*. Both are needed;
neither substitutes for the other.

---

# PART 8 — Contract enforcement 🔓

*Five items. Rules that comments cannot enforce.*

### 43. C31 — single-source palette
**The quick fix is copying values across. The correct fix is a single source of
truth** — emit the palette into `result.json` from the backend and have the
frontend read it, so drift becomes structurally impossible.

**Acceptance:** changing a colour in the backend changes the legend with **no
frontend edit.**

### 44. C4 — assert band order at runtime
Verify against the file's actual band descriptions at load time, not a
top-of-file comment.

### 45. C10 — enforce `source_checkpoint`
Make the loader **refuse** thresholds whose source does not match the loaded
model. **Delete the dead stricter validator or promote it — do not leave two.**

### 46. C13 — full-AOI basemap, or remove the field
Either write a full-AOI RGB basemap (nothing correct currently exists for
`primary_tile` to point at), or remove the field. And correct the in-code comment
claiming the projection "works unchanged regardless of how many tiles" — false
for the base image.

**Note on severity:** downgraded under Decision 15 (confirmed no live
consumer), but the downgrade does not remove this item — severity and fix
priority are separate axes.

### 47. C34 — validate `run_id` at the read boundary 🔓 *(new, added during consolidation)*
`GET /api/runs/{run_id}` constructs a path from an unvalidated parameter — same
bug class as C16, a read sink rather than a write sink. Previously unscheduled;
added here alongside C4/C10/C13 as the same "trust boundary enforced only by
convention" shape.

**How:** same whitelist approach as C16's fix — `[a-z0-9_-]{1,64}`,
`HTTPException(400)`, reject-not-sanitize, applied at this endpoint
specifically. Test percent-encoded, mixed-separator, and absolute-path
variants — none of which were tried during the original finding.

**Acceptance:** verified against the unpatched endpoint first, same discipline
as C16 (a test that cannot fail against broken input is decoration). Also
address C35 in the same pass — `WATCHED_AOIS` bypasses the API boundary
entirely, so "validated at the boundary" must be confirmed true everywhere
`run_pipeline` or path construction from a label can be reached, not just at
the two originally-known sinks.

### 70. C40 — authenticate the API boundary ✅ *(new, added during the pre-push audit)*
`api.py` has no authentication on any of its 8 endpoints. **Pairs with item 47**:
C34/C35 validate *what* crosses the trust boundary, this establishes *who* may
reach it at all. Same "trust boundary enforced only by convention, not code"
shape as C4/C10/C13/C34.

*Numbered 70 rather than 48 because Part 9's deleted items historically occupied
48–50, and 69 is the highest live item. It sits in Part 8 out of numeric
sequence deliberately — the part it belongs to is contract/trust-boundary
enforcement, and the pairing with item 47 above is what governs sequencing, not
the integer.*

**How:** a single shared secret checked at the perimeter — 401 on missing or
wrong, reject-not-sanitize. Secret from the environment with a loud startup
failure if unset: the same "fail loudly" discipline `gee_client.py` already
uses, and subject to the same gap `archive/AUDIT_FINDINGS.md` records against it
— *validate that the variable is actually set, do not pass `None` through*.

**AMENDED DURING BUILD — the enforcement mechanism is middleware, not
`Depends`.** This item originally specified a router-level dependency
(`FastAPI(dependencies=[Depends(...)])`). That was measured insufficient before
implementing: an app-level dependency covers routes on the app router but does
**not** cover `app.mount(...)`, because a Mount is a separate ASGI application
that FastAPI's dependency system never enters. Probed directly — with
`FastAPI(dependencies=[Depends(gate)])` a route returned **401** while a mounted
`StaticFiles` path returned **200 and served the file**. `api.py` mounts `/runs`
over `data/pipeline_runs/`, serving landcover rasters, confidence maps and run
artifacts: **the same data C34 would disclose.** A dependency-only fix would
have closed the front door and left that one open, while reading as complete.

Middleware is therefore the enforcement point — the only mechanism that sits in
front of routes *and* mounts, so coverage is a property of the perimeter rather
than of remembering to decorate each new endpoint. `APIKeyHeader` is still
declared, but for the OpenAPI document only; it documents, it does not enforce.
Registered **after** `CORSMiddleware` so it is outermost (Starlette runs the
last-added middleware first), with `OPTIONS` exempt so CORS preflight — which
browsers send without credentials by design — still reaches the CORS layer.

Router-level, not per-endpoint, so a future endpoint is covered **by default
rather than by remembering**. That is the structural lesson of C35: the
scheduler reached `run_pipeline` without ever crossing the boundary that was
believed to protect it, because protection was applied at call sites rather than
at the perimeter.

**Do not rely on CORS.** `api.py:22` restricts origins to
`http://localhost:5173` and `http://localhost:3000`, which is browser-enforced
and therefore no obstacle to `curl`, a script, or any non-browser client. It is
not an access-control mechanism and must not be counted as one.

**Acceptance:** verified against the unauthenticated endpoints **first**, same
discipline as C16 and item 47 — a test that passes before the fix is decoration.
Specifically assert that `POST /api/scheduler/trigger` returns 401 without a
credential, since that is the amplification path: one unauthenticated call fires
`run_pipeline` across all of `WATCHED_AOIS`, three GEE-backed runs on metered
quota. Confirm coverage by **enumerating the live route table**, not a
hand-written endpoint list, so a later-added endpoint cannot silently escape the
check.

**Sequencing: build item 70 before item 47.** Item 47 narrows what an anonymous
caller may pass through the boundary; item 70 removes the anonymous caller. If
only one ships, item 70 reduces C34's exposure more. `04_FINDINGS_LEDGER.md`
documents C34's sink, file, line, and explicitly which attack variants were
*not* tried — detail that is safe only while the repo is private and the
endpoint is unreachable, and item 70 is what makes reachability a decision
rather than an accident.

**Built.** `tests/test_api_authentication.py`, 46 tests, all passing. Verified
against the unpatched `api.py` first: **31 failed, 3 passed**, and the 3 are the
ones that should pass either way — one structural precondition guard, and two
`must NOT be 401` preflight assertions. No test asserting the security property
passed before the fix. Route coverage is enumerated from the **live route
table** (`app.routes`), not a hand-written list, so a future endpoint joins the
suite automatically. C16's 72 tests still pass; its client fixture is now
authenticated, because an unauthenticated request stops at 401 and would never
reach `aoi_label` validation — leaving it anonymous would have made every C16
assertion pass for the wrong reason. **C35 is not yet closed by this item**: the
perimeter now covers everything reachable over HTTP, but the scheduler calls
`run_pipeline` in-process, which is not an HTTP path. That remains item 47's
scope.

---

# PART 9 — SAM-conditional items — **DELETED per Decision 12** 🚫

*Four items. Decision 12 settled: SAM is deleted. Do not build any of the
below.*

**Numbering note.** These four originally carried numbers 47–50. Part 8's live
item 47 (C34 — validate `run_id` at the read boundary) collided with the first
of them, so the numbers are struck from this part rather than renumbering any
live item. **Item 47 means C34, in Part 8.** The historical numbers are recorded
inline below so references in older documents remain traceable. Numbers 48–50 are
retired and must not be reused.

**What replaces the one real gap this part would have addressed:** if
per-object tracking of non-building features (primarily standing water, for
flood-relevant directional growth) becomes a stated requirement later, the
mechanism is **connected-component labeling on thresholded unmixing-fraction
rasters** — not SAM, not the items below. Not built now; named here so the
gap in this part isn't mistaken for an oversight.

~~### C9 — stable IDs at mask creation~~ — deleted with SAM. *(was item 47 in the pre-Decision-12 numbering; the live item 47 is C34 in Part 8)*
~~### C30 — geometry check, not set membership~~ — deleted with SAM. *(was item 48)*
~~### C28 — unfreeze annotation~~ — deleted with SAM; annotation moves to
stratified points (item 31) regardless. *(was item 49)*
~~### C39 — corrupted annotations + input validation~~ — deleted with SAM. *(was item 50)*

---

# PART 10 — Trust boundaries 🔓

*Three items. Validate at the edges.*

### 51. C1 — mask from SCL, not QA60
The codebase **already computes SCL correctly** in `compute_observation_quality`.
Two code paths that were never joined. Then feed `observation_quality` into
`applicability` (item 40 is already rewiring it).

**Sequencing — this item must run before item 18** (temporal variance), not
independently as originally ordered. Std-dev is maximally sensitive to
exactly the cloud-leakage outliers this fix prevents.

### 52. C2 — validate the export; reconcile the size gap
Assert dimensions, band count, and CRS against what was requested; fail loudly on
mismatch. Then reconcile `MAX_AOI_AREA_KM2 = 100.0` against `tiler.py`'s
documented "< 5 sq km" — **a 20× gap documented in one file and contradicted in
another.** Raise the tiler's real capability or lower the API cap; do not leave
both.

### 53. C8 — INFORM validation + frontend guard
Validate numeric and in-range at read time; an invalid cell yields
`status: "unavailable"`, not `"available"`. **Use the `PCT_MISSING`/`RELIABILITY`
columns that are already read and currently unused.** And guard the frontend
render — `App.jsx:568/572` currently renders `raw_score` with no type check.

---

# PART 11 — Error convention 🔓

*Two items.*

### 54. C18 — in-band errors detected in-band
Pick one convention and use it consistently across the boundary. **Recommended:**
raise on programmer error and integration failure; return status dicts only for
genuine data absence. Then make the scheduler check the thing that is actually
signalled.

### 55. Distinguish exception classes
Catch specific types. Where a broad catch is genuinely right, **record the
exception class in the output** so "broken integration" and "no data here" are
distinguishable downstream.

*This is the shared root cause behind several individual findings across
`hydrology.py`, `coastal.py`, `rainfall.py`, and `vulnerability_sources.py`.*

---

# PART 12 — Hygiene 🔓

*Four items. Individually cheap, collectively substantial.*

### 56. C17 — sort by timestamp
Parse the timestamp; do not sort strings. **And exclude `*_test_*` runs from the
demo endpoint entirely.**

### 57. Delete dead code
`resnet_classifier.py`, `resnet_model.py`, `classifier.py`,
`run_event_hazard_analysis`, the duplicate `decode_mask_rle` in
`verify_masks.py`, the duplicated `GeoWatchResNetSeg`.

**Removes roughly a dozen Moderates at once**, and removes the trap where the
correct provenance check lives in a file nothing imports (C10's root cause).

### 58. Frontend as pure renderer
Renders `result.json` and computes nothing. Remove: hardcoded category lists,
recomputed aggregates, invented thresholds, truncated caveat lists, the hardcoded
Q1-2024 date window, and **the `?? 291 / ?? 257` fallback — verified as exactly
Dharavi's `tile_dimensions`. If the field were ever missing, every AOI worldwide
would be projected through Dharavi's grid, silently.**

### 59. `batch_run_log.json` — append, don't truncate
Each invocation currently truncates; the 11-city history was clobbered by a later
single-city run.

---

# PART 13 — Documentation and publication 🔓

*Nine items.*

### 60. Model card
Mitchell et al. template. Training data, class definitions, LOCO protocol, known
failure modes, intended use, **out-of-scope uses**.

**Must state Decision 16 explicitly:** this is a research-audience
contribution, not a validated planning tool. Outputs should be framed as
"here is why this should be trusted" rather than "a planner validated this."

### 61. Datasheet
Gebru et al. template, covering the training data.

### 62. Provenance Reconstruction — a named section
Document how the production checkpoint's training notebook was identified, by
fingerprinting four independent config values against checkpoint metadata.

**This does not recover history — it recovers auditability**, which is the actual
function git history serves. Frame it as a named subsection, not a footnote.
Reviewers respect a documented forensic process far more than silence.

### 63. Written labeling guide
The exact decision rules the annotator followed, including edge cases. **This is
the standard substitute for inter-rater statistics in small studies** and is
broadly accepted when explicit.

### 64. Gate C protocol — written, unrun
Write the study design — recruitment, task, metrics — whether or not it gets run.
Disclose non-execution explicitly as an access constraint.

**Per Decision 17: this is not Gate C's closure mechanism** — Gate C itself
closes via structured advisor/faculty review against D.7's five reporting
requirements (item 65 below documents that review). This item is the
real-planner protocol, filed as documented future work, disclosed as blocked
by access rather than by design choice.

### 65. Gate C — advisor review write-up *(new, added during consolidation)*
Document the structured advisor/faculty review against D.7's five
requirements (confusion matrix before/after, per-class accuracy before/after,
separability analysis, WorldCover/Dynamic World comparison, causal mechanism
tied to resolution) that formally closes Gate C per Decision 17. This is the
record of the review that actually happened, distinct from item 64's unrun
protocol for the review that could not happen.

### 66. Susceptibility dependency DAG
Plus a correlation matrix across the AOIs. **Directly defuses the "four of five
layers agree, therefore convergent evidence" misreading** — they are driven by
two shared inputs, normalized by three provisional ceilings, and reported with
byte-identical class breaks. Probably a figure in the paper.

### 67. Population from two sources, as a range
WorldPop and GHS-POP disagree ~7.6% at 2020 over the same AOI. **Report the
range, not a point estimate.** More honest, costs nothing.

Record the constraint: no enumerated Indian microdata before 2027–28.

### 68. Email Planet re: publishing rights
Ask explicitly whether annotated masks and model weights derived from
PlanetScope may be published openly — **before annotating anything on it.**

**This is a real strategic constraint, not a formality:** an open annotated
benchmark for informal-settlement land cover would be a stronger contribution
than another model, and Planet's terms partly foreclose it. Sentinel-2 does not
have this problem.

### 69. Literature table
Columns for resolution, protocol (within-city split vs cross-city LOCO vs
cross-region), and class count — showing **no directly matched benchmark
exists.**

That gap is itself a finding about the state of the field, and more valuable than
a possibly-misleading number-to-number comparison.

---

# Never build

`C7` · `C9` · `C11` · `C12` · `C28` · `C29` · `C30` · `C39` ·
`CONFUSION_PAIRS` · `CLASS_WEIGHTS` mismatch · `W1` · `W2` · `W3` · `W4` ·
`C3` *(the finding — the 6-band tiler itself is a Part 4 prerequisite, see
item 21)* · `C6` *(→ item 20)* · `audit_roofing_labels.py` repair · all four
of Part 9 (SAM-conditional)

---

# Working practices

Carried from what worked during the audit.

**Investigate → plan → implement → review, as separate instructions.** The single
best moment of the audit was catching a wrong "CONFIRMED" verdict by verifying one
level further down. Fixes deserve the same skepticism.

**Every fix ships with a test that would have caught the bug.** The deepest
lesson here is that this codebase's safety nets — `verify_masks.py`,
`applicability`, `check_generated_water_mask.py`, the palette comment — were all
*written* and all *non-functional*. A fix without a regression test recreates
that pattern.

**The test for a test: does it FAIL against the broken input?** This is why the
C16 fix was verified against the unpatched file (70 failed, 2 passed). If a check
cannot fail, it is decoration.

**Derived figures must name the operation that produced them.** Both spot-check
defects were derived numbers presented as measured ones, and **both would have
survived a line-reference audit.** Verifying a citation establishes almost
nothing about whether the number attached to it was measured or inferred.

**Scope every task explicitly** — which files, and what not to touch. The audit's
best work came from bounded prompts; its worst moments came from unbounded ones.

**Record dead ends.** `03_EVIDENCE.md` exists so nothing gets re-investigated.
Every question already settled should be answered from there.

**Decide once, build once.** Part 3's seven decisions took real calendar time
and no code. That was correct — every item in Parts 4-13 that would have been
built against the old, unsettled framing would have needed rework once the
decisions landed.

---

# Realistic timeline

Part-time alongside coursework:

| Part | Effort | Notes |
|---|---|---|
| 1–2 | ✅ done | |
| 3 — Decisions | Complete | All seven settled |
| 4 — Architecture | ~6 weeks | Item 18 first (after 51); 21 is the risk, pilot validation gates it |
| 5 — Validation | ~1 week | |
| 6 — Epistemic contract | ~1 week | Highest leverage; read the translation note first |
| 7–8 — Gating, contracts | ~1 week | Includes new items 70 (C40) and 47 (C34/C35), in that order |
| 9 — SAM-conditional | 0 | Deleted per Decision 12 |
| 10–12 — Boundaries, hygiene | ~1 week | |
| 13 — Documentation | ~1.5 weeks | Do not leave to the last week; includes new item 65 |

**Roughly 12–14 weeks part-time from Part 4 onward, and treat that as a lower
bound.** Solo projects with research components routinely run 1.5–2× over.

**The temptation will be to skip straight to typing code.** Part 3's decisions
are why Part 4 can be built once instead of twice.
