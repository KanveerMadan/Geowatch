# Item 21 measurement A — high-resolution imagery inventory

Generated from `imagery_inventory.json` (2026-09-25T05:46:11.949835Z). **Inventory only: no source is chosen here.**

- **Catalogues:** OpenAerialMap (bbox query), Maxar Open Data STAC (55 events scanned), and the source recorded in `05_BUILD_MANUAL.md` item 21 where it is in neither (Cape Town city imagery, Rio IPP mosaic).
- **High resolution** = ≤ 2 m (the sub-2 m criterion of the 2026-09-24 site-list check). Coarser catalogue entries are dropped and counted.
- **Time:** the catalogue's own acquisition start (→ end) in UTC. OpenAerialMap times that fall exactly on the hour are usually a date entered at local midnight (Lima 05:00Z = 00:00 local) and are flagged. Local solar time = UTC + longitude/15, for shadow geometry.
- **Sentinel-2 L2A:** `COPERNICUS/S2_SR_HARMONIZED` scenes with scene `CLOUDY_PIXEL_PERCENTAGE` < 20 at the centroid of the scene/site overlap, within ±30 / 60 / 90 days of the acquisition date, and the nearest such scene. Scene-level, not per-pixel.
- **Licence:** as the catalogue states it; the right-hand note is what that licence permits for digitising a derived label dataset.

## Cape Town — training

Search window [18.3, -34.2, 18.95, -33.7]. 3 candidate(s).

| Source | Scene | Acquisition (UTC) | Res. (m) | Licence | S2 clear ±30/60/90 d |
|---|---|---|---:|---|---|
| City of Cape Town image service | City of Cape Town aerial imagery, 'Aerial Imagery 2025Jan' | 2025-01 (month only, from the service name); **time not published** | ? | `same portal and terms as 2026Jan (not separately verified)` | 6 / 10 / 15; nearest 4 d |
| OpenAerialMap | Khayamandi Drone Imagery `6939920491e1cc75b4a05d2b` | 2025-12-01 11:00:00 UTC — *on the hour: date-only or approximate* | 0.0321 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 12 / 19 / 24; nearest 1 d |
| recorded (City of Cape Town) | City of Cape Town aerial imagery, 'Aerial Imagery 2026Jan' | 2026-01 (month only, as recorded); **time not published** | 0.05 | `City of Cape Town: 'no restrictions on the digital file for non-commercial purposes' (as recorded 2026-09-24; not re-verified 2026-09-25)` | 8 / 15 / 23; nearest 1 d |

## Lima — training

Search window [-77.2, -12.3, -76.7, -11.75]. 18 candidate(s).

