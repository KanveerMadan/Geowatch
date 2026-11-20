# Two-cell development check of the change-history pipeline

GeoWatch detected the loss of open-water signal in a drained reservoir cell and reported no water-loss episode in an upstream comparison cell. This check exercised real Earth Engine observations, seasonal detection, storage and retrieval. Two deliberately selected cells support no estimate of global accuracy.

## Fixed design

The 100 m UTM cells contain 34.355° E, 47.525° N in Kakhovka Reservoir and 32.485° E, 49.318° N in upstream Kremenchuk Reservoir. Both were fixed before their observations or detector outputs were examined. The target was the change in open water after the Kakhovka dam breach on June 6, 2023. Gauge records from Nikopol and independent radar observations document the reservoir drawdown at regional scale. [Primary gauge and satellite analysis](https://doi.org/10.1029/2024WR038314)

The detector used only Sentinel-2, with every available acquisition grouped by day and orbit. All 25 fixed 20 m sample centres in each cell had to be usable. Training and within-site temporal calibration used January 1, 2020 through May 31, 2023. The prospective replay monitored June 1 through August 31, 2023 with the default operating policy. Its three retrospective calibration blocks per cell give limited evidence about false alarms. New scenes may enter the catalog after acquisition, so the timing below measures acquisition dates. The check used the frozen detector version seasonal-history-v1. The measured output and source hashes, scene IDs and dates appear in [live_results.json](live_results.json).

The reference used the USGS Landsat 8 and 9 QA_PIXEL water bit. It counted native clear, unsaturated pixel centres inside each cell during May 1–June 5 and July 1–August 31. Each sensor has its own footprint and grid. These classified pixel-dates are correlated observations of two small areas. Clouds, ice, suspended sediment and vegetation can complicate optical classification, and individual discordant dates are retained in the artifact. [USGS Landsat quality bands](https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands)

## Measured results

| Cell | Sentinel-2 date/track groups fetched | Usable history / monitoring | Landsat clear pixel-dates marked water, before → after | Detector result |
|---|---:|---:|---|---|
| Kakhovka | 526 | 212 / 25 | 24/24 over 2 dates → 1/55 over 5 dates | First water loss June 20, confirmed June 25 |
| Kremenchuk | 525 | 182 / 24 | 60/60 over 5 dates → 105/120 over 10 dates | No water loss. Two isolated greenness gains remained candidates |

At Kakhovka, the first orbit bracketed onset between June 5 and June 20. Its first detection and confirmation were 14 and 19 days after the regional breach. There is no independent daily timestamp of water recession at the exact cell. The second Sentinel-2 orbit issued another water-loss episode on August 2, confirmed August 7. Both orbits also recorded increases in the SWIR/NIR built-surface index, on June 25 and August 17. Exposed reservoir bed is a concrete example of why that index alone cannot identify construction. These four records describe signal episodes at one site and share one sensor lineage.

At Kremenchuk, both greenness candidates were single observations, on August 15 and August 27. Landsat marked all 12 clear samples as nonwater on August 27 and all 12 as water on August 28. The comparison supports generally persistent open water while leaving the cause and reality of brief surface anomalies unresolved.

## Other source checks

At one Navi Mumbai airport cell containing 73.054° E, 18.990° N, January 1–16, 2023 produced six complete acquisition groups: three Sentinel-2, one descending Sentinel-1 relative orbit 34 (VV/VH), one Landsat 8 and one Landsat 9. The check verified real, finite indices and radar measurements. It tested retrieval only.

At that cell Open Buildings supplied an annual 2022 record, targeted to June 30 using imagery spanning January 1–December 27. GeoWatch consequently exposed it from December 27. The valid sample mean confidence was 0.0. This measurement describes the source product at those sampled locations and carries no physical area or construction count. The January 2023 sub-month request correctly returned no new annual acquisition. [Open Buildings Temporal metadata](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_Research_open-buildings-temporal_v1)

## Reproduction

From the repository root, use a configured Earth Engine project and a change-only cache.

```sh
python -m experiments.change_history.live_check prepare --cache /tmp/geowatch-change-check
python -m experiments.change_history.live_check evaluate --cache /tmp/geowatch-change-check
python -m experiments.change_history.live_check buildings --cache /tmp/geowatch-change-check
```

The first step acquires the two cells and Landsat comparison windows sequentially. The second uses the ordinary history pipeline, then reads back its cell records. Source catalogs can be refreshed over time. All three stages leave the flood caches separate.
