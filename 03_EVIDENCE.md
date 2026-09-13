# GeoWatch — Evidence Base

**Everything checked, measured, researched, and ruled out.**

This document exists so nothing gets re-investigated. When a question arises that
was already settled, it should be answered from here rather than researched
again.

Confidence markers used throughout:
- **[E]** empirical — measured or executed first-hand
- **[S]** static — verified by code or artifact inspection
- **[R]** reasoned — inferred, not independently verified
- **[X]** external — from published literature or a third-party source

---

## PART A — Measured facts about the system

### A.1 Model behaviour [E]

Measured on `phase1_dharavi_20260820_125646` (291×257, 1 tile),
`phase1_dharavi_20260820_125809` (determinism control), and
`phase1_multitile_20260820_130117` (892×891, 4 tiles, ~75 km²).

**Per-class probability structure:**

| class | mean *p* | median *p* | argmax % | mean *p* when not winner | rank-2 rate |
|---|---:|---:|---:|---:|---:|
| **paved_road** | **0.3757** | **0.3244** | 42.45% | **0.1420** | **42.70%** |
| dense_vegetation | 0.2099 | 0.0041 | 22.43% | 0.0255 | 5.11% |
| sparse_informal_roofing | 0.1528 | 0.0053 | 13.66% | 0.0566 | 15.44% |
| dense_informal_roofing | 0.1317 | 0.0128 | 11.36% | 0.0681 | 20.18% |
| active_construction | 0.0606 | 0.0052 | 4.98% | 0.0321 | 7.81% |
| vegetation_clearing | 0.0426 | 0.0046 | 2.83% | 0.0264 | 6.70% |
| standing_water | 0.0267 | 0.0014 | 2.29% | 0.0070 | 2.07% |

**The diagnostic column is median *p*.** `dense_vegetation` has a comparable
*mean* (0.2099) but a median of 0.0041 — confident where it belongs, silent
elsewhere. `paved_road`'s median is 25–230× higher than every other class's and
close to its own mean: **uniformly elevated, not concentrated.**

- `paved_road` is top-2 partner for **all six** other classes (55.4%–80.9%)
- Top-2 for **85.1%** of all pixels; top-3 for 96.4%
- **42.45%** of raw argmax against **17.81%** of pixel supervision → **2.4×
  over-predicted**

*(Note: 42.45% is the value confirmed by the argmax column above, which sums
to exactly 100.00. An earlier "42.15%" figure appeared in two places in V1/V2
documents and has been corrected throughout to 42.45%.)*

**Eliminated as mechanisms:**
- *Final classifier layer* — bias spread 0.0617 across all seven; `paved_road`'s
  bias is not the highest; its weight-norm is the **lowest** (0.8548 vs up to
  0.9616)
- *Class weighting* — `paved_road` carries the **lowest** CE weight (0.1707).
  Weighted CE resamples class *c* by *w_c*, so a low weight *suppresses*. The
  weighting was fighting the over-prediction.

**Confirmed mechanism:** a diffuse learned prior traceable to sub-pixel label
geometry (see A.4).

### A.2 Unknown-pixel rate [E]

| Run | Array | total px | ==255 | Computation | Result |
|---|---|---:|---:|---|---:|
| dharavi_125646 | 257×291 | 74,787 | 19,252 | 100×19,252/74,787 | **25.74%** |
| dharavi_125809 | 257×291 | 74,787 | 19,252 | identical | **25.74%** |
| multitile | 891×892 | 794,772 | 228,785 | 100×228,785/794,772 | **28.79%** |

Denominator is `H*W` of the full mosaicked array, per `inference.py:308-312`.
Both Dharavi runs are **bit-identical**, independently confirming determinism.

**Note:** an earlier "25.73%" appeared four times in V1 and three in V2. It is
not derivable from the data — 100 × 19,252 / 74,787 = 25.742442. Corrected
throughout; the C11 delta corrected 24.45 → 25.74 = **+1.29 pp** (not +1.28).

*Caveat:* the 24.45% no-penalty baseline was not itself re-measured, so the delta
is corrected for internal consistency with two stated rounded values, not
independently verified.

**Superseded by Decision 14:** this section's "unknown" (CAAT-rejected pixels)
no longer exists as a concept under the fraction architecture. Retained here
as historical record of the old system's behaviour, not as a spec for the new
one. See `05_BUILD_MANUAL.md` Part 3, Decision 14, for the current
observability/coverage convention (known-pixel denominator; shadow,
cloud/nodata, and low-confidence unmixing reported as three separate fields).

### A.3 The "~50% unknown" figure — origin traced [E]

Not a transcription error. It describes a **superseded system state**.

1. `caat_diagnostic.py`'s docstring records the hypothesis: CAAT thresholds
   computed from isolated single-patch forward passes, while production uses
   sliding-window overlapping softmax-averaged inference, which systematically
   lowers confidence.
2. It refers throughout to *"the ~50% unknown rate"* as the condition diagnosed.
3. `recalibrate_caat.py`'s methodology string records the outcome: the new CAAT
   *"supersedes the original CAAT… see caat_diagnostic.py for the confirmed
   **+22pp unknown-rate gap** this was causing."*
4. `breakdown_unknown_class.py`'s docstring still cites "~50%" and was **never
   updated**.

**Measured confirmation** (current deployed CAAT, same tile):

| mode | stride | unknown | mean top-1 confidence |
|---|---:|---:|---:|
| production | 32 | 24.45% | **0.7264** |
| isolated | 64 | 11.33% | **0.8174** |

Sliding-window averaging lowers mean confidence by 0.091. **24.45% + 22 pp =
46.4% ≈ "~50%".** Arithmetic closes.

### A.4 Sub-pixel supervision geometry [E/S]

**Road widths from `generate_osm_road_masks.py`'s `HIGHWAY_WIDTH_M`:**

| class | width | px at 10 m |
|---|---:|---:|
| motorway | 12 m | 1.20 |
| trunk | 10 m | 1.00 |
| primary | 9 m | 0.90 |
| residential | 5 m | 0.50 |
| service | 4 m | 0.40 |

Only `motorway` exceeds one pixel. `trunk` lands exactly on one — and a feature
exactly one pixel wide is still mixed whenever it does not align to the grid.

Cape Town: **192 records, median mask area 23.5 px** — verified exactly.

**Water widths — the same pathology, independently:**

| class | width | px at 10 m |
|---|---:|---:|
| river | 15 m | 1.50 |
| tidal_channel | 10 m | 1.00 |
| canal | 8 m | 0.80 |
| stream | 3 m | 0.30 |
| drain | 2 m | 0.20 |
| ditch | 1.5 m | 0.15 |

