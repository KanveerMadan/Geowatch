# flood_round3: status

Branch `exp/flood-round3` (from `07e9920`, round 2's result), worktree gw-floodproto. Read this first on any restart, and never redo a phase marked done. Judgement calls are in DECISIONS.md (R18 onwards). The diagnosis is in DIAGNOSIS.md.

## Waiting on the owner: accounts (being created 2026-11-23; nothing waits on them)
Open substitutes are in use. This is what each account will add when it exists:

| account | open substitute in use now | what the account adds |
|---|---|---|
| **Copernicus EMS** | MMFlood footprints plus our own Sentinel-1 labels (river); 2022+ public EMS list (11 AOIs) | image times and reported extents for 2015–2021 activations: checkable R19 timing for MMFlood's 95 activations and more analyst-made (optical/VHR) labels for river, flash, rain and compound |
| **GFM** (`~/.config/geowatch/gfm.json`, `{"email","password"}`, chmod 600) | our v3 Sentinel-1 label (κ 0.82 vs radar EMS for waterlogging) | an independent ensemble Sentinel-1 flood extent to cross-check waterlogging plains and river units; GFM rain/urban events for the coherence route |
| **GES DISC** (Earthdata app authorisation) | IMERG V07 through Earth Engine | direct IMERG files (only needed if Earth Engine throttles) |
| **EWDS terms (GloFAS)** | GEOGloWS v2 discharge | a second discharge source for river and compound driver checks and event features |

- **311 data:** approved for validation (2026-11-22). Each city's portal is cited in LICENCES.md, and raw reports never enter the repo.

## Credentials (checked 2026-11-22; the files are never printed, logged or committed)
| service | state |
|---|---|
| CDS (`~/.cdsapirc`, cdsapi 0.7.7) | works: ERA5 and ERA5-Land both downloaded |
| EWDS (GloFAS) | key works; CEMS terms not accepted (403) |
| Earthdata → ASF HyP3 | works, 8000 credits |
| Earthdata → GES DISC | app not authorised; IMERG comes from Earth Engine instead |

## Phases
| # | phase | state | notes |
|---|---|---|---|
| 0a | PR #1: elevation instead of the learned model | done | `39d31e4`; output `flood_ranking`, `experimental`; PR updated |
| 0b | Ida compound SFINCS rerun | running (2 of 4 members done) | `~/.cache/geowatch/flood_round3/ida_queue.log`; ~65 min per member, Docker capped at 3 GB, peak use ~300 MB |
| 0c | city-rain SFINCS | moved to Phase 4 | never built in round 2 |
| 0d | round-2 appendix | done | APPENDIX_ROUND2.md |
| 1 | diagnosis | **done** | DIAGNOSIS.md: all 9 suspected causes plus 3 new ones measured |
| 2 | label rules v3 | rules done; burned units relabelled; **rain: 311 street-flooding labels designed** | labels_r3.py; R19; R21; RAIN_311_DESIGN.md (NYC: 103 DEV / 30 reserve events before driver checks) |
| 3 | seal the round-3 reserve | criteria drafted (draft pushed); sources being added | RESERVE_CRITERIA_R3.md §8 (MMFlood via Sentinel-1, no EMS account needed); 311 for rain; R24–R25 8 km units |
| 4 | features the terrain cannot know | started | model_r3.py (anchored learner). 8 km DEV tables building (`build_r3.py`, 77 units, 2 workers, ~16 h) |
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
| Flash | 0.82, +0.016 | labels mostly 3+ days late | peak-time labels (≤ 2 d) on ~30 events; terrain headroom +0.06 exists | new source: NOAA Storm Events + Sentinel-1 inside 2 days (FLASH_SE_DESIGN). DEV: 77 usable units; reserve projected ≈ 30 |
| Waterlogging | 0.72, +0.012 | gain noisy between events | ~40–100 events, or less noisy gains; terrain headroom +0.04 | needs a much bigger pool |
| Rain | 0.61 (elevation) | labels were noise and too late | urban, peak-time labels (coherence, VHR); scoring on open cells only otherwise | 311 street-flood reports give real labels (R28, DIAGNOSIS §k). NYC: lidar + report history reach 0.79 on DEV. Chicago (flat) reaches only 0.64, below the 0.70 floor. |
| Compound | 0.66, −0.08 | one marsh box plus one late, mistyped unit | anchored model; physics (Ida SFINCS) for a real gain; ~90 events at today's spread | hard: little terrain headroom |
| Coastal | not judged (4 events) | too few events; noisy labels | ≥ 12 storm candidates with a pass inside 2 days; physics or surge height for a gain | hard: little terrain headroom |

## Running now
- 8 km DEV tables (`build_r3.py dev`, two shards; 40 of 77 built; logs `~/.cache/geowatch/flood_round3/big_dev_*.log`). bad_neuenahr is rerun after the shards finish.
- Done: Ida SFINCS (R26), MMFlood screen (R27), 311 driver checks and box features.

## New since the Phase 1–2 checkpoint
- **Gain spread (DIAGNOSIS §j):** for coastal and compound it is mostly noise inside units that are too small (25 blocks). For river and waterlogging it is mostly real event-to-event difference. So round 3 uses 8 km units (R24, R25).
- **Rain gets a real label source:** city 311 street-flooding reports, timestamped during the storm, with other reports in the same window as the dry control. NYC has 133 storm events from 2010 onwards. Typing uses IMERG rain and the Battery tide gauge (surge days become coastal or compound).
- **MMFlood without the EMS account:** the criteria now take its 95 activations on a Sentinel-1 route, for river and waterlogging only. The discharge peak, Sentinel-1 pass times and baselines all come from metadata.
- **311 fixes and checks (R28, DIAGNOSIS §k):**
  - one labelled event per storm (identical duplicate labels were removed);
  - Chicago's street-flood reports do not follow 30 m terrain (AUC ≈ 0.47), but they do recur by place, so a causal report-history feature (pre-2022 reports only) and 10 m US lidar terrain are now candidates;
  - combined, on DEV: NYC 0.79, Chicago 0.64.
- **Flash and waterlogging sources searched, none fit yet:**
  - the CC BY Zenodo 10 m set is Copernicus EMS products (our EMS route);
  - Urban Flood Observations (CC BY 4.0, PlanetScope) is 12 of 14 river events, includes a used event, and its images are mostly days after the peak;
  - Kuro Siwo (MIT) is Sentinel-1 on EMS activations, and Sentinel-1 is at chance for flash (DIAGNOSIS §e).
  - Re-typing MMFlood's "no river wave" refusals as waterlogging is rejected: DEV waterlogging is river-driven (median return period 4.7 y), so it would change the type's meaning between DEV and reserve.

<!-- DEV-CV:BEGIN -->
## DEV comparison (auto-updated 2026-11-24 19:31; leave-region-out CV, DEV units only, reserve untouched)

- **gain** is the method's mean within-unit AUC minus the better of elevation and HAND (the bar's comparison), with its 95 % cluster-bootstrap CI.
- **vs elevation** is the method's mean AUC minus elevation's.
- **chosen** is picked by the pre-registered rule: highest lower CI bound, ties within 0.005 go to the simpler method.
- **provisional:** the flash and waterlogging rows rest on a partial build that is still filling up.

