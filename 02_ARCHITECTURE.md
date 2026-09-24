# GeoWatch — Architecture

**What the project becomes, and why each piece is shaped the way it is.**

Read `01_DIAGNOSIS.md` first — this document assumes the conclusions reached
there.

**Two claims in this document are falsified by the item 21 investigation** —
§"the classes are no longer sub-pixel" and §"misallocation between `built` and
`paved` leaves `impervious_total` unchanged". Both are recorded in
`07_ITEM_21.md`, with the full measurements in `06_UNMIXING_CEILING.md` on the
unmerged `unmixing-ceiling-investigation` branch. They stand uncorrected here
pending sign-off; do not build against them. `08_STATE.md` has the current
state of that sign-off and of every branch.

---

## 1. What GeoWatch is now

**A global urban analysis system that measures proportions, densities,
connections, and change over an area — with flood risk as one of several
outputs.**

Two shifts define it:

- From **naming pixels** to **measuring areas**
- From **one representation for everything** to **the right representation per
  question**

Formal and informal urban fabric are weighted equally. The same pipeline, the
same taxonomy, and the same outputs apply in Paris, Beijing, Kampala, Lagos, and
Dharavi. No regional variants, no per-city manual steps.

---

## 2. Three sources of truth

Each does what it is physically capable of, and nothing more.

| Source | Provides | Why it can |
|---|---|---|
| **Spectral unmixing** | Continuous fractions per area | A 4.5 m road contributes its correct *proportional* share to a block even though it cannot be resolved as an object. Aggregates survive sub-pixel mixing; labels do not. |
| **Vector geometry** (OSM + building footprints) | Network connectivity, road length, footprint density, access distances, morphology | Vector has no ground sample distance. Works identically at any scale, anywhere. |
| **Temporal signal** | Surface permanence; change over time | Sentinel-2's actual advantage — 5-day revisit, decade-long free archive. Nobody holds a decade of sub-metre imagery over Kampala. |

**Change over time deserves emphasis.** It is the one capability free 10 m
imagery has that expensive very-high-resolution imagery does not. For an urban
planning product, *"how has this area changed over eight years"* may be more
valuable than *"what exactly is this pixel"* — and it is precisely the capability
the old architecture was least equipped to deliver.

---

## 3. The fraction taxonomy (Decision 11 — SETTLED; amended 2026-09-23 and 2026-09-24)

> **AMENDED 2026-09-24 — five fractions become eight.** A planning session
> decided three new fractions (`snow_ice`, `solar`, `mixed_water_vegetation`),
> an explicit occlusion list, a set of per-pixel feature/context layers that
> are *not* fractions, and a list of surface types folded into existing
> fractions as metadata flags. The full record is §"The taxonomy expansion"
> below; `05_BUILD_MANUAL.md` Decision 11 and item 21 carry the same. Where
> this section still says "five", read it as the pre-2026-09-24 taxonomy.

*The governing principle below — measure disjoint things, derive overlapping
ones — is settled and, per the item 21 pilot, vindicated. What the pilot
contradicts is **which** quantities are measured and which derived: it proposes
measuring `impervious_total`, taking `built` from vector footprints directly,
and deriving `paved`. Same principle, reversed assignment. Proposed, not
settled — see `05_BUILD_MANUAL.md` Decision 11 and item 21, and
`06_UNMIXING_CEILING.md` §4.3.*

### ~~The five fractions~~ The eight fractions *(amended 2026-09-24)*

Disjoint. Sum to approximately 1 per unit area **on the known-pixel
denominator** (Decision 14). The first five rows are the original taxonomy; the
last three are new — see §"The taxonomy expansion" below.

| Fraction | Definition |
|---|---|
| **built** | Roofed structure — has a footprint. **Taken from vector footprints, not measured spectrally** (see below) |
| **paved** | ~~Hard surface, unroofed — paving, hardstanding, courtyard, compacted yard.~~ **Sealed surface, unroofed** — asphalt, concrete, tiles, laid stone (sealed courtyards and hardstanding included). **Unsealed ground, even if compacted, is `bare`** *(amended 2026-09-24; see `LABELLING_GUIDE.md` §4)*. **Derived: `impervious_total − built`**, carried with explicit uncertainty |
| **vegetation** | |
| **water** | |
| **bare** | ~~Permeable unpaved ground, exposed soil.~~ **Unsealed ground, including compacted ground** (dirt roads, gravel, compacted yards, dirt parking) and exposed soil *(amended 2026-09-24 with `paved`)*. The residual. Note: "permeable" was struck because compacted earth often is not; see `LABELLING_GUIDE.md` §4 |
| **snow_ice** *(new)* | **Permanent** snow and ice only — spectral signature *plus* low temporal variance. Transient snow is occlusion, like cloud |
| **solar** *(new)* | Solar panels / arrays, as their own fraction |
| **mixed_water_vegetation** *(new)* | Wetlands, mangroves, mudflats / tidal zones, water hyacinth. Sub-typed from datasets; feeds the flood model as its own hydrological input, weighted by sub-type |