| Source | Scene | Acquisition (UTC) | Res. (m) | Licence | S2 clear ±30/60/90 d |
|---|---|---|---:|---|---|
| OpenAerialMap | Cajamarquilla, Peru `59e62b8f3d6412ef72209f61` — **site list says exclude: no licence** | 2017-03-19 23:00:00 → 05:21:17 UTC — *on the hour: date-only or approximate* | 0.0775 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 1 / 1 / 1; nearest 7 d |
| OpenAerialMap | Pampa Pacta, Punta Hermosa, Peru `59e62b8f3d6412ef72209f5b` | 2017-03-19 23:00:00 → 11:16:00 UTC — *on the hour: date-only or approximate* | 0.0844 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 1 / 1 / 1; nearest 7 d |
| OpenAerialMap | Complejo Arqueológico Mateo Salado `59e62b943d6412ef7220a2eb` | 2017-05-21 05:00:00 → 04:59:59 UTC — *on the hour: date-only or approximate* | 0.0334 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 1 / 1 / 2; nearest 17 d |
| OpenAerialMap | school `5dae503f73c69f000530ee6c` | 2019-10-21 05:00:00 → 00:39:29 UTC — *on the hour: date-only or approximate* | 0.0727 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 1 / 1 / 2; nearest 7 d |
| OpenAerialMap | Santuario de las Vizcachas `5fa4dedd73fd1d000512b0d9` | 2019-12-19 05:00:00 → 06:00:00 UTC — *on the hour: date-only or approximate* | 0.0639 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 1 / 2 / 3; nearest 18 d |
| OpenAerialMap | Candelaria `601c75ae5ed94000077fc5ed` | 2019-12-19 15:30:00 → 16:00:00 UTC (≈ 10:22 local solar) | 0.0796 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 1 / 2 / 3; nearest 18 d |
| OpenAerialMap | Mangomarca 2 `5fbb5324fb6d580005a5672f` | 2020-02-16 05:00:00 → 06:00:00 UTC — *on the hour: date-only or approximate* | 0.053 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 1 / 4 / 7; nearest 24 d |
| OpenAerialMap | Mangomarca 1 `5fae0e941d7a180007e702d8` | 2020-02-16 05:00:00 → 06:00:00 UTC — *on the hour: date-only or approximate* | 0.0532 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 1 / 4 / 7; nearest 24 d |
| OpenAerialMap | Sector Guadalupe - Quebrada Quirio `66d43b4411a1ae0001f7b07d` | 2024-06-17 06:00:48 → 07:00:48 UTC (≈ 00:53 local solar) | 0.05 | `CC BY-SA 4.0` — derivatives allowed; attribution; derived labels must be released CC BY-SA | 12 / 21 / 27; nearest 1 d |
| OpenAerialMap | Hospital Víctor Larco Herrera - 22/6/2024 `66d40df911a1ae0001f7b076` | 2024-06-22 05:44:11 → 06:44:11 UTC (≈ 00:36 local solar) | 0.0547 | `CC BY-SA 4.0` — derivatives allowed; attribution; derived labels must be released CC BY-SA | 0 / 1 / 5; nearest 54 d |
| OpenAerialMap | Yanacoto `66b585f87f12df0001cdd080` | 2024-08-08 05:00:00 → 00:44:09 UTC — *on the hour: date-only or approximate* | 0.05 | `CC BY-SA 4.0` — derivatives allowed; attribution; derived labels must be released CC BY-SA | 11 / 18 / 26; nearest 1 d |
| OpenAerialMap | Posible sitio arqueológico Yanacocto `66bfa2f398a7740001cf3d6c` | 2024-08-16 05:00:00 → 16:41:01 UTC — *on the hour: date-only or approximate* | 0.05 | `CC BY-SA 4.0` — derivatives allowed; attribution; derived labels must be released CC BY-SA | 11 / 18 / 26; nearest 1 d |
| OpenAerialMap | RRD Caritas Peru `6a56980bef1a469dcf237ec8` | 2025-01-05 06:00:00 → 07:00:00 UTC — *on the hour: date-only or approximate* | 0.0363 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 1 / 2 / 9; nearest 9 d |
| OpenAerialMap | RRD Caritas Peru `6a569856ef1a469dcf237ff3` | 2025-01-05 06:00:00 → 07:00:00 UTC — *on the hour: date-only or approximate* | 0.0378 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 1 / 2 / 9; nearest 9 d |
| OpenAerialMap | UNI OSM+GRD `67dce2d9d1f1285c00fcb196` | 2025-03-17 18:33:49 → 19:33:49 UTC (≈ 13:26 local solar) | 0.0558 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 9 / 10 / 12; nearest 2 d |
| OpenAerialMap | Santa_Anita_-_Ate `686df2c05857d50b70e1fa3a` | 2025-07-08 05:00:00 → 04:32:47 UTC — *on the hour: date-only or approximate* | 0.0325 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 0 / 0 / 3; nearest 75 d |
| OpenAerialMap | Sencico_25_07_12 `687336e1bef211f37006156a` | 2025-07-08 05:00:00 → 04:35:31 UTC — *on the hour: date-only or approximate* | 0.0341 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 0 / 0 / 3; nearest 75 d |
| OpenAerialMap | Sencico_Thermal_25_07_12 `687342acbef211f370061c5a` | 2025-07-12 05:00:00 → 04:21:02 UTC — *on the hour: date-only or approximate* | 0.0464 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 0 / 0 / 2; nearest 79 d |

## Karachi — training

Search window [66.85, 24.75, 67.35, 25.1]. 6 candidate(s).

