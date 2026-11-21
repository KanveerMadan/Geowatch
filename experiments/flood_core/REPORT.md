# Flood-core prototype: P0 results (synthetic) and proposed real development cases

**Date:** 2026-10-31. **Branch:** `proto/flood-core`, worktree `~/gw-floodproto`, from `master` @ `87f52cb`. **Not committed.**

**Isolation:**
- Python environment: `~/gw-floodproto-env` (Python 3.12; numpy 2.5.4, h5py 3.16.0, rasterio 1.5.1, pytest 9.2.0).
- SFINCS image: `deltares/sfincs-cpu:sfincs-v2.4.1`, digest `sha256:cab764e13a6c…`, **linux/amd64 run under emulation on an arm64 Mac**, so every time below is an upper bound for native execution.
- Run outputs: the session scratchpad (`sfincs_runs/`, 19 MB).

**Not touched:** production methods, labels, UI, `geowatch-env`, round 4b, and reserved events. Every Earth Engine read was a HydroBASINS polygon lookup or a dev-box input; nothing was read for a reserved event except its approximate town point for the basin lookup.

**Disk:** 1.3 GiB free on the host after setup. The image is 218 MB and the environment 143 MB. No existing Docker images were removed.

---

## 1. Event registry (`registry/`, see its README)
- **46 units** (43 dev, 3 reserved), **7 alias groups**, and **29 independent clusters** among the dev units. 7/7 tests pass.
- The name-only guard used by round 4b misses aliases the registry blocks. A test demonstrates this with a renamed Valencia EMSR773 AOI03 unit.
- HydroBASINS surfaced two links no name or curated cluster held:
  - Himachal and Sindh share the Indus basin;
  - Bihar, Assam, Sylhet and Dhaka share the GBM basin.
- **Reserved verdicts:**

| Event | Verdict | Why |
|---|---|---|
| noakhali_2024 | needs a signed exception | linked only through the curated GBM region; its own main basin is the Feni |
| calais_2023 | clear | — |
| redon_2025 | clear | — |

- Two settings are your judgement: `PROXIMITY_KM` (20, from the round-4 S1 search square) and `BASIN_LEVEL` (6).

## 2. GEDTM30 scale finding: reproduced, not corrected (`gedtm30/FINDING.md`)
The header declares scale 0.1, but the stored values are metres:

| Point | Published | Raw | Raw × 0.1 |
|---|---|---|---|
| Denver capitol step | 1,609.3 m | 1,613.8 | 161.4 |
| El Alto airport | 4,061.5 m | 4,030.5 | 403.1 |

This was done with a different GDAL build and different checkpoints from the first observation. A scale-honouring reader would be 10× low. A ledger entry (C82) is drafted, not added.

## 3. P0: SFINCS on synthetic cases (`sfincs/p0_cases.py` → `sfincs/results/p0_results.json`, `p0_runtime.json`)

No check uses a pass/fail threshold. Each one's basis is stated.

### c1 Water conservation (closed irregular basin, 1 km², 50 mm/h for 1 h, 3 h run)
- **Basis:** conservation. Stored volume must equal rain volume. The model starts dry, so no initial storage enters the balance.
- **Rain then stop:** after the rain stops, the residual is constant at **−15.8 m³ of 50,000 (−0.032 %)**, about one second of rainfall at the stop time. There is **no drift** over the following 2 h.
- **Steady rain:** the final residual is +0.005 %.
- **During rain:** the residual saw-tooths up to **0.12 %** and resets about every 30 min. I suspect the meteorological forcing update interval, but this is **not verified**.
- The residual is about 3 orders of magnitude above the float32 output resolution (≈0.006 m³), so it is the solver or forcing, not output precision.
- **First-attempt correction:** my first c1 counted SFINCS's default initial water level (0 m) filling cells below zero (≈1,542 m³) as error, and computed a float32 bound over −99999 fill values. Both were fixed before the numbers above.

### c2 Known solution: kinematic sheet flow on a plane (1 km, slope 0.01, n = 0.04, 100 mm/h)
- **Basis:** analytic steady state h(x) = (n·i·x/√S)^(3/5). Equilibrium is reached in about 40 min; the run lasts 3 h.

| `huthresh` | median rel. error | max |abs.| | upstream quarter | downstream quarter |
|---|---|---|---|---|
| **default** | **+82 %** | 311 % | +117 % | +83 % |
| 0.001 m | **+3.1 %** | 14 % | +6.7 % | +2.2 % |

