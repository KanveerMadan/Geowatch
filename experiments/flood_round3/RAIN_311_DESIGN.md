# Rain (urban) labels from city 311 street-flooding reports: design, written before any report location is read

**Status: DRAFT.** It becomes a decision (DECISIONS R-entry) and a section of RESERVE_CRITERIA_R3 once the city list is fixed. Nothing below has been applied to any event.

## Why
- Round 2's rain labels were Sentinel-1 / optical images taken a median 4 d after the rain, and noise at that (DIAGNOSIS §b, §e).
- R19 allows rain labels at most 1 d after the peak. Satellites almost never manage that through cloud and over buildings.
- City 311 reports are the opposite:
  - each one is timestamped to the minute;
  - each is located at an address;
  - each is made during or just after the flooding, exactly where people saw surface water.
- **Count check (metadata only, NYC; first done with SC included, before this rule):** 630 "Street Flooding (SJ)" reports on 2023-09-29/30, against 5 on a dry day. The same window holds ~19,000 reports of other kinds.

## Label rules (same for every method)
1. **Window:** [rain start, IMERG 3-day peak + 24 h], for R19's 1-day lag.
2. **FLOODED:** 30 m cells holding ≥ 1 report in the window whose descriptor is surface flooding:
   - NYC: `Street Flooding (SJ)`, `Highway Flooding (SH)`;
   - other cities: their nearest equivalents, listed per city before use.
   - **Ambiguous, so neither flooded nor dry:**
     - `Catch Basin Clogged/Flooding (SC)` mixes "clogged" and "flooding";
     - sewer backup, manhole overflow and water in basement are driven by the sewer network, not by surface water.
3. **DRY (reporting-propensity control):** cells holding ≥ 1 report of any kind other than flood or ambiguous in the same window, with no flood report within 90 m (3 cells).
   - This compares flooded places with places where people were out reporting other problems during the same storm.
   - So the AUC does not reward a score for simply tracking where people report.
4. **Unobserved:** everything else. Permanent water (JRC ≥ 80 %) is its own state, as in v3.
5. **Location:** the report's geocoded latitude/longitude. Reports without coordinates are dropped and counted.

## Units and events
- **Unit:** an 8 km box (R25), centred on the 8 km window with the most flood reports (the analogue of `place()`'s flood centre). It is placed at build time.
  - A second box per event is allowed if it does not overlap the first and holds ≥ 50 flood reports.
  - Units of one storm form one cluster.
- **Event (metadata only):** consecutive days with ≥ 50 surface-flood (SJ + SH) reports city-wide each. That count plays the role of EMS's reported affected area (§4). Its driver checks (§2), from metadata:
  - IMERG 3-day ≥ 20 mm over the city;
  - **not coastal:** the NOAA tide gauge (NYC: The Battery, 8518750) stays below NOAA's minor-flood threshold in the window. Otherwise the event is typed coastal or compound (with rain ≥ 50 mm) and joins those types under the same label rules.
- **Never used:** no unit in any round is inside these cities (checked against all 169 burned units).
- **DEV / reserve split, fixed now:**
  - events before 2022-01-01 are DEV (free for development);
  - events on or after 2022-01-01 are the round-3 reserve, sealed with the rest before any Phase 4 model.

## Candidate cities (open 311 APIs; licences to be listed in LICENCES.md before use)
New York (NYC Open Data, Socrata `erm2-nwe9`), plus cities still to check: Chicago, Philadelphia, Washington DC, Baltimore, Boston, Toronto, San Francisco, Houston, Detroit.

## Known limits (to be stated in the pre-registration)
- These are case-control labels on report locations, not a complete flood map. A cell with no report is unobserved, not dry.
- Reports sit on streets and addresses, so this tests where surface water collects along the street network. That is exactly the rain product's claim.
- City coverage is North American. This is reported, not hidden.
