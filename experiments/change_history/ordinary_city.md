# Ordinary city-month validation

This experiment measures how often the frozen detector fires during ordinary monitoring. Six neighborhood plots were selected by geographical context before consulting imagery, known changes or event catalogs. The sample includes the East Kolkata Wetlands and a peri-urban Mekong farming area as well as urban areas in Jakarta, Lagos, Nairobi and Recife. These are landscape contexts for the sampling frame. They do not certify each cell's land use.

Each plot is a 600 m square. All 36 of its 100 m cells and all twelve calendar months of 2021 are included, giving 2,592 cell-months across 72 plot-months. The plots are purposive. Extrapolation to an entire city, to all wetlands, or to worldwide deployment would require a different sample design.

## Lock and replay

The protocol was written and hashed before reading images, event histories or reference labels for the sample. The runner verifies its hash and the byte hashes of the production detector and observation provider from commit `e457e57`. The study uses the Sentinel-2 input configuration. Reserving Landsat for independent water references means these results apply only to this sensor configuration. The local seasonal detector receives the production support, indices and scene filtering and observes a strict month-end cutoff.

Run from the repository root. Supply an environment that has the Earth Engine Python client and project access. Existing EE authentication is used. The optional dotenv file should specify GEE_PROJECT_ID. Use one detector run at a time when sharing the laptop with other work.

```sh
python -m experiments.change_history.ordinary_city roster --cache /tmp/geowatch-ordinary > blind-roster.jsonl
python -m experiments.change_history.ordinary_city run --env-file PATH_TO_PROJECT_ENV --cache /tmp/geowatch-ordinary
python -m experiments.change_history.ordinary_city summary --cache /tmp/geowatch-ordinary > counts.json
python -m experiments.change_history.ordinary_city rows --cache /tmp/geowatch-ordinary > predictions.jsonl
python -m experiments.change_history.ordinary_city review --cache /tmp/geowatch-ordinary --labels independent-labels.jsonl
```

Pixel batches and complete site checkpoints survive retries. The summary requires all six sites. Raw hashes and individual results are local to the protocol-specific cache. The blind roster can be regenerated offline, without reading predictions, any time. Failures to fetch data are errors, while a valid acquisition masked by cloud is an observation gap.

## Interpreting the counts

- The observation denominator includes every scheduled cell-month, including those with no complete channel. Full coverage requires at least one seasonal series passing the detector's original continuity checks. A partial month can still have a confirmed episode.
- The burden metric counts at most one cell with a confirmation per calendar month, even if multiple signals or episodes fire there. Neighboring cells and adjacent months can still refer to one physical disturbance. Plot-level burdens are reported per 0.36 km² sampled area. They are different from the number of deduplicated incidents a deployed app would send.
- `quiet` counts rows with no candidate or confirmed episode. Poor coverage can cause silence, so quiet must never be read as a verified stable surface.
- The water reference uses the EC JRC / Google GSW monthly history. Its Landsat-derived water classes are sampled at the same 25 lattice centers per cell. Any missing center in either the preceding or monitoring month makes the pair unknown. Net gains and losses are changes in the number of water-classified centers. The complete raw counts travel with each result. Nearby centers sampling the same native pixel are correlated.
- The confusion counts measure agreement of a confirmed MNDWI change with the direction of net monthly mapped water change. They do not establish physical truth for every signal. Adjacent monthly composites can span a different event time, normal seasonal water can legitimately shift between months, and subpixel or temporary changes can be missed by the reference. The denominator for the primary proxy confusion counts is every pair with a complete JRC reference, including detector abstentions. The secondary table includes only those reference pairs where the detector also had complete water observations.
- The experiment has no automatic independent vegetation or building truth. For physical review, give a reviewer only the blind roster. Each evidence row identifies site, cell, month, target (`water` or `vegetation`), verdict (`gain`, `loss`, `both`, `stable`, `unknown`), reviewer, `prediction_blind: true`, and, for resolved labels, `evidence_source`, a dated `evidence_id`, and `independent_of_sentinel2: true`. The join is keyed to the locked sample. Unreviewed or ambiguous evidence remains unknown. The report bounds false-alarmed cells per plot-month by treating unresolved confirmations as all true or all false at the extremes. For the pooled any-direction count, a physical confirmation matches when at least one reported direction matches the label. Direction-specific tables keep opposite-direction errors visible.