### A.5 Supervision composition [E]

Pool: 33 files across the 11 training runs — 331 human annotations, 976
OSM-generated road, 101 OSM-generated water. Restricted to the 7 model classes:
**1,345 patches / 484,796 pixels.**

| class | patches | patch % | pixels | pixel % |
|---|---:|---:|---:|---:|
| paved_road | 987 | **73.38%** | 86,349 | **17.81%** |
| standing_water | 133 | 9.89% | 238,265 | **49.15%** |
| dense_vegetation | 94 | 6.99% | 82,695 | 17.06% |
| dense_informal_roofing | 53 | 3.94% | 43,230 | 8.92% |
| vegetation_clearing | 38 | 2.83% | 12,723 | 2.62% |
| active_construction | 25 | 1.86% | 14,360 | 2.96% |
| sparse_informal_roofing | 15 | 1.12% | 7,174 | 1.48% |

Machine-generated labels outnumber human **3.25×** (1,077 vs 331).

**On the "41%" figure:** it is obtained by *inverting the checkpoint's
`class_weights`* (→ 40.96%), not by counting. The measured by-patch figure for
this pool is **73.38%**. Pairing "41% by patch" with "17.8% by pixel" in a
summary understates patch dominance by nearly 2× while appearing to correct it.

**The 25/city cap does not explain the gap.** Direct reconstruction of the cap
gives 637 patches → 44.74%, against the checkpoint-implied 40.96%. And the
checkpoint records `n_train_patches = 1272` + `n_monitor_patches = 141` = 1,413,
matching neither the capped 637 nor the uncapped 1,345. **The real training pool
is not reconstructible from the files on disk.**

### A.6 Class weights [E]

All 21 values verified to 4 decimal places against the checkpoint.

| class | checkpoint | patch-derived | pixel-derived | pixel/actual |
|---|---:|---:|---:|---:|
| paved_road | **0.1707** | 0.0415 | **0.2394** | **1.40×** |
| standing_water | 0.4915 | 0.3077 | **0.0868** | **0.18×** |
| dense_informal_roofing | 0.6135 | 0.7723 | 0.4782 | 0.78× |
| dense_vegetation | 0.3646 | 0.4354 | 0.2500 | 0.69× |
| sparse_informal_roofing | 2.9653 | 2.7287 | 2.8814 | 0.97× |
| vegetation_clearing | 1.3479 | 1.0771 | 1.6247 | 1.21× |
| active_construction | 1.0466 | 1.6372 | 1.4395 | 1.38× |

**The patch/pixel mismatch makes `paved_road` over-prediction *less* bad.** Pixel
weighting would raise its weight 1.40× (0.1707 → 0.2394), pushing more
prediction. The damage lands on `standing_water` instead — inflated **5.7×**
relative to pixel weighting, because water is patch-rare but pixel-dominant
(large filled polygons vs thin road ribbons).

The two classes whose label *geometry* differs most are distorted in opposite
directions.

### A.7 Water-mask quality [E]

**`standing_water`'s 49.15% pixel dominance is NOT a generator artifact.**

| Source | annotations | total px | share |
|---|---:|---:|---:|
| Human | 32 | 206,512 | **86.7%** |
| OSM-generated | 101 | 31,753 | 13.3% |

Jakarta alone supplies 68.5% of all `standing_water` supervision, and a single
SAM segment covering 59.1% of its tile supplies 65% of that. **That segment was
verified spectrally as correct:** NDWI +0.425 inside vs −0.154 outside, NIR
0.0175 (textbook open-water absorption), 100.0% of masked pixels water-positive.
North Jakarta genuinely is mostly water.

Root cause is AOI selection plus pixel-weighted aggregation — the mirror image of
`paved_road` (many-and-thin vs few-and-huge).

**But a worse, previously unflagged problem: W1.** Only **48.7%** of
OSM-generated water pixels are spectrally water. Human annotations: **98.6%**
(197,637 / 200,428, verified to the pixel).

| city | % water-like | tile baseline |
|---|---:|---:|
| Guatemala | **0.6%** | 3.5% |
| Kigali | 3.1% | 0.5% |
| Dharavi | 4.5% | — |
| Nairobi | 10.1% | — |
| Cape Town | 10.8% | — |
| Dhaka | 53.0% | — |
| Jakarta | 74.7% | — |

Guatemala is **worse than random** against its own tile baseline.

Two causes: semantically, `way["waterway"]` is queried with **no filtering** — a
mapped drain is a *channel*, not water in it, and in dry cities it is dry on the
imagery date. Geometrically, W2 (§A.4).

### A.8 Segment ID divergence [E]

Fresh run: 36 segments (ids 0–35) vs 44 masks (ids 0–43). **11/36 = 30.6%**
disagree. Disagreeing ids are contiguous 25–35.

**The offset accumulates — it is not a constant shift:**

| ids | offset |
|---|---:|
| 25–28 | +1 |
| 29–31 | +2 |
| 32–35 | +3 |

Every disagreeing segment still matches *some* mask, so nothing is lost. But
cumulative drift is exactly what two divergent counters produce, whereas a
constant shift would suggest a single one-off skip. **A repair keyed to a
constant +1 would fix 25–28 and silently corrupt 29–35.**

Root cause confirmed at `pipeline.py:332-361` — `next_segment_id` increments over
`tile_segments` (post `w<8/h<8` filter); `next_mask_id` over all raw masks.

**Superseded by Decision 12:** SAM is deleted. This section is retained as the
historical record of why — C9, C28, C30 are deleted rather than fixed as a
direct consequence of this measurement.

### A.9 Multi-tile spatial failure [E]

4 tiles; `tile_dimensions` 892×891; `landcover.png` 892×891; **`primary_tile`
actually 512×512.** Segment bboxes reach x=891, y=890.

**102/116 segments (87.9%) fall outside `primary_tile`**, which covers 57.4% of
AOI width and 57.5% of height. No full-AOI RGB basemap is ever written.

The live frontend is immune — it never reads `primary_tile`. Any other consumer
is not.

### A.10 Palette drift [E]

**0 of 8** exact matches between `App.jsx` `CAT_COLORS` and `inference.py`
`CATEGORY_COLORS_RGB`, despite `inference.py:165-168` asserting they must match
exactly. Worst: `dense_vegetation`, Δ(34, 37, 75) — forest green in the
server-rendered PNG vs mint green in the legend beside it.

The deltas are small enough to read as opacity variation, which is what makes
misidentification easy.

*(The `unknown` row's backend value comes from `UNKNOWN_COLOR_RGB` at line 179,
just outside the cited range.)*