| Source | Scene | Acquisition (UTC) | Res. (m) | Licence | S2 clear ±30/60/90 d |
|---|---|---|---:|---|---|
| Maxar Open Data · pakistan-flooding22 | Pakistan Flooding `1040010073509D00` (sun el. 59.6°, off-nadir 20.0°) | 2022-03-26 06:12:36 → 06:12:41 UTC (≈ 10:41 local solar) | 0.34 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 22 / 42 / 53; nearest 1 d |
| Maxar Open Data · pakistan-flooding22 | Pakistan Flooding `10300100CFA70700` (sun el. 62.7°, off-nadir 21.9°) | 2022-03-29 06:26:20 → 06:26:24 UTC (≈ 10:54 local solar) | 0.53 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 23 / 41 / 55; nearest 0 d |
| Maxar Open Data · pakistan-flooding22 | Pakistan Flooding `10300100D13F6500` (sun el. 62.6°, off-nadir 27.0°) | 2022-03-29 06:26:33 → 06:26:37 UTC (≈ 10:54 local solar) | 0.57 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 23 / 44 / 58; nearest 0 d |
| Maxar Open Data · pakistan-flooding22 | Pakistan Flooding `10300100D5339F00` (sun el. 73.4°, off-nadir 27.0°) | 2022-06-24 06:22:17 → 06:22:20 UTC (≈ 10:50 local solar) | 0.57 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 3 / 8 / 15; nearest 1 d |
| Maxar Open Data · pakistan-flooding22 | Pakistan Flooding `10300100D404DA00` (sun el. 73.6°, off-nadir 30.8°) | 2022-06-24 06:22:29 → 06:22:32 UTC (≈ 10:50 local solar) | 0.61 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 8 / 19 / 34; nearest 1 d |
| Maxar Open Data · pakistan-flooding22 | Pakistan Flooding `105001002DCAC300` (sun el. 66.7°, off-nadir 27.1°) | 2022-08-11 06:06:41 → 06:06:43 UTC (≈ 10:35 local solar) | 0.5 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 2 / 6 / 15; nearest 23 d |

## Monrovia — training

Search window [-10.85, 6.23, -10.7, 6.37]. 27 candidate(s).

