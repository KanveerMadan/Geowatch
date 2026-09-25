# GeoWatch — Labelling Guide (item 21)

**Guide version 1.2 — 2026-09-25** (v1.0 decided 2026-09-24; changelog at
the end). This is the hand-labelling
protocol for the item 21 regressors and their validation. It applies at every
site in the item 21 site list (`05_BUILD_MANUAL.md` item 21, "Site list"):

- **Training:** Cape Town, Lima, Karachi, Monrovia; Marrakech optional.
- **Validation:** Makoko, Kibera, Rocinha.

**Status: decided, not yet used.** No tile has been labelled. Five numbers must
be set before labelling starts — see §9, *Open*. Any change to this guide bumps
the version and triggers the recheck in §7.

Related decisions: taxonomy (Decision 11), shadow rule (Decision 11 and
Decision 14), regressor training and firewall (item 21).

---

## 1. Label set

| Label | Meaning |
|---|---|
| `built` | Any roof, of any material |
| `paved` | Sealed unroofed surface: asphalt, concrete, tiles, laid stone |
| `bare` | Unsealed ground, **including compacted ground** |
| `vegetation` | |
| `water` | |
| `mixed_water_vegetation` | Wetlands, mangroves, mudflats / tidal zones, water hyacinth |
| `snow_ice` | Permanent snow and ice |
| `solar` | ~~Solar panels / arrays~~ **Ground-mounted solar arrays only** *(v1.1)*. Rooftop panels are `built` + the rooftop-solar flag |
| `shadow_full` | Shadow so deep the underlying surface **cannot** be identified |
| `shadow_partial` | **Not a class of its own.** Labelled as the underlying class **plus a partial-shadow flag**. Use it when the surface under the shadow *can* be identified |
| `unsure` | Genuinely ambiguous. **Excluded from scoring. Never guessed** |

**Hand-labelled `built` is the independent check on footprint-derived
`built`.** The pipeline takes `built` from vector footprints, not from spectra.
The hand label exists so footprint `built` can be measured against something
that does not share its source.

## 2. Label form

- **Polygons**, traced on the high-resolution imagery.
- **Fractions per 10 m Sentinel-2 cell are computed from polygon areas —
  never eyeballed.** A labeller never types a percentage.
- The same polygons are also rasterised to a **pixel-level map** to support
  the IoU check.

## 3. Sampling

- Each site is split into **fixed ~200 m × 200 m tiles**.
- Tiles are chosen **randomly, stratified by fabric type**: dense informal,
  formal, mixed, fringe.
- **Every pixel in a chosen tile is labelled.** No partial tiles, and no
  picking the easy parts of a tile.
- **Tile count follows item 21's stopping rule:** keep adding tiles until
  leave-one-city-out (LOCO) stops improving. The starting count is open (§9).

## 4. Hard cases

**Governing principle: label the top-most surface visible from directly
above.**

| Case | Label |
|---|---|
| Sealed surface: asphalt, concrete, tiles, laid stone | `paved` |
| Unsealed ground, **even if compacted**: dirt roads, gravel, compacted yards, dirt parking | `bare` |
| Concrete-lined drain, dry | `paved` |
| Earth channel, dry | `bare` |
| Any channel with water in it | `water` |
| Construction site | **its current surface**, never its intended use |
| Any roof, any material | `built` |
| Solar panels on a roof *(v1.1)* | `built`, **plus the rooftop-solar flag** — never `solar` |
| Ground-mounted solar array *(v1.1)* | `solar` |
| Car or other vehicle | **the surface beneath it** |
| Genuinely ambiguous | `unsure` |

The sealed/unsealed line is the `paved`/`bare` definition in Decision 11 as
amended 2026-09-24. Compacted earth is `bare`, not `paved`.

## 5. Shadow

- **`shadow_full`:** the underlying surface is **not identifiable**.
- **`shadow_partial`:** the underlying surface **is identifiable**. Label it
  as that surface, plus the partial-shadow flag.
- **When in doubt, `shadow_full`.**
- **Record the image acquisition time** (time of day, not only date) for every
  tile. Shadow geometry depends on it. *(v1.2)* **Where the publisher gives
  no acquisition time**, record instead the **sun azimuth and elevation
  measured from the shadows of at least 3 buildings in the tile**, and record
  the method used. A tile record with neither is incomplete under §8
  (every field mandatory).