### The taxonomy expansion (DECIDED 2026-09-24)

Recorded from a planning session; not previously written down anywhere.

**Three new fractions.**

- **`snow_ice`** — permanent only. Identified spectrally *and* by low temporal
  variance (§5.2). Seasonal or transient snow does not get a fraction; it is
  occlusion (below).
- **`solar`** — its own fraction. **Whether `solar` enters `impervious_total`
  is DEFERRED** until real-world solar prevalence is measured in the
  validation data. Until then `impervious_total = built + paved`, unchanged.
- **`mixed_water_vegetation`** — wetlands, mangroves, mudflats/tidal zones,
  water hyacinth. Sub-typed using Global Mangrove Watch and the Global Lakes
  and Wetlands Database. Enters the flood model (item 26) as **its own
  hydrological input, weighted by sub-type** — not folded into `water` or
  `vegetation`.

**The hard-surface remainder.** The impervious/bare regressor (item 21) splits
whatever is left after the non-hard fractions are taken out:

    hard_surface_remainder = 1 − (vegetation + water + snow_ice + solar
                                  + mixed_water_vegetation)
        — computed on the known-pixel share only (~~shadow-renormalised~~,
          struck 2026-09-24: there is no shadow term to renormalise out)
    impervious_total, bare  = regressor split of hard_surface_remainder
    built                   = vector footprints
    paved                   = impervious_total − built

~~`+ shadow)`~~ — **struck 2026-09-24.** As first recorded, the formula also
subtracted `shadow`, while Decision 14 separately removed shadow from the
known-pixel denominator. That counted shadow twice. The shadow rule below
replaces it.

Before the 2026-09-24 taxonomy amendment the remainder subtracted only
vegetation, water ~~and shadow~~. **It must now also subtract `snow_ice`,
`solar` and `mixed_water_vegetation`**, or those surfaces leak into
`impervious_total` or `bare`.

**Producers of the three new fractions.** Each runs **before** the
hard-surface remainder is computed, because the remainder subtracts it:

| Fraction | Producer |
|---|---|
| `snow_ice` | spectral signature + low temporal variance (§5.2) |
| `solar` | spectral-signature detector |
| `mixed_water_vegetation` | spectral, sub-typed from datasets (Global Mangrove Watch, GLWD) |

Vegetation, water and `impervious_total` are **spectral regression**, per the
item 21 table signed off 2026-09-23 (§5.1).

**The shadow rule (LOCKED 2026-09-24; amended the same day).** Each pixel is
handled one way, never both:

