# Dixie Fire vegetation check

The National Park Service documented high-intensity burning on Flatiron Ridge near Drakesbad in Lassen Volcanic National Park and identified western trails that escaped the 2021 Dixie Fire. Areas of unchanged vegetation also occurred inside the fire perimeter. We therefore used local burn-severity measurements to check the forest cells. [NPS fire chronology](https://www.nps.gov/lavo/learn/nature/dixie-fire.htm) · [NPS fire effects](https://www.nps.gov/lavo/learn/nature/dixie-fire-effects.htm) · [NPS Flatiron Ridge photo](https://www.nps.gov/lavo/learn/nature/dixie-fire-qa.htm) · [NPS recovery overview](https://www.nps.gov/lavo/learn/management/post_fire_recovery.htm)

Before retrieving cell data, we recorded the 100 m cell at 121.399° W, 40.456° N as the expected greenness-loss site and 121.582° W, 40.531° N as the west-park comparison. Both were kept. Sentinel-2 supplied the inputs, grouped by relative orbit. The local seasonal history ran from January 2018 through July 2021. The replay monitored August through October 2021. The same frozen detector operated in the [reservoir check](REPORT.md).

## Independent evidence at the measured cells

The USDA Forest Service and USGS MTBS product identified Dixie Fire event CA3987612137920210714. All 12 native 30 m pixel centres in the Flatiron Ridge cell were classified high severity in the annual mosaic. MTBS lists Landsat 8 path 44 row 32 imagery from July 8, 2020 and July 14, 2022, separate from GeoWatch's Sentinel-2 input. The exact burn date of the 100 m cell is unknown. [USFS/USGS MTBS severity](https://developers.google.com/earth-engine/datasets/catalog/USFS_GTAC_MTBS_annual_burn_severity_mosaics_v1) · [USFS/USGS MTBS fire boundaries](https://developers.google.com/earth-engine/datasets/catalog/USFS_GTAC_MTBS_burned_area_boundaries_v1)

Landsat 8 also supplied same-season September–October evidence for 2020 and 2021. Each entry below is the median of the date-level medians across available clear, unsaturated pixels within the selected cell. These measurements and MTBS share a Landsat lineage.

| Site | Clear dates 2020 / 2021 | Landsat NDVI 2020 → 2021 | Landsat normalized burn ratio 2020 → 2021 |
|---|---:|---|---|
| Flatiron Ridge | 4 / 3 | 0.731 → 0.183 | 0.536 → −0.362 |
| West park | 5 / 6 | 0.842 → 0.832 | 0.766 → 0.804 |

The west-park cell lay outside the 2021 mapped burns, so its MTBS severity samples had no class. The retained Landsat greenness and burn-ratio evidence supports a stable forest comparison at the seasonal scale. Brief disturbances between images remain possible.

## Frozen detector output

| Cell | Sentinel-2 date/track groups fetched | Usable history / monitoring | Raw signal episodes |
|---|---:|---:|---|
| Flatiron Ridge | 277 | 157 / 7 | Greenness loss first seen August 22, confirmed August 27 |
| West park | 277 | 125 / 14 | Five candidates on three dates, none confirmed |

At Flatiron Ridge the initial onset interval was August 12–22. A 30-day gap between accepted observations split later evidence into a second greenness-loss episode, first seen September 26 and confirmed October 1. October 16 contributed a further isolated greenness-loss candidate. The SWIR/NIR built-surface index also rose in a confirmed September episode and an October candidate. The site supplies independent evidence for vegetation loss, and no independent evidence for construction.

At the comparison cell, August 17 and August 27 each produced a greenness-loss candidate and a water-index-gain candidate. September 6 produced a built-surface-index-gain candidate. None had corroborating observations under the frozen operating policy. All three signals at both sites carried partial temporal coverage in the monitoring interval. The candidate signals could reflect short-lived surface or atmospheric conditions.

These four development cells across the water and forest checks show that the measurement and detection path can work and can yield repeated episodes from a single disturbance. Their purposeful selection precludes estimating class accuracy or false-alarm rates. [Raw episode summary, reference scene IDs and detector hash](vegetation_results.json)

To repeat this check in a configured Earth Engine environment, run the following from the repository root.

```sh
python -m experiments.change_history.vegetation_check --cache /tmp/geowatch-change-check
```