- **Finding:** with the default `huthresh`, water must reach about 5 cm before it flows. Shallow sheet flow is therefore held at about 0.05 m (analytic 0.012–0.061 m). That matters directly for pluvial (rain-driven) runs. **Any real run must set and record `huthresh`, with its sensitivity reported.**

### c3 Backwater (2 km reach, slope 0.0005, 5 m³/s inflow; downstream level −1.0 / 0.5 / 1.0 / 1.5 m)
- **Monotonicity** (a higher downstream level must not lower any upstream water level): **0 violations** over 200 cells × 3 level pairs.
- **Hydrostatic bound** (with inflow, the water level must be at or above the boundary level wherever the bed is below it): **0 cells** below the bound.
- **Backwater reach:** 735 / 1,775 / 1,995 m, against level-pool limits of 1,000 / 2,000 / 2,000 m. That is consistent: the reach is bounded by where the bed meets the boundary level, plus the profile curve upstream.

### c4 Interacting drivers (estuary valley 3 × 1.2 km; rain R, river Q, surge B; 10 runs + 3 closed)
- **Monotonicity** (adding a driver must not lower peak depth at any point): **no decreases**, with every decrease listed and no tolerance applied.
- **Interaction**, where the term is joint minus the sum of single-driver increments:
  - **Upstream floodplain:** joint 0.234 m vs best single driver 0.158 m (**+48 %**), interaction **+0.024 m** (super-additive: surge blocks river drainage).
  - **Town basin:** interaction **−0.747 m** (sub-additive: the basin fills to the surge level).
  - **Channel near outlet:** −0.230 m.
- **Timing:** moving the surge peak 6 h later lowers the upstream floodplain from 0.234 to 0.200 m, the town from 1.569 to 1.541 m, and the flooded land area (> 0.10 m) from 1.93 to 1.78 km².
- **Known-answer attribution** (closed domain, every input stored):

| Driver | Model | Known input | Difference |
|---|---|---|---|
| rain | 324,048 m³ | 324,000 m³ | +0.015 % |
| river | 2,260,862 m³ | 2,260,800 m³ | +0.003 % |
| removal attribution, rain | 324,021 | 324,000 | — |
| removal attribution, river | 2,260,835 | 2,260,800 | — |

- **Implication:** a maximum (or average) of single-driver results understates the joint result upstream (0.158 vs 0.234 m). This supports the proposal's compound claim on a **synthetic** case only.
- **First design was replaced:** the first town basin sat above every driver's reach, so it could not test interaction, and dry cells (−99999) contaminated the sums. Both were fixed; the replacement is recorded in the code.

### c5 Grid size (one analytic 3 × 3 km terrain, three Gaussian hollows 0.6 m deep, radii 60/120/250 m, cell-averaged)

| Grid | small hollow max depth | mid | large | DEM relief of small hollow | flooded > 0.10 m | solver s | peak RSS |
|---|---|---|---|---|---|---|---|
| 10 m | 0.640 | 0.607 | 0.476 | 0.76 | 0.51 km² | 4.9 | 60 MiB |
| 30 m | 0.510 | 0.573 | 0.470 | 0.62 | 0.55 km² | 0.26 | 31 MiB |
| 90 m | 0.246 | 0.454 | 0.440 | 0.35 | 0.70 km² | 0.07 | 28 MiB |

At 90 m the small hollow loses about 60 % of its depth. Coarser grids report **more** area above 0.10 m because averaging spreads shallow water.

### c6 Terrain error at 30 m: SUPERSEDED by P0b-3 (§6)
**Superseded (2026-11-01).** c6 used GEDTM30's std (1.24 m) as an error amplitude. That std is ensemble **model spread, not measured elevation error**, and c6 used a single assumed correlation range. P0b-3 replaces it with documented error magnitudes, multi-range correlation and systematic biases. The c6 numbers below are kept as the record of what ran.

(8 realisations per amplitude; correlated noise, 90 m correlation length, which is **assumed, not measured**)
- **Basis for the amplitudes:**
  - 0.10 m = pluvial's current bluespot depth threshold;
  - 1.24 m = GEDTM30 std, median over the Hanoi dev box (measured);
  - 0.50 m = an intermediate value.

