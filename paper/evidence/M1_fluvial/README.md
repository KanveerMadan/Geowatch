# Evidence pack: M1 fluvial

This pack is read-only on all existing results. It is built on top of `exp/flood-baselines` (`d1894e4`), and the only new computation is figure generation.

| File | Contents |
|---|---|
| `METHOD.md` | The exact method: formula, weights, ceilings, inputs with versions and licences, evaluation; `file:line` at `d1894e4` |
| `EVIDENCE.md` | Every fluvial result (rounds 1, 2 and 4, and the baselines), each with its source file, commit and run date; pre-registration hashes |
| `LIMITS.md` | Where it fails, the excluded circular references, how independent the evidence is, licences, scope |
| `REPRODUCE.md` | Commands to regenerate every table and figure |
| `data_manifest.csv` | One row per (event, use): date, centre, bbox, reference, role, flooded/dry cells, flags |
| `tables/*.csv` | Every number in EVIDENCE.md and LIMITS.md, with `source_file`, `source_commit` and `source_commit_date` |
| `figures/` | (a) per-event AUC with CIs; (b) ROC curves for the five clear wins; (c) Hanoi and Assam maps |
| `build_evidence.py` | Builds `tables/`, `data_manifest.csv` and `figures/` |

**Headline.**
- Round 2 is a pre-registered pass on 2 held-out river-city events: mean AUC 0.8579, bar 0.70.
- Round 4 is a pre-registered fail on 3 South Asian floodplain events: mean 0.5365. The scope was narrowed accordingly.
- Across 34 development events, fluvial ties HAND on average (+0.003 [−0.065, +0.066]). It clearly beats the best baseline on 5 events, 4 of them in the cleanest 17-event set.
- **flood_final (2026-11-20), independent river test on 8 new reserved units in 7 clusters, outside and inside South Asia** (`FLOOD_FINAL.md`):
  - the production fluvial module re-test **failed** (mean 0.578, Δ vs HAND −0.119 [−0.237, −0.019]);
  - the pre-registered learned model (`open__logreg`) **passed** (0.791, Δ +0.095 [+0.011, +0.192]);
  - plain low elevation, which was not pre-registered, scored 0.850.
