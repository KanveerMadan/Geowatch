# M6–M8 v2: what an event is, and how events are split (written before any v2 selection)

Fixed before any candidate is listed. It follows ARCHITECTURE_V2.md ("Event supply", "What can earn a pass"), with the owner's standing rules. Reserve selection reads metadata only: no pixels, labels, quicklooks, features or scores.

## 1. Incident and submode

An **incident** is one physical flood at one reach, with a cause from an independent source (agency report, gauge qualification code, investigation, inventory record). Submodes are tested separately:

| type | submode | the cause must say |
|---|---|---|
| M7 | `reservoir_breach` | a dam or reservoir embankment failed and released stored water (tailings excluded unless free water is distinguishable) |
| M7 | `levee_breach` | a river levee or embankment breached and water entered protected land |
| M8 | `sustained_melt` | spring snowmelt, with or without rain on snow, raised the river over days |
| M8 | `ice_jam` | an ice jam or breakup obstruction raised the stage (gauge ice flag, ice database, report) |
| M6 | `water_release` | a glacial or moraine lake released water (outburst) |
| M6 | `debris_runout` | a debris flow or debris-rich surge (target: deposit boundary, not water) |

## 2. Window, crest, anchor, footprint

- **Crest:** as in v1's addendum. In order of preference:
  1. an approved gauge bracket;
  2. an agency crest record, including WSC annual peaks, USGS peak records, CRID break-up peaks and NVE;
  3. a published reading;
  4. a published day;
  5. GEOGloWS, only for levee breaches and melt, never for dam or lake failures.
- **Image window:** v1's limits are kept as outer bounds:
  - M6, M7 and ice jams: [crest − 24 h, crest + 48 h];
  - sustained melt: [crest − 24 h, crest + 72 h];
  - levee breaches: after the breach.
  The primary temporal merge is locked on DEV (BUILD_PLAN step 2).
- **Reach anchor:** the gauge, breach, dam or lake outlet location from the source record. For a lake, the anchor is the downstream reach used for timing.
- **Footprint:** primary is the 8 km scored box, placed by round 4's flood-centre rule on the 20 km search square around the anchor (labelled on its own grid). Routing runs beyond it. A source-located corridor is a predeclared secondary diagnosis only.

## 3. Independence (joined before counting or splitting)

The **component** is the transitive closure, across v1, round 3 and v2 records, of:
- the same named storm or synoptic event, including a spring melt season in one basin;
- the same reach (anchors within 20 km on the same river) or the same gauge;
- the same lake;
- a cascade (one failure triggering another);
- any shared historical branch.

Leads with anchors within 20 km and dates within 30 days are joined as well. Components are counted, assigned and folded whole.

## 4. Exclusions (`registry.json`, pinned SHAs)

- Any component containing a v1 reserve cluster or incident: excluded from v2 forever.
- v1 DEV incidents and round-3 DEV units: DEV-only.
- A reserve candidate whose 20 km search square touches any of round 3's 961 footprints: excluded.
- Round 3's reserve metadata is rechecked at seal time.

## 5. Target population and split

- **DEV and reserve, by the owner's standing rule:**
  - DEV: incidents before 2022-01-01;
  - reserve: incidents on or after 2022-01-01;
  - plus whole-component assignment: a component containing any DEV-only or pre-2022 incident is DEV. A reserve component has only incidents from 2022 onwards and nothing previously inspected.
