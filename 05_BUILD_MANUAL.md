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
    solar                  — NEW: own fraction. GROUND-MOUNTED arrays only
                             (amended 2026-09-25); rooftop panels are built
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
    solar                  — spectral-signature detector; per AOI "excluded"
                             when a global solar-installation dataset shows
                             none (amended 2026-09-25)
    mixed_water_vegetation — spectral + dataset sub-typing (GMW, GLWD).
                             Amended 2026-09-25: MANGROVE producer = Global
                             Mangrove Watch extent directly; other sub-types
                             not_computed

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
geographic-plausibility flags; ~~docks → `built`~~ *(struck 2026-09-25: piers and quays are unroofed sealed decks, so by the labelling guide's top-surface rule they are `paved`; roofed dock buildings already arrive via footprints. `man_made=pier` / `man_made=quay` is kept as a context flag only)*.

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

**Low-coverage policy (decided 2026-09-24; see the Part 4 mandate note):**
outputs that stay meaningful at low coverage (footprint density, coarse
`built`) are computed with a confidence flag. Network-topology metrics
(orthogonality, dead-end ratio, fine connectivity) are suppressed below a
threshold. **This item sets those thresholds.**

**Acceptance:** score emitted for every AOI, **never optional, never null**; a
low-coverage AOI is visibly flagged end-to-end through to the UI; Lagos (0.19)
and Khayelitsha (8.35) produce visibly different scores.

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
  ~~(Marrakech optional)~~ — *city list replaced 2026-09-24, see "Site list"
  below; Marrakech removed 2026-09-25*. It is **weighted toward genuine bare ground**, the boundary
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
> optional city (semi-arid, North Africa). *(Marrakech removed 2026-09-25 —
> see its row below.)* **Delhi may be re-added later**
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
| **Lima** | OpenAerialMap drone scenes | 3–8 cm | 2017–2025 | CC BY 4.0 | varies by scene (UNI 2025-03-17: 11 / 12 / 14; Caritas 2025-01-05: 1 / 2 / 9) | **Prioritise the desert-hillside scenes, Candelaria and Santuario de las Vizcachas** (genuine bare ground). ~~**Exclude Cajamarquilla** (no licence)~~ *Corrected 2026-09-25:* Cajamarquilla's OpenAerialMap record (`59e62b8f3d6412ef72209f61`) carries **CC-BY 4.0**. The exclusion's only stated reason does not hold; whether to use the scene is **not re-decided here** |
| **Karachi** *(replaces Delhi)* | Maxar Pakistan floods open data | 0.53 m | **2022-03-29 only** | CC BY-NC 4.0 | 66 / 127 / 169 | **Pre-flood scene only.** Later scenes contain flood water that would pass for bare ground or water |
| **Monrovia** *(replaces Jakarta)* | Uhuru Labs / HOT drone surveys | 5 cm | 2020-02-23 | CC BY 4.0 | 22 / 43 / 53 | — |
| ~~**Marrakech** *(optional, replaces Cairo)*~~ | ~~Maxar Morocco earthquake open data~~ | ~~0.31–0.55 m~~ | ~~pre-quake 2023 scenes (e.g. 2023-03-28, 2023-08-06)~~ | ~~CC BY-NC 4.0~~ | ~~20 / 39 / 49 (08-06)~~ | **REMOVED 2026-09-25:** Open Buildings v3 has zero coverage in Morocco, and using Microsoft footprints at one site would mix `built` sources across the training set (measured: 0 footprints at any confidence in Marrakech, Casablanca, Rabat) |

The Sentinel-2 counts are whole scenes under 20% cloud, not per-pixel. A
masked composite can still work where the count is low.

**Caveats — recorded with the list:**

1. **Licence assumption.** Most of these sources are non-commercial (CC BY-NC
   or equivalent): Kibera, Rocinha, Cape Town, Karachi~~, Marrakech~~. That is fine
   for academic use. **If GeoWatch or its labels are ever used commercially,
   these labels must be re-sourced.**
2. **Regional overlap.** The firewall is city-level and is not broken. But
   Monrovia shares a region with Makoko (West Africa), and Lima shares one with
   Rocinha (South America). **Validation reporting must note this.**
   **Kibera (East Africa) is the coldest transfer test.**
3. **Coverage areas overstate usable ground.** Drone mosaics have internal
   no-data gaps; the Old Fadama rectangle was ~36% nodata. **Real pixel
   coverage must be checked per site before labelling time is committed.**

**Site AOIs — approved 2026-09-25.** Each site is a **3 km × 3 km box**,
exact in its UTM zone, centred on the named settlement
(`experiments/item21_sites/results/aoi_proposals.json`; coordinates in
`configs/labelling.yaml` `aois`).

| Site | Centre (lon, lat) | Centred on | Status |
|---|---|---|---|
| Makoko | 3.3923, 6.4959 | OSM place node "Makoko" | approved |
| Kibera | 36.7890, −1.3113 | OSM place node "Kibera" | approved |
| Rocinha | −43.2484, −22.9897 | OSM admin boundary (relation 5520358) centroid | approved |
| Lima | −76.9286, −12.1336 | **Option B:** midpoint of the two prioritised scenes (Candelaria, Santuario de las Vizcachas) | approved |
| Monrovia | −10.8064, 6.3259 | West Point (mean of 6 OSM "West Point" features; no boundary) | approved |
| Karachi | — | Orangi; a new centre toward its western / northern edge is proposed so the box holds undeveloped fringe | **pending** |
| Cape Town | — | Khayelitsha proposed; the city imagery's extent is not machine-readable | **pending** |

**Box vs frame:**
- **Measurement B runs on the full 3 × 3 km box.**
- **The labelling frame is box ∩ the chosen scene's footprint.** Tiles are
  drawn only inside it: a tile is eligible only if it lies **entirely** in
  the frame (`labelling.tiles.build_frame`). Which scene defines each frame
  is the imagery-source choice, **not yet made** (`frame_scene` UNSET).

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

**Scored cells — pre-registered 2026-09-25, before any labelling.**
Validation scores **only 10 m cells with a computed remainder** (R2 as
amended: pixels in non-Dryland GLWD cells, or blocked by any other
not-computed input, have no `impervious_total` / `bare` / `paved` to score).
The **per-site scored share** — scored cells ÷ labelled cells — is reported
**alongside every metric**, so a pass on a small scored share is visible as
such. Neither the rule nor the share may be changed after labels or results
exist.

**What each validation site validates — pre-registered 2026-09-25, before
any labelling.**

| Site | `built` | `impervious_total` |
|---|---|---|
| Makoko | **validated** | **not validated** |
| Kibera | validated | validated |
| Rocinha | validated | validated |

**Why Makoko validates `built` only:** 99.3% of Makoko's approved 3 × 3 km box
lies in non-Dryland GLWD cells, where (R2 as amended) the non-mangrove
`mixed_water_vegetation` component is `not_computed` and the remainder is
blocked — so `impervious_total` would be scored on < 1% of the box.
`built` comes from footprints and does not depend on the remainder, so
Makoko still tests it. **`impervious_total` is validated on Kibera and
Rocinha only.** This narrows the validation-site list above for one
quantity; the firewall and the sealed batches are unchanged.

**`built` validation.**

- **Hand-digitised buildings** at Makoko, Kibera and Rocinha are compared
  against **Open Buildings** and a **second footprint source** (Microsoft or
  OSM buildings, per Decision 11's new datasets).
- **Ongoing, everywhere:** the **per-AOI disagreement between the two
  footprint sources** is reported as `built` confidence. That signal is
  **calibrated by the hand-digitised check**, which ties a given disagreement
  level to a measured error.
- **`built` pass/fail — decided 2026-09-25, fixed before any run** (Phase A
  rulings, third round, R5):

  | Metric | Bar | Role |
  |---|---|---|
  | Per 10 m cell **MAE** | ≤ 10 pp | **Hard gate** |
  | Per 10 m cell **R²** | ≥ 0.5 | **Hard gate** |
  | Per-site **absolute coverage bias** | ≤ 5 pp | **Hard gate** |
  | Polygon **IoU** | — | **Diagnostic only**, never disqualifying |

  **Why stricter than `impervious_total` (MAE ≤ 15 pp, R² ≥ 0.3):**
  `paved = impervious_total − built` inherits `built`'s error on top of
  `impervious_total`'s, so `built` must be measured more tightly than the
  quantity it is subtracted from or `paved` is unusable by construction.

  **Pre-registered failure branch:** if Open Buildings fails `built`,
  alternatives (Microsoft; the Open Buildings ∪ Microsoft union) may be
  evaluated **on TRAINING sites only — never on the sealed validation
  sites**. Choosing a footprint source by looking at validation results
  would be the firewall breach item 21 exists to prevent.

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
(~~v1.0~~ ~~v1.1~~ ~~v1.2~~ v1.3 since 2026-09-25: `solar` = ground-mounted only; sun geometry measured from ≥ 3 buildings where no acquisition time is published; Marrakech removed from its site list).** It is the protocol for every training and validation label above:
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
sand, rock, dry lakebeds, landfills, quarries etc. → `bare`; ~~docks → `built`~~ *(struck 2026-09-25; see Decision 11)*),
the extended occlusion list (Decision 14), the volcano and terrain context
layers, the new datasets (including a second footprint source — Microsoft or
OSM buildings — for `built` confidence), and the volcanic hazard module parked
as a future sixth hazard module.

#### Phase A — build rulings, decided 2026-09-25

*Phase A is everything in this item that needs no training labels. It trains
nothing and builds nothing past item 21 (validation-first mandate). These
rulings were made when the Phase A build plan surfaced gaps in the specs above;
they are recorded here so the code has a written source.*

- **Grid.** Fractions and label fractions share the **native Sentinel-2 UTM
  grid**. `export_image_local` gains optional `crs` / `crs_transform`; its
  default EPSG:4326 path stays byte-identical.
- **Full shadow.** The full/partial boundary is still open, so the full-shadow
  producer exists as an interface with its criterion **UNSET**, and the field
  is emitted as `status: "not_computed"` — never as 0. **SCL = 3 is NOT full
  shadow**: it is cloud shadow only.
- **Occlusion attribution in a composite.** Masking is per scene, one cause at
  a time. A pixel is occluded when it has zero valid observations; it is
  attributed to one cause only if every removal had that cause, otherwise to a
  separate `occluded_multiple_causes` field. Per-cause shares of removed
  *observations* are reported alongside. *(Recorded 2026-09-25, second
  round:)* each observation gets exactly one category, by the precedence
  **nodata > cloud > fire > snow**; it only matters for an observation that is
  two things at once (e.g. cloud over a fire).
- **Occlusion producers.** Transient snow = SCL 11 excluding `snow_ice`
  pixels. Fire = FIRMS active fire matched to scene dates. **Smoke and ships:
  `status: "no_producer"`.**
- **Negative `paved`.** Clamped to 0, **flagged**, with the unclamped value and
  the resulting sum excess emitted beside it.
- **Remainder split.** The (placeholder) impervious regressor predicts
  `impervious_total` as a **share of the hard-surface remainder**. All
  over-subscription (non-hard producers summing above 1, `built` above the
  remainder) is **flagged, never rescaled**.
- **Detector fractions and precedence — a Phase A simplification, to be
  revisited after each detector's own validation case.** A detected pixel has
  fraction 1.0. Detectors (`snow_ice`, `solar`, `mixed_water_vegetation`)
  override the vegetation and water regressors on the same pixel; a
  `mixed_water_vegetation` pixel is not also counted as vegetation or water.
  *(Added 2026-09-25, second round:)* where a `solar` detection intersects an
  Open Buildings footprint, **`built` wins** — rooftop panels are `built`.
- **Thresholds.** Every threshold is either cited or measured, lives in
  config, and is marked UNVALIDATED; an uncited one is **UNSET** and its
  detector emits `status: "not_computed"`. In any run other than the Dharavi
  smoke test, a remainder with a `not_computed` input is itself
  `not_computed`. *(Amended 2026-09-25, second round:)* an **`excluded`**
  input — known to be zero in the AOI from a dataset — does **not** make the
  remainder `not_computed`. Placeholder substitution for a `not_computed` detector is
  allowed **only** in the smoke test, marked `provenance: "placeholder"`.
- **`built`.** Open Buildings v3, `confidence ≥ 0.7`, only. The second source
  is **Microsoft Global ML Building Footprints (sat-io)**, used only for the
  disagreement signal: both coverage totals, per-pixel fraction MAE, and ~~10 m
  IoU~~ `weighted_jaccard` *(renamed 2026-09-25)* are emitted, and **none is named the confidence score** until the
  hand-digitised check calibrates one.
- **Docks.** The "docks → `built`" folding is struck (Decision 11, 2026-09-25).
  `man_made=pier` / `quay` is a context flag only.
- **Fabric strata** for tile sampling come from a **hand-drawn GeoJSON per
  site**; nothing derives them (morphology is item 23, past the mandate).

#### Phase A — build rulings, second round, decided 2026-09-25

1. **Detector status `excluded`.** A detector *known to be zero in the AOI
   from a dataset* has status `excluded` and provenance
   `excluded:<dataset>`. An excluded input does **not** make the remainder
   `not_computed`. **`snow_ice`** is excluded per AOI from a global
   permanent-snow / glacier dataset. The low-temporal-variance threshold
   stays UNSET.
2. **`mixed_water_vegetation` mangrove producer = Global Mangrove Watch
   extent, directly** (Decision 11 producer table amended). The other
   sub-types (wetland, mudflat / tidal, water hyacinth) stay `not_computed`.
3. **`solar` = ground-mounted arrays only.** Rooftop panels are `built`.
   Where a `solar` detection intersects an Open Buildings footprint, `built`
   wins. Per AOI, `solar` is `excluded` if a global solar-installation
   dataset shows none.
4. **`LABELLING_GUIDE.md` → v1.1:** the `solar` label is ground-mounted arrays
   only; rooftop panels are `built` plus a solar flag.
5. **`label_limited`.** For `impervious_total`: agreement of the derived
   (`built` ∪ `paved`) label fractions between labellings, against the
   model's `impervious_total` pass bar. For `built`: against its validation
   bar. Every other class: `None`.
6. **Naming and records.** The Open Buildings / Microsoft "10 m IoU" is
   renamed **`weighted_jaccard`** everywhere. The occlusion precedence is
   recorded above. The tile-sampler seed is stored in run metadata.
7. **Part 6 context thresholds** (terrain, volcano radius, synthetic turf,
   bare plausibility, salt flat) **stay UNSET, deferred, off the critical
   path.** GLWD class 32 is **not** a salt-flat producer.

#### Phase A — build rulings, third round, decided 2026-09-25

- **R2 — `mixed_water_vegetation` from datasets.** ~~Detected pixel =
  fraction 1.0, overriding vegetation / water~~ *(amended for dataset
  producers only)*: **Global Mangrove Watch coverage is kept as a continuous
  fraction**, with **no 1.0 override** of the vegetation / water regressors;
  any over-subscription is flagged, never rescaled. The spectral-detector
  override (fraction 1.0) still applies to `snow_ice` and `solar`.
  Per AOI, the class has two components:
  - **mangrove** — Global Mangrove Watch extent, always computed;
  - **non-mangrove** (wetland, mudflat / tidal, water hyacinth) —
    ~~**`excluded`** if the Global Lakes and Wetlands Database shows **no
    wetland class of any kind** in the AOI, otherwise **`not_computed`**,
    which keeps the remainder blocked.~~ **Amended 2026-09-25 — per GLWD
    cell, not per AOI:** pixels inside a Dryland GLWD cell are `excluded`;
    pixels inside any non-Dryland GLWD cell (classes 1–33, config list
    unchanged) are `not_computed`, and **the remainder is blocked for those
    pixels only**. Mangrove still comes from GMW everywhere. Every run emits
    a per-AOI `blocked_pixel_share`.

    **Why per cell:** GLWD's over-calling only *enlarges* the blocked zone,
    so the rule stays conservative; blocking whole AOIs made
    `impervious_total` unscoreable at the validation sites.

  **Why GLWD exclusion is conservative:** GLWD over-calls wetland (at
  ~464 m it labels 77% of Dharavi "Other coastal wetland"), so an AOI where
  it shows *nothing* is very unlikely to hold unmapped wetland. *Recorded
  interpretation:* "any wetland class" is read as **any non-Dryland GLWD
  class (1–33)**, because water hyacinth — part of this class — grows on
  the lakes and rivers GLWD maps as classes 1–7.
- **R5 — `built` pass/fail bar:** see "`built` validation" above.

**Phase A progress** *(one line per part as it lands)*:

- **Part 1 — input assembly** *(2026-09-25)*: `surface_fractions/inputs.py`.
  One float32 stack on the native Sentinel-2 grid (6-band composite,
  `s2_observed`, item 18 variance, Open Buildings ≥ 0.7 and Microsoft
  coverage, Copernicus DEM elevation + slope) plus OSM layers via
  `ingestion/overpass.py`. `export_image_local` gained `crs` /
  `crs_transform`. OSM has no usable tag for salt flats or dry lakebeds:
  both layers are `no_producer`.
- **Part 2 — occlusion** *(2026-09-25)*: `surface_fractions/occlusion.py`.
  Per-scene categories (precedence nodata > cloud > fire > snow), exported
  as per-pixel counts; attribution in local numpy. Fields: cloud, nodata,
  transient_snow, fire (FIRMS, same-date, no confidence cut-off),
  multiple_causes; shadow_full `not_computed`; smoke, ships `no_producer`;
  the denominator carries an explicit upper-bound caveat naming them. SCL 11
  where `snow_ice` is not computed is reported as `snow_unresolved`, never
  guessed. Dharavi 2024-Q1: 31 scenes, observed_fraction 1.0.
- **Part 4 — `built`** *(2026-09-25)*: `surface_fractions/built.py`.
  `built` = Open Buildings v3 (≥ 0.7) coverage only. Microsoft disagreement
  emitted as coverage totals, per-pixel fraction MAE and ~~10 m IoU~~
  `weighted_jaccard` (area-weighted, threshold-free), explicitly not a
  confidence score. Dharavi: Open Buildings 22.0% vs Microsoft 16.1%, MAE
  0.200, ~~IoU~~ weighted_jaccard 0.313.
- **Part 3 — detectors** *(2026-09-25)*: `surface_fractions/detectors.py`.
  All three are **`not_computed`** under the shipped config: `snow_ice`
  has a cited spectral half (Hall et al. 1995: NDSI ≥ 0.4, NIR > 0.11,
  UNVALIDATED) but its low-temporal-variance band and cut-off are UNSET;
  `solar` and `mixed_water_vegetation` have no verified spectral criterion
  (UNSET). Predicates are implemented where a method is cited (snow) and
  refuse to run where none is. GMW / GLWD sub-typing layers are exported
  and reported regardless. **Observation:** at ~464 m, GLWD calls 77% of
  Dharavi "Other coastal wetland" — it can sub-type a spectral detection,
  never stand in for one.
- **Part 5 — bookkeeping** *(2026-09-25)*: `surface_fractions/bookkeeping.py`,
  `regressors.py`, `output.py`, `run_fractions.py`. Remainder →
  `impervious_total` (share of remainder) → `bare` residual → `paved` =
  `impervious_total − built`, clamped at 0 and flagged, with `paved_unclamped`
  and `sum_excess` emitted; the eight sum to exactly `1 + sum_excess`
  (asserted). Over-subscription flagged, never rescaled. Vegetation, water
  and the impervious share are **PLACEHOLDER constants**; any quantity
  derived from one has provenance `placeholder:<method>`, and the run
  carries `contains_placeholder: true`. The writer refuses output that
  breaks either rule. Estimate-quality fields (prediction intervals,
  `paved` derivation uncertainty) are `not_computed`.
- **Part 6 — flags and context** *(2026-09-25)*: `surface_fractions/context.py`.
  Per-pixel OSM sub-type flags (any overlap; covered share emitted
  alongside): vegetation (sports field, golf, park, farmland), bare (sand,
  rock, landfill, quarry, dirt track, unpaved parking), other (pier/quay,
  context only). Salt flat and dry lakebed: `no_producer`. Synthetic-turf
  check and bare geographic plausibility: criteria UNSET, `not_computed`.
  Volcano: GVP match inside the AOI plus a descriptive DEM summary; **the
  GVP service refuses programmatic access** (HTTP 403 / reset, 2026-09-25),
  so the layer reads a hand-supplied official export and is `unavailable`
  until one exists; per-pixel volcano flag `not_computed` (radius UNSET).
  Terrain: cut-offs UNSET, class distribution `not_computed`; slope and
  elevation percentiles reported.
- **Part 7 — labelling tooling** *(2026-09-25)*: `labelling/`,
  `configs/labelling.yaml`. Stratified tile frame (200 m tiles on the S2
  lattice, hand-drawn strata, seeded rank per stratum fixed before any
  count; imagery-footprint eligibility); polygon → 10 m fractions through
  the pipeline's own rasteriser, with `unsure` + `shadow_full` out of the
  cell denominator and partial shadow as a flag; per-tile §8 record (all
  fields mandatory), versioned never-overwritten label store, dropped tiles
  locked, validation labels sealed by batch with an unseal log; blind
  re-label QC at polygon (IoU) and 10 m fraction (MAE, R²) level. **All
  five §9 open numbers are UNSET** and every function needing one refuses
  to run. Phase A default flagged for review: a tile straddling strata
  takes the plurality stratum; ties are ineligible.
- **Rulings 1 + 3 — `excluded`, solar** *(2026-09-25)*: detectors gain
  status `excluded` (provenance `excluded:<datasets>`, zero on known pixels,
  does not block the remainder). `snow_ice`: GLIMS `current` + MODIS
  MCD12Q1 (2024) IGBP class 15; `solar`: TZ-SAM 2025Q3 + Global Renewables
  Watch v1, with a caveat that both are utility/commercial scale. Excluded
  only if every dataset shows none. Positive controls: Mont Blanc (GLIMS 86
  outlines, MODIS class 15 present) and Bhadla (TZ-SAM 3, GRW 4) are not
  excluded; Dharavi is excluded for both. Solar yields to `built` on
  footprints (`solar ≤ 1 − built`, flagged `solar_yielded_to_built`).
- **Ruling 4 — guide v1.1** *(2026-09-25)*: `solar` label ground-mounted
  only; rooftop panels `built` + `rooftop_solar` flag (refused on any other
  label).
- **Ruling 5 — `label_limited`** *(2026-09-25)*: `impervious_total` label
  agreement = the derived `built + paved` label fractions compared between
  labellings (MAE, R²), label-limited if worse than item 21's floors (MAE
  ≤ 15 pp, R² ≥ 0.3) on either. **`built` has no numeric validation bar in
  this manual** (item 21 "`built` validation" defines a comparison, not a
  number), so its bar is UNSET in `configs/labelling.yaml` and its
  `label_limited` is `None`. Every other class: `None`.
