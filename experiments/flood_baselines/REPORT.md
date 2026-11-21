# Flood baselines and case screening (exp/flood-baselines)

Experiments only. No production code, label, reference, verdict, pre-registration or UI was changed. Round 4b was not run. No reserved unit was read: `events.gate` refuses anything whose registry role is not `dev` before any array is opened. Every number below comes from `results/baselines.json`; `results/tables.md` has the full set, including every sensitivity and mechanism group.

**Part A is a report, not a stop rule.**

---

## Part A. Three baselines beside the four current modules

### A1. What was scored
- **Events.** The registry gives 40 dev units in 28 link-clusters (clusters are joined by any registry link).
  - 34 units qualify under the harness rule: at least 50 flooded and at least 50 dry evaluation cells (`MIN_FLOODED_CELLS`, `MIN_DRY_CELLS`).
  - The 6 that do not qualify: guatemala, hue, jakarta_gfd_3280, kastelli, kigali, nysa.
  - The 34 fall into 22 clusters.
  - References and evaluation blocks are the cached round 2–4 ones. Nothing about them was rebuilt or re-chosen.
- **Cells.** All seven scores use the same 30 m cells per event: the reference's valid cells where every primary score is defined.
- **Baselines** (higher = more flood-prone):
  - `hand`: −MERIT HAND (m).
  - `occurrence`: JRC GSW 1.4 occurrence (%), 1984–2021.
  - `dist_water`: −distance (m) to OSM waterways and water areas or JRC permanent water, using the project's existing `JRC_PERMANENT_WATER_OCCURRENCE_PCT`.
    - The distance is computed on the box plus a 2 km margin and capped there.
    - Basis for 2 km: half the 4 km box side. Water just outside the box is found, and nothing further away changes a within-box ranking much.
- **Modules.** The production functions with their **current config defaults** (as agreed):
  - pluvial: c_perv 0.30 (`configs/pluvial_constants.py:83`);
  - waterlogging: weights {1, 1, 1, 1} (`configs/waterlogging_constants.py:69`);
  - flash flood: {hand_max_m 10, power_exponent 1.0} (`configs/flash_flood_constants.py:92`);
  - fluvial: the validated config.
- **Sensitivity runs:**
  - `occurrence_pre`: JRC monthly water frequency from the years before the event only;
  - `dist_osm_only`: distance to OSM water alone;
  - `<module>_r4chosen`: the parameters round 4's tuning chose (pluvial c_perv 0.5; waterlogging low_relief 0.5; flash {5.0, 0.5}).
- **Check on the scoring path.** Round 4's cached test arrays, run through its chosen parameters and its own `event_auc`, reproduce **11 of 11** pinned per-event AUCs exactly. These are already-published numbers re-read, not new test scoring.

### A2. Spatially blocked bootstrap: block size and why
- **Why block.** Neighbouring 30 m cells are not independent. A cell-level bootstrap would give intervals that are far too narrow.
- **How the block size was chosen.** For each qualifying event I measured the isotropic correlogram of the reference flood indicator on valid cells (`blocks.correlation_range`). The range is the first lag where the correlation falls to 0.05, the "practical range" convention for an exponential variogram (Journel & Huijbregts 1978). Results over the 34 events:
  - median **750 m**;
  - quartiles 368–960 m;
  - maximum 1,950 m (paiporta);
  - 26 of 34 at or below 990 m.
- **Chosen block: 33 × 33 cells = 990 m**, just above the upper quartile. Sensitivity runs: 66 cells (1,980 m, which covers the maximum) and each event's own range.
- **Resampling.** 1,000 replicates (Efron & Tibshirani 1993), seed 20261114.
  - Tiles are resampled with replacement, **paired across all scores**, so every score and every difference sees the same resample.
- **Intervals:**
  - Per-event intervals are percentile 95%.
  - Means use a two-stage **cluster × block** bootstrap: resample link-clusters, then each member event's block replicates. Linked events (for example valencia_2024 and paiporta) therefore do not count as independent.
- **Block-size sensitivity.** Across the 135 event × module comparisons (pluvial has 33), the number whose difference from the best baseline has a 95% interval above 0:
  - 8 at 990 m;
  - 7 at 1,980 m;
  - 12 at each event's own range (often below 990 m, so narrower intervals).

  The conclusions below do not depend on the choice.

### A3. A problem in the reference data: five references are JRC occurrence itself (‡)
- **Which events.** For accra, capetown, dhaka, hcmc and nusantara (round 2, waterlogging), the cached reference *is* "JRC/GSW1_4 occurrence, recurrent 5–80 %".
- **What that does to the baselines:**
  - On these events the `occurrence` baseline is the reference's own source: AUC 1.000 [1.000, 1.000] by construction.
  - `dist_water` is inflated too, because permanent water (occurrence ≥ 80 %) borders the recurrent band.
- **How they are handled.** These events stay in "all" (nothing was dropped or relabelled). They are shown with ‡, and every summary is also given without them.
- **The other 29 references** are Copernicus EMS, UNOSAT or Sentinel-1 change maps.
- **This is the main reason** JRC occurrence looks strong in the waterlogging group.
- **Separate issue, not mine to change:** a module scored against these five references is scored against recurrent surface water, not an observed event flood. For the ledger.

