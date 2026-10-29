# Flood validation round 3 — pre-registration (item 26 follow-ups)

**Written 2026-10-29, and committed before any round-3 score, box or
cell count was computed.** Its SHA256 is recorded in the round-3 result
file. `harness_round3.py` implements this text and is committed with it.
Rounds 1 and 2 (`PREREGISTRATION.md`, `PREREGISTRATION_ROUND2.md` and their
result files) are unchanged, and they stay the record of those rounds.

**Modules:** pluvial, waterlogging, flash flood. Fluvial (validated) and
coastal (failed) are not in this round.

## Why a round 3

In round 2 these three modules were **not-run**: each had only one held-out
event with ≥ 50 flooded cells. The boxes were 4 km squares centred on a
town-centre coordinate chosen without looking at the flood polygons, and
most of them missed the mapped flooding. Hai Phong, Belize City, Volos and
Choloma had 0 flooded cells, Thai Binh 7 (C67). Choloma's centre lay outside
its product's extent (C66). Round 3 changes **one thing: where the box
goes.** It now goes where the reference product mapped the flood.

## What was looked at before this was written, and nothing else

- Round 2's result file. It includes the round-2 held-out AUCs of the three
  events that qualified then: **Milagro 0.350 (pluvial), Kastelli 0.881
  (flash flood), Nam Dinh 0.472 (waterlogging).** Those scores are known.
  See "Events already scored" below.
- The footprint of GFD event 3280: its image bounds (105.1–115.9° E,
  8.9–5.7° S, all of Java) and its total flooded area at 1 km. That is
  reference availability only.

No round-3 box, centre, cell count, input value or score was computed.

## What does NOT change (fixed at master `cf3f5a3`)

- **Methods, components, ceilings and weights.** Nothing is tuned in round
  3. Flash flood and waterlogging use the weights round 2 chose on its
  tuning events (`configs/flash_flood_constants.py`,
  `configs/waterlogging_constants.py`, equal to round 2's `weights_used`).
  Pluvial uses item 26 tasks 1–4 as built. No tuning event is run.
- **The metric:** ROC AUC of the module score, flooded vs dry 30 m cells,
  ties count one half (`harness.auc`), computed **within each event**.
- **The bar:** the **unweighted mean of the per-event AUCs over qualifying
  held-out events**. **AUC ≥ 0.70 → validated; < 0.70 → failed.** An event
  qualifies with **≥ 50 flooded and ≥ 50 dry** evaluation cells. A module
  needs **≥ 2 qualifying held-out events**, or it is **not-run**.
- **References:** the same Copernicus EMS DEL products as round 2.
  Flooded = `Flooded area` ∪ `Flood trace` polygons. A 30 m cell is flooded
  if ≥ half its area is covered. Dry = the rest of the product extent.
- **Valid cell:** inside the box and the product extent, not JRC permanent
  water (occurrence ≥ 80 %), with a finite score.
- **Grid:** per event, a 30 m UTM grid covering the box (`utm_grid`).
  Pluvial uses item 19's layer grid for the box, as in round 2.
- **Inputs:** fetched exactly as in round 2 (`build_event` in
  `harness_round2.py`). Pluvial keeps its round-2 vegetation windows.

## The box-placement rule (the one change)

For each event, using **only the reference product** (its extent and its
flooded polygons, no score and no module input):

1. **Flood extent F** = the union of the product's `Flooded area` and
   `Flood trace` polygons, intersected with the product extent.
2. **Centre** = the area-weighted centroid of F. It is computed in the UTM
   zone of F's lon/lat centroid. If that centroid does not lie in F (a ring
   or several separate patches), the centre is **the nearest point of F to
   it**. The centre therefore always lies on mapped flood.
3. **Box** = a **4 km × 4 km** square centred there (`square_bbox`, the
   same size as round 2), fixed for every event.
4. **Qualification:** if the box has < 50 flooded or < 50 dry valid cells,
   the event does not qualify and is named. **No other placement is tried,
   and no box is moved, resized or replaced after any count or score is
   seen.** An event whose product has no flooded polygon is dropped and
   named.

