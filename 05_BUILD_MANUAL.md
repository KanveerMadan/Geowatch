# GeoWatch — Build Manual

**All 13 parts, all 68 items. What to build, how to build it, and how to know it
worked.**

Read `01_DIAGNOSIS.md` and `02_ARCHITECTURE.md` first. Check
`04_FINDINGS_LEDGER.md` before starting any item — roughly a third of the
original findings are deleted rather than fixed.

**Check `08_STATE.md` before picking an item.** Several items marked 🔓 here are
already complete on an unmerged branch — Part 7 (40–42) and Part 8's 43, 44 and
45 all landed on `applicability-gating` — and item 46's fork is already decided.
Statuses in this file reflect `master` only. For item 21, read `07_ITEM_21.md`
first: it ran, and it did not pass in the form specified below.

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

### 11. Fraction taxonomy ✅ **SETTLED — AMENDED 2026-09-23, signed off**

> **Amendment adopted 2026-09-23.** The governing principle below — *measure
> disjoint things, derive overlapping ones* — survives the item 21 pilot
> unchanged and is if anything vindicated by it. What the evidence contradicts is
> **which** quantities are measured and which derived: this decision measures
> `built` and `paved` and derives `impervious_total`, but `built` vs `paved` is
> separated by only **1.70°** of spectral angle against a ~0.7° noise floor and
> is therefore unidentifiable, while `impervious_total` is recoverable
> (ceiling R² 0.822 vs 0.490). The proposal is to measure `impervious_total`,
> take `built` from vector footprints directly, and derive `paved` — same
> principle, reversed assignment. See item 21 and `06_UNMIXING_CEILING.md`.
>
> The note below that "`built` vs. `paved` is the weakest boundary of the five"
> was directionally right and understated: it is not weak, it is unidentifiable.
> **SIGNED OFF 2026-09-23.** The amendment described above is adopted; this
> decision is settled again as amended. `02_ARCHITECTURE.md` is corrected to
> match.
>
> **Second amendment, DECIDED 2026-09-24 (planning session): five fractions
> become eight.** Recorded here for the first time. The block below the rule is
> the pre-2026-09-24 list, kept for provenance; the current list follows it.
> Full record: `02_ARCHITECTURE.md` §3 "The taxonomy expansion".

*Superseded 2026-09-24 — the original five:*

    Fractions (disjoint, sum to ~1):
    built — roofed structure
    paved — hard surface, unroofed
    vegetation
    water
    bare — permeable unpaved ground

    Derived:
    impervious_total = built + paved

**Current — eight fractions, disjoint, summing to ~1 on the known-pixel
denominator (Decision 14):**

    built                  — building footprints (vector)
    paved                  — derived: impervious_total − built.
                             SEALED unroofed surface only: asphalt,
                             concrete, tiles, laid stone
    vegetation
    water
    bare                   — residual. Unsealed ground, INCLUDING compacted
                             ground (dirt roads, gravel, compacted yards)
    snow_ice               — NEW: permanent only (spectral + low temporal variance)
    solar                  — NEW: own fraction
    mixed_water_vegetation — NEW: wetlands, mangroves, mudflats/tidal, water hyacinth

    Derived:
    impervious_total = built + paved        (unchanged; solar DEFERRED — see below)

    hard_surface_remainder = 1 − (vegetation + water + snow_ice + solar
                                  + mixed_water_vegetation)
      — on the known-pixel share only (~~shadow-renormalised~~, struck
        2026-09-24: there is no shadow term to renormalise out)
      → split by the item 21 regressor into impervious_total and bare

    Producers, all run BEFORE the remainder is computed (added 2026-09-24):
    vegetation, water      — spectral regression (item 21, signed off 2026-09-23)
    snow_ice               — spectral signature + low temporal variance
    solar                  — spectral-signature detector
    mixed_water_vegetation — spectral + dataset sub-typing (GMW, GLWD)

*Amended 2026-09-24: the formula as first recorded ended `+ shadow)`. That
term is ~~struck~~ because it counted shadow twice: subtracted here, and
removed from the denominator by Decision 14. See the shadow rule below.*

- **`paved` is sealed surfaces only** *(amended 2026-09-24)*. The definition
  in `02_ARCHITECTURE.md` §3 read *"Hard surface, unroofed — paving,
  hardstanding, courtyard, ~~compacted yard~~"*. Compacted yard is struck.
  **Unsealed ground, even if compacted, is `bare`.** Hard-case rules:
  `LABELLING_GUIDE.md` §4.
- **`snow_ice`** is permanent snow/ice only. Transient snow is occlusion, like
  cloud.
- **`solar`** is its own fraction. **Whether it is added to
  `impervious_total` is DEFERRED** until real-world solar prevalence is
  measured in the validation data.
- **`mixed_water_vegetation`** is sub-typed via Global Mangrove Watch and the
  Global Lakes and Wetlands Database, and feeds the flood model (item 26) as
  **its own hydrological input, weighted by sub-type**.
- **Ceiling checks, 2026-10-28** *(recorded only; no decision changed, no
  status flipped)*. `06_UNMIXING_CEILING.md` Part 8 measured all three new
  fractions by Part 3's method against a pre-registered bar (R² ≥ 0.70
  label it, < 0.50 don't, between indeterminate): **`snow_ice` 0.925, label
  it. `solar` 0.677, indeterminate; rooftop solar at realistic panel shares
  0.436, don't label it. `mixed_water_vegetation` 0.368, and the
  pre-registered rule issued no verdict** because the class drops
  vegetation's own ceiling from 0.974 to 0.634. Whether these change
  Decision 11 is a human call (C60, C61 under NEEDS FATE).
- **The hard-surface remainder now subtracts `snow_ice`, `solar` and
  `mixed_water_vegetation`** in addition to vegetation and water ~~and
  shadow~~.
