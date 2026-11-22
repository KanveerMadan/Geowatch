# GEDTM30 v1.2: declared scale factor does not match the stored values

**Status:** reproduced independently on 2026-10-31. **Not corrected.** No code in this repository reads GEDTM30, so nothing is affected today.

## The issue
The elevation COG (`gedtm_rf_m_30m_…_v1.2.tif`) and the std COG declare **scale 0.1, offset 0** in the GDAL band metadata. Header details: float32, EPSG:4326, nodata 3.4028e38, `VERTICAL_DATUM=EGM2008/EPSG:3855`, and no units tag.

## The stored values are already metres

Run 1 (exploratory, `geowatch-env`) compared raw values with FABDEM and GLO-30 medians:

| Box | GEDTM30 raw | FABDEM | GLO-30 |
|---|---|---|---|
| Hanoi | 14.0 | 12.4 | 15.4 |
| Valencia | 61.1 | 60.9 | 61.6 |

Run 2 (`reproduce_scale.py` → `reproduce_scale_result.json`) used the separate prototype environment (rasterio 1.5.1, its bundled GDAL) and 3×3 windows at benchmarks published independently of any DEM:

| Point | Published | Raw | Raw × header scale |
|---|---|---|---|
| Denver capitol "mile" step | 1,609.3 m | **1,613.8** | 161.4 |
| El Alto airport (LPB) | 4,061.5 m | **4,030.5** | 403.1 |
| Dead Sea shore, Ein Bokek | ≈ −430 m | −323.1 | −32.3 |

The Dead Sea point is a weak check: the window sits on the shore slope (std 26.6), not at the water line.

## Consequences
- A reader that honours GDAL scale metadata (e.g. `gdal_translate -unscale`, many GIS tools) would return heights **10× too small**.
- The std layer has the same issue: raw values of about 0.3–3 m are plausible as metres.
- Any ingest must pin units explicitly and record that the header was **overridden by decision**.
- The Zenodo and Codeberg documentation disagree on the scale (10, 1) and on nodata; that is consistent with this confusion.

## Proposed ledger entry (not added; for when or if GEDTM30 is adopted)
> **C82: GEDTM30 v1.2's declared GDAL scale (0.1) does not match its stored values (metres) [E].** Raw values match published benchmarks and two independent DEMs; applying the header scale gives heights 10× too small. Any ingest must pin units and must not honour the header scale silently.
