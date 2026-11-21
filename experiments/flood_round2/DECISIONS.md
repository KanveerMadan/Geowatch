# flood_round2: decisions

Judgement calls, numbered R1, R2, and so on. Round-1 decisions are D1–D23 in `experiments/flood_final/DECISIONS.md`.

## R1 (2026-11-21) The secrets scan blocks through explicit gates, not repo-wide git hooks
- `tools/secrets_scan.py` exits 1 on a finding. Every commit runs `secrets_scan.py --staged && git commit`, and every push goes through `tools/safe_push.sh`, which scans the unpushed range and pushes only if it is clean.
- It is not installed as a pre-commit/pre-push hook. Hooks live in the shared `.git` directory and would change behaviour in every worktree of the repo (~/geowatch, ~/gw-product, …), and touching other worktrees is a hard stop.
- The owner can install it in one line, e.g. `.git/hooks/pre-push` calling `tools/safe_push.sh`'s scan step.

## R2 (2026-11-21) Local paths: removed only from files Claude sessions created
- Fixed:
  - `experiments/flood_core/screening/catchments.py` now reads .env relative to the repo;
  - `experiments/ward_ranking/result_2026-10-28.json` now has `<repo>/` in one description string. Not pinned by any hash.
- Left as they are: `archive/AUDIT_FINDINGS.md` and `push_water_annotations_to_drive.py`. They are human-authored, and overwriting files I did not create is a hard stop. The scan blocks new paths from now on, which is what "going forward" asks.

