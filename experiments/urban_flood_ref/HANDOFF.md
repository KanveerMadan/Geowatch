# Handoff to the flood-model session

The evidence package contains 36 radar incident tiles and 37 pre-event control tiles. Each line in [handoff_manifest.csv](handoff_manifest.csv) identifies a shipped model-compatible NPZ, its checksum, the two scientific maps, provenance and its evidence-review receipts.

Treat incident products as development candidates. Preserve the wet, dry and unknown label mask. The emitted dry labels are the detector’s restricted open-ground proxy. Ambiguous urban streets must remain unknown. Controls measure repeat-detection burden and have no event target for retraining. The three Weihui tiles share one flood and a SAR-derived benchmark used during development. Keep them in one development group. Quantify transfer on independently selected incidents in a future locked test.

External reviewer evidence and automatic optical checks have separate rows in the evidence tables. A shared-sensor external benchmark is not an independent sensor. Some automated optical maps may contain no observed wet or dry cells; inspect the actual denominators. Assisted visual interpretation on a small VHR patch supports only its reviewed footprint. Source imagery in download caches is outside this shipment.

| Unit | Acquisition | 30 m flooded | Dry | Ambiguous | Unobserved | Action |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| dharavi | 2017-08-29 | 0 | 0 | 7836 | 342 | Hold for review |
| dharavi_control | 2017-07-24 | 0 | 0 | 7836 | 342 | Exclude control |
| beira | 2019-03-26 | 2 | 0 | 19426 | 1872 | Hold for review |
| beira_control | 2019-02-18 | 0 | 0 | 19428 | 1872 | Exclude control |
| kerala_2018 | 2018-08-21 | 482 | 0 | 17595 | 13 | Hold for review |
| kerala_2018_control | 2018-07-16 | 43 | 0 | 18034 | 13 | Exclude control |
| usf_weihui_1 | 2021-07-27 | 207 | 0 | 18836 | 1 | Hold for review |
| usf_weihui_1_control | 2021-06-21 | 0 | 0 | 19043 | 1 | Exclude control |
| usf_weihui_2 | 2021-07-27 | 0 | 0 | 18669 | 237 | Hold for review |
| usf_weihui_2_control | 2021-06-21 | 0 | 0 | 18669 | 237 | Exclude control |
| usf_weihui_3 | 2021-07-27 | 0 | 0 | 18496 | 0 | Hold for review |
| usf_weihui_3_control | 2021-06-28 | 0 | 0 | 18496 | 0 | Exclude control |
| mabi_2018 | 2018-07-10 | 41 | 0 | 12616 | 5839 | Hold for review |
| mabi_2018_control | 2018-06-04 | 24 | 0 | 12633 | 5839 | Exclude control |
| nagano_2019 | 2019-10-17 | 0 | 0 | 15803 | 3379 | Hold for review |
| nagano_2019_control | 2019-09-11 | 0 | 0 | 15803 | 3379 | Exclude control |
| hitoyoshi_2020 | 2020-07-04 | 75 | 0 | 15847 | 2710 | Hold for review |
| hitoyoshi_2020_control | 2020-06-04 | 10 | 0 | 15912 | 2710 | Exclude control |
| hyderabad_2020 | 2020-10-21 | 7 | 0 | 18574 | 51 | Hold for review |
| hyderabad_2020_control | 2020-09-15 | 0 | 0 | 18581 | 51 | Exclude control |
| bima_2016_control | 2016-11-20 | 0 | 0 | 14289 | 3936 | Exclude control |
| sentani_2019 | 2019-03-19 | 0 | 1 | 17678 | 411 | Hold for review |
| sentani_2019_control | 2019-02-12 | 0 | 0 | 17679 | 411 | Exclude control |
| shah_alam_2021 | 2021-12-20 | 5 | 0 | 17886 | 199 | Hold for review |
| shah_alam_2021_control | 2021-11-15 | 0 | 0 | 17891 | 199 | Exclude control |
| hue_2020 | 2020-10-22 | 3 | 0 | 17729 | 900 | Hold for review |
| hue_2020_control | 2020-09-16 | 0 | 0 | 17732 | 900 | Exclude control |
| beledweyne_2019 | 2019-10-29 | 254 | 0 | 17694 | 7 | Hold for review |
| beledweyne_2019_control | 2019-09-24 | 0 | 0 | 17948 | 7 | Exclude control |
| bor_2020 | 2020-08-12 | 46 | 0 | 18033 | 11 | Hold for review |
| bor_2020_control | 2020-07-07 | 45 | 1 | 18033 | 11 | Exclude control |
| bozkurt_2021 | 2021-08-11 | 5 | 0 | 4662 | 13829 | Hold for review |
| bozkurt_2021_control | 2021-07-12 | 0 | 0 | 4667 | 13829 | Exclude control |
| shiraz_2019 | 2019-03-27 | 0 | 0 | 10907 | 7725 | Hold for review |
| shiraz_2019_control | 2019-02-19 | 0 | 0 | 10907 | 7725 | Exclude control |
| marikina_2020 | 2020-11-16 | 0 | 0 | 18201 | 159 | Hold for review |
| marikina_2020_control | 2020-10-13 | 0 | 0 | 18201 | 159 | Exclude control |
| belo_horizonte_2020 | 2020-01-24 | 0 | 0 | 16402 | 1823 | Hold for review |
| belo_horizonte_2020_control | 2019-12-24 | 0 | 0 | 16402 | 1823 | Exclude control |
| durban_2019 | 2019-04-30 | 8 | 0 | 13832 | 4792 | Hold for review |
| durban_2019_control | 2019-03-25 | 0 | 0 | 13840 | 4792 | Exclude control |
| jakarta_new_year_2020 | 2020-01-02 | 0 | 0 | 18071 | 19 | Hold for review |
| jakarta_new_year_2020_control | 2019-12-05 | 0 | 0 | 18071 | 19 | Exclude control |
| edgecumbe_2017 | 2017-04-11 | 657 | 6 | 17427 | 0 | Hold for review |
| edgecumbe_2017_control | 2017-03-06 | 1 | 24 | 18065 | 0 | Exclude control |
| rio_2019 | 2019-04-11 | 0 | 0 | 5601 | 12895 | Hold for review |
| rio_2019_control | 2019-03-06 | 0 | 0 | 5601 | 12895 | Exclude control |
| tbilisi_2015 | 2015-06-13 | 0 | 0 | 12543 | 5547 | Hold for review |
| tbilisi_2015_control | 2015-05-14 | 0 | 0 | 12543 | 5547 | Exclude control |
| puri_2019 | 2019-05-06 | 3 | 0 | 7713 | 10508 | Hold for review |
| puri_2019_control | 2019-04-03 | 4 | 0 | 15293 | 2927 | Exclude control |
| marsh_harbour_2019 | 2019-09-02 | 232 | 0 | 10534 | 7866 | Hold for review |
| marsh_harbour_2019_control | 2019-08-05 | 0 | 2 | 10764 | 7866 | Exclude control |
| gatineau_2017 | 2017-05-12 | 1 | 0 | 16068 | 2427 | Hold for review |
| gatineau_2017_control | 2017-04-06 | 0 | 0 | 16069 | 2427 | Exclude control |
| mocoa_2017 | 2017-04-01 | 0 | 0 | 14670 | 3286 | Hold for review |
| mocoa_2017_control | 2017-02-24 | 0 | 0 | 14670 | 3286 | Exclude control |
| beira_ufo_1ynv | 2019-03-26 | 0 | 0 | 11226 | 1 | Hold for review |
| beira_ufo_1ynv_control | 2019-02-18 | 0 | 0 | 11226 | 1 | Exclude control |
| beira_ufo_a69z | 2019-03-26 | 298 | 0 | 10877 | 52 | Hold for review |
| beira_ufo_a69z_control | 2019-02-18 | 0 | 0 | 11175 | 52 | Exclude control |
| cto_ufo_0p0o | 2019-10-04 | 0 | 0 | 7063 | 3857 | Hold for review |
| cto_ufo_0p0o_control | 2019-09-04 | 0 | 0 | 7063 | 3857 | Exclude control |
| cto_ufo_ebrl | 2019-10-04 | 0 | 0 | 5791 | 4921 | Hold for review |
| cto_ufo_ebrl_control | 2019-09-04 | 0 | 0 | 5791 | 4921 | Exclude control |
| ktm_ufo_P6SA | 2020-08-30 | 16 | 0 | 9808 | 988 | Hold for review |
| ktm_ufo_P6SA_control | 2020-07-25 | 0 | 0 | 9824 | 988 | Exclude control |
| ktm_ufo_L895 | 2020-08-30 | 76 | 0 | 10238 | 604 | Hold for review |
| ktm_ufo_L895_control | 2020-07-25 | 0 | 0 | 10314 | 604 | Exclude control |
| sps_ufo_7ev7 | 2020-11-25 | 39 | 0 | 10881 | 0 | Hold for review |
| sps_ufo_7ev7_control | 2020-10-26 | 0 | 0 | 10920 | 0 | Exclude control |
| sps_ufo_6oqt | 2020-11-25 | 1 | 0 | 10429 | 386 | Hold for review |
| sps_ufo_6oqt_control | 2020-10-26 | 0 | 0 | 10430 | 386 | Exclude control |