### A.11 Imperviousness deflation [E]

Emitted `impervious_fraction_pct = 41.68`
(25.97×1.0 + 9.58×0.9 + 11.81×0.6 = 41.678 — reproduced exactly).

Recomputed with a known-pixel denominator (55,535 of 74,787): **56.13**.

Ratio 1.346689, against 1/(1−0.2574) = 1.346620 — agreeing to four significant
figures, **not identically**. Both round to 1.347×.

*Note:* an earlier "56.12" was reproducible only by *rescaling* the emitted value
(41.678 / (1−0.2574) = 56.1244), not by recounting. The claim that the factor was
"exactly 1/(1−0.2574)" was therefore true by construction, not an independent
confirmation.

**Superseded by Decision 14:** the specific 25.74% "unknown" figure this
section is built on was a CAAT-era concept. The 1.35× denominator-choice
effect it demonstrates is why Decision 14 mandates a coverage field regardless
of which denominator convention is chosen — the underlying lesson survives
even though the specific number does not carry forward unchanged.

### A.12 Determinism [E]

Two identical-parameter runs: **0 of 74,787 differing pixels** in
`landcover_map_full.npy`, plus identical susceptibility scores, impervious
fraction, segment count, and exposure population (282,983).

This **isolates C27**: ward-screening non-reproducibility is the 90-second
wall-clock GEE timeout, not model nondeterminism.

### A.13 Ambiguity composition is AOI-dependent [E]

| AOI | roofing\|road | veg\|water | unknown |
|---|---:|---:|---:|
| Dharavi | 5.25 pp | 0.03 pp | 25.74% |
| Dharavi (rerun) | 5.25 pp | 0.03 pp | 25.74% |
| multi-tile (75 km²) | 2.42 pp | 0.89 pp | 28.79% |

The wider AOI contains more water, so the vegetation/water pair becomes
non-trivial where in Dharavi it is negligible. The roofing/road pair more than
halves. **Conclusions drawn from a single small AOI do not transfer cleanly.**

**Carries forward as a methodological caution for Decision 13's validation
pilot:** the same AOI-dependence risk applies to endmember extraction. The
2–3 city pilot required before full Part 4 build-out exists specifically to
catch this class of problem before it propagates into the unmixing solve.

---

### A.14 The classifier is RGB-only, on tile-relative values [E]

Two measured facts about what the production classifier actually consumes. Both
were established while verifying a *different* concern (a suspected 13-band →
6-band `conv1` slice with wrong indices), which does not exist — there is no
slicing code in the repository at all.

**1. Three bands reach the model, not six.**

`ingestion/resnet_model.py` loads `ResNet50_Weights.SENTINEL2_RGB_MOCO`:

| property | value |
|---|---|
| `in_chans` | **3** |
| `bands` | `['B4', 'B3', 'B2']` — Red, Green, Blue |
| checkpoint | `resnet50_sentinel2_rgb_moco-2b57ba8b.pth` |
| `conv1.weight`, fresh load | `(64, 3, 7, 7)` |
| `conv1.weight`, **deployed** checkpoint | `(64, 3, 7, 7)` |

NIR, SWIR1 and SWIR2 are exported into `raw.tif` and written to `.npy` by
`generate_tiles()`, then **discarded before inference**: `run_inference()` reads
the 8-bit RGB PNG produced by `generate_rgb_preview_tiles()`
(`inference.py:390`). Band *order* is correct — `['B4','B3','B2']` matches the
`[Red, Green, Blue]` stacking order — so nothing is transposed. The bands are
simply not there.

**2. The values are tile-relative, not absolute reflectance.**

The checkpoint's own documented transform is `Normalize(mean=[0], std=[10000])`
— Sentinel-2 DN ÷ 10,000, i.e. absolute surface reflectance. Measured, `raw.tif`
is *already* float reflectance on exactly that scale. But the model consumes a
**per-tile 2nd/98th percentile stretch** to uint8 ÷ 255 instead:

| AOI | raw reflectance (mean) | value fed to model | inflation |
|---|---:|---:|---:|
| Dharavi | 0.089 | **0.212** | 2.4× |
| Accra | 0.124 | **0.389** | 3.1× |
| Jakarta | 0.187 | 0.204 | 1.1× |
| Cape Town | 0.175 | 0.400 | 2.3× |

Both land in [0, 1], so nothing errors. But the stretch is computed **per tile**,
so the same physical surface produces different model input depending on what
else shares its tile — and the distortion is city-dependent, from 1.1× to 3.1×
across four AOIs.

*Not a train/serve skew.* Training and inference apply the identical transform
(`/255.0`, no mean/std — `inference.py:391` and the training notebook), which
independently re-confirms **C5**'s refutation. The concern is pretraining
transfer and **cross-city generalisation**, which is exactly what LOCO measures.

**What this qualifies.**

- **The 0.313 ± 0.056 LOCO baseline** is an RGB-only, tile-relative number. It
  is not a measurement of what this architecture can do with Sentinel-2's full
  6-band signal, and should not be quoted as one.
- **Every prior conclusion about spectral separability *in the classifier*** is
  bounded the same way — including the `paved_road` magnet-class behaviour
  (§01_DIAGNOSIS §6) and the failure of the paved/roofing separation loss. Those
  were observed in RGB.
- **Item 21 measured a different space.** Its 1.70° built/paved spectral angle,
  the ~0.7° noise floor, and the R² ceilings (built 0.490, `impervious_total`
  0.822, impervious+bare 0.964) were all computed in **6-band** space. **The
  classifier does not operate in that space.** Item 21's ceilings therefore
  neither predict nor are predicted by classifier performance — they describe
  the signal available to a 6-band solver, while the classifier sees three
  bands after a tile-relative rescaling. Conflating the two would overstate what
  either result says about the other.

*Enforced going forward:* `assert_encoder_band_contract()` runs at every
encoder construction and refuses a checkpoint whose band list, channel count or
ordering stops matching what the pipeline supplies — so a move to the 13-band
`SENTINEL2_ALL_MOCO` checkpoint must add a deliberate, verified channel
selection rather than silently working.

---

## PART B — OSM coverage baseline [E]

Measured across all 11 training AOIs. Lengths clipped to AOI before measuring,
geodesic.