## R3 (2026-11-21) EMSR683 fetch bug (Phase B)
- Cause: `flood_learned.fetch._mosaic` called `Image.projection()` on a whole GLO-30 tile. Above 60° latitude the tile's bands have different projections, so EE raises "bands … contain different projections".
- Fix: take the projection of the selected band. On r_emsr683_aoi01 the margin stack now builds, with elevation 355–1,516 m.
- On a DEV control unit (emsr757_aoi02) the DEM is identical to the cached training DEM (max diff 0.0), so the validated features do not change.
- Production imports this function, so the fix is cherry-picked to build/flood-learned (PR #1).
- Regression test: `tests/test_learned_flood.py::test_mosaic_takes_the_selected_bands_projection`. It fails on the old code and passes on the new.

## R4 (2026-11-21) Fort Myers reference: Sentinel-1 box labels; USGS high-water marks unavailable
- USGS STN high-water marks would be the urban-capable reference for Ian (surveyed water levels among buildings).
- The STN web services (stn.wim.usgs.gov/STNServices, incl. Events/325/HWMs.json) answer 301 to the STN web app, and no replacement API is documented. A SFWMD flood-documentation feature service did not return JSON either.
- So Phase C scores against the DEV unit's existing S1 VV-drop labels (4 km box). They are blind among buildings (D20), and Fort Myers Beach is mostly built-up. That limit is stated in the results. If the owner knows the current STN endpoint, HWMs can be added later as a second reference.

## R5 (2026-11-21) Fort Myers SFINCS set-up choices
- **Sea floor.** 3DEP has no bathymetry (water surfaces are flattened near 0 m), so cells with JRC occurrence ≥ 80 % are lowered to at most −1.5 m.
  - Basis: Estero Bay and the nearshore Gulf are mostly 1–3 m deep (NOAA chart 11426).
  - Surge propagation is not sensitive to depth at this scale once the cells are wet. This is stated as an assumption, not measured.
- **GLO-30 offset.** Median(3DEP − GLO-30) over dry land is −1.54 m. That is mostly GLO-30 being a surface model (trees, buildings) plus the EGM2008/NAVD88 difference. The glo30 member is shifted by it, so it is "GLO-30, bias-corrected to 3DEP", not a pure datum fix.
- **Boundary forcing.** NOAA 8725520 Fort Myers (NAVD88, metres; peak 2.26 m hourly mean, residual peak 2.18 m).
  - The gauge sits ~10 km up the Caloosahatchee from the open coast, so it likely understates the open-coast peak.
  - Member `surge2x` doubles the residual as an upper bracket. That is a sensitivity, not a calibration.
  - The Naples gauge stopped at its peak and is not used.
- **Members:** base (3DEP), surge2x, glo30, lidar_e1 (3DEP + spatially correlated noise, σ 0.10 m, the 3DEP QL2 RMSEz).

## R6 (2026-11-21) flood_final's reserved units become DEV
- The 47 flood_final reserved units were scored once (2026-11-20), and the results are public. They are now role `dev`, exposure 6.
- Where a reference was built, their geometry is that reference box, so box and proximity rules see them.
- They add DEV units for the weakest types: of the 34 that qualified, 13 coastal, 6 flash, 5 compound and 4 pluvial.
- Round-1 guard tests are updated to this state (`experiments/flood_final/test_final.py`):
  - block links are still never allowed;
  - an exception link is allowed only where R7 accepted it.

## R7 (2026-11-21) Main-basin-only links accepted for reserved units, by a fixed rule
- Of the 53 reserved candidates, the guard dropped 19 at first. Most were dropped only for being in the same continental "main basin" as a DEV unit (Danube, Rhine, Ganges-Brahmaputra), hundreds of km and years apart.
- Rule (`events_round2.MAIN_BASIN_MIN_KM = 100`): a reserved unit is kept only if every one of its links is `main_basin`, each to a unit of another storm cluster more than 100 km away.
  - Any sub-basin, box, proximity, alias or storm link still drops it.
  - Basis: such units share no water, storm, reference or box with the test.
  - 100 km is 5x the registry's proximity radius (20 km), far beyond the 4 km boxes plus their 2 km margins.
- Accepted under R7: EMSR728 AOI01 and AOI03, EMSR722 AOI01 and AOI02, EMSR927 AOI01 and AOI02, EMSR802 AOI01 and AOI02 (listed in `registry_units_round2.json`).
- Still dropped: EMSR866 AOI01 (proximity), EMSR854 AOI02 (sub-basin), EMSR797 AOI01 and AOI02 (a main-basin link within 100 km), EMSR794 (sub-basin), EMSR772 and s1_ndjamena_2024 (proximity to EMSR779), EMSR789 (sub-basin).

## R8 (2026-11-21) Round-2 reserved set (42 units, metadata only) and its weak spots
- **By tag:** fluvial 20, flash 9, coastal 5, compound 5, waterlogging 4, pluvial 3. Extra tags: snowmelt 3, glof 2, dam_breach 2.
- **Coastal and compound** are Sentinel-1 cyclone cases (Helene, Remal, Biparjoy, Francine, Dana). Copernicus EMS has no unused coastal-surge activation. S1 images can be a day or more after the surge peak, so some boxes may not qualify. That is decided once, at scoring.
- **Pluvial** has only 3 units (EMSR721 Milan; Jeddah 2022 and Kinshasa 2022 by S1). The two S1 cases are urban, where S1 sees little (D20), so pluvial may end "not-run (insufficient)". The urban reference work (Phase F) is the planned fix and is not available yet.
- **Waterlogging:** 4 units (Jowhar, Ubon, Garsen, Sukhothai), all S1.
- Points and dates for S1 events come from general reporting only. No image, reference, input or score of any reserved unit has been read.

## R9 (2026-11-21) Round-2 DEV additions
- References were built for the DEV EMS activations (storm-linked to used units) and the 5 S1 coastal cases.
- s1_michael_mexicobeach_2018 has no reference: no Sentinel-1 scene over the point in the window ("LookupError: S1 over …"). It is skipped.
- Registration drops a DEV unit with ANY link to a reserved unit, main-basin links included. That is stricter than R7 on purpose, since it only protects the reserved set.
  - 14 of 23 were kept (fluvial 8, coastal 5 = Ida, Laura, Amphan, Fani + one flipped, compound 2, flash 1).
  - Dropped: EMSR764 x3, EMSR759 x2 and EMSR665 x2 (main basin with reserved EMSR728 / EMSR802); EMSR705 AOI06 and AOI08 (proximity to reserved EMSR795).

## R10 (2026-11-21) Compound SFINCS case: Hurricane Ida at Lafitte (DEV)
- It needed open data, DEV status and rain + surge together. Ida is a DEV unit (s1_ida_lafitte_2021): Gulf surge through Barataria Bay plus about 146 mm of IMERG rain over the domain. Helene, which would also fit, is reserved and so excluded from SFINCS set-up.
- It uses the same code and settings as Fort Myers; only the case constants differ (domain 661 km², UTM 15N).
- **Boundary:** NOAA 8761724 Grand Isle, the open-Gulf gauge south of Lafitte, in local MSL. CO-OPS publishes no NAVD88 offset for it, and 3DEP is NAVD88.
  - base assumes MSL ≈ NAVD88;
  - member datum03 adds +0.3 m, as an assumption bracket for SE Louisiana subsidence;
  - surge2x doubles the residual.
- **Reference limit:** the S1 reference's first post-event pass is 11 days after landfall (2021-09-10). It shows residual ponding inside the levees, not the surge extent, so the AUC here tests "where water stayed".
- No river inflow boundary is added. The Mississippi is leveed and outside the domain, and Barataria's bayous are inside the grid.

## R11 (2026-11-21, owner's instruction) More reserved rain and waterlogging units
- The owner judged 3 rain and 4 waterlogging reserved units too few to prove anything and asked for ≥ 8 each: regions never used, chosen from metadata only, same guard, in a separate registry commit before the pre-registration is pushed.
- 21 Sentinel-1 units were added from general reporting (a town point and a date); no image was read.
  - **Rain / urban rain (14):** Seoul 2022, Bengaluru 2022, Hyderabad 2020, Durban 2022, Nairobi 2024, Fort Lauderdale 2023, Auckland 2023, Klang Valley 2021, Manila 2024, Antananarivo 2022, Recife 2022, Abidjan 2018, Port-au-Prince 2023, Lagos 2021.
  - **Waterlogging (7):** Bentiu 2022, Budalangi 2020, Battambang 2020, Ayutthaya 2021, Khuzestan 2019, Kebbi 2020, Mopti 2024.
- Excluded on purpose: storms already used (Ida 2021, the Pakistan 2022 monsoon, Idai 2019, Henan July 2021 = the Weihui urban test) and cities already in the registry.
- **Guard:** all 21 kept. Four were accepted under R7 (main basin only, other storm, > 100 km): Bentiu and Budalangi (Nile: Kigali, EMSR662), Kebbi and Mopti (Niger: Lokoja).
- **Totals:** rain 17 units in 17 clusters; waterlogging 11 in 11.
- **Risk:** Sentinel-1 sees little among buildings (D20), so many urban-rain units may not reach 50 flooded cells. Whether a unit qualifies is decided once, at scoring. The pre-registration therefore raises the minimum for a verdict (R12).
