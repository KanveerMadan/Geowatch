# Evidence pack: M3 waterlogging

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

**Headline.** **PASSED** (pre-registered). Learned `open__logreg` on 3 reserved units (2 clusters): mean AUC 0.791, Δ vs HAND +0.167 [+0.118, +0.226]. Plain low elevation scored 0.843 on the same cells — higher than the learned model.
