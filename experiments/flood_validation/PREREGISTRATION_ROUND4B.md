# Flood validation round 4b — pre-registration (M3 waterlogging, persistence only)

**Written 2026-10-31, and committed before any round-4b box, cell count,
module input or score was computed.** Its SHA256 is recorded in the
round-4b result file. Rounds 1–4 and their result files are unchanged, and
they stay the record of those rounds.

## Why a round 4b

Round 4 failed waterlogging at 0.613 (Assam 0.406, Sylhet 0.668, Kerala
0.766). Computed after the verdict, a post-hoc diagnostic showed that the
`persistence` component alone ranked above 0.72 on all three test events
(C80, confirmed 2026-10-31). Those three events have now been seen, so they
cannot test that idea. Round 4b tests it **on new events only**. This is the
user's decision (2026-10-31): waterlogging = historical standing-water
persistence only, on at least 2 new waterlogging events, with the same bar
and box rules, and no tuning.

## The method under test (nothing tuned)

**Score = `persistence`**, exactly round 4's component
(`susceptibility/waterlogging.persistence`). Per 30 m cell, it is the mean
of the available of:

- **JRC GSW monthly history:** water months / observed months, January 1984
  to December of min(event year − 1, 2021);
- **Sentinel-1 IW VV:** the share of acquisitions below −18 dB over the 3
  calendar years before the event year.

Only years **before** the event are read. Weights are `persistence` 1 and
`clay`, `low_relief`, `backwater` 0 (`WATERLOGGING_R4B_WEIGHTS`). There is no
grid and no tuning event. The pipeline's waterlogging module runs this
configuration from the commit after this one, so the label applies to what
runs.

## What was looked at before this was written, and nothing else

- **Event facts**, from news and agency reports:
  - **Noakhali, Bangladesh:** floodwater from Feni from 20 August 2024.
    Noakhali was newly inundated on 28 August, with 2.1 million stranded.
    Water rose again on 10 September, and waterlogging continued in late
    September.
  - **Pas-de-Calais:** about 300 mm of rain in a month (Oct–Nov 2023). The
    wateringues drainage network was saturated and could not evacuate
    water, and fields were still waterlogged more than ten days after the
    start.
  - **Redon:** the Vilaine/Oust peaked on 30 January 2025 and receded
    slowly over several days. The town is built on marshland.
- **Reference availability only:**
  - the EMS product lists of EMSR706, EMSR712 and EMSR788, and their
    `observedEventA` layer names and image dates;
  - HDX listings of UNOSAT products, and the FL20240825BGD description
    (Sentinel-1, two periods, 18–26 Aug and 28 Aug–4 Sep 2024, about
    140,000 km² analysed). Its geodatabase's layer names, and the one
    attribute row of the second-period flood layer (class 1 = "Flood
    Water", sensor date 2024-09-04). No geometry was read.
- **No** round-4b box, centroid, flooded cell, input value or score.

## Events (all new: none appears in rounds 1–4 in any role)

A waterlogging reference should map water that **stayed**. Where a product
has several dates, the **latest** is used: the water still standing at the
end.

| Event | Event date | Reference | Why it is waterlogging |
|---|---|---|---|
| **noakhali_2024** (Feni–Noakhali, Bangladesh) | 2024-08-25 | UNOSAT FL20240825BGD, Sentinel-1, **second period 28 Aug – 4 Sep 2024** (geodatabase layer `S1_20240828_20240904_FloodExtent_Bangladesh`, `Water_Class` 1 = "Flood Water"; extent `AnalysisExtent_Bangladesh`) | water standing a week or more after the 20–26 Aug flood, in flat, drainage-blocked coastal plain |
| **calais_2023** (Calaisis wateringues, France) | 2023-11-07 | Copernicus EMS **EMSR706 AOI01 Calais**, DEL monitoring 0 (Sentinel-1, **2023-11-24**) | polder lowland whose drainage network was saturated; water 17 days after the start |
| **redon_2025** (Vilaine–Oust marshes, France) | 2025-01-30 | Copernicus EMS **EMSR788 AOI06 Redon**, DEL **monitoring 4** (TerraSAR-X, **2025-02-05**), the latest | marsh backwater behind a slowly receding river, 6 days after the peak |

Three events, so one can fail qualification without leaving the module
not-run. **At least 2 must qualify.**

## The bar and the box rule (unchanged from rounds 3 and 4)

- **Metric:** ROC AUC of the score, flooded vs dry 30 m cells, ties one half,
  **within each event**.
- **Qualifying event:** ≥ 50 flooded **and** ≥ 50 dry valid cells in the box.
- **Verdict:** the unweighted **mean of per-event AUCs over qualifying
  events**. **≥ 0.70 → validated; < 0.70 → failed**; fewer than 2
  qualifying → **not-run**.
- **Box:** a 4 km square centred on the area-weighted centroid of the
  reference's flooded area inside its extent (the nearest flooded point if
  the centroid is not on it). EMS extent = the product extent; UNOSAT extent
  = its `AnalysisExtent`.
- **Valid cell:** inside the box and the reference extent, not JRC permanent
  water (occurrence ≥ 80 %), finite score.
- **Flooded:** EMS `Flooded area` ∪ `Flood trace`, or UNOSAT `FloodExtent`
  "Flood Water", covering ≥ half the cell.
- **Pooled AUC:** a diagnostic only.
- Run **once**. No box is moved after any count or score is seen.

## Weaknesses stated in advance

- **Persistence is partly circular:** in places that flood every year, past
  water predicts present water by construction. That is the method's claim,
  not a flaw in the test. But a pass says "it floods where it flooded
  before", not why.
- **Bangladesh:** UNOSAT's analysis extent is about 140,000 km², so the
  centroid may land far from Noakhali (C72's issue). The rule is applied as
  written. The product is a machine-learning S1 classification, preliminary
  and not field validated, and SAR misses water among buildings and
  vegetation.
- **The French events are winter floods in temperate lowland.** JRC monthly
  history there is less complete in winter (cloud), and S1 history is
  three years.
- **Redon** is a river-backwater marsh, the backwater side of waterlogging,
  not rain ponding.
- JRC monthly history ends in 2021, so for 2024 and 2025 the last 2–3 years
  come from Sentinel-1 alone.

A fail is still a fail against the bar.

## Labels (what each outcome does)

- **validated:** waterlogging reads `validated` only through the C70 rule.
  The exact configuration (method, weights {persistence 1, others 0},
  ceilings, input sources and methods) and its scope (these events,
  regions, input versions) go into `analysis/contract.VALIDATED_CONFIGS`.
- **failed:** waterlogging stays `failed`.
- **not-run:** waterlogging stays `failed`. Round 4's verdict stands, and
  nothing has passed.
