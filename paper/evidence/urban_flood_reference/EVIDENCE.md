# Evidence

[The generated development results](RESULTS.md) report coverage, external comparisons and control detections for the current shipment. The generated tables preserve incident and reference identities. Their denominators answer different questions.

| Output | Readout |
| --- | --- |
| `tables/coverage_and_additions.csv` | One row per product, stratum and detector. Read mapped wet, dry, ambiguous and unobserved counts. `new_wet` counts candidates absent from the matched intensity baseline. |
| `tables/agreement.csv` | Agreement for each external reference, labelled by provenance. New candidates split into independently or externally mapped wet, mapped dry, and unknown. The coverage and acquisition-lag fields show where agreement is measurable. |
| `tables/legacy_comparison.csv` | Replaces the ablation with the exact archived VV-drop product on coincident grids and post acquisitions. Signed reasons record the excluded comparisons. `new_wet_over_legacy_valid_nonwet` excludes unknown historical cells. |
| `tables/partial_water_presence.csv` | Positive-only urban water-presence training aids. An eligible 30 m neighbourhood contains at least one homogeneous newly wet 10 m patch. The child count is reported separately. These counts do not enter whole-cell accuracy or label counts. |
| `tables/figures.csv` | Index of four-panel map figures. A separate archived-intensity comparison is drawn when available. Orange denotes an added candidate inside the model urban mask. The reference panel retains unknowns. |
| `data_manifest.csv` | Input checksums and provenance. Scientific package manifests additionally carry acquisition IDs, dates, licences and dimensions. |

For the Weihui urban benchmark, use the flooded-urban reference, `stratum=all`, and `wet_recall`. The historic baseline recovered 34 of 3,200 benchmark urban-flood cells in tile 1, 62 of 879 in tile 2 and 11 of 450 in tile 3. The three tiles sample the same July 2021 incident. Those counts use the original dated VV-drop map on each benchmark grid. The urban-flood class is radar-derived; it is a shared-sensor recovery diagnostic. The all-flood benchmark additionally has a mapped non-flood class for conditional false-alarm comparison. Class-specific urban-only and open-only masks carry positive labels and unknown elsewhere.

A positive `paired_recall_delta` means the candidate detects additional known wet cells on net. Review the independently observed dry rate, coverage and absolute numerators alongside this delta. The pre-event rows quantify apparent detections on controls. Their dates alone cannot establish whether each detection was false.

The full study conclusions and transfer instructions are in the [report](../../../REPORT.md) and [short handoff](../../../HANDOFF.md). The [catalogue](../../../experiments/urban_flood_ref/catalog.csv) includes Bima, where the event-acquisition rule failed. Human optical annotations, published radar-derived labels, and detector-only candidates have distinct training roles in the [source-specific manifest](../../../experiments/urban_flood_ref/label_options.csv).