| Source | Scene | Acquisition (UTC) | Res. (m) | Licence | S2 clear ±30/60/90 d |
|---|---|---|---:|---|---|
| OpenAerialMap | Monrovia FT03 Ortho `5b75f9366175253ca55dac59` | 2018-08-16 10:00:00 → 11:00:00 UTC — *on the hour: date-only or approximate* | 0.05 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 0 / 0 / 0; none within 90 d |
| OpenAerialMap | Monrovia Doe 20180821 `5b83a621c8e197000a934041` | 2018-08-21 10:00:00 → 11:00:00 UTC — *on the hour: date-only or approximate* | 0.042 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 0 / 0 / 0; none within 90 d |
| OpenAerialMap | Monrovia Clara 20180822 `5b8182287343a98c3f347d1c` | 2018-08-22 10:00:00 → 11:00:00 UTC — *on the hour: date-only or approximate* | 0.04 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 0 / 0 / 0; none within 90 d |
| OpenAerialMap | OCA Monrovia - River View Community `5bcdcf3ab9e5f20005f7da40` | 2018-10-05 08:00:00 → 10:00:00 UTC — *on the hour: date-only or approximate* | 0.0566 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 0 / 0 / 4; nearest 71 d |
| OpenAerialMap | OCA Monrovia - Hope Community `5c08c36c6918390006b7a8a3` | 2018-11-21 11:00:00 → 14:00:00 UTC — *on the hour: date-only or approximate* | 0.0574 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 2 / 5 / 7; nearest 24 d |
| OpenAerialMap | Duala Market `5dee77e79c3b1700059a3593` | 2019-10-02 11:00:00 → 14:00:00 UTC — *on the hour: date-only or approximate* | 0.0499 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 0 / 1 / 4; nearest 54 d |
| OpenAerialMap | Monrovia Red Light Market `5e0ef7c515d478000501ea61` | 2019-12-09 21:00:00 → 22:00:00 UTC — *on the hour: date-only or approximate* | 0.05 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 8 / 14 / 17; nearest 1 d |
| OpenAerialMap | Monrovia gapfill 2 `65c4f27d499b4d000186ee77` | 2020-01-19 21:00:00 UTC — *on the hour: date-only or approximate* | 0.0506 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 13 / 19 / 20; nearest 0 d |
| OpenAerialMap | Monrovia gapfill 2 `65c4f013499b4d000186ee73` | 2020-01-19 21:00:00 UTC — *on the hour: date-only or approximate* | 0.0509 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 13 / 19 / 20; nearest 0 d |
| OpenAerialMap | Monrovia gapfill 2 `65c4f779499b4d000186ee78` | 2020-01-19 21:00:00 UTC — *on the hour: date-only or approximate* | 0.051 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 13 / 17 / 18; nearest 0 d |
| OpenAerialMap | Monrovia gapfill 2 `65c4f013499b4d000186ee74` | 2020-01-19 21:00:00 UTC — *on the hour: date-only or approximate* | 0.0513 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 13 / 19 / 20; nearest 0 d |
| OpenAerialMap | Monrovia gapfill 2 `65c4f03f499b4d000186ee75` | 2020-01-19 21:00:00 UTC — *on the hour: date-only or approximate* | 0.0516 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 13 / 19 / 20; nearest 0 d |
| OpenAerialMap | Monrovia gapfill 2 `65c4f080499b4d000186ee76` | 2020-01-19 21:00:00 UTC — *on the hour: date-only or approximate* | 0.0531 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 13 / 19 / 20; nearest 0 d |
| OpenAerialMap | Central Monrovia Orthomosaic `63247b059ee90900078a70ff` | 2020-01-24 08:00:00 → 15:00:00 UTC — *on the hour: date-only or approximate* | 0.05 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 12 / 19 / 20; nearest 0 d |
| OpenAerialMap | Central Monrovia 1 `5e53faa7906c590005ecc5bb` | 2020-02-23 21:00:00 → 15:53:46 UTC — *on the hour: date-only or approximate* | 0.05 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 8 / 14 / 16; nearest 5 d |
| OpenAerialMap | Monrovia Pt 4 of 4 `5e6a8cdb5abd57000732847c` | 2020-02-23 21:00:00 → 15:53:46 UTC — *on the hour: date-only or approximate* | 0.0504 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 8 / 14 / 16; nearest 5 d |
| OpenAerialMap | Monrovia Pt 3 of 4 `5e679949e82eb700055028ca` | 2020-02-23 21:00:00 → 15:53:46 UTC — *on the hour: date-only or approximate* | 0.0507 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 8 / 14 / 16; nearest 5 d |
| OpenAerialMap | Central Monrovia 2 `5e55b345642d040007b7c573` | 2020-02-23 21:00:00 → 15:53:46 UTC — *on the hour: date-only or approximate* | 0.0508 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 8 / 15 / 20; nearest 5 d |
| OpenAerialMap | Central Monrovia 2 `5e557ce2642d040007b7c56f` | 2020-02-23 21:00:00 → 15:53:46 UTC — *on the hour: date-only or approximate* | 0.0508 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 8 / 15 / 20; nearest 5 d |
| OpenAerialMap | Monrovia Pt 1 of 4 `5e6941c0ce171e0005d341f3` | 2020-02-23 21:00:00 → 15:53:46 UTC — *on the hour: date-only or approximate* | 0.051 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 8 / 15 / 20; nearest 5 d |
| OpenAerialMap | Central Monrovia 2 `5e71be79ccc61e00059aedcc` | 2020-02-23 21:00:00 → 15:53:46 UTC — *on the hour: date-only or approximate* | 0.0526 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 8 / 15 / 20; nearest 5 d |
| OpenAerialMap | Block1_1 `5ec65321e3882d00079e72c1` | 2020-05-20 21:00:00 → 09:52:09 UTC — *on the hour: date-only or approximate* | 0.256 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 0 / 1 / 4; nearest 37 d |
| OpenAerialMap | Monrovia gapfill `65c4dcd4ed310f0001613075` | 2021-05-31 21:00:00 → 22:00:00 UTC — *on the hour: date-only or approximate* | 0.05 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 1 / 2 / 4; nearest 17 d |
| OpenAerialMap | Monrovia `64d4eaba19cb3a000147a604` | 2023-08-09 22:00:00 → 09:54:23 UTC — *on the hour: date-only or approximate* | 0.051 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 1 / 1 / 1; nearest 3 d |
| OpenAerialMap | 2024-02-29_New_Kru_Town_Monrovia_Mavic_flights_1-5 `65e4bdfce6f8d4000128235d` | 2024-02-27 14:00:00 → 17:00:00 UTC — *on the hour: date-only or approximate* | 0.0498 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 4 / 8 / 12; nearest 15 d |
| OpenAerialMap | Fahnbulleh Neighborhood-1 `6844c95e71853678801bd3d5` | 2024-12-02 10:41:07 → 11:41:07 UTC (≈ 09:58 local solar) | 0.0839 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 5 / 9 / 13; nearest 4 d |
| OpenAerialMap | Fahnbulleh Neighborhood-2 `6844c99071853678801bd3e2` | 2024-12-04 11:38:33 → 12:38:33 UTC (≈ 10:55 local solar) | 0.08 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 6 / 9 / 14; nearest 6 d |

