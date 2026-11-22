# M1 fluvial: the method as validated

## Code version
- Every `file:line` reference below is at commit **`d1894e4`** (`d1894e4dd1322e935f2731000c33b6d010dafe00`, branch `exp/flood-baselines`, 2026-11-17). This evidence branch is cut from that commit.
- The fluvial computation has not changed since the round-2 run, commit `2832dc8` (2026-10-28):
  - `git diff 2832dc8 d1894e4 -- susceptibility/fluvial.py configs/fluvial_constants.py` shows only one change: an output metadata key (`"ceilings"`, `susceptibility/fluvial.py:109-110`).
  - The changes to `susceptibility/hydro_rasters.py` since then add layers for other modules (`upa_flash_km2`, clay, rainfall, water history). Fluvial reads none of them.
  - Two checks confirm this. The baselines run (2026-11-17) reproduces round 2's held-out AUCs exactly (Hanoi 0.9162, Kolonnawa 0.7996). Round 4's three fluvial AUCs reproduce exactly from cached arrays (`tables/baselines_reproduce_round4_fluvial.csv`).

| File | Last change before `d1894e4` |
|---|---|
| `susceptibility/fluvial.py` | `dca9e27` 2026-10-29 |
| `configs/fluvial_constants.py` | `2832dc8` 2026-10-28 |
| `susceptibility/hydro_rasters.py` | `b4b70fe` 2026-10-30 |
| `analysis/contract.py` | `5f6e22c` 2026-10-31 |

## What it computes
Fluvial is a per-pixel susceptibility **ranking** on a 30 m grid. It is not a depth, an extent or a return period.

```
low_hand   = clip01(1 − HAND_m / 30)
river_size = clip01( log10(1 + upa_near_km2) / log10(1 + 10 000) )
score      = (w_hand · low_hand + w_river · river_size) / (w_hand + w_river),   w_hand = w_river = 1
```

| Element | Value | Where |
|---|---|---|
| `low_hand` component | 1 − HAND / `HAND_NORMALIZATION_MAX_M` | `susceptibility/fluvial.py:46` |
| HAND ceiling | **30 m** (provisional, not calibrated) | `configs/fluvial_constants.py:30` |
| `river_size` component | log10(1 + upa_near) / log10(1 + `FLUVIAL_UPSTREAM_AREA_NORMALIZATION_MAX_KM2`) | `susceptibility/fluvial.py:47-49` |
| Upstream-area ceiling | **10,000 km²** (provisional) | `configs/fluvial_constants.py:49` |
| Drainage search radius for `upa_near` | **1,000 m** | `configs/fluvial_constants.py:46` |
| Weights | `{"low_hand": 1.0, "river_size": 1.0}` | `configs/fluvial_constants.py:54` |
| Weight grid (round-2 tuning) | `low_hand` 1, `river_size` ∈ {0, 0.25, 0.5, 1} | `configs/fluvial_constants.py:55` |
| Clipping to [0, 1] | `clip01` | `susceptibility/hydro_rasters.py:105-106` |
| Weighted mean | per pixel; a NaN component drops out at that pixel; zero total weight gives NaN | `susceptibility/hydro_rasters.py:117-132`, called at `susceptibility/fluvial.py:53-54` |
| Entry point | `compute_fluvial_susceptibility` (applicability-gated) | `susceptibility/fluvial.py:57-119` |
| Validated configuration and scope | `VALIDATED_CONFIGS["fluvial"]` | `analysis/contract.py:89-127` |

**How the weights were chosen.**
- The pre-registered default was `river_size` 0, i.e. HAND only (`PREREGISTRATION_ROUND2.md`, "Fluvial").
- The weights 1 : 1 were chosen on the two round-2 **tuning** events only (Faenza, Encantado), by the pre-registered rule "highest mean tuning AUC" (`choose_weights`, `experiments/flood_validation/harness_round2.py:154`).
- They were fixed before the held-out events were scored (`tables/round2_fluvial_tuning.csv`).