| city | AOI km² | all km | km/km² | pedestrian km/km² |
|---|---:|---:|---:|---:|
| capetown | 23.04 | 572.2 | 24.83 | **8.35** |
| dharavi | 6.97 | 160.4 | 23.02 | 2.78 |
| dhaka | 13.55 | 285.1 | 21.04 | 2.27 |
| nairobi | 14.23 | 300.8 | 21.14 | 2.11 |
| kigali | 6.79 | 96.9 | 14.27 | 1.94 |
| guatemala | 19.07 | 503.5 | 26.40 | 1.83 |
| accra | 12.87 | 269.9 | 20.98 | 1.29 |
| hcmc | 120.96 | 3,013.8 | 24.92 | 0.90 |
| nusantara | 40.61 | 176.5 | 4.35 | 0.63 |
| jakarta | 42.84 | 355.8 | 8.31 | 0.39 |
| lagos | 17.13 | 162.4 | 9.48 | **0.19** |

**Pedestrian-path density spans 44×. Total network density spans only 6×.
Arterial coverage is near-universal.** The variance is concentrated almost
entirely in the pedestrian layer — exactly the layer informal-settlement routing
needs.

### The correction this forces

**Dharavi (2.78) and Kibera/Nairobi (2.11) are NOT the well-mapped ceiling.**
Khayelitsha (Cape Town) is **8.35** — three times Dharavi.

Either Khayelitsha is exceptional even among community-mapped areas, or Dharavi
and Kibera are less complete than their reputation implies. These cannot be
separated from this data. **Neither should be used as the representative case or
as an optimistic bound.**

### Under-mapped, in confidence order

- **Lagos (0.19)** — clearest. 3.30 km from 14 footway ways; `pedestrian` and
  `steps` both zero; over an AOI containing Makoko. Arterial coverage is fine at
  32 km. *Good arterials + near-zero pedestrian is the signature of partial
  mapping, not an unmapped area.*
- **Jakarta (0.39)** — central kampung fabric; no place nodes returned at all
  across 42.84 km²
- **Accra (1.29)** — 102 km service against 13.9 km footway; vehicular-first
- **HCMC (0.90)** — genuinely ambiguous. AOI is 5–17× the others and likely spans
  periurban land, so the low mean may be an averaging artifact. Do not flag
  without re-measuring on a comparable sub-AOI.
- **Nusantara (0.63)** — the one low city **not** flagged. Greenfield new-capital
  site; sparse mapping plausibly reflects sparse construction.

### Methodological note

The grouping matters. `service`, `residential`, and `track` are
vehicular-capable; only `footway/path/pedestrian/steps` stand in for alleys.
HCMC ranks 2nd on the broad grouping and 3rd-lowest on the narrow one, because
2,372 of its 2,488 "pedestrian" km are service and residential.

AOI contents were verified rather than assumed: Cape Town is **Khayelitsha**, not
Table Mountain (hiking-trail hypothesis tested — only 3 of 1,544 path ways carry
hiking tags). Nairobi is **Kibera**. Lagos is **Ebute-Metta and Makoko**.

**No completeness rate is claimed.** There is no reference network to measure
against. "Under-mapped" means density is low relative to peers of similar
character, never *X% missing*.

---

## PART C — Imagery and data source availability

### C.1 Free VHR coverage over the 11 training cities [E]

| City | OpenAerialMap optical | Umbra SAR | Capella SAR |
|---|---|---|---|
| Dhaka | 25 (1.5–5 cm UAV) | 0 | 4 |
| Accra | 6 (5 cm UAV, Old Fadama) | 0 | 6 |
| Nairobi / Kibera | 3 (30.5 cm Maxar) | 1 (0.125 m) | 4 |
| Lagos | 3 (5.4 cm UAV, Makoko) | 0 | 6 |
| Guatemala City | 1 (22 m — unusable) | 0 | 8 |
| Kigali | 0 | 0 | 4 |
| Jakarta | 0 | 0 | 0 (near-miss) |
| Cape Town | 0 | 0 | 0 (near-miss) |
| **Dharavi / Mumbai** | **0** | **0** | **0** |
| HCMC | 0 | 0 | 0 |
| Nusantara | 0 | 0 | 0 |

**Dharavi — the primary AOI, the demo AOI, and the AOI both Phase 1 runs used —
is the worst-covered city in the entire set.** Zero across all three sources.

Umbra traversal was exhaustive: 2 years, 14 months, 225 days, 1,558 items.
Capella enumeration was exhaustive: 7 years, 66 months, 928 days, 9,999 items.

**Four cities are well-covered from multiple independent sources** — Dhaka,
Accra, Nairobi, Lagos all have both centimetre-scale optical and sub-metre SAR.
Three of those (Old Fadama, Makoko, Kibera) are UAV surveys of the *exact*
informal settlements the project targets.

**Capella coverage clusters almost entirely in 2024-11** — it reads as a
coordinated open-data release, not a time series. Single-date SAR: an independent
structural reference for validation, never a Sentinel-2 substitute.

### C.2 Sources ruled out [E/X]

**NICFI — dead.** [E] `EEException: not found` on every asset path
(`asia`, `africa`, `americas`, and the parent folder), confirmed against a
healthy EE session (control: `COPERNICUS/S2_SR_HARMONIZED` returned 36 images).
Program phase-out began January 2025; Norway cancelled the next-phase procurement
September 2025. *Honest limit: GEE returns an identical error for "does not
exist" and "caller lacks access," so deleted-vs-permission-gated is
undetermined.*

**Google Open Buildings road layer — does not exist.** [E] Namespace enumerated
via `listAssets`: `GOOGLE/Research/open-buildings` contains exactly three folders
(v1, v2, v3), each holding only `polygons` and `polygons_FeatureView`. Temporal
v1 bands read live: `building_fractional_count`, `building_height`,
`building_presence` — three bands, all buildings.

Sirko et al. (arXiv:2310.11622) §7 states directly: *"Our evaluations focus on
the building detection task and we do not report metrics for the road detection
and image super-resolution tasks."* `source.coop` and the project site mention
"road" only inside the citation of the paper title.

*Honest limit: EE has no server-side wildcard search, so this is exhaustive
within the open-buildings namespace but name-probing only outside it.*

**Sentinel-1 for road/alley detection — ruled out.** [X/R]

Sentinel-1 IW GRDH is **not 10 m**: resolution is 20.4 × 22.5 m; the "10 m"
universally quoted is *pixel spacing*. So it is twice as coarse as Sentinel-2, not
equal.

Layover geometry: ground-range layover extent of a vertical edge of height *h* at
incidence θ is `L = h·cot θ`. For h = 3 m the break-even against a 3 m alley is
**θ = 45° exactly** — and Sentinel-1 IW operates at ~29–46°. So **layover covers
100% of the alley width across essentially the entire operating range**, and at
near-range overshoots by ~70%.

**But layover is not the binding constraint.** A 3 m alley is **15–20× below the
resolution cell in azimuth**. One resolution cell integrates several structures,
several alleys, and their layover together. Whether layover occludes the alley is
moot when the alley is never resolved.