A 4 km box centred on mapped flood will normally hold both flooded and dry
cells. Where the flood fills the whole box (no dry cells), or is a thin
trace (too few flooded cells), the event fails qualification. That is
reported, not repaired.

## Events

The held-out EMS events of round 2 for these modules, each re-boxed by the
rule. Round 2's tuning events are not used.

| Module | Event | Reference (round 2's product) | Veg window (pluvial) |
|---|---|---|---|
| pluvial | hai_phong, Typhoon Yagi 2024-09-07 | EMSR754 AOI05 DEL m0 | 2024-11-01 → 2025-01-31 |
| pluvial | milagro, Ecuador rains 2025-02-26 | EMSR796 AOI06 DEL m0 | 2024-07-01 → 2024-09-30 |
| pluvial | belize_city, Tropical Storm Sara 2024-11-15 | EMSR777 AOI01 DEL m0 | 2024-03-01 → 2024-05-31 |
| flash flood | volos, Storm Daniel 2023-09-05 | EMSR692 AOI01 DEL m3 | — |
| flash flood | kastelli, Crete 2026-10-01 | EMSR933 AOI01 DEL m1 | — |
| flash flood | choloma, Tropical Storm Sara 2024-11-16 | EMSR778 AOI10 DEL m0 | — |
| waterlogging | thai_binh, Yagi 2024-09-09 | EMSR754 AOI06 DEL m0 | — |
| waterlogging | nam_dinh, Yagi 2024-09-09 | EMSR754 AOI07 DEL m0 | — |

**Excluded: waterlogging `jakarta_gfd_3280`.** GFD event 3280's mapped
extent covers all of Java (105.1–115.9° E). A box centred on it would land
wherever MODIS saw the most water on the island, not on the Jakarta event
the round-2 entry stood for, and its 240 m blocks give only 256 evaluation
cells per 4 km box. Waterlogging therefore has two events, and **both must
qualify** for a verdict.

### Events already scored

Milagro, Kastelli and Nam Dinh were scored in round 2 on different boxes.
Those AUCs are known, so these events are not unseen. Nothing round 3 can
change was set from them: weights, ceilings and components are frozen, and
the box rule is mechanical and identical for every event. They count toward
the verdict like the others. As a **diagnostic only** (no verdict), the
result also reports each module's mean AUC over its qualifying events that
round 2 never scored. That shows how much the verdict leans on the known
events.

Pooled held-out AUC (all qualifying held-out cells together) is also
reported, **as a diagnostic only**, as in round 2.

## Weaknesses stated in advance

- Centring on mapped flood makes flooded cells common in the box, so the
  base rate differs from a random urban box. AUC does not depend on the base
  rate, but the dry cells are now the flood's near surroundings, which is a
  harder and fairer comparison than distant high ground.
- The events are round 2's: the same storms. The Yagi events (Hai Phong,
  Thai Binh, Nam Dinh) share one typhoon, and two of them are waterlogging's
  only events.
- Late images undercount (Thai Binh +11 days). SAR misses flooding among
  dense buildings (double bounce).
- Pluvial's inputs and waterlogging's `built` input are placeholders.
  Waterlogging weights `built` at 0.
- IMERG and CHIRPS are near-constant over a 4 km box, so within-event AUC
  cannot see flash flood's rainfall component.

A fail is still a fail against the bar.

## Labels

- **validated** (held-out mean ≥ 0.70 on ≥ 2 qualifying events): the
  module's label is `validated` only through the C70 rule. The exact
  configuration it ran (method, weights, ceilings, input sources and
  methods) and its scope (these events, their regions, input versions) are
  recorded in `analysis/contract.VALIDATED_CONFIGS` in the same commit as
  the result. Any other configuration falls back to the worst-of-inputs
  rule.
- **failed:** the module's contract label becomes `failed`.
- **not-run:** round 3 adds nothing. The contract label stays exactly what
  it is now: pluvial `failed` (round 1, same method), flash flood and
  waterlogging `experimental` (a real method, not yet validated: the decided
  meaning, C69).