| Pixel | Treatment | Reported as |
|---|---|---|
| **Fully shadowed** | **Occlusion.** Removed from the known-pixel denominator (Decision 14, observability group). **Not** subtracted in the remainder | The shadow observability field |
| **Partially shadowed** | ~~A sub-pixel shadow term in the solve, renormalised out so the fractions sum to ~1 over the illuminated share (§5.1, Decision 13's sixth term)~~ **Stays in the known-pixel denominator. No explicit shadow term.** The regressors are trained on hand labels that include partially shadowed pixels, so robustness to partial shadow is *learned* | Nothing. Never a fraction, never a coverage field |
| **Unshadowed** | Normal | — |

> **Amended 2026-09-24.** The partial-shadow row first named a sub-pixel term
> in "the solve". The design has no unmixing solve: vegetation, water and
> `impervious_total` are regression (item 21, 2026-09-23), so that term had no
> host. A "layered" stage-1 unmixing design was proposed to host it and was
> **withdrawn without being decided**. The partial-shadow row is struck and
> replaced.

So shadow appears as a subtracted term nowhere. Fully shadowed pixels have left
the denominator before the remainder is computed, and partially shadowed
pixels go through the regressors like any other known pixel.

**Partial shadow is tested, not assumed.** The hand-digitisation pass labels
partial shadow separately (item 21, "Validation additions"), so validation can
measure whether learned robustness holds. **If it fails, a dedicated fix is
added then, with evidence** — not now, in advance. **Open, not decided:** where
the full/partial boundary sits; the same labels are the evidence that can set
it.

**Folded into existing fractions as metadata flags — no new fraction.**

| Surface | Fraction | Flag |
|---|---|---|
| Sports fields, golf courses, parks, farmland | `vegetation` | OSM sub-type flag. Sports fields also get a **secondary, confidence-flagged synthetic-turf spectral check** |
| Sand, salt flats, rock / bedrock / volcanic rock, dry lakebeds, dirt tracks / unpaved parking, landfills, quarries | `bare` | OSM or geographic-plausibility flag |
| Docks | `built` | — |

**Occlusion — never a fraction.** Cloud, shadow, transient snow, fire/smoke of
all kinds, ships. All sit in Decision 14's **observability** group and remove
the pixel from the denominator.

**Feature / context layers — not fractions.** Per-pixel, and one AOI can carry
many flags at once.

- **Volcano** — named identification by matching the Smithsonian Global
  Volcanism Program. **No confidence flag on a database match.** Copernicus
  DEM is secondary shape confirmation. The surface underneath is still counted
  in its real fraction; the volcano flag never replaces it.
- **Terrain** — flat / hilly / mountainous from Copernicus DEM slope and
  elevation, per pixel, reported **as a distribution per AOI**.
- **Named mountain ranges** — not built. Possibly a cosmetic label later.

**New datasets:** Global Mangrove Watch; Global Lakes and Wetlands Database;
Smithsonian GVP; a **second building-footprint source** (Microsoft or OSM
buildings) to give `built` a confidence; regional geological data where
available; expanded OSM `landuse` tags.

**Volcanic hazard module:** parked as a future sixth hazard module. Not
specified.

### The measured quantity, and the derived one (INVERTED — signed off 2026-09-23)

    impervious_total  = measured spectrally          (ceiling 0.822)
    built             = taken from vector footprints
    paved             = impervious_total − built     (derived, with uncertainty)

**This is the reverse of what this document originally specified**, which
measured `built` and `paved` and derived `impervious_total = built + paved`.
The inversion is signed off; the reasoning and the measurements behind it are
`06_UNMIXING_CEILING.md` and `07_ITEM_21.md`.

**Why it had to invert.** `built` and `paved` are not separably measurable at
10 m from Sentinel-2. Spectral angle between a realistic informal `built`
endmember and `paved` is **1.66°** — the institutional `built` candidate shows
4.69°, but using it *manufactures a separability that does not physically
exist*. Meanwhile `impervious_total` — the quantity the flood model actually
consumes — is measurable to a ceiling of 0.822. So the architecture now
measures the thing it can measure and derives the thing it cannot.

`bare` becomes the residual, absorbing the impervious/bare confusion where it
belongs rather than hiding it inside `paved`.

**This preserves the governing principle below — measure disjoint things,
derive overlapping ones — and corrects which quantity is which.** `paved` must
never be presented as measured.

**Downstream cost is small.** Flood risk consumes `impervious_total`, so it is
unaffected — in fact it now consumes a measured quantity instead of a sum of
two unreliable ones. Morphological characterisation (item 23) is explicitly
non-spectral, so it is unaffected. Change-over-time improves. The only genuine
loss is *roofing material per building*, which was never deliverable from this
data.

### Why disjoint, and why this matters

A concrete roof is physically both a structure and an impervious surface. The
temptation is to let it count in both.

**Do not.** The moment fractions overlap:

- **Sums break.** A block that is entirely concrete roof reports built 100%,
  paved 100%, total 200%. Every consumer must then know which fractions overlap
  and by how much — tribal knowledge encoded nowhere.
- **Change detection breaks.** If `paved` rises 5 points between epochs, did
  paving increase, or did buildings increase and drag `paved` up with them? With
  disjoint fractions the answer is unambiguous.
- **The built-vs-footprint cross-check dies.** That check works only because
  `built` means *structures only*. If `built` also absorbs paving, a mismatch
  against footprint coverage could mean either missing footprints or inflated
  fraction.

**The governing principle: measure disjoint things, derive overlapping ones.**

A measured quantity should have exactly one meaning. Derived quantities can
combine measured ones however downstream needs — and each derivation names its
own inputs, so the ambiguity lives in a formula someone can read rather than
inside a number someone must remember the rules for.

The audit is a catalogue of what happens when that principle is violated: a
value whose meaning depended on which module produced it, a percentage whose
denominator was invisible at the call site, a distance normalized by something
that varied per AOI. Every one was a measured quantity carrying more than one
meaning.

### The naming choice

`paved` rather than `impervious` is deliberate. It names *what the thing is*
rather than *a property it has* — which prevents exactly the confusion that
"impervious excludes buildings, but buildings are impervious" invites. Then
`impervious_total = built + paved` is transparently derived and nobody misreads
it.

### Where the fine detail lives

Fractions answer **how much**. Vector answers **what kind**.

Fractions: this block is 62% built, 4% paved, 18% vegetation, 3% water, 13% bare

Vector: those 62% built comprise 340 footprints, median area 28 m²,
90th-percentile spacing 2.1 m, path network density 8 km/km²,
low orthogonality index
→ informal fabric, characterized by measurement


The same machinery describes Paris: 240 footprints, median 180 m², regular
spacing, gridded network, high orthogonality → formal.

**This is the key move for the formal/informal distinction.** Formal and informal
roofing are not reliably separable by reflectance at 10 m. They are very
separable by **morphology** — footprint size distribution, spacing regularity,
density, network geometry, block structure. All of that lives in vector, at
native geometry, with no resolution ceiling.

So the distinction is placed where the evidence actually is, rather than
demanded from spectra that cannot supply it.

### The weakest boundary, named

**`built` vs `paved` is the least reliable of the five.** A concrete roof and a
concrete yard are close to identical in reflectance at 10 m.

Their actual separators are not spectral:

- **Temporal variance** — roofs are more stable than open hardstanding, which
  accumulates dust, wetness, vehicles, seasonal use
- **The footprint layer as a prior** — a structure has a footprint; a courtyard
  does not

This is a case where the three components genuinely reinforce each other rather
than merely coexisting. But it must be **reported as a confidence distinction**,
not hidden: the `built`/`paved` split carries lower confidence than the other
boundaries, and consumers should be told so.

### Does the old confusion return?

The same spectral ambiguity exists. The failure mode does not.

**What made the old failure catastrophic was argmax.** A pixel that was genuinely
50/50 road-and-roof was forced to a single hard label, and because the feature
was generic, one class won that coin-flip everywhere. The ambiguity *compounded*
— every mixed pixel handed its full weight to one class.

**Now**, an ambiguous pixel resolves to `built 0.45, paved 0.40, bare 0.15`. That
is not an error; it is the correct answer for a pixel that genuinely contains
both. There is no argmax, no winner, nothing to be a magnet *of*. Ambiguity stays
proportional instead of amplifying.

**This argument survives, with one part of it removed.** Eliminating argmax does
eliminate the magnet failure mode, and that reasoning is untouched. But the
worked example presupposes that the `built`/`paved` split *can* be resolved into
those numbers. Measurement has since shown it cannot at 10 m — see the corrected
bullets below and `06_UNMIXING_CEILING.md`. Proportional ambiguity is still
better than a coin-flip label; it is not the same as a correct decomposition.

Three further differences were claimed here. **Two of them have since been
falsified by measurement** — see `06_UNMIXING_CEILING.md`. They are corrected in
place below rather than deleted, because the original wording is load-bearing
for arguments made elsewhere in this document and in Decision 13.

- **The classes are no longer sub-pixel — CORRECTED, this was wrong.** The
  original read: *"A roof is 3–6 m, a courtyard often 5–15 m — comparable to or
  larger than a 10 m cell."* A 3–6 m roof is **smaller** than a 10 m cell; the
  sentence conceded the problem and then concluded the opposite. Measured
  square-equivalent footprint sizes are **6.9 m (Khayelitsha), 10.6 m
  (Dharavi), 12.4 m (formal Cape Town)**. And "comparable to a 10 m cell" is not
  sufficient: with arbitrary grid phase, the formal suburbs' 12.4 m buildings
  still yield only **4.97%** fully-covered pixels. Roads at 4.5 m were the
  pathological case, but removing that class did not remove the pathology.
- **They do not compete for the same physical space — geometrically true, and it
  does not help.** Roofs and courtyards genuinely are adjacent distinct areas
  rather than interleaved within a square metre. But at 10 m a *single cell
  spans both*, so the mixing is sub-pixel whether or not the surfaces are.
  Measured pure-pixel yield across three AOIs: **1.02–5.43%**.
- **The error is bounded where it matters most — CORRECTED, this was wrong.**
  The original claim was that misallocation between `built` and `paved` leaves
  `impervious_total` unchanged, so the flood model is unaffected. That holds for
  a **swap**, which cancels in the sum. The measured error is not a swap.
  Changing only the `built` endmember between two defensible choices moves
  `impervious_total` by **+81.6% (Dharavi), −27.1% (Khayelitsha), +16.2% (formal
  Cape Town)**. In Dharavi both fractions rose and *compounded*; nothing
  cancelled. The direction is not even consistent across AOIs, so no calibration
  constant can correct it. **The primary consumer is affected.**

**The residual risk is no longer a risk — it is a measurement.** The original
text said that if `built` systematically absorbs `paved` in dense fabric,
morphology metrics distort, and called this "real, not hypothetical." It is now
quantified, and it is worse than the framing suggested: `built` and `paved` are
separated by **1.70°** of spectral angle against a sensor noise floor of ~0.7°,
so the split is not low-confidence — it is **unidentifiable**. Worse, the
institutional-roof endmember that Decision 13's spec would actually produce sits
4.69° from `paved`, versus 1.66° for a realistic informal-roof endmember:
**using it manufactures separability that does not physically exist**, yielding
a confident-looking split that is an artifact.

The cross-check below remains a deliberate build item, and becomes more
important rather than less.

**Resolved 2026-09-23: the inversion is signed off.** Everything above is now
the *reason* for the architecture in §3 rather than an open problem — the
`built`/`paved` split is no longer attempted, so an unidentifiable 1.70°
separation stops being a defect and becomes a design constraint that is
respected. `impervious_total` is measured; `built` comes from the footprints;
`paved` is the difference.

**One residual risk the inversion introduces, stated plainly:** `paved` is a
difference of two independently-estimated quantities, so its uncertainty is at
least the larger of the two and it **can go negative** in dense fabric where
footprint coverage over-calls. It must be reported with that uncertainty
attached and clamped explicitly, never silently.

### The built-vs-footprint cross-check

Two independent sources on the same quantity, which the project has never had.

If a block reads 40% `built` but Open Buildings footprints cover 8% of it,
something is wrong — either the footprint layer is missing buildings there, or
the fraction is over-calling `built`. Either way you know, and you know *where*.

Contrast with the old architecture: nothing could reveal that `paved_road` was
2.4× over-predicted until a bespoke analysis was run months later.

**Known scope boundary, stated explicitly:** these ~~five~~ eight fractions
answer land-cover proportion and imperviousness. The 2026-09-24 metadata flags
(OSM sub-types, volcano, terrain) add *context*, not land-use classification. They do not answer land-use,
vegetation type, building condition, or anything demographic/administrative.
A "full" urban planning tool would need those as separate data layers (census,
cadastral, infrastructure records) on top of this one. This architecture is the
physical land-cover layer of such a system, not the whole system — see §9.

---

## 4. The road architecture

### The governing rule: one source, many representations

**All road-derived outputs trace to a single vector layer.** Rasterization for
flood, aggregation for density, network analysis for access — every one
downstream of the same source.

This is non-negotiable, for a reason the audit already established. If each
consumer maintains its own road representation, the same value means different
things in different places (C9, C19, the denominator problem). One source means
that when coverage is thin in Kampala, **all road outputs degrade together and a
single coverage number explains all of them.**

### Global road source composition

OSM alone fails the equal-treatment requirement. Measured across the 11 training
AOIs, pedestrian-path density spans **44×** (0.19 to 8.35 km/km²), while total
network density spans only 6× and arterial coverage is near-universal.

The variance is concentrated in exactly the layer informal-settlement routing
needs.

**Composite source, in priority order:**

1. **OSM roads and paths** — primary where present. Globally queryable via
   Overpass.
2. **Building-footprint negative space** — where OSM is thin, the gaps between
   footprints carry road-space information. Open Buildings covers Africa, South
   Asia, Southeast Asia, Latin America and the Caribbean; Overture and Microsoft
   cover formal cities better. Between them, global.
3. **Per-area completeness score — always emitted, never optional.**

### The completeness score is load-bearing

The system must **know it is in a low-coverage regime and say so**, rather than
silently producing worse routing in Kampala than in Paris with identical-looking
confidence.

This is the same lesson as C14 and C32: a system that detects its own
unreliability and hides the detection is failing at its own stated purpose.

Note the score is load-bearing for **two** outputs, not one. Routing degrades
with thin coverage — but so does morphological characterization, since
formal/informal now depends on network geometry. In Lagos you would have
footprints but almost no path network.

### What happens when OSM is missing a road

This is the obvious objection, and two of the three components already answer it.

**Imperviousness is unaffected.** An unmapped footpath is still hard surface.
Unmixing registers it in `paved` regardless of whether anything named it a road.
The flood model's runoff input does not degrade.

**Temporal variance flags it independently.** A paved surface is spectrally
stable year-round; bare soil and vegetation are not. Low temporal variance over a
strip OSM does not know about is a "permanent hard surface here" signal requiring
no vector data at all.

**What is genuinely lost:** *routing geometry* — which specific alley channels
water, and network connectivity for access metrics. Not existence. Not
hydrological contribution.

That is a far narrower loss than "we now depend on OSM," and it is quantifiable.

### Explicitly rejected: the hybrid

Keeping a low-confidence raster `paved_road` as a fallback where OSM is silent
**reintroduces the magnet class into the label space** — the exact thing being
deleted — and requires a reconciliation rule for vector-says-no /
raster-says-maybe conflicts.

Full cost of the class, to recover a signal that unmixing and temporal variance
already supply more cleanly. **Do not build it.**

---

## 5. Component detail

### 5.1 Spectral regression → continuous fractions (Decisions 11 / 13, as amended)

*Heading was "~~Spectral unmixing → continuous fractions (Decision 13 —
REOPENED BY EVIDENCE)~~". Renamed 2026-09-24: the method is spectral
regression (item 21 table, signed off 2026-09-23), and there is no unmixing
endmember. The local paved endmember survives only as an optional regressor
feature, kept if a LOCO ablation shows it helps (Decision 13 as amended
2026-09-24). The unmixing text below is preserved for provenance, with
superseded parts struck.*

