# Urban flood reference study

Completed on isolated branch `exp/urban-flood-ref`. The short [handoff](HANDOFF.md) and [report](REPORT.md) give the training targets, outcomes and remaining scientific limits.

| Phase | Outcome |
|---|---|
| Catalogue and leakage | 30 pre-2022 non-US incidents cleared using the pinned flood-final registry and historical Round 3 candidate metadata. Bernd was excluded at storm level. |
| Measurement | 36 event and 37 control tiles. Bima lacked a qualifying event pass. Each shipped map has a nested 10 m grid, exact 30 m model grid, provenance and four-state verdict. |
| Independent checks | Dated human optical annotations on eight footprints, independent automated optical checks, two Maxar reviews, the Weihui shared-sensor comparison and matched historical intensity maps where available. |
| Model delivery | Portable files under `experiments/urban_flood_ref/products`, plus the event catalogue, model reader example, per-file checksums, handoff and empirical limitations. |
| Evidence | Reproducible per-tile scores, spatial intervals and maps under `paper/evidence/urban_flood_reference`. |

Status of the scientific method: radar-only urban reference generation remains experimental. Can Tho supplied no surviving human optical training cells. Marsh Harbour lacked usable pre-event Maxar pixels. Street-level dry specificity remains unresolved.
