# flood_round3: status

Branch `exp/flood-round3` (from `07e9920`, round 2's result), worktree gw-floodproto. Read this first on any restart, and never redo a phase marked done. Judgement calls go in DECISIONS.md (R18 onwards).

## Credentials and data access (checked 2026-11-22; the files are never printed, logged or committed)
| service | state | what it unlocks |
|---|---|---|
| CDS (`~/.cdsapirc`, cdsapi 0.7.7) | key works; ERA5-Land downloads; ERA5 licence accepted by the owner | ERA5 / ERA5-Land soil moisture and rain; GTSM surge (request format still to check) |
| EWDS (same key) | **CEMS Early Warning Data Store terms not accepted**: GloFAS returns 403 | GloFAS discharge. **The owner can accept the terms at https://ewds.climate.copernicus.eu/licences/terms-of-use-cems.** Until then, GEOGloWS is used. |
| Earthdata (`~/.netrc`) | ASF HyP3 login works (8000 credits) | on-demand InSAR coherence for urban labels |
| Earthdata → GES DISC | redirected to the login page: the "NASA GESDISC DATA ARCHIVE" app is probably not authorised in the Earthdata profile | IMERG files. Not blocking: IMERG V07 comes through Earth Engine. |
| GEOGloWS v2 | open (CC BY 4.0), REST API plus S3 tables | daily discharge 1940 to last week, every river reach |

## Phases
| # | phase | state | notes |
|---|---|---|---|
| 0a | PR #1: elevation instead of the learned model | done | build/flood-learned `39d31e4`; output `flood_ranking`, `experimental`; PR title and text updated; suite 1051 passed (2 known Earth Engine-auth failures) |
| 0b | Ida compound SFINCS rerun | running | `~/.cache/geowatch/flood_round3/ida_queue.log`; 4 members one at a time, Docker capped at 3 GB |
| 0c | city-rain SFINCS runs | moved to Phase 4 | never built in round 2; Phase 4 builds rain-on-grid with subgrid on burned rain events |
| 0d | round-2 appendix | done | APPENDIX_ROUND2.md |
| 1 | diagnosis | running | catalog.py, diagnose.py, diagnose_ee.py; DIAGNOSIS.md when the label-agreement and discharge runs finish |
| 2 | labels and test design | todo | |
| 3 | seal the round-3 reserve | todo | |
| 4 | features the terrain cannot know | todo | |
| 5 | pre-register and freeze | todo | |
| 6 | one held-out pass | todo | |
| 7 | evidence packs and product PR | todo | |

## Running now
- Ida SFINCS queue (Docker).
- `diagnose_ee agree`: S1 vs EMS labels on the same grid (Earth Engine, one request at a time).
- `diagnose_ee discharge`: GEOGloWS peak timing per river unit (REST, cached per reach).
