# Evidence pack: M4 flash flood

Built from `exp/flood-final` (one event set, pre-registered method choice, one held-out pass). Read-only on results.

| File | Contents |
|---|---|
| `METHOD.md` | The learned model, features, choice rule, evaluation, inputs and licences |
| `EVIDENCE.md` | Pre-registration, DEV result, the held-out verdict, per-unit results |
| `LIMITS.md` | Where it fails and what the evidence does not show |
| `REPRODUCE.md` | Commands that regenerate every number |
| `data_manifest.csv` | Every DEV and RESERVED unit of this type, with status |
| `tables/*.csv` | Every number, with `source_file`, `source_commit`, `source_commit_date` |
| `figures/` | Per-event AUC with 95% CIs (DEV and RESERVED) |

**Headline.** **FAILED** (pre-registered). Learned `open__lgbm` on 6 reserved units (3 clusters): mean AUC 0.810, Δ vs HAND -0.017 [-0.060, +0.026]. Plain low elevation scored 0.862 on the same cells — higher than the learned model.
