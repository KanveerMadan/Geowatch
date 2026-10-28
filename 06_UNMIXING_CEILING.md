# GeoWatch — The Unmixing Ceiling

**Six pre-registered methods, one mechanism, and a measured limit.**

This document consolidates the investigation into whether per-pixel `built`
fraction can be recovered for small-structure informal fabric at 10 m / 6-band
Sentinel-2, as Decision 13 and Part 4 item 21 assume.

It concludes that it cannot, and — unusually for a negative result — says *why*
quantitatively rather than empirically. The limit is computed from measured
surface spectra and documented sensor noise, not inferred from a run of
failures.

Confidence: **[E]** empirical · **[S]** static · **[R]** reasoned

---

## Bottom line

1. **The `built`/`paved` split is not recoverable at 10 m / 6 bands.** [E]
   Under conditions strictly more favourable than reality, the best achievable
   R² for built fraction is **0.49–0.56** — the project's own success bar is
   0.50. Every real-world effect pushes below it.

2. **The cause is spectral, not methodological.** [E] All four hard-surface
   classes — institutional roof, informal roof, asphalt, bare soil — lie within
   a **cone under 5° wide**, against a sensor noise floor of ~0.7°.

3. **The union is recoverable even though the split is not.** [E] Merging
   `built` and `paved` into `impervious` raises the ceiling from **0.49 to
   0.82**, because the confusion becomes internal to the class.

4. **`built` should come from vector footprints, not from spectra.** [R] Open
   Buildings coverage was used as the regression *label* throughout this
   investigation. It is a VHR-derived, Sentinel-2-independent estimate of
   exactly the quantity item 21 tries to predict from spectra.

