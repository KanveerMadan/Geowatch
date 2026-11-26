# Independent Amazon clearing test

GeoWatch's default sensor configuration confirmed a greenness decrease in **14 of 20 selected clear-cut notice cells**. Sentinel-2 alone confirmed 12 of the same 20. Both additional detections were in Amazonas. These are 20 cells from three dense clusters and a single reference month.

| State | Registered test cells | Sentinel-2 confirmed | Default confirmed | Default conclusive non-detections | Default unresolved |
|---|---:|---:|---:|---:|---:|
| Amazonas | 7 | 3 | 5 | 2 | 0 |
| Mato Grosso | 8 | 7 | 7 | 1 | 0 |
| Pará | 5 | 2 | 2 | 2 | 1 |
| Total | 20 | 12 | 14 | 5 | 1 |

A conclusive non-detection means a fully observed greenness series under the detector's continuity rule, with no confirmed loss during the study window. INPE's independently mapped clear-cut remains in the denominator. The default configuration uses Sentinel-1, Sentinel-2, Landsat 8 and 9 and annual Open Buildings context. The study measured the bundle's performance. It did not attribute the two additional detections to a particular sensor.

INPE returned 4,092 July 2024 clear-cut records from WFI/AWFI aboard Amazônia-1 and CBERS-4/4A. Geometry, interior support and uniqueness checks yielded 1,598 reference locations in the registry. The locked sampling rule selected one comparatively dense cluster per state in the three best-supported states. The other 1,578 rows have reference metadata only. Polygon segments represented in the scored subset range from 13.4 to 196.1 hectares; the detector was tested on one 100 m interior cell per notice. This design leaves the smallest clearings, boundaries and everyday urban conditions untested.

Among confirmed cases, the median signed difference between GeoWatch confirmation and the independent notice's **image date** was 32 days for Sentinel-2 alone and 21 days for the default sources. Across all 20 cells, the median wait from the reference date to the first subsequent usable greenness observation was 3 and 0.5 days respectively. The wait includes a same-day observation as zero. The last intact date of each cell is unknown, and the two confirmation medians have different denominators. These are neither clearing-onset delays nor an 11-day paired speedup estimate.

## Reproduce

The registry, locks and per-cell results are included. To replay imagery, use an Earth Engine authenticated environment with GEE_PROJECT_ID set. Initialize the project via the standard GeoWatch setup or the project environment. Commands below use an empty writable cache. The local studies do not update the GeoWatch application.

```sh
python -m experiments.change_history.amazon_clearing run /tmp/gwc-inpe-replay --state MT
python -m experiments.change_history.amazon_clearing run /tmp/gwc-inpe-replay --state AM
python -m experiments.change_history.amazon_clearing run /tmp/gwc-inpe-replay --state PA
python -m experiments.change_history.amazon_default run --cache /tmp/gwc-inpe-replay --state MT
python -m experiments.change_history.amazon_default run --cache /tmp/gwc-inpe-replay --state AM
python -m experiments.change_history.amazon_default run --cache /tmp/gwc-inpe-replay --state PA
```

Each command writes a per-state receipt to the cache. The original combine/registration commands use exclusive output paths to preserve the published results. A new working copy omitting the generated result JSONs can combine fresh receipts. An offline check of the committed locks, grid, selected IDs and paired counts is in the test suite.

[Registered design](AMAZON_PROTOCOL.md) · [Source query and lock](amazon_clearing_lock.json) · [Reference registry](amazon_clearing_registry.csv) · [Sentinel-2 results](amazon_clearing_result.json) · [Default-source results](amazon_default_result.json) · [Instituto Nacional de Pesquisas Espaciais, DETER methods and attribution](https://data.inpe.br/biomasbr/en/deter-daily-monitoring-of-native-vegetation-suppression-and-degradation/)
