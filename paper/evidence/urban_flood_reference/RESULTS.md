# Development results

The 36 event tiles from 29 distinct incidents contain 234 confidently mapped urban wet cells. 203 were absent from the matched intensity-only map. The urban area contains 0 confidently dry cells, 290,402 ambiguous and 11,999 excluded or unobserved cells.

Across 37 earlier control tiles from 30 incident locations, the detector flagged 12 of 303,484 observed urban cells as wet. It classified 0 as confidently dry. The dates are nominal controls; independently observed non-water appears below only where available.

## Urban flood benchmark recovery

| Tile | Benchmark urban-flood cells | New detector | Matched darkening | Archived VV-drop |
| --- | ---: | ---: | ---: | ---: |
| usf_weihui_1 | 3200 | 14 | 0 | 34 |
| usf_weihui_2 | 879 | 0 | 0 | 62 |
| usf_weihui_3 | 450 | 0 | 0 | 11 |

The Weihui tiles cover one event. The external benchmark and the candidate both use SAR. The benchmark's flooded-urban denominator includes all such cells, including those outside the candidate’s own urban mask.

## Checks with optical evidence

Counts cover the detector’s urban stratum. Each row gives detected/reference counts for two observed classes. An empty or zero denominator leaves that measure unresolved.

| Unit | Evidence | Flagged / known wet | Flagged / known non-water |
| --- | --- | ---: | ---: |
| dharavi | Sentinel-2 visible water | 0/0 | 0/0 |
| dharavi_control | Sentinel-2 visible water | 0/0 | 0/0 |
| beira | Sentinel-2 visible water | 0/1 | 2/14342 |
| beira | Maxar visual review | 0/0 | 0/2 |
| beira_control | Sentinel-2 visible water | 0/0 | 0/0 |
| kerala_2018 | Sentinel-2 visible water | 0/0 | 0/0 |
| kerala_2018_control | Sentinel-2 visible water | 0/0 | 0/0 |
| usf_weihui_1 | Sentinel-2 visible water | 0/0 | 0/0 |
| usf_weihui_1_control | Sentinel-2 visible water | 0/0 | 0/404 |
| usf_weihui_2 | Sentinel-2 visible water | 0/0 | 0/0 |
| usf_weihui_2_control | Sentinel-2 visible water | 0/0 | 0/0 |
| usf_weihui_3 | Sentinel-2 visible water | 0/0 | 0/0 |
| usf_weihui_3_control | Sentinel-2 visible water | 0/0 | 0/12896 |
| mabi_2018 | Sentinel-2 visible water | 0/0 | 0/0 |
| mabi_2018_control | Sentinel-2 visible water | 0/0 | 0/0 |
| nagano_2019 | Sentinel-2 visible water | 0/0 | 0/2085 |
| nagano_2019_control | Sentinel-2 visible water | 0/0 | 0/5402 |
| hitoyoshi_2020 | Sentinel-2 visible water | 0/0 | 0/0 |
| hitoyoshi_2020_control | Sentinel-2 visible water | 0/0 | 0/0 |
| hyderabad_2020 | Sentinel-2 visible water | 0/0 | 0/0 |
| hyderabad_2020_control | Sentinel-2 visible water | 0/0 | 0/0 |
| bima_2016_control | Sentinel-2 visible water | 0/0 | 0/0 |
| sentani_2019 | Sentinel-2 visible water | 0/0 | 0/0 |
| sentani_2019_control | Sentinel-2 visible water | 0/0 | 0/0 |
| shah_alam_2021 | Sentinel-2 visible water | 0/0 | 0/0 |
| shah_alam_2021_control | Sentinel-2 visible water | 0/0 | 0/0 |
| hue_2020 | Sentinel-2 visible water | 0/0 | 0/0 |
| hue_2020_control | Sentinel-2 visible water | 0/0 | 0/0 |
| beledweyne_2019 | Sentinel-2 visible water | 0/0 | 0/0 |
| beledweyne_2019_control | Sentinel-2 visible water | 0/0 | 0/0 |
| bor_2020 | Sentinel-2 visible water | 0/0 | 0/0 |
| bor_2020_control | Sentinel-2 visible water | 0/0 | 0/0 |
| bozkurt_2021 | Sentinel-2 visible water | 0/0 | 0/0 |
| bozkurt_2021_control | Sentinel-2 visible water | 0/0 | 0/776 |
| shiraz_2019 | Sentinel-2 visible water | 0/0 | 0/0 |
| shiraz_2019_control | Sentinel-2 visible water | 0/0 | 0/6177 |
| marikina_2020 | Sentinel-2 visible water | 0/0 | 0/0 |
| marikina_2020_control | Sentinel-2 visible water | 0/0 | 0/0 |
| belo_horizonte_2020 | Sentinel-2 visible water | 0/0 | 0/0 |
| belo_horizonte_2020_control | Sentinel-2 visible water | 0/0 | 0/11268 |
| durban_2019 | Sentinel-2 visible water | 0/0 | 2/8672 |
| durban_2019_control | Sentinel-2 visible water | 0/23 | 0/2779 |
| jakarta_new_year_2020 | Sentinel-2 visible water | 0/0 | 0/0 |
| jakarta_new_year_2020_control | Sentinel-2 visible water | 0/0 | 0/0 |
| edgecumbe_2017 | Sentinel-2 visible water | 0/0 | 0/0 |
| edgecumbe_2017_control | Sentinel-2 visible water | 0/0 | 0/0 |
| rio_2019 | Sentinel-2 visible water | 0/0 | 0/0 |
| rio_2019_control | Sentinel-2 visible water | 0/0 | 0/3903 |
| tbilisi_2015 | Sentinel-2 visible water | 0/0 | 0/0 |
| tbilisi_2015_control | Sentinel-2 visible water | 0/0 | 0/0 |
| puri_2019 | Sentinel-2 visible water | 0/0 | 0/0 |
| puri_2019_control | Sentinel-2 visible water | 0/0 | 0/11044 |
| marsh_harbour_2019 | Sentinel-2 visible water | 0/0 | 0/0 |
| marsh_harbour_2019 | Maxar visual review | 0/0 | 0/0 |
| marsh_harbour_2019_control | Sentinel-2 visible water | 0/0 | 0/0 |
| gatineau_2017 | Sentinel-2 visible water | 0/0 | 0/0 |
| gatineau_2017_control | Sentinel-2 visible water | 0/0 | 0/0 |
| mocoa_2017 | Sentinel-2 visible water | 0/0 | 0/0 |
| mocoa_2017_control | Sentinel-2 visible water | 0/0 | 0/0 |
| beira_ufo_1ynv | Sentinel-2 visible water | 0/0 | 0/0 |
| beira_ufo_1ynv | UFO PlanetScope visible water | 0/0 | 0/0 |
| beira_ufo_1ynv_control | Sentinel-2 visible water | 0/0 | 0/0 |
| beira_ufo_a69z | Sentinel-2 visible water | 0/0 | 0/0 |
| beira_ufo_a69z | UFO PlanetScope visible water | 0/0 | 0/0 |
| beira_ufo_a69z_control | Sentinel-2 visible water | 0/0 | 0/0 |
| cto_ufo_0p0o | Sentinel-2 visible water | 0/0 | 0/429 |
| cto_ufo_0p0o_control | Sentinel-2 visible water | 0/0 | 0/0 |
| cto_ufo_ebrl | Sentinel-2 visible water | 0/0 | 0/4 |
| cto_ufo_ebrl_control | Sentinel-2 visible water | 0/0 | 0/0 |
| ktm_ufo_P6SA | Sentinel-2 visible water | 0/0 | 1/6625 |
| ktm_ufo_P6SA | UFO PlanetScope visible water | 0/0 | 0/0 |
| ktm_ufo_P6SA_control | Sentinel-2 visible water | 0/0 | 0/14 |
| ktm_ufo_L895 | Sentinel-2 visible water | 0/0 | 0/5446 |
| ktm_ufo_L895 | UFO PlanetScope visible water | 0/1 | 0/0 |
| ktm_ufo_L895_control | Sentinel-2 visible water | 0/0 | 0/2067 |
| sps_ufo_7ev7 | Sentinel-2 visible water | 0/0 | 0/0 |
| sps_ufo_7ev7 | UFO PlanetScope visible water | 0/17 | 0/0 |
| sps_ufo_7ev7_control | Sentinel-2 visible water | 0/0 | 0/0 |
| sps_ufo_6oqt | Sentinel-2 visible water | 0/0 | 0/0 |
| sps_ufo_6oqt | UFO PlanetScope visible water | 1/47 | 0/0 |
| sps_ufo_6oqt_control | Sentinel-2 visible water | 0/0 | 0/0 |

