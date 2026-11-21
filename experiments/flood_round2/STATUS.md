# flood_round2: status

Branch `exp/flood-round2`, in worktree gw-floodproto: exp/flood-final plus build/flood-learned (PR #1). Read this first on any restart, and never redo a phase marked done. Judgement calls are in DECISIONS.md.

## Open questions for the owner
- none

## Phases
| # | phase | state | notes |
|---|---|---|---|
| A | PR #1 decisions + blocking secrets scan | done | build/flood-learned d206554; PR #1 ready for review (not merged); C78 demoted; tools/secrets_scan.py + safe_push.sh; LICENCES.md |
| B | EMSR683 fetch bug | done | `_mosaic` takes the selected band's projection; regression test; control DEM unchanged (diff 0.0) |
| C | Fort Myers coastal SFINCS | **running** | prep done (3DEP, JRC sea, IMERG, NOAA 8725520); 4 members queued (base, surge2x, glo30, lidar_e1); R4, R5 |
| D | coastal forcing + features | part done | sea spill / shielding / connectivity features (features_r2); GTSM unavailable (no ~/.cdsapirc); gauges used in SFINCS cases |
| E | flash-flood features | done | D8 accumulation (local + HydroSHEDS), hand_d8, valley floor, SPI, upslope slope, Kirpich tc |
| F | urban flood references | waiting | origin/exp/urban-flood-ref not pushed yet (checked 2026-11-21) |
| G | better terrain | todo | |
| H | model v3 (DEV) | code ready | model_v3.py cv/choose/report; runs after Fort Myers SFINCS (never together) |
| I | SFINCS rain / coastal / compound | part | Valencia reused; Ida (compound) prepped, runs after model v3; urban rain cases next |
| J | pre-register round 2, freeze | draft | PREREGISTRATION_ROUND2.md drafted locally (not pushed); reserved registered 0d569a1; heldout_r2.py ready |
| K | one held-out pass | todo | |
| L | evidence packs | todo | |
| M | production PR | todo | |
| N | M7 / M6 / M8 scenarios | todo | |

## Running now
- Fort Myers SFINCS queue (~/.cache/geowatch/flood_round2/fortmyers/queue.log)
- round-2 DEV inputs (build_dev inputs; ~/.cache/geowatch/flood_round2/build_dev_inputs.log)

## Next steps
1. After Fort Myers: features_r2 for new DEV tables, model_v3 cv, choose, report.
2. Ida SFINCS queue (scratchpad ida_queue.sh logic), then urban rain cases.
3. Finalise and push PREREGISTRATION_ROUND2.md + hash, freeze tag, heldout_r2 build + score.
