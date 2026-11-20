# flood_final: status

Branch `exp/flood-final` (from `origin/exp/flood-learned` @ a8395d1; baselines, flood-core and paper/evidence-fluvial merged). Read this first on any restart; never redo a phase marked done. Judgement calls: DECISIONS.md.

## Open questions for the owner
- Commit c35c02a (pushed to a public repo) contains a local home-directory path inside two error strings in results/heldout.json. It is redacted in the next commit (D22), but it stays in history. Purging it needs a history rewrite and force-push, which the brief forbids without you: do you want that?

## Phases
| # | phase | state | notes |
|---|---|---|---|
| 0 | context, branch | done | 1744fc5 |
| 1 | one event set (DEV + RESERVED) | done | registry c6fb5b1: +38 DEV units (18 EMS activations), +47 RESERVED (23 EMS activations, 6 S1 events) |
| 2 | pre-registration pushed | done | eed20fe, sha256 e49bca3f..., pushed 2026-11-19T07:37:07Z (PREREG_HASH.txt eb0b0c3) |
| 3 | inputs for all DEV events | done | 67 DEV units (29 + 38), all built 2026-11-20 07:00 IST; counts per mechanism D18 |
| 4 | urban-capable reference | done | Weihui: round-4 S1 VV-drop marks 43% of flooded-open but 1.1% of flooded-urban cells (dry 4.8%) -> urban flooding invisible to S1 refs (urban/results/weihui_s1_capture.json). Model: ranks flooded-urban cells below chance (0.12–0.36) -> blind spot (D20) |
| 5 | learned model v2 (DEV) | done | method_choice.json (D19); results/dev_tables.md: Δ vs HAND CI > 0 on DEV for fluvial, waterlogging, flash_flood; not pluvial, coastal, compound |
| 6 | SFINCS (DEV) | Valencia done; coastal deferred (D17) | 4 members, hmax AUC 0.75–0.83 vs HAND 0.706 (valencia_2024); 0.60–0.71 vs 0.501 (paiporta) |
| 7 | one held-out pass | done | heldout.json (D21): fluvial + waterlogging passed; pluvial, flash, coastal, compound failed; fluvial module re-test failed; elevation baseline beats the learned model on held-out |
| 8 | evidence packs | todo | |
| 9 | production PR | todo | |
| 10 | M7/M6/M8 scenarios | todo | |

## Running now
- none

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
