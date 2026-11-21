# Block expansion and removal

GeoWatch estimates two scores per 200 m block, one for a new built surface and one for a removed built surface. Both can be high when one part of a neighborhood gains buildings while another part loses them. The numerical outputs rank resemblance to a training label. Physical probabilities require validation against independently dated surveys.

## Development

The ten existing round-1 ordinary-monitoring city anchors supply 49 contiguous 200 m blocks each. The study uses all three one-year comparisons, 2017–18, 2019–20 and 2021–22. The center years have annual observations on either side, so the full reference period extends from 2016 through 2023. This gives 1,470 scheduled block comparisons. Regional coverage of the Google source varies. Every scheduled row is retained, including missing reference coverage.

The training reference is Google's annual Open Buildings Temporal presence confidence. At each of 2,500 points on a 4 m grid, expansion requires a confidence of at most 0.25 in both early years and at least 0.75 in both later years. Removal reverses the transition. Spatial aggregation sums such points at 16 m² per point. The 0.25 and 0.75 cutoffs are deliberately separated engineering choices; the source confidence has no probability calibration. Two-year persistence reduces one-frame errors but may retain systematic source errors. Both directions need surveyed coverage at every point in every year. At least 100 m² of qualifying change represents a roof roughly 10 m on a side. Intermediate changes fall in the unknown class. Zero qualifying change is a negative *proxy label*, which can include a real change that the source missed.

The predictors use the same-track median Sentinel-1 VV, VH and neighborhood VH texture, and Sentinel-2 greenness and water indices. Before and after windows cover 45 days on either side of the chosen date to collect repeated observations, and training uses June 30 as the nominal annual snapshot. A track needs two complete acquisition dates at each endpoint. Features include the two endpoint levels and their signed difference. A median over common tracks limits dependence on a particular orbit. Built-up share from the 2015 GHSL layer supplies a historical context feature. Changes in building-product confidence never enter the predictor. The weak reference and the optical predictor share Sentinel-2 lineage. Google's annual map timing also differs from the shorter predictor windows, and the historical layers can include retrospective processing.

Separate balanced logistic regressions train for expansion and removal. A fixed 0.5 threshold on the balanced score is the experiment's equal-class operating point. Default inference uses both sensors where available and falls back to the trained radar or optical model when only one is available. A target with no supported model is unknown. Models train on all observed strong proxy positives and negatives. Each development fold withholds an entire city across all years. The zero-detection baseline uses exactly the same reference and observation mask as the candidate. Its recall on observable positives is zero. Precision, ranking and recall on the proxy have different meanings from performance on independently surveyed buildings. The recent, independent test has its own registration.

## Reproduction and data terms

Run from the isolated worktree in a configured Earth Engine environment. The raw source cache resumes by region, sensor and time block. Development rows, numerical model coefficients and comparison counts travel with the code. Inference uses the model bundle without fitting again.

```sh
caffeinate -i env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 geowatch-env/bin/python -m experiments.change_round2.monitor_lock experiments.change_round2.buildings all
```

Open Buildings Temporal v1 uses CC BY 4.0 (Google Research, derived from modified Copernicus Sentinel data). GHSL built-up surface R2023A is provided by the European Commission Joint Research Centre under the Commission reuse policy with attribution. Sentinel-1 GRD and Sentinel-2 SR Harmonized use the Copernicus Sentinel data terms. [Google product and limitations](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1) · [GHSL source, release and reuse terms](https://developers.google.com/earth-engine/datasets/catalog/JRC_GHSL_P2023A_GHS_BUILT_S)

The standalone mapper emits 49 experimental 200 m polygons with a score, decision and selected sensor combination for each target. Pass two ISO dates at least 90 days apart. Each prediction carries its before/after anchors and model hash. A null score signals unavailable input or a target with no usable trained estimator. For example, to replay a previously seen development location:

```sh
caffeinate -i env OPENBLAS_NUM_THREADS=1 geowatch-env/bin/python -m experiments.change_round2.monitor_lock experiments.change_round2.buildings map --centre 88.463 22.545 --epochs 2019-06-30 2020-06-30 --output /tmp/kolkata-building-round2.geojson
```

## Development results

Every scheduled block had four years of jointly visible weak-reference pixels. Intermediate proxy areas left 195 expansion and 109 removal outcomes unresolved. Ten block comparisons qualified in both directions. Leaving one development city out at a time produced the following pooled comparison:

| Target | Reference-positive blocks, including abstentions | Reference-known and sensor-observable | Model hits / false positives | Silent baseline hits / false positives | Ranking AUC / zero baseline |
|---|---:|---:|---:|---:|---:|
| Expansion | 70 | 1,255 | 28 / 449 | 0 / 0 | 0.574 / 0.500 |
| Removal | 32 | 1,341 | 7 / 515 | 0 / 0 | 0.333 / 0.500 |

Only 5.9% of expansion flags and 1.3% of removal flags matched a positive proxy label in these comparisons. Sensor coverage was available for all 70 proxy gains and 31 of 32 proxy removals. That makes confusion, rarity and reference quality more consequential here than abstention alone. Expansion rankings varied by city: AUC was 0.85 in Can Tho (nine observed positives) and 0.24 in Bandung (twelve). Sampled neighborhoods and colocated blocks limit geographic inference. The production of a working score and the small rise over zero in expansion ranking provide insufficient support for building-change alerts.

The final artifact trained on all development cities, including 30 expansions and 24 removals on common multisensor support. The radar fallback saw 70 expansions and 31 removals. These targets describe persistent changes in an earlier satellite model. Independent recent footprint or aerial observations remain decisive for physical conclusions. [Per-city development results](building_development_results.json) · [Portable model](building_model.json)
