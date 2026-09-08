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
