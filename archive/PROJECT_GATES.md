# GeoWatch Copilot — Phase 10B Gate Status

Last updated: 2026-08-01

Phase 10B (vulnerability + risk integration) requires ALL FIVE gates below
to be satisfied before implementation begins. Do not start Phase 10B code
until every gate below shows PASSED or an explicit, dated WAIVER with a
stated reason.

| Gate | Status | Date | Notes |
|---|---|---|---|
| A. Exposure correctness | PASSED | 2026-08-01 | WorldPop scale bug found+fixed+re-verified on 2 AOIs. See dharavi_phase10a_final / delhi_phase10a_final runs. |
| B. Live-run gate (incl. real event) | PASSED | 2026-08-01 | 4 static runs + 1 real event-mode run (dharavi_gate_b, using real July-2026 monsoon rainfall data, 1506.8mm/month, independently sourced from Phase 9 CHIRPS/GPM data). |
| C. Product-value gate | WAIVED | 2026-08-01 | No real user (planner/NGO/researcher) has reviewed exposure output. Waived due to pre-launch status -- no users exist yet. REVISIT BEFORE treating exposure output as validated for real decision-support use. See waiver note below. |
| D. Vulnerability-source feasibility | NOT STARTED | -- | -- |
| E. Methodology definition | NOT STARTED | -- | Blocked on D. |

## Gate C waiver -- full reasoning

Gate C could not be honestly satisfied: this is a pre-launch, solo-built
project with no real users yet. Exposure output (Phase 10A) has been
reviewed for internal technical correctness (live-verified data sources,
consistent numbers across evidence layers, honest limitation labeling) but
has NOT been validated by anyone outside this project for:
- whether the output shape (AOI-total exposure per evidence layer) is
  actually the right granularity for real planning use (e.g. vs. ward-level)
- whether limitation text is sufficient to prevent real misreading of
  "estimated population exposed" as "confirmed people affected"
- whether 2020 population data is an acceptable gap for real use cases

**Action required when a real user becomes available:** show them exposure
output directly, ask whether it's useful and whether they understand the
caveats without prompting. Update this file's Gate C row to PASSED (with
date and reviewer context), and update `GATE_C_STATUS` in
`exposure/compute.py` from `"waived_pending_real_user_validation"` to
`"passed"` in the same commit/session -- these two must never drift out of
sync.

**Until Gate C is actually passed:** exposure output must continue to be
labeled "screening/experimental" everywhere it's surfaced (frontend,
result.json, any report) and must never be presented as validated for
real decision-making, regardless of how many additional phases are built
on top of it. Any future phase (10B risk, a frontend panel, a generated
report) that consumes exposure output must propagate
`product_validation_status` forward into its own output -- see
`exposure/compute.py`'s module docstring and `risk/compute.py`'s intended
future behavior.

## How to use this file

Paste this file's table at the start of any future Phase 10B session. Do
not begin Phase 10B implementation code until gates D and E are resolved
(PASSED, with real written feasibility/methodology content -- not just a
status flip). Gate C's waiver is permanent-until-explicitly-updated, not
a technicality that expires on its own.