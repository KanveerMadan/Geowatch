# M1 fluvial: every result, with its source

- Every number here is in a CSV under `tables/`, with columns `source_file`, `source_commit` and `source_commit_date`.
- Commits are those that wrote the result file. "Run" is the `run_utc` recorded inside the result.
- The method is in `METHOD.md`, the limits in `LIMITS.md`, the regeneration commands in `REPRODUCE.md`.

## Summary
| # | Test | Events | Result | Verdict | Source (commit, run) |
|---|---|---|---|---|---|
| R1 | Round 1: an **older AOI-wide scalar method** (now removed), pooled over sites | 9 JRC-recurrent-water sites | pooled AUC **0.4476** | failed | `result_2026-10-28.json` (`78c5031`, run 2026-10-28 12:39 UTC) |
| R2 | Round 2: **current per-pixel method**, pre-registered, tuned on 2 events, held out on the rest | Hanoi, Kolonnawa (qualifying); Nysa, Hue (did not qualify) | **mean 0.8579** (Hanoi 0.9162, Kolonnawa 0.7996); bar 0.70 | **validated** | `result_round2_2026-10-28.json` (`2832dc8`, run 2026-10-28 18:04 UTC) |
| R4 | Round 4: the same configuration re-tested, nothing tuned | Bihar, Assam, Pakistan (Sindh) | **mean 0.5365** (0.6425, 0.3878, 0.5791) | failed → scope narrowed | `result_round4_2026-10-30.json` (`21d645c`, run 2026-10-30 19:27 UTC) |
| B | Baselines: fluvial vs HAND, JRC occurrence and distance to water on the same cells | 34 qualifying dev events (22 clusters) | beats the best baseline clearly on **5 of 34**; mean Δ vs HAND **+0.003** [−0.065, +0.066] | report (no verdict) | `experiments/flood_baselines/results/baselines.json` (`d1894e4`, run 2026-11-17 06:44 UTC) |

Round 3 did not test fluvial (pluvial, flash flood and waterlogging only).

## 1. Criteria were fixed before scoring: pre-registration hashes
Table: `tables/preregistration_hashes.csv`.

| Round | Pre-registration | SHA256 recorded in the result file | = file at its commit | = file now | Pre-reg commit (author date / committer date) | Run (UTC) | Result commit |
|---|---|---|---|---|---|---|---|
| 1 | `PREREGISTRATION.md` | `d4b5e5639f77e4f466a194894a3e2a50273f319d175314ce4d7d435b20a91400` | ✓ | ✓ | `78c5031` 18:28 IST / 18:28 IST, 2026-10-28 (same commit as the result) | 2026-10-28 12:39 | `78c5031` |
| 2 | `PREREGISTRATION_ROUND2.md` | `f2ab3c744ac26336489a51e0645e7146b3b5860ec733ff0ff76cbd193a30f406` | ✓ | ✓ | `3692894` **19:34 IST** / 23:53 IST, 2026-10-28 | 2026-10-28 18:04 (23:34 IST) | `2832dc8` |
| 3 | `PREREGISTRATION_ROUND3.md` (no fluvial) | `930fc2303d1a1e1b84ede7843d4027411251601f54ea0232677b1bd17518b37b` | ✓ | ✓ | `56a875b` 11:29 IST / 12:37 IST, 2026-10-29 | 2026-10-29 06:59 (12:29 IST) | `d9a3ebd` |
| 4 | `PREREGISTRATION_ROUND4.md` | `4555ce1a4ff062b54dabd763fafdc8db4c295c7d535dc208796be07b943fea86` | ✓ | ✓ | `a772336` **20:12 IST** / 20:12 IST, 2026-10-30 | 2026-10-30 19:27 (00:57 IST, 10-31) | `21d645c` |

**What this shows:**
- Each harness hashed its pre-registration at run time (`harness_round2.py:432`, `harness_round4.py:443`).
- The recorded hash equals the file in the commit that first added it, and the file is unchanged since. So the criteria applied are byte-for-byte the committed text.

**What it does not show by itself:**
- **Timing.** For round 2 and round 4, the pre-registration's **author date** is 4.0 h (round 2) and 4.75 h (round 4) before the run.
  - Round 4's committer date is also before the run.
  - Round 2's commit was rewritten after the run (committer date 23:53 IST, after the 23:34 IST run). Its author date and content hash are unchanged.
- Git dates are self-recorded, not third-party timestamps.
- Round 1's pre-registration was committed together with its result. Its only timing evidence is its own statement, "written before the harness computed any reference or score". Round 1's method has since been removed.

