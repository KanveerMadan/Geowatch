# Known-change test on independent forest and water maps

GeoWatch confirmed the expected change direction in **43 of 99 forest-loss cells**, **22 of 33 water-loss cells**, and **0 of 8 water-gain cells**. These are three separate results from the unchanged seasonal-history-v1 detector using Sentinel-2 observations. The test covered 140 fixed 100 m cells in eight regions during 2021. Each reference came from a separate Landsat-derived mapping program. The scores measure agreement at the cell and time-window level. The observations share optical failure modes, and several cells may represent the same physical event.

## Site selection and coverage

Twelve 40 km boxes were registered before inspecting the reference yield or predictions. The reference rules found 7,274 eligible cells. A deterministic hash selected up to 24 per region and direction, spaced at least 500 m apart within each stratum. The manifest, evaluation code, protocol and production model were locked before acquiring or scoring the held-out Sentinel-2 histories. Four boxes provided no reference cases under the rules. The original four hand-inspected development cells were outside every box.

| Region | Direction | Reference cases | Confirmed | Fully observed | At least partially observed |
|---|---|---:|---:|---:|---:|
| Pará, Brazil | Greenness loss | 24 | 20 | 1 | 24 |
| Chaco, Paraguay | Greenness loss | 24 | 11 | 24 | 24 |
| Sumatra, Indonesia | Greenness loss | 24 | 0 | 1 | 3 |
| Borneo, Malaysia | Greenness loss | 24 | 10 | 1 | 24 |
| Équateur, DRC | Greenness loss | 3 | 2 | 0 | 3 |
| Zambézia, Mozambique | Greenness loss | 0 | — | — | — |
| GERD, Ethiopia | Open water gain | 8 | 0 | 0 | 7 |
| Furnas, Brazil | Open water loss | 9 | 8 | 8 | 9 |
| Urmia, Iran | Open water loss | 24 | 14 | 24 | 24 |
| Poyang, China | Open water, either direction | 0 | — | — | — |
| Jamuna, Bangladesh | Open water, either direction | 0 | — | — | — |
| Murray, Australia | Open water, either direction | 0 | — | — | — |

Every selected cell had at least one usable Sentinel-2 measurement during monitoring. A fitted target series with enough historical measurements and a usable monitoring date qualified for partial observation. Full observation also required coverage through the window under the detector's existing continuity rule. A positive signal can be confirmed during a partial window. On the fully observed subset the counts were 13/27 for greenness loss, 21/32 for open-water loss, and 0/0 for gain. The eight water gains came from one reservoir, with a median of five distinct usable monitoring dates. There is no basis here for a worldwide estimate of water-gain performance. Regional contrasts also reflect different sample sizes and local conditions.

The red/near-infrared comparison has a different failure at Pará and at Chaco. In Pará, the detector found a change in 20 cells despite gaps elsewhere in most annual histories. At Chaco it had continuous target-signal coverage in all 24 cells and confirmed 11. Improving cloud coverage alone would leave 13 observed Chaco disagreements to explain. The case set deliberately selected large, consistently labelled changes. Minimum detectable area, construction sensitivity and false-alert frequency require separate studies.

## Reference meaning and timing

For forest, each of the 25 sample centres in the reporting cell had annual Landsat stand-replacement class 2021. A confirmed Sentinel-2 greenness loss anywhere in calendar 2021 counted as a match. This reference favours large, homogeneous changes. Recovery, harvest cycles and other disturbances can produce a matching signal in the same year. The reference does not date the local onset. Credit to Hansen/UMD/Google/USGS/NASA under CC BY 4.0. [Hansen et al.](https://doi.org/10.1126/science.1244693) · [Pinned reference asset](https://developers.google.com/earth-engine/datasets/catalog/UMD_hansen_global_forest_change_2024_v1_12)

For water, the prior-year July–September state and March–May 2021 state had to agree and the July–September 2021 state had to reverse. Each period required at least two agreeing observed months and no conflicting observed months, at every sampled centre. Missing labels never supplied a dry control. The detector looked for confirmed changes between June and September inclusive. A transition after the last spring observation could precede June. Confirmation and first clear observation dates are available for each case, alongside bounds on lag under a single sustained transition assumption. An exact delay from physical onset cannot be measured with these reference periods. Source: EC JRC/Google. [Pekel et al.](https://doi.org/10.1038/nature20584) · [Monthly history asset](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_MonthlyHistory)

## Reproduction

From the repository with its Earth Engine environment and project configured, run:

```sh
python -m experiments.change_history.known_change run --cache /tmp/geowatch-known-change --workers 2 --project "$GEE_PROJECT_ID"
```

The published manifest includes all twelve boxes and all case IDs. The study IDs and the `xy` field encode the southwest UTM corner. The production app indexes cells by their northwest corner. Add 100 m to the study northing when looking up a cell in the app. For example, study cell `EPSG:32722/236800/9264900` corresponds to app cell `EPSG:32722/236800/9265000`. The extraction compares the same physical square. The executable checks the detector, source reader, protocol, manifest and study code against the pre-score hashes. The sampler uses the production Sentinel-2 optical bands, quality masks, orbit grouping and fixed 20 m lattice, batching sparse 100 m cells to save work. A separate check on the June 2023 Kakhovka development cell compared the batched sampler with the production block reader over 12 acquisition groups. Both returned the same nine usable groups, three masked groups and identical float32 values for all three indices. Source inventories and extraction batches are cached on disk. Result dates use acquisition time and exclude delivery latency.

[Locked protocol](known_change_protocol.json) · [Case IDs and grid coordinates](known_change_manifest.json) · [Pre-score hashes](known_change_lock.json) · [Per-case outcomes](known_change_results.json)

A second extraction at the explicit 20 m sample centres of all 140 selected squares verified the expected reference class at every square. The original Hansen asset version remains pinned to reproduce this study. Earth Engine now marks that release deprecated.
