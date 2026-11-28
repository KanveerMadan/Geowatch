# M6–M8 v2 decisions (append-only)

2026-11-27. **Step 0 (protect the evidence).**
- **Branches:**
  - Implementation branch `feat/m678-v2-impl` from `origin/design/m678-v2` at **bfa85d0d207ee6d19619085e21a280b2a52abce7**.
  - The design is based on v1 at f8e0777. v1 has one later commit, a0bfe89, the reserve-labeller defect note. It is reconciled below.
- **Pins** (`registry.py`):
  - v1 seal `fb73a2e` (tag `m678-reserve-seal`);
  - v1 freeze `222c904` (tag `m678-freeze`);
  - round 3 at `5ca318f`, which includes R35 (no baseline exemption).
  v2 imports round 3's code from a detached worktree at that SHA (`~/gw-r3pin-r35`), never from a moving branch.
- **v1 quarantine, forever:**
  - Every v1 reserve cluster (19 type:cluster keys, 70 incidents including the pre-2022 ones withheld from DEV and those refused by the per-cluster cap) is excluded from v2 training and testing.
  - The 18 v1 reserve labels that were built before v1 stopped are moved to `~/.cache/geowatch/flood_m678/QUARANTINE_v1_reserve`, mode 000. Nobody scored or inspected them beyond the label-builder's own count line.
  - The v1 labeller defect (6 incidents) is moot: v1 never runs its one-shot test.
  - v1 scoring is disabled in this workflow: v2 never imports or calls `score_m678.py` or `chain_reserve.sh`.
- **v1 DEV incidents** (14) were inspected. In v2 they are DEV-only, never reserve.
- **Round 3:**
  - Its 449 DEV units (burned and Sentinel-1-route catalogues) are the only round-3 tables that `transfer.py` may read.
  - Its registries, candidate pools and DEV footprints (961 footprints) exclude any v2 reserve candidate that touches them (20 km rule, as v1).
  - Round 3's own reserve is not sealed yet. v2 reserve selection rechecks its metadata at v2 seal time.
- **Storage:**
  - DEV data under `~/.cache/geowatch/m678v2/dev`.
  - Reserve under `~/.cache/geowatch/m678v2/reserve`, created mode 000. Only `score_once` (step 6) may unseal it, after verifying seal, freeze and power receipts.
  - Unit tests use synthetic data only (`test_step0.py`).
- **Owner additions recorded:**
  - **Priority:** M7 first, then M8 sustained melt, then M8 ice jam. M6 ships as a labelled scenario (water release and debris runout separate) unless its own evidence qualifies.
  - **Resources:**
    - the Earth Engine lock is held exclusively for heavy calls;
    - one heavy worker;
    - pause below 20 % free memory;
    - stop downloads below 15 GB free disk;
    - caffeinate, checkpoint and resume.
  - **Reporting:** STATUS.md after each step, a push after each step, and a PR to master only for product changes.

2026-11-27. **Step 2 labels, before any v2 label.**
- v1's labeller reproduces its published DEV counts on two pinned fixtures, from this branch's code into the v2 DEV store:
  - Midland (optical): 3,706 flooded / 5,378 dry;
  - Grand Forks BC (optical with radar fill): 2,191 / 20,610.