### River: 31 units, 22 clusters; chosen **elev**

| method | mean AUC | vs elevation | gain vs better baseline | 95 % CI | clears CI? |
|---|---|---|---|---|---|
| elev | 0.798 | +0.000 | +0.150 | [0.1148, 0.188] | yes |
| hand | 0.648 | -0.150 | -0.150 | [-0.188, -0.1148] | no |
| elev_hand_lr | 0.798 | -0.001 | -0.001 | [-0.0042, 0.0022] | no |
| anc_elev_lgbm | 0.816 | +0.018 | +0.018 | [-0.0026, 0.0404] | no |
| anc_elev_lgbm_ev | 0.821 | +0.023 | +0.023 | [0.0028, 0.0436] | yes |

- **Still missing:** nothing on DEV; the reserve test decides.

### Flash (provisional): 14 units, 13 clusters; chosen **elev_hand_lr**

| method | mean AUC | vs elevation | gain vs better baseline | 95 % CI | clears CI? |
|---|---|---|---|---|---|
| elev | 0.697 | +0.000 | +0.030 | [-0.0138, 0.0706] | no |
| hand | 0.667 | -0.030 | -0.030 | [-0.0706, 0.0138] | no |
| elev_hand_lr | 0.701 | +0.004 | +0.004 | [0.0013, 0.006] | yes |
| anc_elev_lgbm | 0.703 | +0.006 | +0.006 | [-0.0113, 0.0241] | no |