- **Ruling 6 — naming and records** *(2026-09-25)*: `iou_10m` →
  `weighted_jaccard` in code, tests and docs; result schema bumped to
  `geowatch.surface_fractions.phase_a/2`. `labelling.tiles.save_frame()`
  writes the frame with run metadata (sampler seed, stratum rule, guide
  version, config SHA-256, git HEAD) and never overwrites.
- **Measurement A — imagery inventory** *(2026-09-25; measurement, no
  status change)*: `experiments/item21_sites/results/imagery_inventory.md`.
  104 candidate scenes ≤ 2 m across the 8 sites (OpenAerialMap, Maxar Open
  Data, recorded city sources), each with its catalogue acquisition time
  (on-the-hour OAM times flagged as date-only), resolution, licence and
  Sentinel-2 L2A clear-scene counts. **No source chosen.** Kibera's pre-flood
  Maxar scene reproduces the site list's 2 / 4 / 9. Flags: OAM lists
  Cajamarquilla as CC-BY 4.0 while the site list says "no licence"; Maxar
  Kenya acquisition collections say `proprietary` under a CC-BY-NC event;
  neither Cape Town's image service nor Rio IPP's publishes an acquisition
  time.
- **R2 — `mixed_water_vegetation` from datasets** *(2026-09-25)*: mangrove =
  GMW coverage, continuous, no override (dataset provenance never zeroes
  vegetation / water); non-mangrove `excluded` when the AOI's GLWD band holds
  no class 1–33, else `not_computed`. Live controls (3 × 3 km, real export
  path): **positive** — East Kolkata Wetlands: GLWD 1 + 30, mangrove 0 →
  `not_computed`; Dharavi: mangrove 8.9%, GLWD 6/15/19/28/31 →
  `not_computed`; **negative** — Sahara interior and Orangi (Karachi): no
  GLWD class → `excluded`. **Consequence:** at 3 × 3 km boxes on 7 of the 8
  site settlements (all but Orangi) GLWD shows some class, so the remainder
  stays blocked there; Riyadh's Olaya district also shows class 15. Reading
  "wetland" as 8–33 instead of 1–33 changes none of these outcomes.