- v2 `labels.py` keeps v1's five-state rules unchanged (imported, not copied) and changes three things:
  1. **No union across flood phases.** A cell takes the in-window observation nearest the local crest, optical first; radar fills only cells no optical scene decides. The union is kept as a secondary layer, for the label-QA comparison only.
  2. **Per-cell provenance:** sensor family, scene and offset.
  3. **The 8 km box is labelled on its own grid** when it extends past the search square (v1's defect).
- DEV takes at most two leads per component, earliest first, and builds M8 sustained melt first.

2026-11-27. **Corridor diagnostic (the design's predeclared secondary footprint), fixed before any corridor number exists (owner instruction).**
- **Domain:** a 40 km square centred on the lead's anchor (the gauge).
- **Network:** MERIT upstream area ≥ 10 km², so tributaries are included.
- **Corridor footprint:** cells within 1.5 km of the network with HAND ≤ 30 m. This spans several reaches, tributaries and levee compartments, where stage really varies.
- **Labels:** v2's rules over the whole domain (nearest-to-crest merge, optical first, radar fill), scored on corridor cells, needing ≥ 50 flooded and ≥ 50 dry.
- **Physics:** the same score as the box (`routing.physics_score`), with per-cell discharge Q = Q_gauge × (upa / upa_gauge)^0.8 and HAND rating-curve stage per upstream-area band.
- **Forcing variants:**
  - real (the event peak);
  - seasonal (station median annual maximum, 1984–2021);
  - exchanged (another DEV unit's peak/median ratio, paired in sorted order);
  - ×0.5 and ×2.
- **Reported per unit:**
  - AUC of each variant, plus elevation and HAND on the same corridor cells;
  - Spearman correlation of physics scores, real against seasonal;
  - the share of corridor cells whose predicted wet status (score > 0) changes;
  - whether predicted wet extent increases with Q (direction check).
- **Stop rule for M8 sustained melt:** over ≥ 20 usable corridor units, if the median |AUC(real) − AUC(seasonal)| < 0.005 AND the median Spearman(real, seasonal) > 0.99, forcing changes nothing that matters. The M8 snowmelt bid for spatial skill then stops at experimental (ARCHITECTURE_V2 item 5). Otherwise development continues. The corridor never replaces the 8 km box as the primary footprint.

2026-11-27. **Corridor diagnostic: the forcing must be able to vary between reaches (recorded before any per-reach number exists).**
- **Finding** on the first 3 corridor units: physics AUC is identical under real, seasonal, ×0.5 and ×2 forcing, Spearman(real, seasonal) ≥ 0.9998, and ≤ 0.008 % of corridor cells change predicted wet status.
- **Why:** the forcing scales one gauge discharge to every reach by upstream area, so every stage shifts by nearly the same factor. The order of cells cannot move by construction. The stop rule as written would therefore be met trivially, and that would say nothing about forcing as such.
- **Added variant `reach`:** per-reach GEOGloWS v2 forcing. Each channel cell takes the event peak (in [crest − 3 d, crest + 5 d]) of its nearest GEOGloWS reach, and the seasonal comparator `reach_seasonal` takes each reach's own median annual maximum (1984–2021). This is the "routed discharge per reach" of ARCHITECTURE_V2 (M8 adapter). Tributaries can now carry a different event magnitude from the trunk.
- **The stop rule is evaluated on `reach` against `reach_seasonal`,** with the same thresholds: median |ΔAUC| < 0.005 and median Spearman > 0.99, over ≥ 20 usable corridor units.
- The uniform-scaling result is kept and reported as what it is: a property of that forcing design.
- **Engineering:** terrain is requested one band per call (the 40 km domain exceeded Earth Engine's per-request memory), and a failing unit is logged and skipped, never fatal.

2026-11-28. **Addendum seal 2.2 rules (owner approved both), before any label of an affected lead.**
1. Levee/embankment breach window: [breach, breach + 72 h]. Dam breaches unchanged. Lag per label to the breach.
2. Keyed random split for newly entering components. Key sha256 `742b0d6f05365c71cb4151e28ce7c4a2ef6b9ec65364d6a9771163bd7f5abb8b` (`split_key.txt`), published with SELECTION.md Amendment 4 before assignment. Previously used, labelled or inspected units stay DEV-only. Seal 2.0/2.1 sides are fixed.

## 2026-11-28: Amendment 5 (seal 2.3 rules), written before any ASDSO/NPDP lead is screened
- New M7 sources: ASDSO failures (owner export) and NPDP uncontrolled-release incidents (fetched by the session from the public search page; raw HTML kept under `~/.cache/geowatch/m678v2/sources/npdp/`). Crest = incident day, time zone unknown. No size floor at lead stage, the same as the USGS code-3 leads; the label floor (≥ 50 flooded and ≥ 50 dry cells) decides.
- Round 3 asked (cross-session, 2026-11-28) that EMSR753 stay round-3 territory. Verified in round 3's `r3_ems_candidates.json` and DECISIONS at 30580f9. Excluded by name.
- Gap found and fixed: `seal_v2.py` never applied SELECTION §4's round-3 footprint test itself. Rechecked: 0 of 265 seal-2.2 reserve components touch a footprint (one DEV component does, and DEV is allowed). The test is now in code from seal 2.3, against the pinned set plus round 3's live candidate pools.

## 2026-11-28: M7 DEV labels (code fixed before any M7 label)
- `labels.py dev --seal 2.3 --type M7` labels the M7 DEV components of seal 2.3 (2 leads per component at most, as before).
- M7 scene windows come from the same function the seal screen uses (`screen_v2.screen_lead`), so a DEV label sees exactly the sealed window. A dry run showed the same optical and radar counts as the screen for all 23 leads.
- Each M7 label records its lag to the breach (Amendment 4.1): from the reported breach time, the start of the breach day, or, for dams known only to the day, the start of the crest window.
- Priority M7 > M8: the corridor (an M8 diagnostic) is paused between units for the M7 DEV labels, then resumes. It saves after every unit.

## 2026-11-28: owner decisions recorded as Amendment 6
- Free-tier Earth Engine: no quota raise, wait for resets, batch exports where possible, one heavy job at a time, and pause while round 3 uses EE.
- M7: levees and large reservoirs (≥ 3 million m³) are primary; small dams are scenario-only unless a label survives.
- Power is reported, not a gate.
- **DEV observation behind the M7 split:** the two small-dam DEV labels that passed the floor come from tiny reservoirs (about 37,000 and 61,000 m³). Their flooded cells are more likely the storm's ordinary flooding than breach water. Label QA checks where those cells lie relative to the dam's downstream valley before they count as M7 evidence.
- Batch export: `ee_batch.py` (interactive request → batch export to an asset → read back on the same grid) is written. It stays inactive, because the project has no asset root. A likely fix (not yet tested here) is for the owner to open the Earth Engine Code Editor for this project once and create its home asset folder, which is free.
- The corridor now stops when 20 units are usable (`--until-usable 20`), which is when the stop rule is judged.