- **Shadow rule (LOCKED 2026-09-24): each pixel is handled one way, never
  both.**
  - **Fully shadowed pixels are occlusion.** They are removed from the
    known-pixel denominator (Decision 14's observability group) and are
    **not** subtracted in the remainder.
  - ~~**Partially shadowed pixels get a sub-pixel shadow term** in the solve,
    renormalised out (Decision 13's sixth term). It is **never reported as a
    fraction** and never touches the denominator.~~ **Amended 2026-09-24:**
    partially shadowed pixels **stay in the known-pixel denominator with no
    explicit shadow term.** The regressors are trained on hand labels that
    include partially shadowed pixels, so robustness to partial shadow is
    learned. (The struck version needed an unmixing solve; the design is
    regression, and a proposed "layered" stage-1 solve to host the term was
    withdrawn without being decided.)
  - Shadow therefore appears nowhere in the remainder formula.
  - **Partial shadow is tested, not assumed.** The Makoko/Kibera/Rocinha
    labelling pass marks it separately. **If validation shows learned
    robustness fails, a dedicated fix is added then, with evidence.**
  - **Open:** where the full/partial boundary sits is not yet decided. The
    same labels supply the evidence.

**Folded into existing fractions — metadata flags only, no new fraction:**
sports fields / golf courses / parks / farmland → `vegetation` with OSM sub-type
flags (sports fields also get a secondary, confidence-flagged synthetic-turf
spectral check); sand, salt flats, rock / bedrock / volcanic rock, dry lakebeds,
dirt tracks / unpaved parking, landfills, quarries → `bare` with OSM or
geographic-plausibility flags; docks → `built`.

**Occlusion — no fraction:** cloud, shadow, transient snow, fire/smoke of all
kinds, ships. Decision 14's observability group.

**Feature / context layers — not fractions, all per-pixel, many per AOI:**
volcano (named via Smithsonian GVP match — no confidence flag on a database
match; Copernicus DEM as secondary shape confirmation; the underlying surface
still counted in its real fraction); terrain (flat / hilly / mountainous from
DEM slope + elevation, reported as a distribution per AOI). Named mountain
ranges: not built (optional cosmetic later).

**New datasets:** Global Mangrove Watch, Global Lakes and Wetlands Database,
Smithsonian GVP, a second building-footprint source (Microsoft or OSM
buildings) for `built` confidence, regional geological data where available,
expanded OSM `landuse` tags.

**Volcanic hazard module:** parked as a future sixth hazard module, not
specified.


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
~~five~~ eight fractions answer land-cover proportion and imperviousness. They do not
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
**connected-component labeling on thresholded ~~unmixing-~~fraction rasters** *(2026-09-25; mechanism unchanged)* —
threshold the `water` fraction, run connected components, get labeled,
pre-typed objects with no separate mask-vs-segment ID synchronization problem
to fail (the exact failure mode that produced C9).

**Named as a deferred, unbuilt forward reference — not scope now:** if
per-object tracking of non-building features becomes a stated requirement, the
mechanism is connected-component extraction on ~~unmixing~~ fraction rasters. Not SAM. Not
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

### 13. Global endmember strategy ✅ **SETTLED — Option D, AMENDED 2026-09-23 (signed off); AMENDED 2026-09-24: no unmixing endmember — optional regressor feature, gated by LOCO ablation**

> **The pilot this decision required has run, and it falsified the decision's
> central assumption.** Both risks this decision left explicitly open (below)
> have now fired. `built` and `paved` are separated by **1.70°** of spectral
> angle against a ~0.7° sensor noise floor, so the constrained extraction cannot
> produce a usable `built` endmember for informal fabric by any method — three
> extraction families were tried and failed, and the failure was then shown to
> be an information limit rather than a method problem.
>
> Worse than a null result: the institutional-roof endmember this spec would
> actually produce sits **4.69°** from `paved`, versus **1.66°** for a realistic
> informal-roof endmember. **Following this spec manufactures separability that
> does not physically exist**, yielding a confident-looking split that is an
> artifact.
>
> The text below is preserved for provenance. Evidence:
> `06_UNMIXING_CEILING.md`, `07_ITEM_21.md`.
>
> **RE-SETTLED 2026-09-23 as amended:** ~~one `impervious_total` endmember rather
> than a `built`/`paved` pair;~~ `built` from vector footprints, not unmixed at
> all; `paved` derived by difference with explicit uncertainty. The re-scope is
> adopted, not merely proposed, and `unmixing-ceiling-investigation` is merged.
>
> **AMENDED 2026-09-24 — there is no unmixing endmember.** Under the recorded
> design, vegetation, water and `impervious_total` are **spectral regression**
> (item 21 table, signed off 2026-09-23). No unmixing solve exists, so no
> endmember enters one. The "one `impervious_total` endmember" clause above is
> struck.
>
> **The local paved endmember is repurposed as an OPTIONAL regressor
> feature.** The feature is the per-pixel spectral angle to the AOI's *own*
> local paved endmember. It acts as a per-city calibration reference.
>
> - **Default: the regressor is built WITHOUT it.**
> - **Ablation:** during leave-one-city-out on the training cities, train with
>   and without the feature. **Keep it only if it measurably improves
>   cross-city transfer; otherwise retire it.** "Measurably" follows the
>   working rules in `08_STATE.md`: paired per-fold comparison, per-city
>   reporting, and no rounding a within-noise result up.
> - **If kept,** the 2026-09-24 endmember-stability findings (item 21) define
>   how it is built: extraction is local, buffer radius 0, n\* measured per
>   AOI, bootstrap with independent pairs.
> - **If retired,** that apparatus becomes historical record, and Decision 13
>   has no live subject beyond `built` from footprints and `paved` by
>   difference.
>
> Everything below the rule, including "The split" table, is the original
> unmixing spec, preserved for provenance.

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
same separated-reporting logic to cloud/nodata and ~~low-confidence unmixing~~ the regression prediction interval *(renamed 2026-09-25, Decision 14 (b))*.

**Reflectance precondition — tightened.** BOA surface reflectance is already
available via `COPERNICUS/S2_SR_HARMONIZED`. The precondition is not
"obtain reflectance," it is: **~~unmixing~~ the regression inputs *(2026-09-25)* must read the float32 multi-band tile
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

### 14. `category_area_pct` denominator ✅ **SETTLED — reasoning intact; amendment SIGNED OFF 2026-09-23**

> **Amendment adopted 2026-09-23.** The core of this decision — known-pixel
> denominator, mandatory `observed_fraction` sibling, and above all the rule
> that distinct causes are never merged — survives the item 21 pilot untouched,
> and the anti-merging rule is *strengthened* by it. What breaks is narrower:
> **two of the three named components delegate to mechanisms that no longer
> exist**, because Decision 13 is reopened. Four changes follow, and all four are
> **signed off**. Evidence: `06_UNMIXING_CEILING.md`.
>
> A fifth, added at sign-off: **`paved`'s derivation uncertainty is its own
> reported quantity.** It belongs in the *estimate quality* group of (c), never
> in the observability group — a derived value is not an unobserved one.
>
> **(a) Shadow's mechanism is orphaned.** This decision delegates shadow to
> Decision 13 — *"solved as a sixth endmember term; five fractions renormalize
> over the illuminated portion."* Under the item 21 re-scope there is no
> unmixing solve and therefore no sixth term, so the field has no producer and
> "illuminated portion" has no definition. A standalone shadow estimator is
> needed (SCL class 3 plus solar geometry is the obvious candidate). Note also
> that shadow is shakier than this decision assumes: the B-decomposition test
> asked directly whether a dark spectrum was material or material-plus-shadow
> and returned **indeterminate at 6.5–9.7% residual** across three independent
> shadow references. Whatever produces this field should carry that caveat.
>
> **(b) "Low unmixing confidence" needs redefinition — and improves.** It is
> currently specified as *"pixels where the solve is poorly constrained against
> the endmember model."* With no solve and no endmember model, the field has no
> definition at all. Under regression it becomes a genuine **prediction
> interval** (quantile regression or ensemble spread), which is better founded
> than a residual against a simplex. Rename accordingly; the concept survives
> and strengthens.
>
> **(c) The taxonomy should split into two groups, along an axis already latent
> in it.** This decision is fundamentally about **the denominator**: what counts
> as observed. Shadow and cloud/nodata *remove a pixel from the denominator* —
> that is what makes them observability. Estimate quality does not: such a pixel
> was validly observed, stays in the denominator, and merely carries wide
> uncertainty. The seam already exists here — the third field explicitly says it
> is *"not folded into either the fractions or the coverage number"*, i.e. it is
> already an estimate-quality field listed among two denominator-defining ones.
>
> | group | fields | touches the denominator? |
> |---|---|---|
> | **Observability** | shadow, cloud/nodata → feed `observed_fraction` | **yes — these define it** |
> | **Estimate quality** | per-fraction confidence / prediction interval | **no — never** |
>
> Keeping them in one list invites a consumer to subtract ambiguity from
> coverage, shrinking the denominator and reintroducing **exactly the C19 bias
> direction** (less observed area silently reading as less flood-prone). That is
> this decision's own founding failure, recreated one level up.
>
> **(d) The impervious/bare finding enters as a confidence marker on
> `impervious_total` — NOT as a member of the observability list.** Measured
> directly rather than inferred: ceiling R² **0.822** at documented S2 noise,
> and **0.737** even in a bare-dominated arid scene. That is the **weakest
> remaining boundary, recoverable**, and it inherits Decision 11's treatment of
> the weakest boundary — its own confidence marker, never presented at the same
> confidence as vegetation or water. It is explicitly **not** the
> "unidentifiable in principle" case; that claim is earned only by `built`/
> `paved` at 0.490. One conditional caveat carries with it: at 2× noise the arid
> scene falls to 0.477, so the recoverability is contingent on radiometric
> quality. Because regression emits prediction intervals natively, and those
> widen precisely where impervious/bare ambiguity bites, this likely needs **no
> new field at all** — the interval on `impervious_total` encodes it.
>
> **Downstream, flagged but deliberately NOT yet edited:** item 33's acceptance
> criterion reads *"the three non-observation components are independently
> readable"*, and the Part 6 header note at §"Part 6" describes the same
> three-field contract. If (c) is accepted, both need rewording to the
> two-group structure. ~~**Left for a separate pass once this decision's wording
> is confirmed.**~~ **Done 2026-09-25:** item 33 and the Part 6 note are
> reworded to the two-group structure, with (b)'s prediction-interval rename
> applied.
>
> **Extended 2026-09-24 (planning session) — the occlusion list, and eight
> fractions.** Recorded here for the first time:
>
> - **The observability group is now five causes:** cloud, shadow *(fully
>   shadowed pixels only — see the shadow rule below)*, **transient
>   snow**, **fire/smoke of all kinds**, **ships**. None is a fraction. All
>   remove the pixel from the denominator. The anti-merging rule applies to the
>   new ones as it does to the old: each is reported separately, never folded
>   into one "unknown". *Permanent* snow is not occlusion — it is the
>   `snow_ice` fraction (Decision 11).
> - **The fractions summing to ~1 on the known-pixel denominator are now
>   eight** (Decision 11 second amendment), not five. The field-naming
>   discipline below applies unchanged: a consumer summing the eight gets ~1
>   over the observed portion.
> - **Context layers (volcano, terrain, OSM sub-type flags) belong to neither
>   group.** They are not observability and not estimate quality; they touch
>   neither the denominator nor any fraction's uncertainty — with one
>   exception: the sports-field synthetic-turf spectral check carries its own
>   confidence flag, which is estimate quality.
> - **Shadow gets a measured accuracy.** Its accuracy is measured in the same
>   hand-digitisation pass at Makoko / Kibera / Rocinha (item 21, "Validation
>   additions") — this is the first direct measurement of the caveat in (a).
>   Full and partial shadow are labelled as separate cases so each can be
>   checked.
>
> **Shadow rule, LOCKED 2026-09-24 — the observability shadow field covers
> fully shadowed pixels only.**
>
> - **Fully shadowed pixel:** occlusion. It leaves the denominator and is
>   reported in this group's shadow field.
> - **Partially shadowed pixel:** stays in the denominator. ~~Its shadow share
>   is a sub-pixel term renormalised out in the solve (Decision 13's sixth
>   term).~~ **Amended 2026-09-24: no explicit shadow term.** Robustness to
>   partial shadow is learned by the regressors from hand labels that include
>   partially shadowed pixels. It is **never reported as a fraction** and
>   never feeds `observed_fraction`.
> - **No pixel is handled both ways.** This fixes a double count: as first
>   recorded, Decision 11's hard-surface remainder also subtracted shadow.
>   That term is struck.
>
> ~~Two points remain open. Where the full/partial boundary sits is not yet
> decided; the labelled pass supplies the evidence. And what produces the
> partial term still inherits (a)'s question — under regression there is no
> unmixing solve to host a sixth term — so the rule fixes *routing*, not the
> producer.~~ **Amended 2026-09-24:** the producer question is closed by
> having no partial-shadow term at all, so (a) stands unchanged. Its "no
> unmixing solve under regression" is correct for the recorded design. One
> point stays open: **where the full/partial boundary sits.** The labelled
> pass supplies the evidence. Partial shadow is validated separately, and
> **if learned robustness fails, a dedicated fix is added then, with
> evidence.**

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
  field. *Amended 2026-09-24 (shadow rule):* ~~reported as its own field~~ —
  the field covers **fully shadowed pixels only**, which are occlusion. ~~The
  sixth-term renormalisation applies to partially shadowed pixels~~ Partially
  shadowed pixels have no explicit term (amended again 2026-09-24): they stay
  in the denominator, are never reported, and robustness to them is learned
  by the regressors. The "sixth endmember term" in this bullet's first
  sentence is superseded with Decision 13's unmixing spec; see item 21.
- **Cloud / nodata** — genuine gaps in the composite for the observation
  window. Requires the SCL-based masking fix (item 51, C1) to be trustworthy.
- ~~**Low unmixing confidence** — pixels where the solve is poorly constrained
  against the endmember model.~~ **Regression prediction interval**
  *(renamed 2026-09-25, applying Decision 14 (b) as signed off)* —
  per-fraction prediction interval from the regressors (quantile regression
  or ensemble spread). Reported as its own field, not folded into either the
  fractions or the coverage number. Per (c), it belongs to the
  **estimate-quality** group: it never touches the denominator, unlike
  shadow and cloud/nodata.

Merging these three was the CAAT-era pathology — the same S1 collapse
(`01_DIAGNOSIS.md` §4) that produced nine findings from one design gap.
Keeping them separate lets a consumer reconstruct *why* coverage is low
(seasonal shadow vs. a cloudy acquisition vs. a genuinely ~~hard-to-unmix~~
hard-to-estimate surface) rather than only *that* it is.

**Field-naming discipline for Part 6:** the three non-observation fields must
be structurally distinct from the ~~five~~ eight land-cover fractions, so a
consumer summing built+paved+vegetation+water+bare *(+snow_ice+solar+
mixed_water_vegetation since 2026-09-24)* gets ~1 over the observed portion
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
| 11 | Fraction taxonomy | Five disjoint fractions; `impervious_total` derived; scope boundary stated. ⚠️ *Amendment proposed: measure `impervious_total`, derive `paved` — principle intact, assignment reversed* |
| 12 | SAM | Deleted; connected-components on fraction rasters deferred, named, unbuilt |
| 13 | Endmembers | Option D constrained; corrected `paved` source; shadow as 6th term, renormalized. ⚠️ **REOPENED — pilot falsified the central assumption; `built`/`paved` unidentifiable at 1.70°** |
| 14 | Denominator | Known-pixel; mandatory coverage field; shadow/cloud/low-confidence reported separately. ⚠️ *Amendment proposed: shadow mechanism re-pointed, low-confidence → prediction interval, taxonomy split into observability vs estimate-quality* |
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

> **OVERRIDDEN 2026-10-28 by the user:** build everything except item 21's
> dependencies, and label every output `validated` / `experimental` /
> `placeholder`. The validation criteria below still define `validated`. See
> `08_STATE.md`, §"Decision recorded 2026-10-28". The original note is kept
> below as the record.
>
> ### ⛔ Validation-first mandate — decided 2026-09-24
>
> **No further architecture or build progression past item 21** until two
> things are tested against **independent reference data**, with **criteria
> fixed in advance**:
>
> 1. **The land-classification architecture** — item 21's fractions, and
>    `built`.
> 2. **All five flood/hazard calculations.** These are the five
>    susceptibility modules in `susceptibility/`: pluvial, fluvial, coastal,
>    flash flood, waterlogging. `event_hazard.py` conditions some of them on
>    event forcing; it is not a sixth calculation.
>
> **Until then, every result is proposed research design, not an established
> claim.** That covers this manual, `02_ARCHITECTURE.md`, and any output.
>
> **Also decided 2026-09-24, under this mandate:**
>
> - **Land-classification criteria and guardrails** — the `impervious_total`
>   pass/fail bars, `built` validation, and regressor guardrails. See item 21,
>   "Validation criteria and guardrails".
> - **Flood validation approach (Tier 2; sites not yet chosen).**
>   - Each of the five hazard calculations is validated by
>     **discrimination**: does its score rank **observed-flooded cells above
>     dry ones, across many cells**?
>   - Reference: observed inundation extents — JRC Global Surface Water and
>     Sentinel-1 flood mapping.
>   - **Single-event anecdotes are sanity checks only**, never evidence of
>     validity.
>   - **Each hazard gets its own site or sites.** Pass criteria are fixed
>     before any run, as for item 21.
> - **Low-coverage policy for vector-dependent outputs** — tiered by output
>   type:
>   - **Outputs that stay meaningful at low coverage** (footprint density,
>     coarse `built`) are **computed with a confidence flag**.
>   - **Outputs that become misleading** (network-topology metrics:
>     orthogonality, dead-end ratio, fine connectivity) are **suppressed below
>     a threshold**.
>   - **Thresholds are set when item 20 is built.**
> - **Volcanic hazard module:** parked. The user has a specific idea to
>   discuss later. **Not specified — do not specify it.**

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

### 19. Vector road layer ✅

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

**Built 2026-10-27** (`vector/sources.py`, `vector/roads.py`, `vector/aois.py`).
*Label: `experimental` (decision 2026-10-28, `08_STATE.md`; nothing here is
`validated`).*

- **Fetch.** OSM `highway=*` through the shared C44 client, split into five
  disjoint per-tag clauses (a test pins the partition as exhaustive and
  disjoint). Each clause is cached and fetched by a 2-worker thread pool. A
  clause that hits Overpass's own query limit is re-queried on the box's four
  quarters (depth ≤ 3). A clause that cannot be retrieved is recorded as
  unavailable, never read as zero.
- **Footprints.** Open Buildings v3 where it has coverage (verified live per
  AOI), otherwise OSM `building=*` ways. The source is recorded in every
  output.
- **Widths.** `HIGHWAY_WIDTH_M_DEFAULT` is labelled *defaults, not
  measurements*. Road length does not depend on it; road area does.
- **Groupings.** Arterial, narrow (`footway/path/pedestrian/steps`) and broad
  (narrow + `service/residential/track`) are reported separately and never
  merged.
- **Negative space.** Derived only where narrow pedestrian density is below
  `NEGATIVE_SPACE_TRIGGER_KM_PER_KM2 = 1.0`, as a morphological closing of the
  footprint union (gaps up to 6 m) minus footprints and minus mapped road
  space. It is area only and never enters the network. These constants were
  fixed before the live run.
- **One source, many representations.** `lengths_km`, `road_space`,
  `rasterize`, `graph` (real OSM node ids), `blocks`, `surface_coverage` and
  `paved_status` are all methods of `RoadLayer`. Every output carries
  `source_layer_id`.

**Live run, 2026-10-27** (the Overpass primary was timing out; every clause was
satisfied by fallback endpoints, none unavailable):

| AOI | morphology | footprints | narrow km/km² | broad | all | `surface` tagged (by length) | negative space |
|---|---|---|---:|---:|---:|---:|---|
| barcelona_eixample | formal European | 4,449 OSM | 37.81 | 45.07 | 66.84 | 91.7% | not triggered |
| chandigarh_central | formal Asian | 11,266 OB | 2.25 | 18.55 | 25.92 | 75.5% (narrow 1.4%) | not triggered |
| dharavi | dense informal | 19,339 OB | **2.78** | 13.97 | 23.10 | 16.6% | not triggered |
| lagos | dense informal | 34,056 OB | **0.19** | 6.62 | 9.53 | 89.5% (70.8% unpaved) | **triggered, 0.561 km²** |

Live re-measurement reproduces `03_EVIDENCE.md` Part B exactly for Dharavi
(2.78) and Lagos (0.19). Rasterised road area matches vector road space within
0.1% in every AOI, and every representation carries the layer id.
**Barcelona's 37.8 km/km² is 4.5× Khayelitsha's 8.35**, because Barcelona
maps its sidewalks as footways. That is the saturation item 20's baseline
caution predicted. Lagos's negative space is 3.3% of the AOI and is
unvalidated candidate road space.

`tests/test_vector_roads.py`, 37 tests: **0 before** (the `vector` package did
not exist; collection error) and **37 passed after**.

*Doc contradictions:* `diagnose_pure_pixels_paved.py` has per-tag caching but
**no threaded fetch** (it is sequential with 3 s sleeps), so the thread pool is
new here. `generate_osm_road_masks.py` keeps its own copy of the width table,
not changed here; two copies can drift.

### 20. Per-area completeness score ✅ *(was 🔶 PARTIAL until the low-coverage flag reached the UI; flipped 2026-10-28, `build/coverage-ui`)*

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

**Low-coverage policy (decided 2026-09-24; see the Part 4 mandate note):**
outputs that stay meaningful at low coverage (footprint density, coarse
`built`) are computed with a confidence flag. Network-topology metrics
(orthogonality, dead-end ratio, fine connectivity) are suppressed below a
threshold. **This item sets those thresholds.**

**Acceptance:** score emitted for every AOI, **never optional, never null**; a
low-coverage AOI is visibly flagged end-to-end through to the UI; Lagos (0.19)
and Khayelitsha (8.35) produce visibly different scores.

**Built 2026-10-28** (`vector/coverage.py`). *Label: `experimental` (decision 2026-10-28, `08_STATE.md`; nothing here is
`validated`).* ~~**Partially accepted: the UI half is NOT met**
(see below).~~ **Accepted 2026-10-28**: the UI half is met (see "The UI half"
below).

- **Fields** (all always present, never null; the JSON forbids NaN and inf):
  `osm_density_percentile` (narrow pedestrian density ranked against the
  reference set), `coverage_regime_flag`, `regime_reasons`,
  `arterial_to_pedestrian_ratio`, `footprints_per_road_km`, `footprint_count`
  and its method, `topology_metrics_suppressed`,
  `footprint_metrics_confidence`, and `measure: "peer_relative_density_rank"`.
  Named per the caution above: not a completeness rate.
- **Low-coverage policy thresholds, set here** (fixed before any score was
  computed). `very_low` below 0.3 km/km² narrow density. `low` below 1.0 (the
  same constant as item 19's negative-space trigger), or above 5.0
  arterial/pedestrian, the partial-mapping signature. `not_measurable` if the
  pedestrian or arterial clause was not retrieved. Under low or worse,
  topology metrics are **suppressed** and footprint metrics carry reduced
  confidence. A zero denominator gives a capped value with `capped: true`.
  Footprints per road km is reported but not used in the regime, because no
  threshold for it is justified.
- **Partial fetch.** Each output declares the Overpass clauses it is built
  from (`roads.GROUP_CLAUSES`, tested against the clause partition). When one
  was not retrieved, it carries `partial_fetch`, the missing clauses, and a
  lower-bound note. The arterial/pedestrian ratio reads only the arterial and
  narrow clauses, so a missing `service` clause leaves it complete.
- **Reference set, measured live** (13 AOIs: the 11 baseline AOIs plus
  Barcelona and Chandigarh as formal anchors), committed as
  `REFERENCE_NARROW_KM_PER_KM2`. It reproduces Part B within 0.1 km/km²: the
  largest drifts are HCMC 0.99 vs 0.90, Kigali 1.87 vs 1.94 and Jakarta 0.41
  vs 0.39. Dharavi 2.78, Lagos 0.19 and Khayelitsha 8.35 match exactly.

**Scores, 2026-10-28** (percentile leave-one-out, 12 others):

| AOI | narrow km/km² | percentile | regime | arterial/ped | footprints per road km |
|---|---:|---:|---|---:|---:|
| lagos | 0.193 | **0.0** | **very_low** | 11.10 | 208.9 |
| jakarta | 0.407 | 8.3 | low | 4.02 | 76.9 |
| nusantara | 0.633 | 16.7 | low | 1.59 | 9.7 |
| hcmc | 0.990 | 25.0 | low | 3.86 | 204.2 |
| accra | 1.303 | 33.3 | adequate | 3.78 | 127.6 |
| guatemala | 1.830 | 41.7 | adequate | 4.22 | 125.9 |
| kigali | 1.874 | 50.0 | adequate | 1.82 | 185.7 |
| nairobi | 2.110 | 58.3 | adequate | 1.66 | 108.7 |
| chandigarh_central | 2.248 | 66.7 | adequate | 3.09 | 81.9 |
| dhaka | 2.284 | 75.0 | adequate | 2.52 | 96.4 |
| dharavi | 2.782 | 83.3 | adequate | 2.72 | 120.1 |
| capetown (Khayelitsha) | 8.348 | **91.7** | **adequate** | 0.25 | 196.0 |
| barcelona_eixample | 37.807 | 100.0 | adequate | 0.26 | 16.9 (OSM footprints) |

**Lagos vs Khayelitsha: visibly different** (0.0 / very_low vs 91.7 / adequate).
Every field is present and non-null for all 13. The low regime covers exactly
`03_EVIDENCE.md`'s under-mapped list (Lagos, Jakarta, HCMC) plus Nusantara,
which Part B deliberately did *not* flag: sparse mapping there plausibly
reflects sparse construction. This score cannot tell those apart.

~~**NOT met: "flagged end-to-end through to the UI".** The flag reaches the
output of every vector product (items 22–24 embed it in every AOI block and
every unit). No UI consumer of the vector track exists yet, so nothing renders
it.~~ **Met 2026-10-28** (below).

**Deviations (recorded 2026-10-28):**
1. *Reference check narrowed.* `measure_reference` first refused any AOI
   with any unretrieved clause. It now refuses only a missing
   `narrow_pedestrian` clause, the one its value is built from. Prompted by
   HCMC's `service` clause failing; tested both ways.
2. *Footprint count method.* For every Open Buildings AOI, the count is the
   server-side `filterBounds` count, not a download. The 112k-polygon Cape
   Town download stalled for 23 h. Same asset, same `filterBounds(Rectangle)`,
   no extra confidence threshold. **Verified identical** to the
   downloaded-then-layer-filtered count on Dharavi (19,339), Chandigarh
   (11,266) and Lagos (34,056), so one method is used for all 12 OB AOIs, not
   a mix. Barcelona (no OB) counts OSM buildings, a different source,
   recorded. The download now has a 300 s per-request deadline.
3. *Percentile is leave-one-out for reference members.* Ranking an AOI
   against its own rounded entry moved it by about 4 points with the 4th
   decimal. The regime flags do not use the percentile and are unchanged.

`tests/test_vector_coverage.py`, 26 tests: **0 before** (module absent) and
**26 passed after**. The partial-fetch tests were also run against item 19's
`roads.py` (no `fetch_status`): **6 failed, then 6 passed** with it.

**Toward the UI half (2026-10-28, `build/coverage-ui`).** The backend now
serves what the UI needs, so the frontend decides nothing:

- Every block carries `low_coverage_warning` (true for `low`, `very_low`,
  `not_measurable`: `coverage.LOW_COVERAGE_REGIMES`, the same set that
  suppresses topology) and `scored`.
- `vector/coverage_report.py` scores all 13 vector AOIs (the reference set)
  and stores one report under `experiments/vector_coverage/`. An AOI whose
  inputs raise is kept as `not_measurable` with the error as its reason and
  **no number** (`coverage.not_measurable_block`); it is never dropped.
- `GET /api/vector/coverage` serves the newest stored report verbatim; 404
  with the command to run when none exists.
- `sources.count_open_buildings` had **no Earth Engine timeout**; it now goes
  through `ee_timeout.call` (`OPEN_BUILDINGS_COUNT_TIMEOUT_S = 120`).

`tests/test_vector_coverage_report.py`, 11 tests: collection error on old
code (module absent); with only the new module added, **9 failed**; **11
passed** after.

**The UI half (2026-10-28, `build/coverage-ui`).** The sidebar's "OSM
coverage · vector AOIs" panel lists every AOI in the report, in the
backend's order, with its regime. A row whose block does not carry
`low_coverage_warning: false` gets a red `role="alert"` box with the
backend's own `regime_reasons`, the topology-suppressed note and the
footprint-confidence level. `not_measurable` (or `scored: false`) prints
"not measurable" and **no number**, even where the block carries densities
from the clauses that were fetched. Every `{status: "partial_fetch"}` in a
block, at any depth, is listed with its missing clauses and lower-bound note.
`geowatch-ui/src/coverage.js` is a reader in the `applicability.js` mould: no
thresholds, no regime list (a test checks its source for both). A missing
warning field warns.

`tests/test_coverage_ui.mjs` (node; its report is emitted by the real
`build_report` over synthetic layers), 13 checks: **crashes on old code**
(no `coverage.js`); against master's `App.jsx` **2 failed**; **13 passed**
after. App.jsx is checked structurally, not rendered: there is no browser or
component renderer in the test setup, the same limit as the other `.mjs`
tests.

**Stored live report, 2026-10-28** (`experiments/vector_coverage/result_2026-10-28.json`,
`python -m vector.coverage_report`, thresholds unchanged). 12 of 13 AOIs
reproduce the table above exactly (percentile, regime, density, ratios).
Two differ, both from Overpass transport failures (`overpass.kumi.systems`
ReadTimeout), and both are reported as such, not retried into agreement:

| AOI | this run | the table above | why |
|---|---|---|---|
| dhaka | **not_measurable**, warns, no number shown | adequate, 75.0 | `narrow_pedestrian` clause not retrieved |
| lagos | very_low, 0.0, warns; **partial_fetch** (`service`) on road lengths and footprints/road km (250.4 vs 208.9) | very_low, 0.0 | `service` clause not retrieved |

Rerunning `python -m vector.coverage_report` re-fetches only the missing
clauses (the rest are cached) and writes a new dated report, which the route
then serves.

**Acceptance, against the text above:**
- *Score emitted for every AOI, never null*: 13/13 in the stored report.
- *A low-coverage AOI is visibly flagged end-to-end through to the UI*: met.
  The stored report goes through `GET /api/vector/coverage` and
  `coverage.js` to a `role="alert"` box. Lagos, Jakarta, HCMC, Nusantara and
  Dhaka (this run) warn; the other eight do not.
  `tests/test_coverage_ui.mjs` has an acceptance check that runs the
  stored report through the real route. **Limit:** the panel was not
  inspected in a browser (the browser tool was not connected). The JSX is
  checked structurally and `vite build` compiles it.
- *Lagos and Khayelitsha visibly different*: 0.0 / very_low / warning vs
  91.7 / adequate / no warning.

### 21. ~~Spectral unmixing~~ Spectral regression → fractions 🔓 **PILOT COMPLETE — RE-SCOPE SIGNED OFF 2026-09-23; not yet built** *(heading was "⚠️ PILOT COMPLETE — RE-SCOPE PROPOSED, AWAITING DECISION"; corrected 2026-09-24)*

> **The sequencing requirement below was honoured, and the pilot returned a
> negative result.** This item as originally specified is not buildable. The
> original text is preserved below the rule for provenance; the re-scope
> proposed above it ~~has **not** been signed off and this item is not
> settled~~ **was signed off 2026-09-23** (see Decisions 11/13/14 and
> `08_STATE.md`). The item is open to build, not awaiting a decision.
> Full evidence: `06_UNMIXING_CEILING.md`.

#### What the pilot established

Seven pre-registered methods failed to recover per-pixel `built` fraction for
small-structure informal fabric. Measured pairwise spectral angles put every
hard surface — institutional roof, informal roof, asphalt, bare soil — inside a
cone **under 5° wide**, against a Sentinel-2 L2A noise floor of ~0.7°.
`built` vs `paved` is **1.70°**.

Simulating from those measured endmembers under conditions strictly *more
favourable* than reality (exact labels, linear mixing, fixed endmembers, no
shadow, no cross-city transfer), the best achievable R² for `built` fraction is
**0.49–0.56** — against a success bar of 0.50. Observed real values were
0.35–0.41 within-AOI and 0.08–0.18 cross-city.

**This is an information limit, not a method-selection problem.** No unmixing
solver, endmember library or feature set can exceed it.

#### Proposed re-scope

**1. Retire the `built`/`paved` split as a measured product.** State it as a
non-goal with the ceiling as its justification. Decision 11 already calls this
"the weakest boundary of the five"; the measurement shows it is not weak but
*unidentifiable*.

**2. Invert where each quantity is estimated.** Decision 11 measures `built`
and `paved` and derives `impervious_total`. The evidence says reverse it, while
keeping Decision 11's governing principle — *measure disjoint things, derive
overlapping ones* — fully intact:

| Fraction | Source | Ceiling R² |
|---|---|---|
| **built** | **vector footprints, directly** | n/a — not estimated from spectra |
| **impervious_total** | spectral regression | 0.822 |
| **paved** | derived: `impervious_total − built`, with explicit uncertainty | — |
| **vegetation** | spectral regression | 0.974 |
| **water** | spectral regression | 0.965 |
| **bare** | residual | — |

The first row is the substantive move. Open Buildings coverage **is** a `built`
estimate — VHR-derived, Sentinel-2-independent, and it served as the regression
*label* throughout the pilot. Predicting it from spectra re-derives, badly, what
the vector layer already supplies well.

**3. Revised acceptance.** Fractions produced for at least one formal and one
informal AOI; sum to ~1 within tolerance over the observed portion; documented
**provenance per fraction** (training-data provenance where regression replaces
an endmember); per-fraction confidence with **`paved` explicitly marked derived,
never measured**; and `impervious_total` validated against a held-out AOI rather
than against a same-AOI split.
The Stage 1 trainer must load hand tiles only through experiments/harness/firewall.py training_tiles(); a test must show it raises HeldOutError on a validation tile.

**4. Blocking gap, stated plainly.** The 0.822 `impervious_total` ceiling is
*simulated, not achieved*. Testing it needs a real impervious label, and the
only available paved source — unroofed OSM polygons — covers **0.23–1.82%** of
the pilot AOIs against a built mean of 19–30%. **This item cannot be closed
until that label exists.** It is a data-sourcing problem (VHR-derived or
hand-annotated paved labels on a sample), not a method problem.

#### What this costs downstream

- **Flood risk** — unaffected. Its stated input is `impervious_total` plus
  vector conduits (§6 outputs table; item 26). *(Qualified 2026-09-24:
  unaffected by the inversion, but the sealed-only `paved` definition moves
  compacted earth into `bare`. Item 26 now uses runoff coefficients per
  fraction; see item 26.)*
- **Morphological characterisation** — unaffected. Item 23 separates formal from
  informal *without any spectral input*.
- **Change over time** — improved. A stable estimator of a recoverable quantity
  yields more defensible deltas than an unstable estimator of an unrecoverable
  one.
- **Roofing material per building** — was never deliverable from this data.
  Should be stated out of scope explicitly.

#### Recorded 2026-09-24 — eight fractions, regressor training, validation additions

*Decided in a planning session; written down here for the first time. The
taxonomy change itself is Decision 11's second amendment — this subsection is
what it means for item 21.*

**The re-scope table above gains three rows, and the remainder changes.**

| Fraction | Source |
|---|---|
| **snow_ice** | spectral + low temporal variance (item 18). Permanent only; transient snow → occlusion |
| **solar** | own fraction. Inclusion in `impervious_total` **DEFERRED** until solar prevalence is measured in the validation data |
| **mixed_water_vegetation** | spectral, sub-typed via Global Mangrove Watch + Global Lakes and Wetlands Database; own flood-model input (item 26), weighted by sub-type |

The regressor no longer splits "everything that is not vegetation, water or
shadow". It splits the **hard-surface remainder**:

    hard_surface_remainder = 1 − (vegetation + water + snow_ice + solar
                                  + mixed_water_vegetation)
        — on the known-pixel share only (~~shadow-renormalised~~, struck
          2026-09-24)

into `impervious_total` and `bare`. Omitting any of the three new subtractions
lets that surface leak into `impervious_total` or `bare`.

**Producers for the three new fractions (recorded 2026-09-24),** all run
before the remainder is computed:

| Fraction | Producer |
|---|---|
| `snow_ice` | spectral signature + low temporal variance (item 18) |
| `solar` | spectral-signature detector |
| `mixed_water_vegetation` | spectral + dataset sub-typing (Global Mangrove Watch, GLWD) |

Vegetation and water stay spectral regression, as in the table above.

*Amended 2026-09-24:* ~~`+ shadow)`~~ is struck from the formula as first
recorded. **Shadow rule, locked:**
- **Fully shadowed pixels** are occlusion and leave the denominator
  (Decision 14).
- **Partially shadowed pixels** ~~get a sub-pixel shadow term in the solve,
  renormalised out and never reported as a fraction~~ — *amended 2026-09-24:*
  stay in the known-pixel denominator with **no explicit term**. The
  regressors are trained on hand labels that include partially shadowed
  pixels, so robustness is learned. They are never reported as a fraction.
- **No pixel is handled both ways.** Fully shadowed pixels have left the
  denominator before the remainder is computed, and shadow is not subtracted
  again.

See Decision 11.

**Regressor training — the impervious vs bare split.**

- **Core:** a small hand-labelled set at ~~**Delhi, Lima, Cape Town,
  Jakarta** (Cairo optional)~~ **Cape Town, Lima, Karachi, Monrovia**
  (Marrakech optional) — *city list replaced 2026-09-24, see "Site list"
  below*. It is **weighted toward genuine bare ground**, the boundary
  Decision 14 (d) names as the weakest recoverable one.
- **Optional bulk weak labels** from external impervious products (GISA /
  GAIA) — **only if LOCO shows they help**. Default is off.
- **Optional endmember feature** *(added 2026-09-24, Decision 13)*: per-pixel
  spectral angle to the AOI's own local paved endmember. **Default off.**
  Ablate with vs without during LOCO; keep only if it measurably improves
  cross-city transfer, otherwise retire it. If kept, build it per the
  endmember-stability findings below: local extraction, buffer 0, per-AOI n\*,
  independent bootstrap pairs.
- **Firewall:** no training in any city containing a validation site —
  **Lagos, Nairobi and Rio are excluded** from training entirely.
- **Leave-one-city-out within the training cities before any contact with
  validation.** Validation sites are touched once, after LOCO.
- **How many labelled areas:** determined empirically — keep adding until LOCO
  stops improving, then stop. No number is fixed in advance. Working rules 2–4
  in `08_STATE.md` apply (paired per-fold comparison, per-city and per-class
  reporting, no rounding a within-noise result up).

**Site list — FINAL, recorded 2026-09-24.** Recorded decisions only: no
imagery has been downloaded and nothing is built.

> **Why the training list changed.** The list first recorded was ~~Delhi,
> Lima, Cape Town, Jakarta, Cairo (optional)~~. A per-site imagery check on
> 2026-09-24 found that **Delhi, Jakarta and Cairo had no free sub-2 m imagery
> whose licence permits deriving labels.** Across OpenAerialMap and the
> Maxar/Vantor open-data catalogues:
>
> - **Delhi and Cairo:** zero scenes metro-wide.
> - **Jakarta:** one 8.6 km² scene at 0.5 m, with 0 / 1 / 2 clear Sentinel-2
>   scenes within ±30 / 60 / 90 days.
> - **Basemap fallbacks are forbidden by their terms:**
>   - Bhuvan's 1 m imagery is view-only, and its terms forbid derivative
>     works.
>   - Google's terms forbid tracing and training, testing or validating
>     models.
>   - Esri restricts derived data to non-commercial use within ArcGIS and
>     forbids programmatic requests.
>
> Karachi replaces Delhi (arid, South Asia), Monrovia replaces Jakarta (humid
> tropical, informal and formal fabric), and Marrakech replaces Cairo as the
> optional city (semi-arid, North Africa). **Delhi may be re-added later**
> through academic access to commercial imagery (ESA Third Party Missions,
> Airbus academic). That is not a blocker.

**Validation sites — unchanged, imagery confirmed:**

| Site | Imagery | Resolution | Date | Licence | Sentinel-2 overlap (clear scenes, ±30 / 60 / 90 d) |
|---|---|---|---|---|---|
| **Makoko** (Lagos) | Uhuru Labs drone survey | 5.4–6.4 cm | 2019-10-02 | CC BY 4.0 | **Weak: 0 / 2 / 4.** Needs a wide (~6-month) composite window, as for Old Fadama in `06_UNMIXING_CEILING.md` §7.1 |
| **Kibera** (Nairobi) | Maxar Kenya floods open data | 0.30–0.32 m | **2023-11-30, the PRE-flood scene only** | CC BY-NC 4.0 | 2 / 4 / 9 |
| **Rocinha** (Rio) | IPP city true-orthophoto mosaic (`Imagens/Mosaico_2024`) | 15 cm | first half of 2024 | Non-commercial; commercial use needs IPP's prior written authorisation | 3 / 8 / 15 (checked against 2024-04-01) |

**Training sites — final:**

| Site | Imagery | Resolution | Date | Licence | Sentinel-2 overlap | Notes |
|---|---|---|---|---|---|---|
| **Cape Town** | City of Cape Town aerial imagery (`Aerial Imagery 2026Jan`) | 5 cm | 2026-01 | Non-commercial ("no restrictions on the digital file for non-commercial purposes") | 9 / 16 / 24 | — |
| **Lima** | OpenAerialMap drone scenes | 3–8 cm | 2017–2025 | CC BY 4.0 | varies by scene (UNI 2025-03-17: 11 / 12 / 14; Caritas 2025-01-05: 1 / 2 / 9) | **Prioritise the desert-hillside scenes, Candelaria and Santuario de las Vizcachas** (genuine bare ground). **Exclude Cajamarquilla** (no licence) |
| **Karachi** *(replaces Delhi)* | Maxar Pakistan floods open data | 0.53 m | **2022-03-29 only** | CC BY-NC 4.0 | 66 / 127 / 169 | **Pre-flood scene only.** Later scenes contain flood water that would pass for bare ground or water |
| **Monrovia** *(replaces Jakarta)* | Uhuru Labs / HOT drone surveys | 5 cm | 2020-02-23 | CC BY 4.0 | 22 / 43 / 53 | — |
| **Marrakech** *(optional, replaces Cairo)* | Maxar Morocco earthquake open data | 0.31–0.55 m | pre-quake 2023 scenes (e.g. 2023-03-28, 2023-08-06) | CC BY-NC 4.0 | 20 / 39 / 49 (08-06) | **Add only if LOCO shows four training cities are too narrow** |

The Sentinel-2 counts are whole scenes under 20% cloud, not per-pixel. A
masked composite can still work where the count is low.

**Caveats — recorded with the list:**

1. **Licence assumption.** Most of these sources are non-commercial (CC BY-NC
   or equivalent): Kibera, Rocinha, Cape Town, Karachi, Marrakech. That is fine
   for academic use. **If GeoWatch or its labels are ever used commercially,
   these labels must be re-sourced.**
2. **Regional overlap.** The firewall is city-level and is not broken. But
   Monrovia shares a region with Makoko (West Africa), and Lima shares one with
   Rocinha (South America). **Validation reporting must note this.**
   **Kibera (East Africa) is the coldest transfer test.**
3. **Coverage areas overstate usable ground.** Drone mosaics have internal
   no-data gaps; the Old Fadama rectangle was ~36% nodata. **Real pixel
   coverage must be checked per site before labelling time is committed.**

**Validation criteria and guardrails — decided 2026-09-24, fixed before any
run.** This item is under Part 4's validation-first mandate: nothing past
item 21 progresses until these are met, and until then item 21's outputs are
proposed research design, not claims.

**`impervious_total` pass/fail:**

| Metric | Floor | Target | Role |
|---|---|---|---|
| **MAE** | ≤ 15 pp | ≤ 10 pp | **Hard gate** — failing the floor fails the item |
| **R²** | ≥ 0.3 | ≥ 0.6 | **Hard gate** — failing the floor fails the item |
| **IoU** | ≥ 0.45 | ≥ 0.6 | **Diagnostic only.** Reported, never disqualifying |

These are fixed now and may not be moved after a result is seen. Scoring uses
the sealed validation batches (`LABELLING_GUIDE.md` §8) and follows the
working rules in `08_STATE.md`: per-city and per-class reporting, no rounding
a within-noise result up.

**`built` validation.**

- **Hand-digitised buildings** at Makoko, Kibera and Rocinha are compared
  against **Open Buildings** and a **second footprint source** (Microsoft or
  OSM buildings, per Decision 11's new datasets).
- **Ongoing, everywhere:** the **per-AOI disagreement between the two
  footprint sources** is reported as `built` confidence. That signal is
  **calibrated by the hand-digitised check**, which ties a given disagreement
  level to a measured error.

**Regressor guardrails.**

- **Deliberately low capacity.** The training set is small (hand labels,
  four cities), and a high-capacity model would memorise cities rather than
  transfer.
- **Mandatory LOCO with a predefined bar.** The bar is fixed before the first
  LOCO run, like the criteria above.
- **Fallback if the impervious/bare split fails LOCO:** report **hard surface
  unsplit** rather than a bad split. That is the hard-surface remainder
  (Decision 11) reported as one quantity.

**Labelling guide — decided 2026-09-24: [`LABELLING_GUIDE.md`](LABELLING_GUIDE.md)
(v1.0).** It is the protocol for every training and validation label above:
- the label set, including `shadow_full` / `shadow_partial` and `unsure`
- polygon labels, with fractions computed from area and never eyeballed
- stratified random ~200 m tiles
- hard cases: sealed = `paved`, compacted = `bare`
- the time-gap and change-test rules
- QC: ~15% blind re-labels, and agreement bars fixed before evaluation
- sealed validation in two batches

**Labelling may not start until its open numbers are set:** change-test
method and threshold, maximum date gap per site, starting tile count, and
per-class agreement bars (guide §9).

**Validation additions.**

- **Shadow accuracy** is measured in the **same hand-digitisation pass** at
  Makoko (Lagos), Kibera (Nairobi) and Rocinha (Rio) — not a separate
  campaign. It gives Decision 14 (a)'s "indeterminate at 6.5–9.7% residual"
  caveat a direct measurement. **Added 2026-09-24: the pass must label full
  and partial shadow as separate cases**, because the shadow rule routes them
  differently. Full shadow is checked against the occlusion mask; partial
  shadow is checked ~~against the sub-pixel term~~ *(amended 2026-09-24)* as
  the **regressors' error on partially shadowed pixels compared with
  unshadowed ones**. That includes whether shadow drifts into `water`. This
  is the test of learned robustness; **if it fails, a dedicated fix is added
  then, with evidence.** A single "shadow" label cannot check either case.
  The same labels are the evidence for setting the full/partial boundary.
  **Partially shadowed pixels must also appear in the *training* labels**
  (Cape Town, Lima, Karachi, Monrovia), or there is nothing to learn from.
- **`snow_ice`, `solar` and `mixed_water_vegetation` each get their own
  validation case** at a site where they actually occur, against an
  **independent reference dataset**. The `solar` case is also where the
  prevalence measurement that settles the deferred `impervious_total`
  question comes from.

**Also in scope from the same session, recorded in `02_ARCHITECTURE.md` §3:**
the metadata-flag foldings (sports fields / parks / farmland → `vegetation`;
sand, rock, dry lakebeds, landfills, quarries etc. → `bare`; docks → `built`),
the extended occlusion list (Decision 14), the volcano and terrain context
layers, the new datasets (including a second footprint source — Microsoft or
OSM buildings — for `built` confidence), and the volcanic hazard module parked
as a future sixth hazard module.

---

*Original specification, preserved for provenance. Superseded by the pilot
result above.*

**What:** linear unmixing per 10 m pixel into the five fractions, per Decision
13's constrained-extraction spec in full.

**Precondition — tightened:** BOA surface reflectance is already available via
`COPERNICUS/S2_SR_HARMONIZED`. **~~Unmixing~~ The regression inputs *(2026-09-25)* must read the float32 multi-band
tile path — never the per-tile percentile-stretched 8-bit PNG preview.** The
6-band float32 tiler is a *prerequisite* for this item, not a retired path;
only the dual-stem classifier that used to consume its output is dead.

~~**How:** constrained least squares (sum-to-one, non-negativity), or
`pysptools`, or Earth Engine's own unmixing. Endmembers per Decision 13
**as amended 2026-09-23**: three stable fractions (vegetation, water, bare)
from a global library directly, plus **one `impervious_total` endmember** from
wide unroofed OSM polygons (parking, aprons, plazas) — never road centerlines.~~
**`built` is not unmixed**: it is rasterised from vector footprints, and
`paved` is `impervious_total − built`, reported with its derivation
uncertainty and explicitly clamped if negative.

> **Superseded 2026-09-24 — one method, not two.** The struck "How" described
> a single constrained unmixing solve. It conflicts with the **spectral
> regression** table signed off 2026-09-23 (re-scope step 2 above), which is
> the method: vegetation, water and `impervious_total` by regression, `bare`
> as the residual, and the three new fractions from the producers listed
> under "Recorded 2026-09-24". The `built` and `paved` sentence stands.

> **STATUS OF THE ENDMEMBER MATERIAL BELOW — conditional (2026-09-24).** The
> next several blocks are dated 2026-09-23/24 and were written as live spec
> for an unmixing endmember:
>
> - the annotation-provenance check
> - the C44 rationale
> - the sparse-paved observation
> - the stability findings (local extraction, buffer 0, per-AOI n\*,
>   independent bootstrap pairs)
> - the endmember-uncertainty field
>
> **Decision 13 as amended 2026-09-24 removes the unmixing endmember.** The
> local paved endmember survives only as an **optional regressor feature**:
> per-pixel spectral angle to the AOI's own local paved endmember. It is built
> **without** by default and **kept only if the LOCO ablation shows it
> measurably improves cross-city transfer**. So:
>
> - **If the ablation keeps the feature,** this material is the live spec for
>   building it. "Endmember" below then means *the feature's reference
>   spectrum*, not an unmixing endmember.
> - **If the ablation retires it,** this material is historical record,
>   kept for the measurements.
>
> Until the ablation runs, read it as conditional. The C44 fix itself is
> unconditional (see its note).

**Annotation-provenance check — done, clean (2026-09-23).** *(Conditional as
of 2026-09-24: it matters only if the endmember feature is kept. The `built`
half — Open Buildings, not C45-affected — holds regardless.)* The endmember
sources were audited against **C45** (the OSM builders that overwrite human
labels). They do **not** share a source: `built` comes from Google Open
Buildings v3 (`confidence ≥ 0.7`) plus S2 temporal variance, and the impervious
endmember comes from a *fresh* Overpass polygon query
(`amenity=parking`, `aeroway=apron`, `highway=pedestrian`+`area=yes`,
`place=square`, `landuse=garages`) that deliberately reuses neither
`generate_osm_road_masks.py`'s centreline query nor
`generate_osm_water_masks.py`'s. No extraction script reads
`annotations.json`, `osm_generated_annotations*.json`, `mask_rle`,
`roads.geojson` or `waterways.geojson`. **C45 is therefore not a blocker to
this item.** The one real inheritance is `OVERPASS_URLS`, imported by
`diagnose_pure_pixels_paved.py` from `generate_osm_road_masks` — that is
**C44** (two of three endpoints dead, failures logged without status codes).

**C44 is now FIXED (2026-09-23) and this item is unblocked on that front.**
*(2026-09-24: the fix stands unconditionally — it is the project's single
Overpass client. Its rationale here, protecting "this item's endmember
library", applies only if the LOCO ablation keeps the endmember feature.)*
All Overpass access goes through `ingestion/overpass.py`, which classifies
failures by cause — a malformed query fails immediately rather than being
reissued to every host, a genuine query timeout is distinguished from the
transient dispatcher fault, a 429 backs off and retries, and a dead host is
rotated past with no backoff. The endpoint list is re-measured: `openstreetmap.ru`
removed (dead), `maps.mail.ru` added (200/50 elements, 12–22 s),
`overpass.osm.ch` **deliberately excluded** because it answers 200 in 0.6 s with
zero elements outside Switzerland — a silently-empty endpoint would have built
this item's endmember library on no polygons at all. Verified end-to-end:
`diagnose_pure_pixels_paved.py --aoi dharavi` completed against the live list
(5 paved polygons, 62 pure pixels), having hit and recovered from a 429, a 504
and a ReadTimeout in the same run. Probe the list any time with
`python ingestion/overpass.py`.

**Sparse-paved observation from that run:** Dharavi yielded only **5**
unroofed paved polygons across 4.68 km², 3 of which contributed a pure pixel.
That is a real signal about informal fabric, not an extraction bug.

> **CORRECTION 2026-09-24 — do not buffer.** This caveat originally continued
> *"…it means the impervious endmember for informal AOIs may have to be drawn
> from a wider region than the AOI itself."* **That guess was tested and is
> wrong.** It is struck rather than deleted because it is the kind of
> reasonable-sounding inference someone will re-derive from the sparse-polygon
> count above, and the measurement against it should be findable from here.
> Evidence: `diagnose_endmember_stability.py`, results in
> `experiments/endmember_stability/results/stability.json`.

**Extraction is LOCAL. Buffer radius = 0.** *(2026-09-24: this and the n\*
findings below define how the optional feature's reference spectrum is built
**if the LOCO ablation keeps it**. The measurements stand either way.)*

Widening the draw region reduces sampling noise and increases spectral drift,
and drift wins immediately. Total endmember error — `hypot(sampling, drift)` —
is minimised at 0 km in every AOI tested:

| AOI | radius | pure px | sampling | drift | total |
|---|---:|---:|---:|---:|---:|
| Dharavi | **0 km** | 62 | 1.68° | — | **1.68°** |
| Dharavi | 1 km | 306 | 0.76° | 1.86° | 2.01° |
| Dharavi | 2 km | 1,067 | 0.41° | 2.87° | 2.90° |
| Dharavi | 5 km | 3,000* | 0.24° | 3.01° | 3.02° |
| Khayelitsha | **0 km** | 251 | 0.58° | — | **0.58°** |
| Khayelitsha | 1 km | 396 | 0.46° | 1.56° | 1.62° |

\* sampling cap, so a floor not a count.

One kilometre of reach at Dharavi buys 4.9× more samples (−0.92° of noise) and
costs **1.86° of drift** — already past the **1.70°** built-vs-paved separation
the endmember exists to support. Sparse local pixels beat plentiful distant
ones.

**Confidence: strongly suggested, not universally confirmed.** The buffer sweep
ran on **2 of the 4** AOIs tested — Dharavi and Khayelitsha, which agree in
both direction and magnitude (drift 1.56–1.86° at 1 km). Cape Town formal and
Jakarta have Part A (the n\* threshold) but **no buffer sweep**. The result is
consistent with the underlying model — drift is a *bias* that grows with
distance while sampling error is *noise* that falls only as 1/√n, so bias
overtakes quickly — but it has not been demonstrated on a formal-suburban or
dense-mixed AOI. Run those two sweeps before treating buffer=0 as settled.

**n\* is per-AOI and must be measured, not assumed.**

The number of pure pixels needed for a stable endmember spans **21×** across
the four AOIs, and it does **not** track sample availability or city density —
it tracks the **material heterogeneity of the paved surface itself**:

| AOI | pure px | px/km² | n @1.70° | **n\* @0.7°** | local error | verdict |
|---|---:|---:|---:|---:|---:|---|
| Khayelitsha (informal) | 251 | 10.9 | 29 | **172** | 0.58° | clears noise floor locally |
| Dharavi (sparse informal) | 62 | 13.3 | 60 | **358** | 1.68° | ship with disclosed uncertainty |
| Jakarta (dense mixed) | 1,585 | 36.8 | 154 | **868** | 0.51° | clears noise floor locally |
| Cape Town formal | 1,107 | 77.1 | 530 | **3,532** | 1.20° | ship with disclosed uncertainty |

**Counterintuitively, the denser formal AOI is the harder problem.** Cape Town
formal has 6× Dharavi's pure-pixel density and needs ~10× more samples: its
between-draw spread starts at 18.41° against Khayelitsha's 5.49°, because
"paved" there is asphalt car parks, concrete plazas, aprons and garage courts
of differing age and wear under one label. Informal fabric is more uniform. So
**do not size n\* from city density or from how many polygons OSM returns.**

**How to compute it:** bootstrap the AOI's own pure-pixel spectra — draw B
independent subsample *pairs* at each n and take the p90 spectral angle between
them. Cheap: one GEE sampling pass per AOI, then pure numpy. Use **independent
pairs, never a nested growing sample** — a nested sequence shares n of its n+1
pixels and is correlated by construction, which understated the true spread by
**9.9×** at Dharavi (0.30° vs 2.92° at n=20) and would have declared every AOI
stable at n≈20.

The fitted exponent came out −0.47 to −0.51 across all four AOIs, i.e. clean
1/√n sampling noise, so the curves differ in height rather than shape and
projecting past the available pixel count is interpolation of a validated
model. Report the exponent alongside n\* — a curve that is *not* near −0.5 is
not behaving like sampling noise and its projection should not be trusted.

~~**Endmember uncertainty is a first-class reported field**~~ **Endmember
uncertainty is reported ONLY IF the LOCO ablation keeps the endmember
feature** *(amended 2026-09-24)*. If it is retired, there is no endmember and
no such field. When reported, it belongs in Decision 14's
**estimate-quality** group (never the observability group — a wide endmember is
not an unobserved pixel). Two of the four AOIs clear the 0.7° noise floor
locally; the other two do not and must ship at their measured local error
(Dharavi 1.68°, Cape Town formal 1.20°) **with that number disclosed**, rather
than being buffered into a smaller-looking but genuinely worse endmember.
~~Propagate it into `paved`'s derivation uncertainty, which is already required
by Decision 14 as amended.~~ If kept, it propagates into the prediction
interval of `impervious_total` — the quantity the feature feeds — and from
there into `paved`'s derivation uncertainty. *(Decision 14 itself never listed
an endmember-uncertainty field; this paragraph was the only place it was
defined.)*

**Shadow handling:** ~~solve as a sixth term; renormalize the five reported
fractions over the illuminated portion only;~~ ~~report shadow fraction as its
own field~~, per Decision 14's separated-reporting convention. *Superseded
2026-09-24 by the shadow rule (Decision 11):* ~~the sixth term covers partially
shadowed pixels only and is never reported~~ there is no sixth term; partially
shadowed pixels carry no explicit term and are handled by learned robustness
(amended again 2026-09-24). Fully shadowed pixels are occlusion, and only they
populate Decision 14's shadow field.

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

### 22. Aggregation units ✅

**Sequence, in order:**
1. **Regular-grid blocks** — free, immediately available
2. **Building-footprint units** — individually addressable, good for risk
   communication
3. **Path-delineated segments** — most faithful to how water and people move, but
   requires item 19 to define boundaries

**Acceptance:** each unit type produces the same fraction totals over the same
area (a consistency check); every unit carries `{value, status, coverage}`.

**Built 2026-10-28** (`vector/units.py`, `vector/fractions.py`). *Label: `experimental` (decision 2026-10-28, `08_STATE.md`; nothing here is
`validated`).*

- **Units, in the specified order.**
  1. A regular 100 m grid on the 10 m pixel grid.
  2. One unit per building: a centroid-Voronoi tessellation clipped to the
     AOI (momepy is not installed, so this is the simpler centroid form).
  3. Path-delineated blocks from item 19's `blocks()`, carrying
     `partial_fetch` if a clause was missing.
- **Fractions: built, vegetation and water only.**
  - **built** is the item 19 layer's footprints rasterised to 10 m
    (02_ARCHITECTURE.md's definition of `built`).
  - **vegetation and water are PROXIES, not item 21 fractions.** They are
    index thresholds on a Sentinel-2 median composite: water is MNDWI > 0 (Xu
    2006), and vegetation is NDVI > 0.3 and not water. A pixel needs ≥ 3
    cloud-free (SCL) observations. Item 21's regression, the decided
    producer, is not built. Every output carries `method` and `producer`
    saying so.
  - **`impervious_total` is `not_computed` in every unit**, with value
    `None`, never 0.
- **Every unit** carries `{value, status, coverage}` per fraction (status is
  `insufficient_observation` below 50% coverage) plus item 20's coverage
  regime, inherited at AOI level.
- **Consistency check** (tolerance fixed before the run: 0.5% of AOI area per
  fraction) on a 2 m sub-grid.

**Live, Dharavi, Sentinel-2 2024-01-01..03-31** (36 images, 98.1% clear):

| unit type | units | built | vegetation (proxy) | water (proxy) |
|---|---:|---:|---:|---:|
| grid | 728 | 24.61% | 27.42% | 7.35% |
| footprint | 19,246 | 24.61% | 27.42% | 7.35% |
| path | 985 | 24.60% | 27.41% | 7.34% |

**Consistency: PASS.** The largest spread between unit types is 0.009% of the
AOI (built), against a 0.5% bar. Path units cover 99.95% of the AOI; the road
cut-strips and slivers account for the rest. 19,246 footprint units for 19,339
footprints: 93 footprints touch the AOI but have their representative point
outside it, so they get no cell. One path block is `insufficient_observation`
in every fraction: it is too small to hold a single 2 m sub-cell.

`tests/test_vector_units.py`, 11 tests: **0 before** (module absent) and **11
passed after**.

### 23. Density metrics 🔶 **BUILT — pre-registered acceptance test FAILED (2026-10-28)**
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

**Built 2026-10-28** (`vector/density.py`). *Label: `experimental` (decision 2026-10-28, `08_STATE.md`; nothing here is
`validated`).* Every metric is a `{value, status}` block, computed from the
item 19 layer only. A test forbids imagery imports, and `spectral_inputs` is
`[]`.

- Road length per area: all, arterial, narrow and broad, kept separate.
- Footprint density and built-area share.
- Footprint size distribution: p10, p25, median, p75, p90 and mean.
- Spacing: centroid nearest-neighbour distance.
- **Orthogonality:** Boeing's (2019) orientation order φ. It is a topology
  metric, so it is suppressed under item 20's low coverage (Lagos:
  `suppressed_low_coverage`).
- `impervious_total`: `not_computed`.

**Separation test, pre-registered in code before either AOI was computed**
(`SEPARATION_TEST`). Known-formal is chandigarh_central and known-informal is
dharavi, with the same footprint source (Open Buildings v3) so the source
cannot separate them. Pass = at least 3 of 4 predictions hold and none is
reversed.

| prediction | formal | informal | statistic | bar | outcome |
|---|---:|---:|---:|---:|---|
| larger formal footprints (median m²) | 50.4 | 46.1 | 1.09× | ≥ 2.0× | short of bar |
| denser informal footprints (/km²) | 2,101 | 2,761 | 1.31× | ≥ 2.0× | short of bar |
| wider formal spacing (median m) | 7.6 | 6.7 | 1.13× | ≥ 1.5× | short of bar |
| more orthogonal formal network (φ) | 0.879 | 0.047 | +0.832 | ≥ +0.10 | **holds** |

**Result: FAIL.** 1 of 4 hold, 0 reversed. The bar was not moved. The street
network separates the two decisively. The footprint metrics all point the
predicted way and fall well short of their bars.

~~*Not explained, and needing your decision:* Chandigarh's median Open Buildings
footprint is **50 m²**, implausibly small for planned formal fabric. Barcelona
(OSM footprints) is 287 m². Possible causes, NOT tested: Open Buildings
fragmenting formal houses; the AOI including many small structures; or a
real property of Chandigarh's sector housing. Until that is resolved, the
footprint metrics cannot be read as morphology signals on Open Buildings
input.~~

**Investigated 2026-10-28** (not re-tested, as instructed). **The cause is Open
Buildings fragmenting formal buildings, not informal colonies in the AOI, and
not something a confidence filter fixes.**

1. **Confidence filter.** None is applied beyond the dataset's own 0.65
   publication floor. Confidence and size are strongly linked:

   | confidence | share of polygons | median area |
   |---|---:|---:|
   | 0.65–0.70 | 28% | 27.6 m² |
   | 0.70–0.75 | 26% | 36.4 m² |
   | 0.75–0.80 | 21% | 66.3 m² |
   | 0.80–0.85 | 15% | 119.2 m² |
   | ≥ 0.85 | 10% | 179.3 m² |

   Filtering at ≥ 0.75 would move the median to 106 m². But a filter would
   hide the problem rather than fix it: in the imagery sample below,
   fragments occur at confidence 0.79–0.87, and whole buildings at 0.75–0.82.
   No threshold separates them.
2. **Is the AOI informal?** No evidence of it. The AOI is Sectors 17, 18, 21,
   22 and 23 plus Sector 20A and police quarters (OSM place nodes and named
   landuse, queried live). OSM maps no colony, village or basti in it. The
   imagery shows plotted formal housing and commercial blocks throughout.
3. **Does Open Buildings split houses? Yes.**
   - **OSM cross-check.** OSM has only 1,271 buildings here (median 139 m²)
     against Open Buildings' 11,266, so it is incomplete. But where both map
     a building, **60% of OSM buildings over 200 m² contain two or more Open
     Buildings polygons** (24% across all sizes; 7.6% contain four or more).
     The 86% of Open Buildings polygons outside any OSM building have a median
     of 44 m².
   - **Imagery sample.** 30 polygons, simple random sample with a fixed seed
     (sample median 36.6 m² vs AOI 50.9 m²), outlined on Esri World Imagery at
     zoom 19 and classified by eye:

   | outcome | count |
   |---|---:|
   | **fragment of a larger building** (rooftop room, stair tower, one roof level, part of a block) | **21 (70%)** |
   | whole building | 5 (17%) |
   | small real structure (annex or outbuilding) | 2 (7%) |
   | not a building (tree canopy, gap between buildings) | 2 (7%) |

   Chandigarh's multi-level plotted houses, with rooftop rooms, water tanks
   and solar arrays, are mapped by Open Buildings as several small
   "buildings". That pulls the median footprint down to informal-fabric
   sizes.

**Consequence.** On Open Buildings input, footprint size, density and spacing
measure segmentation behaviour as much as morphology, in formal fabric at
least. Whether Dharavi's footprints fragment the same way was not checked.
The separation test's footprint predictions cannot be read as a statement
about the two places until that is addressed.

*Limits:* a single observer, 30 samples, and imagery of unknown date relative
to Open Buildings' inference.

Other AOIs, for the record: Barcelona φ = 0.617 (sidewalk footways add
off-grid bearings), 1,093 footprints/km², median 287 m². Lagos φ suppressed,
1,983 footprints/km², median 52 m².

`tests/test_vector_density.py`, 14 tests (commit 61547c6 said 15; corrected in item 24's commit): **0 before** (module absent) and **14
passed after**.

### 24. Access and service indicators ✅
Network connectivity, distance-to-nearest-paved-access per building or per block.

**Acceptance:** computed from the vector layer alone; degradation with
coverage is reported via item 20's score, not silent.

**Built 2026-10-28** (`vector/access.py`). *Label: `experimental` (decision 2026-10-28, `08_STATE.md`; nothing here is
`validated`).* Built from the item 19 layer alone; a test
forbids imagery imports.

- **Network connectivity** on real OSM node topology: components,
  largest-component length share, intersections per km² (degree ≥ 3),
  dead-end ratio (degree 1 over topological nodes) and link-node ratio. It is
  **suppressed** under item 20's low coverage, because under thin mapping a
  dead end measures the mapping, not the place.
- **Paved access** per building: the Euclidean distance from the footprint
  edge to the nearest paved centreline, summarised per building and per block
  (the layer's `blocks()`, the same partition item 22 uses). Paved means the
  `surface` tag where present, otherwise a highway-class DEFAULT. The share of
  buildings whose nearest paved way rests on that default is reported.
  Distances are always computed, carry item 20's confidence, and are UPPER
  bounds when a clause is missing (`partial_fetch`).

**Live, 2026-10-28:**

| AOI | regime | network | components | intersections/km² | dead-end ratio | median building→paved | ≤ 50 m | nearest paved on class default |
|---|---|---|---:|---:|---:|---:|---:|---:|
| chandigarh_central | adequate | reported | 25 | 206 | 0.21 | 11.0 m | 98.1% | 11% |
| dharavi | adequate | reported | 27 | 260 | 0.27 | 17.5 m | 87.5% | **91%** |
| barcelona_eixample | adequate | reported | 36 | 1,375 | 0.09 | 2.8 m | 100% | 0.4% |
| lagos | **very_low** | **suppressed** | — | — | — | 186.8 m (confidence **low**) | 17.2% | 51% |

Degradation is visible: Lagos's topology is suppressed, and its distances carry
low confidence. They also reflect a real 70.8% unpaved-tagged network (item
19). **Dharavi's access figure rests 91% on the class default**, since its
surface tagging covers 16.6% of length, so it is mostly an assumption.
Barcelona's sidewalk footways cut the AOI into 4,771 blocks, only 340 of them
with a building, which inflates per-block counts there.

`tests/test_vector_access.py`, 7 tests: **0 before** (module absent) and **7
passed after**.

### 25. Change over time ✅ *(acceptance met; the pre-registered expectation was NOT met, see below)*
Fraction deltas across composites.

**Why this matters:** the one capability free 10 m imagery has that VHR does not.
For an urban planning product, *"how has this area changed over eight years"* may
be the most valuable output.

**Acceptance:** deltas computed across at least two epochs for one AOI; a change
is attributable to a specific fraction (not "something changed"); the epochs'
observation quality is carried alongside so a cloud-affected epoch cannot
masquerade as change.

**Built 2026-10-28** (`vector/change.py`). *Label: `experimental` (decision 2026-10-28, `08_STATE.md`; nothing here is
`validated`).* **built, vegetation and water only;
`impervious_total`, `paved` and `bare` are `not_computed`.** Every change
record names its fraction. There is no combined "something changed".

- **built:** Open Buildings 2.5D Temporal `building_presence`, mean on the
  10 m grid. Its years (2016–2023) and coverage were verified live before
  use. It is a model score, so it is a built *proxy*, not footprint area. The
  asset's native grid was found live to be **0.5 m** (400 input pixels per
  10 m output pixel).
- **vegetation, water:** item 22's labelled Sentinel-2 index-threshold
  proxies, on two composites over the same calendar window.
- **Units:** item 22's 100 m grid.

**Pre-registered in code before any change data was fetched:**
- the AOI: the Navi Mumbai International Airport site, OSM way 455547086
  bounds, fetched live;
- the epochs;
- `K_NOISE = 3.0`, so a change counts only if |Δ| > 3 × noise for that
  fraction;
- the noise procedure:
  - vegetation and water: the std of split-half composites (days 1–15 vs
    16–31) of the same window, which contain no real change; conservative,
    because a half-composite is noisier than a full one;
  - built: the std of 2022→2023 differences; conservative, because it may
    include real change;
- the observation gates: an epoch below 50% clear at AOI level makes every
  unit `epoch_unreliable`; a unit below 80% coverage in either epoch is
  `insufficient_observation`;
- an expectation: *where change is detected, vegetation mostly DECREASES*.

**Live, 2026-10-28** (1,683 grid units):

| fraction | epoch A | epoch B | noise | threshold | increase | decrease | no detectable change | insufficient obs. |
|---|---|---|---:|---:|---:|---:|---:|---:|
| built | OB Temporal 2019 (1 image) | 2023 (1 image) | 0.0204 | 0.0612 | 44 | 40 | 1,598 | 1 |
| vegetation | S2 2019-01-01..03-31 (34 images, 92.2% clear) | S2 2024-01-01..03-31 (36 images, 96.0% clear) | 0.0419 | 0.1257 | **138** | **75** | 1,469 | 1 |
| water | same | same | 0.0437 | 0.1311 | 66 | 61 | 1,555 | 1 |

**The three checks asked for (2026-10-28):**
1. *The two dates.* Vegetation and water: 2019-01-01..2019-03-31 and
   2024-01-01..2024-03-31. Built: Open Buildings Temporal 2019 and 2023, the
   latest year it has.
2. *Same season: YES for vegetation and water.* The windows are identical
   (Jan–Mar, the dry season, in both years), and a test pins the month-day
   windows equal. *Not applicable to built:* Open Buildings Temporal is one
   annual estimate per year, with no within-year window to match. This is
   stated rather than claimed as a pass.
3. *Threshold a constant fixed before the run: YES.* `K_NOISE = 3.0` and the
   noise procedure were in code before the first live attempt. The noise
   values themselves are measured in the run, as pre-registered. The only
   edit between the failed first attempt and the run reported here was the
   resampling limit (`maxPixels` 64 → 1024). *Limit:* git cannot prove the
   ordering, because `change.py` was not committed before the run.

**Acceptance: met.** Two epochs over one AOI; every change attributable to a
named fraction; each epoch's observation quality carried. **The pre-registered
expectation was NOT met: vegetation increased in 138 units and decreased in
75**, the opposite of the prediction. Not investigated here. One possibility,
not checked, is that the site was already cleared by early 2019 and has since
regrown cover on airside land. The threshold was not changed.

`tests/test_vector_change.py`, 9 tests: **0 before** (module absent) and **9
passed after**.

### 26. Rewire flood risk 🔶 **PARTIAL (2026-10-28) — the final impervious input waits on item 21**

*Validation (decided 2026-09-24; see the Part 4 mandate note): each of the
five hazard calculations is validated by discrimination against observed
inundation (JRC Global Surface Water, Sentinel-1), on its own site(s), with
criteria fixed in advance. Sites are not yet chosen.*
Susceptibility consumes ~~`impervious_total`~~ **fractions, through a runoff
coefficient per fraction** *(amended 2026-09-24)* rather than a discrete
class; roads enter as rasterized vector conduits at hydrology resolution.

**Requirement, decided 2026-09-24 — runoff coefficients per fraction.**
Compacted earth is now labelled `bare`, because `paved` is sealed surfaces
only (Decision 11; `LABELLING_GUIDE.md` §4). So **`impervious_total` no longer
captures compacted earth's runoff**, and it cannot be the only runoff signal.

- Item 26 assigns a runoff coefficient to each fraction instead of treating
  `impervious_total` as the sole runoff input.
- **`bare` gets a non-zero coefficient.** It **may be higher in dense
  informal fabric**, where unsealed ground is typically heavily compacted.
- `mixed_water_vegetation` keeps its own sub-type-weighted hydrological input
  (Decision 11).
- **The exact coefficients are set when item 26 is designed.** Not now.

**Deleted in this item:** the road-proximity penalty (C7, C11) ceases to exist.

**Acceptance:** susceptibility runs end-to-end on fraction input; no reference to
`paved_road` as a class remains anywhere in the flood path; **every fraction's
runoff coefficient is documented with its source, and `bare`'s is non-zero**
*(added 2026-09-24)*.

#### Built 2026-10-28 on `build/flood` — partial

Item 21's fractions do not exist, so the per-fraction runoff input (and with it
the acceptance above) cannot be met yet. What is built uses stand-ins that
declare themselves. Every new output carries `validation_status`; none claims
`validated`.

- **Task 1 — decoupled from the retired 7-class map.**
  `susceptibility/inputs.py` defines a declared surface input (`raster`,
  `source`, `method`, `validation_status`). Pluvial takes `impervious` and
  `infiltration`; waterlogging takes `impervious`. Producers, both
  `placeholder`: **impervious = Open Buildings built AREA fraction** (the
  footprint union's area per cell, never a count, because Open Buildings
  fragments houses — item 23's Chandigarh finding); **infiltration = Lane B's
  Sentinel-2 NDVI vegetation stand-in**, classified at 10 m and averaged to the
  cell. Both sit on a 30 m hydrology grid (`HYDROLOGY_PIXEL_M`, the DEM's
  resolution) in the item 19 layer's UTM CRS. An output is no more validated
  than its weakest input, so pluvial and waterlogging are `placeholder`.
  `pipeline.py` builds the inputs as a contained context layer
  (`flood_inputs`) and reprojects the waterway distance map onto that grid;
  `hydrological_surfaces` stays in `result.json` as a legacy record that
  nothing consumes. `zonal/landcover_screening.py` now reports per-ward
  pluvial and waterlogging as `not_calculated` (no per-ward inputs exist).
  The applicability gate moves pluvial and waterlogging to
  `LANDCOVER_INDEPENDENT`. Tests: `tests/test_flood_inputs.py` (20; an AST
  scan proves no `susceptibility/` module names the 7-class map, and 9 fail on
  the old code), two pipeline-boundary tests.
- **Task 2 — the road-proximity penalty (C7, C11) is deleted.** The
  road and waterway penalty block in `run_inference` (formerly
  `inference.py:607-624`), both `*_PROXIMITY_PENALTY_STRENGTH` constants and
  `run_inference`'s `road_dist_map` / `waterway_dist_map` parameters are gone,
  and `pipeline.py` no longer passes them. `compute_road_distance_map` stays:
  segment `road_access_score` still reads it, and that is not a penalty.
  `git grep` for the penalty finds only the deletion comment.
  `tests/test_proximity_penalty_deleted.py` (3; all fail on the old code).
- **Task 3 — roads as rasterised vector conduits.** `road_conduits()`
  rasterises item 19's road space (OSM centrelines at `HIGHWAY_WIDTH_M_DEFAULT`
  class widths; footprint negative space excluded, since it is open ground) as
  an area fraction per 30 m hydrology cell, supersampled to 2 m so area is
  preserved. It enters pluvial as `road_conduit` (weight 0.6, quality 0.5,
  provisional) — the sealed road surface that built area omits.
  `experimental` (item 19's own label). `tests/test_flood_conduits.py` (5;
  they fail on the old code, where `road_conduits` does not exist).
- **Task 4 — DEM hydrology as pluvial inputs.** `susceptibility/terrain.py`
  derives four per-cell inputs from FABDEM on the 30 m hydrology grid:
  `low_slope`, `flow_accumulation` (D8), `topographic_hollow` (−TPI, 150 m
  radius) and `drainage_disconnection` (D8 path ends in an interior pit, not
  the grid edge). D8 runs on the **unfilled** DEM on purpose — a closed
  depression is where rain ponds. Each has its own weight and quality, and the
  three normalisations are module constants fixed before any real DEM was run
  (`configs/pluvial_constants.py`; all provisional). `experimental`. Smoke run
  on Dharavi (FABDEM 0–12.0 m, mean 4.89): component means 0.854 / 0.102 /
  0.125 / **0.914** — on flat ground almost every cell ends in a pit, so
  `drainage_disconnection` is near-saturated there (listed for a fate, not
  tuned). A first smoke run returned a constant DEM because `mosaic()` drops
  FABDEM's native projection; fixed before commit. `tests/test_flood_terrain.py`
  (8, synthetic planes and bowls; they fail on the old code, where the module
  does not exist).
- **Task 5 — ward-ranking test (evidence only; nothing changed on it).**
  Pre-registered first (`experiments/ward_ranking/PREREGISTRATION.md`,
  SHA256 `881d5665…`): Spearman ρ over Mumbai's 24 BMC wards (the wide run
  behind the Dharavi ward screening), **stable if ρ ≥ 0.80** per pair. The
  brief's "08_STATE §5.7 option C3" does not exist on any branch; the brief's
  own description was followed. Estimates: (a) stored spectral
  `impervious_fraction_pct`, (b) Open Buildings footprint built area,
  (c) `built + max(0, 1 − built − vegetation − water)`. **Result: all three
  pairs stable** — ρ(a,b) = **0.920**, ρ(a,c) = **0.906**, ρ(b,c) =
  **0.960**, n = 24. The ward *order* holds; the *levels* do not: built area
  is about 0.4× the stored estimate (ward A 0.216 vs 0.508), so absolute
  thresholds would not transfer between estimates. `validation_status:
  experimental`. A first run hung silently for 2 h 40 min on one Earth Engine
  reduction; the rerun sets a 10-minute deadline with one retry (no retry
  fired). `tests/test_ward_ranking.py` (3, the verdict logic).
- **Task 6 — one 2,500 mm rainfall ceiling.** The duplicate in
  `configs/waterlogging_constants.py` (item 66's finding) is removed;
  waterlogging imports `FLASH_FLOOD_RAINFALL_NORMALIZATION_MAX_MM` from
  `configs/flash_flood_constants.py`, the single definition.
  `docs/susceptibility_dag.md` updated. `tests/test_rainfall_ceiling_single_definition.py`
  (2; both fail on the old code).
- **Task 7 — `test_flood_flag_combination` fixed, not deleted.** It guards a
  real regression (each elevation source judged on its own status), so it is
  kept. Its fixture patched functions `pipeline.py` no longer has
  (`get_best_image`, `save_masks`, `get_imagery_acquisition_date`) and errored
  at setup; it now builds on the maintained `stub_pipeline` fixture and lets
  the real Open Elevation source and the conftest mocks drive the assessment.
  **Errors 3 → 0**; all three pass, and the "both sources fail →
  insufficient_evidence" case confirms the mocks reach the logic.
- **Task 8 — flood validation harness (Tier 2), run.** Pre-registered per
  module before any score or reference was computed
  (`experiments/flood_validation/PREREGISTRATION.md`, SHA256 `d4b5e563…` in the
  result file): ROC AUC of the module's score over 30 m cells, flooded vs dry,
  JRC permanent water excluded; **validated if AUC ≥ 0.70**; not-run below 50
  flooded / 50 dry cells or, for pooled scalar modules, below 3 sites.
  References: Sentinel-1 event extents (the project's VV −3 dB drop rule) or
  JRC GSW recurrent water (5–80 % occurrence). **No module validated.**

  | Module | Reference, sites | AUC | Verdict |
  |---|---|---|---|
  | pluvial | S1, Dharavi, Mumbai 2017-08-29 (502 flooded / 7,373 dry cells) | 0.533 | **failed** |
  | fluvial | JRC, 9 `BASELINE_AOIS` (held-out Lagos, Nairobi excluded) | 0.448 | **failed** |
  | waterlogging | JRC, same 9 AOIs | 0.432 | **failed** |
  | coastal | S1, Beira / Chennai / Fort Myers Beach | — | **not-run**: no S1 image in any 3-day event window |
  | flash flood | S1, Paiporta / Derna / Bad Neuenahr | 0.447 | **failed** |

  Read with the stated weaknesses: four modules emit one AOI-wide scalar, so
  their AUC is a ranking of a handful of sites; SAR misses urban flooding
  (double bounce); and the pluvial inputs are placeholders. A fail is still a
  fail against the bar. Module labels are unchanged (nothing became
  `validated`). `tests/test_flood_validation_harness.py` (4: AUC, ties,
  pooled counts, verdict and minimums).

#### Phase 1a — flood round 2, on `build/flood2` (2026-10-28) — item 26 stays partial

Pre-registered first, before any round-2 score was computed
(`experiments/flood_validation/PREREGISTRATION_ROUND2.md`, SHA256
`f2ab3c74…`, commit `45307b8`). It fixes, per module, the reference events,
the metric (AUC), the bar (0.70, unchanged), the per-pixel formulas and
constants, a finite weight grid, and a fixed split into tuning and held-out
events. Weights move only on tuning events, and the verdict is the held-out
result.

- **Task 1 — fluvial, flash flood and waterlogging are per-pixel maps.**
  `susceptibility/hydro_rasters.py` samples their inputs onto one 30 m grid.
  Each Earth Engine call has a 600 s hard deadline via `ee_timeout.call`,
  and a rainfall timeout loses only that layer:
  - MERIT Hydro HAND, bilinear;
  - MERIT upstream area, focal max within 1 km, so a cell reads the
    drainage line that floods it, not its own near-zero `upa`;
  - FABDEM slope, and its 1 km focal mean;
  - CHIRPS mean annual total;
  - IMERG V07 p99.9 half-hourly rate over the 10 years before the
    reference year.

  The modules:
  - **Fluvial** = `low_hand` (1 − HAND/30) plus an optional `river_size`
    (log upstream area / log 10,000 km²). Its default weights are round 1's
    HAND-only method.
  - **Flash flood** = `valley_floor` (1 − HAND/10), `steep_surroundings`
    (relief slope/15°, *not* the cell's own slope, which would rank
    hillsides above the valley floors that flood), `small_catchment`
    (1 − upa/50 km²) and `rainfall_intensity` (IMERG/20 mm h⁻¹). The last
    replaces the annual-total proxy.
  - **Waterlogging** = `low_relief` (1 − HAND/15), per-cell `impervious`
    (built/0.70), `flatness` (1 − slope/5°) and CHIRPS/2,500 mm.

  The old ceilings are kept as provisional constants, and the new ones are
  in `configs/*_constants.py`. Each module returns `susceptibility_map`,
  with `spatial: true`, and `aoi_mean_score` is the map's mean. Without
  rasters each returns `insufficient_evidence`; there is no scalar
  fallback. `pipeline.py` fetches the rasters on the flood-input grid
  (`hydro_rasters` block, contained like every context layer) and saves the
  three maps. `zonal/hazard_screening.py` scores each ward from the per-pixel
  maps over its bbox, with rainfall intensity excluded per ward (one 0.1°
  value cannot rank wards) and recorded. `docs/susceptibility_dag.md` is
  updated.

  Tests: `tests/test_flood_per_pixel.py` (18), which fail on the old code
  (ImportError: `hydro_rasters` did not exist). `test_fluvial_susceptibility`
  was rewritten for rasters (8; all fail on the old code).
  `test_pipeline_layer_boundary` gained a `fetch_hydro_rasters` stub, and a
  failed-raster test replaces the old slope one (it errors at setup on the
  old code). The gating, validation-status, flood-input and rainfall-ceiling
  tests moved to the new signatures. Suite **727 → 748 passed**, with the
  same 2 Earth Engine-auth failures.

- **Task 2 — better references.** `experiments/flood_validation/references.py`
  adds two sources beside Sentinel-1 and JRC:
  - **Copernicus EMS rapid-mapping delineations.** These are the public
    dashboard API's DEL products, `observedEventA` polygons with notation
    `Flooded area` or `Flood trace`. A 30 m cell is flooded if ≥ half its area
    is covered (rasterised at 3 m), and valid if ≥ half lies in the product
    extent. The layer is cached, with its SHA256 in the result. Only
    activations from EMSR656 (2023) on are public without login.
  - **The Global Flood Database.** This is MODIS 250 m, scored on 240 m
    blocks.

  Sentinel-1 is tightened to the earliest acquisition date in the event
  window, against a same-relative-orbit pre-event median. Each reference
  records its source, resolution and the dates of the images actually used.
  JRC permanent water is excluded everywhere. Earth Engine calls run under a
  600 s hard deadline, and HTTP under 120 s. Tests:
  `tests/test_flood_references_round2.py` (8; they fail on the old code,
  where the module does not exist).

- **Task 3 — coastal gets a testable Sentinel-1 window.** The window is
  pre-registered as the event day through day + 12
  (`S1_EVENT_WINDOW_DAYS["coastal"] = 13`), against 3 days for the other
  modules. Twelve days is Sentinel-1's single-satellite repeat since S1B
  failed, so it is the shortest window that guarantees a pass. Round 1's
  3-day window held no image at any coastal site (C53). The stated cost is
  that surge water drains within days, so a late image undercounts: Beira's
  and Fort Myers Beach's first images are at day + 4. Chennai has no image
  within + 12 (its next is + 20 or later) and is dropped from coastal. Tests:
  3 added to `tests/test_flood_references_round2.py`. They fail on the old
  code, where the constant does not exist. Both coastal sites are not-run
  under round 1's window and testable under the new one.

---

# PART 5 — Validation discipline 🔓

*Six items. What keeps the new system honest.*

### 27. Held-out firewall ✅
~~Split the 331 human labels.~~ A subset **never touches training** — it exists
solely to validate.

**This is the only independent signal available**, and the architecture change
does not create one. Enforce it in code, not convention.

**Acceptance:** the split is recorded in a file, hashed, and the training path
raises if it reads a held-out record.

*Re-scoped and built 2026-10-28.* The 331 human labels belong to the retired
7-class pipeline (`08_STATE.md` §RETIRED) and are not covered. The held-out
set is the item 21 hand-traced fraction tiles, **held out by validation site**:
Makoko, Kibera and Rocinha (sealed batches 1 and 2), plus any record naming
their host cities Lagos, Nairobi and Rio (the firewall is city-level).

- `configs/heldout_split.json` registers them **by path and tile-ID pattern
  only** — the validation tiles are not selected yet, and no tile data was
  read. Its SHA256 is in `ARTIFACT_HASHES.txt`; `load_split` refuses a
  mismatch.
- `experiments/harness/firewall.py`: `training_tiles` is the training path's
  way in for hand tiles. It checks the whole set before any file is touched,
  and one held-out tile refuses all of it (`HeldOutError`, no override).
  **The item 21 Stage 1 trainer, not yet written, must take its tiles through
  `training_tiles`.** Other training reads use `assert_training_set`.
- The split's notes carry the §RETIRED lesson: **the fraction validation set
  is drawn from the full raster, not from annotated segments.**
- `tests/test_heldout_firewall.py`: training on the 8 Stage 1 tiles passes;
  training on that set plus one validation tile raises (each site, a misfiled
  tile, a sealed-batch tile). The training-path tests failed (6 of 21: "DID NOT
  RAISE") before the guard was added to `training_tiles`.

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

### 30. ~~Test logit adjustment~~ ❌ **DELETED 2026-09-23**
**Deleted, not conditional.** This item existed only for a discrete
classification step ("subtract `τ·log(π_y)` before softmax"). There is no
softmax and no argmax anywhere in the fraction architecture, and the 4-class
discrete taxonomy that was the last possible host for one is **retired** (see
`09_TAXONOMY_MIGRATION_PLAN.md`). The condition it was held open against —
"only if any discrete classification step remains" — can no longer be met.

The one part worth keeping was the ablation ("correct the prior, then check
whether precision improves; if it does not, the residual is feature
genericness"). **That question has since been answered directly and more
strongly**: item 21 measured the `built`/`paved` spectral angle at 1.66°, which
is the feature-genericness argument established by measurement rather than
inferred from a prior-correction ablation. Nothing is lost by deleting this.

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
`observed_fraction` field, and ~~three separately-reported non-observation
fields (shadow, cloud/nodata, low-confidence unmixing)~~ separately-reported
fields in **two groups** rather than one merged "unknown":

- **Observability**, which defines the denominator: cloud/nodata, fully
  shadowed pixels, transient snow, fire/smoke, ships.
- **Estimate quality**, which never touches the denominator: the per-fraction
  **regression prediction interval**, plus `paved`'s derivation uncertainty.

*(Reworded 2026-09-25, applying Decision 14 (b) and (c) as signed off
2026-09-23, and the 2026-09-24 occlusion list and shadow rule.)* Read each item below against that fraction-pipeline vocabulary,
not the classification-pipeline vocabulary the original text may still
suggest. See `04_FINDINGS_LEDGER.md`'s Part 6 translation note for the full
mapping.

### 33. C19 — denominator + `observed_fraction` ✅ *(2026-10-28, in the analysis pipeline; the retired 7-class pipeline is not changed)*

> **Built 2026-10-28 (`analysis/observability.py`, Phase 2).** A pixel is
> observed with ≥ `MIN_VALID_OBS` clear Sentinel-2 observations, and shadow
> (SCL 3) and snow (SCL 11) observations now leave the composite as cloud
> and no-data already did. `observed_fraction` is emitted beside every
> fraction, and every output of the result carries a coverage sibling (the
> result contract enforces it). Observability: `cloud_nodata`
> (`experimental`), `fully_shadowed` and `transient_snow` (`placeholder`:
> SCL only — no solar geometry, no permanent-snow layer), `fire_smoke` and
> `ships` (`not_computed`). Each is the share of pixel-scene observations it
> removed; they are not summed. Estimate quality: per-fraction
> `prediction_interval` and `paved_derivation_uncertainty`, all
> `not_computed` until item 21, and `observed_fraction` reads only the
> clear-observation count. Tests: `tests/test_observability.py`.
Apply Decision 14's convention. **Emit `observed_fraction` as a mandatory
sibling field** — fixing the denominator alone just moves the bias. Emit
~~shadow / cloud-nodata / low-confidence-unmixing as three separate fields~~
each observability cause (cloud/nodata, fully shadowed, transient snow,
fire/smoke, ships) as its own field, and the per-fraction **regression
prediction interval** as a separate estimate-quality field — never merged
*(reworded 2026-09-25 per Decision 14 (b)/(c))*.

**Acceptance:** no derived physical quantity is emitted without its coverage
sibling; ~~the three non-observation components are independently readable~~
every observability field and every estimate-quality field is independently
readable, not summed into one number by the producer, and **no
estimate-quality field reduces the denominator** *(reworded 2026-09-25)*.

### 34. C21 — `hydrological_surfaces.py` status field and failure path ✅ *(2026-10-28)*

> **Built 2026-10-28 (Phase 2).** `compute_hydrological_surfaces()` returns
> `status` on every path; an all-unknown AOI (empty or all-zero
> `category_area_pct`) gives `insufficient_evidence` with both surfaces
> `None`. The once-dead branches are reachable and tested — the ledger's
> line numbers are stale; today they are `applicability.py:71`
> (`finalize_applicability`) and `:210` (`compute_applicability`), both
> waterlogging `not_calculated`, and `waterlogging.py:65`
> (`insufficient_evidence`). In the analysis pipeline an AOI with no
> footprint source gives unobserved imperviousness rather than zero, and an
> AOI with every highway clause unretrieved gives no conduit input; a
> synthetic all-unknown AOI is `insufficient_evidence` / `not_applicable` on
> every hazard. `hydrological_surfaces` itself is a legacy-only record
> (label `retired`). Tests: `tests/test_item34_insufficient_evidence.py`.
The only module in the analysis chain with neither. That single omission produces
C19, C21, and C25, and makes two separate guard clauses vacuous.

**Acceptance:** a synthetic all-unknown AOI produces `insufficient_evidence`
throughout rather than `score: 0.0, class: "very_low"`. **The two dead
`insufficient_evidence` branches at `applicability.py:133` and
`waterlogging.py:57` become reachable and are unit-tested.**

### 35. C25 / C26 — ward coverage fields ✅ *(2026-10-28, in the analysis pipeline)*

> **Built 2026-10-28 (`analysis/wards.py`, Phase 2).** Every served unit —
> item 22's grid / footprint / path units and `ward:<boundary_id>` wards —
> carries `observability.observed_fraction` (observed share of its area) and
> `observability.valid_pixel_count` (observed 10 m pixels with their centre in
> the unit, beside `pixel_count`), on the same denominator as the fractions.
> A fully dark unit serves its fractions as `insufficient_observation` with
> `value: null`; a half-observed unit's value is over its observed part (the
> C25 case). Phase 12A's `zonal/` ward screening is not changed by this item.
> Tests: `tests/test_item35_ward_coverage.py`.
Emit per-ward `observed_fraction` and valid-pixel count, per Decision 14's
convention. C26 is what makes C25 detectable.

**Acceptance:** a 100%-unobserved and a 50%-unobserved ward are distinguishable
from the output alone, without inference.

### 36. C33 — absent ≠ measured-zero 🔶 **PARTIAL (2026-10-28) — backend and renderer helper done; no UI view of the new result yet**

> **Built 2026-10-28 (Phase 2).** Backend: the result contract
> (`analysis/contract.py`) refuses a `null` value without an absent status
> (`not_computed`, `insufficient_observation`, `timeout`, ...) and refuses a
> number whose status is not `available`, across the whole result and every
> served ward, so a zero is always a measured zero
> (`tests/test_result_contract.py`). Renderer: `fmtMeasured()` in
> `geowatch-ui/src/render.js` renders absent as "—" plus its reason and zero
> as "0.0%", checked in `tests/test_measured_vs_absent_ui.mjs`. **Stays
> partial** because no UI view renders the analysis result yet: `App.jsx`
> still renders the legacy shape (where `fmtPct` already returns "—" for
> null).
`null`/absent and `0` must be distinguishable end to end. Absent renders as "—"
or "not measured"; zero renders as "0.0%".

**Copy the existing correct pattern** — `road_access_score === -1` → "N/A", and
the gated modules' status pills. Do not invent a new one.

### 37. C22 — no-data must not collide with real classes ✅ *(2026-10-28, in the analysis pipeline)*

> **Built 2026-10-28 (`analysis/rasters.py`, Phase 2).** The pluvial map is
> stored as an RGBA PNG (`GET /api/results/{id}/maps/pluvial_susceptibility`,
> public). Observed cells take their tier's colour at alpha 255; no-data
> cells are alpha 0 — a state of their own, not a colour on the scale — and
> the legend lists it separately. The mask is propagated, not re-derived:
> fewer than `MIN_VALID_OBS` clear observations at ingestion → NaN
> vegetation → NaN infiltration → NaN pluvial cell → transparent pixel. The
> legacy preview (`save_pluvial_susceptibility_output`, NaN rendered black)
> is retired with its pipeline and not changed. Tests:
> `tests/test_item37_nodata_render.py`.
The surviving defect: no-data scores identically to `standing_water` and
`active_construction`. Give it a distinct render state — never a value on the
susceptibility scale.

*Requires a nodata mask propagated from ingestion through to render, which may be
the larger part of the work.*

### 38. C27 — timeout ≠ tier ✅ *(2026-10-28)*

> **Built 2026-10-28 (Phase 2), in both places.** `zonal/hazard_screening.py`
> (C27's own site): a timed-out context is now `status: "timeout"`, not
> `"unavailable"`; a ward hazard block with any timed-out input is
> `status: "timeout"` with `score` and `tier` `null` and the error kept in
> `error` / `timed_out_inputs`, and every non-available input's status and
> error survive in `input_status`. In the analysis pipeline every context
> layer and spatial input is a timed stage; a module with an input that timed
> out or failed is emitted with that status and no tier (the partial score is
> withheld, `score_from_partial_inputs_withheld`), and every ward unit
> inherits it. A run with any incomplete stage is never cached, so a retry
> can complete it. Tests: `tests/test_item38_timeout_not_tier.py` — two runs
> give identical tiers or an explicit `timeout` status, on both paths.
Preserve the error at the ward boundary. A timeout must produce
`status: "timeout"`, **never a tier**.

**Acceptance:** two consecutive runs of the same wards produce identical tiers,
or explicitly differing `status` fields explaining why.

### 39. C15 — derive the claim, do not latch it ✅ *(2026-10-28)*

> **Built 2026-10-28 (Phase 2).** Legacy pipeline (C15's site):
> `pipeline.derive_osm_context()` computes `osm_available`,
> `road_access_scores_reliable` and `road_score_method` after the distance
> map and every segment score exist; a run whose scores are all the -1.0
> sentinel, or that has no distance map, can no longer claim
> `distance_transform`. Analysis pipeline: `osm_coverage.osm_claims` is
> derived after the layer is built and pluvial has run (`osm_available` from
> the ways actually retrieved, `road_conduits_used_by_pluvial` from pluvial's
> own `components_used`). Tests: `tests/test_item39_derived_claims.py`.
Compute `osm_available` and the reliability claim **from the actual outcome**,
after the map is built.

**The general principle:** a claim must be derived from an outcome, never
asserted ahead of it. Same shape as C37.

---

# PART 7 — Gating architecture ✅ **COMPLETE**

*Three items, all done. Two signals that were computed correctly and then
discarded: `applicability` died three times (C14 → C20 → C32, items 40 and 41)
and the Gate C waiver died twice (C23 → C24, item 42). Both are now carried
from the point of computation through to the screen.*

### 40. C14 / C20 — `applicability` gates downstream ✅
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

**Built.** `tests/test_applicability_gating.py`, 23 tests, all passing. The
acceptance assertion is `test_every_block_carries_the_flag`: 11 blocks — five
susceptibility, exposure, and five risk — every one carrying a flag, with the
gate reporting something other than `not_wired`.

**The ordering was a real cycle, not a simple mis-ordering.**
`compute_applicability()` *read* `hydrological_surfaces`, for one check: whether
`waterlogging` has a usable input. So the call could not just be moved. Split
into two stages — stage 1 decides everything depending only on inference output
and external context and runs first; `finalize_applicability()` runs after the
surfaces exist and resolves the single status that needed them. Proved
behaviour-preserving across **all 192 input combinations** before the reorder
landed, and that equivalence is pinned by a test.

*Noted while there: the resolved check is **vacuous**. It asks whether
`impervious_fraction_pct is not None`, and `compute_hydrological_surfaces()`
always returns a float on every path because it has no failure path at all —
C21/S1 at this exact site. The guard is preserved exactly as written rather than
"fixed", because making it meaningful means giving that module a real failure
path, which is C21's item, not this one.*

**Compute-and-flag, per rule 3.** No value is ever withheld; a test asserts the
score survives an OOD verdict. Withholding would have invented a fourth
ambiguous state for downstream code to guess about — S1 again, in a new costume.

**The dependency chain is modelled, per rule 4, and blanket-flagging is
explicitly rejected.** Traced through the code: `pluvial` consumes the
classified raster, `waterlogging` consumes `hydrological_surfaces` (a weighted
sum of `category_area_pct`), and `exposure` consumes `landcover_builtup_pct` —
so those three inherit the land-cover verdict. `fluvial` reads MERIT Hydro,
`coastal` a GEE shoreline dataset, `flash_flood` slope and upstream catchment —
**none touch the semantic model, so none is marked OOD by it.** Marking them
anyway would be false, and would train a reader to ignore the flag the way
C33's `{pct ? ... : '0.0%'}` taught readers that "0.0%" means nothing. A test
asserts each direction, so a later "simplification" into blanket-flagging fails.

`compute_risk()` inherits instead: it has no applicability entry of its own, so
it takes the worst trust of the hazard and exposure it consumed and carries
their `degraded_by` forward.

**Enforcement is a decorator at the function boundary**, not edits to ~15
individual `return` statements. These consumers have several early returns each
(`insufficient_evidence`, `not_applicable`, the success path) and the acceptance
criterion is *every* block — a rule applied at the boundary cannot miss a path.
Same argument that made item 70's auth middleware rather than per-endpoint.

A consumer called without the gate reports `gate: "not_wired"` rather than
presenting itself as trusted — silently implying trust is precisely C14.

*Does not close C32 (the frontend still never renders it) — that is item 41.*

### 41. C32 — render it ✅
Surface `applicability` as a prominent banner, not a buried field. Add to
`NAV_SECTIONS`.

**Acceptance:** an AOI that trips `out_of_distribution` produces a UI where the
user cannot miss it.

**Built.** `tests/test_applicability_ui.mjs`, 15 tests, all passing
(`node tests/test_applicability_ui.mjs`). C32's three specific claims are now
all false — measured before and after:

| C32's claim | before | after |
|---|---:|---:|
| `applicability` occurrences in `App.jsx` | 1 | 12 |
| `NAV_SECTIONS` entries | 6 | 7 |
| `result.applicability` ever read | no | yes |

**Three surfaces, because "cannot miss it" is not one thing.** A banner above
every section, so a flagged run cannot be read without meeting it first; the
`Reliability` nav entry itself turns coral with a dot and an `OOD`/`WEAK` tag,
because the sidebar is always on screen and the banner is not; and a
`BlockTrustNote` beside each affected number in Hazard, Exposure and Risk,
because "not a buried field" has to mean the warning travels *with the value*,
not merely that a banner exists somewhere above it.

**Loud only when there is something to be loud about.** On a clean run the
banner collapses to one quiet confirmation line. A banner that fires on every
run trains readers to scroll past it — the same mechanism that made C33's
`{pct ? ... : '0.0%'}` meaningless. The quiet line still appears, because
silence would leave a reader unable to tell *checked and fine* from *never
checked*, and that collapse is S1.

**The UI reads, it never re-derives.** Trust comes from the flag item 40 emits
on every block. Recomputing it in JavaScript from `unknown_pct` and a threshold
would recreate C31 exactly — a Python rule restated in JS, drifting silently.
A test forges a block whose status contradicts any threshold rule and asserts
the UI follows the block, plus greps the module to assert the threshold is not
reimplemented.

**Absence does not read as approval.** A run predating item 40 carries no
`applicability` block; it renders as *not checked*, and its blocks are counted
`ungated` rather than `unaffected`. Asserted by a fixture with every flag
stripped.

*Fixtures are generated from the real backend, not hand-written — a
hand-written fixture lets the UI test keep passing while the emitted shape
moves underneath it, which is C31's failure mode applied to tests.*

**Verification note:** `geowatch-ui` has no test runner installed, so the
reliability logic lives in a plain module (`geowatch-ui/src/applicability.js`)
that `node` imports directly, with no new dependencies. JSX validity is covered
by `vite build` (passes, 41 modules) and `oxlint` (passes, **no new findings** —
the 3 reported are pre-existing and identical on the unmodified file).

*Separate finding, not fixed here: `tests/FloodAssessmentPanel.test.jsx` cannot
run. It imports `vitest` and `@testing-library/react`, neither installed, and
`../src/FloodAssessmentPanel`, which does not exist in `src/`. A test that
cannot fail is decoration — the same standard C16 and item 47 were held to.
Worth its own item.*

### 42. C23 / C24 — Gate C waiver on all paths, rendered ✅
`product_validation_status` must be present on the `not_calculated` path too, and
the frontend must read it.

**The susceptibility panel already does this correctly, in the same file.** Copy
that pattern. Low effort, high integrity value.

**Note:** this is distinct from Decision 17's Gate C closure (advisor review
against D.7). This item fixes how the waiver *status field* propagates through
code; Decision 17 settles how Gate C itself is *validated*. Both are needed;
neither substitutes for the other.

**Built.** `tests/test_gate_c_waiver.py` (22 tests) and
`tests/test_gate_c_ui.mjs` (11 tests), all passing. C23 and C24 reproduced
against the unmodified code first:

| | before | after |
|---|---|---|
| exposure `not_calculated` keys | `['label','layer_id','reason','status']` | `+ product_validation_status` |
| `.get('product_validation_status')` | `None` | `'waived_pending_real_user_validation'` |
| `product_validation_status` in `App.jsx` | 0 | 6 |

**Why `None` was the bug, not merely untidy.** `None` is also what a caller sees
once Gate C is **passed** and the waiver field is removed. So *"never reviewed
by a real user"* and *"reviewed and cleared"* arrived as the same value — the
waiver did not weaken, it **inverted**, on the one path nobody exercised.

**The same defect, one level up, was fixed in the same pass.** `compute_risk()`
has four return paths and carried `exposure_product_validation_status` on only
the last. The three early returns are the ones that actually fire in Phase 10A,
since the fusion methodology is deliberately undefined — so the waiver vanished
on *every real run*, at the layer `risk/compute.py`'s own docstring calls "the
most consequential output this system produces", in the very field that
docstring demands be propagated "rather than silently disappearing two layers up
the stack." All four paths now route through one helper.

**A third state was needed.** "Waived", "no product to validate", and "passed"
are three different things; C23 collapsed the first and third. `GATE_C_STATUS`
and the new `GATE_C_STATUS_NO_PRODUCT` sit together in `exposure/compute.py`,
keeping that module's "single source of truth — do not hardcode the string"
rule. A test asserts the literal is not re-hardcoded inside the function.

**The frontend copies the susceptibility panel, verbatim.** Same
`status=` prop on `ReportCard` → `StatusPill` in the header; and `GateCNote`
reuses that panel's caveat-span style object *unchanged*
(`FONTS.body, fontSize: 11, color: C.textDim`), asserted by a test that greps
both. `waived_pending_real_user_validation` was **already** in `STATUS_META`
before this item — the vocabulary existed with nothing feeding it, which is
precisely C24's "the discipline exists; it just was not applied here." It is
extended, not replaced.

---

# PART 8 — Contract enforcement 🔓

*Six items. Rules that comments cannot enforce. Five are done (43, 44, 45, 47,
70); one remains: 46.*

### 43. C31 — single-source palette ✅
**The quick fix is copying values across. The correct fix is a single source of
truth** — emit the palette into `result.json` from the backend and have the
frontend read it, so drift becomes structurally impossible.

**Acceptance:** changing a colour in the backend changes the legend with **no
frontend edit.**

**Built.** `tests/test_palette_single_source.py` (20 tests) and
`tests/test_palette_ui.mjs` (14 tests), all passing. The 0/8 drift was
reproduced numerically first, matching the ledger including its worst case:

| category | backend | frontend | Δ |
|---|---|---|---|
| `dense_informal_roofing` | `#e03c3c` | `#e0625a` | (0, 38, 30) |
| `sparse_informal_roofing` | `#f08c50` | `#e8a35a` | (8, 23, 10) |
| `paved_road` | `#7878b4` | `#8888c8` | (16, 16, 20) |
| `standing_water` | `#2864c8` | `#4a90e2` | (34, 44, 26) |
| `vegetation_clearing` | `#d2c850` | `#d8c85a` | (6, 0, 10) |
| `active_construction` | `#c850c8` | `#c878d0` | (0, 40, 8) |
| `dense_vegetation` | `#3cb450` | `#5ed99b` | **(34, 37, 75)** |
| `unknown` | `#606080` | `#716fa0` | (17, 15, 32) |

**The acceptance test is behavioural, not structural.** It mutates the backend
palette, re-emits it through the real `palette_for_result()`, reads what the
frontend resolver returns — and asserts `App.jsx` is byte-identical before and
after, so "no frontend edit" is verified rather than asserted.

**One definition, in `configs/palette.py`.** `inference.py` now re-exports it,
and the comment that made the unenforceable promise — *"must match App.jsx's
CAT_COLORS ... exactly"*, a Python comment asserting a JavaScript constant, S3
in one line — is gone. `App.jsx`'s `CAT_COLORS` literal is deleted outright.
A test asserts the canonical hex values appear **nowhere** in `App.jsx`: not
even correct copies, because a correct copy still drifts at the next edit, which
is how 0/8 happened.

*The OSM-only three (`unpaved_dirt_road`, `open_drainage_channel`,
`open_waste`) are included in the emitted palette, so the frontend needs no
private map for them either. Without that, the single source of truth would
have been only three-quarters true.*

**Legacy runs still render.** `palette.js` keeps a frozen shim of the OLD
frontend values for results predating this item — deliberately the *wrong*
values, since that is what those runs were rendered with when produced. A test
asserts it never mirrors the canonical values, so it cannot be "fixed" into a
second live source.

**⚠️ A third copy exists and is deliberately untouched.** `annotate.py`'s
`CATEGORY_COLORS` also disagrees (`dense_informal_roofing` 220 vs 224). It is a
standalone annotation tool, not on the pipeline → `result.json` → frontend path
C31 measured, so changing it under an item that did not scope it would be a
silent behaviour change to a tool with no tests. **Worth its own item.** A test
asserts the disagreement still exists, so the note cannot rot.

---

**Second half: the `X-API-Key` header, closing live breakage.**

Item 70 put an API-key check at the perimeter of `api.py`. This frontend sent no
header on any request, so **every call had been returning 401 since that
shipped** — analysis, OSM overlays, and the landcover image alike. Verified
against a live server: without the header `/api/runs` and `/runs/*` both 401;
with it, 200 and 404-from-StaticFiles respectively. CORS preflight was also
verified to admit the custom header.

*The landcover overlay needed more than a header.* Leaflet's `<ImageOverlay>`
loads a plain `<img>`, which **cannot carry a custom header**, and `/runs` is
behind the key. The bytes are now fetched with credentials and handed over as a
blob URL (revoked on unmount). The alternatives were rejected on the record: a
key in the query string puts the secret into URLs, history and logs; exempting
the mount reopens exactly the hole item 70 closed, since `/runs` serves
`data/pipeline_runs/` — the same data C34 would have disclosed.

*Every request now routes through `apiFetch`*, so a newly added call is
authenticated by construction rather than by someone remembering — the same
argument item 70 used for middleware over per-endpoint checks.

**⚠️ Honest limit, recorded in `api.js` and `.env.example`:** Vite **inlines**
`VITE_*` values into the built bundle, so anyone who loads the page can read the
key. That is a property of shipping a secret to a browser, not a defect here.
This is a **development shared secret for a localhost tool, not client
authentication** — adequate because the API binds to `127.0.0.1` and CORS admits
only localhost, and *not* adequate if this is ever deployed, which would need a
server-side session or per-user tokens.

### 44. C4 — assert band order at runtime ✅
Verify against the file's actual band descriptions at load time, not a
top-of-file comment.

**Built.** `tests/test_band_order.py`, 30 tests, all passing.

**⚠️ The item as specified could not work, and the fix is larger because of it.**
Measured before building: **150 of 150** GeoTIFFs this project has produced
report `descriptions == (None,) * 6`. Neither `geemap.ee_export_image` nor the
chunked stitcher writes band descriptions. So "check the file's actual band
descriptions" had nothing to read — asserting equality would have failed every
existing run, and asserting only-when-present would never have fired. A check
that cannot fail is decoration, which is the standard C16 and item 47 were held
to.

Four parts, because the contract had to be *created* before it could be checked:

1. **`BAND_NAMES` is derived from `sentinel2.py`**, not retyped, plus an
   import-time assertion. The comment said the two must match; now they are the
   same list and cannot disagree.
2. **`RGB_BAND_INDICES` is derived from `BAND_NAMES`** rather than pinned to
   2/1/0. *This is the half that kills C4 at the root* — a reorder now moves the
   indices with it, so the swap is impossible rather than merely detectable.
   Values are unchanged today (`Red: 2, Green: 1, Blue: 0`).
3. **Exports stamp the band names into the file**, so the contract travels with
   the data. Best-effort: failing to annotate a good export must not discard it.
4. **Both read boundaries verify against the file** — `generate_tiles` (the
   training path, where a wrong order is baked into every `.npy`) and
   `generate_rgb_preview_tiles` (which actually indexes with
   `RGB_BAND_INDICES`).

**Three verdicts, kept distinct:** `verified`, `mismatch` (always raises), and
`unverifiable` — descriptions absent, the state all 150 existing files are in.
Letting that third state read as "verified" would be the same collapse C23 made
with Gate C's waiver: *nobody checked* rendering as *checked and fine*. It warns
by default and tells the reader how to fix it; `GEOWATCH_STRICT_BAND_ORDER=1`
promotes it to an error. The default decays toward strict on its own as files
are re-exported.

*A wrong band **count** now raises too. It was previously a `print()` that
execution ran straight past — and a wrong count makes every index into the
array meaningless, `RGB_BAND_INDICES` included.*

**Demonstrated, not just asserted.** Against the pre-fix code, a GeoTIFF whose
bands are `["Red","Green","Blue",...]` was read with `Red` taken from index 2
(value 9000, actually blue) and `Blue` from index 0 (value 1000, actually red) —
**R and B swapped, `generate_rgb_preview_tiles()` completing without complaint.**
The same file now raises `BandOrderError` naming both orders.

### 45. C10 — enforce `source_checkpoint` ✅
Make the loader **refuse** thresholds whose source does not match the loaded
model. **Delete the dead stricter validator or promote it — do not leave two.**

**Built.** `tests/test_caat_provenance.py`, 19 tests, all passing.

> ### ⚠️ THIS TAKES THE PIPELINE OFFLINE UNTIL CAAT IS RECALIBRATED
>
> `run_pipeline()` now **raises** on the deployed thresholds file. That is the
> item's intent, not a regression — but it is a hard stop on real runs, so it is
> stated here rather than discovered.
>
> `models/production/caat_thresholds.json` carries **no `source_checkpoint` key
> at all**, and its own caveat records that it *"derived from 11 separate LOCO
> fold models (each missing one city), NOT from the production checkpoint."* It
> has never had provenance.
>
> **To restore runs:** `python recalibrate_caat.py` against the production
> checkpoint, review the old-vs-new comparison it prints, then swap its output
> into `models/production/caat_thresholds.json`. It now records the checkpoint's
> sha256, so its output loads. **Do not weaken the validator instead** — a test
> asserts the refusal, so relaxing it fails the suite.

**Promoted, and the duplicate deleted.** 97 lines of dead
`load_production_model` are gone from `resnet_classifier.py`, with the deletion
recorded in place. The provenance checks now live on the live path in
`ingestion/inference.py:_verify_caat_provenance()`. One loader, per the fork.

**Strengthened from a filename to a content hash.** The dead validator compared
`os.path.basename(source_checkpoint)` — which passes for any file sharing a
name, *including a retrained checkpoint written to the same path*, which is the
realistic failure. A test proves the point using two different checkpoints both
named `model.pth`. Hashing the 133 MB checkpoint costs **0.07s**, and the result
cross-checks byte-for-byte against `ARTIFACT_HASHES.txt`.

**`source_checkpoint=?` is gone.** That log line came from
`data.get('source_checkpoint', '?')` — a missing provenance record rendering as a
cosmetic gap. There is no `?` path now: either provenance verified, or the load
raised.

*A same-bytes-different-path checkpoint is noted, not refused: the hash settles
identity, so a basename difference only means the file moved. The dead validator
would have raised there, wrongly.*

*Omitting `checkpoint_path` skips the check and says so loudly. A silent skip is
exactly what C10 was — an unvalidated load indistinguishable from a validated
one.*

### 46. C13 — full-AOI basemap, or remove the field ✅
Either write a full-AOI RGB basemap (nothing correct currently exists for
`primary_tile` to point at), or remove the field. And correct the in-code comment
claiming the projection "works unchanged regardless of how many tiles" — false
for the base image.

**Note on severity:** downgraded under Decision 15 (confirmed no live
consumer), but the downgrade does not remove this item — severity and fix
priority are separate axes.

**Built — the field is removed, not backfilled.** Taking the fork already
decided: no basemap was manufactured.

- `pipeline.py` — `primary_tile` dropped from the schema v2.0 contract comment,
  from the assignment (`tiles[0]["path"]`), and from the `result.update()`
  block. No writer remains.
- `pipeline.py:337` — the false comment is corrected. It now says the
  full-raster projection holds for **segment geometry only**, states plainly
  that no full-AOI RGB raster exists on disk, and records why a single-tile
  base-image pointer must not be reintroduced.
- **Two readers existed** beyond the frontend, which the C13 note missed
  because it only verified `App.jsx`: `annotate.py:266` and
  `debug_segments.py:13`. Both now resolve `tiles/tile_0_0.png` from the run
  directory. `annotate.py` keeps a `primary_tile` *read* as a fallback for
  pre-item-46 runs on disk — reading a legacy field is not the same as
  depending on it.

**Verified:** no `"primary_tile":` writer anywhere in the tree; all three files
compile; full suite **369 passed**, identical to the pre-change baseline (the
2 failures / 3 errors in `test_coastal_context`, `test_one_tile_guard` and
`test_flood_flag_combination` predate this work — confirmed on `f69b40e`).

### 47. C34 — validate `run_id` at the read boundary ✅ *(new, added during consolidation)*
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

**Built.** `tests/test_api_run_id_validation.py`, 115 tests, all passing.
Verified against the unpatched endpoint first: **58 failed, 57 passed.**

**The untried variants are now tried, and they answer C34's open question.**
The ledger recorded that "Starlette normalizes some traversal in the URL path,
so it is likely weaker — but untested." Measured by recording the exact string
the unpatched handler passed to `Path()`:

- **POSIX traversal** (`../`, `../../../etc/passwd`, `%2e%2e%2f`, double-encoded,
  `/etc/passwd`) — **the handler never ran.** Starlette normalised or rejected
  the path before routing. The hypothesis was right for this class, and C34 was
  **not exploitable through it on this stack.**
- **Backslash variants** (`..\`, `..\..\windows\system32`, `C:\Windows\Temp`)
  — **reached the handler with the hostile string intact**, e.g.
  `Path('data/pipeline_runs/..\..\windows\system32/result.json')`. Inert on
  POSIX, where a backslash is an ordinary filename character; **real traversal
  on Windows.** Nothing in the code was platform-guarded.
- `x/../<real_run_id>` returned 200, but *not* because traversal succeeded — the
  URL normalised to `/api/runs/<real_run_id>` before routing and the handler
  received the clean id.

**Net: C34's practical severity on POSIX was lower than feared, and the
mitigation was incidental** — the router plus the host OS, neither a control
this codebase owns. The whitelist makes refusal explicit, platform-independent
and testable. A `resolve_within_data_root()` containment check backs it up, so a
future sink whose author forgets to validate is still contained — which is how
C34 came to exist after C16 was fixed.

**C35 closed in the same pass.** The whitelist is now one predicate,
`_matches_label_whitelist()`, called by both the HTTP boundary (400) and a
startup assertion over `WATCHED_AOIS` (RuntimeError), so the two cannot drift
about what a valid label is. The scheduler loop re-checks at call time, since
`WATCHED_AOIS` is a mutable module-level list and the import-time assertion
proves only that the *configured* value was good; a bad entry is skipped loudly
rather than raising, so one typo cannot stop the other cities refreshing.
`get_latest_run()` is checked too — traversal is not reachable through its
`startswith()` filter today, but "not reachable through the current code" is
precisely the reasoning that left C35 open.

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

**Built.** `tests/test_api_authentication.py`, 46 tests, all passing. The
secret is read from `.env` via `load_dotenv()`, called in `api.py` ahead of the
import-time key read — `ingestion/gee_client.py` already loads `.env` for
`GEE_PROJECT_ID`, but `api.py` imports `pipeline` lazily inside handlers, so
that call lands long after this module's import-time check. Each entry point
needs its own load; `dotenv` is idempotent. Verified
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
mechanism is **connected-component labeling on thresholded ~~unmixing-~~fraction
rasters** *(2026-09-25)* — not SAM, not the items below. Not built now; named here so the
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

### 52. C2 — validate the export; reconcile the size gap ✅
Assert dimensions, band count, and CRS against what was requested; fail loudly on
mismatch. Then reconcile `MAX_AOI_AREA_KM2 = 100.0` against `tiler.py`'s
documented "< 5 sq km" — **a 20× gap documented in one file and contradicted in
another.** Raise the tiler's real capability or lower the API cap; do not leave
both.

**Built.** `tiler.validate_export()` checks the downloaded file for **exact**
width, height, band count and CRS. The expected values are the
`_compute_export_grid` grid, `image.bandNames()` and `EXPORT_CRS = "EPSG:4326"`.
It raises `ExportValidationError` with every mismatch listed. On failure,
`export_image_local` deletes the bad file so no later step or re-run can pick
it up. Exact equality is safe here: before building, `_compute_export_grid`
was checked against every real `raw.tif` with a bbox `aoi`, and it reproduced
**137 of 137** exactly.

**The size gap: the tiler's docstring was the wrong side.** Measured live on
real Sentinel-2 composites centred on Dharavi. The pass bar was fixed before
running: export returns, `validate_export` passes, tiling completes.

| AOI | grid | chunks | time | result |
|---:|---|---:|---:|---|
| 99.5 km² | 1059×1001 | 2 | 53 s | PASS |
| 397.9 km² | 2117×2002 | 6 | 188 s | PASS |
| 895.2 km² | 3175×3002 | 12 | 354 s | PASS |

The chunked export removed the request-size limit that the "< 5 sq km" note
and the old 943 km² failure reflected. The note is replaced, and the measured
figure is now `tiler.MEASURED_MAX_EXPORT_AREA_KM2 = 895.2`. **It is a lower
bound, because no failure was reached.** It covers export and tiling only, not
SAM or inference memory downstream. `MAX_AOI_AREA_KM2` stays at 100 because
that downstream cost was not measured. A test asserts the API cap never
exceeds the measured tiler figure, so there is one number, not two.

`tests/test_export_validation.py`, 9 tests: **8 failed, 1 passed before** (the
guard that a correct export still succeeds) and **9 passed after**.

*Observed, not changed:* at 398 and 895 km², the grid computed from the
client bbox is one row short of the grid computed from GEE's
`aoi.bounds()`. The export follows GEE's bounds, and validation checks
against that same grid, so the two agree. Any consumer that predicts raster
size from the request bbox alone will be off by one row at those sizes.

### 53. C8 — INFORM validation + frontend guard ✅
Validate numeric and in-range at read time; an invalid cell yields
`status: "unavailable"`, not `"available"`. **Use the `PCT_MISSING`/`RELIABILITY`
columns that are already read and currently unused.** And guard the frontend
render — `App.jsx:568/572` currently renders `raw_score` with no type check.

**Built.** `vulnerability_sources.INFORM_VALID_RANGES` validates all four
values at read time: both scores, `Lack of Reliability (*)` and
`% of Missing Indicators`. Each must be a finite number, not bool and not
text, and inside **the file's own range**. Both scores and reliability are
0–10 (from the file's units row). Missing indicators is 0–1, because the
cells use the `0%` number format and so store a fraction. Any invalid cell
makes the lookup `unavailable`, and the reason names each bad column. The
two quality columns are now required columns too.

**Reliability is validated and reported, not used as a quality cut-off.**
INFORM publishes no global threshold for its Lack of Reliability index, so
none was invented here. Whether a high-but-valid score should suppress the
output is a decision, and it is not made.

**On the real file** (`INFORM_Risk_2026_v072.xlsx`), **190 of 191 rows
pass.** The failure is real data: **Tajikistan's reliability cell is the Excel
error string `'#REF!'`**, so TJK is now `unavailable`. Before this change it was
`available`, with `'#REF!'` passed through as `lack_of_reliability_score`.

Frontend: the ledger's `App.jsx:568/572` are now at 964/968. All four values go
through `geowatch-ui/src/inform.js`, a type guard that shows `—` for anything
that is not a finite number and drops the `/ 10` unit when the value is
missing. It deliberately has no 0–10 range check, because that would be a
second copy of the backend rule (the C31 pattern).

Tests: `tests/test_inform_validation.py`, 17 tests: **16 failed, 1 passed
before** (the valid-row guard) and **17 passed after**.
`tests/test_inform_ui.mjs`, 12 tests: **0 passed before** (the module did not
exist) and **12 passed after**.

~~*Live check:* the JRC results page now offers `INFORM_Risk_Mid_2026_v073.xlsx`,
so the repo's v072 is one release behind. The source was not switched under
this item.~~

**v073 adopted 2026-10-27.** Downloaded live from the JRC results page
(`/inform-index/Portals/0/InfoRM/2026/INFORM_Risk_Mid_2026_v073.xlsx`, HTTP
200, 2,546,463 bytes, sha256 `7e0cc5e5…9e66`). Its structure is identical to
v072: same sheet name, header row 2, units row 3, columns and cell formats.
`INFORM_RISK_FILE_PATH` and `INFORM_RISK_EDITION` (`"Mid 2026 (v073)"`) now
point at it. It is a real update: 186 of 191 rows changed (IND vulnerability
4.4 → 4.3, coping 4.2 → 3.9). **Item 53's validation on v073: 190 of 191 rows
pass.** The one failure is again Tajikistan, whose `Lack of Reliability (*)` is
still the Excel error `'#REF!'` in the new release, so it is an upstream
defect rather than a stale file. The file itself is untracked (`data/` is
gitignored) and must be placed at `data/external/` in each checkout that runs
the pipeline. Without it, the INFORM layer now reports `failed` /
`FileNotFoundError` (item 54 amendment) rather than stopping the run.

---

# PART 11 — Error convention 🔓

*Two items.*

### 54. C18 — in-band errors detected in-band ✅
Pick one convention and use it consistently across the boundary. **Recommended:**
raise on programmer error and integration failure; return status dicts only for
genuine data absence. Then make the scheduler check the thing that is actually
signalled.

### 55. Distinguish exception classes ✅
Catch specific types. Where a broad catch is genuinely right, **record the
exception class in the output** so "broken integration" and "no data here" are
distinguishable downstream.

*This is the shared root cause behind several individual findings across
`hydrology.py`, `coastal.py`, `rainfall.py`, and `vulnerability_sources.py`.*

**Built, as one change, because the root cause is shared.** The convention is
written once, in `ingestion/errors.py`:

- **Raise** on integration and programmer errors. This covers GEE errors,
  network failures, typos, a matched country boundary with no `country_co`
  (schema change), the INFORM file not installed, a missing INFORM sheet, and
  a changed INFORM header row.
- **`status: "unavailable"` means genuine no-data only.** That covers a
  reduction that returned no value, no CHIRPS images, a centroid over ocean,
  an ISO2 code pycountry cannot resolve, an ISO3 not in INFORM, and an INFORM
  cell that fails item 53's validation. Each such dict is produced by
  catching `NoDataError` and nothing else, and it carries
  `exception_class: "NoDataError"`. The old field shapes are kept, plus `error`.
- All seven `except Exception` blocks in the four modules are gone.
  `coastal.py` has no genuine no-data case ("far inland" is a real
  `available` result), so it has no catch at all.
- **Broad catches remain only where they are right**, and each records the
  class. The scheduler loop and the `run_all_cities` batch loop do this so
  one city cannot stop the rest. The `/api/analyze` and
  `/api/analyze_inundation` 500s now read `EEException: …` rather than a bare
  message.
- **C18: the scheduler checks what is signalled.** `refresh_all_watched_aois`
  checks both the raise and the returned `status`. It prints "refreshed OK"
  only for `complete`, and returns one outcome per AOI
  (`complete` / `failed` / `exception` + class).

~~**Behaviour change, stated plainly:** `run_pipeline` and
`run_inundation_analysis` call these sources without a guard. A GEE or network
failure in any context layer therefore **now aborts the run**, where before it
silently degraded that layer to "unavailable". That is the convention as
specified. Whether the pipeline should degrade per layer instead is a separate
question, not decided here.~~ *Superseded by the amendment below.
`run_inundation_analysis` never called these sources. The calls seen were in
`run_event_hazard_analysis`, which item 57 deleted.*

**Amendment (decided 2026-10-27): a failed layer is contained, not fatal.** The
sources still raise. `run_pipeline` now calls each of its seven context layers
through `_context_layer()`: MERIT HAND, FABDEM, CHIRPS, coastline, slope, the
country lookup and INFORM. A raise there becomes that layer's block with
**`status: "failed"`** plus `exception_class` and `layer`, built by
`errors.layer_failed()`, and the run continues and completes. `"failed"` is
deliberately distinct from `"unavailable"` (genuine no-data, `NoDataError`),
so result.json says which happened. Every consumer gates on
`status == "available"`, so a failed layer is excluded exactly as an
unavailable one is. A failed country lookup makes the vulnerability block
`failed` too (`failed_upstream: "country_lookup"`). Otherwise INFORM would
report the missing ISO3 as a data gap.

`tests/test_pipeline_layer_boundary.py`, 11 tests, driving the real
`run_pipeline` with its external dependencies stubbed: **9 failed, 2 passed
before** (the harness baseline, and the guard that a data-absent layer stays
`unavailable`) and **11 passed after**.

Tests: `tests/test_error_convention.py`, 46 tests: **46 failed before, 46 passed
after.** Three existing tests encoded the old convention and were rewritten to
the new one. They are `test_hydrology_hand.py`'s two
`test_gee_failure_returns_unavailable_not_fabricated` tests (now
`..._raises_...`) and item 53's `test_missing_quality_column_...` (now
expects `KeyError`).

Verified live against GEE for Dharavi: MERIT HAND, FABDEM, slope, coastline,
CHIRPS and the country lookup all return `available`. An ocean AOI returns
`unavailable` / `NoDataError`. INFORM returns IND `available`, and TJK (`#REF!`)
and ATA (not listed) `unavailable` / `NoDataError`.

---

# PART 12 — Hygiene 🔓

*Four items. Individually cheap, collectively substantial.*

### 56. C17 — sort by timestamp ✅
Parse the timestamp; do not sort strings. **And exclude `*_test_*` runs from the
demo endpoint entirely.**

**Built.** `api.get_latest_run` orders candidates by `run_dir_timestamp()`, the
parsed trailing `_%Y%m%d_%H%M%S` that `pipeline.py` writes. It drops every
`*_test_*` directory before ordering, and drops directories with no parseable
timestamp instead of guessing a position for them.
`tests/test_latest_run_ordering.py`, 12 tests: **12 failed before, 12 passed
after**. It rebuilds the ledger's exact three names. Against the real
`data/pipeline_runs/` the demo now selects
`dharavi_phase11_postfix_20260807_125913`, which is the ledger's
newest-by-mtime run.

~~*Not changed, outside the item:* `startswith(aoi_label)` still admits
`dharavi_*_inundation_*` and `*_eventhazard_*` runs, which have a different
result shape. If one is ever the newest, `/api/demo` would serve it.
`/api/runs` still lists in reverse string order.~~

**Finished 2026-10-27.** `*_inundation_*` and `*_eventhazard_*` runs are now
excluded from "latest" selection alongside `*_test_*` (`_EXCLUDED_FROM_LATEST`).
`/api/runs` lists newest first by parsed timestamp, with undated directories
listed after every dated one in name order rather than dropped. 4 more tests
in the same file: **4 failed before, 4 passed after** (16/16 in the file). On
the real `data/pipeline_runs/` the demo still selects
`dharavi_phase11_postfix_20260807_125913`, and `/api/runs` lists all 137
runs.

### 57. Delete dead code ✅ *(partial: two of six targets kept, see below)*
`resnet_classifier.py`, `resnet_model.py`, `classifier.py`,
`run_event_hazard_analysis`, the duplicate `decode_mask_rle` in
`verify_masks.py`, the duplicated `GeoWatchResNetSeg`.

**Removes roughly a dozen Moderates at once**, and removes the trap where the
correct provenance check lives in a file nothing imports (C10's root cause).

**Built.** Every target was grepped for importers repo-wide first, and on
every other branch (none imports a deleted name).

| target | result |
|---|---|
| `ingestion/resnet_classifier.py` | **deleted**: no importer |
| `ingestion/classifier.py` | **deleted**, together with root `test_classifier.py`, its only importer. That is a hard-coded RemoteCLIP smoke script outside `tests/` and never collected, which the original audit had already named as the sole importer |
| `run_event_hazard_analysis` | **deleted** from `pipeline.py`, with the five imports only it used |
| `verify_masks.py` fallback `decode_mask_rle` | **deleted**. It decoded with a different layout (`(w, h).T`) behind a print-only warning. The import of `segmentation.decode_mask_rle` is now unconditional |
| `ingestion/resnet_model.py` | **KEPT**: live importers are `tests/test_encoder_band_contract.py` and `experiments/band_reflectance/{run_probe,fidelity_run,run_comparison}.py` |
| duplicated `GeoWatchResNetSeg` | **KEPT**: the two are not duplicates. `resnet_model.py`'s loads pretrained SSL4EO weights and runs `assert_encoder_band_contract()`. `inference.py`'s uses `weights=None` and runs no contract check. Merging them changes behaviour on one side, so it is a design decision, not a deletion |

`tests/test_dead_code_removed.py`, 12 tests: **6 failed, 6 passed before** (the
six that pass are the "live modules still import" safety net) and **12 passed
after**. `test_caat_provenance.py::test_the_dead_duplicate_validator_is_deleted`
read `resnet_classifier.py` directly. It was restated to keep its property
(exactly one `load_production_model`, in `inference.py`) without the file.

*Left dead, outside the list:* with `run_event_hazard_analysis` gone,
`ingestion/event_hazard.py` and `susceptibility/event_hazard.py` have no entry
point. The Part 4 validation mandate still names `event_hazard.py`.

### 58. Frontend as pure renderer ✅
Renders `result.json` and computes nothing. Remove: hardcoded category lists,
recomputed aggregates, invented thresholds, truncated caveat lists, the hardcoded
Q1-2024 date window, and **the `?? 291 / ?? 257` fallback — verified as exactly
Dharavi's `tile_dimensions`. If the field were ever missing, every AOI worldwide
would be projected through Dharavi's grid, silently.**

**Built.** The helpers live in `geowatch-ui/src/render.js` (plain JS, tested
under node). Removed from `App.jsx`:

| removed | replaced by |
|---|---|
| `?? 291 / ?? 257` | `segmentGrid(result)`. With no valid `tile_dimensions`, segments are **not drawn** and the map says why |
| `CAT_LABELS` category table | `humanize(key)`. Every old entry was the key in sentence case, so no label changes, and a new category is no longer blank in the legend |
| `Object.entries(SUSC_INFO)` deciding which hazards render | `hazardKeys(result.susceptibility)`. `SUSC_INFO` is now display text only, so a hazard it does not list still renders |
| `UNPAVED_HIGHWAY_TYPES`, a copy of `osm_dem.py`'s set | `roads.geojson` now carries the backend's own `unpaved` flag. `osm_dem.UNPAVED_HIGHWAY_TYPES` is one module-level frozenset used by both paths |
| client-side informal-roofing segment count | removed. No run has ever emitted it, and recomputing it is the defect |
| `standing_water_segment_count ?? 0`, legend `'0.0%'` for missing, `aoi_mean_class \|\| 'unknown'`, architecture `\|\| 'GeoWatchResNetSeg'` | missing renders as `—` |
| `unknown_pct > 15` colour threshold | removed |
| "one of its 11 training cities", "data … from 2020" | read from `loco_n_folds` and `population_year` |
| `CaveatList` `items.slice(0, 5)` | every caveat renders |
| hardcoded `2024-01-01 … 2024-03-31` analyze window | omitted. The backend uses its own window, and the report already shows `imagery.requested_period` |

*Legacy runs:* roads from runs before this item carry no `unpaved` flag, so they
all render in the paved style rather than being classified client-side.

Tests: `tests/test_pure_renderer_ui.mjs`, 15 tests: **0 passed before, 15 passed
after**. `tests/test_renderer_contract.py`, 2 tests: **2 failed before, 2 passed
after**. The `vite build` succeeds. `oxlint` reports the same two findings as on
`master` (`App.jsx` unused expression in `DragToggle`, conditional `useState` in
`SecExposure`); neither was introduced here.

### 59. `batch_run_log.json` — append, don't truncate ✅
Each invocation currently truncates; the 11-city history was clobbered by a later
single-city run.

**Built.** `run_all_cities.run_batch` reads the existing log before any city
runs. It writes `history + this batch` after each city, through a temp file and
`os.replace`. Each entry carries a `batch_id`, so invocations can be told apart,
and an `exception` entry also records `exception_class`. If an existing log
cannot be parsed as a JSON list, the run **raises before running anything**.
Treating that file as empty would overwrite it, which is the defect itself.
`tests/test_batch_run_log_append.py`, 6 tests: **5 failed, 1 passed before**
(the guard that the return value stays per-batch) and **6 passed after**.

*The lost history is not recovered.* The on-disk log still holds the single
`nusantara` entry that clobbered it. The earlier entries are not in git
(`data/pipeline_runs/` is untracked), so they are gone.

---

# PART 13 — Documentation and publication 🔓

*Nine items.*

### 60. Model card
Mitchell et al. template. Training data, class definitions, LOCO protocol, known
failure modes, intended use, **out-of-scope uses**.

**Must state Decision 16 explicitly:** this is a research-audience
contribution, not a validated planning tool. Outputs should be framed as
"here is why this should be trusted" rather than "a planner validated this."

### 61. Datasheet ✅
Gebru et al. template, covering the training data.

**Done:** `docs/retired_datasheet.md`. This is a historical record of the
**retired** 7-class checkpoint's training data (`08_STATE.md` §RETIRED). It
does not describe the class definitions (item 21). Composition was re-derived
from the 5-builder rebuild, not copied.

### 62. Provenance Reconstruction — a named section ✅
Document how the production checkpoint's training notebook was identified, by
fingerprinting four independent config values against checkpoint metadata.

**This does not recover history — it recovers auditability**, which is the actual
function git history serves. Frame it as a named subsection, not a footnote.
Reviewers respect a documented forensic process far more than silence.

**Done:** `docs/provenance_reconstruction.md`, kept short because it concerns
only the **retired** checkpoint. Re-run 2026-10-28. The four config values
narrow 28 archived notebooks to **12**, not one. The single file is reached
only via the `.npy`, builder-count and mtime steps. The checkpoint's stored
LOCO fields match **no** archived artifact (notebook 0.2994,
`patch_checkpoint_provenance.py` 0.3037, checkpoint 0.313).

### 63. Written labeling guide
The exact decision rules the annotator followed, including edge cases. **This is
the standard substitute for inter-rater statistics in small studies** and is
broadly accepted when explicit.

### 64. Gate C protocol — written, unrun ✅
Write the study design — recruitment, task, metrics — whether or not it gets run.
Disclose non-execution explicitly as an access constraint.

**Per Decision 17: this is not Gate C's closure mechanism** — Gate C itself
closes via structured advisor/faculty review against D.7's five reporting
requirements (item 65 below documents that review). This item is the
real-planner protocol, filed as documented future work, disclosed as blocked
by access rather than by design choice.

**Done (written; not run):** `docs/gate_c_protocol.md`. It covers
recruitment (three user classes), a four-stage task in Decision 17's shape,
and metrics M1–M7 against an answer key frozen before recruitment.
Non-execution is stated at the top as an access constraint.
`GATE_C_STATUS` is unchanged.

### 65. Gate C — advisor review write-up *(new, added during consolidation)*
Document the structured advisor/faculty review against D.7's five
requirements (confusion matrix before/after, per-class accuracy before/after,
separability analysis, WorldCover/Dynamic World comparison, causal mechanism
tied to resolution) that formally closes Gate C per Decision 17. This is the
record of the review that actually happened, distinct from item 64's unrun
protocol for the review that could not happen.

### 66. Susceptibility dependency DAG ✅
Plus a correlation matrix across the AOIs. **Directly defuses the "four of five
layers agree, therefore convergent evidence" misreading** — they are driven by
two shared inputs, normalized by three provisional ceilings, and reported with
byte-identical class breaks. Probably a figure in the paper.

**Done:** `docs/susceptibility_dag.md`, re-derived from code and the stored
runs. MERIT Hydro and CHIRPS are each read by three of the five layers, and
the class breaks hash identically across all six configs. **Ceilings
re-counted:** ten fixed definitions (the 2,500 mm rainfall ceiling is defined
twice) plus two AOI-relative normalisations, not "three". The correlation
matrix covers the only 11 distinct AOIs with a susceptibility block (n = 7–9,
geographically clustered), so it is descriptive only.

### 67. Population from two sources, as a range ✅
WorldPop and GHS-POP disagree ~7.6% at 2020 over the same AOI. **Report the
range, not a point estimate.** More honest, costs nothing.

Record the constraint: no enumerated Indian microdata before 2027–28.

**Done:** `docs/population_range.md`, re-queried in GEE 2026-10-28. The
"~7.6%" is **one AOI** (Dharavi), computed as (WP − GHS)/WP; it is 8.19% with
GHS as the denominator. On four other AOIs the sign flips and the spread runs
9.5–96.9%, so the range must be computed per AOI. **Stale record:**
`03_EVIDENCE.md` §C.4 says WorldPop R2025A is absent from GEE. It is now
present (`WorldPop/GP/100m/R2025A/v1/pop`) and gives sums 2.8–6.3× off both
models. It was not investigated and is not in the range. The census
constraint was re-checked; no official results date exists.

### 68. Email Planet re: publishing rights
Ask explicitly whether annotated masks and model weights derived from
PlanetScope may be published openly — **before annotating anything on it.**

**This is a real strategic constraint, not a formality:** an open annotated
benchmark for informal-settlement land cover would be a stronger contribution
than another model, and Planet's terms partly foreclose it. Sentinel-2 does not
have this problem.

### 69. Literature table ✅
Columns for resolution, protocol (within-city split vs cross-city LOCO vs
cross-region), and class count — showing **no directly matched benchmark
exists.**

That gap is itself a finding about the state of the field, and more valuable than
a possibly-misleading number-to-number comparison.

**Done:** `docs/literature_table.md`. Seven nearest-neighbour works, each
cell checked against its source on 2026-10-28, with unconfirmed cells marked
rather than filled. None combines 10 m, held-out-city evaluation and dense
multi-class output. No GeoWatch number appears (the retired LOCO figure is
excluded per C43). This is not a systematic review, and the doc says so.

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