## Optional source-specific development aids

[label_options.csv](label_options.csv) lists every additional shipped NPZ and its provenance. Each uses the same Boolean flooded/valid schema. Published benchmark positives and visually reviewed optical cells and published human optical labels have separate files. Their masked neighbours remain unknown. Never replace the existing development references in place or count an incident used for training as an independent test.

The positive-only partial urban water target means at least one homogeneous 10 m patch within a built-up 30 m cell shows newly visible water. Those cells can overlap strict training labels. Keep a separate model target and denominator. The child-count raster records the observed area. An all-unknown package contributes no training rows.

| Unit | Source / target | Positive | Known dry | Licence |
| --- | --- | ---: | ---: | --- |
| usf_weihui_1 | benchmark | 3200 | 0 | CC BY 4.0 |
| usf_weihui_2 | benchmark | 879 | 0 | CC BY 4.0 |
| usf_weihui_3 | benchmark | 450 | 0 | CC BY 4.0 |
| beira_ufo_1ynv | published human optical | 157 | 2867 | CC BY 4.0 |
| beira_ufo_1ynv | partial urban water presence (positive-only) | 25 | 0 | CC BY 4.0 |
| beira_ufo_a69z | published human optical | 806 | 1389 | CC BY 4.0 |
| beira_ufo_a69z | partial urban water presence (positive-only) | 0 | 0 | CC BY 4.0 |
| cto_ufo_0p0o | published human optical | 0 | 0 | CC BY 4.0 |
| cto_ufo_0p0o | partial urban water presence (positive-only) | 0 | 0 | CC BY 4.0 |
| cto_ufo_ebrl | published human optical | 0 | 0 | CC BY 4.0 |
| cto_ufo_ebrl | partial urban water presence (positive-only) | 0 | 0 | CC BY 4.0 |
| ktm_ufo_P6SA | published human optical | 31 | 0 | CC BY 4.0 |
| ktm_ufo_P6SA | partial urban water presence (positive-only) | 3 | 0 | CC BY 4.0 |
| ktm_ufo_L895 | published human optical | 494 | 0 | CC BY 4.0 |
| ktm_ufo_L895 | partial urban water presence (positive-only) | 37 | 0 | CC BY 4.0 |
| sps_ufo_7ev7 | published human optical | 547 | 28 | CC BY 4.0 |
| sps_ufo_7ev7 | partial urban water presence (positive-only) | 113 | 0 | CC BY 4.0 |
| sps_ufo_6oqt | published human optical | 325 | 0 | CC BY 4.0 |
| sps_ufo_6oqt | partial urban water presence (positive-only) | 266 | 0 | CC BY 4.0 |

[Compatibility and retraining instructions](LOAD.md). Use a new registered DEV identifier, keep every tile from a flood in one split, and rebuild that identifier’s feature cache.
