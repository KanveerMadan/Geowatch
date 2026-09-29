# GeoWatch — Labelling Guide (item 21)

**Guide version 1.6 — 2026-09-29** (v1.0 decided 2026-09-24; changelog at
the end). This is the hand-labelling
protocol for the item 21 regressors and their validation. It applies at every
site in the item 21 site list (`05_BUILD_MANUAL.md` item 21, "Site list"):

- **Training:** Cape Town, Lima, Karachi, Monrovia. ~~Marrakech optional.~~ *(Removed 2026-09-25, v1.3.)*
- **Validation:** Makoko, Kibera, Rocinha.

**Status: decided, not yet used.** No tile has been labelled. The five
numbers that must be set before labelling starts (§9) are **all set**: four
frozen on 2026-09-29 (v1.5), and the starting tile count (§9.3) set the same
day (v1.6). Any change to this guide bumps
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

- **Polygons**, traced **by hand** on the high-resolution imagery.
- *(v1.6)* **Cluster outlines.** Adjacent roofs separated by gaps narrower
  than ~1 m may be outlined together as one `built` polygon. Gaps wider than
  ~2 m are excluded and labelled by their own surface. Where more than about
  one third of an outlined area would be non-roof, outline smaller groups.
  **Known effect:** small inter-roof gaps are counted as `built`, a
  systematic upward bias in `built` in dense fabric. The same convention
  applies to QC re-traces (§7).
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
  leave-one-city-out (LOCO) stops improving. The starting count is set in
  §9.3.

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
  the method used. *(v1.6)* **An uploader-entered acquisition window (e.g.
  OpenAerialMap `acquisition_start` / `_end`) is not publisher metadata:**
  such tiles use sun-from-shadows too. The window is recorded, and marked
  *corroborated* if the shadow-measured azimuth is within 5° of the sun's
  azimuth at some daylight minute of the window. A tile record with neither is incomplete under §8
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

The change-test method and threshold and the per-site maximum gap were
**frozen on 2026-09-29 (v1.5)**; see §9.1 and §9.2.

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
| Imagery | source, acquisition date — *(v1.4)* **or, where the publisher gives only a period, a date range with the reason recorded** —, **acquisition time — or, where unpublished (v1.2), sun azimuth + elevation measured from the shadows of ≥ 3 buildings in the tile, with the method and building count recorded**, resolution, licence |
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

## 9. Numbers set before labelling starts — FROZEN 2026-09-29 (v1.5), except 3

None of these may be set after labelling begins, and none may be set after
seeing model results. 1, 2, 4 and 5 were **frozen on 2026-09-29**, after a
label-free pilot (`05_BUILD_MANUAL.md` item 21, "§9 pilot" and "Decisions
after Pilot A"). The machine-readable copy is `configs/labelling.yaml`
`open`.

1. **Change test** (§6). *Frozen.*
   - **Scenes:** Sentinel-2 L2A scenes under 20 % cloud intersecting the
     site's box, within the §9.2 window around the imagery date.
   - **Composite:** the existing 6-band median with the SCL cloud mask.
   - **Per 10 m cell, two metrics:** the spectral angle, and the absolute
     difference of the 6-band mean reflectance.
   - **Noise unit per metric per site:** all window scenes are split at
     random into two halves, 20 times with fixed seeds. Each half is
     composited, and the unit is the median over the splits of the 95th
     percentile of the per-cell difference.
   - **Change:** the earliest half of the scenes against the latest half (an
     odd middle scene goes to the earlier half). From each metric, **its
     site-wide median over the eligible cells is subtracted**. A cell is
     changed if **either** de-trended metric exceeds **3 × its noise unit**.
   - **A tile is dropped if more than 10 % of its cells are changed.**
   - Makoko and Lima have 3–4 scenes; there the test is **low-power**.
2. **Maximum date gap, per site** (§6). *Frozen.* **±90 d** around the
   imagery date, with **at least 3 clear scenes**. *(v1.6, replacing "a date
   range takes the worst case across the range")* For an imagery date known
   only as a **range**, the window is the scenes within 90 d of **every** day
   of the range: **[range end − 90 d, range start + 90 d]**. **Rocinha:
   181 d**, an explicit exception (consolidated, slow-changing fabric). Its
   range is longer than 180 d, so the rule gives an empty window; the range
   is extended by 90 d on each side instead. The change test still applies
   there.
3. **Starting tile count** (§3). *Set 2026-09-29 (v1.6).*
   - **Training:** the 8 Stage 1 tiles — per training site, the first tile
     in the sampler order of two strata (`dense_informal` and `formal`; Lima
     `mixed` and `fringe`). Thereafter the Stage 1 stop rule and LOCO decide.
   - **Validation:** 2 tiles per stratum per site, where the stratum has at
     least 2 eligible tiles (Kibera 8, Rocinha 8, Makoko 6). They are split
     into batch 1 / batch 2 (§8) by a seeded split balanced per site per
     stratum: one tile of each site-stratum per batch.
4. **Per-class label-agreement bars** (§7). *Frozen.* 10 m fraction MAE:
   `built` ≤ 5 pp; `impervious_total` ≤ 7.5 pp; `vegetation` ≤ 7.5 pp;
   `water` ≤ 7.5 pp (half the model pass bars where one exists). Polygon IoU
   is a diagnostic, never a bar.
5. **`unsure` and `shadow_full` in a cell's fractions.** *Frozen.* Both are
   excluded from the cell's denominator. A cell is scored when its excluded
   share is **≤ 0.25**, and is not scored above that.

---

## Changelog

- **v1.6 — 2026-09-29.**
  - §2: tracing is by hand, with the **cluster-outline** convention and its
    known upward `built` bias.
  - §5: uploader-entered acquisition windows are not publisher metadata;
    sun-from-shadows, with the window recorded for corroboration.
  - §9.2: the **date-range window** is [range end − 90 d, range start +
    90 d], replacing the worst-case rule. Rocinha keeps its 181 d exception.
  - §9.3: the **starting tile count** is set.

  No tile has been labelled (the practice tiles are never scored), so the §7
  recheck is empty.

- **v1.5 — 2026-09-29.** §9: numbers 1 (change test), 2 (maximum date gap),
  4 (agreement bars) and 5 (maximum excluded share 0.25) are **frozen**;
  §6 and the status line point to them. §9.3 (starting tile count) was not
  part of the freeze and stays open. **No tile has been labelled** (the two
  practice tiles are never scored), so the §7 recheck has nothing to
  recheck.

- **v1.4 — 2026-09-25.** §8: the acquisition date may be a **date range
  with a recorded reason** where the publisher gives only a period (Rio IPP
  `Mosaico_2024`: "1st half 2024"). **No tile has been labelled, so the §7
  recheck has nothing to recheck.**
- **v1.3 — 2026-09-25.** Site list only: Marrakech removed (Open Buildings v3 has zero coverage in Morocco, and using Microsoft footprints at one site would mix `built` sources across the training set). No
  labelling rule changed. **No tile has been labelled, so the §7 recheck has
  nothing to recheck.**
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