5. **Of the three rare fractions, only `snow_ice` clears the bar.** [E]
   *(Part 8, 2026-10-28.)* `snow_ice` 0.925, label it; `solar` 0.677,
   indeterminate (rooftop panels at realistic shares 0.436, don't label);
   `mixed_water_vegetation` 0.368 with no verdict, because adding it drops
   vegetation's own ceiling from 0.974 to 0.634.

---

## Part 1 — What was tried

Six methods, each pre-registered before running, each with a synthetic
self-test on data with a known answer, each measured with the same three
diagnostics (leave-one-AOI-out transfer; within-AOI reference with zero domain
shift; performance on building-containing pixels only).

AOIs throughout: **Dharavi** (4.68 km²), **Khayelitsha**
(`capetown_20260702_164022`, 23.11 km²), **Cape Town formal suburbs**
(ad-hoc Rondebosch/Claremont bbox, 14.36 km²).

| # | Method | Result | Script |
|---|---|---|---|
| 1 | Vector-mask endmember extraction | 1–5% pixel purity; adverse selection 4.66–22.45× toward largest buildings | `diagnose_pure_pixels.py` |
| 2 | VCA / N-FINDR (pure-pixel spectral) | **0 of 44** vertices were small-structure fabric | `extract_endmembers_vca.py` |
| 3 | SISAL (minimum-volume simplex) | Hollow pass; 56% of vertices physically impossible, 52% pure extrapolation | `extract_endmembers_sisal.py` |
| 4 | Per-pixel spectral regression | Transfer R²=0.080; within-AOI ~0.35; **negative** on building-containing pixels | `regress_built_fraction.py` |
| 5 | + spatial texture + item-18 temporal variance | Transfer R²=0.093; within-AOI 0.380; **still negative** on building pixels | `regress_built_fraction_spatial.py` |
| 6 | Scale-mismatch hypothesis | **Falsified by its own self-test** before real data | `regress_scale_sweep.py` |
| 7 | + PanTex texture + Sentinel-1 SAR | Transfer R²=**0.175** — best of the investigation, still 3× below bar; building-pixel R² **still −0.182** | `regress_scale_sweep.py` |

### 1.1 Why each failed — and why it is one mechanism, not six

**Method 1** established that Open Buildings footprints supply almost no clean
`built` endmember pixels. Only 1.02% (Khayelitsha) to 5.43% (Dharavi) of
building-touching pixels are fully covered by footprint on the real S2 grid,
and the buildings that do contribute are 4.66–22.45× larger than the local
building population. In Khayelitsha, **200 buildings out of 93,409** contribute
a pure pixel, mean footprint 1,057 m² against a settlement mean of 47.1 m².
Those are warehouses and civic halls, not the corrugated metal that constitutes
the settlement.

An important negative-of-a-negative: the **formal-fabric advantage disappears**
at the pixel level. Dharavi's 5.43% *beats* the formal suburbs' 4.97%. The
earlier "formal fabric gives ~2× better yield" conclusion was an artifact of a
polygon-area proxy and did not survive direct measurement.

**Method 2** confirmed the mechanism rather than merely failing. VCA and
N-FINDR select the most *extreme* observed pixel; small-structure fabric is
**interior** to the spectral simplex and never extreme. The control matters:
small-fabric pixels are **9.98% of Khayelitsha's uniform sample**, so the
failure is not that the class is absent — it is that the class is never at an
extreme. 37 of 44 vertices were also weakly supported (under 100 pixels within
5.74°), several by exactly one pixel.

**Method 3** was the correct tool for "no pure pixels exist" — minimum-volume
methods fit an enclosing simplex rather than assuming pure pixels at the
extremes. It produced a vertex 2.36° from the small-fabric reference with 40%
support, which passed the pre-registered angle test. **That pass was hollow:**
the vertex was the reference direction scaled by **5.06×**, with reflectance up
to 1.106 — physically impossible. Spectral angle is scale-invariant and was
structurally blind to a 5× magnitude error. Recorded as a defect in the
criterion, not reclassified after the fact.

**Methods 4 and 5** removed the endmember requirement entirely, regressing
6-band reflectance directly onto a geometric label. This was the cleanest
possible test — no mixing model, no purity requirement. Adding 20 spatial and
temporal features moved cross-city R² from 0.080 to 0.093, and within-AOI (zero
domain shift) from 0.346 to 0.380. **On building-containing pixels R² stayed
negative in all three AOIs and all three feature sets** — worse than a constant
predictor at estimating how much building is present.

**Method 7** — PanTex anisotropic contrast (GHS-BUILT-S's own lever) plus
Sentinel-1 VV/VH backscatter and its texture — produced **the best result of the
whole investigation**, and it is still nowhere near sufficient:

| held-out AOI | transfer R² | MAE | baseline MAE | built>0 R² | within-AOI R² |
|---|---|---|---|---|---|
| Dharavi | 0.149 | 0.2306 | 0.2862 | −0.488 | 0.344 |
| Khayelitsha | 0.075 | 0.1908 | 0.2363 | −0.104 | 0.389 |
| CT formal | 0.300 | 0.1963 | 0.2620 | **+0.045** | 0.437 |
| **mean** | **0.175** | 0.2059 | — | **−0.182** | 0.390 |

Transfer R² nearly doubled (0.093 → 0.175), confirming these are genuinely
informative features — S1 covered all three AOIs (8 / 16 / 24 scenes). But the
bar is 0.50, and building-containing pixels remain negative in aggregate. Only
CT formal turned marginally positive (+0.045), the first non-negative value
seen on that diagnostic anywhere in the investigation.

**Direction C (combined impervious label) behaved exactly as predicted in
advance.** The pre-registration stated it would barely differ from `built`
because OSM paved coverage is 0.23–1.82% of AOI against a built mean of 19–30%.
Measured: **0.158 vs 0.175** — marginally *worse*. The null result is a property
of the label source's sparsity, not evidence against combining the classes; the
ceiling analysis shows the combination is right in principle (0.822), and it is
the *label* that is missing.

**Method 6** was falsified by its own self-test. B11 and B12 are natively 20 m
in `S2_SR_HARMONIZED` (verified against the asset), and
`ingestion/temporal_variance.py:18-21` states that built/paved separation
"reads most directly off these two bands" — i.e. the project's stated signal
carrier is the part that cannot resolve 10 m. But simulating SWIR blur, MTF
blur and one-cell label jitter at realistic severity moved synthetic R² only
from ~1.0 to **0.939**. Those mechanisms cannot produce a 0.35 ceiling.
Hypothesis rejected before any real-data result was read.

---

## Part 2 — The mechanism [E]

Pairwise spectral angles between the **real measured endmembers** (Khayelitsha,
`COPERNICUS/S2_SR_HARMONIZED` median 2026-04-03 → 2026-07-02, SCL-masked, on
the real S2 grid `EPSG:32734`):

| | built_inst | built_fabric | paved | bare | veg | water |
|---|---|---|---|---|---|---|
| **built_inst** | 0.00 | 3.35 | 4.70 | 3.86 | 26.19 | 42.76 |
| **built_fabric** | 3.35 | 0.00 | **1.70** | 3.65 | 24.51 | 45.90 |
| **paved** | 4.70 | **1.70** | 0.00 | 3.45 | 23.15 | 46.86 |
| **bare** | 3.86 | 3.65 | 3.45 | 0.00 | 23.38 | 44.04 |
| veg | 26.19 | 24.51 | 23.15 | 23.38 | 0.00 | 60.66 |
| water | 42.76 | 45.90 | 46.86 | 44.04 | 60.66 | 0.00 |

**Every hard surface sits inside a cone under 5° wide.** Vegetation is 23–26°
away; water 43–47°. Sentinel-2 L2A BOA uncertainty of ~0.005 reflectance is
~0.7° at this magnitude.

So built-vs-paved discrimination lives at roughly **2.4× the noise floor**,
while built-vs-vegetation lives at ~35×. This single table explains every prior
failure: why VCA returned only vegetation and water vertices, why the simplex
was degenerate in the built direction, and why regression went negative
precisely on building-containing pixels (where the remaining variation *is* the
built/paved/bare distinction).

---

## Part 3 — The ceiling [E]

`ceiling_built_fraction.py` simulates pixels from the measured endmembers under
conditions **deliberately more favourable than reality**:

- labels exact — no footprint/grid co-registration error
- mixing exactly linear — no multiple-scattering effects
- endmembers **fixed** — no within-class spectral variability
- no shadow term, no atmospheric residual, no BRDF
- random train/test split — the cross-city transfer problem removed entirely

**Control / self-test:** the same simulation targeting *vegetation* fraction
recovers at **R² = 0.974**, confirming the simulation works on a
well-separated class.

### Noise sweep, target = built fraction

| noise (reflectance) | R² (ridge) | R² (gbt) |
|---|---|---|
| 0.000 | 1.000 | 0.769 |
| 0.001 | 0.776 | 0.750 |
| 0.002 | 0.682 | 0.699 |
| **0.005 (realistic)** | **0.490** | **0.558** |
| 0.010 | 0.335 | 0.405 |
| 0.020 | 0.187 | 0.240 |

**At realistic S2 noise the ceiling coincides with the project's 0.50 bar.**

Stated precisely, without overselling: the pre-registered rule (ridge primary)
returns *bar unreachable in principle* at 0.490; GBT gives 0.558. The
defensible claim is that **the ceiling sits essentially on the bar under
maximally optimistic conditions** — and since reality adds co-registration
error, endmember variability, shadow, atmospheric residual and cross-city
transfer, the achievable value is far below.

Observed real values corroborate this: **0.35–0.41 within-AOI, 0.08–0.09
cross-city** — exactly where one lands after subtracting those effects from a
0.49 ceiling.

### The constructive result

Same simulation, different targets:

| target | ceiling R² |
|---|---|
| **built** (fabric + institutional) | **0.490** |
| **impervious** (built + paved) | **0.822** |
| impervious + bare (all hard surface) | 0.964 |
| vegetation | 0.974 |
| water | 0.965 |

**The split is impossible; the union is recoverable.** Merging `built` and
`paved` raises the ceiling from 0.49 to 0.82 because the 1.70° confusion
becomes internal to the class and no longer needs resolving. The residual cost
(0.964 → 0.822) is separating impervious from bare at 3.45° — which is exactly
the WorldCover Africa failure mode the architecture already cites (47.1%
built-up user's accuracy, bare compacted earth called built).

### 3.1 The new weakest boundary, measured directly [E]

Reading the 0.964-vs-0.822 gap as evidence about impervious-vs-bare is an
*inference from two numbers*, not a measurement of that split. Because it was
about to be used to support a strong claim, it was measured directly
(`ceiling_impervious_bare.py`), with the decision rule fixed in advance:
below 0.50 → unidentifiable in principle, the same claim as built/paved; at or
above 0.70 → the weakest remaining boundary, recoverable but warranting its own
confidence marker; between → indeterminate.

Control passed first (vegetation R² = 0.974).

| scene | bare mean | R² @ 0.005 (ridge / gbt) | R² @ 0.010 | R² @ 0.020 |
|---|---|---|---|---|
| **realistic (primary)** | 0.294 | **0.822 / 0.867** | 0.615 | 0.333 |
| pairwise impervious+bare | 0.496 | 0.859 / 0.923 | 0.753 | 0.631 |
| bare-dominated (arid) | 0.676 | **0.737 / 0.813** | 0.477 | 0.233 |

**Verdict: the weakest remaining boundary — recoverable, needs a confidence
marker. NOT unidentifiable.** At documented S2 noise the split clears 0.70 even
in the bare-dominated arid stress case. Against built/paved's 0.490 at the same
noise, these are categorically different situations, and the "no remediation
ever" framing that applies to built/paved **does not** apply here.

Two corrections to expectations stated before the run:

- The pairwise scene was pre-registered as *"strictly harder than any real
  scene, a conservative lower bound."* It scored **higher** (0.859 vs 0.822) —
  removing vegetation and water removed variance sources rather than adding
  difficulty. The stated expectation was wrong.
- **The real sensitivity is to radiometric noise, not to bare dominance.** At
  2× noise the arid scene falls to 0.477, into unidentifiable territory. So the
  earned claim is conditional: *recoverable at documented radiometry, degrading
  sharply if radiometric quality drops* — not a blanket verdict either way.

---

## Part 4 — Consequences for settled decisions

### 4.1 `02_ARCHITECTURE.md:161-164` is falsified [E]

> "**The classes are no longer sub-pixel.** A roof is 3–6 m, a courtyard often
> 5–15 m — comparable to or larger than a 10 m cell."

A 3–6 m roof is *smaller* than a 10 m cell; the sentence concedes the problem
and concludes the opposite. Measured square-equivalents: Khayelitsha 6.9 m,
Dharavi 10.6 m, formal 12.4 m. And "comparable to 10 m" is not sufficient — the
formal suburbs' 12.4 m buildings still yield only 4.97% pure pixels, because
comparable-to-a-cell plus arbitrary grid phase means almost no cell falls fully
inside.

**This claim is load-bearing for the section's conclusion and must be
corrected.**

### 4.2 `02_ARCHITECTURE.md:169-172` does not cover the observed failure [E]

> "Misallocation between `built` and `paved` leaves `impervious_total`
> unchanged — the flood model, the primary consumer, is unaffected."

Valid for a *swap* between two classes, which cancels in the sum. The measured
failure is not a swap. `test_endmember_sensitivity.py` unmixed the same AOI and
composite twice, changing only the `built` endmember between two defensible
choices:

| AOI | built Δ | paved Δ | **impervious Δ** | **relative** |
|---|---|---|---|---|
| Dharavi | +0.1342 | +0.1330 | **+0.2672** | **+81.6%** |
| Khayelitsha | +0.1845 | −0.3126 | **−0.1281** | **−27.1%** |
| CT formal | −0.0085 | +0.0293 | **+0.0208** | **+16.2%** |

In Dharavi both fractions rose and **compounded**; nothing cancelled. The
direction is not even consistent across AOIs, so no calibration constant can
correct it.

A second finding from the same test: separation from the `paved` endmember is
**4.69°** for the institutional `built` candidate but **1.66°** for the
realistic informal one. **Using the institutional endmember manufactures
separability that does not physically exist** — the current spec would produce
a confident-looking split that is an artifact.

### 4.3 Decision 11 is directionally right and under-stated [R]

Decision 11 already calls `built`/`paved` "the weakest boundary of the five"
and requires its own confidence marker. This investigation quantifies how weak:
**1.70°, at 2.4× the noise floor**. That is not a low-confidence measurement —
it is an unidentifiable one.

Decision 11's other claim — "formal vs. informal is morphological, not
spectral" — was **not** tested here and remains plausible. What was tested and
failed is the weaker proposition that *per-pixel raster texture at 10 m* can
substitute for vector morphology. Vector-derived morphology over aggregation
units (items 22–23) is untouched and still standing.

---

## Part 5 — Proposed architecture

### 5.1 Retire the `built`/`paved` split as a measured product

State it as a **non-goal with a measured justification**, not a failure to be
engineered around. The ceiling number is the justification.

### 5.2 Invert where each quantity is estimated

Decision 11 measures `built` and `paved` and derives `impervious_total`. The
measurements say reverse it:

| fraction | source | ceiling | rationale |
|---|---|---|---|
| **built** | **vector footprints, directly** | n/a | Open Buildings coverage *is* a built estimate — VHR-derived and S2-independent. It was the regression *label* throughout. Predicting it from spectra re-derives, badly, what the vector layer already supplies well. |
| **impervious_total** | spectral regression | 0.822 | What the flood model actually consumes (`02_ARCHITECTURE.md:171`, `:393`; item 26) |
| **paved** | `impervious_total − built`, derived | — | Emitted with explicit uncertainty; **never** presented as measured |
| **vegetation** | spectral regression | 0.974 | Well separated (23–26°) |
| **water** | spectral regression | 0.965 | Well separated (43–47°) |
| **bare** | residual | — | Absorbs the impervious/bare confusion, which is where it belongs |

This preserves Decision 11's governing principle — *measure disjoint things,
derive overlapping ones* — while correcting which quantity is measured and
which derived.

### 5.3 What this costs downstream

- **Flood risk** — unaffected. `02_ARCHITECTURE.md:393` lists its input as
  `impervious_total` + vector conduits; item 26 has susceptibility consuming
  `impervious_total` rather than a discrete class.
- **Morphological characterisation** — unaffected. Item 23 states density
  metrics separate formal from informal *without any spectral input*.
- **Change over time** — improved. A stable estimator of a recoverable quantity
  gives more defensible deltas than an unstable estimator of an unrecoverable
  one.
- **Anything needing roofing material per building** — was never deliverable
  from this data and should be stated as out of scope.

---

## Part 6 — Open, untested, and honest gaps

1. **The 0.822 impervious ceiling is a simulation result, not an achieved
   one.** [R] Testing it on real data requires a real impervious label. The only
   available paved source (OSM unroofed polygons) covers **0.23–1.82%** of
   these AOIs against a built mean of 19–30% — too sparse to move the target.
   **This is the single most important unfinished piece**, and it is a
   data-sourcing problem rather than a method problem. Concretely it means
   VHR-derived or hand-annotated paved labels on a sample of these AOIs.

2. **The multi-scale aggregation sweep is incomplete.** [E] Directions A, C and
   D were completed at 10 m (method 7 above), but the 20/30/60/90 m aggregation
   arm stalled on Earth Engine for the largest AOI and was stopped. Its
   motivating hypothesis had already been falsified by self-test, so this is a
   low-value gap — but the empirical scale curve on real data remains
   unmeasured, and a coarser-cell product is the one reformulation this
   investigation never got a real-data number for.

3. **Vector morphology over aggregation units** (items 22–23) is untested by
   this investigation and remains the most plausible route to
   formal/informal characterisation.

4. **Higher-resolution imagery** would dissolve the problem but is not
   uniformly available: NICFI Planet basemaps (~4.8 m) cover roughly 30°N–30°S,
   which includes Dharavi, Lagos, Accra, Nairobi and Jakarta but **not** Cape
   Town at −34°. Mixed resolution across cities would break comparability.

5. **Literature position.** [S] The field's method for this exact problem is
   synthetically-mixed-spectra regression (Okujeni et al.), which
   **presupposes a library of pure spectra** — precisely what methods 1–3
   proved unavailable here. It is demonstrated on Berlin, Munich and Brussels:
   formal European fabric. No published product (WorldCover, Dynamic World,
   GHS-BUILT-S) ships a paved/roofing split at 10 m. GHS-BUILT-S itself never
   attempted spectral-alone extraction — it uses PanTex texture and
   morphological decomposition from the start.

---

## Appendix — Reproduction

| Script | Purpose |
|---|---|
| `diagnose_open_buildings_aoi.py` | Staged footprint survival, any AOI |
| `sweep_open_buildings_params.py` | Buffer × area-bar sensitivity (27 cells) |
| `diagnose_pure_pixels.py` | Pure-pixel counts on the real S2 grid |
| `diagnose_pure_pixels_paved.py` | Same for unroofed OSM polygons |
| `test_endmember_sensitivity.py` | Does endmember error reach `impervious_total` |
| `test_b_decomposition.py` | Is informal roofing a material or A+shadow |
| `extract_endmembers_vca.py` | VCA / N-FINDR extraction |
| `extract_endmembers_sisal.py` | Minimum-volume simplex |
| `regress_built_fraction.py` | Per-pixel spectral regression |
| `regress_built_fraction_spatial.py` | + texture + temporal variance |
| `regress_scale_sweep.py` | Scale sweep, PanTex, SAR, combined label |
| `ceiling_built_fraction.py` | **The ceiling computation** |
| `ceiling_impervious_bare.py` | Dedicated ceiling for the impervious/bare split |
| `measure_rare_endmembers.py` | Rare-fraction endmembers at verified sites (Part 8) |
| `ceiling_rare_fractions.py` | Ceilings for solar, snow_ice, mixed_water_vegetation (Part 8) |

Every script carries its pre-registered thresholds as module constants fixed
before results existed, and documents any deviation inline.

### Recorded deviations

- **SISAL λ** pre-committed at 10.0; the solver failed its synthetic self-test
  there (35.8° recovery). Recalibrated to 1e4 against **synthetic ground truth
  only, before any real-data result was inspected** (1.22° recovery). Solver
  calibration, not outcome fitting.
- **Texture self-test** bar pre-committed at R² ≥ 0.90; observed 0.851. A
  window sweep showed the construction's own ceiling is ~0.85
  (`[3]`=0.803, `[9]`=0.802, `[3,9]`=0.848, `[15]`=0.699, `[3,9,15]`=0.853), so
  0.90 was unreachable by construction. Proceeded with the deviation on record.
- **Excluded B-decomposition cell.** The CT-formal / SCL-shadow nnls cell
  (residual 2.66%) was excluded because its coefficients (0.522, 1.104) sum to
  1.63 and therefore **violate the convexity constraint the hypothesis
  `B = α·A + (1−α)·S` requires** — it is not a mixture. Excluded on that ground
  alone, *not* because it disagreed with the convex fit, which gave 8.48% and
  indeterminate on identical inputs.

---

## Part 7 — Item 21 Phase 0: a real impervious label from VHR [E]

The 0.822 `impervious_total` ceiling in Part 3 is simulated. Testing it needs a
real impervious label; OSM unroofed polygons cover only 0.23–1.82% of the pilot
AOIs, which is why Direction C returned null. This part builds the label from
centimetre-scale UAV imagery and runs the test.

### 7.1 Source, verified live

`03_EVIDENCE.md` C.1's record was re-checked against the OpenAerialMap API on
2026-09-09 rather than trusted. All three settlements still resolve
(Makoko 3 scenes, Old Fadama 7, Kibera 3). Selected:

> **Oldfadama Agbogloshie_combined_high_compression**, Accra
> acquired 2024-08-26 · GSD 0.049998 m · 145 MB · EPSG:32630
> 32,281 × 25,811 · 3-band uint8 RGB · bbox −0.225852, 5.541892, −0.214147, 5.556530

Verified on open: CRS, bands, dtype and bounds match the API record. ~36% of the
rectangle is nodata (irregular mosaic footprint). **RGB only — no NIR**, so
vegetation separation uses green-excess rather than NDVI.

**Temporal matching:** the S2 composite was rebuilt over 2024-06-01 → 2024-11-30
(13 images) to bracket the UAV date. Reusing the 2026 composite would have put a
two-year gap between label and imagery in a settlement that changes fast.

### 7.2 The label, and its accuracy

Model-generated, not hand-digitised: a random forest on colour + texture +
structure-tensor coherence at 20 cm, trained on **125 patches of 5 m × 5 m that
were each visually assigned by inspecting the rendered imagery**. Classes: roof,
hard_unroofed, vegetation, bare, water; `impervious = roof + hard_unroofed`.
Roof and hard are stored separately so the built/paved split can be checked
later at no cost now.

Accuracy is measured on a **patch-level** held-out split, never pixel-level —
pixels inside one 5 m patch are near-identical and a random pixel split would
report ~99% and mean nothing.

| | value |
|---|---|
| five-class accuracy (held-out patches) | **0.547** |
| **impervious vs not** | **0.711** |
| impervious precision / recall | **0.629 / 0.863** |

**A first labelling pass was wrong and was corrected.** At 1× zoom, bare recall
came out at 0.29 with 2,412 of 4,375 bare pixels predicted roof. Re-inspecting
at 2× showed the *classifier* was frequently right and the *labels* wrong —
patches 14 and 63 are flat roofs with visible seams, 50 and 55 are water with
floating rubbish. All patches were re-assigned at 2×, ambiguous ones discarded.

**Why accuracy plateaus here is physical, not a modelling artifact.**
Agbogbloshie is one of the world's largest e-waste and scrap sites: its "bare
ground" is largely covered in sheet metal and plastic that is genuinely
near-identical to corrugated roofing at any resolution. Note that roof↔hard
confusion is *internal to impervious* and harmless to the target; the damage is
bare↔roof.

### 7.3 Label geometry and distribution

**13,090 usable 10 m cells** (≥60% valid UAV coverage) of 21,780 on the real S2
grid `EPSG:32630`, transform `[10, 0, 699960, 0, -10, 700020]`. UAV and S2 share
the UTM zone, so the label needs no reprojection.

| statistic | impervious fraction |
|---|---|
| mean / sd | 0.810 / 0.279 |
| p5 / p25 / p50 / p75 / p95 | 0.072 / 0.775 / 0.942 / 0.985 / 1.000 |
| exactly 0 / exactly 1 | 2.6% / 4.2% |

Not degenerate — but **heavily saturated**: half the cells exceed 0.94. That is
partly Old Fadama genuinely being wall-to-wall dense and partly the classifier's
known over-calling (precision 0.629). Either way the target has little dynamic
range, and R² is variance-normalised, so this site is a hard place to score well
even with a good model.

### 7.4 Co-registration — measured, not assumed

At 5 cm versus 10 m, a one-cell misalignment is 200 UAV pixels and would
decorrelate label from imagery. Cross-correlating the aggregated label against
S2 visible brightness over ±4 cells:

> best |corr| = **0.480** at shift **(0, 0)** — aligned at 10 m, no correction needed.

The 0.48 correlation between a VHR-derived label and raw S2 brightness is itself
independent evidence of real signal.

### 7.5 The regression, against the pre-registered bar

Spatially blocked 200 m checkerboard split (6,774 train / 6,316 test) — not
random, per A.13.

| model | R² | MAE |
|---|---|---|
| ridge (pre-registered primary) | **0.363** | 0.1571 |
| gradient boosting | **0.537** | 0.1167 |
| baseline (predict train mean) | — | 0.2020 |

**Pre-registered verdict on the primary model: R² = 0.363 → DOES NOT WORK at
10 m per-pixel** (bar: ≥0.60 works, 0.50–0.60 caveat, <0.50 fails).

**This miss is confounded, exactly as stated before the run.** The label's own
binary accuracy is 0.711 and the target is saturated, so the measured R² is a
**lower bound**: a pass would have been strong evidence, a miss cannot separate
"reflectance does not predict impervious" from "the label is too noisy and too
saturated to tell." It does **not** settle the question.

Two things point the other way and are worth carrying:

- **Gradient boosting reaches 0.537**, inside the caveat band. In every earlier
  test in this investigation GBT never beat ridge; here it beats it by 0.17,
  which suggests a genuinely nonlinear reflectance→impervious relationship
  rather than an absent one.
- **MAE 0.1167 against a 0.2020 baseline** is a 42% improvement on predicting
  the mean, and the co-registration correlation is 0.48. There is real signal.

### 7.6 What would actually close this

Not more modelling on this scene. Two specific data needs:

1. **A site without the scrap/roof ambiguity.** Agbogbloshie is pathological for
   this label. Makoko (5.4 cm, Lagos) and Kibera (30.5 cm, Nairobi) are both
   verified live and neither is an e-waste site.
2. **A site with dynamic range.** A median impervious fraction of 0.94 leaves
   almost nothing to explain. A mixed formal/informal extent would give the
   target real variance.

Phase 0 delivers a working, verified end-to-end pipeline — source verification,
visual labelling, classifier, S2-grid aggregation, measured co-registration and
a blocked-split regression — and a label that is **not yet good enough to test
the 0.822 ceiling**. That is a data-sourcing outcome, not a method failure.

---

## Part 8 — Ceiling checks for the three rare fractions [E]

*Added 2026-10-28 (Phase 1b, branch `build/ceilings`). Simulated upper bounds;
`validation_status: experimental`. Nothing was labelled.*

Decision 11 (amended 2026-09-24) added `snow_ice`, `solar` and
`mixed_water_vegetation`, each with its own producer and validation case.
Nobody had asked whether 10 m / 6-band Sentinel-2 can recover them at all.
Part 3 showed that question has a computable answer, and that a split which
looks reasonable (built/paved) can be unidentifiable. This part asks it of the
three new fractions before anyone spends labelling time on them.

### 8.1 Rule and method, pre-registered

Committed in `a0292b4` **before any endmember spectrum was read**;
spectra in `a0753fe`, results in `2715fc8`.

| | |
|---|---|
| **Rule** (ridge, noise 0.005, realistic scene) | R² ≥ 0.70 → **label it**; R² < 0.50 → **don't label it**; between → **indeterminate** |
| **Method** | Part 3's, unchanged: Dirichlet mixtures of measured endmembers, exactly linear, Gaussian noise, 40,000 px, seed 42, 50/50 split, ridge (primary) and GBT with `regress_built_fraction.py`'s settings. The six Khayelitsha endmembers and their mixture weights are unchanged |
| **Rare class** | A seventh component at α = 0.35 (paved's weight), whose spectrum is one of that fraction's measured site endmembers, chosen per pixel. Target = its share (realised mean 0.127, sd 0.171) |
| **Noise** | 0.005 primary; 0.010 and 0.020 reported |
| **Controls, first** | (1) vegetation must reproduce **0.974** and (2) built **0.490**, both within ±0.005. These prove the restated code is the Part 3 method. (3) In each rare scene, vegetation must stay ≥ 0.90 |
| **Solar share** | Solar share ~ U(0, s_max), s_max ∈ {0.05, 0.10, 0.25, 0.50, 1.00}. **Rooftop sub-verdict** at s_max = 0.25 with the rooftop endmember: a 10–20-panel array is 20–40 m², at most 0.2–0.4 of a 100 m² cell, and arrays straddle cells |

**Controls passed: vegetation 0.974, built 0.490** (GBT 0.976 / 0.558, also
identical to Part 3).

### 8.2 Sites, verified live 2026-10-28

Every site was located by a **mapped reference, never by a spectral
threshold**. Selecting snow by NDSI, say, would hand the ceiling an endmember
that is separable by construction. Pure pixels: the reference eroded by 10 m
(≥ the 7.07 m half-diagonal of a pixel), tested at the pixel centre; raster
references eroded by one pixel. Composite: `S2_SR_HARMONIZED`,
`CLOUDY_PIXEL_PERCENTAGE` < 20, SCL-masked (`mask_s2_clouds`, which keeps SCL
11 snow), median. Record: `experiments/rare_fraction_ceilings/site_verification.json`
and `endmembers.json`.

| Fraction | Site | Reference (verified live) | Window | Images | Pure px |
|---|---|---|---|---:|---:|
| solar | Bhadla, Rajasthan | OSM relation 11250846, *Bhadla Solar Park*, 2245 MW | 2025-01 → 03 | 30 | 463,984 |
| solar | Benban, Egypt | OSM way 694477324, *محطة بنبان*, 1465 MW | 2025-01 → 03 | 25 | 366,160 |
| solar | Witznitz, Germany | OSM relation 15093634, *Energiepark Witznitz*, 650 MW | 2025-06 → 08 | 23 | 33,159 |
| solar (rooftop) | Venlo, NL | 13 OSM `generator:source=solar` + `location=roof` polygons | 2025-06 → 08 | 31 | 1,264 |
| snow_ice | Aletsch, CH | GLIMS (415 outlines incl. *Grosser Aletschgletscher*) ∩ WorldCover 70 | 2025-08 → 09 | 12 | 645,022 |
| snow_ice | Quelccaya, Peru | GLIMS (147 outlines) ∩ WorldCover 70 | 2025-06 → 09 | 44 | 357,218 |
| mixed_w_v (mangrove) | Sundarbans, BD | GMW v3 2020 (35 polygons) ∩ GLWD v2 28 ∩ WorldCover 95 | 2025-01 → 03 | 12 | 844,639 |
| mixed_w_v (marsh) | Everglades, US | GLWD v2 non-forested wetland ∩ WorldCover 90 | 2025-08 → 10 | 11 ‡ | 1,082,281 |
| mixed_w_v (marsh) | Sudd, South Sudan | GLWD v2 non-forested wetland ∩ WorldCover 90 | 2025-10 → 12 | 22 | 279,518 |
| mixed_w_v (tidal flat) | Neuwerk Watt, DE | Murray global intertidal 2014–2016, tidal flat | 2025-05 → 08 | 9 | 475,838 |

‡ Fell back to the pre-registered 50% cloud filter (wet season).
**Not measured:** water hyacinth, a Decision 11 sub-type. No independent map of
it was found, so nothing was substituted.

**Recorded deviation.** The GLWD marsh class list first omitted non-forested
peatland (23/25/27). The `--verify` pass found **0 pure pixels** at the
Everglades, because GLWD v2 maps that sawgrass marsh as class 27 *(tropical
peatland, non-forested)* while WorldCover calls 98% of the box herbaceous
wetland. The three classes were added from class histograms alone, before any
spectrum was read.

### 8.3 Spectral angles

Same format as Part 2. Rare classes are the mean of their sites. The base
block is Part 2's table unchanged.

| | built_inst | built_fabric | paved | bare | veg | water | solar | snow_ice | mixed_w_v |
|---|---|---|---|---|---|---|---|---|---|
| **built_inst** | 0.00 | 3.35 | 4.70 | 3.86 | 26.19 | 42.76 | 10.77 | 40.27 | 24.91 |
| **built_fabric** | 3.35 | 0.00 | 1.70 | 3.65 | 24.51 | 45.90 | 8.07 | 43.32 | 24.50 |
| **paved** | 4.70 | 1.70 | 0.00 | 3.45 | 23.15 | 46.86 | **7.16** | 44.01 | 23.41 |
| **bare** | 3.86 | 3.65 | 3.45 | 0.00 | 23.38 | 44.04 | 9.71 | 40.75 | 22.05 |
| veg | 26.19 | 24.51 | 23.15 | 23.38 | 0.00 | 60.66 | 24.07 | 53.33 | **10.70** |
| water | 42.76 | 45.90 | 46.86 | 44.04 | 60.66 | 0.00 | 50.81 | **14.30** | 51.86 |
| **solar** | 10.77 | 8.07 | 7.16 | 9.71 | 24.07 | 50.81 | 0.00 | 48.97 | 26.13 |
| **snow_ice** | 40.27 | 43.32 | 44.01 | 40.75 | 53.33 | 14.30 | 48.97 | 0.00 | 43.64 |
| **mixed_w_v** | 24.91 | 24.50 | 23.41 | 22.05 | 10.70 | 51.86 | 26.13 | 43.64 | 0.00 |

The class means hide most of the story, so per site:

| Site | Nearest base (°) | Surround (°) | Convex-hull residual (× noise) | Best convex fit |
|---|---|---|---:|---|
| bhadla | paved 6.08 | 7.61 | 5.3 | 0.62 paved + 0.36 bare |
| benban | paved 5.24 | **3.02** | 14.4 | 1.00 built_inst |
| witznitz | paved 23.38 | 34.79 | 12.5 | 0.49 veg + 0.44 built_fabric |
| rooftop_venlo | built_inst 8.53 | 16.36 | 5.0 | 0.69 paved + 0.19 built_inst |
| aletsch | water 13.72 | 42.51 | 47.2 | — (outside, far) |
| quelccaya | water 14.67 | 44.56 | 89.4 | — (outside, far) |
| sundarbans | veg 14.12 | 37.52 | 6.0 | 0.84 veg + 0.17 water |
| everglades | veg 11.51 | 14.79 | 4.5 | 0.65 veg + 0.35 water |
| sudd | **veg 4.35** | **0.84** | **2.3** | **0.99 veg** |
| wadden_neuwerk | water 8.48 | 14.79 | 11.2 | 0.81 water + 0.20 veg |

"Convex-hull residual" is what is left after the best non-negative,
sum-to-one fit by the six base endmembers, in units of the noise vector
(0.005·√6). A spectrum near the hull is a mixture of fractions that already
exist, however large its angles look. The pre-run self-test confirmed the
ceiling cannot recover such a class: a synthetic half-vegetation,
half-water class scores below 0.50.

**Within-class spread** (largest angle between two sites of one class):
solar **21.5°**, snow_ice 1.5°, mixed_water_vegetation **54.4°**.

### 8.4 Ceilings

| Fraction | R² @ 0.005 (ridge / gbt) | MAE @ 0.005 | R² @ 0.010 | R² @ 0.020 | vegetation R² in the scene |
|---|---|---|---|---|---|
| **snow_ice** | **0.925** / 0.969 | 0.032 | 0.910 | 0.892 | 0.972 |
| **solar** | **0.677** / 0.839 | 0.072 | 0.516 | 0.290 | 0.967 |
| **mixed_water_vegetation** | **0.368** / 0.610 | 0.100 | 0.331 | 0.297 | **0.634** — control 3 fails |

Stress scene, all three rare fractions at once (noise 0.005, reported
only): snow_ice 0.909, solar 0.589, mixed_water_vegetation 0.304 (ridge).

### 8.5 Solar against panel share

Solar share ~ U(0, s_max) in every pixel, all four solar endmembers.

| s_max | R² @ 0.005 (ridge / gbt) | R² @ 0.010 | R² @ 0.020 | MAE @ 0.005 |
|---|---|---|---|---|
| 0.05 | 0.027 / 0.024 | 0.009 | 0.003 | 0.012 |
| 0.10 | 0.092 / 0.117 | 0.034 | 0.011 | 0.024 |
| **0.25** | **0.311** / 0.431 | 0.166 | 0.067 | 0.050 |
| 0.50 | 0.546 / 0.722 | 0.399 | 0.218 | 0.080 |
| 1.00 | 0.794 / 0.925 | 0.699 | 0.516 | 0.105 |

**Rooftop sub-verdict** (Venlo rooftop endmember, s_max = 0.25, noise 0.005):
ridge **0.436**, GBT 0.448 → **don't label it**.

Solar becomes recoverable only when panels fill most of a cell. Below a
quarter of a cell it is essentially invisible: at s_max = 0.10 the MAE
(0.024) is half the mean share itself.

### 8.6 Verdicts

| Fraction | Pre-registered result | Verdict |
|---|---|---|
| **snow_ice** | 0.925 ≥ 0.70 | **LABEL IT.** Recoverable, and the most robust result in this document: still 0.892 at four times documented noise. Snow sits 14° from water and 40–54° from everything else |
| **solar** | 0.677, between 0.50 and 0.70 | **INDETERMINATE.** Neither framing is earned. Rooftop solar at realistic panel shares: **DON'T LABEL IT** (0.436) |
| **mixed_water_vegetation** | 0.368, but **control 3 failed** | **INDETERMINATE: the pre-registered rule issued no verdict.** The evidence below points to *don't label it as one fraction*, but the rule did not reach that, and this document does not round it up |

**On mixed_water_vegetation, stated plainly.** Control 3 required vegetation
to stay ≥ 0.90 in every rare scene. It was written to catch a *broken
simulation*. It fired here for a different reason: the scene is the same code
that passed controls 1 and 2, and vegetation fell to 0.634 because the
mangrove and marsh spectra are nearly vegetation (Sudd: 4.35° from
vegetation, 0.84° from its own surround, 2.3× noise from the hull). The class
does not just fail to be recovered; **adding it damages vegetation, which is
otherwise the best-recovered fraction in the architecture**. That is a design
flaw in the pre-registration, which conflated two failure modes in one
control. It is recorded as one and not repaired after the fact. The numbers
are: target 0.368 (below 0.50), vegetation 0.634.

### 8.7 Post-hoc, not pre-registered — per site

Written after 8.4–8.6, **carrying no verdict**
(`experiments/rare_fraction_ceilings/posthoc_per_site.py`). The same scene,
with one site endmember at a time:

| Site | R² @ 0.005 (ridge / gbt) | @ 0.010 | @ 0.020 | vegetation R² |
|---|---|---|---|---|
| solar · bhadla | 0.763 / 0.850 | 0.528 | 0.272 | 0.971 |
| solar · benban | 0.793 / 0.915 | 0.694 | 0.581 | 0.968 |
| solar · witznitz | 0.944 / 0.950 | 0.848 | 0.645 | 0.972 |
| solar · rooftop_venlo | 0.839 / 0.856 | 0.580 | 0.283 | 0.971 |
| mixed_w_v · sundarbans | 0.588 / 0.831 | 0.488 | 0.365 | 0.619 |
| mixed_w_v · everglades | 0.450 / 0.786 | 0.360 | 0.307 | 0.844 |
| mixed_w_v · sudd | 0.322 / 0.428 | 0.287 | 0.243 | 0.504 |
| mixed_w_v · wadden (tidal) | 0.729 / 0.894 | 0.694 | 0.639 | 0.965 |

Two readings, offered as hypotheses for the next decision and not as results:

- **Every solar site alone clears 0.70; pooled, they fall to 0.677.** The
  cost is the 21.5° between farms. Desert farms look like paved/bare; the
  Witznitz farm, with grass between rows, sits between vegetation and roof.
  "Solar" at 10 m is panels *plus whatever is under and between them*, and
  that varies by site more than panels do.
- **`mixed_water_vegetation` behaves as two classes.** Tidal flat alone is
  recoverable (0.729) and leaves vegetation intact. Mangrove and marsh are
  not recoverable (0.32–0.59) and pull vegetation down to 0.50–0.84. The class
  is a hydrological category (Decision 11 feeds it to item 26 by sub-type),
  not a spectral one.

### 8.8 What this does not show

- **Each ceiling is an upper bound.** "Label it" for `snow_ice` means
  physics does not rule it out, not that a producer will work.
- **Snow's real confuser is cloud,** which is occlusion and not in the base
  set. Sen2Cor's SCL can call bright snow cloud. The ceiling does not test
  that, and it is the producer's actual risk.
- **Absolute noise understates noise on bright surfaces** (radiometric error
  grows with signal), which inflates `snow_ice`. Not guarded.
- **The base set is Khayelitsha, not each site's surroundings.** Benban
  sits **3.02°** from its own desert surround, closer than to any base
  endmember. Against local sand, the utility-solar ceiling would be lower
  than 8.4 reports.
- **Farm pixels are panels plus inter-row ground,** and OSM rooftop polygons
  may trace the roof rather than the panels. Neither is a pure panel
  spectrum.
- **Within-class variability is modelled as a few discrete endmembers** the
  regressor sees, the same generosity Part 3 gave built_fabric/inst. Real
  variability is continuous and only lowers these numbers.
- **Tidal-flat composites mix tide states,** and Murray is 2014–2016.

**Reproduction:** `python measure_rare_endmembers.py --verify`, then
`python measure_rare_endmembers.py` (Earth Engine + Overpass), then
`python ceiling_rare_fractions.py` (offline, about 3 min). Tests:
`tests/test_ceiling_rare_fractions.py`.