## Marrakech — training

Search window [-8.1, 31.55, -7.9, 31.7]. 28 candidate(s); 2 coarser than 2 m dropped.

| Source | Scene | Acquisition (UTC) | Res. (m) | Licence | S2 clear ±30/60/90 d |
|---|---|---|---:|---|---|
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `1040010006B2B200` (sun el. 32.4°, off-nadir 9.3°) | 2015-01-08 11:12:13 → 11:12:31 UTC (≈ 10:40 local solar) | 0.31 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 0 / 0 / 0; none within 90 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `8c061358-66fa-497f-971e-ff8781108894-inv` (sun el. 63.8°, off-nadir 19.5°) | 2018-09-01 11:40:54 → 11:40:59 UTC (≈ 11:08 local solar) | 0.34 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 11 / 20 / 28; nearest 2 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `1040010049981000` (sun el. 47.6°, off-nadir 28.6°) | 2019-02-27 11:44:15 → 11:44:18 UTC (≈ 11:12 local solar) | 0.39 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 8 / 16 / 27; nearest 1 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `104001004ACFF200` (sun el. 69.5°, off-nadir 21.7°) | 2019-04-25 11:50:13 → 11:50:16 UTC (≈ 11:18 local solar) | 0.35 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 8 / 18 / 27; nearest 2 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `104001004E78C700` (sun el. 76.2°, off-nadir 28.1°) | 2019-07-03 11:47:47 → 11:47:51 UTC (≈ 11:15 local solar) | 0.38 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 11 / 22 / 32; nearest 2 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `104001004D86FB00` (sun el. 71.8°, off-nadir 9.3°) | 2019-07-21 11:33:35 → 11:33:48 UTC (≈ 11:01 local solar) | 0.32 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 12 / 23 / 33; nearest 0 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `104001005FC0C600` (sun el. 65.7°, off-nadir 26.9°) | 2020-08-22 11:34:58 → 11:35:02 UTC (≈ 11:02 local solar) | 0.38 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 12 / 24 / 33; nearest 2 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `10300100B33D1000` (sun el. 36.0°, off-nadir 10.2°) | 2021-01-27 11:17:50 → 11:17:53 UTC (≈ 10:45 local solar) | 0.48 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 9 / 19 / 27; nearest 1 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `10300100B53F9800` (sun el. 44.2°, off-nadir 15.9°) | 2021-02-23 11:22:14 → 11:22:17 UTC (≈ 10:50 local solar) | 0.5 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 10 / 16 / 27; nearest 2 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `104001006800CE00` (sun el. 67.2°, off-nadir 10.8°) | 2021-05-02 11:17:03 → 11:17:16 UTC (≈ 10:45 local solar) | 0.32 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 8 / 17 / 27; nearest 1 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `104001006975B600` (sun el. 67.1°, off-nadir 15.1°) | 2021-05-02 11:17:24 → 11:17:37 UTC (≈ 10:45 local solar) | 0.33 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 7 / 16 / 26; nearest 4 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `1040050039DC5C00` (sun el. 50.3°, off-nadir 28.9°) | 2021-10-07 11:20:41 → 11:20:45 UTC (≈ 10:48 local solar) | 0.39 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 10 / 21 / 29; nearest 1 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `10300500C2F93F00` (sun el. 37.8°, off-nadir 12.4°) | 2021-11-16 11:20:18 → 11:20:21 UTC (≈ 10:48 local solar) | 0.48 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 10 / 19 / 27; nearest 1 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `1040050046DBE400` (sun el. 67.8°, off-nadir 7.5°) | 2022-07-31 11:19:31 → 11:19:36 UTC (≈ 10:47 local solar) | 0.31 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 9 / 18 / 28; nearest 1 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `104005004ADBF200` (sun el. 49.8°, off-nadir 12.5°) | 2022-10-08 11:19:07 → 11:19:12 UTC (≈ 10:47 local solar) | 0.32 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 9 / 17 / 27; nearest 0 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `104001007D498500` (sun el. 43.7°, off-nadir 6.7°) | 2022-10-27 11:19:17 → 11:19:18 UTC (≈ 10:47 local solar) | 0.31 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 9 / 16 / 26; nearest 1 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `105001002FC38300` (sun el. 41.4°, off-nadir 21.4°) | 2022-11-05 11:27:18 → 11:27:20 UTC (≈ 10:55 local solar) | 0.46 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 8 / 17 / 25; nearest 2 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `10300100DF7ADD00` (sun el. 36.3°, off-nadir 12.5°) | 2023-01-24 11:31:43 → 11:31:46 UTC (≈ 10:59 local solar) | 0.49 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 8 / 14 / 25; nearest 2 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `1050010031762F00` (sun el. 38.8°, off-nadir 14.1°) | 2023-02-06 11:22:19 → 11:22:26 UTC (≈ 10:50 local solar) | 0.43 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 6 / 16 / 26; nearest 1 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `1040010084646C00` (sun el. 55.8°, off-nadir 7.5°) | 2023-03-28 11:17:45 → 11:17:50 UTC (≈ 10:45 local solar) | 0.31 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 10 / 15 / 25; nearest 1 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `1040010084B2E200` (sun el. 55.8°, off-nadir 8.0°) | 2023-03-28 11:17:58 → 11:18:03 UTC (≈ 10:45 local solar) | 0.31 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 10 / 15 / 25; nearest 1 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `10400100846B5A00` (sun el. 64.7°, off-nadir 24.1°) | 2023-04-28 11:09:06 → 11:09:09 UTC (≈ 10:37 local solar) | 0.36 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 9 / 18 / 26; nearest 2 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `10300100EBC1A000` (sun el. 68.1°, off-nadir 25.1°) | 2023-08-06 11:26:38 → 11:26:40 UTC (≈ 10:54 local solar) | 0.55 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 11 / 21 / 27; nearest 2 d |
| OpenAerialMap | MAXAR 10300100EBC1A000 Morocco `64fcf1d3649d390001c474e5` | 2023-08-06 15:26:00 → 16:26:00 UTC (≈ 14:54 local solar) | 0.305 | `CC BY-NC 4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 11 / 21 / 27; nearest 2 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `10300100EB8B4500` (sun el. 62.6°, off-nadir 14.9°) | 2023-08-28 11:20:57 → 11:20:58 UTC (≈ 10:48 local solar) | 0.49 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 10 / 20 / 29; nearest 1 d |
| OpenAerialMap | Marrakesh Morocco Earthquake Maxar pre-event 10300100EB8B4500 `64fca589649d390001c474d7` | 2023-08-28 04:00:00 → 05:00:00 UTC — *on the hour: date-only or approximate* | 0.305 | `CC BY-NC 4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 10 / 20 / 29; nearest 1 d |
| Maxar Open Data · Morocco-Earthquake-Sept-2023 | Morocco Earthquake `1040050057DC8500` (sun el. 59.5°, off-nadir 22.4°) | 2023-09-10 11:25:14 → 11:25:17 UTC (≈ 10:53 local solar) | 0.35 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 10 / 19 / 28; nearest 2 d |
| OpenAerialMap | Maxar 1040050057DC8500 Morocco Marrakesh `64febc27649d390001c47518` | 2023-09-10 08:00:00 → 08:30:00 UTC — *on the hour: date-only or approximate* | 0.305 | `CC BY-NC 4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 10 / 19 / 28; nearest 2 d |

## Makoko — validation

Search window [3.37, 6.47, 3.42, 6.52]. 3 candidate(s).

| Source | Scene | Acquisition (UTC) | Res. (m) | Licence | S2 clear ±30/60/90 d |
|---|---|---|---:|---|---|
| OpenAerialMap | Maxar 2019 Lagos Mosaic `5ea1cb44411bed00056803b8` | 2019-06-05 23:00:00 → 00:00:00 UTC — *on the hour: date-only or approximate* | 0.5 | `CC BY-NC 4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 0 / 0 / 0; none within 90 d |
| OpenAerialMap | Makoko `5dd0f6dda7dadc0006433b5b` | 2019-10-02 11:00:00 → 14:00:00 UTC — *on the hour: date-only or approximate* | 0.054 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 0 / 2 / 4; nearest 51 d |
| OpenAerialMap | Task of 2019-10-08T08:14:21.855Z `5dd0f370a7dadc0006433b56` | 2019-10-02 16:28:19 → 17:28:19 UTC (≈ 16:41 local solar) | 0.0638 | `CC-BY 4.0` — derivatives allowed, incl. commercial; attribution required | 0 / 2 / 4; nearest 51 d |

