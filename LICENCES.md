# Data licences: current status

These are the datasets GeoWatch's flood outputs read, as recorded on 2026-11-21. "Commercial use" means use inside a product that is sold or used commercially.
- **yes:** the terms say so.
- **no:** the terms forbid it.
- **unconfirmed:** the terms were not read in full, or sources conflict. The owner is checking GLO-30 and HydroSHEDS.

Earlier notes: `experiments/flood_learned/REPORT.md` §7 and `paper/evidence/M2_pluvial/METHOD.md`.

## Inputs to the learned flood output (`learned_flood`, open variant)
| dataset | used for | licence | commercial use | source |
|---|---|---|---|---|
| Copernicus DEM GLO-30 (2024_1) | terrain, elevation | Copernicus WorldDEM-30 licence; attribution "© DLR e.V." / "Produced using Copernicus WorldDEM-30 © DLR e.V." | **unconfirmed** (no purpose restriction found in the summary; full text not read) | [licence PDF](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/DEM/resources/license/License-COPDEM-30.pdf), [EE catalogue](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30_2024_1) |
| HydroSHEDS v1 15ACC | flow accumulation | HydroSHEDS licence ("free for non-commercial and commercial use", conditions in TechDoc App. A); one catalogue record says CC BY-NC 3.0 | **unconfirmed** (sources conflict) | [terms](https://hydrosheds.org/terms-of-use), [TechDoc v1.4](https://data.hydrosheds.org/file/technical-documentation/HydroSHEDS_TechDoc_v1_4.pdf), [Stanford record](https://purl.stanford.edu/zc665xv7392) |
| JRC Global Surface Water 1.4 | occurrence, recurrence, permanent water | Copernicus programme, free; attribution "Source: EC JRC/Google" | yes | [EE catalogue](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater) |
| OpenStreetMap | water mask, distance to water | ODbL 1.0 | yes (share-alike for derived databases; attribution) | [copyright](https://www.openstreetmap.org/copyright) |
| CHIRPS v2 | annual and design-day rain | CC0 / public domain (per EE and NOAA listings) | yes | [EE catalogue](https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY) |
| NASA GPM IMERG V07 | rain intensity | NASA open data policy | yes (not re-checked this round) | [NASA data policy](https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance) |
| SoilGrids (clay) | clay share | CC BY 4.0 | yes (not re-checked this round) | [ISRIC](https://www.isric.org/explore/soilgrids/faq-soilgrids) |
| ESA WorldCover 2020 / 2021 | land-cover fractions, built-up mask | CC BY 4.0 | yes (not re-checked this round) | [ESA WorldCover](https://esa-worldcover.org/en/data-access) |
| Sentinel-2 L1C + Cloud Score+ | pre-event NDVI | Copernicus open licence; Cloud Score+ CC BY 4.0 | yes (not re-checked this round) | [Copernicus legal notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice), [EE catalogue](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_CLOUD_SCORE_PLUS_V1_S2_HARMONIZED) |
| JRC GHSL GHS-BUILT-S 2020 (P2023A) | built-up share, not-assessed mask | CC BY 4.0 | yes | [GHSL](https://human-settlement.emergency.copernicus.eu/download.php) |
| sat-io shoreline outlines | distance to coast | per the sat-io catalogue entry | **unconfirmed** | [sat-io](https://gee-community-catalog.org/) |

## Other production flood inputs
| dataset | used for | licence | commercial use | source |
|---|---|---|---|---|
| FABDEM | pluvial and coastal modules; downloaded in the learned margin stack but not used by the learned output | CC BY-NC-SA 4.0 | **no** | [Bristol data.bris](https://data.bris.ac.uk/data/dataset/s5hqmjcdj8yo2ibzi9b4ew3sn) |
| MERIT Hydro | fluvial module (now experimental), HAND baseline | CC BY-NC 4.0 or ODbL 1.0 (dual) | only under ODbL (share-alike) | [MERIT Hydro](https://global-hydrodynamics.github.io/MERIT_Hydro/) |

## Validation data (labels and references; not shipped in outputs)
| dataset | used for | licence | commercial use | source |
|---|---|---|---|---|
| Copernicus EMS rapid mapping | flood references | CEMS terms of use (information purposes; attribution) | **unconfirmed** for redistribution | [EMS terms](https://emergency.copernicus.eu/mapping/ems/cite-copernicus-emergency-management-service) |
| Sentinel-1 GRD | VV-drop flood references | Copernicus open licence | yes | as Sentinel-2 above |
| UNOSAT products | round-4 references | varies by product; not recorded for FL20220808PAK, FL20220525BGD | **unconfirmed** | product pages |
| UrbanSARFloods v1 | urban-reference test (Weihui) | CC BY 4.0 | yes | [Hugging Face](https://huggingface.co/datasets/S1Floodbenchmark/UrbanSARFloods_v1) |
| IGN MDT05 (Spain) | Valencia SFINCS terrain | CC BY 4.0 (IGN / CNIG) | yes | [CNIG](https://centrodedescargas.cnig.es/) |

## Planned for flood round 2 (status before use)
| dataset | licence | commercial use | source |
|---|---|---|---|
| NOAA CO-OPS water levels | US federal public domain | yes | [CO-OPS API](https://api.tidesandcurrents.noaa.gov/api/prod/) |
| USGS 3DEP | US federal public domain | yes | [USGS 3DEP](https://www.usgs.gov/3d-elevation-program) |
| UHSLC tide gauges | per UHSLC data policy (free; citation) | **unconfirmed** | [UHSLC](https://uhslc.soest.hawaii.edu/) |
| GESLA-3 | free for research; terms per contributing agency | **unconfirmed** | [GESLA](https://gesla787883612.wordpress.com/) |
| Copernicus GTSM (CDS) | Copernicus licence | yes; needs a CDS account, used only if one already exists | [CDS](https://cds.climate.copernicus.eu/) |
| GEDTM30 | CC BY 4.0 (per data.gov / OpenGeoHub) | yes if CC BY holds; the server failed reads in round 1 | [OpenGeoHub](https://peerj.com/articles/19673) |

## Added for flood round 3 (2026-11-22)
| dataset | used for | licence | commercial use | source |
|---|---|---|---|---|
| GEOGloWS v2 retrospective discharge + model tables | discharge peaks per reach, rating curves, event typing | CC BY 4.0 (`licenses.md` in the `geoglows-v2` S3 bucket, read 2026-11-22) | yes (attribution) | [GEOGloWS](https://geoglows.org/), s3://geoglows-v2 |
| NASA GPM IMERG V07 (Earth Engine `NASA/GPM_L3/IMERG_V07`) | rain-peak timing, event rain | NASA open data policy | yes | [NASA data policy](https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance) |
| ERA5 / ERA5-Land (CDS) | antecedent soil moisture, rain checks | Copernicus product licence (accepted on the account 2026-11-22; full text not re-read) | **unconfirmed** | [CDS](https://cds.climate.copernicus.eu/) |
| ASF HyP3 on-demand InSAR (from Sentinel-1 SLC) | urban coherence-drop labels (planned) | Copernicus open licence for Sentinel-1 derived products | yes | [HyP3](https://hyp3-docs.asf.alaska.edu/) |
| GloFAS (EWDS) | discharge (planned) | CEMS terms of use; **terms not yet accepted on the account** | not used yet | [EWDS](https://ewds.climate.copernicus.eu/) |
| Maxar Open Data | VHR post-event imagery for urban labels (planned) | CC BY-NC 4.0 | **no** (evaluation / paper only; never in product outputs) | [Maxar Open Data](https://www.maxar.com/open-data) |
| MMFlood (Zenodo 6534637) | event list + AOI footprints only (activation code, date, DEM tile headers); labels are our own Sentinel-1 | CC BY 4.0 (Zenodo record) | yes (attribution) | [Zenodo 6534637](https://zenodo.org/records/6534637) |
| Sen1Floods11, Kuro Siwo | candidate extra labelled events (planned) | to check before use | to check | dataset pages |
| NYC 311 Service Requests (NYC Open Data `erm2-nwe9`, `76ig-c548`) | urban rain / coastal labels from street-flooding reports (validation only) | **no licence named** in the dataset metadata (checked 2026-11-22); NYC Open Data Law makes the data public. nyc.gov's site terms reserve rights over site content without clearly covering datasets | **unconfirmed**. Validation only; raw reports are never committed or redistributed, only counts and scores | [NYC Open Data](https://opendata.cityofnewyork.us/) |
| City of Chicago 311 Service Requests (`v6vf-nfxy`) | as NYC | dataset metadata says "See Terms of Use" (the terms page returned 403 to automated reads) | **unconfirmed**; as NYC | [Chicago Data Portal](https://data.cityofchicago.org/) |
| NOAA CO-OPS water levels (The Battery 8518750) and flood thresholds | coastal typing of 311 events | US government public domain ("may be used freely by the public"); attribution requested | yes | [CO-OPS disclaimers](https://tidesandcurrents.noaa.gov/disclaimers.html) |
| NOAA NCEI Storm Events database (details files) | flash-flood episode list (metadata only; FLASH_SE_DESIGN) | US government public domain; attribution requested | yes | [Storm Events](https://www.ncdc.noaa.gov/stormevents/) |
| USGS 3DEP 10 m DEM (via Earth Engine `USGS/3DEP/10m_collection`) | 10 m lidar terrain features for US rain units (fine_feats) | US government public domain | yes | [3DEP](https://www.usgs.gov/3d-elevation-program) |
