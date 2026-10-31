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

### c6 Terrain error at 30 m (8 realisations per amplitude; correlated noise, 90 m correlation length, which is **assumed, not measured**)
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

## 4. Proposed real development cases (P1), selection not run

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
