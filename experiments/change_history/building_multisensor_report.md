# Building additions and removals from radar and optical observations

The radar, optical and combined models were trained from dated building footprints and tested on four geographically separate, previously unseen study areas. **Predicting zero change had the lowest average error for both added and removed area.** Radar provided measurements in two places with severe optical gaps, but it also predicted substantial change in stable blocks. These results support an experimental command-line map and further research. They do not support public building alerts.

## What was measured

SpaceNet 7 tracks individual building IDs across monthly, manually annotated Planet mosaics. The reference was the area of footprints whose IDs appeared or disappeared across a one-year interval. Only objects fully within jointly visible survey coverage were used. For each 200 m square block the models estimated added and removed square metres separately. Additions and removals may coexist in the same block. Extensions of a continuing ID fall outside the target. A disappearance can also reflect a tracking error, and cannot by itself establish demolition. [SpaceNet study](https://openaccess.thecvf.com/content/CVPR2021/papers/Van_Etten_The_Multi-Temporal_Urban_Development_SpaceNet_Dataset_CVPR_2021_paper.pdf)

The exact site IDs, geographic centres, epoch months and source checksums were frozen in advance. The Ghana development tile lies near **Kumasi**; the prose protocol called this site Accra in error. The locked tile ID and coordinates were used throughout. Five development areas were previously seen during the older optical experiment. All four geographic test areas were new. The models used a single estimator configuration, without adjustment after the test.

## Geographic test

| Test region | Surveyed blocks | Blocks with mapped additions | Blocks with mapped removals | Stable for both targets | Radar available | Optical and combined available |
|---|---:|---:|---:|---:|---:|---:|
| West of Mexico City | 90 | 18 | 2 | 70 | 90 | 90 |
| Rotterdam | 90 | 1 | 0 | 89 | 90 | 0 |
| Lusaka | 64 | 22 | 0 | 42 | 64 | 1 |
| Dhaka | 90 | 43 | 4 | 45 | 90 | 90 |
| Total | 334 | 84 | 6 | 246 | 334 | 181 |

The table uses a complete, aligned 200 m grid within each 2 km study area. There were 360 complete blocks across these sites, 26 of which lacked joint survey support. Combined predictions require both modalities. Radar-only predictions cover all 334 surveyed blocks. In Lusaka, the single block with usable optical observations was stable. All 22 blocks with mapped additions lacked joint model support.

| Model | Error in added area (m²/block) | Error in removed area (m²/block) |
|---|---:|---:|
| Predict zero change | **91.69** | **8.61** |
| Optical only | 106.88 | 9.08 |
| Radar only | 226.02 | 41.89 |
| Radar and optical | 152.63 | 9.12 |

Errors are mean absolute errors on the same 181 blocks. The registered headline gives equal weight to each site contributing at least one block, so Lusaka's single common block has as much site weight as Dhaka's 90. Rotterdam contributes only to the radar-available comparison. The per-site results also include mean error for changed blocks, unchanged blocks, signed bias and the zero baseline on each mode's own available coverage. In Dhaka the combined model's mean error on gain-positive blocks was 393 m², while it incorrectly predicted an average 85 m² of additions on gain-negative blocks. [Per-site results](building_multisensor_result.json)

The optical and combined estimators trained on 533 usable development blocks across six sites, with additions in 80 and removals in five. Radar trained on 631 blocks across seven sites, with additions in 99 and removals in 11. Rare removals, neighborhood-scale sensor resolution and missing optical coverage limit what can be inferred. The historical geographic test used 2018–2020 endpoint pairs. It does not estimate recent routine construction performance.

## Independent recent-year check

The same models ran on a separate, frozen Pacific Palisades study area using February 2024 and February 2025 observations. **3,696 CAL FIRE field inspection records** fell inside 98 of the 100 complete blocks. Ninety blocks contained at least one structure recorded as destroyed. Three blocks contained only inspected structures marked undamaged. The other seven blocks had no qualifying comparison label. All 93 eligible blocks had measurements for both sensors. [CAL FIRE inspections](https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/ArcGIS/rest/services/POSTFIRE_MASTER_DATA_SHARE/FeatureServer/0)

| Predicted removed-area ranking | ROC AUC | Average precision |
|---|---:|---:|
| Zero-change comparator | 0.500 | 0.968 |
| Optical | 0.448 | 0.971 |
| Radar | 0.344 | 0.961 |
| Combined | 0.650 | 0.986 |

Only three inspected-undamaged blocks determine the negative side of this comparison. High average precision is expected at this prevalence, even for constant predictions. This check measures ranking against field-reported fire destruction. It cannot establish square metres lost, construction skill, or transfer to routine demolition. The original and recent protocols were independently hashed before scoring. [Recent result](building_multisensor_recent_result.json)

## Run the model on another location

Run from the repository root with the existing GeoWatch Python environment, authenticated Earth Engine access and the configured Earth Engine project. The small bundled training table contains only the seven development sites. The command fits the locked regressors locally and fetches observations only for the requested area. It writes an experimental GeoJSON with separate radar, optical and combined estimates for each complete 200 m block. Missing model support is represented by null. The model was trained on same-calendar-month, one-year pairs.

```sh
geowatch-env/bin/python -m experiments.change_history.building_multisensor_apply \
  /tmp/geowatch-building-cache /tmp/palisades-estimates.geojson \
  --centre -118.525 34.047 --months 2024_02 2025_02
```

The application produced 100 blocks in the 2025 study. All six gain/loss estimates for each block matched the original cache-trained model exactly. This verifies that the standalone command reproduces the experiment.

## Reproduce the locked tests

```sh
cache_dir=/tmp/geowatch-building-study
for sensor in sentinel1 sentinel2 targets
do
  geowatch-env/bin/python -m experiments.change_history.building_multisensor prepare "$cache_dir" --sensor "$sensor" || break
done
geowatch-env/bin/python -m experiments.change_history.building_multisensor evaluate "$cache_dir" --output /tmp/building-holdout.json
geowatch-env/bin/python -m experiments.change_history.building_multisensor_recent prepare "$cache_dir"
geowatch-env/bin/python -m experiments.change_history.building_multisensor_recent evaluate "$cache_dir" --output /tmp/building-palisades.json
```

Fresh output filenames are required. The study caches observations, source scene identifiers, summaries and reference inputs. SpaceNet downloads are pinned by object ETag and size. The CAL FIRE result records the hash of the aggregated inspection snapshot, and a later service revision may change it. The bundled development measurements include SpaceNet 7 data from SpaceNet Partners under CC BY-SA 4.0 and modified Copernicus Sentinel data. Individual CAL FIRE inspection records and addresses are excluded from the repository. [SpaceNet 7](https://spacenet.ai/sn7-challenge/) · [Sentinel-1 GRD](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD) · [Sentinel-2 SR](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED)

## Routine building additions after 2023

A second external check compared March 2024 and March 2025 predictions with independent high-resolution Dutch spring aerial surveys. One reviewer working blind to the model scores identified three clear additions, 41 blocks with no clear addition and four uncertain blocks. All three additions lay in Utrecht, including two neighboring blocks. Radar supplied estimates for all 44 decided blocks. Optical and combined estimates covered 27, of which two had clear additions.

On these same 27 blocks, the area under the ROC curve for ranking additions was **0.52 combined, 0.84 optical, 0.36 radar and 0.50 constant**. With only two positives on common coverage, changing the rank of a single block materially changes this comparison. Different local flight and satellite dates can also change which construction is visible at each endpoint. The geographic and temporal tests together give insufficient evidence for public construction alerts.

Reproduce with the frozen labels and development bundle using `python -m experiments.change_history.building_multisensor_dutch evaluate /tmp/geowatch-dutch --output /tmp/geowatch-dutch-replay.json` in a configured Earth Engine environment. The image acquisition and review rules, the reviewer’s reasons for each classification, and the per-site metrics are archived. [Review protocol](building_multisensor_dutch_protocol.md) · [Labels](building_multisensor_dutch_labels.csv) · [Results](building_multisensor_dutch_result.json)