## 2. Round 2: pre-registration and result (the validation)
Pre-registration: `experiments/flood_validation/PREREGISTRATION_ROUND2.md` (sha256 above).
- **Bar:** mean within-event AUC over qualifying held-out events ≥ 0.70.
- At least 2 qualifying held-out events are required.
- Each event needs at least 50 flooded and at least 50 dry cells.
- Weights may change only on tuning events.

**Tuning** (`tables/round2_fluvial_tuning.csv`):

| `river_size` weight | Faenza | Encantado | Mean | Chosen |
|---|---|---|---|---|
| 0 (pre-registered default, HAND only) | 0.6866 | 0.7786 | 0.7326 | |
| 0.25 | 0.7778 | 0.8119 | 0.7949 | |
| 0.5 | 0.7827 | 0.8267 | 0.8047 | |
| **1.0** | 0.7872 | 0.8302 | **0.8087** | ✓ |

**Held out, scored once with the chosen weights** (`tables/round2_fluvial_heldout.csv`):

| Event | Date | Reference | Flooded / dry cells | AUC |
|---|---|---|---|---|
| Hanoi (Red River, Typhoon Yagi) | 2024-09-09 | Copernicus EMS EMSR754 AOI03, WorldView-3, 2024-09-14 | 940 / 13,776 | **0.9162** |
| Kolonnawa (Kelani Ganga, Colombo) | 2025-11-30 | Copernicus EMS EMSR851 AOI02, PlanetScope | 573 / 8,617 | **0.7996** |
| Nysa (Nysa Kłodzka) | 2024-09-14 | EMSR756 AOI03, Sentinel-1 | 2 / 17,782 | did not qualify |
| Hue (Perfume River) | 2025-10-29 | EMSR848 AOI06, GeoEye-1 | 10 / 12,668 | did not qualify |
| **Mean (2 qualifying)** | | | | **0.8579 ≥ 0.70 → validated** |

- Pooled held-out AUC, reported as a diagnostic only: 0.8851.
- The validated configuration and its scope are recorded in `analysis/contract.py:89-127`.

## 3. Round 4: re-test, and what it means for scope
- Pre-registration: `PREREGISTRATION_ROUND4.md`, "M1 fluvial: unchanged". The exact validated configuration was run, and nothing was tuned.
- Table: `tables/round4_fluvial_test.csv`.

| Event | Date | Reference | Flooded / dry cells | AUC |
|---|---|---|---|---|
| bihar_2026 (Kosi–Ganga at Kursela) | 2026-09-11 | Sentinel-1 change, 2026-09-12 (+1 d) | 8,923 / 8,786 | 0.6425 |
| assam_2026 (Dikhow at Nazira) | 2026-07-20 | Sentinel-1 change, 2026-07-22 (+2 d) | 5,327 / 13,059 | **0.3878** |
| pakistan_2022 (Sindh, Indus plain) | 2022-08-31 | UNOSAT FL20220808PAK, Sentinel-2 2022-08-31 | 10,153 / 7,570 | 0.5791 |
| **Mean (3 qualifying)** | | | | **0.5365 < 0.70 → failed** |

- Pooled diagnostic: 0.4714.
- All three AUCs reproduce exactly from cached arrays (`tables/baselines_reproduce_round4_fluvial.csv`).

**What it means.** The round-4 pre-registration fixed the consequence in advance (`PREREGISTRATION_ROUND4.md`, "Labels", M1):
- **The label stays as round 2 decided** (`validated`, through rule C70).
- **The scope note is narrowed.** `analysis/contract.py:108-125` now says the validation covers Hanoi and Kolonnawa (two Asian river cities). It explicitly does **not** extend to the Bihar, Upper Assam and Sindh events and regions.
- Whether the label itself should change is an open question for a person (C78, NEEDS FATE). It is not decided here.

So the paper can claim: a pre-registered pass on two held-out events, and a pre-registered fail on three South Asian monsoon-floodplain events. It cannot claim general validity.

## 4. Baselines: does fluvial add anything over trivial scores?
- Source: `experiments/flood_baselines/` at `d1894e4` (REPORT.md §A).
- All four scores are evaluated on the same cells of each of the **34 qualifying dev events**.
- Intervals:
  - per event: paired 990 m block bootstrap, 95 %;
  - means: cluster × block bootstrap.
- Tables:
  - `tables/baselines_per_event.csv`
  - `tables/baselines_fluvial_beats_best.csv`
  - `tables/baselines_means.csv`
  - `tables/baselines_group_members.csv`
- Figure: `figures/fig_a_per_event_auc.png`.

