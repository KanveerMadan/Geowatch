# Rain test label: NYC FloodNet street sensors (round 3, pre-registered before the seal)

Owner decision, 2026-11-26.
- **Training and DEV:** 311 street-flooding reports, unchanged.
- **The rain type's held-out test:** FloodNet sensors. FloodNet is a test label only and is never used for training, tuning or method choice.
- **Why:** the 311 label cannot show 0.70 (DIAGNOSIS §l: split-half oracle ≈ 0.60). FloodNet measures water depth at fixed street points, so it gives both wet and dry, independent of who reports.

## What was seen before this was written
- **Sensor metadata** (NYC Open Data `kb2e-tjy3`): location, install date, tidal flag. This is not label data.
- **FloodNet event records** (`aq7i-eu5q`):
  - the dataset's first and last event dates and its row count;
  - the daily event counts before 2022 (DEV);
  - **one reserve-period record**, shown while the schema was inspected: sensor "Q - Beach 84 St (2)", 2026-11-09, max 1.18 in.
  - Rule 6 excludes that storm window. The sensor is also tidally influenced, which rule 3 excludes.
- No other reserve-period FloodNet event and no reserve-period 311 report has been read.

## Rules (fixed now)
1. **Storms (metadata only):**
   - A storm is a day whose IMERG centred 3-day mean over the NYC box (rain311 `CITIES["nyc"]["bbox"]`) is ≥ 25 mm, from 2022-01-01 to the seal date.
   - Overlapping windows are one storm, keeping the day with the largest 3-day sum.
   - Peak = that day. Window = [peak − 1 d, peak + 2 d) UTC, as the 311 labels use.
   - The storm list does not depend on 311 or FloodNet.
2. **Rain, not coastal:** the Battery tide gauge (8518750) stays below NOAA's minor-flood level in [peak − 1 d, peak + 1 d]. Otherwise the storm is refused (rain311's rule).
3. **Sensors:**
   - non-tidal only (`tidally_influenced` = "No");
   - active = installed at least 1 day before the window starts.
4. **Minimum sensors per storm:** ≥ 100 active non-tidal sensors at the window start (metadata). Fewer → the storm is refused before any label is read. In practice this admits storms from mid-2024 on.
5. **Labels (read only after the freeze), per sensor and storm:**
   - **wet** if FloodNet records an event with `flood_start_time` in the window and `max_depth_inches` ≥ 1.0;
   - **dry** if the sensor is active and records no event in the window;
   - an event below 1.0 in → neither wet nor dry (excluded).
6. **Excluded window:** any storm whose window contains 2026-11-09 (the one record seen above).
7. **Cell matching:**
   - each sensor maps to the 30 m cell containing its published latitude/longitude, on a city-wide NYC UTM 18N 30 m grid snapped like `utm_grid`;
   - two or more sensors in one cell: wet if all are wet, dry if all are dry, otherwise excluded;
   - all other cells are unobserved.
8. **Unit and the bar (unchanged):**
   - one storm = one unit, scored by the same scorer: within-unit AUC over the labelled sensor cells, 990 m blocked bootstrap, gain over the better of elevation and HAND;
   - a unit is usable only with ≥ 50 wet and ≥ 50 dry sensor cells, the bar's own floor;
   - each dropout is reported with its counts.
9. **Verdict:**
   - The rain verdict uses the usable FloodNet units. At least 5 are needed.
   - With fewer than 5, rain is reported as **not testable with FloodNet in round 3**. That is not a pass, and the reason is stated.
   - 311 reserve storms (all cities) are scored too and reported as a secondary result. They do not decide the verdict.
10. **Model scores at sensor cells:**
    - Scores come from the frozen rain method, using feature tables of 8 km lattice boxes (rain311 `lattice("nyc")`) that cover every sensor cell. Those boxes are built from metadata only.
    - A cell covered by several boxes takes the box whose centre is nearest.
11. **Flat-vs-hilly split (criteria §9):** applied per sensor cell's box and reported in addition.

## Known limits (stated in the pre-registration)
- **Sensors are not a random sample:** FloodNet places sensors at known flood-prone streets. That shifts the base rate. It does not bias the within-storm ranking towards any one method.
- **No uptime record:** the event dataset has no sensor-uptime record, so a broken sensor would read dry. This affects every method alike.
- **Coverage:** NYC only, mid-2024 onwards (rule 4).
