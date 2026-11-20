# GeoWatch change history

The Change tab monitors the selected date interval against up to five earlier years in the same place. Open a cell to inspect the acquisition dates, viewing track, measured signal, local seasonal baseline and timing of each detected episode. Date comparison shows the signed difference between two sets of observations. The image browser shows a true-colour composite for its own selected period. Saved item-25 results retain their original interpretation.

## Run change on its own

From the GeoWatch repository, using its Python environment and configured Earth Engine project:

```sh
python -m analysis.change_cli run --bbox 73.053 18.989 73.055 18.991 --start 2023-01-01 --end 2023-04-01 --sources sentinel2 sentinel1 --out /tmp/geowatch-change-example
python -m analysis.change_cli cell /tmp/geowatch-change-example 0 --out /tmp/geowatch-cell-0.json
```

The first command creates a new directory with a GeoJSON map, a summary, and a SQLite observation archive. The second command reads it offline. Both accept `--help`. The archive can replay a shorter period and cut off the evidence on a particular date. Retrospective mode can use later acquisitions to establish persistence or recovery. Acquisition dates describe what was visible in the archived scenes. Publication delays and subsequent satellite reprocessing can affect what an analyst actually had on a historical date.

The standalone run uses one numerical worker, serial Earth Engine requests, spatial tiles and reusable source batches. Use `--cache` to choose a cache. On a timeout or provider error, repeat with the same cache and output path. Missing coverage from a functioning source can produce a completed result with unknown cells. In the full app, a temporarily degraded source can produce a separate, readable snapshot and the next request retries the canonical result. The standalone command runs independently of the other GeoWatch analysis stages.

## Measurements

| Input | Use | Limits |
|---|---|---|
| Sentinel-2 surface reflectance | Greenness, open-water signal, SWIR/NIR built-surface signal | Cloud, shadow and snow masks limit coverage. Dry sediment can raise the built-surface signal. |
| Landsat 8 and 9 | The same three indices at 30 m native resolution | Each mission and path keeps its own baseline. |
| Sentinel-1 | VV and VH backscatter averaged in linear power | Track, platform and pass are kept separate. Urban geometry, terrain and moisture can confound interpretation. |
| Open Buildings Temporal | Annual historical building-presence confidence | Coverage varies. A source record becomes eligible at the later of its target and contributing imagery dates. Confidence has no unit of physical area. |
| Dynamic World, optional | Nine contextual class scores including bare ground, built surfaces, flooded vegetation and snow/ice | Shares Sentinel-2 imagery. Score patterns can inform an interpretation. |
| Dated survey polygons, optional | Gross gain, gross loss and net change in m² on joint surveyed ground | Results inherit survey coverage, acquisition interval, registration and delineation error. |

The default uses the first four rows. Set `GEOWATCH_CHANGE_SOURCES` to a comma-separated list in the app or pass `--sources` to the standalone command. Examples of source identifiers are `sentinel2`, `sentinel1`, `landsat8`, `landsat9`, `open_buildings` and `dynamic_world`. The summary records source identifiers, native resolution and attribution. The standalone grid supports local UTM areas from 80°S to 84°N. More recent imagery supports monitoring after the last Open Buildings year.

A 100 m reporting cell uses a fixed set of 20 m sample centres. A usable acquisition must cover every centre inside the requested area. The 20 m spacing does not resolve individual buildings or improve Landsat's native resolution. Each channel learns a robust seasonal cycle and trend, with forecast errors measured on a later historical year. Historical extremes over multiple channels and date blocks set the local screening level. The detector preserves candidate, corroborated, persistent and recovered episodes. A weak seasonal history or long gap can leave a cell unjudged. Evidence from an observed channel says little about changes visible only in a missing channel. Multiple tracks can report the same physical event.

## Survey measurements and reviewed causes

