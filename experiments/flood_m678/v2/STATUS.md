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