## Kibera — validation

Search window [36.76, -1.33, 36.81, -1.29]. 5 candidate(s).

| Source | Scene | Acquisition (UTC) | Res. (m) | Licence | S2 clear ±30/60/90 d |
|---|---|---|---:|---|---|
| OpenAerialMap | Maxar 2019 Nairobi Mosaic `5ea29a2e411bed00056803c9` | 2019-05-14 23:00:00 → 00:00:00 UTC — *on the hour: date-only or approximate* | 0.3 | `CC BY-NC 4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 0 / 3 / 7; nearest 45 d |
| Maxar Open Data · Kenya-Flooding-May24 | Kenya Flooding `104001008E063C00` (sun el. 61.8°, off-nadir 10.6°) | 2023-11-30 08:00:58 → 08:01:02 UTC (≈ 10:28 local solar) | 0.32 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution; **acquisition collection says `proprietary`** | 2 / 4 / 9; nearest 1 d |
| OpenAerialMap | Kenya Flooding May 2024 (pre-event) `663d16016049ef00013b84b8` | 2023-11-30 13:00:00 → 13:01:00 UTC — *on the hour: date-only or approximate* | 0.305 | `CC BY-NC 4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 2 / 4 / 9; nearest 1 d |
| Maxar Open Data · Kenya-Flooding-May24 | Kenya Flooding `105001003B003900` (sun el. 55.7°, off-nadir 40.3°) | 2024-05-11 07:33:59 → 07:34:02 UTC (≈ 10:01 local solar) | 0.68 | `CC-BY-NC-4.0` — derivatives allowed, NON-COMMERCIAL only; attribution; **acquisition collection says `proprietary`** | 3 / 6 / 12; nearest 16 d |
| OpenAerialMap | Kenya Flooding May 2024 Maxar 105001003B003900 (post-event) `6642a8a66049ef00013b85d7` | 2024-05-11 11:34:00 → 12:34:00 UTC (≈ 14:01 local solar) | 0.305 | `CC BY-NC 4.0` — derivatives allowed, NON-COMMERCIAL only; attribution | 3 / 6 / 12; nearest 16 d |

## Rocinha — validation

Search window [-43.262, -22.995, -43.238, -22.978]. 1 candidate(s).

| Source | Scene | Acquisition (UTC) | Res. (m) | Licence | S2 clear ±30/60/90 d |
|---|---|---|---:|---|---|
| recorded (Rio IPP) | IPP city true-orthophoto mosaic, Imagens/Mosaico_2024 | first half of 2024 (as recorded); **time not published** | 0.15 | `IPP: non-commercial; commercial use needs IPP's prior written authorisation (as recorded 2026-09-24)` | 3 / 8 / 15; nearest 21 d |
