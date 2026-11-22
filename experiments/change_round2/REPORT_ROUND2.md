# GeoWatch change detection, round 2

**Keep public alerts off for all five targets.** Forest loss gave the strongest result. The detector found clearing in all three new regions, including two in Southeast Asia. Radar also made floodwater visible in places where clouds had defeated the old method. The water results varied sharply across incidents. The building models missed nearly all additions and generated many false removal flags.

## Results on previously unseen locations

| Change | Found / all reference changes | False flags / observed negative controls | Next step before public alerts |
|---|---:|---:|---|
| New open water | **12/18 (67%)** | **0/13** | Continue silent monitoring. Collect independently dated flood outlines and stable controls in the same flood areas, particularly around Guaíba and in built-up neighborhoods. Measure how quickly a second satellite look arrives. |
| Water loss | **10/24 (42%)** | No eligible stable-wet controls | Test a separate recession detector that compares an observed wet peak with the subsequent drying phase. Include reservoirs and seasonally wet areas known to have stayed wet. |
| Forest loss | **29/34 (85%)** | **0/16** | Expand silent monitoring into forest regions. Review quiet and flagged cells in plantations, seasonal canopy and partial clearings, and date changes with independent repeat imagery. |
| Building additions | **2/74 (3%)** | **6/193** | Train on independently dated, tracked footprints, including recent construction and stable blocks in each city. Evaluate whether 200 m radar and optical observations can separate the two. |
| Building removals | **2/11 (18%)** | **49/269** | Collect verified demolitions and stable built blocks exposed to construction, shadows and seasonal shifts. Calibrate on whole held-out cities before considering an alert threshold. |

The always-silent baseline detected **zero** of the listed changes and raised **zero** false flags on every available control. All reference-positive cells count in the first column, including detector abstentions. The control column uses only independently labelled negatives the detector could judge. Building controls are direction-specific, so a block with no additions may contain removals. These counts are for individual cells or blocks. [Locked results, including per-site rows and baseline comparisons](fresh_result.json)

## Forest and buildings on new ground

* **Forest.** The detector found 10/12 reference losses in West Kalimantan, 8/10 in Ratanakiri and 11/12 in Madre de Dios. It abstained on two positive cells, both in Cambodia, and two of the 18 stable controls. Only four observable stable controls came from Southeast Asia. The positive references describe annual stand-replacement loss, and the stable controls were selected for persistently green canopy. Recent plantings and partial clearing need separate tests. The detector's prior forest layer ends in 2020.
* **Building additions.** Across the three SpaceNet neighborhoods, the model found 0/12 additions in Panama, 2/13 in China and 0/49 in Sudan. The Sudan blocks all had radar and optical inputs. Thirteen of 280 block-level addition references were ambiguous and were excluded. On the remaining blocks the pooled ranking AUC was **0.286**, compared with **0.500** for a constant score.
* **Building removals.** Of 51 removal flags, only two matched a tracked disappearance. Pooled ranking AUC was **0.605**, compared with **0.500** for a constant score. Within the two neighborhoods that actually had removals, AUC was **0.437** and **0.326**. At the frozen threshold the model flagged almost the same share of changed and stable blocks. The three comparisons span January 2019–January 2020. Accuracy on recent construction and demolition is still unknown.

## What changed in development

**New open water.** Radar can now confirm a gain when clouds hide the optical view. It compares VV and VH backscatter against earlier observations on the same viewing track, screens terrain and historical permanent water, and requires corroboration. On the previously studied Sylhet flood, the old detector confirmed 0 of 120 flooded cells. Radar confirmed 68 by the June 18 survey and 93 by June 30. All 120 lacked a usable optical measurement in June. In Sindh, radar confirmed only 11 of 48 cells marked flooded in an independent Sentinel-2 survey. All 48 had compatible radar observations. These positive-only samples measure missed mapped floods. They cannot measure false alarms. The always-silent baseline detected zero in each. [Sylhet records](water_dev.json) · [Sindh records](sindh_dev.json)