- **Reserve eligibility** (metadata only): crest evidence plus a full-box scene in the window (v1's screen), per submode.
- **No replacement after labels are seen.** New leads found later enter a versioned addendum seal under the same rules, before any reserve access.
- **The test opens per type** only when the power receipt (BUILD_PLAN step 5, ≥ 0.80 for the joint pass rule) exists. Otherwise recruitment continues and the reserve stays sealed.

## 6. Lead sources (open), joined before counting

- **DFO** (cause-matched dam/levee and snowmelt/ice records).
- **USGS annual peaks:**
  - qualification code 3 (dam failure) → M7 lead;
  - code 9 (snowmelt, hurricane, ice jam, debris dam) → M8 lead, needing a cause confirmed by a second source.
- **WSC annual peaks and daily ice symbols** (B = backwater from ice) → M8.
- **CRID:** spring break-up peak HM (ice jam) and open-water peak HO (melt), 196 gauges, 1894–2015 → M8, DEV.
- **USACE CRREL ice-jam database** (where exportable) → M8.
- **USACE National Levee Database** → levee geometry for M7 (not events).
- **National breach investigations and DFO** → M7.
- **GLOF v4.2 and NVE GLOF reports** → M6.
- **Nordic national gauges** (SMHI, SYKE, NVE) → M8.
- **Copernicus EMS / GFM** when the owner grants access.

Each lead keeps its source row, cause text, date fields and anchor. Yield is logged by region and submode at every stage: lead → joined component → crest → scene → (DEV only) label.

## Amendment 1 (2026-11-27, before any v2 selection or component split has run)

§5's whole-component rule is replaced, because almost every gauge or lake has pre-2022 history, so a recurring reach would always fall to DEV. The reserve then could not approach the 34–42 clusters per type that the power target needs. The rule is now v1's (DECISIONS_M678 2026-11-27):
- A component with any v1-reserve incident is excluded from v2.
- A component containing an inspected unit (v1 DEV incident or round-3 DEV unit) is DEV-only.
- Any other component with a timed, full-box incident on or after 2022-01-01 is a reserve component. Its pre-2022 incidents are withheld from DEV training, CV and method choice.
- Every remaining component is DEV.

Joining edges (transitive), across all types:
- the same station or anchor id (any date);
- the same lake name (any date);
- anchors within 20 km and dates within 30 days;
- anchors within 20 km on the same named river (river token in the station names), any date.
Leads without a coordinate anchor (country-only) cannot be joined or screened. They stay in the lead log until geolocated.

## Amendment 2 (2026-11-27, before the screen runs)

Sustained-melt cause from gauge history (metadata only): a WSC station is nival when at least 60 % of its 1984–2021 annual maximum water levels fall in April–June. Spring peaks at other stations are refused as `not_nival` (likely rain-driven). Other M8 leads need a cause from their source: a USGS code 9 lead needs a second source naming snowmelt or ice, and a CRID HM peak is break-up by definition. A WSC crest reading gets a ±15 min bracket from its UTC offset. A crest day without a time zone gets a window wide enough for any zone (local day −12 h to +36 h UTC).

## Amendment 3 (2026-11-27, before addendum seal 2.1 and before any v2 label of these leads)

New lead sources, under the same rules:
- **USGS annual peaks:** code 3 gives M7 dam failures. Code 9 peaks stay `cause_unconfirmed` until a second source names snowmelt or ice.
- **Copernicus EMS activations** keyword-matched by the round-3 session (metadata; the EMS centroid is the anchor; no crest unless found elsewhere).
- **Hand-located breaches** (`handlocated.csv`): coordinates from OSM place points, times as reported, and the retrieved source URL for each.

Changes to joining and sealing:
- **Storm tags:** leads sharing a storm tag are one component.
- **Stable assignment in an addendum seal:** a component that shares any lead with a sealed component keeps that component's side. One that would merge a sealed DEV component with a sealed reserve component is excluded. Seal 2.0 assignments never change.

## Amendment 4 = addendum seal 2.2 rules (owner approval 2026-11-28; written before any label of an affected lead)

1. **Levee and embankment breaches: image window up to 3 days after the breach.** The window is [breach time, breach time + 72 h]; a lead needs a reported breach time. The protected land stays flooded for days, so the late bound runs from the breach, not the river crest. Dam and reservoir breaches keep the same-day/next-day rule ([crest − 24 h, crest + 48 h]). Applied identically to DEV and reserve. Each label records its lag to the breach in hours.
2. **Fresh reserve by a keyed random split, for uninspected pre-2022 incidents.**
   - Key: `split_key.txt` (sha256 `742b0d6f05365c71cb4151e28ce7c4a2ef6b9ec65364d6a9771163bd7f5abb8b`), committed with these rules before any component is assigned under them.
   - A component newly entering in seal 2.2 or later (in no earlier seal) is reserve if `int(HMAC-SHA256(key, component_id)[:8], 16) / 2^32 < 0.5`, otherwise DEV, for every date.
   - The following stay DEV-only (or excluded) whatever the key says: any component containing a previously used, labelled or inspected unit, meaning v1 DEV incidents, round-3 DEV units, or any v2 DEV label already built.
   - Components that touch v1 reserve or round-3 footprints stay excluded, as before.
   - Components already in seal 2.0 or 2.1 keep their side.
   - On the reserve side, all of a component's timed incidents count, of any date (no 2022 cut for keyed components).

### Amendment 4a (2026-11-28, before any component is assigned under Amendment 4)

Matching the owner's instruction ("a keyed random split by component for uninspected pre-2022 incidents"), the keyed split applies only to newly entering components with at least one timed pre-2022 incident. A newly entering component whose timed incidents are all from 2022 onwards is reserve by the date rule, as before. Everything else in Amendment 4 stands.

## Amendment 5 = addendum seal 2.3 rules (2026-11-28; written before any ASDSO or NPDP lead is screened, and before any M7 label)

1. **New M7 lead sources (metadata only), all as `reservoir_breach`:**
   - **ASDSO Dam Incident Database:** the owner's export of https://damsafety.org/incidents (2026-11-28). Only rows with Incident Type = Failure, from 1984. Anchor: ASDSO's dam coordinates. When the row's NID number is in the National Inventory of Dams (owner's export, data date 2026-11-20) and NID puts the dam more than 5 km away, the lead is unlocated ("country only") and is not screened. A named hydrologic event becomes a storm tag, so dams failing in one storm are one component.
   - **NPDP Dam Incident Database:** the search "Uncontrolled Release of the Reservoir = Yes" on https://npdp.stanford.edu/data_access/dam_incidents_list.php, from 1984. Coordinates and storage come from each incident's own page (`dam_incidents_view.php?editid1=<id>`).
   - Tailings dams are dropped, as in §1.