| σ | hollows wet > 0.10 m (small / mid / large) | ponded peak volume, large hollow (median; reference 35,480 m³) | Jaccard of flooded pattern vs reference (median) | flooded area (reference 0.55 km²) |
|---|---|---|---|---|
| 0.10 m | 100 % / 100 % / 100 % | 30,651 | 0.19 | 0.95 km² |
| 0.50 m | 100 % / 100 % / 100 % | 14,401 | 0.06 | 0.95 km² |
| 1.24 m | 50 % / 75 % / 100 % | 15,546 | 0.05 | 0.76 km² |

At the measured GEDTM30 spread, **where** water ponds at 30 m is not identifiable (Jaccard ≈ 0.05), and even 10 cm of correlated error creates spurious ponds. Only the largest hollow is wet in every realisation. This supports the proposal's call for terrain ensembles; it argues against single-DEM pond maps.

**First-attempt correction:** my first c6 tested wetness at each hollow's centre cell only, which misses ponds shifted by noise. It was replaced by the maximum within the hollow radius before the numbers above.

### Runtime and memory (all P0 runs; emulated amd64)
- **Throughput:** 27–108 million cell-steps per solver-second (median 69 M, for runs ≥ 9k cells). SFINCS skips dry cells, so this depends on the wet fraction.
- **Average time step:** 1.3–2.8 s at 10–20 m and 7 s at 30 m. Deeper water shortens it: c3 went from 2.5 s to 1.3 s as the boundary rose.
- **Peak memory:** 28 MiB base, 60 MiB at 90k cells.
- **Projection, not a measurement:**
  - A 1,000 km² domain at 30 m (≈1.1 M cells) for a 48 h event (≈60k steps at dt ≈ 3 s) would take roughly **10–40 min per run** here, at roughly 0.4 GB.
  - Four ensemble members (2 terrains × 2 drainage scenarios) would take roughly 40–160 min.
  - The 3 dev boxes with upstream areas > 10,000 km² (Hanoi 137k, Bihar 87k, Encantado 19k) are out of reach as full 30 m domains.
  - P1 must measure real wet fractions.

## 4. Proposed real development cases (P1): SUPERSEDED by §6–§7 (screening, 2026-11-01)
**Outcome:** Volos fails screening (its reference does not cover Volos city). Dubai is diagnostic-only. Valencia (Horta Sud) is the recommended first case (§7). The original proposal is kept below as the record.

