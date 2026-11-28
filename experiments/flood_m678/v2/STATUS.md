# M6–M8 v2: status in plain words

## Step 0, protect the evidence: done (2026-11-27)

**What was done**
- Started a separate v2 branch from the reviewed design (bfa85d0).
- Pinned every source by its exact commit.
- Locked away all of v1's reserve:
  - 19 clusters and 70 incidents can never be used in v2, for training or testing;
  - the 18 v1 reserve labels that had been built are on disk with no read permission.
- v1 will never run its one-shot test.
- Listed which old data v2 may learn from:
  - round 3's 449 DEV units;
  - v1's 14 DEV incidents.
- Listed what a new reserve event must avoid: 961 round-3 footprints.
- Gave DEV and reserve separate storage. The reserve folder cannot be opened by anything except the final one-shot scorer.

**Also done (round 3, owner fixes)**
- The scorer no longer lets a baseline "pass" against the weaker baseline. Elevation or HAND can now never pass on their own, and a tie fails. A test checks this.
- The flash-flood MRMS DEV result (AUC 0.720, gain +0.071, CI 0.051 to 0.091) is pinned in round 3's STATUS with date and commit.
- Pushed as exp/flood-round3 5ca318f.

**Numbers**
- registry.json sha256 `19632c94…` (see decisions.md).

**Next: step 1, a new metadata-only seal**
- Define incidents, submodes, windows, reach anchors, footprints and independence first.
- Recruit events from open sources:
  - DFO;
  - national breach investigations;
  - the USACE levee database;
  - the CRREL ice-jam database;
  - Canadian ice flags and the Canadian River Ice Database;
  - Nordic agencies;
  - NVE;
  - GLOF v4.2;
  - gauges.
- Join related storms, then split into DEV and reserve by whole clusters.
- Push the seal before any v2 model work.

## Step 1, new seal: in progress (2026-11-27)

**Done so far**
- Wrote the rules before choosing any event (`SELECTION.md`: what counts as an event, the six submodes, time windows, the 8 km box, how related events are joined, exclusions, and the DEV and reserve split). Two amendments were also written before any split or screen:
  - recurring reaches go to the reserve, as in v1;
  - the snowmelt cause rule: a station counts as snowmelt-driven if at least 60 % of its yearly peaks fall in April–June.
- Collected event leads from open sources (`leads.csv`):

  | source | leads |
  |---|---:|
  | GLOF v4.2 lake outbursts (M6) | 1,896 |
  | DFO dam/levee (M7) and snowmelt/ice (M8) | 223 |
  | Wikipedia dam-failure list (M7) | 46 |
  | Canadian River Ice Database break-up peaks, 1984–2015 (M8 ice jam) | 1,067 |
  | WSC spring annual peaks at or above each gauge's 1-in-5-year level (M8 melt) | 5,957 |
  | USGS peak codes 3 (dam failure) and 9 (snowmelt/ice) | downloading (6 of 102 state files) |

- Joined related leads into independent groups: 1,753 groups. 7 touch v1's quarantined reserve and are excluded; 3 contain already-inspected units and are DEV-only.

**What the pool looks like before the image screen** (groups with a map location)

| submode | DEV groups | clean 2022+ groups (reserve candidates) |
|---|---:|---:|
| M7 dam/levee breach | 16 | **0** |
| M8 sustained melt | 627 | 418 |
| M8 ice jam | 111 | 44 |
| M6 lake outburst | 21 | 28 |

254 more groups have no map location (country-only records) and cannot be screened until they are located.

**What this means**
- **M8 sustained melt** is the only submode with enough supply for a properly powered test (about 34–42 usable groups needed per type). It also has a large DEV supply.
- **M7 is blocked on data**, not method: open structured sources give no located, clean 2022+ breach. What would unlock M7:
  1. Copernicus EMS / GFM access (activation footprints and image times for 2022+ breaches);
  2. a breach list with coordinates and times, such as USACE levee-breach after-action reports, NPDP/ASDSO dam incidents, or national investigations;
  3. hand-locating the 2022+ DFO dam/levee records;
  4. USGS dam-failure peak codes, still downloading.
  Recruiting continues; M7 stays experimental until a powered reserve exists.
- **M6** stays a labelled scenario unless its own evidence qualifies.

**Running now**
- Image-availability screen (metadata only):
  - log: `~/.cache/geowatch/m678v2/screen.log`;
  - check: `tail -5 ~/.cache/geowatch/m678v2/screen.log`.
