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
