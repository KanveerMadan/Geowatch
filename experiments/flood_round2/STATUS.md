# flood_round2: status

Branch `exp/flood-round2`, in worktree gw-floodproto: exp/flood-final plus build/flood-learned (PR #1). Read this first on any restart, and never redo a phase marked done. Judgement calls are in DECISIONS.md.

## Open questions for the owner
- none

## Phases
| # | phase | state | notes |
|---|---|---|---|
| A | PR #1 decisions + blocking secrets scan | done | build/flood-learned d206554; PR #1 ready for review (not merged); C78 demoted; tools/secrets_scan.py + safe_push.sh; LICENCES.md |
| B | EMSR683 fetch bug | done | `_mosaic` takes the selected band's projection; regression test; control DEM unchanged (diff 0.0) |
| C | Fort Myers coastal SFINCS | done | R14: model wets 99 % of the box; S1 labels 10 %: reference-limited (AUC 0.54–0.74) |
| D | coastal forcing + features | part done | sea spill / shielding / connectivity features (features_r2); GTSM unavailable (no ~/.cdsapirc); gauges used in SFINCS cases |
| E | flash-flood features | done | D8 accumulation (local + HydroSHEDS), hand_d8, valley floor, SPI, upslope slope, Kirpich tc |
| F | urban flood references | waiting | origin/exp/urban-flood-ref not pushed yet (checked 2026-11-21) |
| G | better terrain | todo | |
| H | model v3 (DEV) | done | method_choice_r2.json (e6c2796), dev_report_r2.json; no learned candidate beats elevation with CI > 0 on DEV (R15) |
| I | SFINCS rain / coastal / compound | running | Ida (compound) running; urban rain cases after |
| J | pre-register round 2, freeze | done | prereg 9853dd6 pushed 2026-11-21T10:07:11Z sha256 7a06490c...; hash file ae0022a; freeze tag flood-round2-heldout-freeze |
| K | one held-out pass | running | heldout_r2 build (63 units), then score once |
| L | evidence packs | todo | |
| M | production PR | todo | |
| N | M7 / M6 / M8 scenarios | todo | |

## Running now
- Ida SFINCS queue (~/.cache/geowatch/flood_round2/ida/queue.log)
- heldout_r2 build (~/.cache/geowatch/flood_round2/heldout_build.log); HEAD must stay at the freeze tag in gw-floodproto until score; other work in a separate worktree

## Next steps
1. heldout_r2 score (once), commit heldout_r2.json.
2. Ida score; urban rain SFINCS cases (separate worktree until scoring is done).
3. Evidence packs (Phase L), production PR (Phase M), REPORT.md.
