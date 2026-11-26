# M6–M8 status

Owner since 2026-11-27: Claude Code, taking over from Codex on the same branch (`feat/flood-m6-m8`, worktree `~/gw-m678`). Round 3's methods are imported unchanged from a pinned read-only checkout: `git worktree add --detach ~/gw-r3pin f28d714`.

## Where to resume

1. **DEV chain** (labels, then round 3's feature tables) runs unattended:
   - log: `~/.cache/geowatch/flood_m678/chain_dev.log`;
   - check: `tail -20 ~/.cache/geowatch/flood_m678/chain_dev.log`;
   - restart: `nohup caffeinate -i sh experiments/flood_m678/run/chain_dev.sh &`, which is resumable.
2. **Then:**
   - `dev_cv_m678 feats` and `dev_cv_m678 cv` (Phase C);
   - write PREREGISTRATION_M678.md and `score_m678 freeze`, then tag the freeze;
   - build the reserve and run `score_m678 test` once (Phase D);
   - wire the trust labels into the product (Phase E).

## Done

- **Phase A, events.**
  - Before: 1 timed DEV cluster for M7 and 0 non-Alaskan M6 clusters.
  - Now, timed incidents with a full-box scene in the window:
    - M7: 8 DEV clusters;
    - M8: 4 DEV clusters plus split clusters;
    - M6: 1 DEV cluster;
    - reserve candidates in every type.
  - Crest sources:
    - USGS gauge brackets;
    - NWS historic crests;
    - Water Survey of Canada annual-peak clock times;
    - published readings (CWC, MLIT, J-STAGE);
    - GEOGloWS daily peaks only for levee breaches without a gauge.
  - The image window was restated to the brief's "same day or next day" (DECISIONS_M678.md).
- **Reserve sealed from metadata only**, before any model work:
  - commit `fb73a2e`, tag `m678-reserve-seal`;
  - `reserve_m678.json` sha256 is in `experiments/flood_m678/RESERVE_HASH_M678.txt`.

  | type | reserve clusters (incidents) | clusters |
  |---|---|---|
  | M6 | 6 (10) | Mendenhall, Skaftá, Taku, Kenai/Snow, Salmon/Summit, Kennicott |
  | M7 | 6 (6) | Kakhovka/Kherson, Orsk, Pajaro, Al-Tlul, Gabrielle/Tutaekuri, Ussuriysk |
  | M8 | 7 (8) | Red River, Hay River, Kallio, Ottawa, Saint John, Upper Mississippi, Yukon |

  - A recurring lake or reach flooded both before and after 2022 is a reserve cluster, and its older floods are withheld from DEV, so DEV and reserve never share a place.
  - That empties M6 DEV apart from Grímsvötn.
- **Labels:**
  - Round 3's v3 Sentinel-1 rules, unchanged.
  - An optical rule (two signals for new water, a pre-event land view, a green-canopy abstain, built-up unobserved) generalised from Codex's Midland pilot.
  - MODIS snow is unobserved.
  - Four states plus "permanent water". The lag of every scene to the crest is recorded.

## DEV labels so far (8 km box; flooded / dry cells)

| incident | type | source | flooded | dry | QA |
|---|---|---|---:|---:|---|
| Midland 2020 | M7 | Landsat 8 + 7 | 3,706 | 5,378 | single instrument family; the USGS high-water-mark service has moved (pending) |
| Gulf Port 2008 | M7 | Landsat 7 | 13,673 | 2,390 | – |
| Hamburg 2019 | M7 | Sentinel-1 | 5,820 | 22,579 | κ 0.49 against optical |
| Holt County 2019 | M7 | Sentinel-2 | 5,014 | 8,079 | – |
| Gandak 2020 | M7 | Sentinel-1 | 35,583 | 34,006 | monsoon paddy may inflate radar water |
| Fort McMurray 2020 | M8 | Sentinel-1 | 642 | 44,537 | κ 0 against a 47 h-later Landsat 7 |
| Grand Forks BC 2018 | M8 | Sentinel-1 | 2,284 | 19,160 | κ 0.72 against Sentinel-2 |
| Minot 2011 | M8 | Landsat 7 | 1,470 | 4,975 | – |
| Grímsvötn 2021 | M6 | Sentinel-1 (December) | 18,987 | 52,480 | unverified: winter radar, no optical, no MODIS in polar night |

Dropouts (no flooded cell, or too few flooded or dry cells), all from cloud or no usable scene:

- Annamayya, Mabi and Fort Vermilion had no flooded cell;
- Chikuma had 3 flooded cells;
- Xe Pian had 0 dry cells.

## Next

- Phase C DEV comparison.
- Pre-registration and freeze, then the one-shot test.
- Product (contract, modules, API, web), tests, PR.
- Evidence pack.

## Resume note (2026-11-27, usage limit reached)

- **Product wiring is drafted and imports cleanly, but is not yet tested.** It covers:
  - `susceptibility/conditional_flood.py`;
  - `configs/m678_constants.py` (METHODS are placeholders until the freeze);
  - `ingestion/m678_context.py`;
  - hazards, contract, wards and hydro_rasters edits.
- **Still open in the product:**
  - run the full suite and fix it;
  - web blurbs and scenario note in `web/src/lib/flood.js`;
  - an API scenario endpoint;
  - a `VALIDATED_CONFIGS` entry if a type passes.
- **DEV feature chain:** check it is finished, then reset the Grímsvötn entry in `~/.cache/geowatch/flood_m678/big/build_log.json` and rerun `features_m678 dev`.
- **Then:**
  - `dev_cv_m678 feats`, then `cv`;
  - write `results/chosen_methods.json` and PREREGISTRATION_M678.md;
  - `score_m678 freeze` and the freeze tag;
  - reserve labels and features, then `score_m678 test` once.