- USGS downloads:
  - log: `~/.cache/geowatch/m678v2/recruit.log`;
  - check: `ls ~/.cache/geowatch/m678v2/sources/usgs | wc -l` (102 files when done).

**Next**
- Finish the screen.
- Seal v2.0: components, split and hashes, pushed before any v2 model work.
- Then step 2 (DEV labels), starting with M8 sustained melt.

## Step 1 result: seal 2.0 published (2026-11-27, tag `m678v2-seal-2.0`, commit ae935ef)

**The image screen** (metadata only, 4,294 leads):

| | DEV leads | reserve leads (2022+) |
|---|---:|---:|
| M8 melt with a crest reading and a full-box scene in the window | 881 | 389 |
| M8 melt refused as not snowmelt-driven (station peaks not mostly April–June) | 1,034 | 379 |
| M8 melt with no scene in the window | 442 | 10 |
| M8 ice jam timed with a scene | 113 | 7 |
| M8 ice jam with no scene | 554 | 5 |
| M6 lake outbursts with no downstream crest time | 296 | 168 |
| M7 breaches with no crest time | 16 | 0 |

**Seal 2.0, independent groups:**

| submode | DEV groups | reserve groups |
|---|---:|---:|
| M8 sustained melt | 301 | **254** |
| M8 ice jam | 52 | 7 |
| M7 | 0 | 0 |
| M6 | 0 | 0 |

**What this means, simply**
- **M8 snowmelt** now has far more independent held-out groups (254) than the ~34–42 a properly powered test needs, even after the losses expected when labels are built. It also has 301 DEV groups to develop on. It is the type to build first.
- **M8 ice jam** has only 7 reserve groups: too few for its own test. It stays in development, and recruiting continues: 2016+ WSC daily ice flags, CRREL, Nordic gauges.
- **M7 and M6** have no group with an independent crest time. The unlock list above stands for M7. M6 needs downstream gauge timing for lakes outside the quarantined Alaskan and Icelandic ones.
- **USGS:** 1,362 leads came in after the screen started, so they wait for addendum seal 2.1:
  - 11 dam-failure gauge records (M7);
  - 1,304 "snowmelt, hurricane, ice jam or debris" peaks, which need a second source naming the cause.

**Next: step 2 (DEV labels), M8 sustained melt first**
1. Reproduce v1's published DEV label counts on a pinned v1 fixture (Midland: 3,706 flooded / 5,378 dry) before changing anything.
2. Build a provenance record for every cell (sensor, time, offset from the local crest).
3. Show the DEV inclusion funnel by submode, region, crest precision and lag.

## Steps 2–3: DEV labels and physics, in progress (2026-11-27)

**Done**
- **Label rules pinned:** v1's labeller, run from this branch, reproduces its published DEV counts exactly on two fixtures:
  - Midland: 3,706 flooded / 5,378 dry;
  - Grand Forks BC, optical with radar fill: 2,191 / 20,610.
- **v2 labels** (`labels.py`):
  - each cell takes the observation nearest the local crest, optical first, radar only where optical says nothing (no mixing of different flood phases);
  - every cell records which sensor and how many hours from the crest;
  - DEV storage only.
- **Physics** (`routing.py`, `forcing.py`), 11 synthetic tests passing, covering:
  - zero release;
  - a hollow behind a ridge staying dry;
  - an intact levee protecting and a breached one flooding;
  - a tributary below its bed;
  - finite volume (conserved within 2 %);
  - datum shift;
  - ice-jam backwater raising only the upstream reach;
  - unknown terrain;
  - rating-curve inversion.
- **The physics score:** water depth where land is connected to the river at the event water level; elsewhere, how much higher the water would need to be (a negative number). It ranks every cell with no ties.

**First DEV numbers (too few to conclude: 2 units with full forcing)**

| unit | elevation | HAND | physics | physics, seasonal forcing | stage minus HAND |
|---|---:|---:|---:|---:|---:|
| 01BC001, 2018 | 0.394 | 0.514 | 0.367 | 0.367 | 0.520 |
| 03NF001, 2020 | 0.868 | 0.762 | 0.629 | 0.629 | 0.769 |

- **Real and seasonal forcing give identical rankings.** Inside one 8 km box, a larger discharge raises every water level about equally, so the order of cells does not move. This is exactly the design's warning. If it holds over many units, M8 melt's validation bid for spatial skill stops, and the physical gain is documented instead.
- Elevation below 0.5 at 01BC001 (radar-only label) needs a blind label check before anything is read into it.