> **The 2–3 city pilot this section required has run, and it falsified the
> central assumption.** Both risks left explicitly open below have fired.
> `built` and `paved` are separated by **1.70°** of spectral angle against a
> ~0.7° sensor noise floor, so the constrained extraction cannot produce a
> usable `built` endmember for informal fabric by any method — three extraction
> families were tried and failed, and the failure is an information limit, not
> a method problem. Worse, the institutional-roof endmember this spec would
> produce sits **4.69°** from `paved` versus **1.66°** for a realistic
> informal-roof endmember, so following the spec manufactures separability that
> does not physically exist. The text below is preserved for provenance. See
> item 21 in `05_BUILD_MANUAL.md` for the proposed re-scope (awaiting decision)
> and `06_UNMIXING_CEILING.md` for the evidence. **Not re-settled.**

Model each 10 m pixel as a linear mixture of endmembers; solve for per-pixel
abundance fractions via constrained least-squares (non-negativity,
sum-to-one). `pysptools`, or Earth Engine's own unmixing tools.

**Chosen strategy: Option D, constrained — AS AMENDED BY THE INVERSION
(signed off 2026-09-23).** The original spec extracted `built` *and* `paved`
as separate spectral endmembers. Item 21 measured that this is not achievable
at 10 m, and §3 now inverts it. ~~What unmixing solves for is:~~