Set `GEOWATCH_CHANGE_SURVEYS` to a local JSON manifest. Each listed epoch is a WGS84 GeoJSON FeatureCollection containing polygons with property `role` equal to `coverage` or `surface`. Coverage must describe where that survey could establish presence **and absence**. A covered epoch may legitimately contain zero surface polygons. Each pair needs two nonoverlapping dated surveys entirely inside the monitoring interval. A single-date epoch can use `date` in place of `interval`; interval endpoints are inclusive.

```json
[{
  "name": "building_footprints",
  "source": "Example municipal survey",
  "license": "Record the actual reuse terms",
  "before": {"interval": ["2021-01-01", "2021-01-31"], "file": "before.geojson"},
  "after": {"interval": ["2023-01-01", "2023-01-31"], "file": "after.geojson"}
}]
```

On the overlap of the two surveyed areas, gain is the area present only in the later footprints. Loss is the area present only in the earlier footprints. Net change is gain minus loss. Archive and result versions identify the source material. Reported precision describes polygon arithmetic. Statistical uncertainty in the surveys remains unmeasured.

The default detector names the measured signal. A separate gradient-boosted interpreter can learn transition labels from reviewed candidate episodes. Its inputs include available optical and radar departures, timing, repeated evidence and optional same-season land-cover context. It emits an experimental interpretation or unknown, and exposes a model margin. A trusted, separately trained artifact can be loaded via `GEOWATCH_CHANGE_INTERPRETER`. No globally validated cause classifier is bundled. Public change alerts remain disabled.

## Evaluate against independent observations

The validation harness accepts one JSONL row per cell, time interval and target, alongside a cell-detail export from the app or standalone command. A review must establish whether that target changed, stayed stable, or was unobserved at the reporting scale. Cite acquisition dates, licence and spatial support in the reference record. Each changed case represents a single known target episode and supplies an inclusive `onset` date bracket. A case can use `signals` to declare which fully observed channels establish detectability for a semantic target.

```json
{"id":"review-01","region":"site-a","block":"site-a-west","split":"development","cell_id":"as exported","period":["2023-01-01","2023-04-01"],"detail":"cell-0.json","target":"greenness_loss","state":"changed","onset":["2023-02-02","2023-02-10"],"independent":true,"reference":"independent dated survey and reviewer record","license":"record actual terms","event_labels":{"reviewed-event-id":"clearing"}}
```

For training, review individual episode IDs and include false alarms labelled `stable` or `other`. Reserve entire later regions, blocks and cells for evaluation. Training reads only development detail files. Evaluation rejects geographical or temporal overlap with the trained artifact. Keep the held-out scores sealed until the protocol and detector are frozen.

```sh
python -m experiments.change_history.validate fit cases.jsonl --model interpreter.json
python -m experiments.change_history.validate evaluate cases.jsonl --model interpreter.json
```

The report includes precision, recall including abstentions, stable-cell false positives, judged coverage and confirmation delay. It separates target and region results and resamples whole regions for uncertainty. Sampling is the reviewer's responsibility. A hand-selected case study cannot establish a global false-alarm rate.

## Existing evidence

The [reservoir check](REPORT.md) and [wildfire check](VEGETATION.md) cover four deliberately selected cells with independent reference observations. The [building-survey check](SURVEY.md) measures polygon differences where two survey epochs have common coverage. The [held-out building benchmark](BUILDING_ENDPOINT_RESULTS.md) compares an experimental satellite estimator against zero and median change. The detector can also be exercised on synthetic histories with `python -m experiments.change_history.benchmark`.

At Navi Mumbai airport the original 2019–2024 dry-season test counted 138 vegetation increases and 75 decreases. It expected clearing to dominate change across the airport boundary. The airport's environmental impact assessment records that land development began in April 2017. The baseline already fell during project works. The airport boundary supplies no independent label for individual cells, and the cause of the increases remains unresolved. [Original test](../../05_BUILD_MANUAL.md) · [Airport environmental impact assessment](https://www.nmiairport.co.in/-/media/Project/NMIA/Circulars/NMIA_EIA_Report_2021.pdf)