**Criteria** (from the supplement's gap table and the registry):
- dev role only;
- one per independent cluster;
- upstream area < 1,000 km² at the box, so a full connected domain is feasible;
- not surge-driven by a tropical cyclone (GTSM-ERA5 underestimates TC surge);
- no known levee or polder control (no levee data source);
- a reference with a known observation time, VHR or optical preferred.

| Rank | Unit (cluster) | Upstream at box | Reference (observation lag) | Why | Known weaknesses |
|---|---|---|---|---|---|
| 1 | **valencia_2024** (DANA 2024; alias of paiporta) | 309 km² | EMSR773 AOI03, WorldView-2/GeoEye-1, **+2 d** | rain-driven ravine flood into an urban area; best reference | culverts and urban drainage unknown, so drainage must run as scenarios; the domain must take the whole Poyo catchment; exposure level 6 (burned) |
| 2 | **volos** (Storm Daniel; alias of derna, derna_2023) | 119 km² | EMSR692 AOI01 m3, WorldView-3, **+4 d** | short steep catchments onto a coastal city; rain-driven | Daniel was a medicane: a check is needed that surge did not drive the Volos footprint; monitoring-3 image is late |
| 3 | **dubai_2024** (UAE 2024) | 79 km² | Sentinel-1, **+8 d** | arid urban pluvial; tests four-state observations under SAR urban blindness and a long lag | SAR misses water among buildings; drainage pumping unknown |
| alt | **kastelli** (Crete 2026) | 34 km² | EMSR933, Legion VHR, +5 d | tiny catchment; a cheap first real run | only 45 flooded cells in the round-3 box |
| alt | **choloma** (TS Sara; alias of belize_city) | 74 km² | EMSR778, COSMO-SkyMed, +6 d | rain-driven inland flooding | TS rainfall; mountain-front alluvial fan |

**Excluded and why:**
- Faenza: levee breach.
- Kerala: polders and bunds.
- Hanoi, Bihar, Encantado: catchments > 10,000 km² and dikes.
- All coastal dev units: tropical cyclones.
- Milagro: +38 d lag.
- JRC climatology sites: not events.
- **Optional P1b:** hanoi or bihar_2026 as a nested domain with a GloFAS inflow boundary. It is blocked on an EWDS account and tests coupling and runtime only; the levee gap is stated, not modelled.

**P1 inputs, all verified readable this session:** IMERG V07, ERA5-Land, GEDTM30 (raw metres, units pinned), FABDEM, the cached EMS layers.

**P1 checks:**
- water balance on the real domain;
- forcing response (rain scaled down and up);
- `huthresh` sensitivity (c2);
- terrain ensemble (c6);
- observation-time comparison in four states;
- the baselines from the supplement;
- runtime and memory, measured.

These are diagnostics, not verdicts.

## 5. Open items for you
1. Approve P1 and its three cases (or swap in alternates).
2. Set `PROXIMITY_KM` / `BASIN_LEVEL`, and decide the Noakhali exception question for 4b.
3. Set a compute budget for the P1 runtime stop rule.
4. Get an EWDS account if you want P1b.
5. Native (arm64) SFINCS: build from source if you need runtime figures without emulation. It needs gfortran and NetCDF-Fortran; the disk has 1.3 GiB free.
6. Commit or discard the `proto/flood-core` branch; nothing is committed.

---

# Addendum, 2026-11-01: P0b checks, screening, and the first-case recommendation

The first part of this report was committed as `503ab5a`. Same isolation and same rules: no production change, no 4b run, no reserved event. Every result below is synthetic or a screen of already-seen development data.

## 6. P0b: three checks before any real-data run

### 6.1 Water-balance saw-tooth: explained (`sfincs/p0b_waterbalance.py` → `results/p0b_waterbalance.json`)
- **Hypothesis tested and rejected:** the meteo update interval (`dtwnd`, documented default 1,800 s). Varying it over 60 / 600 / 1,800 / 3,600 s leaves the residual **identical**. It is also unchanged in a flat basin (no flow) and with `advection = 0`.
- **Separating forcing from continuity:** with SFINCS's own cumulative-rain output (`storecumprcp`), stored water minus applied rain is at most about 1.4 m³ in 150,000 (< 1×10⁻⁵). The saw-tooth lies entirely in applied-vs-input rain.
- **Cause, confirmed:** **output time-stamping.** Maps are written at the first internal step at or after each nominal output time but stamped with the nominal time. With an average step of 2.52 s, the predicted overshoot is 0.70 / 1.44 / 2.15 / 0.33 s; measured 0.73 / 1.47 / 2.20 / 0.42 s.
- **Confirmation run:** capping the step at a divisor of the output interval (`dtmax` = 2 or 1 s) drops the stored-vs-input residual from 1.2×10⁻³ to **≤ 4×10⁻⁶**.
- **Conclusion:** the continuity solver conserves mass. c1's 0.12 % was an artefact of stamping, not a mass error.
- **Side note:** SFINCS's `cumprcp` diagnostic itself drifts by about 9 m³ in 150,000, consistent with float32 accumulation (unverified). The analytic input is the better reference.
- **For real runs:** do water-balance checks with output-aligned steps or after forcing ends. Map time stamps can be up to one step late, which is negligible against the hours-to-days lags of the references.

### 6.2 Shallow-flow threshold `huthresh` (documented default 0.05 m): converges (`sfincs/p0b_huthresh.py` → `results/p0b_huthresh.json`)
Kinematic plane, dx 10 m, median relative error of steady depth against the analytic solution:

| `huthresh` (m) | 0.05 | 0.02 | 0.01 | 0.005 | 0.002 | 0.001 | 0.0005 | 0.0002 | 0.0001 |
|---|---|---|---|---|---|---|---|---|---|
| 100 mm/h (h 1.2–6.5 cm) | +82 % | +44 % | +23 % | +12 % | 5.4 % | 3.1 % | 2.0 % | 1.3 % | 1.1 % |
| 20 mm/h (h 0.45–2.5 cm) | +198 % | +82 % | +54 % | +30 % | 13 % | 6.6 % | 3.6 % | 1.9 % | 1.3 % |

- **Grid refinement** (huthresh 0.0001; dx 20 / 10 / 5 m): 1.65 / 1.06 / 0.77 % (100 mm/h) and 1.87 / 1.27 / 0.98 % (20 mm/h).
- **Basis for "converged":** at 0.0002 m the threshold's added error (1.3 % vs 1.06 %, 1.9 % vs 1.27 %) is comparable to the dx = 10 m discretisation error, which no threshold reduction can remove.
- **Cost:** the time step is unchanged (CFL uses `hmin_cfl`) and the solver time stays within run-to-run noise.
- **On the c5 terrain (30 m):**

| `huthresh` | area > 0.05 m | area > 0.10 m | large-hollow depth |
|---|---|---|---|
| 0.05 m (default) | 8.9 km² | 0.55 km² | 0.47 m |
| 0.001 m | 5.7 km² | 0.91 km² | 0.58 m |

  The default holds a fictitious 5 cm film over the domain and under-fills hollows.
- **Decision for real runs:** `huthresh = 0.0002 m`, recorded in every run's metadata.

### 6.3 Terrain sensitivity with documented error structure (`sfincs/p0b_terrain.py` → `results/p0b_terrain.json`)
**GEDTM30's std is now treated as model spread and is not used as an error amplitude.**

**Error model and its basis:**
- **Magnitudes:** FABDEM MAE 1.12 m built-up, 2.88 m forest; COPDEM30 1.61 m built-up (Hawker et al. 2022, ERL 17:024016). DeltaDTM MAE 0.45 m. σ = MAE·√(π/2) assumes zero-mean Gaussian errors, which is an assumption because MAE includes bias. That gives σ = 1.40 m (FABDEM urban) and 0.56 m (DeltaDTM).
- **Correlation:** short range ~20–200 m plus long range ~1–50 km (Hugonnet et al. 2022, IEEE JSTARS 15:6456); SRTM near-field ~2 km (Rougier). Modelled as Gaussian 100 m + Gaussian 2 km. **The variance split is not documented for FABDEM**, so 50/50 and 80/20 are run, plus short-only for comparison with c6.
- **Systematic biases (bracketing):**
  - ±1.0 m constant offset against a fixed downstream level;
  - ±1.0 m urban block (residual building artefacts or underestimation);
  - ±0.5 m tilt across 3 km.
- **Run setup:** 10 realisations per random model; level boundary on the east edge; `huthresh` 0.0002 m; 30 m.

**Error-free reference:** 1.00 km² flooded > 0.10 m; large hollow ponds 52,337 m³.

| Random error model | flooded km² (p10 / median / p90) | overlap with reference (median) | reference cells wet in ≥ half the realisations | extra area wet in ≥ half (km²) | small / mid / large hollow wet |
|---|---|---|---|---|---|
| FABDEM-urban σ 1.40, short only | 1.30 / 1.50 / 1.69 | 0.11 | 19 % | 0.23 | 70 / 100 / 100 % |
| FABDEM-urban, 50 short / 50 long | 1.35 / 2.21 / 6.96 | 0.10 | 77 % | 2.67 | 100 / 90 / 100 % |
| FABDEM-urban, 80 short / 20 long | 1.20 / 1.38 / 5.24 | 0.08 | 18 % | 0.40 | 50 / 100 / 100 % |
| DeltaDTM σ 0.56, 50 / 50 | 1.91 / 3.30 / 8.98 | 0.12 | 80 % | 3.61 | 100 / 100 / 100 % |

| Systematic bias | flooded km² | overlap with reference | near-boundary flooded (ref 0.37 km²) |
|---|---|---|---|
| offset +1.0 m | 0.92 | 0.93 | 0.30 |
| **offset −1.0 m** | **2.57** | **0.39** | **1.50** |
| urban block +1.0 m | 1.09 | 0.67 | 0.36 (mid-hollow ponding +29 %) |
| urban block −1.0 m | 0.83 | 0.83 | 0.29 (large hollow 0.59 → 1.12 m deep) |
| tilt ±0.5 m | 0.92 / 1.10 | 0.92 / 0.91 | 0.36 / 0.39 |

**Reading:**
- On gentle terrain (0.001 slope), the **long-range** error component controls the outcome. It creates or removes km-scale closed basins: large-hollow storage reaches 0.76 hm³ at the 90th percentile against 0.05 hm³ in the reference.
- Even the best documented global DTM error (DeltaDTM) gives a pixel pattern that is **not identifiable** (overlap ≈ 0.1). Only an ensemble frequency is defensible.
- A **datum offset relative to a level boundary** is the largest systematic effect (4× near-boundary area for −1 m). For Valencia's lagoon boundary, the datum chain matters more than the DEM choice.
- **Limits:** synthetic, gentle terrain. Steeper real catchments will be less sensitive upstream, but flat coastal plains such as Horta Sud are similar. The variance split is an assumption.

## 7. Screening and the first-case recommendation (`screening/SCREENING.md`)

- **Volos: fails.** EMSR692 has no AOI over Volos city. The regional product's water lies on the Thessaly plain (21.74–22.33° E), and the Volos town box holds **0.0 km²** of flooded area or trace. The referenced flood is a large-basin plain flood, suitable at most for a later nested test.
- **Dubai:** diagnostic only (as instructed).
- **Recommendation: Valencia, Horta Sud (DANA 2024), as the one first development case** (dev, exposure 6; never a test event).
  - **Physics fits the core:** rain-driven ravine floods (Poyo ≈ 413–421 km², plus Poçalet–Saleta) onto an urban plain, with a lagoon boundary.
  - **Best available reference:** VHR on 31 Oct 10:22, plus a Landsat-8 view on 30 Oct 10:37 in AOI01.
  - **An independent 2D hydraulic study exists** (Vallés-Morán 2025) for qualitative comparison of dynamics: V-31 backwater, sub-hour response.

**Gaps that become scenarios (not blockers):**
- Albufera level and gate (gola) timing: {closed, open} at the sea boundary, with the lagoon inside the domain;
- datum chain (lagoon gauge / EGM2008 / sea): an offset sweep, given 6.3;
- rainfall: IMERG plus a gauge-informed bracket;
- crossings: {as DEM, culverts open};
- the Turia new channel as a wall, with one sensitivity run;
- drainage: {none, nominal}, with low priority (it matters for duration, not the peak).

**Gaps that limit claims:** EMS traces are a maximum-extent proxy with unknown detection limits, and only 0.84 km² was still water at image time. There are no tributary gauges. Bridges and culverts are unresolved at 30 m.

### Estimated needs for Valencia (basis stated; extrapolated, not measured)
| Quantity | Estimate | Basis |
|---|---|---|
| Active domain | 550–800 km² | Poyo 421 km² (MERIT) + Poçalet–Saleta + plain + lagoon. **DEM delineation pending.** HydroBASINS level 12 is wrong here (it assigns Paiporta to the Turia) |
| Cells at 30 m | 0.61–0.89 M | area / 900 m² |
| Simulated window | 60 h (29 Oct 00:00 → 31 Oct 12:00 UTC) | covers both reference acquisition times |
| Average step | 1.5–4 s → 54k–144k steps | CFL with α = 0.5, dx = 30 m: h 4 m and u 8 m/s give ≈ 1.05 s; shallow cells are capped by `hmin_cfl` (≈ 4.8 s) |
| Run time per member | **≈ 5–80 min** (amd64 emulated) | cells × steps / measured 27–108 M cell-steps/s (P0). SFINCS skips dry cells, so the real wet fraction decides |
| Peak memory per member | ≈ 0.25–0.4 GiB | P0 slope ≈ 0.37 KiB per cell + 28 MiB base, extrapolated about 10× beyond the measured range |
| Inputs | < 100 MB total | GEDTM30 window (~4 MB), FABDEM (~4 MB), IMERG / ERA5-Land (≪ 10 MB), EMS AOI01 m0 layer (size unknown; not yet downloaded), OSM crossings (a few MB) |
| Outputs per member (lean) | ≈ 20–30 MB | hmax + snapshots at 30 Oct 10:37 and 31 Oct 10:22 + gauge points; full hourly maps would be ≈ 0.4 GB uncompressed per member, so **avoid them** |
| Staged ensemble | A: 4 members (terrain {GEDTM30 raw m, FABDEM} × golas {closed, open}); B: +5 (rain bracket ×2, crossings ×2, Turia sensitivity); C: +10 documented-error terrain realisations on one configuration | about 19 members, **≈ 1.5–25 h compute, ≈ 0.4–0.6 GB** |

**Disk is the binding constraint: 1.3 GiB free.** Stage A fits with lean outputs. Before Stage C, free space or use external storage.

## 8. Open items for you
1. **Approve Valencia** as the first development case and Stage A (4 members, lean outputs).
2. **Datum:** decide whether to search further for the Albufera gauge datum and gola timing (CHJ / Ajuntament), or proceed with the offset sweep.
3. **Rain bracket:** accept the gauge-informed bracket method, or require radar or gauge data access first.
4. **Disk:** free space before Stages B–C.
5. **Native arm64 SFINCS build** (optional): it removes the emulation upper bound on run times.
6. **Push `proto/flood-core`?** It is not pushed.
