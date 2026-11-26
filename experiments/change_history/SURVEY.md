# Independent building-footprint measurement

On 2026-11-19, GeoWatch compared the January 2018 and January 2020 SpaceNet 7 building surveys for the first public training site in catalogue order, L15-0331E-1257N_1327_3160_13 (California). These are the site's first and last available monthly mosaics. Six source files totaled 9.30 MiB.

| Quantity | Measured area |
| --- | ---: |
| Joint surveyed ground | 14,823,320 m² |
| Footprint in the later survey only | 41,287 m² |
| Footprint in the earlier survey only | 3,981 m² |
| Net change | +37,306 m² |

The importer takes the georeferenced monthly image alpha mask, subtracts the survey's unusable-data polygons, and clips the mapped footprints to this coverage. The production survey reader intersects the two coverage masks and measures polygon differences in UTM zone 10N. In this pair, both surveys cover the whole 14.82 km² site. A separate query outside it returned no measurement. Synthetic tests also verify a partially obscured site and a fully masked month.

These are differences between mapped building outlines. Boundary registration and delineation error are unmeasured, particularly relevant to the smaller loss estimate. The measurements preserve both monthly acquisition intervals and give no exact construction or demolition dates. Sentinel-2 and radar detection accuracy was outside this check.

Run the import in a dedicated directory. It caches and verifies six individually hashed public assets. The generated result contains source URLs, hashes, sizes, site bounds and measurements. The generated manifest can be supplied to GeoWatch through GEOWATCH_CHANGE_SURVEYS.

```sh
python -m experiments.change_history.spacenet_survey /tmp/geowatch-spacenet7-history
```

Source data and adapted survey files are attributed to SpaceNet Partners under CC BY-SA 4.0. [Dataset and licence](https://spacenet.ai/sn7-challenge/) · [Annotation and unusable-mask methodology](https://openaccess.thecvf.com/content/CVPR2021/papers/Van_Etten_The_Multi-Temporal_Urban_Development_SpaceNet_Dataset_CVPR_2021_paper.pdf)
