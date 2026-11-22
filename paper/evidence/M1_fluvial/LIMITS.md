# M1 fluvial: limits and scope

## 1. Where it fails
**Round 4: South Asian monsoon floodplains** (`tables/round4_fluvial_test.csv`). The pre-registered re-test of the unchanged configuration failed:

| Event | AUC |
|---|---|
| Bihar (Kosi–Ganga) | 0.6425 |
| Upper Assam (Dikhow) | **0.3878** (worse than chance) |
| Sindh (Indus plain) | 0.5791 |
| **Mean** | **0.5365** (bar 0.70) |

- **Assam** (`figures/fig_c_maps_hanoi_assam.png`, bottom row): HAND is low across the whole 4 km box, so the HAND term barely separates cells. The ranking that remains disagrees with the Sentinel-1 flood map. HAND alone does better there (0.750).
- **Possible explanations, none tested:** distributed monsoon flooding of a flat plain rather than flooding from a single channel; the 90 m MERIT terrain; the Sentinel-1 reference (dense vegetation and urban areas hide water from SAR). Region and reference type are confounded: every round-2 pass used Copernicus EMS maps; every round-4 fail used Sentinel-1 or UNOSAT.

**Baselines (34 dev events,** `tables/baselines_per_event.csv`**):**
- Fluvial AUC is below 0.70 on 21 of 34 events, and below 0.5 on 6: assam_2026 0.388, kerala_2018 0.463, fort_myers_beach 0.463, beira 0.466, choloma 0.489, dubai_2024 0.489.
- The event's best baseline **clearly beats** fluvial (95 % CI of the difference below 0, column `clear_loss_990m`) on **11** events:

| Group | Events | Note |
|---|---|---|
| JRC-circular references | capetown, hcmc, accra, nusantara, dhaka | §2; the JRC baseline is 1.000 by construction |
| Round-4 test events | assam_2026 (−0.362 vs HAND), kerala_2018 (−0.324 vs JRC), sylhet_2022 (−0.188 vs HAND) | South Asia again |
| Others | thai_binh (−0.320 vs distance to water), fort_myers_beach (−0.195 vs HAND, coastal surge), bad_neuenahr (−0.021 vs HAND, flash flood) | |

- **On average fluvial is not distinguishable from HAND alone:**
  - all 34 events: +0.003 [−0.065, +0.066];
  - cleanest 17: +0.056 [−0.036, +0.129].

  Its added value over HAND is shown only on the 4 fluvial-mechanism events (§3).

## 2. Five events excluded as circular (JRC references)
- **The events:** accra, capetown, dhaka, hcmc and nusantara. Their cached reference is JRC GSW 1.4 occurrence "recurrent 5–80 %" (round 2's waterlogging reference), **not an observed flood**.
- **Effect on the baselines:**
  - The JRC-occurrence baseline *is* that reference's source: AUC 1.000 [1.000, 1.000].
  - Distance to water is inflated too, because permanent water (≥ 80 %) borders the recurrent band.
- **For fluvial itself there is no leakage** (fluvial reads no JRC layer). But these events measure recurring surface water, not a flood, so they are the wrong target for a flood claim.
- **Round 1** (pooled AUC 0.4476, an older method) used only references of this kind, on 9 sites.
- They are kept in "all" for completeness. **The recommended event set to quote excludes them, together with round-4 test events and their aliases: 17 events in 12 clusters** (`EVIDENCE.md` §4).
- They were also excluded as training labels for any learned model (owner's instruction, 2026-11-18).

## 3. How independent the evidence is
- **Two held-out events.** The validation rests on two events, the pre-registered minimum: Hanoi 0.9162 and Kolonnawa 0.7996. Two other held-out events (Nysa, Hue) had too few flooded cells to count (2 and 10).
- **The baselines comparison is a development-set report, not a held-out test.**
  - All 34 events are registry role `dev`.
  - Of the 5 clear wins:
    - **kolonnawa** is round 2's held-out event;
    - **encantado** is one of the two events the weights were **tuned** on;
    - **paiporta** is an alias (same EMS product) of round-4 test event valencia_2024.
  - The 4 "fluvial-mechanism" events where fluvial clearly beats every baseline (Hanoi, Kolonnawa, Faenza, Encantado) are round 2's own tuning and held-out events.
- **Chance level.** About one "clear win" per module is expected by chance across 34 events (one-sided 2.5 % × 34 ≈ 0.85). Five is above that, but events are not fully independent (22 clusters).
- **The best baseline is picked per event after seeing the results.** That favours the baselines, so the win count is conservative in that respect.
- **Block-size sensitivity.** Across all modules, the count of clear wins over the best baseline changes with the block: 8 at 990 m, 7 at 1,980 m, 12 at each event's own correlation range (baselines REPORT §A2). The fluvial wins are listed at 990 m.

## 4. Input and resolution limits
- **MERIT Hydro is ~90 m,** bilinear- and nearest-resampled to 30 m. It is too coarse for street- or parcel-level claims (`susceptibility/fluvial.py:85-86`).
- **The two ceilings are provisional, not calibrated:**
  - HAND 30 m (`configs/fluvial_constants.py:30`);
  - upstream area 10,000 km² (`configs/fluvial_constants.py:49`).
- **Only the river-size weight was tuned** (on two events).
- The score is a within-box **ranking**. It is not a depth, an extent, a probability or a return period. AUC tests ranking only, not calibration.
- **Reference timing and type vary:**
  - EMS maps are taken hours to days after the peak and include "Flood trace" (maximum-extent proxy) polygons.
  - Sentinel-1 misses flooding under dense urban double-bounce and vegetation (stated in `PREREGISTRATION.md`).

## 5. Licences
- **MERIT Hydro v1.0.1** (the only data the score uses): **CC BY-NC 4.0 or ODbL 1.0 (dual)**.
  - Non-commercial use can take CC BY-NC.
  - Commercial use needs the ODbL option, which makes derived maps ODbL (share-alike).
- **FABDEM** (CC BY-NC-SA 4.0) is **not used by fluvial.** It feeds other modules' slope and relief in the same raster fetch (`susceptibility/hydro_rasters.py:14, 87`). A fluvial-only product does not inherit its share-alike terms.
- **UNOSAT FL20220808PAK** (Sindh reference, round 4): licence varies by UNOSAT product and was **not recorded** for this one. Check before redistributing any figure that shows it (none in this pack shows it).
- **Copernicus EMS:** free under the CEMS terms with attribution, information purposes. Figure (c) shows an EMS-derived map (Hanoi, EMSR754): attribute "© European Union, Copernicus Emergency Management Service".
- **Non-commercial status.** That GeoWatch is non-commercial research is an **assumption** (audit A1), not verified here.

## 6. Scope note (what may be claimed)
**May be claimed:**
- Per-pixel MERIT HAND + river size (weights 1 : 1) ranks observed-flooded 30 m cells above dry ones with mean within-event AUC 0.8579. This was on two pre-registered held-out river-city events (Hanoi 2024, Kolonnawa 2025), against a pre-registered bar of 0.70.
- It also clearly outperforms HAND, JRC occurrence and distance to water on the fluvial-mechanism development events.

**May not be claimed:**
- Validity outside those events. The same configuration **failed** a pre-registered re-test on three South Asian monsoon-floodplain events (mean 0.5365). The project's validated-config record (`analysis/contract.py:108-125`) excludes those events and regions explicitly.
- That it beats HAND in general. Across 34 development events it does not on average.
- Whether the round-4 failure should change the module's label is open (C78, NEEDS FATE). This pack does not decide it.
