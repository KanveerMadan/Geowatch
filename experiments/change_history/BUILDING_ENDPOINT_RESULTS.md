# Can satellite index changes predict building footprint area?

The registered Sentinel-2 estimator failed to beat zero change on the only observable held-out site. At the other held-out site, independent surveys recorded building changes, but the earlier Sentinel-2 window contained no acquisitions. This run measures error on stable ground and a coverage failure. It gives no estimate of sensitivity to real building change. GeoWatch keeps the regressor out of its default Change tab.

| Site and role | Surveyed cells | Cells with paired Sentinel-2 observations | Cells with mapped gain / loss across all surveyed ground |
|---|---:|---:|---:|
| California, development | 400 | 400 | 7 / 2 |
| Sahara, development | 400 | 400 | 85 / 1 |
| Central Asia, development | 400 | 388 | 0 / 1 |
| Florida, held out | 400 | 400 | 0 / 0 |
| South China, held out | 400 | 0 | 36 / 15 |

Each ground unit was a full 100 m square covered at both survey epochs. The two regressors trained on 1,188 development cells. In Florida, the mean absolute errors per cell were **14.62 m² for footprint gain** and **9.02 m² for loss**. Both the zero baseline and the development-median baseline had zero error for both quantities. In South China, the paired SpaceNet surveys mapped 17,228 m² of gain and 2,945 m² of loss in the sampled area. The September 2018 optical inventory returned zero acquisitions. September 2019 returned six, including four with usable measurements somewhere on the grid. Every cell therefore remained unscored. These are comparisons of mapped polygons, subject to their registration and delineation uncertainty.

Sites, monthly acquisition windows, training settings, fallback and eligibility were fixed before examining the held-out labels. The Planet fallback condition did not trigger. The two held-out locations are geographically distinct from training. Their observation periods do not establish strict temporal independence. Correlated cells in one observable region cannot support a global confidence interval. See the [protocol](BUILDING_ENDPOINT_PROTOCOL.md), [selected sites and source files](building_endpoint_sites.json) and [machine-readable scores](building_endpoint_result.json).

To reproduce the fit, run these commands from the repository root with an Earth Engine project. The first two commands fill a separate cache with the registered reference material and source observations. The last reads it locally.

```sh
python -m experiments.change_history.building_endpoints labels /tmp/geowatch-spacenet7-history
python -m experiments.change_history.building_endpoints s2 /tmp/geowatch-spacenet7-history
python -m experiments.change_history.building_endpoints evaluate /tmp/geowatch-spacenet7-history
```

SpaceNet Partners provide the reference data under CC BY-SA 4.0. The predictors use Copernicus Sentinel-2 surface reflectance. [SpaceNet 7 data and terms](https://spacenet.ai/sn7-challenge/) · [Sentinel-2 collection](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED)