**Forest loss.** We traced all 13 Chaco misses before revising the method. Eleven cells never crossed the old greenness threshold. Two crossed it on just one date. The revised detector checks for sustained losses in optical greenness or radar VH, using seasonally comparable observations and a prior forest map. It confirmed 24/24 known Chaco losses and 20/24 known Sumatra losses. Eleven of the 20 Sumatra hits came from radar alone. The old detector found 11/24 and 0/24 respectively. The silent baseline found zero. These are the cases used to develop the revision, and the forest reference dates a loss only to the year. [Original Chaco traces](chaco_misses.json) · [Forest replay](forest_dev.json)

**Building expansion and removal.** Two separate 200 m block classifiers use radar, optical imagery and historical built-up share. The training set contains 1,470 annual block comparisons from ten city neighborhoods. Training labels use persistent changes in Google's annual building confidence from 2016–2023. In development folds that withheld entire cities, the expansion classifier found 28 of 70 proxy gains and flagged 449 other blocks. The removal classifier found 7 of 32 proxy losses and flagged 515 others. The silent baseline had zero hits and zero false flags. The numerical outputs are uncalibrated scores. [Building method, training coverage and results](building_method.md)

## Test integrity

The protocol fixed the sites or deterministic selectors, observation windows, reference definitions, sampling, model weights and scoring before any held-out imagery or reference records were opened. The Git push finished at **19:57:57 UTC on November 21, 2026**. The runner checked the exact commit against the live remote at **19:58:17 UTC**, then opened the data. The dates correspond to November 22 in India. The lock-file SHA256 is `afc2a8d137d4649d83649dc4d86c9530f365956a78e816a474a2ff51855d301e`. [Published registration](https://github.com/KanveerMadan/Geowatch/commit/7d8a23c3117f079c6bb96b477081fcb533d7e13e) · [Protocol](fresh_protocol.md) · [File hashes](fresh_lock.json)

Natural-area tests use up to 12 geographically spaced cells per reference class and site. Water references come from Landsat, forest references from annual Hansen loss and Landsat stable-canopy checks, and building references from SpaceNet's independently tracked Planet footprints. A cloudy date, an ambiguous reference or a location without suitable observations remains unknown. Neighboring cells can share the same event. Sampling on reference class prevents estimation of the proportion of all future public alerts that would be correct.

The run completed at 20:11:21 UTC. An independent offline count reproduced every per-site and pooled confusion table, abstention and building ranking metric across all 667 archived target rows. The result file's SHA256 is `f739a952a1c5d95251ca29f9297179ae2e09cf72a2511f96fabd72044827351f`.

## Where new water and water loss worked

| Independent test window | New water found / labelled | Flags / observed stable-dry controls | Water loss found / labelled | Flags / observed stable-wet controls |
|---|---:|---:|---:|---:|
| Edenville and Sanford, Michigan | 0/3 | 0/1 | 10/12 | No eligible controls |
| Lismore, Australia | 2/3 | 0/12 | No eligible losses | No eligible controls |
| Guaíba, Brazil | 10/12 | No eligible controls | 0/12 | No eligible controls |

The sites reveal two different limitations. Guaíba supplied most of the gain detections and none of the stable-dry controls. All 12 missed water losses there had comparable sensor looks, but none generated even one loss candidate. In Michigan the same method found ten losses, with the first confirmation 17–22 days after the first changed Landsat observation. For the ten gains found in Guaíba, that interval was 10–13 days. In Lismore, one detection preceded the first clear Landsat observation by five days and the other followed it by three. Satellite observation dates bracket when change was visible. These intervals cannot establish emergency warning time.

## What the silent monitor saw

The first prospective collection covers acquisitions through November 20 UTC in Kolkata, Pune, Bandung, Dakar, Haarlem and Utrecht. The six plots contain **54 cells totaling 0.54 km²**. The registered detector version logged two candidate cells, one for water and one for forest, and zero confirmations. The always-silent comparator also issued zero confirmations. An earlier version processed the same cutoff. This is **one monitoring period**.

An image reviewer assessed eight masked Landsat cases before seeing the predictions, including the two candidate cells and six quiet cells. Four had visibly stable water and four had insufficient evidence. Two had visibly stable vegetation, and the forest detector abstained on both. The other six vegetation cases were unresolved. No reviewed case established a positive transition. The field false-alert rate and real-world recall remain unknown. Daily collection and blind review are scheduled for 09:30 India time. [Collector and review procedure](monitoring.md) · [Collection totals](monitor_corrected_summary.json) · [Sealed visual review](monitor_corrected_review.json)
