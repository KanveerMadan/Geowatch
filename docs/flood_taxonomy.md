# Flood taxonomy — the eleven flood types

Recorded 2026-10-30 (flood round 4, `build/flood4`). Every flood type has an
id, a status and the round it belongs to. Each type also has a result
label in `analysis/contract.FLOOD_TAXONOMY`, `not_computed` included, so the
pipeline cannot drop a type without saying so.

| Id | Type | Pipeline module | Status | Round |
|---|---|---|---|---|
| **M1** | Fluvial (river overflow) | `fluvial` | **validated**, scoped (round 2: Hanoi, Kolonnawa); round 4 **failed** on Bihar, Assam and Sindh (0.537), so the scope is narrowed (C78) | round 4, method unchanged |
| **M2** | Pluvial (surface water from rain on the spot) | `pluvial` | **failed** round 4 (0.524): depression ("bluespot") detection with fill-and-spill; re-test when item 21's `impervious_total` exists | round 4 |
| **M3** | Waterlogging (persistent standing water, poor drainage) | `waterlogging` | **failed** round 4 (0.613): historical standing-water persistence, clay, low relief, backwater | round 4 |
| **M4** | Flash flood (short, intense rain on steep, fast catchments) | `flash_flood` | **failed** round 4 (0.640): short-duration intensity, catchment response time, stream power on channels and valley floors | round 4 |
| **M5** | Coastal (surge, tide) | `coastal` | `failed` (round 2, pooled AUC 0.646); a new method is planned | round 5 |
| **M6** | Debris flow / glacial lake outburst | `debris_flow_glof` | not built | round 5 |
| **M7** | Embankment / dam breach | `embankment_dam_breach` | not built | round 5 |
| **M8** | Snowmelt / ice jam | `snowmelt_ice_jam` | not built | round 5 |
| **M9** | Compound (two or more of the above at once) | `compound` | not built; needs M1–M3 first | round 6 |
| **M10** | Groundwater (rising water table) | `groundwater` | **not measurable** with the project's inputs: labelled, not tested | — |
| **M11** | Tsunami | `tsunami` | **out of scope** | — |

## What the labels mean here

- A **built** type (M1–M5) takes its label from the module, its pinned
  Tier 2 verdict and its inputs (`analysis.contract.hazard_label`), as
  before. M5 keeps its round-2 method and verdict until round 5 replaces it.
- An **unbuilt** type (M6–M9) is reported as an output with no value,
  status `not_computed` and label `placeholder`, the same treatment as the
  other `not_computed` outputs (e.g. `impervious_total`). The reason says
  which round builds it.
- **M10 groundwater** is `not_computed` for good unless an input appears:
  the project has no water-table observation, so a score could not be
  tested against a reference. It is named so a reader sees it is missing on
  purpose.
- **M11 tsunami** is `not_applicable`: out of scope, never computed.

## Validation rule for every round

The Tier 2 rule from rounds 2 and 3 applies unchanged: per-event ROC AUC of
the score, flooded vs dry 30 m cells, against an independent reference
(Copernicus EMS, an official map, or Sentinel-1 with the method stated);
the 4 km box goes on the mapped flood; ≥ 50 flooded and ≥ 50 dry cells, or
the event is not-run; **mean within-event AUC ≥ 0.70 over ≥ 2 qualifying
held-out events → validated**. Parameters are fitted only on named tuning
events that are never test events. Each round is pre-registered and
committed before any score is computed.

Round records: `experiments/flood_validation/PREREGISTRATION*.md` and their
`result_*.json` files.