- **Still missing:** nothing on DEV; the reserve test decides.

### Waterlogging (provisional): 32 units, 29 clusters; chosen **elev**

| method | mean AUC | vs elevation | gain vs better baseline | 95 % CI | clears CI? |
|---|---|---|---|---|---|
| elev | 0.775 | +0.000 | +0.146 | [0.1068, 0.1868] | yes |
| hand | 0.629 | -0.146 | -0.146 | [-0.1868, -0.1068] | no |
| elev_hand_lr | 0.774 | -0.001 | -0.001 | [-0.0036, 0.0006] | no |
| anc_elev_lgbm | 0.764 | -0.011 | -0.011 | [-0.0463, 0.0152] | no |
| anc_elev_lgbm_ev | 0.772 | -0.003 | -0.003 | [-0.0217, 0.0128] | no |

- **Still missing:** nothing on DEV; the reserve test decides.

### Rain: 65 units, 54 clusters; chosen **anc_elev_lgbm_fine**

| method | mean AUC | vs elevation | gain vs better baseline | 95 % CI | clears CI? |
|---|---|---|---|---|---|
| elev | 0.521 | +0.000 | -0.021 | [-0.0372, -0.0009] | no |
| hand | 0.543 | +0.021 | +0.021 | [0.0009, 0.0372] | yes |
| elev_hand_lr | 0.522 | +0.001 | -0.021 | [-0.0363, -0.0011] | no |
| anc_elev_lgbm | 0.525 | +0.004 | -0.018 | [-0.0348, 0.0026] | no |
| anc_elev_lgbm_fine | 0.591 | +0.070 | +0.049 | [0.0331, 0.0652] | yes |

- **Still missing:** mean AUC 0.5911 is below 0.70.

### Coastal: 14 units, 11 clusters; chosen **elev**

| method | mean AUC | vs elevation | gain vs better baseline | 95 % CI | clears CI? |
|---|---|---|---|---|---|
| elev | 0.763 | +0.000 | +0.094 | [0.0424, 0.1335] | yes |
| hand | 0.669 | -0.094 | -0.094 | [-0.1335, -0.0424] | no |
| elev_hand_lr | 0.763 | -0.000 | -0.000 | [-0.0028, 0.0024] | no |
| anc_elev_lgbm | 0.76 | -0.004 | -0.004 | [-0.0459, 0.0294] | no |

- **Still missing:** nothing on DEV; the reserve test decides.

### Compound: 10 units, 7 clusters; chosen **elev**

| method | mean AUC | vs elevation | gain vs better baseline | 95 % CI | clears CI? |
|---|---|---|---|---|---|
| elev | 0.759 | +0.000 | +0.074 | [0.01, 0.1268] | yes |
| hand | 0.685 | -0.074 | -0.074 | [-0.1268, -0.01] | no |
| elev_hand_lr | 0.759 | +0.000 | +0.000 | [-0.0037, 0.0038] | no |
| anc_elev_lgbm | 0.765 | +0.006 | +0.006 | [-0.0496, 0.0333] | no |
| anc_elev_lgbm_ev | 0.778 | +0.019 | +0.019 | [-0.0053, 0.0361] | no |

- **Still missing:** nothing on DEV; the reserve test decides.

<!-- DEV-CV:END -->