**High-resolution shadow labels are a separate shadow-handling check, NOT a
pixel-level target for Sentinel-2.** The high-resolution image and the
Sentinel-2 composite were taken under different illumination, so the same
place is shadowed differently in each. The labels test the shadow rule
(Decision 11 / Decision 14):

- `shadow_full` tests the occlusion route.
- `shadow_partial` tests whether the regressors' *learned* robustness holds
  on partially shadowed pixels.

They must never be scored as though Sentinel-2 should reproduce the same
shadow pixels.

Partially shadowed pixels appear in **training** labels as well as
validation labels. The regressors can only learn robustness to what they
have seen.

## 6. Time gap

- **Label only what the high-resolution image shows.** Never "correct" it from
  newer knowledge, other imagery, or Street View.
- The Sentinel-2 composite is taken **as close in time as possible** to the
  high-resolution image. Makoko needs a ~6-month window (weak Sentinel-2
  overlap; see the site list).
- **Per-site maximum date gap:**
  - Within the maximum: the tile is kept **unless the pre-defined change test
    detects meaningful change**. If it does, the tile is dropped.
  - Beyond the maximum: the tile is **dropped regardless**.
- **Dropped tiles are never relabelled.** Dropping is final, so the change
  test cannot be used to shop for tiles.

Both the change-test method and threshold and the per-site maximum gap are
open (§9) and must be fixed before the first tile is labelled.

## 7. Quality control

- **~15% of tiles are blind re-labelled.** If the same labeller does it, the
  re-label waits **at least one week**.
- **Per-class agreement is measured at two levels:** polygon (IoU) and
  **10 m fraction** (the quantity the model is actually scored on).
- **The per-class agreement bar is set BEFORE model evaluation.** It is never
  set after seeing model results.
- **Label-limited classes:** a class whose label agreement is worse than the
  model's pass bar is reported as label-limited. A model cannot be held to
  better agreement than its labels have with themselves.
- **Drift check:** an early tile is re-labelled near the end of the campaign.
- **Guide changes are versioned.** Every tile labelled under an affected rule
  is rechecked under the new version.

## 8. Metadata and sealing

**Per-tile record, every field mandatory:**

| Field | |
|---|---|
| Site, tile ID | |
| Imagery | source, acquisition date, **acquisition time — or, where unpublished (v1.2), sun azimuth + elevation measured from the shadows of ≥ 3 buildings in the tile, with the method and building count recorded**, resolution, licence |
| Sentinel-2 composite window | |
| Date gap + change-test result | |
| Labeller, labelling date | |
| Guide version | |
| % `unsure`, % `shadow_full` | |
| QC status | |

**Labels are never overwritten.** A correction creates a new version with its
reason recorded. The old version is kept.

**Validation labels (Makoko, Kibera, Rocinha) are stored separately and
sealed.** They are **never** used to modify thresholds, architecture,
preprocessing, or labelling rules. This is the firewall from item 21 applied
to the labels themselves.

**Validation tiles are split into two sealed batches:**

- **Batch 1** — the first validation.
- **Batch 2** — confirmation of batch 1, or the **fresh test after any
  redesign**. Once batch 1 has been seen, only batch 2 is untouched evidence.

## 9. Open — numbers to set before labelling starts

None of these may be set after labelling begins, and none may be set after
seeing model results.

1. **Change-test method and threshold** (§6).
2. **Maximum date gap, per site** (§6).
3. **Starting tile count** (§3). After the start, LOCO decides.
4. **Per-class label-agreement bars** (§7).
5. *(Added when this guide was written, not part of the 2026-09-24
   decision.)* **How a 10 m cell's fractions treat `unsure` and `shadow_full`
   area.** Presumably both are excluded from that cell's denominator. A
   maximum excluded share per cell, above which the cell is not scored, still
   needs a number.

---

## Changelog

- **v1.2 — 2026-09-25.** §5 / §8: where no acquisition time is published,
  sun azimuth and elevation measured from the shadows of ≥ 3 buildings in
  the tile stand in for it, with the method recorded (Cape Town's image
  service and Rio IPP's mosaic publish no time; item 21 measurement A).
  **No tile has been labelled, so the §7 recheck has nothing to recheck.**
- **v1.1 — 2026-09-25.** `solar` is ground-mounted arrays only; rooftop
  panels are labelled `built` with a rooftop-solar flag (item 21, Phase A
  rulings, second round, 3–4). **No tile has been labelled under v1.0, so the
  §7 recheck of tiles labelled under an affected rule has nothing to
  recheck.**
- **v1.0 — 2026-09-24.** First version.
