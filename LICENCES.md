# Data sources and licences (the public GeoWatch app)

GeoWatch is a **non-commercial research tool**. It runs on Google Earth Engine under Earth Engine's non-commercial terms, and some inputs carry non-commercial licences (marked below). Any commercial use needs these terms re-checked first.

| source | used for | licence | note |
|---|---|---|---|
| Google Earth Engine (platform) | all raster processing | [Earth Engine terms](https://earthengine.google.com/terms/), non-commercial project | non-commercial use only |
| Copernicus Sentinel-2 (`COPERNICUS/S2_HARMONIZED`, `S2_SR_HARMONIZED`) | ground cover, imagery, change | Copernicus open licence | attribution: "Contains modified Copernicus Sentinel data" |
| Copernicus Sentinel-1 (`COPERNICUS/S1_GRD`) | water and change | Copernicus open licence | attribution as above |
| Copernicus DEM GLO-30 (`COPERNICUS/DEM/GLO30_2024_1`) | terrain | Copernicus DEM licence (free, attribution) | "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018, provided under COPERNICUS by the European Union and ESA" |
| **FABDEM** (`projects/sat-io/open-datasets/FABDEM`) | terrain | **CC BY-NC-SA 4.0** | **non-commercial; share-alike for derived products**; attribution: Hawker et al. 2022, University of Bristol / Fathom |
| **MERIT Hydro** (`MERIT/Hydro/v1_0_1`) | HAND, upstream area | dual **CC BY-NC 4.0** or ODbL 1.0 | used here under CC BY-NC 4.0 (non-commercial); attribution: Yamazaki et al. 2019 |
| JRC Global Surface Water (`JRC/GSW1_4`) | permanent / historic water | free use, attribution | EC JRC / Google |
| JRC GHSL built-up (`JRC/GHSL/P2023A/GHS_BUILT_S/2020`) | built-up share | CC BY 4.0 | EC JRC |
| Google Dynamic World (`GOOGLE/DYNAMICWORLD/V1`) | change context | CC BY 4.0 | Google / World Resources Institute |
| Google Open Buildings (v3 polygons, temporal v1) | buildings | CC BY 4.0 / ODbL (v3) | Google |
| NASA GPM IMERG V07 | rainfall | NASA open data policy | NASA |
| CHIRPS daily (`UCSB-CHG/CHIRPS/DAILY`) | rainfall | CC BY 4.0 | UCSB Climate Hazards Center |
| sat-io shoreline (`projects/sat-io/open-datasets/shoreline`) | distance to coast | per the source dataset (Sayre et al., global shoreline) | to confirm |
| OpenStreetMap (Overpass) | roads, waterways | ODbL 1.0 | © OpenStreetMap contributors |
| Esri World Imagery / reference labels (base map) | base map | Esri terms of use | attribution shown on the map |
| DataMeet Mumbai BMC wards | ward boundaries (Mumbai) | **to confirm** | cite the DataMeet repository |

Saved results live on the free server's temporary disk and can disappear after a restart or redeploy.