**Running now (unattended, one heavy worker at a time)**
- **DEV labels for M8 melt:** 20 built so far, about 2–3 min each, roughly a third usable.
  - log: `~/.cache/geowatch/m678v2/labels_dev.log`;
  - check: `grep -v "EE ok" ~/.cache/geowatch/m678v2/labels_dev.log | tail -20`.
- **DEV tables** (terrain, forcing, physics and ablations): start by themselves when the labels finish.
  - log: `~/.cache/geowatch/m678v2/tables_dev.log`.
- Earth Engine is slow at the moment: one request took nearly 2 hours to time out and retry.

**Next**
1. Finish DEV labels and tables.
2. Blind label QA (wet and dry examples, paddy and shadow).
3. The DEV funnel.
4. The full comparison: elevation, HAND, physics, physics plus learned correction, and river and flash transfer.
5. The forcing, exchange and connectivity ablations.
6. Power for the actual joint pass rule.

The reserve stays sealed. Nothing is promoted from DEV.

## Owner follow-ups (2026-11-27): corridor check and M7 recruitment

### 1. Corridor check (40 km along the river network, tributaries included)
- Defined in decisions.md before any corridor number, including the stop rule: over at least 20 usable units, if forcing changes the AUC by less than 0.005 (median) and the rank correlation stays above 0.99, the M8 snowmelt bid stops at experimental.
- First 3 units, discharge scaled from the gauge to every reach:

  | unit | physics AUC (same under real, seasonal, ×½, ×2) | elevation | HAND | cells flipping wet/dry |
  |---|---:|---:|---:|---:|
  | 01BC001 2018 | 0.390 | 0.419 | 0.473 | 0.008 % |
  | 03NF001 2020 | 0.594 | 0.785 | 0.741 | 0.001 % |
  | 05AB044 2006 | 0.501 | 0.627 | 0.817 | 0.001 % |

- **Honest reading:**
  - With discharge scaled by drainage area from one gauge, every water level moves up or down by nearly the same factor, so the ranking cannot change. That is a property of the forcing design, not yet a fact about snowmelt floods. The stop rule as first written would have been met trivially, and I would rather not stop the type on that.
  - So, recorded before any such number: the corridor now also uses per-reach GEOGloWS discharge. Each reach gets its own event peak against its own normal year, so tributaries can differ from the main river. The stop rule is judged on that.
  - Physics also scores below elevation and HAND on all 3 corridors.
- The 4th unit hit an Earth Engine memory limit. Fixed: one band per request, and a failing unit is skipped and logged.
- The corridor runs again by itself after the DEV labels finish, on all units with discharge.

