# Item 23 density metrics: diagnosis, fix, and separation test v2 (pre-registration)

Written 2026-11-20, committed and pushed **before** v2 or side analysis S1
was computed on any AOI. `vector/density.py` at registration:
sha256 `39edc9b2060ae44cb6557ac48073486f136196692fb62ae8696b260c2b386c82` (`result_v2.json` records the hash it ran with; they must
match).

## 1. What failed

Item 23's pre-registered test (`SEPARATION_TEST`, 2026-10-27) failed on
2026-10-28: 1 of 4 predictions held (orthogonality), 0 reversed. Reproduced
exactly on 2026-11-20 from freshly built layers
(`experiments/density_fix/baseline_metrics.json`): median footprint 50.4 vs
46.1 m² (1.09×, bar 2.0×), density 2,101 vs 2,761 /km² (1.31×, bar 2.0×),
spacing 7.6 vs 6.7 m (1.13×, bar 1.5×), φ 0.879 vs 0.047 (+0.83, holds).

## 2. Diagnosis

The manual (item 23, 2026-10-28) found Open Buildings cutting Chandigarh's
plotted houses into rooftop fragments (21 of 30 sampled polygons). The
2026-11-20 diagnosis (`diagnose.py`, `diagnosis.json`) adds: **the same is
true of the informal AOI, for a different reason.** Share of polygons whose
boundary is within d of another polygon's:

| d | Chandigarh (formal) | Dharavi (informal) |
|---|---:|---:|
| 0 (touching) | 72% | 74% |
| 1 m | 87% | 91% |

Formal houses are cut into touching fragments; informal dwellings share
walls. Per-polygon size, density and centroid spacing therefore measure the
segmentation in both places, and the v1 footprint predictions cannot work on
this source. Merging touching polygons does not rescue them either: merged at
d = 0 the median mass is 56 m² formal vs 79 m² informal, the reverse of
v1's first prediction.

What does differ is **contiguity**. Merged at 1 m, the largest built mass is
7,396 m² (80 polygons) in Chandigarh and 144,066 m² (2,315 polygons) in
Dharavi: formal fabric breaks into plot-sized masses at setbacks and
streets; informal fabric runs on.

## 3. The fix (code, `vector/density.py`)

- `MASS_GAP_M = 1.0`: footprints within 1 m are one built mass. Reason,
  fixed before scoring and not tuned: Open Buildings traces ~50 cm imagery,
  so gaps under 1 m are walls or segmentation seams, not passages.
- New block `built_mass`: number of masses, area-weighted mean mass area,
  median mass area, largest mass's share of built area, median edge-to-edge
  gap to the nearest other mass, footprints per mass. Tested to be
  unchanged when a building is cut into fragments.
- `SEPARATION_TEST` (v1) is untouched: same bars, and its FAIL stands.

## 4. Separation test v2 (`SEPARATION_TEST_V2`)

Same AOIs (chandigarh_central formal, dharavi informal), same footprint
source (Open Buildings v3), no spectral input, same rule: **pass = at least
3 of 4 hold and none reversed.**

| # | prediction | statistic | bar |
|---|---|---|---:|
| 1 | more contiguous informal fabric | area-weighted mean mass, informal / formal | ≥ 2.0 |
| 2 | more of the informal AOI built over | built_area_share, informal / formal | ≥ 1.5 |
| 3 | wider gaps between formal masses | median edge-to-edge gap, formal / informal | ≥ 1.5 |
| 4 | more orthogonal formal network | φ, formal − informal | ≥ +0.10 |

**Caveat, recorded before scoring.** v2 was designed after diagnosing these
two AOIs (the contiguity contrast in §2 was seen first), and prediction 4 is
known to hold. A v2 pass on them is therefore a consistency check on DEV
data, **not evidence that the metrics separate formal from informal
fabric**, and it changes no label: density metrics stay `experimental`.
Prediction 2 (built share) was not inspected for these AOIs before
registration.

## 5. Side analysis S1 (descriptive, no verdict)

v1's four predictions with masses in place of polygons (median mass for
footprint size, masses/km² for density, median gap for spacing), to show
whether de-fragmentation alone would have rescued v1. Reported, never a
pass.

## 6. What would count as evidence (not run here)

A held-out pair, chosen and frozen before its metrics are computed, both on
Open Buildings v3: one planned sector grid outside India's Chandigarh (e.g.
an Islamabad or Gandhinagar sector) and one high-density built-up area not
used anywhere in item 23 (e.g. Korail, Dhaka, whose layer is cached).
Choosing the exact boxes needs local knowledge; left to Kanveer.
