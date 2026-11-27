# M6–M8 catalogue sources

- Natalie Lützow and Georg Veh, global Glacial Lake Outburst Flood Database, version 4.2. GeoWatch extracted identity, date and source-location fields and omitted the two descriptive header rows. The modified extract retains attribution under CC BY 4.0. The publisher MD5 of the confirmed worksheet is `37b4516f8ce80824dacb455ac4dfc1a0`. [Dataset and licence](https://zenodo.org/records/23370149) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- DFO – Flood Observatory, Global Flood Records, versioned Zenodo record 19288171. GeoWatch selected and normalised factual date, country, ID and cause metadata from the CSV under CC BY 4.0. Its publisher MD5 is `8fe3cd72474abe8d4d83641e2d33266f`. DFO's dam category includes controlled releases. [Dataset and licence](https://zenodo.org/records/19288171) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- United States Geological Survey. Stage and station observations from USGS Water Data for the Nation. Landsat Collection 2 data are in the public domain. Acknowledge USGS. [USGS acknowledgements](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits) · [Landsat data policy](https://www.usgs.gov/faqs/are-landsat-data-cloud-still-considered-be-within-public-domain)
- NOAA National Weather Service. The catalogue derives event facts from named NWS reports and station metadata. NWS material is public domain unless otherwise indicated. This independent GeoWatch analysis carries no agency endorsement. [NWS notice](https://www.weather.gov/disclaimer)
- European Union, Copernicus Sentinel data. The acquisition receipts use Sentinel-1 and Sentinel-2 metadata for the years shown in each row. Apply the official source and modification notices to any imagery-derived release. [Sentinel legal notice](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice)
- Other linked investigation and agency reports supply bibliographic references and independently restated event facts only. No third-party figures, report text, flood polygons, photographs or map products have been republished. Verify the individual product terms before reuse as a spatial label. The temporary imagery and stage query responses contain no redistributed paid imagery.

## Midland development reference

The 2019 National Land Cover Database layer is a USGS/MRLC land-cover product. Source USGS; the public land-cover data are used for observability. The Landsat surface reflectance and QA layers use the USGS policy above. [NLCD dataset and terms](https://developers.google.com/earth-engine/datasets/catalog/USGS_NLCD_RELEASES_2019_REL_NLCD) · [USGS Landsat quality bands](https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands)

Source: EC JRC/Google. Global Surface Water v1.4 occurrence and observation metadata are used under the Copernicus Programme's free-use terms with attribution. Cite J.-F. Pekel, A. Cottam, N. Gorelick and A. Belward, High-resolution mapping of global surface water and its long-term changes, Nature 540 (2016), 418–422. [Dataset terms and citation](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_Metadata)

LamaH-Ice by Helgason and Nijssen is distributed under Creative Commons Attribution on HydroShare. The catalogue converts the published location of station V299 from the archive's ISN93 / Lambert 1993 projection to WGS84. Gauge attributes row 74, easting 528767 m and northing 396882 m, identify the monitored reach. Icelandic Meteorological Office reports supply the dated downstream observations cited per incident. [LamaH-Ice dataset](https://doi.org/10.4211/hs.86117a5f36cc4b7c90a5d54e18161c91) · [Dataset paper](https://essd.copernicus.org/articles/16/2741/2024/)

Pakistan NDRMF and the Ukrainian Ministry of Infrastructure provide the two publicly cited reach locations. These are published geographic facts. The Pakistan location was cross-checked against the N-35 crossing in the existing Geofabrik Pakistan extract, © OpenStreetMap contributors. No OSM road geometry is distributed. [OSM attribution](https://www.openstreetmap.org/copyright)

## M6–M8 widening, labels and product (Claude Code, 2026-11-27)

- **Water Survey of Canada** hydrometric annual peaks (MSC GeoMet OGC API), used for crest dates and clock times. Contains information licensed under the Open Government Licence – Canada. [Licence](https://open.canada.ca/en/open-government-licence-canada) · [API](https://api.weather.gc.ca/collections/hydrometric-annual-peaks)
- **NOAA National Water Prediction Service** gauge records (historic crests, flood categories). Public domain; no endorsement implied. [NWPS API](https://api.water.noaa.gov/nwps/v1/docs/)
- **GEOGloWS v2** retrospective daily discharge, used only to time levee breaches with no gauge record (Kosi 2024). CC BY 4.0. [GEOGloWS](https://geoglows.ecmwf.int/)
- **Published measured readings and dates**, restated as facts with links in `event_evidence.json`:
  - Central Water Commission (India) flood situation reports;
  - MLIT Chugoku and the J-STAGE / JSNDS articles (Japan);
  - UNEP / UN Ukraine;
  - SANDRP;
  - OCHA ReliefWeb;
  - national news reports.
  No text, figures or maps were copied.
- **OpenStreetMap place points** via Nominatim, used to locate reaches: © OpenStreetMap contributors, ODbL. Only coordinates of named places are kept; no OSM geometry is redistributed. [Copyright](https://www.openstreetmap.org/copyright)
- **Copernicus Sentinel-2 L1C and s2cloudless probabilities** (Earth Engine `COPERNICUS/S2_HARMONIZED`, `COPERNICUS/S2_CLOUD_PROBABILITY`), used where no L2A exists. Copernicus Sentinel data terms as above.
- **MODIS Terra MOD10A1 v6.1 snow cover** (NASA NSIDC DAAC), used for the snow mask (labels) and the M8 applicability check (product). NASA data are free of restrictions; cite Hall & Riggs, MODIS/Terra Snow Cover Daily L3 Global 500m Grid, Version 61. [Dataset](https://nsidc.org/data/mod10a1/versions/61)
- **GLOF v4.2 lake points** (Lützow & Veh, CC BY 4.0, listed above) are redistributed as coordinates and lake names only in `configs/data/glof_lakes.csv` for the M6 applicability check. Modified extract: de-duplicated at 0.001°. Attribution as above.
- **Round 3's inputs** (MERIT Hydro, Copernicus GLO-30, FABDEM, GHSL, ESA WorldCover, JRC GSW) are reused unchanged under the terms recorded on `exp/flood-round3`. FABDEM is CC BY-NC-SA 4.0 and MERIT Hydro is CC BY-NC 4.0 or ODbL: both are non-commercial use only, as for the existing modules.
- **Scenario formulas** are cited, not copied:
  - Froehlich (1995), J. Water Resour. Plann. Manage. 121(1);
  - Walder & Costa (1996), Earth Surf. Process. Landforms 21;
  - Andreadis, Schumann & Pavelsky (2013), Water Resour. Res. 49.
