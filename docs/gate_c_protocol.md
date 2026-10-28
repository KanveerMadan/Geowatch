# Gate C — real-planner study protocol, written and not run (item 64)

> **Status: NOT RUN. Blocked by access, not by design choice.**
> The users this protocol needs are municipal planners, disaster-management
> staff and NGO staff working in informal settlements. Reaching them takes
> institutional access and lead time this solo project does not have
> (`05_BUILD_MANUAL.md` Decision 16). The protocol is filed so the gap is
> named and can be closed later. It is not a placeholder for work done.

**Relation to Gate C's closure.** Gate C is **closed** by structured
advisor/faculty review against `03_EVIDENCE.md` §D.7's five reporting
requirements (Decision 17; the write-up is item 65). That review shows the
work is accurate and well reasoned. **It does not show that a planner would
find the outputs useful.** This protocol is the study that would, and
Decision 17 says outright that advisor review does not satisfy it.

**Code state this protocol is coupled to.** `exposure/compute.py:27`
`GATE_C_STATUS = "waived_pending_real_user_validation"`, pinned by
`tests/test_gate_c_waiver.py:104`. Under `archive/PROJECT_GATES.md` §"Gate C
waiver", the status may change only when a real user has reviewed the
output, and the gates file and the constant change in the same commit. Running
this protocol is the only path to that change described in the repository.

**Numbers in this document** are design choices, marked *(design)*. None is
a measured or derived figure.

---

## 0. Precondition: what may be shown

Run this only against outputs that have **passed the validation-first
mandate** (`05_BUILD_MANUAL.md`, Part 4 banner, 2026-09-24). Showing a
planner unvalidated outputs tests whether plausible-looking numbers persuade
people. It does not test usefulness, and it risks the misreading this study
is meant to measure.

Not to be shown: anything from the retired 7-class pipeline (`08_STATE.md`
§RETIRED), including the legacy results the UI still serves under the
"retired, not validated" banner.

The output set is whatever has passed validation when the study runs. It is
deliberately not enumerated here, because the land-classification outputs
depend on item 21, which is unsettled.

## 1. Recruitment

**Target user classes**, from Decision 16's reasoning about who the
flood/planning framing needs:

| class | example role | why |
|---|---|---|
| U1 municipal planning | ward-level planning or storm-water engineering staff | the AOI-total vs ward-level granularity question (§3, M5) is theirs |
| U2 disaster management | city or state disaster-management authority staff | consumers of susceptibility and exposure screening |
| U3 civil society | NGO staff working in informal settlements | most exposed to the misreading in M2, and to harms from a wrong map |

**Inclusion.** The participant uses spatial data in their current role for
planning, flood response or settlement work, and has an AOI in their own
jurisdiction that the pipeline can run.

**Exclusion.** Anyone who has worked on GeoWatch, or anyone who took part in
the Gate C advisor review (item 65). Exposure to the project's framing
contaminates the "cold" step.

**Size.** 3–5 per class *(design)*. This is a qualitative usability study,
and results are reported per participant (§4). The sample is far too small
for inferential statistics, and none will be computed.

**Ethics and consent.** Institutional ethics review before any contact.
Written consent. Record role and organisation type only, no names in any
artifact. Participants may withdraw their data at any time before
publication. This is a prerequisite, not part of the protocol's design
freedom.

**Access path (why this is blocked).** Each class needs an institutional
introduction: a faculty contact, an MoU, or an NGO partner. None exists
today, and setting one up is outside this project's timeline. **That is the
whole reason the protocol is unrun.**

## 2. Task

One session per participant, 60 minutes *(design)*, on an AOI from their own
jurisdiction, run by one facilitator from a fixed script. The four stages
follow the shape Decision 17 specifies. **Stage order is fixed and stages 1–3
come before any caveat is shown.**

1. **Cold read** (no explanation, no limitations panel). Show the output.
   *"What does this tell you about this area?"*
2. **Interpretation.** For each output shown, the participant states in
   their own words what the number or map means.
3. **Action.** *"What, if anything, would you do with this?"* Follow-up:
   *"What would you need to see before acting?"*
4. **Caveats, unprompted then prompted.** First *"What should someone be
   careful about with this?"* Then reveal the output's own limitations text,
   ask whether it changes their answer to stage 3, and ask the three
   questions the original waiver left open (`archive/PROJECT_GATES.md`):
   granularity, whether "estimated population exposed" could be read as
   "confirmed people affected", and whether 2020 population data is
   acceptable.

Sessions are audio-recorded with consent, or notes are taken verbatim
otherwise. Coding uses the answer key in §3, which is written and frozen
before the first session.

## 3. Metrics

**The answer key is frozen before recruitment begins.** It holds the correct
reading of each output, the list of key caveats, and the list of critical
misreadings. This is the same pre-registration discipline item 21 applies to
its validation criteria.

| id | metric | measured at | scoring |
|---|---|---|---|
| **M1** | Unprompted caveat recall | stages 1–4a | count of key caveats raised before any caveat is shown, out of the frozen list |
| **M2** | Critical misreading | stages 1–3 | per participant per output: did they state a screening estimate as confirmed fact? (binary, against the frozen list) |
| **M3** | Interpretation accuracy | stage 2 | per output: correct / partially correct / wrong, against the answer key |
| **M4** | Action fit | stage 3 | coded: no action / seek more information / act. Separately: is the stated action within what the output supports? |
| **M5** | Granularity fit | stage 4 | preferred unit (AOI total, ward, sub-ward) and whether the current unit could be used at all |
| **M6** | Data-age acceptability | stage 4 | whether 2020 population is acceptable for their use, with the participant's reason |
| **M7** | Caveat effect | stage 4b | did revealing the limitations text change the stage-3 action? (binary, with direction) |

**Key caveats for M1 (seed list; finalise when the output set is fixed).**

- Population is a modelled 2020 estimate.
- Two population models disagree by an AOI-dependent amount
  (`docs/population_range.md`).
- Susceptibility layers share inputs, so their agreement is not independent
  evidence (`docs/susceptibility_dag.md`).
- Outputs are screening-grade, not validated for decisions.

**Reading the results.** M2 is the safety metric. One critical misreading
that the limitations text does not correct (M7 = no change) is a
**reportable failure** for that output, whatever the other metrics show
*(design)*. Usefulness claims rest on M3 and M4 together. An output that is
understood but never actionable (M4 = no action, across participants) is
reported as **not useful at this granularity**, not as a pass.

## 4. Reporting

- **Per participant**, by class, with no pooled accuracy figure across
  classes.
- **Every critical misreading verbatim** (M2), with the output it attached
  to.
- **Outcomes, as reported**: PASSED (with date and reviewer context) only if
  no output has an uncorrected critical misreading and at least one class
  finds the outputs actionable. Otherwise the waiver stands with the study's
  findings attached. The status change, if any, follows the coupling rule
  above.
- **Until run**, every description of GeoWatch outputs carries Decision 16's
  framing: *"here is why this should be trusted"*, never *"a planner
  validated this"*.