- **R2 amended — per GLWD cell** *(2026-09-25)*: bookkeeping now blocks
  the remainder **per pixel** (an input NaN on a known pixel blocks only that
  pixel) and reports `blocked_pixel_share` with a per-input breakdown;
  quantities report `computed` / `partial` / `not_computed` and their
  computed share. Controls (3 × 3 km, real export): Sahara and Orangi 0%
  blocked; Riyadh Olaya 2.8%; Dharavi 97.6% (mangrove 8.9%); East Kolkata
  Wetlands 100%. **Site boxes:** Lima B 0%, Karachi (Orangi) 0%, Kibera 9.7%,
  Cape Town (Khayelitsha) 17.5%, Rocinha 26.6%, Monrovia 63.1%, **Makoko
  99.3%** — Makoko lies almost wholly in GLWD wetland cells, so even per
  cell its remainder is computed on < 1% of the box.
  `experiments/item21_sites/results/r2_per_cell_controls.json`.
- **Measurement B — `built` + two-source disagreement** *(2026-09-25;
  measurement, no status change)*: full approved 3 × 3 km boxes (9.06 km²
  after snapping to the 10 m lattice). Descriptive only — two footprint
  datasets, not labels, so no pass/fail:

  | Site | OB coverage | MS coverage | MAE | weighted_jaccard | bias (OB − MS) |
  |---|---:|---:|---:|---:|---:|
  | Makoko | 0.222 | 0.145 | 0.137 | 0.457 | +0.077 |
  | Kibera | 0.284 | 0.244 | 0.143 | 0.574 | +0.040 |
  | Rocinha | 0.080 | 0.054 | 0.064 | 0.353 | +0.026 |
  | Lima (B) | 0.113 | 0.063 | 0.087 | 0.340 | +0.050 |
  | Monrovia | 0.158 | 0.149 | 0.072 | 0.620 | +0.009 |

  Karachi (box pending) and Cape Town (extent pending) not run.
  `experiments/item21_sites/results/built_disagreement_sites.json`. Two
  lookup defects found and fixed on the way (`surface_fractions/inputs.py`):
  the Microsoft country was read at the AOI **centroid**, which in Makoko
  falls in the lagoon with no LSIB polygon (crash) — now every intersecting
  country, refusing multi-country AOIs; and sat-io stores large countries
  as a **folder of tables** (Nigeria: 4) — now merged.

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

### 33. C19 — denominator + `observed_fraction`
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