*This is the stronger and more defensible framing: "the alley is 15-20× below the
resolution cell" needs no further defence, whereas "layover fills the alleys"
invites a request for a layover budget.*

Double-bounce reliability at 2–4 m structure height is weak and unvalidated:
wall is only ~54λ tall in C-band; response falls off sharply beyond ~10–15° of
azimuth-parallel and informal fabric has no dominant orientation; the required
smooth ground plane is itself in layover/shadow; corrugated pitched roofs
dominate the cell; Sentinel-1 is dual-pol, so true Freeman–Durden decomposition
is unavailable.

**The literature genuinely does not cover this case.** No published measurement
of layover occlusion in low-rise informal fabric — the geometry literature is all
mid/high-rise, and the informal-settlement SAR literature treats settlements as a
*texture* class without resolving individual structures. No published Sentinel-1
road detection in informal settlements at all; existing SAR road extraction
targets rural/inter-urban roads wide relative to the pixel.

**Sentinel-2 super-resolution — recommended against.** [X] GeoSR-Bench
(arXiv:2605.00310) benchmarks 9 SR models on downstream tasks including building
segmentation and road detection, and finds *"improvements in traditional SR
metrics often do not correlate with gains in task performance, and the
correlations can be negative."* On the MODIS→Landsat river task: baseline F1
0.68, SR models 0.74–0.75, **real Landsat-8 0.95** — SR recovered ~10% of the
gap.

ESA's own OpenSR project funds `opensr-test`, a benchmark with a dedicated
**hallucination** metric. Reported rates span SuperImage 0.0610 to a
latent-diffusion baseline at **0.5963**. *The existence of an ESA-funded
hallucination metric answers how the field understands SR: as something requiring
a dedicated instrument to police, not a free resolution upgrade.*

**ESA Earthnet Third Party Mission — India ineligible.** [X] Would otherwise be
the best option available: free PlanetScope (3.7 m) *and* SkySat (0.65 m) for
non-commercial research. Restricted to ESA Member States, EC Member States, and
China via the Dragon programme.

**ISRO Cartosat sub-metre — not free to non-government entities.** [X] Under the
Indian Space Policy 2023, data finer than 5 m is free only to Government
Entities; Non-Government Entities purchase commercially via NSIL.

**Multi-temporal sub-pixel shift exploitation — not viable.** [R] Sentinel-2's
sun-synchronous orbit gives near-identical repeat geometry, so the sub-pixel
shift diversity the technique requires is minimal to absent. What remains is
compositing (improves SNR, reduces cloud/shadow noise — genuinely useful) but not
resolution recovery.

**No new free sub-10 m source over Dharavi.** [E] Every channel checked converges
on this. *Continued searching has negative expected value versus digitizing OSM
ground truth for the bounded area that actually matters.*

**Systematic-global check, applied retroactively to all of the above:** the
project's deployment scope is global (Paris, Beijing, Kampala, Lagos, Dharavi —
not just the 11 training cities), so any candidate source must be free,
systematic, and globally uniform in coverage — the same operating model
Sentinel-2 itself provides. Under that stricter bar: commercial VHR (Maxar,
Airbus, Planet SkySat) fails outright — it is tasking-based, not standing
archive coverage, and cannot be deployed as infrastructure for an automated
global pipeline. Hyperspectral (EMIT, PRISMA) fails — non-uniform,
opportunistic revisit patterns (e.g. ISS-based orbits), not a Sentinel-2-like
systematic pattern. Only **Landsat thermal (TIRS)** and **VIIRS nighttime
lights** pass this bar as candidate additions — both free, systematic, and
globally uniform — and both add a genuinely new information axis (surface
temperature / heat-island intensity; economic-activity proxy) rather than
fixing the sub-pixel resolution ceiling itself, which no source meeting the
free-global-systematic bar can do at any price point available to this
project.

### C.3 Sources available [X]

**Google Open Buildings (buildings).** Dual-licensed **CC BY 4.0 or ODbL v1.0**
(choice is yours). 1.8B detections over 58M km². **All ten target countries in
scope** — India, Kenya, Nigeria, Ghana, Bangladesh, Indonesia, Rwanda, South
Africa, Vietnam, Guatemala. Temporal v1: 4 m effective resolution, annual
2016–2023.

Google's own FAQ names the failure modes: *"small buildings, which can appear
only a few pixels wide"* and dense urban settings with *"contiguous buildings not
having clear delineations."* That is a description of Dharavi.

**Critical caveat on Temporal v1: it is derived from Sentinel-2.** Feeding it into
a Sentinel-2 classifier adds a strong inductive prior, not independent
information — and any systematic error it makes on informal fabric is inherited
and amplified. Its confidence values are explicitly uncalibrated.

**Microsoft Global ML Building Footprints.** 1.4B buildings, entire dataset
rebuilt January 2026, ODbL. Only 225M carry height, 344M carry confidence.

**Overture buildings.** 2.5B, ODbL, monthly. **Not independent** — Overture's own
documentation states many buildings derive from ML sources (Microsoft, Google
Open Buildings) with lower footprint precision, explicitly citing the Global
South. Since OSM wins conflation and OSM is ~9% complete in South Asia, Overture
in dense informal fabric is effectively Google/Microsoft ML output with a thin
OSM veneer. **Do not treat as a third opinion.**

**Planet Education & Research Basic.** Free, 3,000 km²/month, PlanetScope ~3 m,
30-day delay (irrelevant for retrospective work), university email required.
**Applied — 3-week processing.**

Terms that matter: non-commercial only; may publish articles and derivative
products with attribution; **raw imagery cannot be made publicly accessible**;
derivative products shareable if they do not preserve original data values.
Retention after program end is *unaddressed* in the ToS.

**The sharing clause is a real strategic constraint:** if you annotate
PlanetScope imagery, you cannot publish the imagery half of that dataset. An open
annotated benchmark for informal-settlement land cover would be a stronger
contribution than another model, and Planet's terms partly foreclose it.
Sentinel-2 does not have this problem.

Scale is not the constraint: a ~7 km² AOI against a 3,000 km²/month quota; a
15-city expansion at ~25 km² each is ~375 km², one-eighth of one month.

**Umbra Open Data.** 25 cm SAR, **CC BY 4.0**, no sign-up, AWS STAC. Highest
free resolution of any source found — but ~20 recurring sites, industrially
skewed. One hit across the training set (Nairobi).

**Capella Space Open Data.** SAR, CC BY 4.0, AWS STAC, quarterly additions. Six
of eleven cities covered.