> **Superseded 2026-09-24 — one method, not two.** The first two rows below
> described a single unmixing solve: vegetation, water and bare from a global
> library, plus one `impervious_total` endmember. That conflicts with the
> **spectral regression** table signed off 2026-09-23 in item 21 (step 2 of
> the re-scope), which is the method. The two rows are struck. The `built` and
> `paved` rows are unchanged and hold under either method.

| fraction | how it is obtained |
|---|---|
| ~~vegetation, water, bare~~ | ~~spectrally, from a global library directly~~ → vegetation, water: **spectral regression**; bare: **residual** of the impervious/bare split (§3) |
| ~~**impervious_total**~~ | ~~**spectrally, as ONE endmember** — ceiling 0.822~~ → **spectral regression**, splitting the hard-surface remainder (§3) — ceiling 0.822 |
| **built** | **from vector footprints. Not unmixed at all.** |
| **paved** | **derived: `impervious_total − built`.** Not unmixed at all. |

**`built` is footprint-derived, not spectrally derived.** Open Buildings /
Microsoft / Overture footprints rasterised to the 10 m grid. The
low-temporal-variance filter is retained, but its job changes: it no longer
selects endmember pixels, it flags footprints whose surface is unstable
(under construction, degrading) so they can be down-weighted. **Any statement
that `built` is spectrally derived is obsolete.**