### A4. Per event (AUC [blocked 95% CI], 990 m blocks)
- † marks a round-4 test event or a block-level alias of one (paiporta = valencia_2024's EMS product; derna and volos via the same-storm link).
- ‡ marks a JRC-occurrence reference (A3).
- "best baseline" is the best of the three **chosen after seeing the event**. This favours the baselines, which is deliberate.

| event | round | mechanism | flooded / dry cells | HAND | JRC occ. | dist. water | fluvial | pluvial | waterlog. | flash | best baseline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| accra ‡ | round2 | waterlogging | 138 / 14001 | 0.895 [0.820, 0.968] | 1.000 [1.000, 1.000] | 0.963 [0.931, 0.980] | 0.856 [0.743, 0.924] | 0.738 [0.616, 0.862] | 0.933 [0.872, 0.989] | 0.897 [0.808, 0.940] | JRC occ. |
| assam_2026 † | round4/test | fluvial, waterlogging | 5327 / 13059 | 0.750 [0.709, 0.788] | 0.522 [0.502, 0.553] | 0.262 [0.212, 0.355] | 0.388 [0.320, 0.499] | 0.734 [0.699, 0.766] | 0.419 [0.352, 0.524] | 0.505 [0.433, 0.590] | HAND |
| bad_neuenahr | round2 | flash_flood | 206 / 10966 | 0.713 [0.597, 0.791] | 0.500 [0.500, 0.500] | 0.701 [0.575, 0.786] | 0.692 [0.568, 0.778] | 0.607 [0.542, 0.650] | 0.696 [0.565, 0.779] | 0.710 [0.574, 0.796] | HAND |
| beira | round2 | coastal | 661 / 18545 | 0.522 [0.472, 0.572] | 0.576 [0.535, 0.608] | 0.585 [0.487, 0.655] | 0.466 [0.406, 0.543] | 0.445 [0.414, 0.471] | 0.583 [0.519, 0.631] | 0.511 [0.440, 0.569] | dist. water |
| belize_city | round4/tuning | pluvial | 1074 / 16622 | 0.646 [0.419, 0.761] | 0.500 [0.500, 0.500] | 0.364 [0.186, 0.631] | 0.609 [0.485, 0.897] | 0.466 [0.333, 0.580] | 0.701 [0.571, 0.785] | 0.685 [0.556, 0.763] | HAND |
| bihar_2026 † | round4/test | fluvial | 8923 / 8786 | 0.603 [0.535, 0.689] | 0.642 [0.532, 0.726] | 0.529 [0.391, 0.647] | 0.642 [0.560, 0.716] | 0.602 [0.566, 0.639] | 0.673 [0.575, 0.749] | 0.610 [0.537, 0.683] | JRC occ. |
| black_river | round2 | coastal | 1260 / 10746 | 0.719 [0.604, 0.798] | 0.506 [0.493, 0.534] | 0.606 [0.456, 0.715] | 0.712 [0.580, 0.802] | 0.736 [0.678, 0.813] | 0.709 [0.576, 0.800] | 0.690 [0.558, 0.788] | HAND |
| capetown ‡ | round2 | waterlogging | 161 / 25526 | 0.950 [0.919, 0.982] | 1.000 [1.000, 1.000] | 0.960 [0.915, 0.985] | 0.538 [0.407, 0.682] | 0.530 [0.405, 0.658] | 0.989 [0.976, 0.998] | 0.882 [0.832, 0.931] | JRC occ. |
| choloma | round4/tuning | flash_flood | 4604 / 12374 | 0.614 [0.505, 0.707] | 0.573 [0.540, 0.599] | 0.294 [0.205, 0.393] | 0.489 [0.348, 0.629] | 0.571 [0.504, 0.635] | 0.573 [0.428, 0.694] | 0.436 [0.317, 0.556] | HAND |
| derna † | round2 | flash_flood | 408 / 9239 | 0.617 [0.516, 0.682] | 0.496 [0.490, 0.501] | 0.622 [0.495, 0.704] | 0.633 [0.503, 0.711] | 0.525 [0.501, 0.559] | 0.591 [0.504, 0.649] | 0.607 [0.498, 0.678] | dist. water |
| derna_2023 † | round4/test | flash_flood | 1767 / 14275 | 0.961 [0.939, 0.977] | 0.500 [0.500, 0.500] | 0.746 [0.522, 0.940] | 0.977 [0.946, 0.991] | 0.595 [0.528, 0.719] | 0.829 [0.764, 0.862] | 0.833 [0.786, 0.861] | HAND |
| dhaka ‡ | round2 | waterlogging | 992 / 14663 | 0.790 [0.727, 0.847] | 1.000 [1.000, 1.000] | 0.962 [0.935, 0.976] | 0.861 [0.766, 0.923] | 0.681 [0.620, 0.770] | 0.797 [0.643, 0.903] | 0.924 [0.881, 0.950] | JRC occ. |
| dharavi | round2 | pluvial, waterlogging | 489 / 7385 | 0.640 [0.565, 0.710] | 0.613 [0.487, 0.722] | 0.550 [0.435, 0.647] | 0.601 [0.498, 0.696] | 0.525 [0.451, 0.601] | 0.692 [0.567, 0.787] | 0.648 [0.532, 0.737] | HAND |
| dubai_2024 † | round4/test | pluvial | 591 / 17889 | 0.497 [0.456, 0.543] | 0.487 [0.467, 0.507] | 0.537 [0.469, 0.612] | 0.489 [0.447, 0.536] | 0.493 [0.455, 0.535] | 0.494 [0.451, 0.541] | 0.501 [0.459, 0.544] | dist. water |
| encantado | round2 | fluvial | 725 / 16160 | 0.779 [0.684, 0.871] | 0.559 [0.516, 0.653] | 0.726 [0.645, 0.873] | 0.830 [0.745, 0.913] | 0.489 [0.399, 0.583] | 0.764 [0.656, 0.872] | 0.734 [0.624, 0.872] | HAND |
| faenza | round2 | fluvial | 219 / 8427 | 0.687 [0.530, 0.810] | 0.500 [0.500, 0.500] | 0.771 [0.667, 0.886] | 0.787 [0.640, 0.897] | 0.714 [0.694, 0.743] | 0.731 [0.564, 0.852] | 0.849 [0.722, 0.939] | dist. water |
| fort_myers_beach | round2 | coastal | 578 / 5378 | 0.658 [0.609, 0.710] | 0.581 [0.549, 0.613] | 0.513 [0.433, 0.585] | 0.463 [0.421, 0.533] | 0.589 [0.543, 0.635] | 0.680 [0.623, 0.741] | 0.438 [0.385, 0.514] | HAND |
| hai_phong | round4/tuning | pluvial | 86 / 8144 | 0.871 [0.814, 0.914] | 0.860 [0.804, 0.923] | 0.793 [0.671, 0.910] | 0.596 [0.242, 0.898] | 0.630 [0.507, 0.814] | 0.418 [0.318, 0.546] | 0.161 [0.078, 0.254] | HAND |
| hanoi | round2 | fluvial | 940 / 13776 | 0.481 [0.324, 0.633] | 0.855 [0.804, 0.922] | 0.830 [0.764, 0.896] | 0.916 [0.831, 0.972] | 0.477 [0.420, 0.583] | 0.810 [0.724, 0.909] | 0.587 [0.356, 0.769] | JRC occ. |
| hcmc ‡ | round2 | waterlogging | 505 / 136019 | 0.847 [0.764, 0.891] | 1.000 [1.000, 1.000] | 0.937 [0.858, 0.967] | 0.682 [0.524, 0.788] | – | 0.721 [0.528, 0.942] | 0.784 [0.712, 0.852] | JRC occ. |
| himachal_2023 † | round4/test | flash_flood | 520 / 18227 | 0.534 [0.486, 0.593] | 0.505 [0.500, 0.514] | 0.492 [0.436, 0.555] | 0.546 [0.495, 0.603] | 0.515 [0.476, 0.557] | 0.422 [0.376, 0.469] | 0.510 [0.495, 0.533] | HAND |
| kerala_2018 † | round4/test | waterlogging | 10866 / 7224 | 0.709 [0.652, 0.756] | 0.786 [0.727, 0.846] | 0.270 [0.220, 0.320] | 0.463 [0.394, 0.550] | 0.630 [0.544, 0.692] | 0.773 [0.715, 0.831] | 0.576 [0.476, 0.686] | JRC occ. |
| kolonnawa | round2 | fluvial | 573 / 8617 | 0.606 [0.499, 0.724] | 0.498 [0.495, 0.500] | 0.496 [0.322, 0.778] | 0.800 [0.689, 0.898] | 0.751 [0.672, 0.787] | 0.672 [0.562, 0.771] | 0.595 [0.462, 0.766] | HAND |
| kyaukpyu | round2 | coastal | 381 / 8869 | 0.690 [0.145, 0.792] | 0.448 [0.409, 0.477] | 0.659 [0.137, 0.840] | 0.897 [0.217, 0.947] | 0.607 [0.490, 0.840] | 0.719 [0.142, 0.828] | 0.653 [0.115, 0.878] | HAND |
| milagro | round4/tuning | pluvial | 154 / 17535 | 0.698 [0.414, 0.812] | 0.498 [0.494, 0.500] | 0.372 [0.093, 0.650] | 0.763 [0.558, 0.932] | 0.849 [0.595, 0.879] | 0.740 [0.668, 0.862] | 0.426 [0.263, 0.567] | HAND |
| nam_dinh | round4/tuning | waterlogging | 2733 / 12502 | 0.439 [0.308, 0.562] | 0.560 [0.502, 0.630] | 0.628 [0.504, 0.761] | 0.775 [0.663, 0.874] | 0.438 [0.356, 0.507] | 0.744 [0.669, 0.801] | 0.637 [0.560, 0.732] | dist. water |
| nusantara ‡ | round2 | waterlogging | 1754 / 43199 | 0.738 [0.656, 0.844] | 1.000 [1.000, 1.000] | 0.938 [0.911, 0.955] | 0.860 [0.802, 0.916] | 0.652 [0.623, 0.695] | 0.916 [0.885, 0.956] | 0.796 [0.734, 0.882] | JRC occ. |
| paiporta † | round2 | flash_flood | 3683 / 14103 | 0.501 [0.376, 0.623] | 0.500 [0.500, 0.500] | 0.546 [0.428, 0.652] | 0.686 [0.581, 0.778] | 0.473 [0.425, 0.519] | 0.504 [0.379, 0.638] | 0.528 [0.402, 0.690] | dist. water |
| pakistan_2022 † | round4/test | fluvial | 10153 / 7570 | 0.514 [0.431, 0.603] | 0.465 [0.402, 0.506] | 0.440 [0.346, 0.527] | 0.579 [0.482, 0.683] | 0.531 [0.478, 0.581] | 0.482 [0.381, 0.585] | 0.494 [0.397, 0.601] | HAND |
| sittwe | round2 | coastal | 216 / 11121 | 0.806 [0.733, 0.871] | 0.462 [0.439, 0.482] | 0.324 [0.206, 0.588] | 0.862 [0.736, 0.920] | 0.469 [0.362, 0.552] | 0.837 [0.750, 0.906] | 0.681 [0.545, 0.926] | HAND |
| sylhet_2022 † | round4/test | waterlogging | 8872 / 8564 | 0.730 [0.680, 0.776] | 0.553 [0.510, 0.590] | 0.387 [0.338, 0.436] | 0.542 [0.487, 0.613] | 0.650 [0.611, 0.688] | 0.688 [0.634, 0.740] | 0.632 [0.551, 0.713] | HAND |
| thai_binh | round4/tuning | waterlogging | 506 / 16402 | 0.271 [0.137, 0.425] | 0.441 [0.389, 0.487] | 0.858 [0.756, 0.958] | 0.538 [0.380, 0.690] | 0.323 [0.264, 0.384] | 0.269 [0.135, 0.435] | 0.771 [0.679, 0.881] | dist. water |
| valencia_2024 † | round4/test | flash_flood, pluvial | 2847 / 14924 | 0.706 [0.610, 0.783] | 0.500 [0.500, 0.500] | 0.689 [0.580, 0.822] | 0.699 [0.535, 0.810] | 0.553 [0.511, 0.609] | 0.693 [0.589, 0.771] | 0.741 [0.648, 0.829] | HAND |
| volos † | round4/tuning | flash_flood | 10911 / 6872 | 0.518 [0.415, 0.623] | 0.500 [0.500, 0.500] | 0.581 [0.448, 0.705] | 0.560 [0.403, 0.678] | 0.514 [0.472, 0.562] | 0.560 [0.425, 0.663] | 0.475 [0.394, 0.552] | dist. water |

**Input gaps:**
- **belize_city:** IMERG rain intensity is unavailable, so flash flood uses the 20 mm/h fallback (`FLASH_POWER_INTENSITY_FALLBACK_MM_H`, C73).
- **hcmc: pluvial missing.** Its box is about 9× the typical size (136k dry cells against about 15k typical).
  - The pluvial build was killed at the planned 1 h limit, then failed a single retry at a 2 h limit (double the plan, to leave nothing out).
  - Both times it stalled after the Open Buildings count, while fetching footprints over the margin box.
  - hcmc is a ‡ event, so the clean groups are unaffected.
- **paiporta:** the first pluvial attempt failed on a network loss while the Mac slept. One retry succeeded, using OSM building footprints.
- **Building footprints for pluvial** came from Open Buildings v3 on 19 units and from OSM buildings on 9 (bad_neuenahr, derna, derna_2023, faenza, fort_myers_beach, kyaukpyu, paiporta, sittwe, volos). This is the production fallback order. The other 5 (belize_city, dubai_2024, hai_phong, milagro, valencia_2024) reuse round 4's cached pluvial inputs on an identical box.
- **OSM water** is complete on all 34 (Overpass refresh passes 2 and 4).

### A5. Means (cluster × block 95% CI)
| score | all (34 / 22 clusters) | excl. round-4 test (22 / 17) | excl. JRC-ref (29 / 18) | **clean: excl. both (17 / 12)** |
|---|---|---|---|---|
| hand | 0.667 [0.615, 0.720] | 0.684 [0.612, 0.759] | 0.637 [0.587, 0.682] | 0.637 [0.573, 0.708] |
| occurrence | 0.617 [0.558, 0.690] | 0.660 [0.577, 0.756] | 0.551 [0.507, 0.595] | 0.561 [0.505, 0.617] |
| dist_water | 0.616 [0.544, 0.700] | 0.674 [0.571, 0.780] | 0.558 [0.471, 0.641] | 0.592 [0.476, 0.700] |
| fluvial | 0.670 [0.621, 0.715] | 0.709 [0.635, 0.769] | 0.655 [0.591, 0.709] | 0.694 [0.608, 0.759] |
| pluvial | 0.579 [0.537, 0.630] (n=33) | 0.585 [0.529, 0.658] (n=21) | 0.569 [0.530, 0.626] | 0.570 [0.512, 0.653] |
| waterlogging | 0.671 [0.621, 0.725] | 0.713 [0.645, 0.788] | 0.637 [0.592, 0.683] | 0.667 [0.610, 0.729] |
| flash_flood | 0.633 [0.586, 0.682] | 0.659 [0.591, 0.748] | 0.594 [0.553, 0.643] | 0.601 [0.536, 0.681] |

Mean ΔAUC, module − baseline:

| Δ | all | excl. round-4 test | excl. JRC-ref | **clean** |
|---|---|---|---|---|
| fluvial-hand | +0.003 [-0.065, +0.066] | +0.024 [-0.076, +0.098] | +0.018 [-0.055, +0.076] | +0.056 [-0.036, +0.129] |
| fluvial-occurrence | +0.053 [-0.033, +0.127] | +0.048 [-0.067, +0.148] | +0.104 [+0.022, +0.188] | +0.133 [+0.035, +0.234] |
| fluvial-dist_water | +0.055 [-0.025, +0.120] | +0.035 [-0.073, +0.141] | +0.098 [+0.028, +0.172] | +0.102 [-0.011, +0.207] |
| pluvial-hand | -0.083 [-0.129, -0.035] (n=33) | -0.091 [-0.155, -0.027] (n=21) | -0.068 [-0.108, -0.021] | -0.068 [-0.133, +0.006] |
| pluvial-occurrence | -0.027 [-0.094, +0.045] (n=33) | -0.059 [-0.157, +0.052] (n=21) | +0.018 [-0.050, +0.096] | +0.009 [-0.089, +0.133] |
| pluvial-dist_water | -0.027 [-0.122, +0.073] (n=33) | -0.076 [-0.193, +0.057] (n=21) | +0.011 [-0.102, +0.136] | -0.023 [-0.167, +0.129] |
| waterlogging-hand | +0.004 [-0.026, +0.037] | +0.029 [-0.005, +0.060] | -0.000 [-0.033, +0.031] | +0.029 [+0.003, +0.058] |
| waterlogging-occurrence | +0.054 [-0.010, +0.117] | +0.053 [-0.039, +0.150] | +0.085 [+0.018, +0.158] | +0.106 [+0.001, +0.213] |
| waterlogging-dist_water | +0.056 [-0.034, +0.136] | +0.039 [-0.081, +0.162] | +0.079 [-0.017, +0.183] | +0.074 [-0.070, +0.213] |
| flash_flood-hand | -0.035 [-0.067, -0.001] | -0.025 [-0.073, +0.021] | -0.043 [-0.081, -0.003] | -0.037 [-0.093, +0.019] |
| flash_flood-occurrence | +0.015 [-0.043, +0.079] | -0.002 [-0.083, +0.100] | +0.043 [-0.023, +0.122] | +0.040 [-0.054, +0.160] |
| flash_flood-dist_water | +0.017 [-0.064, +0.084] | -0.015 [-0.112, +0.085] | +0.036 [-0.048, +0.123] | +0.008 [-0.113, +0.131] |

Mechanism groups (registry `uses`) and their round-4-excluded and clean variants are in `results/tables.md`. They have 2–11 events, and their intervals are wide.

### A6. Per module: does it beat the best baseline on any event, and by how much?
- **Counts.** "Beats" means the module's AUC is above the event's post-hoc best baseline. "Clearly" means the paired 990 m-block 95% interval of the difference is above 0.
- **Chance level.** With about 34 events, roughly one "clear" win per module is about what chance alone gives (one-sided 2.5% × 34 ≈ 0.85; events are not fully independent, so this is a rough guide).

**Fluvial: yes, on several events.**
- It beats the best baseline on 14 of 34 events, **5 clearly**:

  | event | margin | best baseline | 95% CI |
  |---|---|---|---|
  | kyaukpyu | **+0.208** | HAND | [0.044, 0.287] |
  | kolonnawa | +0.194 | HAND | [0.063, 0.317] |
  | nam_dinh | +0.147 | dist. water | [0.019, 0.257] |
  | paiporta † | +0.140 | dist. water | [0.056, 0.223] |
  | encantado | +0.052 | HAND | [0.017, 0.097] |

- Median margin −0.021.
- On the mean it is level with HAND on all 34 (+0.003 [−0.065, 0.066]) and ahead but not clearly on the clean 17 (+0.056 [−0.036, 0.129]).
- It is clearly ahead of JRC occurrence on the clean 17 (+0.133 [0.035, 0.234]).
- On the fluvial events excluding round-4 test events (4), it is clearly ahead of all three baselines: +0.195 over HAND, +0.230 over occurrence, +0.128 over dist. water.

**Pluvial: no, beyond chance.**
- It beats the best baseline on 4 of 33 events, **1 clearly**: kolonnawa +0.145 [0.002, 0.260] vs HAND.
- The largest margin is milagro +0.151 [−0.005, 0.289].
- Median margin −0.106.
- **HAND beats pluvial on average:** −0.083 [−0.129, −0.035] on all 33 events; −0.068 [−0.133, 0.006] on the clean 17.

**Waterlogging: no, beyond chance, on single events. Small edge over HAND on the clean set.**
- It beats the best baseline on 9 of 34 events, **1 clearly**: belize_city +0.054 [0.014, 0.150] vs HAND.
- The largest margin is nam_dinh +0.116 [−0.027, 0.232].
- Median margin −0.026.
- Against HAND on the mean: level on all 34 (+0.004 [−0.026, 0.037]); clearly but slightly ahead on the clean 17 (+0.029 [0.003, 0.058]).

**Flash flood: no, beyond chance.**
- It beats the best baseline on 5 of 34 events, **1 clearly**: faenza +0.078 [0.003, 0.126] vs dist. water.
- Median margin −0.075.
- **HAND beats flash flood on average:** −0.035 [−0.067, −0.001] on all 34; −0.037 [−0.093, 0.019] on the clean 17.

**Excluding round-4 test events** (22 events), the counts become:

| module | events scored | clear wins | largest margin |
|---|---|---|---|
| fluvial | 22 | 4 | kyaukpyu +0.208 |
| pluvial | 21 | 1 | milagro +0.151 |
| waterlogging | 22 | 1 | nam_dinh +0.116 |
| flash flood | 22 | 1 | faenza +0.078 |

On the clean 17 the counts are the same (4 / 1 / 1 / 1).

**Plain reading:** HAND is the baseline to beat. Only fluvial clearly beats the best baseline on more events than chance would give. Pluvial and flash flood are, on average, worse than HAND alone.

### A7. Sensitivity
- **Round 4's chosen parameters instead of the defaults** change the mean AUC on all 34 by at most 0.010:

  | module | defaults | round-4 chosen |
  |---|---|---|
  | pluvial | 0.579 | 0.583 |
  | waterlogging | 0.671 | 0.661 |
  | flash flood | 0.633 | 0.638 |

  None of the statements in A6 changes.
- **`occurrence_pre`** (no post-event years): 0.620 against 0.617 for `occurrence` on all 34. Post-event leakage into the occurrence baseline is negligible. The circularity in A3 is the real issue.
- **`dist_osm_only`:** 0.593 against 0.616 on all 34. JRC permanent water adds a little to the distance baseline.
- **Block size:** see A2.

### A8. Candidate finding (for the ledger; not edited here, next number C82)
- **What differs.** Production config defaults are not the values round 4's tuning chose:

  | module | production default | round 4 chose |
  |---|---|---|
  | pluvial c_perv | 0.30 | 0.5 |
  | waterlogging low_relief weight | 1.0 | 0.5 |
  | flash flood {hand_max_m, power_exponent} | {10, 1.0} | {5, 0.5} |

- **Effect here:** small (A7).
- **Open question:** whether the defaults were meant to stay is a decision for the ledger. This report scores the defaults as "current", as agreed.
- **Second candidate:** the five round-2 waterlogging references are JRC occurrence itself (A3).

---

## Part B. Screening Valencia 2024 and Volos 2023 for the first real SFINCS case

Both are registry **dev** units: `valencia_2024` (alias `paiporta`) and `volos` (alias `derna`, `derna_2023`). Nothing was scored. The only new numbers are MERIT upstream areas from Earth Engine reductions (`screen_partb.py` → `results/screen_partb.json`). Everything else is cached EMS metadata (`../flood_core/screening/`) or a public source, cited.

"Volos 2023" is two different places:
- **Volos city**, where short torrents (Krafsidonas, Xirias, Anavros) flash-flooded on 5–6 Sep.
- **The Thessaly plain at Palamas**, where the registry unit's round 3/4 box actually sits (C72: the box rule moved it onto the mapped water), with Enipeas/Pineios plain flooding over the following two weeks.

Both are screened.

### B1. Side by side
| Item | Valencia (Poyo / Horta Sud) | Volos city torrents | Thessaly plain at Palamas (the registry box) |
|---|---|---|---|
| Upstream area (MERIT `upa`, max within radius) | Poyo **413 km²** at Paiporta (600 m), **421 km²** at the Albufera outlet (1.5 km); the box centre reads 309 km² (Poçalet–Saleta side) | **119 km²** (2 km of the mouths); a published 2D study uses **33.5 km²** for the catchment draining through the city ([EGU25-562](https://meetingorganizer.copernicus.org/EGU25/EGU25-562.html)) | **637 km²** within 2 km of the box, **1,492 km²** within 5 km; the Pineios carries **6,687 km²** at Larissa and **9,299 km²** near its mouth (4 km). The earlier screen's "Pineios at Larissa 144 km²" was a point off the main channel; superseded |
| Domain for a connected run | **550–800 km²** (Poyo + Poçalet–Saleta + plain + lagoon); headwaters inside, so no inflow boundary | **35–170 km²** (33.5 km² city catchment; 166 km² wider urban catchment in a SWAT/HEC-RAS study cited in the EGU search) | Full catchment to Larissa ≈ **6,700 km²** (7.4 M cells at 30 m), or a nested plain domain ≈ 1,500–2,500 km² with **inflow boundaries** on the Enipeas, upper Pineios and Karditsa tributaries |
| Rain | IMERG V07 and ERA5-Land, both verified readable in EE. Neither resolves Turís 771.8 mm / 24 h, 184.6 mm / 1 h (AEMET via press); a gauge-informed bracket is needed. AEMET radar/gauge access not verified | IMERG / ERA5-Land; Daniel totals of several hundred mm in 1–4 days. Station data (NOA meteo.gr / HNMS) access not verified | IMERG / ERA5-Land; about 360 mm mean over the Pineios basin in four days ([Water 2024](https://www.itia.ntua.gr/el/getfile/2451/1/documents/water-16-00980.pdf)) |
| River inflow (GloFAS) | **Not needed** (closed headwaters). The Turia new channel bounds the north and is treated as a wall, with one sensitivity run | Not needed | **Needed** and the weak point. GloFAS v4 (0.05°, 1979–present) requires an **EWDS registration** ([EWDS](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical)) we do not have. Gauges (HIMIOFoTS, 7 stations) exist but access and survival through the peak are unverified. Published peak flows conflict: ≈1,950 m³/s near the mouth vs 2,980 m³/s "along the Pineios" ([Water 2024](https://www.itia.ntua.gr/el/getfile/2451/1/documents/water-16-00980.pdf); [Remote Sensing 2025](https://mdpi.com/2072-4292/17/10/1750)) |
| Coast (tide / surge) | Albufera lagoon and its gola outlets to the sea. Microtidal Mediterranean (~0.2 m range, assumed standard); the lagoon rose ~1.0 m on 29 Oct, and the gauge datum was not found. Open sources: Puertos del Estado REDMAR (Valencia port), Copernicus Marine Med physics, SHELDA (CC BY 4.0) ([Ocean Sci. 2022](https://os.copernicus.org/articles/18/997/2022/); [ESSD preprint](https://essd.copernicus.org/preprints/essd-2025-767/essd-2025-767-manuscript-version2.pdf)) | Pagasetic Gulf at the torrent mouths; medicane surge not quantified. A Volos tide gauge (HNHS) was not found in open listings | Inland: none |
| Key infrastructure | **V-31 motorway** embankment backwater (2D study); A-7 and rail embankments; bridges and culverts unresolved at 30 m; urban drains small next to Poyo flows. Known from a published 2D study (Vallés-Morán 2025) | Culverted and channelised torrents through the city, plus bridge collapse on the Krafsidonas (press). No open inventory | Levees and embankments along the Pineios and Enipeas, irrigation channels, Lake Karla; **breaches reported**. No open levee dataset (audit gap) |
| Reference maps vs the peak | Peak ≈ 29 Oct evening (Poyo gauge 2,282 m³/s at 18:55, then failed). **AOI01 m0 Landsat-8, 30 Oct 10:37 (≈16 h after)**; S2 31 Oct 10:51; S1 31 Oct 18:02. **AOI03 Horta Sud VHR, 31 Oct 10:22 (≈40 h)**: 0.84 km² Flooded area plus 23.22 km² Flood trace, i.e. mostly a maximum-extent proxy | **None over the city**: no EMSR692 AOI covers Volos, and the town box holds 0.0 km² flooded or trace (cached layer). The 2D study gives no public map | Rich series: AOI01 m0 PAZ 5 Sep 16:31, m1 S1 6 Sep 04:39, m2 S1 7 Sep 16:25, m3 WorldView-3 9 Sep 09:31; **AOI02 Palamas** GeoEye-1 10 Sep then SPOT/WV2 12–19 Sep (six products). Plain peak ≈ 6–7 Sep (Larissa flooding from the evening of 6 Sep; [CIMA](https://www.cimafoundation.org/en/news/greece-floods-data-forecasts-and-scientific-analysis-of-the-event/)), so the VHR maps are **3–13 days later**, during recession |
| Terrain | GEDTM30 (raw metres, the units finding) or FABDEM at 30 m. **Open local LiDAR:** PNOA-LiDAR and MDT05/MDT02 from IGN/CNIG under **CC BY 4.0** ([INSPIRE MDT05 record](https://inspire-geoportal.ec.europa.eu/srv/api/records/spaignMDT05); [CNIG download centre](https://datos.gob.es/es/aplicaciones/centro-de-descargas)). Pre-event Poyo DTMs (2023 PNOA LiDAR) were used in post-DANA studies ([CSIC Poyo viewer](https://delegacion.comunitatvalenciana.csic.es/wp-content/uploads/2024/11/15-11-2024-DICV-Visor-barranco-Poyo.-CAS.pdf)) | GEDTM30 / FABDEM. Hellenic Cadastre DEMs (5 m 2007–09; 2 m and 25 m 2014–15) exist via its INSPIRE geoportal and open-data portal, **licence not found** ([EuroGeographics slides](https://eurogeographics.org/app/uploads/2022/06/5_GR-_Crowdsourced-and-open-data-in-the-Hellenic-cadastre-.pdf)). A newer national LiDAR programme exists; access unverified | as Volos city |
| Event dynamics | Sub-hour response; 8 m/s, > 4 m depth (2D study) | Flash flood first, then Pineios fluvial flooding two days later (EGU25-562) | Multi-day to two-week plain flood; area estimates 590–1,150 km² |

### B2. Licences of what a run would use
| Data | Licence | Status |
|---|---|---|
| IMERG V07 | NASA open data | verified readable (prototype P1 list) |
| ERA5 / ERA5-Land | Copernicus products licence (free, attribution) | verified readable; licence text not re-checked here |
| GloFAS v4 historical | CEMS-FLOODS conditions; **registration required** | not accessible (no EWDS account) |
| Copernicus EMS EMSR773 / EMSR692 | CEMS terms: free, attribution, information purposes | cached; Valencia AOI01 m0 layer not yet downloaded |
| GEDTM30 v1.2 | **not confirmed**: no licence statement in the Zenodo records or the PeerJ paper text returned by search; the group's older EDTM was CC BY ([Zenodo v1.2.0](https://zenodo.org/records/14900180)) | verified readable; **licence to check before publishing derived maps** |
| FABDEM | CC BY-NC-SA 4.0 (audit §5) | non-commercial only |
| PNOA-LiDAR, MDT05, MDT02 (Spain) | CC BY 4.0 (IGN/CNIG) | open; not downloaded |
| Hellenic Cadastre DEMs | unknown | not checked further |
| OSM (crossings, drains) | ODbL | open |
| REDMAR / Copernicus Marine / SHELDA | open with registration / CC BY 4.0 (SHELDA) | not downloaded |

### B3. Disk and runtime for a ~10-member terrain ensemble
Basis: the prototype's measured SFINCS throughput of **27–108 M cell-steps per solver-second** (P0, amd64 emulated on this Mac; SFINCS skips dry cells, so wet fraction matters) and peak memory of about 0.37 KiB per cell + 28 MiB. Steps come from CFL at 30 m (prototype §7). These are **extrapolations**, not measurements.

| Case | Cells (30 m) | Window and steps | Per member | 10 members | Disk (10 members) |
|---|---|---|---|---|---|
| **Valencia** | 0.61–0.89 M | 60 h, 54k–144k steps | **5–80 min**, 0.25–0.4 GiB | **≈ 1–13 h** | inputs ≈ 0.1 GB (10 terrain realisations ≈ 3.6 MB each, plus forcing); lean outputs (hmax plus the 30 Oct 10:37 and 31 Oct 10:22 snapshots) 20–30 MB per member → **≈ 0.3–0.5 GB**; hourly maps would be ≈ 4 GB |
| Volos city | 0.04–0.19 M | 48 h, about 30k–100k steps (steeper, faster flow: smaller dt; assumption) | under 1–12 min | ≈ 0.2–2 h | ≈ 0.1 GB lean |
| Thessaly (full to Larissa) | 7.4 M | 10 days, ≈ 120k–290k steps (dt 3–7 s; assumption) | **≈ 2.3–22 h** (if fully wet; the plain is partly dry) | **≈ 1–9 days** | ≈ 1–2 GB lean; hourly maps ≈ 30 GB+ |
| Thessaly (nested plain) | 1.7–2.8 M | 10 days | ≈ 0.5–8 h | ≈ 0.2–3.5 days | ≈ 0.5–1 GB lean; **blocked** on inflow hydrographs |

A LiDAR terrain member at native 2–5 m is out of reach for an ensemble here: 36–225× the cells and 6–15× the steps. LiDAR's use is different, and better: **resampled to 30 m, it measures the GEDTM30/FABDEM error at Valencia directly**. The ensemble's error amplitude and correlation range can then come from the site instead of the literature (prototype §6.3 had to assume a 50/50 or 80/20 short/long split). The MDT05 download for ~800 km² is about 0.1–0.2 GB (estimate: 32 M cells of float32, compressed); MDT02 is about 0.8 GB. Both are well inside the 15 GB rule (44 GB free at the start).

### B4. Recommendation: **Valencia (Poyo / Horta Sud, DANA 2024)**, the same choice as the prototype's §7, now with stated reasons against both Volos readings
1. **Boundary conditions are closable without accounts we lack.** Headwaters are inside a ~420 km² connected catchment, so there is no GloFAS inflow. The downstream end is a lagoon on a microtidal coast, handled as scenarios. The Thessaly plain needs inflow hydrographs on three or more rivers, which are blocked on EWDS registration and unverified gauges.
2. **The reference is close to the peak and has two times.** Landsat ≈ 16 h after the peak (AOI01, layer still to download) and VHR at ≈ 40 h. Volos city has **no reference**. The Thessaly VHR series starts 3 days after the plain's peak and tracks recession, which is a test of drainage and levees we cannot represent.
3. **Open CC BY 4.0 LiDAR** allows the terrain-error model to be measured on site. Greece's DEM licence is unknown.
4. **Compute fits:** ~1–13 h for 10 members against ~1–9 days for the full Thessaly domain.
5. **Infrastructure is known from a published 2D study** (V-31 backwater), so it can be a stated scenario. Thessaly's levee breaches are not in any open dataset.

**What stays weak at Valencia:**
- The lagoon gauge datum and gola timing (a 1 m offset was the largest systematic effect in P0b);
- the rain bracket, since IMERG misses the convective core;
- culverts at 30 m;
- the reference being a maximum-extent proxy (traces ≫ standing water);
- exposure level 6: it is a burned development case, never a test.

**Volos keeps one use:** the Thessaly plain is a later **nested-domain** test once GloFAS access exists. Volos city could become a case only if a city-scale flood map is found (none in EMS).

---

## Reproduce

```sh
# from the repo root, GEE_PROJECT_ID in the environment
caffeinate -i sh experiments/flood_baselines/run_all.sh   # build passes 1-4, score, tables
python -m experiments.flood_baselines.screen_partb          # Part B upstream areas
python -m pytest -q experiments/flood_baselines/test_baselines.py
```
Inputs are cached under `~/.cache/geowatch/flood_baselines/` (not committed); each pass skips what is cached.