**OpenAerialMap.** Openly licensed drone/aerial, typically centimetre-scale,
humanitarian focus. Four cities covered including three exact target settlements.

**Vantor (Maxar) Open Data.** Sub-metre optical, **CC BY-NC 4.0**,
**disaster-triggered only** — not systematic.

### C.4 Population data [E/X]

**WorldPop does not cap at 2020 as a product** — current release **R2025A**
(September 2025), covering 2015–2030 including projections.

**But the GEE mirror does.** `WorldPop/GP/100m/pop` verified live: 5,221 images,
distinct years exactly **2000–2020**, globally and for IND. `R2025A` probed under
two plausible paths — neither exists in GEE. **Reaching it requires a non-GEE
ingestion path — real work, not a constant edit.**

**GHS-POP `JRC/GHSL/P2023A/GHS_POP`** is in GEE with 12 epochs: 1975 … 2015,
2020, 2025, 2030.

**Critical: GHS-POP's newest *observation* epoch is also 2020.** Switching buys
projections, not newer measurements. **The 2020 cap is a cap on observed global
gridded population in the GEE catalogue generally, not a WorldPop-specific dead
end.**

Zonal sums over the Dharavi AOI (same `crsTransform` method the code uses):

| Source | Population |
|---|---:|
| GHS_POP 2015 | 248,492 |
| GHS_POP 2020 | 261,569 |
| GHS_POP 2025 | 279,331 *(projection)* |
| GHS_POP 2030 | 309,591 *(projection)* |
| **WorldPop 2020** | **282,983** |

The WorldPop figure matches `exposure_constants.py:35`'s recorded 282,983.025
exactly — confirming the query reproduces the code's path.

**GHS-POP and WorldPop disagree by ~7.6% at 2020** over the same AOI. Different
models; switching source is not like-for-like and breaks comparability with
existing output.

**India's census: postponed to 2027.** Phase 1 (House Listing) April–September
2026; Phase 2 (Population Enumeration) February 2027; provisional results late
2027, final late 2028. First postponement since 1871; first caste enumeration
since 1931. **No enumerated microdata before 2027–28** — any India population
ground truth is either extrapolated from 2011 or modelled.

---

## PART D — Method and literature [X]

### D.1 The magnet class has a name

**Menon et al., "Long-Tail Learning via Logit Adjustment"** (arXiv:2007.07314,
ICLR 2021). Standard cross-entropy converges asymptotically to
`p(y|x) ∝ π_y · f_y(x)` where `π_y` is the training class prior. A large prior
combined with a *generic* feature — which spectrally mixed pixels produce —
means the prior term dominates globally.

**This is why a pairwise loss could not work.** A prior effect is global and
additive across the whole feature space; a discrimination effect is local and
pairwise.

Segmentation-specific: **Wang et al., "Balancing Logit Variation for Long-Tailed
Semantic Segmentation"** (CVPR 2023) frames the identical mechanism as tail
classes being "squeezed" while head-class logits dominate.

**Important gap:** validated only on Cityscapes / GTA5 / SYNTHIA / PASCAL VOC —
driving-scene benchmarks. **No remote-sensing validation of logit adjustment for
segmentation was found.** Running it on a Sentinel-2 LOCO setup would likely be
among the first, which is itself a contribution.

**Two compounding mechanisms, needing different fixes:**
1. *Statistical* — Menon-style prior dominance
2. *Physical* — sub-pixel mixing making the feature generic. **This would produce
   a magnet even with perfectly balanced classes.**

**The clean ablation:** correct the prior (post-hoc, cheap). If road *precision*
does not improve, the residual is feature genericness — direct, testable evidence
for the sub-pixel argument.

**Post-hoc logit adjustment:** subtract `τ·log(π_y)` from each logit before
softmax; tune `τ` on a held-out city. No retraining, reversible. The measured
42.45%-vs-17.81% ratio *is* an empirical estimate of the prior mismatch.
*Caveat: check per-city road prevalence first — a single global `τ` under- or
over-corrects if held-out cities differ substantially.*

**Superseded in part by Decision 11:** with `paved_road` deleted as a discrete
class, the magnet-class mechanism described here does not directly recur under
fractions, since there is no argmax step to compound the ambiguity. Retained
as the causal evidence for *why* the taxonomy changed. Logit adjustment
(item 30) remains relevant only if any discrete classification step survives
downstream of the fraction pipeline.

### D.2 Calibration under distribution shift

**The current method is not a calibration method.** CAAT's 10th percentile of
correctly-predicted confidence is a *recall-preserving cutoff* with zero
information about how many incorrect predictions clear the same bar.

**Conformal prediction's guarantee does not transfer.** Split conformal requires
exchangeability between calibration and test data. LOCO breaks this *by
construction* — the held-out city is deliberately from a different distribution.
Reporting a conformal set size without flagging this is a validity error a
reviewer should catch.

Two live responses in the literature:
- **Weighted / covariate-shift conformal** (Tibshirani, Barber, Candès, Ramdas,
  NeurIPS 2019, arXiv:1904.06019) — reweights by likelihood ratio, restoring
  guarantees *if the ratio is well-estimated*. Estimating a density ratio between
  cities with different urban morphologies is itself high-variance.
- **Non-exchangeable / OT-based conformal** (arXiv:2507.10425, 2025) — drops
  exchangeability, proves *bounds* on coverage degradation as a function of a
  measured distributional distance. Uses *unlabeled* target data, which fits.

**The practical recommendation: risk-coverage curves / selective prediction**
(Geifman & El-Yaniv). Plot risk (error rate among *accepted* predictions) against
coverage as the threshold sweeps, per class per city. This gives the full curve
that the current method collapses to one point on — and directly answers the "no
precision term" critique by construction, at near-zero cost, since the softmax
outputs already exist.

Also relevant: **"Epistemic Reject Option Prediction"** (arXiv:2511.04855, 2025)
separates epistemic from aleatoric uncertainty. `paved_road`'s overconfidence
looks *aleatoric* (physically ambiguous mixed pixels) rather than epistemic.

### D.3 Label noise that is physical, not annotative

Most noisy-label methods (DivideMix, loss-correction, noise-transition matrices)
assume noise is either input-independent given the true label, or from a
human labelling process.

**This noise is physically deterministic given geometry.** A pixel straddling a
road edge *is* spectrally mixed, always, regardless of who labelled it. Not
stochastic annotator error — the sensor's PSF integrating multiple materials.

**Class-conditional noise-transition methods are therefore the wrong tool** —
they estimate a global constant `P(observed = road | true = X)`, while the mixing
fraction varies continuously per pixel with sub-pixel geometry.