**Why `built` and `paved` are not separately unmixed.** Spectral angle between
a realistic informal `built` endmember and `paved` is **1.66°**. The
institutional `built` candidate reaches 4.69°, but choosing it manufactures a
separability that does not physically exist, and swapping between the two
defensible choices moved `impervious_total` by +81.6% / −27.1% / +16.2% across
three AOIs — compounding, with inconsistent sign. See §3.

**The impervious endmember must still not use OSM road centerlines.** A pixel
on a centerline at 10 m is ~45% road / 55% roof — that is C29, the exact
contamination this rebuild exists to escape. Source instead from wide,
unambiguously unroofed OSM *polygons*: `amenity=parking`, `aeroway=apron`,
`highway=pedestrian`+`area=yes`, `place=square`, `landuse=garages` — parking
lots, airport aprons, plazas, hardstanding. **Bare `landuse=industrial` /
`retail` / `commercial` are excluded**: those polygons enclose buildings, so
using them would measure roof purity and label it impervious.

~~**Shadow — solved as a sixth term, not redistributed.**~~ ~~Under sum-to-one with
no shadow term, shadow energy is forced into the darkest available fraction —
`water` — the worst possible direction for a flood-model consumer. Solve
shadow as a sixth endmember, then renormalize the other five to sum to 1 over
the illuminated portion only. Shadow fraction reported as its own coverage
field.~~ ~~*Amended 2026-09-24 by the shadow rule (§3):* the sixth term applies
to **partially shadowed pixels only** and is never reported.~~

> **Superseded 2026-09-24.** There is no unmixing solve, so there is no sixth
> term. Current rule (§3):
>
> - **Fully shadowed pixels are occlusion.** Only they feed the shadow
>   coverage field and leave the denominator.
> - **Partially shadowed pixels** stay in the denominator with no explicit
>   term; the regressors learn robustness from hand labels that include them.
> - No pixel goes through both routes.
>
> **The struck paragraph's warning still applies, in a new form.** Shadow
> energy drifting into `water`, the worst direction for a flood-model
> consumer, is now a failure mode a *learned* model can show. It is exactly
> what the partial-shadow validation labels must test.

Do not redistribute fully shadowed area proportionally across the fractions.
That assumes knowledge of what's under the shadow, and not having that
knowledge is what shadow means. This is structurally the same problem as
Decision 14's observability denominator — see `05_BUILD_MANUAL.md` Part 3,
Decision 14.

**Reflectance precondition:** BOA surface reflectance is already available via
`COPERNICUS/S2_SR_HARMONIZED`. The precondition is not "obtain reflectance,"
it is: unmixing must read the float32 multi-band tile path, never the
per-tile percentile-stretched 8-bit PNG preview. The reflectance exists
upstream; the risk is destroying it downstream at tiling.

**Output shape:** *"this cell is ~35% built, ~5% paved, ~40% vegetation, ~20%
bare"* — an honest representation of what a 10 m cell over mixed fabric
actually contains.

**Validation gate:** compare `built + paved` against two references, weighted
by independence. Open Buildings footprints are VHR-derived and genuinely
independent — weight this comparison more heavily. GHS-BUILT-S is itself
Sentinel-2-derived, so agreement with it is not independent confirmation —
both could share WorldCover's Africa failure mode (47.1% user's accuracy:
bare compacted earth called built). Run a 2–3 city pilot spanning material
diversity before committing to the full build-out.

