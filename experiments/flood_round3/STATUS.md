# flood_round3: status

Branch `exp/flood-round3` (from `07e9920`, round 2's result), worktree gw-floodproto. Read this first on any restart, and never redo a phase marked done. Judgement calls are in DECISIONS.md (R18 onwards). The diagnosis is in DIAGNOSIS.md.

## Waiting on the owner (everything else continues)
1. **EMS account (only you can create it).** Pre-2022 Copernicus EMS activations need a login. They hold the image times and reported extents of 2015–2021 floods, including MMFlood's 95 never-used activations. Without it, the fresh pool with checkable timing is 11 AOIs (R23).
2. **Optional:**
   - accept the CEMS Early Warning Data Store terms (GloFAS) at https://ewds.climate.copernicus.eu/licences/terms-of-use-cems;
   - authorise "NASA GESDISC DATA ARCHIVE" in your Earthdata profile.
   - Both have open substitutes in use (GEOGloWS, IMERG through Earth Engine).

## Credentials (checked 2026-11-22; the files are never printed, logged or committed)
| service | state |
|---|---|
| CDS (`~/.cdsapirc`, cdsapi 0.7.7) | works: ERA5-Land downloaded. The tiny ERA5 request passed the licence check and was still in the CDS queue after 1 h |
| EWDS (GloFAS) | key works; CEMS terms not accepted (403) |
| Earthdata → ASF HyP3 | works, 8000 credits |
| Earthdata → GES DISC | app not authorised; IMERG comes from Earth Engine instead |

## Phases
| # | phase | state | notes |
|---|---|---|---|
| 0a | PR #1: elevation instead of the learned model | done | `39d31e4`; output `flood_ranking`, `experimental`; PR updated |
| 0b | Ida compound SFINCS rerun | running | `~/.cache/geowatch/flood_round3/ida_queue.log`; 4 members in turn, ~45 min each, Docker capped at 3 GB |
| 0c | city-rain SFINCS | moved to Phase 4 | never built in round 2 |
| 0d | round-2 appendix | done | APPENDIX_ROUND2.md |
| 1 | diagnosis | **done** | DIAGNOSIS.md: all 9 suspected causes plus 3 new ones measured |
| 2 | label rules v3 | rules done; burned units relabelled | labels_r3.py; R19; R21. Next: urban labels (HyP3 coherence), max-extent from S2/Landsat/HLS |
| 3 | seal the round-3 reserve | criteria drafted (not pushed); EMS metadata pulled | RESERVE_CRITERIA_R3.md, select_r3.py. **Blocked on the fresh-event pool (R23)** |
| 4 | features the terrain cannot know | started | model_r3.py (anchored learner, λ by inner CV, tests pass). Oracle headroom caps terrain re-weighting (DIAGNOSIS §a) |
| 5–8 | pre-register, freeze, score, evidence, product | todo | |

## What the diagnosis found, in plain words
- **The learned models were elevation in disguise.** Their scores rank cells like elevation (correlation 0.79–0.87), because no input says how much water this event brought or where it went.
- **Even a perfect re-weighting of the terrain layers cannot win by much.** An oracle that knows the answer gains only +0.02 (river), +0.01 (coastal) and +0.03 (compound) over elevation. A test of practical size needs about +0.04–0.05.
- **The rain test measured noise.** Rain labels came 3+ days after the rain in 77 % of events, and none within a day. Our Sentinel-1 rain labels flag high ground as often as low ground, and they agree with independent optical maps only at chance level (κ 0.02).
- **Radar labels cannot see floods among buildings.** Built-up cells are flagged at 2–13 % of the open-ground rate. They are now "unobserved", not "dry".
- **Our Sentinel-1 labels had fixable bugs:** a baseline that sometimes contained the flood, and no open-water test. Both are fixed in v3.
- **Compound's −0.08 was one marsh box** (Francine), where an unanchored model ranked backwards, plus one unit imaged 67 days late. The anchored learner prevents the first; the timing and type checks prevent the second.
- **Round 2 was underpowered.** Its gains (+0.012 to +0.016) would need hundreds of events to confirm.
- **Fresh events are scarce.** Only 11 never-used EMS areas pass the rules. Pre-2022 EMS events need an EMS account.

## Per type (plain English)
| type | round 2 | main cause found | what it needs to pass | outlook now |
|---|---|---|---|---|
| River | 0.91, +0.015 (CI crosses 0) | gain real but small; too few events | ~60 fresh events at the current gain, or a bigger gain from event water levels / physics | best placed; needs the bigger fresh pool |
| Flash | 0.82, +0.016 | labels mostly 3+ days late | peak-time labels (≤ 2 d) on ~30 events; terrain headroom +0.06 exists | needs new peak-time sources |
| Waterlogging | 0.72, +0.012 | gain noisy between events | ~40–100 events, or less noisy gains; terrain headroom +0.04 | needs a much bigger pool |
| Rain | 0.61 (elevation) | labels were noise and too late | urban, peak-time labels (coherence, VHR); scoring on open cells only otherwise | cannot be tested on today's labels |
| Compound | 0.66, −0.08 | one marsh box plus one late, mistyped unit | anchored model; physics (Ida SFINCS) for a real gain; ~90 events at today's spread | hard: little terrain headroom |
| Coastal | not judged (4 events) | too few events; noisy labels | ≥ 12 storm candidates with a pass inside 2 days; physics or surge height for a gain | hard: little terrain headroom |

## Running now
- Ida SFINCS queue (Docker).
