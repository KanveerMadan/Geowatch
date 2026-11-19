# flood_final: status

Branch `exp/flood-final` (from `origin/exp/flood-learned` @ a8395d1; baselines, flood-core and paper/evidence-fluvial merged). Read this first on any restart; never redo a phase marked done. Judgement calls: DECISIONS.md.

## Open questions for the owner
- none

## Phases
| # | phase | state | notes |
|---|---|---|---|
| 0 | context, branch | done | 1744fc5 |
| 1 | one event set (DEV + RESERVED) | done | registry c6fb5b1: +38 DEV units (18 EMS activations), +47 RESERVED (23 EMS activations, 6 S1 events) |
| 2 | pre-registration pushed | done | eed20fe, sha256 e49bca3f..., pushed 2026-11-19T07:37:07Z (PREREG_HASH.txt eb0b0c3) |
| 3 | inputs for all DEV events | **running** | coastal/GHSL extras added to the 29; build_units.py for the 38 new DEV units |
| 4 | urban-capable reference | **part done** | Weihui: round-4 S1 VV-drop marks 43% of flooded-open but 1.1% of flooded-urban cells (dry 4.8%) -> urban flooding invisible to S1 refs (urban/results/weihui_s1_capture.json). Model part waits on v2 |
| 5 | learned model v2 (DEV) | code ready | model_v2.py cv / choose; waits on phase 3 |
| 6 | SFINCS (DEV) | **running** | valencia.py: LiDAR + IMERG prep |
| 7 | one held-out pass | todo | |
| 8 | evidence packs | todo | |
| 9 | production PR | todo | |
| 10 | M7/M6/M8 scenarios | todo | |

## Running now
- build_units --dev (38 new DEV units, ~18 min each, started 2026-11-19 19:32 IST; log ~/.cache/geowatch/flood_final/build_dev.log; resumes, 3 tries per unit)
- SFINCS Valencia queue: base (running) then gauge, glo30, lagoon1m, lidar_e1..e3, then `valencia score`, then Docker quits (log ~/.cache/geowatch/flood_final/sfincs/valencia/run_queue.log)

## Next steps (in order)
1. When both finish: `python -m experiments.flood_final.model_v2 cv`, then `choose` -> results/method_choice.json (commit).
2. `python -m experiments.flood_final.urban.weihui score <final model pickle>` (D11 model part).
3. DEV report tables (block bootstrap on DEV) for the evidence packs.
4. Freeze: commit, tag flood-final-heldout-freeze, push tag. Then `heldout_pass build`, `heldout_pass score` (once).
5. Evidence packs (paper/evidence/M1..M9), then production branch + PR.

## Failed / missing (never zero)
- GEDTM30 v1.2 COG: OpenGeoHub server returns truncated range responses (2026-11-18); GLO-30 fallback.

## Caches (regenerable, created by this work)
- ~/.cache/geowatch/flood_learned/ (batch-0 inputs, tables, preds, maps; heldout/refs = DEV expansion references)
- LightGBM: ~/.cache/geowatch/flood_learned/pylib (PYTHONPATH)
