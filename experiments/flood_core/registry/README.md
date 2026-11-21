# Flood event registry (flood-core prototype)

`events.json` holds one row per observation unit: every event or site that any flood round (1–4) used, plus the three round-4b reserved events. It replaces name-only reuse checks. It is a prototype: no production harness reads it.

| File | What it does |
|---|---|
| `build_registry.py` | Writes `events.json` from the pinned round 2–4 result files (boxes, products) and a curated table (roles, storm/region clusters, exposure). Reserved events get an approximate town point, never a box. |
| `annotate_basins.py` | Adds HydroBASINS `MAIN_BAS`, `hybas_4` and `hybas_6` at each unit's centre point. It is a read-only Earth Engine polygon lookup; run it with `geowatch-env`. |
| `registry.py` | Loads and validates the registry, finds links, issues verdicts and builds alias groups. |
| `../tests/test_registry.py` | 7 tests. |

## Exposure ladder (highest level reached)
| Level | Meaning |
|---|---|
| 0 | unseen |
| 1 | facts or news read |
| 2 | product metadata read |
| 3 | reference geometry or counts computed |
| 4 | scored |
| 5 | used for tuning or method choice |
| 6 | post-hoc diagnostics viewed |

The round-4b events are at level 2 (`PREREGISTRATION_ROUND4B.md`).

## Rules
| Link | Severity |
|---|---|
| shared product id (not bare S1/JRC) | block |
| boxes intersect | block |
| reserved point within `PROXIMITY_KM` of a dev box | block |
| same storm cluster | block |
| same `MAIN_BAS` | needs a signed exception |
| same `hybas_<BASIN_LEVEL>` | needs a signed exception |
| same curated region | needs a signed exception |

A signed exception can clear exception-level links only, never a block.

**Two settings are judgements, not measured thresholds. Both are open for you to set:**
- `PROXIMITY_KM = 20`: the side of round 4's pre-registered S1 search square, the largest search extent any round used.
- `BASIN_LEVEL = 6`. At level 4, coastal inter-basin units are large. For example, Noakhali's level-4 unit `4040024190` also contains Kyaukpyu and Sittwe (Rakhine), which would add links that make no hydrological sense.

## State at build (2026-10-31)
- **46 units:** 43 dev, 3 reserved.
- **Alias groups** (block-level links):
  - {paiporta, valencia_2024}
  - {derna, derna_2023, volos}
  - {hai_phong, hanoi, nam_dinh, thai_binh}
  - {jakarta, jakarta_gfd_3280}
  - {chennai_velachery, chennai_2023}
  - {kyaukpyu, sittwe}
  - {belize_city, choloma}
- **Independent clusters** (counting any link): **29** among the 43 dev units. This, not 43, is the effective sample size for any interval.
- **Hidden basin links** found by HydroBASINS, not by names:
  - himachal_2023 and pakistan_2022 share the Indus `MAIN_BAS`;
  - bihar_2026, assam_2026, sylhet_2022 and dhaka share the GBM `MAIN_BAS`.
- **Reserved verdicts, recorded and not decided:**

| Event | Verdict | Why |
|---|---|---|
| `noakhali_2024` | needs signed exception | linked to dhaka, bihar_2026, assam_2026 and sylhet_2022 only through the curated `gbm_system` region. Its `MAIN_BAS` is the Feni coastal basin, not the GBM. |
| `calais_2023` | clear | no link found |
| `redon_2025` | clear | no link found |
