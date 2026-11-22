# Round-3 reserve: selection criteria (written before any candidate is listed)

The reserve is chosen **mechanically from metadata**. Metadata means:
- imagery availability and acquisition times;
- product footprints;
- reported extent statistics;
- activation text and dates;
- driver timing (rain, discharge, landfall).

**What is never read before the freeze:**
- no label geometry and no flood polygons;
- no reference raster;
- no feature table or score of a candidate;
- nothing that compares labels with any model.

**Sequence:**
1. This file is committed and pushed first.
2. `select_r3.py` runs these rules and writes `reserve_r3.json`.
3. Its SHA256 and the push time go into `RESERVE_HASH_R3.txt`, pushed before any Phase 4 model is built.

## 1. Never used before
A candidate is refused if any of these holds:
- its Copernicus EMS activation code appears anywhere in the registry or in rounds 1–3. This includes all 169 burned units and the round-2 DEV-only activations.
- the registry guard (`experiments/flood_core/registry`) links it to any used unit by a shared product, a box intersection, proximity within 20 km, or the same storm cluster;
- for Sentinel-1 / reporting-based candidates: the same place (within 20 km) and date (within 30 days) as any used unit.

## 2. Event and type
- **Event date:** 2015-01-01 or later (the Sentinel-1 and HLS era).
- **Type:** from the activation text or the reporting, by the round-1 rules (`flood_learned/heldout/select.py`).
- **The drivers must agree with the type** (DIAGNOSIS.md §i), checked from metadata:
  - **river:** a GEOGloWS discharge peak with return period ≥ 1.5 y at the AOI's largest reach, within [event − 10 d, event + 7 d];
  - **rain and flash:** an IMERG 3-day peak ≥ 20 mm over the AOI plus 25 km;
  - **coastal and compound:** a named storm's landfall within 150 km. Compound also needs rain ≥ 50 mm, or a river peak with return period ≥ 1.5 y.
  - A candidate that fails its type's driver check is refused.

## 3. Image timing (R19)
The first label image must fall inside **[peak − 1 d, peak + MAX_LAG]**.
- **MAX_LAG:**

  | type | rain | flash | river | coastal | compound | waterlogging |
  |---|---|---|---|---|---|---|
  | days | 1 | 2 | 3 | 2 | 2 | 14 |

- **Peak by type:**
  - **river:** the GEOGloWS discharge peak at the AOI's reach;
  - **rain, flash and waterlogging:** the IMERG 3-day peak;
  - **coastal and compound:** the landfall date.
- **EMS:** the image acquisition times listed in the product metadata.
- **Sentinel-1:** the image must be in the Earth Engine collection metadata, and it needs ≥ 2 same-orbit baseline images in [t0 − 60 d, t0 − 6 d] or the same window a year earlier. This rule fixes round 2's 3 "no pass" dropouts.

## 4. Enough flooded and dry cells (fixes round 2's 3 "too few" and 2 "no flood centre" dropouts)
- **EMS:** the product's reported `stats` must show an affected area ≥ 45 ha. That is 10× the 4.5 ha that 50 flooded 30 m cells need.
  - The AOI extent must be ≥ 16 km², so a 4 km box fits inside.
  - The flood centre and AOI are taken from the product's own AOI record at build time, not from a search square.
- **Sentinel-1 / reporting candidates:** there is no extent metadata. They are kept only for types that EMS cannot fill (§6), and their dropout risk is stated in the pre-registration.

## 5. Labels at build time (after the freeze)
- v3 rules (`labels_r3.py`; R19).
- Radar labels: built-up cells, HAND > 15 m and slopes > 20° are unobserved. Rain units need an urban-capable label (coherence drop, VHR optical, surveyed marks) for their built-up cells; without one, rain is scored on open cells only, and that is reported.

## 6. Size per type
- **Target:** n = ⌈1.3 × ((z₀.₉₇₅ + z₀.₉₀) × SD / Δ)²⌉ usable units.
  - **SD** is the per-unit gain spread on v3 labels over the burned units (`results/v3_burned_scores.json`).
  - **Δ** is the gain the round-2 DEV CV predicts for that type, floored at 0.03.
  - It is never planned below 5 usable units in 3 clusters.
- **If fresh events run short:** more sources are added (MMFlood, Sen1Floods11, Kuro Siwo, UrbanSARFloods and Sentinel-1 events from reporting, each licence-checked in LICENCES.md). The target is not shrunk.
- **Coastal:** at least 12 candidates, so that ≥ 5 survive. Compound uses the same buffer.
- **Per activation:** up to 2 AOI units, as in round 2. Units of one storm form one cluster.
- If a type still ends below its target, that is stated in the pre-registration with its achieved power. The bar is not changed.

## 7. Order inside a type
Candidates that pass §1–§4 are taken in **ascending activation code**, then AOI number. Sentinel-1 candidates come in ascending date. Taking stops when the target is met. No other ordering is allowed, so no one can pick "easy" events.
