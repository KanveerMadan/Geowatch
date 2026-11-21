# M2 pluvial (rain / urban): method

## Model
- Pre-registered choice for this type: **`open__lgbm`** (PREREGISTRATION.md §4; DEV leave-region-out mean AUC, tie margin 0.005, logistic before LightGBM, open before full).
- `open` features (26, all per 30 m cell in a 4 km box): GLO-30 slope, curvature, TPI 990 m, height above the 2 km minimum, depression depth, HAND to mapped water; log HydroSHEDS accumulation; distance to mapped water; JRC occurrence and recurrence; CHIRPS/IMERG rain statistics (p99.9 hourly, design day, annual); SoilGrids clay; ESA WorldCover fractions (8 classes); pre-event NDVI (Sentinel-2, Cloud Score+); GLO-30 elevation; distance to coast (capped 50 km); GHSL built share.
- Logistic regression: standardised features, L2, C = 1.0. LightGBM: 300 trees, 15 leaves, learning rate 0.05, min 1,089 rows per leaf (one 990 m block), subsample 0.7, colsample 0.8, L2 1.0 (flood_learned.model; unchanged since batch 0).
- Trained on all 67 DEV units, every event equal weight; isotonic calibration on pooled leave-region-out predictions. Final model sha256: `d76aba72f0ec7e59b73ef850730efc6d35c6e6599ca29ba9d1b3e006906c2ad8`.

## Evaluation
- Labels per cell: flooded / dry / unobserved (unobserved never dry); JRC occurrence >= 80 % excluded.
- Primary metric: within-event ROC AUC of the raw score (D15). 95% CIs from a paired 990 m block bootstrap (1,000 reps) inside each event, then a cluster x block two-stage bootstrap of the mean; Δ vs HAND paired on the same blocks.
- Pass bar (pre-registered): mean within-event AUC >= 0.70 AND the lower 95% bound of Δ vs HAND > 0 AND >= 3 units in >= 2 clusters.
- Secondary: average precision, area-matched IoU, calibration (Van Calster weak calibration).

## Inputs and licences

| input (open variant) | licence | commercial use |
|---|---|---|
| Copernicus DEM GLO-30 2024_1 (terrain, elevation) | Copernicus WorldDEM-30 licence, attribution "© DLR e.V." | no purpose restriction found; confirm full text |
| HydroSHEDS v1 15ACC (accumulation) | HydroSHEDS terms (free incl. commercial) vs one catalogue CC BY-NC 3.0 | **conflicting; confirm** |
| JRC Global Surface Water 1.4 (occurrence, recurrence) | Copernicus free; "Source: EC JRC/Google" | yes |
| OpenStreetMap (water, distance to water) | ODbL | yes, share-alike for derived databases |
| CHIRPS v2, IMERG V07 (rain) | public domain / NASA open data | yes |
| SoilGrids (clay), ESA WorldCover (land cover), Cloud Score+ / Sentinel-2 (NDVI) | CC BY 4.0 / Copernicus open | yes |
| GHSL GHS-BUILT-S 2020 (built share) | CC BY 4.0 (JRC) | yes |
| sat-io shoreline outlines (distance to coast) | per catalogue (assumed open) | confirm |
| Copernicus EMS products, Sentinel-1 (labels only) | CEMS terms; Copernicus open | validation only |

FABDEM (CC BY-NC-SA) and MERIT Hydro (CC BY-NC / ODbL) are used only in the `full` variants, which were not chosen.
