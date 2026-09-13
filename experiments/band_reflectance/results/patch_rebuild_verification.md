# Patch rebuild verification — the reconstruction is still wrong, and why

Ported the three patch builders and the assembly step from
`notebooks/archive/geowatch_segformer_finetune_UPDATED.ipynb` at `ecfe370` — the
notebook `ingestion/resnet_model.py` cites. Result: **the rebuild does not match
the checkpoint, so training was not attempted.**

## Cell numbering

The brief's cell numbers do not match this copy. In it: builders are **cell 10**
(11.6 k chars), assembly **cell 12**, class weights **cell 16**, dataset/aug
**cell 19**, encoder swap **cell 21**, loss **cell 23**. 41 cells total.

## Sources: three, not five

This notebook has `build_sam_patches`, `build_osm_patches`,
`build_sliding_window_patches`. It has no `build_osm_generated_patches` and no
`build_osm_generated_water_patches`.

Scanning all 54 archived notebooks, the builders split into two families:

| family | builders | separation loss |
|---|---:|---|
| `..._UPDATED.ipynb` (cited by `resnet_model.py`) | 3 | none |
| `..._water_loco_with_diagnostics.ipynb` and 3 others | 5 | present |

`AUDIT_FINDINGS.md:689` identifies `water_loco_with_diagnostics (2).ipynb` as the
checkpoint's source, and the checkpoint's `architecture` string names a
separation loss that only the 5-builder family implements. **The cited notebook
is the architecture source, not the training source.** Filed as **C42**.

## Counts

    rebuilt total                     2359
    checkpoint n_train + n_monitor    1413   (1272 + 141)

    by source:  osm 1563 | sliding_window 528 | sam 268

## Class weights — the provenance test

Recomputed with cell 16's formula from the rebuilt set, against the checkpoint's
stored values:

| class | rebuilt | checkpoint | ratio |
|---|--:|--:|--:|
| dense_informal_roofing | 0.5766 | 0.6135 | 0.94 |
| sparse_informal_roofing | 2.4671 | 2.9653 | 0.83 |
| **paved_road** | **0.0666** | **0.1707** | **0.39** |
| **standing_water** | **1.3261** | **0.4915** | **2.70** |
| vegetation_clearing | 0.9915 | 1.3479 | 0.74 |
| active_construction | 1.1658 | 1.0466 | 1.11 |
| dense_vegetation | 0.4065 | 0.3646 | 1.12 |

max |Δ| 0.8346, correlation 0.8975. Two failures are diagnostic:

* **`standing_water` ~2.5× under-weighted** — i.e. too few patches. Directly
  explained by the missing `build_osm_generated_water_patches`. §A.5 records 101
  of the 133 `standing_water` annotations as OSM-generated water, and the cited
  notebook reads none of them.
* **`paved_road` 2.75× over-weighted** — too many patches. 1,563 OSM road
  patches against an implied ~579. Not explained by the missing builders, since
  adding sources would push the total further above 1413. Likely the per-city
  `sample_stride = max(20, aoi_km2 * 2)` interacting with a different
  `tile_0_0.png` size: 3 of 11 local tiles are 512-px crops of larger rasters,
  which changes `lon_per_px` and therefore how many pixels a road traverses.

## Status

Not proceeding to training. Per the brief, a rebuild that does not land near
1272 means the reconstruction is still wrong, and Arm A trained on a wrong
dataset would produce another uninterpretable control.

The correct next step is to port the **5-builder** family instead —
`water_loco_with_diagnostics`, which also carries the separation loss and the
LOCO loop the 0.313 figure needs.