**Per event.** Fluvial is above the event's best baseline (chosen after the fact, which favours the baselines) on 14 of 34 events. It is **clearly** above (95 % CI of the paired difference above 0) on **5**:

| Event | Fluvial AUC | Best baseline (AUC) | Fluvial − best [95 % CI] | Notes |
|---|---|---|---|---|
| kyaukpyu | 0.897 | HAND (0.690) | **+0.208** [+0.044, +0.287] | round-2 coastal box, EMS EMSR661 AOI02 |
| kolonnawa | 0.800 | HAND (0.606) | **+0.194** [+0.063, +0.317] | **round-2 held-out fluvial event** |
| nam_dinh | 0.775 | dist. to water (0.628) | **+0.147** [+0.019, +0.257] | round-4 waterlogging tuning box, EMS EMSR754 AOI07 |
| paiporta | 0.686 | dist. to water (0.546) | **+0.140** [+0.056, +0.223] | **alias of round-4 test event valencia_2024** (same EMS product) |
| encantado | 0.830 | HAND (0.779) | **+0.052** [+0.017, +0.097] | **round-2 fluvial tuning event** |

- Two of the five "best baselines" are distance to water, not HAND. The five are wins over the **best** of the three.
- The ROC curves are in `figures/fig_b_roc_five_wins.png`. Its 20 AUCs were recomputed from cached cells and match the stored values exactly (`tables/figure_auc_check.csv`).

**Means** (`tables/baselines_means.csv`):

| Event set | Events / clusters | Fluvial | HAND | JRC occ. | Dist. water | Fluvial − HAND | Fluvial − JRC | Fluvial − dist. |
|---|---|---|---|---|---|---|---|---|
| All qualifying | 34 / 22 | 0.670 [0.621, 0.715] | 0.667 [0.615, 0.720] | 0.617 | 0.616 | +0.003 [−0.065, +0.066] | +0.053 [−0.033, +0.127] | +0.055 [−0.025, +0.120] |
| Excl. round-4 test events + aliases | 22 / 17 | 0.709 [0.635, 0.769] | 0.684 [0.612, 0.759] | 0.661 | 0.674 | +0.024 [−0.076, +0.098] | +0.048 [−0.067, +0.148] | +0.035 [−0.073, +0.141] |
| Excl. JRC-circular references | 29 / 18 | 0.655 [0.591, 0.709] | 0.637 [0.587, 0.682] | 0.551 | 0.558 | +0.018 [−0.055, +0.076] | **+0.104** [+0.022, +0.188] | **+0.098** [+0.028, +0.172] |
| **Excl. both (cleanest)** | **17 / 12** | 0.694 [0.608, 0.759] | 0.637 [0.573, 0.708] | 0.561 | 0.592 | +0.056 [−0.036, +0.129] | **+0.133** [+0.035, +0.234] | +0.102 [−0.011, +0.207] |
| Fluvial-mechanism events, excl. round-4 test | 4 / 4 | 0.833 [0.758, 0.898] | 0.638 | 0.603 | 0.706 | **+0.195** [+0.061, +0.360] | **+0.230** [+0.106, +0.325] | **+0.128** [+0.015, +0.249] |

**The "22-event clean subset" and the 17.**
- The 22 exclude round-4 test events and their aliases. The 22 still contain the five JRC-circular events (A3 in the baselines report; `LIMITS.md` §2).
- With those five removed as well, **17 events in 12 clusters** remain. That is the cleanest set, and the one this pack recommends quoting.
- On the 17, fluvial clearly wins on **4** events (kyaukpyu, kolonnawa, nam_dinh, encantado).

**Plain reading:**
- Fluvial is **not** distinguishable from HAND alone on average, on any event set except the 4 fluvial-mechanism events.
- Those 4 (Hanoi, Kolonnawa, Faenza, Encantado) are round 2's own events. Two of them were used to choose the weights (`LIMITS.md` §3).
- Fluvial does clearly beat the JRC-occurrence baseline once the circular references are removed.

## 5. Figures
- `figures/fig_a_per_event_auc.{png,svg}`: per-event AUC with blocked 95 % CIs for fluvial, HAND, JRC occurrence and distance to water, on all 34 events. The marks are ★ clear win, † round-4 test or alias, ‡ JRC-circular reference.
- `figures/fig_b_roc_five_wins.{png,svg}`: ROC curves for the five clear wins.
- `figures/fig_c_maps_hanoi_assam.{png,svg}`: fluvial score, HAND and the observed reference for Hanoi (best round-2 held-out, AUC 0.916) and Assam (worst round-4 test, 0.388). Cell counts and AUCs are in `tables/figure_c_maps.csv`.