Data credits: ESA/Copernicus Sentinel-2 SR Harmonized; Source: EC JRC/Google. [Earth Engine JRC monthly history](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_MonthlyHistory); [Pekel et al. (2016)](https://doi.org/10.1038/nature20584).

## Results from the registered 2021 sample

| Neighborhood plot | Fully observable out of 432 | Confirmed cell-months | Candidate-only cell-months |
|---|---:|---:|---:|
| Kolkata | 39 | 1 | 11 |
| Jakarta | 86 | 14 | 31 |
| Lagos | 93 | 0 | 14 |
| Can Tho | 23 | 1 | 8 |
| Nairobi | 138 | 4 | 42 |
| Recife | 283 | 6 | 51 |
| Total | 662 | 26 | 157 |

Only 25.5% of 2,592 cell-months met the detector's full monthly coverage criterion. There were 31 confirmed signal episodes in 26 cell-months, equivalent to 0.36 confirmed cells per sampled plot-month. Nine cell-months had a confirmed water signal and sixteen had a greenness confirmation.

The independent JRC product had complete paired months at 933 locations and months. It showed 37 net water gains and 46 losses. No detector confirmation matched any of those changes in direction. Among the 290 pairs that also had complete monthly water observations from the detector, the reference showed six gains and one loss, again with zero matches. Of the nine detector water confirmations, two fell on reference pairs with stable net water occupancy and seven lacked a complete JRC pair. These results offer no support for turning on water-change alerts in these plots. The reference quantity is a monthly change in occupied lattice centers, so disagreement can include small, short-lived and seasonal fluctuations.

A supplemental prediction-blind image interpretation examined all nine water confirmations and nine matched controls, using dated USGS Landsat RGB and SWIR-NIR-red views. Four cases had clearly stable visible water occupancy on at least two distinct within-month dates and preceding imagery. Two of the four were confirmed water signals. The other fourteen cases, including seven of the nine water confirmations, remained ambiguous or lacked adequate observations. This visual evidence establishes two mismatches for a substantial observable open-water change target. The seven unresolved confirmations leave the sample burden bounded between 2/72 and 9/72 mismatched alerted water cells per 0.36 km² plot-month. Temporary changes between acquisitions remain possible. The reviewer was Codex, looking at masked case strips with the prediction, map result, location and calendar month hidden. Landsat is independent of the 2021 Sentinel-2 detector; both reference approaches use Landsat. This is a small retrospective supplement and does not establish accuracy for the default sensor configuration.

The compressed per-cell predictions, JSON counts, visual review protocol and results accompany the code under the `ordinary_city` prefix. Run the offline join directly against the checked-in predictions:

```sh
python -m experiments.change_history.ordinary_city review --labels experiments/change_history/ordinary_city_visual_result.json
```

## Default-source study and forward silent collection

After the Sentinel-2 study, a separate protocol was frozen before evaluating four previously unused neighborhoods and months in 2024. The default detector used all five normal sources in Pune, Bandung, Dakar and Belém. January, April, July and October supplied 576 cell-months and 16 plot-months. The detector had a fully observable series in 540 cell-months (93.8%). Radar accounted for all 540. An optical water or greenness series was fully observable in 359 (62.3%). The detector confirmed one radar VV decrease in Bandung. It confirmed zero water or vegetation signals and produced candidate-only signals in 99 cell-months. No independent reference establishes whether the radar change was physical. Differences between this and the 2021 study cannot be attributed to radar alone because the cities and years differ.

```sh
python -m experiments.change_history.ordinary_city_default run --env-file PATH_TO_PROJECT_ENV --cache /tmp/geowatch-ordinary
python -m experiments.change_history.ordinary_city_default summary --cache /tmp/geowatch-ordinary
python -m experiments.change_history.ordinary_city_shadow --site bandung --env-file PATH_TO_PROJECT_ENV --cache /tmp/geowatch-ordinary
```

The last command runs a forward silent observation, using the current UTC clock and imagery through the most recently completed UTC acquisition day. A full calendar month remains the monitoring window and subsequent dates remain unavailable for confirmation. An atomic SQLite ledger stores the actual observation receipt interval, acquisitions, coverage and candidate counts by cell, and the first logged confirmation of each signal episode. Calling it twice for the same site and cutoff returns the original receipt. Calling it on later dates logs newly available evidence. This CLI requires invocation to collect data and does not backfill missed invocations. It has no external notification path. Cell/track episode IDs can represent one larger physical incident. An ongoing prospective trial is needed to measure delivery latency and establish false incident rates.

The first live receipt covered the Bandung plot on 21 November 2026 at 04:11–04:12 UTC, with an acquisition cutoff of 20 November. All 36 cells had some usable Sentinel-1 and Sentinel-2 data during the month to date. There were zero candidate or confirmed episodes. The configured full-month query was still in progress, so every cell carried insufficient coverage for the complete monitoring interval. A second invocation at the same cutoff reproduced the stored receipt. The checked-in receipt summary records the processing timestamps and full receipt hash.