**Two risks left explicitly open:**
1. Footprint layer quality is weakest exactly where `built`/`paved`
   separation matters most — Open Buildings' own FAQ admits degraded
   performance on small, irregular, densely-packed structures, a description
   of dense informal roofing.
2. Nothing here is confirmed until the pilot validation runs. This is a
   specification for how to build the constrained extraction, not evidence it
   will work.

### 5.2 Temporal variance → permanence signal

Standard deviation of spectral indices across a year of Sentinel-2 composites.
Paved surfaces are stable; bare soil and vegetation are seasonal.

Cheap, orthogonal to everything else, requires no per-city calibration, works
identically worldwide. **Build this regardless of what else happens** — it needs
no decision and provides an early working component.

**Dependency, corrected:** must run after the cloud mask fix (C1, item 51 —
mask from SCL, not QA60), since std-dev is maximally sensitive to exactly the
cloud-leakage outliers an unreliable mask would introduce.

### 5.3 Vector layer

OSM plus footprint negative space, per §4. Emits the completeness score as a
mandatory field.

Derived from it: road length per unit area, footprint density, footprint size
distribution, spacing statistics, orthogonality, network connectivity,
distance-to-access.

### 5.4 Aggregation unit

Ask *"what fraction of this block is hard surface"* rather than *"is this pixel a
road."* A 4.5 m road contributes its correct proportional share rather than being
forced into a false binary.

**Sequence:**

1. **Regular-grid blocks** — free, immediately available, do first
2. **Building-footprint units** — once the footprint layer lands; gives an
   individually-addressable unit for risk communication
3. **Path-delineated segments** — most faithful to how water and people actually
   move, but requires the vector layer to define segment boundaries; sequence last

**State plainly in any writeup:** this is a deliberate resolution tradeoff toward
screening-scale answers, not a limitation that went unsolved.

---

## 6. Outputs

| Output | Source | Global? |
|---|---|---|
| Land-cover proportions per area | Unmixing fractions | Yes |
| Density metrics (road length, footprint density, imperviousness) | Vector + fractions, aggregated per unit | Yes |
| Access / service indicators | Vector network analysis | Degrades with OSM coverage — score emitted |
| Morphological characterization (formal / informal) | Vector footprint + network statistics | Degrades with OSM coverage — score emitted |
| Change over time | Fraction deltas across composites | Yes — the strongest capability |
| Flood risk | `impervious_total` + vector conduits + `mixed_water_vegetation` (own hydrological input, weighted by sub-type — added 2026-09-24) | Yes |
| Context layers *(added 2026-09-24)* | Volcano (Smithsonian GVP + Copernicus DEM), terrain distribution (DEM slope + elevation), OSM sub-type flags | Yes — per-pixel flags, not fractions |
| **Coverage / reliability score** | Per-area, mandatory | Yes — keeps all of the above honest |

---

## 7. Decisions — Part 3

Full reasoning for every decision lives in `05_BUILD_MANUAL.md`, Part 3. This
section is a pointer, not a duplicate, so the two documents cannot drift out
of sync with each other.

Decisions 12, 15, 16 and 17 are settled. **Decisions 11, 13 and 14 carried
amendments proposed by the item 21 pilot; all three were SIGNED OFF on
2026-09-23** and are settled again as amended.

- **Decision 11 — Fraction taxonomy.** Settled, **and AMENDED 2026-09-23 by
  the signed-off inversion**: the five fractions stand, but `impervious_total`
  is measured, `built` is footprint-derived, and `paved` is the difference.
  §3 above. The original "measure `built` and `paved`, derive
  `impervious_total`" formulation is superseded.
  **AMENDED AGAIN 2026-09-24 (planning session):** ~~the five fractions
  stand~~ eight fractions — `snow_ice` (permanent only), `solar` and
  `mixed_water_vegetation` added; the hard-surface remainder subtracts them
  (and, per the shadow rule locked the same day, no longer subtracts shadow);
  whether `solar` joins `impervious_total` is deferred. §3 "The taxonomy
  expansion".
- **Decision 12 — Does SAM survive?** Settled: deleted. Nothing in §6's
  outputs table consumes a segment. The one genuine gap found under
  stress-testing — object-level tracking of non-building features, e.g. water
  bodies — is answered by connected-component labeling on thresholded
  unmixing rasters, named as a deferred, unbuilt forward reference, not by
  keeping SAM.