2. **Timing:** the crest is the reported incident day. Neither source gives a reliable time (ASDSO's time field is sparse and mixes placeholders such as "12:00 AM"), so the day gets the time-zone-unknown window of Amendment 2 (local day −12 h to +36 h UTC), and then the dam window of §2 (crest − 24 h to crest + 48 h).
3. **Duplicates:** ASDSO, NPDP and USGS code-3 records of one failure are joined by §3 (anchors within 20 km and dates within 30 days) before counting.
4. **Split:** as Amendment 4 and 4a. A newly entering component with a pre-2022 incident is assigned by the published key. Components joined to sealed ones keep their side.
5. **§4 enforced in code from seal 2.3.** Until now the seal script did not itself test the round-3 footprint rule (§4, 961 footprints in `registry.json`). A check on 2026-11-28 found that no reserve component of seals 2.0–2.2 touches one, so no earlier assignment is affected. From seal 2.3:
   - every reserve candidate's 20 km search square is tested against the pinned footprints **and** round 3's candidate pools at round 3's current branch head (its SHA is recorded in the seal). A touching new component is excluded. A touching sealed reserve component stops the seal for an owner decision.
   - **EMSR753 (Alau dam, Borno, 2024) is excluded by name.** It is in round 3's public-EMS reserve pool (`r3_emsr753_aoi01`, round-3 DECISIONS §12 at 30580f9), so round 3 keeps it. It was never on either side of a v2 seal (screened `no_scene_in_window`).
6. **Levee breach known only to the day** (`crest_kind = breach_day`): the window is [end of that local day, start of that day + 72 h], so the image is certainly after the breach and never later than 72 h after it.
7. **Older EMS breaches, hand-located with retrieved sources** (same rules as Amendment 3):
   - **Added:** the Mondego, Portugal, 22 Dec 2019 (EMSR417), the second dike collapse, opposite Casal Novo do Rio (ECO/Lusa). The anchor is the Montemor-o-Velho town point, because the breach locality is not in OSM and the town is within a few km of it. The first breach (21 Dec) has no retrieved location or time, so it is not added.
   - **Not added:** Evros, Greece, March 2015 (EMSR122). The retrieved sources say many embankments broke but give no site or date for any one breach.
   - **Not added:** Lazio, January 2021 (EMSR496). No retrieved source reports a breach; the Turano dam was emptied, not breached.
8. **Round 3's sealed reserve** (tag `r3-reserve-seal`, 1aae79a, sealed 2026-11-28) joins the §4 footprints:
   - its 40 waterlogging plains squares and 2 EMSR771 river AOIs (square or bounds in `reserve_r3.json`);
   - New York City as a whole for its 12 FloodNet storm windows, using round 3's own city box (-74.26, 40.49, -73.70, 40.92) from `rain311.py`.
   - All of `r3_ems_candidates.json` stays round-3 territory, whether round 3 refused a unit or not.
   - Rechecked: none of the 265 seal-2.2 reserve components touches any of the 1,538 boxes.
9. **Placeholder days in ASDSO and NPDP** (found by the metadata screen, before any seal 2.3 or label existed): the 1st of a month is about 5 times over-represented (ASDSO 66 against about 14 expected, NPDP 166 against about 27), and NPDP event ids such as `INC_19840000_…` show that an unknown day was stored as the 1st. So in these two sources a lead dated on the 1st of a month is untimed (`no_crest`) and is not screened. A real failure on the 1st is lost; that is the price of never timing a placeholder day. A draft seal 2.3 built before this rule was discarded unpublished, and the screen rows of the affected leads are redone.

## Amendment 6 = owner decisions of 2026-11-28 (before any reserve access; no reserve label exists)

1. **M7 strata** (metadata only; `m7_strata.py`, `m7_strata_2.3.json`):
   - **Primary:** levee and embankment breaches, and reservoir breaches whose reservoir holds at least 3 million m³ (ICOLD's storage criterion for a large dam). Water persists there, so a satellite can still see it. Storage is the largest of ASDSO's Max Storage, NID's Max/NID Storage (matched by NID number) and NPDP's Normal Storage. A component is primary if any of its timed leads is.
   - **Small dams** (below 3 million m³, or storage unknown): scenario-only in the product. A small-dam unit is scored only when its label passes the floor, and it is reported as its own stratum. The M7 verdict for primary units never depends on it.
   - In an M7 component, primary leads are labelled first, then the rest by date (at most 2 per component, DEV and reserve alike).
   - Seal 2.3: reserve has 5 primary and 43 small-dam groups; DEV has 2 primary and 16 small-dam groups. No side changes.
2. **Power is reported, not a gate.** The power report for the joint pass rule is still computed on DEV before any reserve access, and still states what it shows. But the test no longer waits for power ≥ 0.80 (this replaces that sentence of §5). The floor of at least 5 usable units, each with ≥ 50 flooded and ≥ 50 dry cells, stays.
3. **Earth Engine on the free tier:**
   - No quota raise.
   - Wait for resets: after 3 quota or memory errors in a row a worker waits 1 h, and failed units get one retry pass after a further wait.
   - Batch exports are used when a destination exists. This project has no asset root (createAsset is refused, as round 3 found), so until the owner provides one the fallback is off and requests stay interactive.
   - One heavy EE job at a time.
   - Between units, workers pause while round 3 uses EE: a round-3 Python process is running, or another client holds the shared lock.
4. **Order of work:** the corridor stop rule at 20 usable units, then label QA, then the DEV comparison, then the power report.
