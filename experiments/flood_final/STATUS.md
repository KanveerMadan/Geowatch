# flood_final: status

Branch `exp/flood-final` (from `origin/exp/flood-learned` @ a8395d1; baselines, flood-core and paper/evidence-fluvial merged). Read this first on any restart; never redo a phase marked done. Judgement calls: DECISIONS.md.

## Open questions for the owner
- none

## Phases
| # | phase | state | notes |
|---|---|---|---|
| 0 | context, branch | done | 1744fc5 |
| 1 | one event set (DEV + RESERVED) | **running** | 20 EMS activations opened (refs built) -> DEV; RESERVED by metadata only |
| 2 | pre-registration pushed | todo | |
| 3 | inputs for all DEV events | todo | |
| 4 | urban-capable reference | todo | |
| 5 | learned model v2 (DEV) | todo | |
| 6 | SFINCS (DEV) | todo | |
| 7 | one held-out pass | todo | |
| 8 | evidence packs | todo | |
| 9 | production PR | todo | |
| 10 | M7/M6/M8 scenarios | todo | |

## Running now
- nothing

## Failed / missing (never zero)
- GEDTM30 v1.2 COG: OpenGeoHub server returns truncated range responses (2026-11-18); GLO-30 fallback.

## Caches (regenerable, created by this work)
- ~/.cache/geowatch/flood_learned/ (batch-0 inputs, tables, preds, maps; heldout/refs = DEV expansion references)
- LightGBM: ~/.cache/geowatch/flood_learned/pylib (PYTHONPATH)