- **Decision 13 — Global endmember strategy.** Settled: Option D, constrained,
  **AMENDED 2026-09-23 (signed off)**. The pilot falsified the original central
  assumption — `built`/`paved` is **unidentifiable at 1.70° against a ~0.7°
  sensor noise floor**, and the institutional-roof endmember the original spec
  would have produced sits 4.69° from `paved` versus 1.66° for a realistic
  informal one, so choosing it manufactures separability that does not
  physically exist. The amendment: ~~**one impervious endmember**,~~ `built` from
  footprints, `paved` derived. **Amended 2026-09-24:** there is no unmixing
  endmember, because the method is regression. The local paved endmember is
  an **optional regressor feature** (spectral angle to the AOI's own local
  paved endmember). It is off by default and kept only if a LOCO ablation
  shows better cross-city transfer. §5.1 above. Item 21's ceiling result is signed
  off, so this is settled spec rather than an unsigned investigation premise.
- **Decision 14 — The `category_area_pct` denominator.** Settled: known-pixel
  denominator, mandatory observed-fraction field, shadow / cloud-nodata /
  low-confidence unmixing reported as three separate fields, never merged
  into one "unknown."
  **Confirmed 2026-09-23 under the inversion**: `paved`'s derivation
  uncertainty is a fourth thing that must be reported separately and never
  folded into "unknown" — it is a *derived-quantity* uncertainty, not an
  observability one.
  The four field-spec changes that followed from the Decision 13 reopen are
  signed off with it.
  **Extended 2026-09-24:** the observability (occlusion) group is now cloud,
  shadow, transient snow, fire/smoke of all kinds, and ships. None is a
  fraction; all remove the pixel from the denominator. **Shadow here means
  fully shadowed pixels only.** Partial shadow ~~is renormalised out in the
  solve~~ stays in the denominator with no explicit term, and robustness to
  it is learned by the regressors (§3, the shadow rule, amended
  2026-09-24).
- **Decision 15 — Severity re-rating rule.** Settled: downgrade only on
  confirmed unreachability or confirmed absence of a consumer, never on
  "never observed to fire" alone. Severity and fix priority are separate
  axes — a downgrade does not remove a scheduled fix.
- **Decision 16 — Who is the planning user?** Settled: research audience, not
  planning audience. The five outputs above stay in the build, reframed as
  "here is why this should be trusted" rather than "a planner validated
  this."
- **Decision 17 — Gate C.** Settled: closed via structured advisor/faculty
  review against D.7's five reporting requirements. The original
  planner-validation protocol is retained as documented, unrun future work
  (item 64), disclosed explicitly as blocked by access.

---

## 8. What survives from the old architecture

The findings that no architecture change touches — the *irreducible cluster*.

**Authoritative list: see `04_FINDINGS_LEDGER.md`, SURVIVES section.** That
file's fate-tracking is the single source of truth for this list; it is not
reproduced here to avoid the two documents drifting out of agreement with
each other.

That cluster is the epistemic contract, the gating architecture, orchestration
hygiene, and honesty propagation.

**It is the same cluster identified as irreducible before the rebuild was
conceived, and it survived the rebuild** — which is the strongest available
argument that it is real work rather than an artifact of the old design, at
the level of *pattern*. At the level of specific mechanism, several of these
findings are defined against code that Decision 12 deletes (SAM-conditional
items) or that Decision 14 reformulates (the epistemic-contract cluster's
field specs) — see `05_BUILD_MANUAL.md` Part 6's translation note.

---

## 9. What this architecture does not solve

- **The sensor limit remains.** Fractions and vector are honest accommodations,
  not a resolution fix. If the actual need is street-level surface material in
  informal settlements, 10 m optical cannot deliver it.
- **Decision 13's endmember strategy did not survive its pilot.** The 2–3 city
  pilot ran; global endmembers could not be made to work even in constrained
  form, because `built`/`paved` is unidentifiable at 10 m (1.70° against a
  ~0.7° noise floor). Decision 13 is reopened and item 21's re-scope — measure
  `impervious_total`, take `built` from vector footprints, derive `paved` — is
  proposed and awaiting decision. See `05_BUILD_MANUAL.md` items 13 and 21 and
  `06_UNMIXING_CEILING.md`.
- **No global independent gold set exists.** Confirmed dead end. The held-out
  firewall and intra-annotator test-retest mitigate single-annotator risk; neither
  eliminates it, and neither produces a number meaning what Cohen's kappa means.
- **Gate C closes only in its narrower, research-audience form** (Decision 17).
  The planner-usefulness question remains genuinely open, disclosed as future
  work rather than answered.
- **OSM gaps remain real** for routing geometry and access metrics. Quantified,
  not eliminated.
- **Past provenance is permanently lost.** Everything before the first commit is
  unreproducible.
- **Morphological characterization is coverage-dependent.** Formal/informal now
  rests on network geometry, so it degrades exactly where OSM is thin — which is
  disproportionately in informal settlements.
- **Land-use, vegetation type, building condition, and demographic/
  administrative questions are out of scope entirely.** The ~~five~~ eight
  fractions answer land-cover proportion and imperviousness only. A "full" urban
  planning tool needs these as additional, separate data layers on top of
  this one — see §3's scope boundary.
- **Volcanic hazard is not assessed.** Volcanoes are identified as a context
  layer (§3); a volcanic hazard module is parked as a future sixth hazard
  module and is not specified.