**What matches the mechanism:**
1. **Soft/fractional target supervision from an abundance model** — highest
   fidelity. *This is what the architecture change adopts wholesale.*
2. **Buffer-distance-weighted loss** — cheaper; down-weight CE as a function of
   distance from centreline
3. **Uniform label smoothing** — *the wrong tool, named explicitly.* Spreads mass
   uniformly across all classes, not encoding where mixing comes from. Useful only
   as a negative control demonstrating the noise is structured, not random.
4. **Partial-label learning** — candidate sets at boundary pixels; the
   training-time mirror of prediction sets

*The remote-sensing-specific insight: label noise is generated by sensor geometry
and is therefore predictable from geometry — so geometry-informed soft targets
should outperform anything from generic noisy-label literature applied unmodified.*

### D.4 The 0.313 benchmark question — unresolved [X]

**No matched comparison exists.** No paper runs leave-one-city-out
cross-validation across Global South informal-settlement-inclusive cities at 10 m
with this class scheme.

**Two tempting bad comparisons, both warned off:**
- Global intra-urban Sentinel-2 work uses *easier protocols* — same-city splits
  or pooled global training and testing. Not comparable.
- Informal-settlement-specific work mostly uses VHR, so higher numbers partly
  reflect **resolution advantage, not modelling advantage**.

**What can be said with support:** within-distribution mIoU commonly lands 0.5–0.7+
for well-separated classes at appropriate resolution; **cross-domain drops of
30–50% relative are commonly reported** whenever a paper tests this honestly.
0.313 across 11 cities on an under-benchmarked task is consistent with *a hard,
honest number for a hard, honestly-evaluated protocol* — not an outlier.

**The recommended move:** a literature table with columns for resolution,
protocol (within-city split vs cross-city LOCO vs cross-region), and class count,
showing no directly matched number exists. **That gap is itself a finding about
the state of the field**, and more valuable than a possibly-misleading
number-to-number comparison.

### D.5 What the field's 10 m products actually do [X]

**ESA WorldCover v200** — 11 classes, **one built class**. No roads. No
formal/informal distinction. No sub-class within the built environment.

| | Overall | Built-up UA | Built-up PA |
|---|---:|---:|---:|
| Global | 76.7 ± 0.5% | 65.9% | 73.2% |
| **Africa** | — | **47.1%** | 84.0% |
| Asia | — | 68.0% | 71.6% |

Africa's 47.1% user's accuracy against 84.0% producer's accuracy is a striking
asymmetry: it finds most real built-up but **less than half of what it calls
built-up actually is.** Massive over-commission — bare compacted earth being
called built. Directly relevant.

The Product Validation Report gives **no minimum mapping unit for built-up and no
discussion of mixed pixels or roads at all.**

**Google Dynamic World** — 9 classes, **one built area**. No roads, no informal
distinction.

**The design feature worth stealing:** Dynamic World ships **per-pixel class
probabilities alongside the argmax label**, explicitly so users can apply their
own threshold or decision framework. The team's stated position is that the
*hard* label is the lossy artifact and the probability vector is the real output.

**Venter et al. (2022)**, *Remote Sensing* 14(16):4101 — comparative analysis of
Dynamic World, WorldCover, and Esri Land Cover showing systematic confusion
concentrated specifically in built/urban classes across all three.

**The lesson:** two well-funded teams with global validation budgets, working at
exactly 10 m, independently concluded the correct taxonomy has one built class.
Neither attempts road/roof separation. That is precedent, not coincidence.

### D.6 OSM as a label source [X]

**An active methodological literature exists** treating OSM-as-label as a known,
named noise source to be modelled and corrected for — not as ground truth.
Accepted practice: quantify OSM completeness/positional error locally via a small
independently-verified sample, then either weight training loss by estimated
label confidence, or report expected noise rates as a limitation.

**OSM completeness benchmarks:** building completeness averages **9% in South
Asia**, 20% in Latin America and the Caribbean, 30% in Sub-Saharan Africa (Nature
Communications, 2023). Road-network completeness is 80%+ globally in aggregate
(Barrington-Leigh & Millard-Ball, PLOS ONE) — **but informal settlements are
exactly where that average does not hold.**

**HOT is not independent of OSM.** HOT organises volunteer mapping that commits
directly into the OSM database. Using HOT data as a check on OSM-derived labels
restates the circularity rather than fixing it.

**IOM DTM** is displacement/IDP-site specific — conflict-driven coverage, not
general informal urban settlements.

**UN-Habitat SDG 11.1.1** is household survey and administrative boundary data —
validates *aggregate* claims, not pixel- or segment-level correctness.

**No free, independently-sourced, building-level structural dataset for Global
South informal settlements exists in open form.** Every path either shares OSM's
lineage, is the wrong unit of analysis, or does not cover general informal
settlements.

### D.7 Publication framing [X]

**Provenance gaps do not sink a submission.** The ML Reproducibility Checklist
v2.0 (Pineau et al.) and NeurIPS's Reproducibility Statement are both structured
around authors *declaring what is and isn't available* — they require honesty
about the boundary, not perfection.

RS-specific treatments exist: *"How to Improve the Reproducibility,
Replicability, and Extensibility of Remote Sensing Research"* (Remote Sensing
14(21):5471, 2022) and its deep-learning companion (14(22):5760) both discuss
checkpoint/versioning gaps as a known field-wide problem.

**Standard artifacts:** Model Cards (Mitchell et al., arXiv:1810.03993),
Datasheets for Datasets (Gebru et al., arXiv:1803.09010).

**Five things to report alongside a taxonomy change**, so it reads as a finding
rather than metric gaming:
1. Full confusion matrix **before** the change, showing where off-diagonal mass
   concentrates
2. Per-class producer's and user's accuracy before and after — showing the
   *other* classes are essentially unaffected
3. Spectral/spatial separability analysis at the working resolution
4. Explicit comparison to WorldCover/Dynamic World taxonomy
5. A causal mechanism tied to sensor resolution — not "accuracy improved," but
   *why it physically would*

**These five requirements are now Decision 17's formal acceptance criteria
for Gate C** — see `05_BUILD_MANUAL.md` Part 3.

**Substitutes for user validation, ranked:** comparison against an established
product (WorldCover/Dynamic World as de facto reference); a documented but unrun
protocol; expert review; simulated scenarios. **None tells you the tool is
*useful* — only that it is *accurate* or *plausible*.** Decision-support claims
must therefore be dropped explicitly.

