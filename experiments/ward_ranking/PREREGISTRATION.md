# Ward-ranking test — pre-registration (item 26, task 5)

**Written 2026-10-28, before any (b) or (c) value was computed.** Its SHA256 is
recorded in the result file; `c3_ward_ranking.py` reads the metric and bar from
module constants that match this text.

Evidence only. Nothing in the flood path changes on the result.

The brief cites "08_STATE §5.7 option C3". No §5.7 or option C3 exists in
`08_STATE.md` on any branch, so this follows the brief's own description.

## Question

Does the order of Mumbai's wards by imperviousness depend on which impervious
estimate is used?

## Units

The 24 BMC wards in `data/pipeline_runs/phase12b_ward_landcover_v2.json`
(ward polygons: `data/boundaries/datameet_mumbai_bmc_wards/boundary.geojson`,
joined on `gid` = `ward_id`). That file and its wide run
`phase12b_wide_datameet_mumbai_bmc_wards_20260822_014426` are "the existing
Dharavi run": Dharavi sits in ward G/N.

## The three estimates, one value per ward

| | Estimate | Definition |
|---|---|---|
| (a) | stored spectral | `hydrological_surfaces.impervious_fraction_pct` as stored per ward (retired 7-class classifier on Sentinel-2) |
| (b) | footprint built area | Open Buildings v3 polygons, all confidences (as Lane B), painted into one 2 m mask (union: overlaps and fragments count once, by area), averaged over the ward polygon. Never a count |
| (c) | built + remainder | per 10 m pixel, `built + max(0, 1 − built − vegetation − water)`; `built` = the (b) mask averaged to 10 m; vegetation/water = Lane B's Sentinel-2 thresholds (NDVI > 0.3 and not water; MNDWI > 0) on a median of its SCL-masked collection (cloud filter 60), window **2025-11-01 → 2026-08-22** (the stored run's); a pixel counts only with ≥ 3 valid observations. Ward value = mean over counted pixels |

## Metric and bar

- **Metric:** Spearman rank correlation ρ over the 24 wards, per pair:
  (a, b), (a, c), (b, c). Each pair is reported on its own; no averaging.
- **Bar:** ρ ≥ **0.80** → the ward order is **stable** across that pair;
  ρ < 0.80 → **unstable**.
- A pair with fewer than 20 wards carrying a value is **not evaluated**.

Reported plainly against the bar, whatever it shows.
