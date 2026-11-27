# GFM (Global Flood Monitoring) in round 3: label rule and DEV acceptance gate

Written 2026-11-27, before any GFM product was compared with any label or candidate. It is part of RESERVE_CRITERIA_R3 (§11) and is hashed with it at the seal.

## What was seen before this was written
- The API spec, and the account's AOI allowance.
- One probe product for a DEV area: the Ahr valley (bad_neuenahr), 2021-07-01, which is **before** that flood.
  - Seen from it: the list of product times for July 2021 and January–February 2016, and the layer value coding.
  - Its flood layer was all 0 (pre-event). Its exclusion layer covered 79 % of valid cells.
- No GFM product of any reserve-period candidate, and no GFM flood layer during any event, has been read.

## 1. GFM label on a unit's 30 m grid (fixed now)
- **Product:** the first GFM product (Sentinel-1 sensing time) in the type's image window, [peak − 1 d, peak + MAX_LAG] (criteria §3).
- **Per 20 m GFM pixel:**
  - **wet** if ENSEMBLE_FLOOD = 1;
  - **dry** if ENSEMBLE_FLOOD = 0, ENSEMBLE_EXCLAYER = 0, ADVFLAG = 0 and REFERENCE_WATER ∉ {1, 2};
  - **unobserved** otherwise, including the value 255.
- **To the 30 m grid:**
  - the codes {dry 0, wet 1, unobserved 2} are resampled by mode (`rasterio` `Resampling.mode`);
  - the round-3 v3 masks (built-up, HAND > 15 m, slope > 20°) are **not** applied to GFM labels, because GFM carries its own exclusion layer. This is stated and reported.
- **Usable unit:** ≥ 50 wet and ≥ 50 dry cells, the bar's floor.

## 2. DEV acceptance gate: run before any reserve label is read
GFM is a Sentinel-1 product. Our own Sentinel-1 labels failed against independent optical maps for rain, flash, coastal and compound (DIAGNOSIS §e). So GFM may label a type's reserve units only if it passes this gate on DEV.

**Units:**
- the same EMS units as DIAGNOSIS §e (`diagnose_ee.agree`): 2015 or later, with an EMS image, ≥ 50 EMS-flooded cells;
- the GFM product is the first one on or after the EMS image date, at most 3 days later (the §e rule).

**Agreement:** cells both observe, with the same numbers as §e:
- κ;
- GFM recall and precision of EMS flood;
- the binary GFM label's "AUC" for EMS (balanced accuracy).

Also reported: **coverage**, the share of EMS-flooded cells that GFM observes, meaning not unobserved.

**Accept GFM as a reserve label for a type if:**
- **river, waterlogging** (our Sentinel-1 labels are already accepted, §8): GFM's median κ against EMS maps of all sensors is ≥ our own Sentinel-1 label's median κ on the same units (`label_agreement.json`), with ≥ 5 units.
- **rain, flash, coastal, compound** (our Sentinel-1 labels are refused): GFM's median κ against **optical / VHR-made** EMS maps is ≥ 0.40 ("moderate"), with ≥ 5 units. Radar-made EMS maps share the sensor and do not count here.
- **Otherwise:** GFM is not a label for that type in round 3. It may still be used as metadata (product times) and is reported as refused.

The gate's result goes into DECISIONS before any candidate list is drawn.

## 3. Events and storm joining (applies to every source added after this date)
- **Sources (metadata only):**
  - EMS activations (the existing selector);
  - GFM product times;
  - IBTrACS landfalls (coastal, compound);
  - GloFAS v5 discharge peaks (river);
  - IMERG (rain).
- **Joining before counting:** candidates from any sources are one **event** if any of these holds:
  - they share a named storm (IBTrACS SID, or the storm name in the activation text, the same year);
  - their centres are within 20 km and their peak dates within 10 days;
  - they are linked through a chain of such pairs.
- **Clusters and counting:** one event is one cluster. At most 2 units are taken per event (criteria §6), and the second unit's box must not overlap the first. Targets count units, and every report states units and events.
- **Never used (§1)** is checked on the joined event: if any member is linked to a used unit, the whole event is refused.

## 4. Sequence
1. This file and criteria §11 are committed and pushed.
2. The DEV gate is run (`gfm_labels.py agree`), and the result is recorded in DECISIONS.
3. The candidate lists are drawn from metadata by these rules, then joined, ordered (§7) and capped.
4. Seal: `reserve_r3.json` and `RESERVE_HASH_R3.txt`.
5. Only then are reserve labels, EMS or GFM, read.