**Venues:** arXiv preprint regardless. MDPI *Remote Sensing* (publishes exactly
this kind of limitation/comparison study). IEEE GRSL (letter format, good for a
focused negative finding). **INGARSS** — IEEE GRSS regional conference in India,
accessible entry point, feeds a JSTARS special issue. ISPRS Geospatial Week.
Climate Change AI workshop (NeurIPS/ICLR). EarthVision (CVPR workshop).

**The line worth internalising:** *a transparently self-corrected audit is more
credible to a reviewer than a "perfect" one* — especially in 2026, when reviewers
are increasingly aware that LLM-assisted analysis needs spot-checking.

---

## PART E — Verification results

### E.1 Spot-check of ten weight-bearing findings [E]

| # | Finding | Verdict |
|---|---|---|
| 1 | C14/C20 | CONFIRMED |
| 2 | C19 | Claim holds, two numeric caveats |
| 3 | C21 | CONFIRMED |
| 4 | C25/C26 | CONFIRMED |
| 5 | C31 | CONFIRMED |
| 6 | C32 | CONFIRMED |
| 7 | C13 | CONFIRMED |
| 8 | C29 | CONFIRMED |
| 9 | W1 | CONFIRMED |
| 10 | C9 | CONFIRMED except one descriptive claim |

**Eight of ten reproduce exactly, several to the pixel.**

**Line citations held up better than the framing did.** Of eight distinct
references resolved: six exact, two loose-but-containing, **none pointing at the
wrong construct.**

### E.2 The shape of both defects — the important part

Neither defect was a bad citation. Both were **a derived number presented as a
measured one**:

- **C19** — "56.12" is reproducible only by *rescaling* the emitted value, not by
  recounting. And because it was produced by dividing by 1/(1−0.2574), the claim
  that the ratio was "exactly 1/(1−0.2574)" was **true by construction, not
  independent confirmation.**
- **C9** — "a clean one-position shift" was asserted from the first few instances
  without checking the rest. True for ids 25–28, false for 29–35.

**Both would have survived a line-reference audit. Both only fell out of
re-running the measurement.**

**The actionable conclusion:** verifying a citation establishes almost nothing
about whether the number attached to it was measured or inferred. Weight-bearing
figures should be re-derived, and derived figures should **name the operation
that produced them** so a later reader can distinguish corroboration from
restatement.

### E.3 Confirmed-good behaviour

Recorded because an audit reporting only defects misrepresents the system.

- **Determinism is exact** — bit-identical maps and scores across identical runs
- **The pipeline runs clean end-to-end** on both 1-tile and 4-tile AOIs with no
  code changes; environment, credentials, dependencies already correct
- **`risk/compute.py` refuses to fabricate a risk score** even when all three
  inputs are available, rather than inventing a fusion formula. *That restraint
  is load-bearing — do not let a future phase "helpfully" add a formula.*
- **`GATE_C_STATUS` has not drifted** from `PROJECT_GATES.md` and propagates into
  `result.json` on the success path
- **Population is `None`, never a fabricated 0**, when unavailable
- **The WorldPop scale-bug fix holds** — `reduceRegion` uses the image's own
  CRS/transform with no `scale=`
- **Frontend unavailability handling is genuinely good** — every gated module
  renders `.reason`/`.error` with a distinct status pill rather than blanking to
  zero; the `road_access_score === -1` sentinel correctly shows "N/A". *This is
  the pattern to copy elsewhere.*
- **The hand-rolled RLE codec is lossless** across six edge cases
- **`forward_features` hook** fires correctly (empirically verified)
- **Mosaic placement math, distance-map slice shapes, road-score coordinate
  ordering, `compute_aoi_geodesics`' geodesy, and the event loop** all verified
  correct
- **The road-mask generator itself is well-engineered** — meter-accurate UTM
  buffering, per-type widths, unpaved tags excluded. The problem is physics.
- **The water-mask generator's documentation discipline is unusually good** — its
  docstring claims Pass-1-only gave Dhaka "just 148 pixels"; `meta.json` records
  exactly `pass1 = 148`, `pass2 = 8483`. Stated problem, fix, and recorded
  outcome all agree. `skipped_unclosed` is 0 across all 11 cities.
- **C9 does not reach the UI** — `segment_id` is used only as a React key
- **C13 does not reach the live frontend** — `primary_tile` referenced zero times

### E.4 What was refuted

**C5 — the train/inference distribution mismatch. REFUTED.** Chased hard,
disproven by locating and reading the actual training notebook. Preserved in V1
as a documented wrong turn.

**C22's consequence claim — REFUTED.** No-data renders mid-range (125.4), below
the known-pixel mean (149.1), 0.0% at maximum. Mechanism retained; the surviving
defect is a *collision*, not an alarm.

---

## PART F — Open questions

Carried forward deliberately. Not answered.

1. **Does spectral mixing specifically produce the broad prior?** The causal
   chain is strongly supported but the final link is inference — no feature-space
   or per-class spectral-variance analysis was run.
2. **What is the correct class weighting?** The direction of the patch/pixel
   mismatch is established; what should replace it is not. Pixel weighting would
   worsen `paved_road` and gut `standing_water`. *Superseded by Decision 11 —
   relevant only if a discrete classification step survives.*
3. **How much of the magnet effect survives a taxonomy change?** If classes merge
   into fractions, does the diffuseness resolve or persist? *Partially answered
   by Decision 11's argmax analysis in `02_ARCHITECTURE.md` §3 — no argmax step
   means no compounding — but not empirically re-tested.*
4. **What is the true unknown rate across all 11 cities?** Measured on two Mumbai
   AOIs only. §A.13 shows AOI dependence is material. *Reformulated by Decision
   14 — the question is now about the three separate observability components,
   not one merged rate.*
5. **Is the 24.45% no-penalty baseline correct?** Not re-measured; the +1.29 pp
   delta inherits any error in it.
6. **C18, C1, C2, C3, C4 have no demonstrated trigger.** They may be unreachable
   in practice or merely untested. *See Decision 15 for the rule governing when
   this can justify a severity downgrade.*
7. **Nothing here measures correctness.** Every result describes what the system
   *does*. No ground truth was consulted; the independent gold set remains the
   missing instrument.
8. **Global endmember strategy** — *Decision 13 settles the strategy (Option D,
   constrained); this question narrows to whether the constrained approach
   validates on the 2–3 city pilot, which has not yet run.*
9. **Is SLUM-i's Mumbai annotation layer independent of OSM?** Described only as
   derived from "verified administrative boundaries." Provenance unverified.
10. **Would DRP-SRA release the 2024-25 Dharavi LiDAR/digital-twin survey?**
    Known to exist. Not known to be accessible. An RTI request is a legitimate,
    low-cost, non-blocking attempt.