### 2. M7 recruitment, addendum seal 2.1 (tag `m678v2-seal-2.1`, metadata only, before any label)
- **Added:**
  - USGS dam-failure peaks (code 3);
  - 21 EMS activations (from the round-3 session's list);
  - hand-located 2022+ breaches with source links: Bagmati and Kosi, Bihar 2024 (one storm); the Budameru canal, Vijayawada 2024; Alau, Maiduguri 2024; Tuanzhou, Dongting 2024;
  - the Daugava ice jam, Latvia 2023 (M8).
- **Excluded by the round-3 or v1 rules:**
  - Emilia-Romagna 2023 and 2024, Derna, Arbaat and EMSR871 were used before;
  - Pakistan 2022 and Rio Grande do Sul 2024 sit inside round-3 footprints;
  - Pajaro, Orsk, Kherson, Al-Tlul, Gabrielle and Ussuriysk are quarantined v1 reserve.
- **Result:**

  | | reserve groups | DEV groups |
  |---|---:|---:|
  | M7 | **1** | 5 |
  | M8 ice jam | 8 (+1 Latvia) | 52 |
  | M8 snowmelt | 254 | 301 |

  All 614 seal-2.0 groups kept their side.
- **Why M7 is still stuck:** every hand-located 2022+ breach fails on timing, not data. No satellite image falls on the crest day or the day after (the brief's same-day/next-day window). Tuanzhou has no usable discharge peak at all. GFM does not change this: it is built from the same Sentinel-1 passes.
- **What would unlock M7** (owner decisions, not mine to take):
  1. A wider image window for levee breaches, where protected land stays flooded for days (for example up to 3 days after the breach, as round 3 allowed for river floods), with lag reported per label.
  2. Allowing pre-2022 incidents into a fresh reserve when nobody has inspected them (a keyed random split by component instead of the 2022 date rule). That would open the hundreds of documented older breaches.
  3. A breach list with exact coordinates and times. ASDSO's dam-incident table only exports from a browser, and NPDP's list is a web table, so either needs a manual export. USACE after-action reports are scattered PDFs.
- GFM credentials are in place. Round 3 is checking GFM against EMS optical maps today (`results/gfm_gate.json`). GFM will be used as a second, independent radar check only if it passes.

**Running unattended:** the DEV labels, then the DEV tables, then the corridor (now with per-reach forcing). Log: `~/.cache/geowatch/m678v2/dev_chain.log`.

## Addendum seal 2.2 (2026-11-28, tag `m678v2-seal-2.2`): both owner approvals applied

**Done**
- **Rules written and pushed before any affected label** (SELECTION.md Amendment 4 and 4a, decisions.md):
  1. Levee and embankment breaches: an image may be up to 3 days after the breach. Dam breaches keep same day or next day. The same rule applies to DEV and reserve, and each label records its lag to the breach.
  2. Keyed random split: the key (`split_key.txt`, its sha256 in decisions.md) was published before any component was assigned. It applies to newly entering components that have a pre-2022 incident nobody has inspected. Anything previously used, labelled or inspected stays DEV-only or excluded, and all earlier seal assignments are fixed.
- **Effect of the 3-day window on the hand-located 2022+ breaches:**
  - Budameru (Vijayawada), Bagmati and Kosi (Bihar) now have an image in their window.
  - Tuanzhou still has none.
  - Alau is a dam failure, so the same/next-day rule still applies, and it has no image.
- **Seal 2.2:** every seal 2.1 group kept its side (621 of 621).

  | submode | reserve groups | DEV groups |
  |---|---:|---:|
  | M7 dam/levee breach | **3** (2 levee, 1 dam) | 5 |
  | M8 snowmelt | 254 | 301 |
  | M8 ice jam | 8 | 52 |

**Still to do for M7 (next session)**
- **Recruit older documented breaches.** The keyed split can now send them to the reserve, but each needs an anchor and a breach time. Sources:
  - EMS 2015–2021: the 2019 Mondego dike breach in Portugal (EMSR417), Greece 2015 (EMSR122), Lazio 2021 (EMSR496), and a full-text search of older activations, whose detail endpoint fails for most codes before EMSR655;
  - USGS dam-failure peaks (code 3; already in, 5 DEV groups);
  - DFO pre-2022 dam and levee records, which are country-only and need hand-locating;
  - national reports such as India CWC, Bangladesh BWDB and China MWR, plus USACE after-action reports.
- **Owner downloads that would help** (save exactly here):
  1. ASDSO Dam Incident Database: open https://damsafety.org/incidents, click "Reset All Filters", then "Export Table to CSV". Save as `~/.cache/geowatch/m678v2/sources/asdso/asdso_incidents.csv`.
  2. NPDP dam incidents: open https://npdp.stanford.edu/data_access/dam_incidents_list.php and save the full table (CSV or "Save Page As… complete HTML") as `~/.cache/geowatch/m678v2/sources/npdp/dam_incidents.html` or `.csv`.
  3. National Inventory of Dams, to locate those US dams by name: https://nid.sec.usace.army.mil, "Download All Data (CSV)". Save as `~/.cache/geowatch/m678v2/sources/nid/nation.csv`.

**Where to resume after /clear**
- **Worktree:** `~/gw-m678v2` (branch `feat/m678-v2-impl`). Round-3 code runs from `~/gw-r3pin-r35` (with the R35 fix). Run order and plain status are in this file. Rules: SELECTION.md (Amendments 1–4a). Decisions: decisions.md. Seals: SEAL.md, `seal_2.*.json`.
- **Running unattended:** DEV labels (M8 snowmelt), then DEV tables, then the corridor (with per-reach forcing).
  - log: `~/.cache/geowatch/m678v2/dev_chain.log`;
  - check: `grep -v "EE ok" ~/.cache/geowatch/m678v2/dev_chain.log | tail -20`.
- **Next steps, in order:**
  1. When the corridor finishes, evaluate the stop rule (≥ 20 units, per-reach forcing). If forcing still changes nothing, stop M8 snowmelt at experimental.
  2. Blind label QA and the DEV funnel.
  3. The full DEV comparison (elevation, HAND, physics, physics with a learned correction, river and flash transfer) with the ablations.
  4. Power for the joint pass rule (≥ 0.80) before any reserve opens.
  5. M7 older-breach recruitment, then seal 2.3, then DEV labels for M7.
- **Constraints:**
  - one heavy worker at a time;
  - pause below 20 % free memory;
  - stop downloads below 15 GB free disk;
  - the Earth Engine lock is held exclusively for heavy calls;
  - LightGBM comes from `~/.cache/geowatch/flood_learned/pylib` (add it to PYTHONPATH);
  - the reserve stays sealed until its power receipt exists, and nothing is ever promoted from DEV.

## M7 older-breach recruitment and seal 2.3 (2026-11-28, tag `m678v2-seal-2.3`, commit 8e84e28, pushed)

**What was added**
- **ASDSO** (your export): 411 dam failures from 1984 on. 405 have a location. The other 6 have no coordinates, or the National Inventory of Dams puts the dam more than 5 km from ASDSO's point.
- **NPDP:** your save was empty, so I fetched it from npdp.stanford.edu. The search "uncontrolled release = Yes" gives 1,594 incidents, 820 of them from 1984 on, all in the US and none after 2021. 485 have coordinates on their own page. Raw pages are kept under `~/.cache/geowatch/m678v2/sources/npdp/`.
- **Older EMS breaches:**
  - Mondego, Portugal, 22 Dec 2019: added. The source is ECO/Lusa, which gives the day but no clock time.
  - Evros, Greece 2015: not added; no source names one breach with a place and a day.
  - Lazio 2021: not added; no breach is reported.
- **Timing:** each failure is timed to its reported day, because neither database gives a usable clock time. One catch: both databases store an unknown day as the 1st of the month. The 1st shows up about 5 times more often than it should, so those leads are left untimed (111 leads). I caught this after screening a draft seal and before anything was published, so the draft was thrown away.
- **Rules** are in SELECTION.md Amendment 5 (items 1–9), each committed before the step it governs.

**Keeping out of round 3's way**
- EMSR753 (Alau dam) is excluded by name, at round 3's request (checked in its files).
- Round 3 sealed its reserve today (tag `r3-reserve-seal`). Its 40 plains squares, 2 EMSR771 river areas and New York City (for its 12 FloodNet storms) are now off-limits too: 1,538 round-3 boxes in all.
- The seal script now tests this itself. Before, it relied on the rule being met; I checked seals 2.0–2.2 by hand, and none of their reserve groups touches a round-3 box.

**Seal 2.3 result**
- Every seal 2.2 lead kept its side (1,401 of 1,401). Two DEV groups have new names, because a new lead joined them, but they are still DEV.

  | submode | reserve groups | DEV groups |
  |---|---:|---:|
  | M7 dam breach | **46** (was 1) | 17 |
  | M7 levee breach | 2 | 1 (Mondego) |
  | M8 snowmelt | 254 | 301 |
  | M8 ice jam | 8 | 52 |

- Of the 45 new M7 reserve groups, 16 are from 2022 or later. The other 29 are older and went to the reserve by the published random key.
- The key sent 29 of 42 older groups to the reserve, more than the expected half (a 2 % chance). I checked: every group follows the key, and over all 2,763 groups the key splits evenly (1,409 to 1,354). So it is chance, not a bug.
- Caveat: these are mostly small US dams. A dam-break flood often drains within a day, so many will not show flooded cells. The DEV labels will show how many survive.

**Running (the one heavy job):** the corridor has resumed by itself after the M7 DEV labels. Because M7 comes before M8, I paused the corridor between units; it saves after every unit, and nothing was lost.
- Log: `~/.cache/geowatch/m678v2/m7_chain.log`.
- First result: the two Hurricane Floyd 1999 leads show no flooded cell.

**M7 DEV labels: done (23 leads in 18 groups, 14 minutes).** A label is usable if it has at least 50 flooded and 50 dry cells.
- **Usable, 3 groups:**
  - Mondego 2019 levee breach: 27,556 flooded cells, all from radar;
  - a Georgia dam, 2019: 446 flooded;
  - a Virginia dam, 2014: 63 flooded. ASDSO and NPDP list the same failure, so it is one group.
- **Too small, 2:** an NPDP dam, 1999, with 22 flooded cells, and a USGS dam-failure peak, 1996, with 40.
- **No flooded cell seen, 13 groups** (Hurricane Floyd 1999, Mississippi 2020, the North Carolina storm of 2016, and others). As expected, a small-dam flood has mostly drained by the time a satellite passes.
- **What this means:** about 2 in 17 dam groups (12 %) give a usable label. If the reserve behaves the same, its 46 dam groups would give about 5 or 6 usable units. Levee breaches do far better (Mondego). The power step will say whether that is enough. It is not looked at before then.

**Earth Engine warning.** Earth Engine says the project has gone over its free (noncommercial) compute quota and is in "restricted mode". That probably explains the "memory limit" failures that cost the corridor about half its units. Jobs still run, but more slowly and with more failures. **Owner decision:** wait for the quota to reset, or raise it in the Google Cloud console.

**Corridor so far:** 13 units, 11 with per-reach values. Real against seasonal forcing changes the AUC by 0.000 in the median unit and 0.060 at most; rank correlation is at least 0.979. The stop rule needs 20 usable units, so it is not judged yet.

**Next, in order**
1. The corridor stop rule, once 20 units are usable.
2. Blind label QA and the DEV funnel.
3. The full DEV comparison.
4. Power for the joint pass rule.

## Owner decisions applied (2026-11-28, Amendment 6), and label QA part A

**Your decisions, now in the rules (SELECTION.md Amendment 6, committed before any reserve access):**
- **Earth Engine stays free:**
  - after 3 quota errors in a row a job waits an hour, and failed units get one retry later;
  - one heavy job at a time;
  - jobs pause between units while round 3 is using Earth Engine.
- **Batch exports are written (`ee_batch.py`) but cannot run yet.** This Cloud project has no Earth Engine asset folder, so a batch export has nowhere to write (round 3 hit the same wall). Two possible fixes, both free: create the project's asset folder once in the Earth Engine Code Editor (not yet tested), or allow export to your Google Drive. Until then, jobs stay interactive and wait out the quota.
- **M7 split by whether water stays long enough to be seen:**
  - "primary" means levee or embankment breaches, plus dam failures with at least 3 million m³ stored (ICOLD's large-dam figure);
  - "small dam" means everything else. These are scenario-only, unless a label survives and its flooded cells lie within 5 km of the dam.

  | M7 | primary | small dam |
  |---|---:|---:|
  | reserve | **5** (Bihar, Budameru, and dams in Louisiana, Wisconsin and Oklahoma) | 43 |
  | DEV | 2 (Mondego, and Hurricane Matthew's 2 large reservoirs) | 16 |

- **Power is reported, not a gate.** The floor of 5 usable units per type stays.

**M7 DEV, after relabelling with primary leads first**
- The two large Matthew reservoirs (5 and 6.7 million m³) show no flooded cell either.
- **Usable primary evidence on DEV is Mondego alone.**
- Of the two small-dam labels that survived:
  - Georgia 2019 has 117 flooded cells within 5 km of the dam, so it counts (small-dam stratum);
  - Virginia 2014 has none near the dam, so its flood is the storm's, not the breach's.
- **Plain reading:** M7 will be tested on at most 5 primary reserve groups. It can only pass if almost all of them give usable labels, so the best lever is recruiting more levee breaches.

**Label QA part A** (local files only; no prediction, HAND or elevation looked at; `label_qa.json`, `funnel.csv`). Of 643 DEV labels:
- 307 have flooded cells and 184 are usable;
- 40 usable labels are radar-only and need the visual check in part B;
- 25 usable labels have flooded cells covering under 0.5 % of the box: they pass the floor, but the flooded cells could be speckle;
- 4 are over 60 % flooded, so they have few true dry cells;
- the median phase disagreement (union against merge) is 0.

DEV funnel (labelled → no flooded cell / below floor / usable):

| submode | labelled | no flood | below floor | usable |
|---|---:|---:|---:|---:|
| M8 snowmelt | 542 | 254 | 113 | 175 |
| M8 ice jam | 76 | 63 | 8 | 5 |
| M7 dam | 24 | 19 | 2 | 3 |
| M7 levee | 1 | 0 | 0 | 1 |

**Running (the one heavy job):** the corridor, until 20 units are usable (14 done).
- log: `~/.cache/geowatch/m678v2/m7_chain.log`.

**Next:**
1. Corridor stop rule.
2. QA part B: optical-against-radar agreement and the blind visual sample.
3. The DEV comparison.
4. The power report.
