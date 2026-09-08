# GeoWatch — Architecture

**What the project becomes, and why each piece is shaped the way it is.**

Read `01_DIAGNOSIS.md` first — this document assumes the conclusions reached
there.

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

## 3. The fraction taxonomy (Decision 11 — SETTLED)

### The five fractions

Disjoint. Sum to approximately 1 per unit area.

| Fraction | Definition |
|---|---|
| **built** | Roofed structure — has a footprint |
| **paved** | Hard surface, unroofed — paving, hardstanding, courtyard, compacted yard |
| **vegetation** | |
| **water** | |
| **bare** | Permeable unpaved ground, exposed soil |

### The derived quantity

impervious_total = built + paved


This is what the flood model consumes. It is **computed, not measured** — a
derived quantity naming its own inputs, not a sixth fraction.

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

### The built-vs-footprint cross-check

Two independent sources on the same quantity, which the project has never had.

If a block reads 40% `built` but Open Buildings footprints cover 8% of it,
something is wrong — either the footprint layer is missing buildings there, or
the fraction is over-calling `built`. Either way you know, and you know *where*.

Contrast with the old architecture: nothing could reveal that `paved_road` was
2.4× over-predicted until a bespoke analysis was run months later.

**Known scope boundary, stated explicitly:** these five fractions answer
land-cover proportion and imperviousness. They do not answer land-use,
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

### 5.1 Spectral unmixing → continuous fractions (Decision 13 — SETTLED)

Model each 10 m pixel as a linear mixture of endmembers; solve for per-pixel
abundance fractions via constrained least-squares (non-negativity,
sum-to-one). `pysptools`, or Earth Engine's own unmixing tools.

**Chosen strategy: Option D, constrained.** Not five endmembers of equal
difficulty — three spectrally stable fractions extracted from a global
library directly (vegetation, water, bare), and two contested ones (`built`,
`paved`) extracted from the same global-library approach but with extraction
*constrained* by non-spectral priors already built for exactly this pair.

**`built` extraction:** pixels inside a building footprint (Open Buildings /
Microsoft / Overture, inward margin to exclude edge-mixed pixels), further
filtered to low-temporal-variance pixels within that set (stable roofs, not
degrading or under-construction ones). Endmembers extracted from this
filtered pool per region — labeled by construction.

**`paved` extraction — must not use OSM road centerlines.** A pixel on a
centerline at 10 m is ~45% road / 55% roof — that is C29, the exact
contamination this rebuild exists to escape. Source instead from wide,
unambiguously unroofed OSM *polygons*: `landuse`, `amenity=parking`,
`aeroway=apron` — parking lots, airport aprons, plazas, industrial
hardstanding. Many pixels across, spectrally pure by construction, globally
available.

**Shadow — solved as a sixth term, not redistributed.** Under sum-to-one with
no shadow term, shadow energy is forced into the darkest available fraction —
`water` — the worst possible direction for a flood-model consumer. Solve
shadow as a sixth endmember, then renormalize the other five to sum to 1 over
the illuminated portion only. Shadow fraction reported as its own coverage
field. Do not redistribute proportionally across the five — that assumes
knowledge of what's under the shadow, and not having that knowledge is what
shadow means. This is structurally the same problem as Decision 14's
observability denominator — see `05_BUILD_MANUAL.md` Part 3, Decision 14.

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
| Flood risk | `impervious_total` + vector conduits | Yes |
| **Coverage / reliability score** | Per-area, mandatory | Yes — keeps all of the above honest |

---

## 7. Decisions — Part 3, all SETTLED

Full reasoning for every decision lives in `05_BUILD_MANUAL.md`, Part 3. This
section is a pointer, not a duplicate, so the two documents cannot drift out
of sync with each other.

- **Decision 11 — Fraction taxonomy.** Settled. §3 above.
- **Decision 12 — Does SAM survive?** Settled: deleted. Nothing in §6's
  outputs table consumes a segment. The one genuine gap found under
  stress-testing — object-level tracking of non-building features, e.g. water
  bodies — is answered by connected-component labeling on thresholded
  unmixing rasters, named as a deferred, unbuilt forward reference, not by
  keeping SAM.
- **Decision 13 — Global endmember strategy.** Settled: Option D, constrained.
  §5.1 above.
- **Decision 14 — The `category_area_pct` denominator.** Settled: known-pixel
  denominator, mandatory observed-fraction field, shadow / cloud-nodata /
  low-confidence unmixing reported as three separate fields, never merged
  into one "unknown."
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
- **Decision 13's endmember strategy is unvalidated until the pilot runs.** If
  global endmembers cannot be made to work even in constrained form, that
  component weakens substantially and the plan needs revisiting.
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
  administrative questions are out of scope entirely.** The five fractions
  answer land-cover proportion and imperviousness only. A "full" urban
  planning tool needs these as additional, separate data layers on top of
  this one — see §3's scope boundary.
