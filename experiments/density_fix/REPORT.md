# Item 23 density metrics: fix and re-test (2026-11-20)

Pre-registration: `PREREGISTRATION_V2.md`, commit c29ab06, pushed
2026-11-19T19:50:55Z, before any score below was computed. Scored with
`vector/density.py` sha256 39edc9b2…6c82, the registered hash
(`result_v2.json`). DEV AOIs only: chandigarh_central (formal), dharavi
(high-density built-up), both Open Buildings v3.

## Result: still FAIL. No label changes; density metrics stay `experimental`.

| test | holds | reversed | result |
|---|---:|---:|---|
| v1 (unchanged, 2026-10-27 bars) | 1 | 0 | **FAIL** (reproduced exactly) |
| S1: v1 on built masses (descriptive) | 1 | 3 | FAIL |
| v2 (registered 2026-11-20) | 2 | 1 | **FAIL** |

### v2

| prediction | formal | informal | statistic | bar | outcome |
|---|---:|---:|---:|---:|---|
| contiguity: area-weighted mean mass (m²) | 1,481 | 19,417 | 13.1× | ≥ 2.0× | **holds** |
| built-over share of the AOI | 0.207 | 0.247 | 1.19× | ≥ 1.5× | short of bar |
| gap between masses, median (m) | 2.28 | 2.57 | 0.88× | ≥ 1.5× | **reversed** |
| orthogonality φ | 0.879 | 0.047 | +0.83 | ≥ +0.10 | holds |

### S1: would merging fragments alone have rescued v1? No.

Masses instead of polygons reverse three of v1's predictions: median mass
101 vs 174 m², masses/km² 540 vs 430, median gap 2.3 vs 2.6 m.

## What this shows

1. **Why v1 failed (diagnosed).** On Open Buildings, ~72–74% of polygons
   touch another one in both AOIs: formal houses are cut into rooftop
   fragments, informal dwellings share walls. Per-polygon size, count and
   spacing measure segmentation, not fabric. This is a property of the
   source, so no threshold on those metrics will fix it.
2. **Contiguity is the one footprint signal that survives** (13× on these
   AOIs). But v2 was designed after seeing these two AOIs, so this is not
   evidence (stated in advance).
3. **Two of v2's predictions failed.** Likely reasons, *not measured here*
   (each would need its own check before anyone relies on it):
   - *Built share* is only 1.19× higher in the Dharavi box. The box is
     measured whole, and probably includes creek water, mangrove, rail land
     and open ground as well as dense fabric; Chandigarh's sectors are
     evenly built. A box-level share cannot say how dense the built part is.
   - *Gaps*: the median gap between masses may be set by the many small
     masses (sheds, annexes, fragments that stayed separate), which sit 2–3 m
     from a neighbour in both places; formal setbacks and streets would then
     show in the upper gaps, not the median.

## What was not done, on purpose

- No bar was moved and no prediction was re-scored under another name.
- No further variants were tried on these AOIs: a third design fitted to
  the same two boxes would be worth even less than v2.

## Next step (Kanveer's call)

A held-out pair, frozen before scoring (PREREGISTRATION_V2.md §6), testing
contiguity alone as the single pre-stated prediction, alongside φ. If the
product needs a "high-density built-up area" indicator before then, the
honest option is to show contiguity and φ as `experimental` with this
report linked, and not to claim they separate fabric types.