## Independent optical interpretation across the whole footprint

These counts also include visible surfaces outside the study's built-up mask. Compare the corresponding urban-only denominators above before drawing conclusions about streets.

| Unit | Evidence | Detected / observed wet | Flagged / observed dry | Optical minus radar days |
| --- | --- | ---: | ---: | ---: |
| beira | Maxar visual review | 0/0 | 0/2 | 0 |
| marsh_harbour_2019 | Maxar visual review | 0/0 | 0/0 | 3 |
| beira_ufo_1ynv | UFO PlanetScope visible water | 0/157 | 0/2867 | 0 |
| beira_ufo_a69z | UFO PlanetScope visible water | 178/806 | 2/1389 | 0 |
| ktm_ufo_P6SA | UFO PlanetScope visible water | 9/31 | 0/0 | -1 |
| ktm_ufo_L895 | UFO PlanetScope visible water | 24/494 | 0/0 | -1 |
| sps_ufo_7ev7 | UFO PlanetScope visible water | 27/547 | 0/28 | 0 |
| sps_ufo_6oqt | UFO PlanetScope visible water | 1/325 | 0/0 | 0 |

[Per-event intervals and reference timing](tables/agreement.csv). [Exact historical comparisons and reasons for unmatched acquisitions](tables/legacy_comparison.csv).