## Inputs
| Layer | Source and version | Processing | Where |
|---|---|---|---|
| `hand_m` | **MERIT Hydro v1.0.1**, band `hnd` (Earth Engine `MERIT/Hydro/v1_0_1`, ~90 m) | bilinear resample to the 30 m grid | `susceptibility/hydro_rasters.py:69, 85, 220` |
| `upa_near_km2` | **MERIT Hydro v1.0.1**, band `upa` | focal **max** within a 1,000 m circle on MERIT's own projection, then nearest to the 30 m grid. A cell's own `upa` is ~0 on every hillslope, so it reads the largest drainage line nearby | `susceptibility/hydro_rasters.py:86, 201-204, 221` |
| Grid | UTM zone of the box, 30 m (`HYDROLOGY_PIXEL_M`) | — | `susceptibility/hydro_rasters.py:143`, `configs/pluvial_constants.py:25` |

- HAND is MERIT's own, routed by its authors. It is **not** derived from FABDEM (`susceptibility/hydro_rasters.py:44-45`).
- **Fluvial reads no FABDEM, rainfall or land-cover layer.**

## Licences of what the method and its evaluation use
Licence entries are taken from the project's audit (`docs/flood_architecture_audit_2026-10-31.md` §5), which cites the providers' pages.

| Data | Used for | Licence |
|---|---|---|
| MERIT Hydro v1.0.1 | the score (HAND, upa) | **CC BY-NC 4.0 or ODbL 1.0, dual** ([U-Tokyo](https://hydro.iis.u-tokyo.ac.jp/~yamadai/MERIT_Hydro), [EE catalog](https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1)). Commercial use needs the ODbL option, so derived maps must then be ODbL |
| Copernicus EMS rapid mapping (DEL `observedEventA`) | reference (most events) | free under the CEMS terms, information purposes, attribution ([terms](https://mapping.emergency.copernicus.eu/terms-and-conditions/)) |
| UNOSAT FL20220808PAK (Sindh) | reference (round 4) | varies by UNOSAT product (CC BY-SA and CC BY-NC-SA both seen); **not recorded for this product** |
| Sentinel-1 GRD (Copernicus) | reference (S1 change maps) | Copernicus open data (the audit marks this as *assumed*) |
| JRC GSW 1.4 | permanent-water exclusion (occurrence ≥ 80 %); JRC baseline | Copernicus, free, "Source: EC JRC/Google" ([EE](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_Metadata)) |
| OpenStreetMap | distance-to-water baseline | ODbL |

## Evaluation (how every AUC in EVIDENCE.md was computed)
- **Unit:** a 30 m cell inside the event box.
  - **Flooded:** the reference covers at least half the cell (`COVER_MIN = 0.5`, `experiments/flood_validation/references.py:46`).
  - **Excluded:** JRC permanent water (occurrence ≥ 80 %, `configs/inundation_constants.py:16`), applied to every reference (`experiments/flood_validation/references.py:23, 186, 216`).
- **Metric:** within-event ROC AUC, flooded vs dry, with ties counted as half (`experiments/flood_validation/harness.py:56-67`).
  - Per event, at least 50 flooded and at least 50 dry cells are required (`harness.py:31-32`, `harness_round2.py:140-146`).
  - **Bar: mean of per-event AUCs ≥ 0.70** over qualifying held-out (or test) events (`harness.py:30`; pre-registrations).
- **Baselines comparison** (`experiments/flood_baselines/`):
  - All scores use the same cells.
  - Intervals come from a paired spatial block bootstrap: 990 m tiles, 1,000 replicates, seed 20261114.
  - Means use a cluster × block bootstrap over registry link-clusters.
  - The block size was chosen as the measured correlation range of the reference indicator. Details are in `experiments/flood_baselines/REPORT.md` §A2.
