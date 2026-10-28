# Literature table: no matched benchmark (item 69)

**Claim.** No published benchmark combines all three properties a fair
comparison for GeoWatch would need:

1. **Resolution:** 10 m multispectral (Sentinel-2).
2. **Protocol:** evaluation on cities held out from training (leave-one-city-out
   or similar), across Global South cities that include informal settlements.
3. **Task:** dense per-pixel output with more than a binary target.

The gap is the finding. A number-to-number comparison against any row below
would conflate resolution, protocol or task differences with model quality
(`03_EVIDENCE.md` §D.4).

**No GeoWatch number appears in this table.** The retired checkpoint's LOCO
figure is excluded. It describes a materially easier task than the pipeline
performs (`04_FINDINGS_LEDGER.md` C43), and its pipeline is retired
(`08_STATE.md` §RETIRED). GeoWatch's own class count is left as *unsettled*
because the taxonomy is open until item 21.

**Sourcing.** Each cell was checked against the source's own record (paper,
dataset page or official catalog) on 2026-10-28. A cell marked
*not confirmed* is one that check could not establish. It is left blank on
purpose, not filled from memory.

| work | resolution / sensor | protocol | class count | informal settlements? | matches all three? |
|---|---|---|---|---|---|
| **Dynamic World** — Brown et al., *Sci Data* 9:251 (2022), doi:10.1038/s41597-022-01307-4 | 10 m, Sentinel-2 | global; validated against an expert-consensus test set of held-out tiles, each labelled independently by three experts (tile count *not confirmed*: secondary sources disagree) | 9 | no (one built-up class) | no: protocol holds out tiles, not cities |
| **ESA WorldCover 2020 v100** — Zanaga et al. (2021), doi:10.5281/zenodo.5571936 | 10 m, Sentinel-1/2 | global map; independent statistical validation on a sample (CEOS WGCV LPV), OA 74.4 % | 11 (FAO LCCS) | no | no: a map product validated by point sampling, not a cross-city segmentation protocol |
| **So2Sat LCZ42** — Zhu et al., arXiv:1912.12171 | 10 m, Sentinel-1/2 patches | **cities split into non-overlapping train / validation / test sets**; 42 agglomerations + 10 smaller areas | 17 (local climate zones) | indirectly (LCZ morphology classes) | no: **patch-level scene classification**, not per-pixel |
| **LoveDA** — Wang et al., NeurIPS 2021 Datasets & Benchmarks, arXiv:2110.08733 | 0.3 m | urban ↔ rural domain adaptation within 3 Chinese cities (Nanjing, Changzhou, Wuhan) | 7 | no | no: VHR, and the domain split is urban/rural, not held-out city |
| **OpenEarthMap** — Xia et al., WACV 2023, arXiv:2210.10732 | 0.25–0.5 m | 97 regions, 44 countries, 6 continents; also evaluated for unsupervised domain adaptation | 8 | not as a class | no: VHR |
| **Wurm et al.**, *ISPRS J. Photogramm.* 150:59–69 (2019) | QuickBird VHR → transferred to Sentinel-2 (10 m) and TerraSAR-X | transfer learning across sensors (study-area split *not confirmed*) | slum mapping (class count *not confirmed*) | **yes** | no: a cross-*sensor* protocol, not cross-city |
| **Gram-Hansen et al.**, AIES 2019 (arXiv:1812.00812 is a related preprint) | Sentinel-2 (10 m) and VHR | trained on Northern Nairobi and Medellín, predicted on other regions; reports a cross-region drop (exact design *not confirmed*) | informal-settlement presence (class count *not confirmed*) | **yes** | no: target is settlement presence, not multi-class |
| *what a match would need* (GeoWatch's evaluation target) | 10 m, Sentinel-2 | held-out city across Global South cities | *unsettled (item 21)* | yes | — |

## What the table shows

- **Only two rows evaluate across geography at 10 m.** So2Sat LCZ42 holds
  out cities but classifies patches. Gram-Hansen et al. predict on held-out
  regions but map one settlement target. Neither is a dense multi-class
  per-pixel benchmark.
- **Every dense multi-class benchmark here is either VHR** (LoveDA,
  OpenEarthMap) **or validated on held-out tiles or samples, not held-out
  cities** (Dynamic World, WorldCover). Their numbers carry a resolution
  advantage or an easier protocol, the two confounds §D.4 warns about.
- **The informal-settlement rows are binary or near-binary.** Multi-class
  per-pixel land cover inside informal settlements at 10 m, evaluated across
  held-out cities, has no published reference point in this check.

**Limits of this check.** Seven works, chosen as the nearest neighbours on
each axis. This is not a systematic review. The claim is "no match among
the closest candidates", not "no match exists". A systematic search
(protocol: databases, query strings, inclusion rules fixed in advance) would
be needed to make the stronger claim. Work published since 2025 is the most
likely place for a match to appear.

## Sources consulted (2026-10-28)

- Dynamic World: [Earth Engine catalog](https://developers.google.cn/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1?authuser=4) · [expert-consensus validation tiles](https://zenodo.org/records/4766451) · [training data record](https://doi.pangaea.de/10.1594/PANGAEA.933475)
- WorldCover: [product documentation](https://worldcover2020.esa.int/documentation) · [CEOS](https://ceos.org/gst/worldcover.html) · [WUR dataset record](https://research.wur.nl/en/datasets/esa-worldcover-10-m-2020-v100/) · [NASA GLAM record](https://glam1.gsfc.nasa.gov/api/doc/cropmask/v1/ESA-WorldCover_2020_crops)
- So2Sat LCZ42: [arXiv:1912.12171](https://export.arxiv.org/abs/1912.12171) · [TFDS catalog](https://tensorflow.google.cn/datasets/catalog/so2sat)
- LoveDA: [NeurIPS paper](https://datasets-benchmarks-proceedings.neurips.cc/paper/2021/file/4e732ced3463d06de0ca9a15b6153677-Paper-round2.pdf) · [Zenodo](https://zenodo.org/records/5706578)
- OpenEarthMap: [WACV 2023](https://openaccess.thecvf.com/content/WACV2023/html/Xia_OpenEarthMap_A_Benchmark_Dataset_for_Global_High-Resolution_Land_Cover_Mapping_WACV_2023_paper.html) · [arXiv:2210.10732](https://arxiv.org/abs/2210.10732v1)
- Wurm et al. 2019: [mediaTUM full text](https://mediatum.ub.tum.de/doc/1539147/1539147.pdf) · [DLR elib](https://elib.dlr.de/126606)
- Gram-Hansen et al. 2019: [AIES paper](https://www.aies-conference.com/2019/wp-content/papers/main/AIES-19_paper_48.pdf) · [arXiv:1812.00812](https://arxiv.org/pdf/1812.00812)
