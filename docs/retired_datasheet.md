# Datasheet — training data of the retired checkpoint (item 61)

> **Historical record. This documents the RETIRED 7-class pipeline.**
> Per `08_STATE.md` §RETIRED, the per-pixel 7-class pipeline and its
> checkpoint `models/production/geowatch_production_model.pth` are retired,
> not validated, and are retired inputs, not reference data. Nothing here
> describes current GeoWatch capability. The checkpoint's stored LOCO figure
> is **not** a capability number. It was measured on a materially easier task
> than the pipeline performs (`04_FINDINGS_LEDGER.md` **C43**), and its
> provenance is itself unresolved (see `docs/provenance_reconstruction.md`).
>
> **Out of scope here:** the class definitions, both the retired 7-class
> scheme and the fraction taxonomy. The fraction taxonomy is unsettled until
> item 21. The retired scheme is named only by its stored location
> (checkpoint field `categories`). Where a count is broken down by label,
> this sheet reports *how many distinct labels* a patch holds, never which.

Template: Gebru et al., *Datasheets for Datasets* (arXiv:1803.09010). Section
order follows the template. Questions with no recoverable answer say so.

**How the numbers were produced.** Every figure carries a tag:

| tag | operation | input |
|---|---|---|
| **[CK]** | read from the checkpoint dict (`torch.load(..., weights_only=False)`) | `models/production/geowatch_production_model.pth`, sha256 `f70000c4…6120d`, matching `ARTIFACT_HASHES.txt:2` (`shasum -c`, 2026-10-28) |
| **[NB]** | read from code cells of the training notebook | `notebooks/archive/geowatch_water_loco_with_diagnostics (2).ipynb` at `ecfe370` (`git show`), sha256 `1438bdcf…0964`, identified in `docs/provenance_reconstruction.md` |
| **[RB]** | counted over the 5-builder rebuild, `build_all_patches()` | `experiments/band_reflectance/production_patches_v2.py`, re-run 2026-10-28 (snippet below) |
| **[RJ]** | read from each training run's `result.json` | `data/pipeline_runs/<run_id>/result.json` for the 11 run ids in [NB] cell 4 |

The [RB] rebuild is a **near**-reconstruction: 1,414 patches against the
checkpoint's 1,413 [CK]. The one-patch excess is unexplained
(`experiments/band_reflectance/results/patch_rebuild_v2.md`). So [RB] shares
describe the rebuilt set, which is within one patch of the trained set. They
are not the trained set byte for byte.

```python
# [RB] re-derivation, run from the repo root (read-only; nothing is written)
from collections import Counter; import numpy as np
from experiments.band_reflectance import production_patches_v2 as pp
P = pp.build_all_patches(verbose=False)
Counter(p["source"] for p in P); Counter(p["city"] for p in P)
m = [np.asarray(p["mask"]) for p in P]
lab = sum(int((x != 255).sum()) for x in m); tot = sum(x.size for x in m)
Counter(len(np.unique(x[x != 255])) for x in m)
```

---

## 1. Motivation

**Purpose.** Supervision for a per-pixel land-cover segmentation model on
Sentinel-2 RGB. Its outputs fed the flood-susceptibility layers
(`docs/susceptibility_dag.md`).

**Creator.** A single developer. Annotation was done by the same person (§3).
No institutional affiliation is recorded in the repository.

**Funding.** None recorded.

## 2. Composition

**Instances.** 64×64×3 `uint8` image patches, each with a 64×64 label mask
(255 = IGNORE) [RB] and one patch-level `label` used for class weighting
[NB cell 39].

**Count.** 1,272 training + 141 monitoring = 1,413 patches [CK
`n_train_patches`, `n_monitor_patches`]. The monitoring split is a random
10% (`PROD_VAL_FRACTION = 0.10`, `random.seed(42)`) [NB cell 39], and
`int(1413 × 0.10) = 141`. It is a **random, not held-out-city**, split, and
the notebook prints that warning itself [NB cell 39].

**Cities.** 11 [CK `training_cities`]. One pipeline run per city [NB cell 4
`CITY_MAP`]:

| city | run id | AOI (W, S, E, N) [RJ] | approx. area¹ | tile px [RJ] | S-2 window [RJ] | patches [RB] |
|---|---|---|---:|---|---|---:|
| accra | `accra_20260702_163854` | −0.225, 5.54, −0.19, 5.57 | 12.9 km² | 390×335 | 2026-04-03 → 07-02 | 100 |
| capetown | `capetown_20260702_164022` | 18.66, −34.075, 18.71, −34.03 | 22.9 km² | 512×502 | 2026-04-03 → 07-02 | 172 |
| dhaka | `dhaka_20260702_163939` | 90.385, 23.765, 90.425, 23.795 | 13.5 km² | 446×335 | 2026-04-03 → 07-02 | 129 |
| dharavi | `dharavi_20260702_163012` | 72.836, 19.037, 72.862, 19.06 | 7.0 km² | 291×257 | 2026-04-03 → 07-02 | 140 |
| guatemala | `guatemala_20260702_164206` | −90.54, 14.61, −90.5, 14.65 | 19.1 km² | 446×447 | 2026-04-03 → 07-02 | 97 |
| hcmc | `hcmc_20260702_163714` | 106.58, 10.78, 106.68, 10.88 | 120.9 km² | 512×512 | 2026-04-03 → 07-02 | 131 |
| jakarta | `jakarta_20260702_163609` | 106.78, −6.13, 106.85, −6.08 | 42.8 km² | 512×512 | 2026-04-03 → 07-02 | 126 |
| kigali | `kigali_20260702_163814` | 30.058, −1.975, 30.082, −1.952 | 6.8 km² | 268×257 | 2026-04-03 → 07-02 | 99 |
| lagos | `lagos_20260702_165430` | 3.37, 6.475, 3.41, 6.51 | 17.1 km² | 446×390 | 2025-06-01 → 2026-02-01 (manual) | 148 |
| nairobi | `nairobi_20260702_164731` | 36.778, −1.318, 36.812, −1.284 | 14.2 km² | 380×379 | 2025-11-01 → 2026-02-01 (manual) | 109 |
| nusantara | `nusantara_20260702_165811` | 116.7, −1.0, 116.76, −0.945 | 40.6 km² | 512×512 | 2025-06-01 → 2026-02-01 (manual) | 163 |
| **all** | | | | | | **1,414** |

¹ Derived: bbox degrees × 111.32·cos(mid-lat) × 110.57 km. This is a
planar approximation, not a geodesic area. `imagery_acquisition_date` is
`"unknown"` in all 11 `result.json` files [RJ]. Each tile is a composite over
the stated window, and no per-pixel acquisition date is recoverable.

**Sources (patch builders).** Five builders [NB, cells 11–13]; counts [RB]:

| builder | patches | patches holding exactly one label |
|---|---:|---:|
| `sliding_window` | 502 | 295 |
| `osm` | 275 | 275 |
| `osm_generated` | 274 | 274 |
| `sam` | 268 | 268 |
| `osm_generated_water` | 95 | 95 |
| **all** | **1,414** | **1,207 (85.36%)** |

Patches by number of distinct labels present [RB]: 1 → 1,207; 2 → 165;
3 → 37; 4 → 3; 5 → 2.

**Labelled share.** 2,127,525 of 5,791,744 mask pixels carry a label
(36.73%), and 63.27% are IGNORE [RB]. Loss is computed on the labelled
pixels only. These figures re-derive, and agree with, the ones `C43` records.
They were recomputed here, not copied.

**Per-label counts.** The checkpoint's class weights imply integer per-label
counts on the 1,272-patch train split: weights are `(1/c)/Σ(1/c)·7`
[NB cell 39], so c ∝ 1/w. At total 1,272 the implied counts are integral to
within 0.001, and fed back through the formula they reproduce the stored
weights to 1e-7 [CK `class_weights`]. At total 1,413 they are not integral
(max residual 0.42). The counts themselves are not listed, because listing
them per label would describe the retired scheme. They are recoverable from
[CK] with the operation above.

**Missing information.** No per-pixel acquisition dates. No annotator
confidence. No record of which segments were offered for annotation but
skipped, beyond the `skipped` field in each `annotations.json`.

**Confidential or sensitive data.** None identified. Inputs are public
satellite imagery and OpenStreetMap geometry. No person-level data.

**Sub-populations.** Patches are grouped by city and by builder (above).
Cities are **not** a sample of any population of cities. They were chosen by
the developer, and no selection rule is recorded.

## 3. Collection process

**Imagery.** Sentinel-2 composites exported by the pipeline as `raw.tif`,
then rendered to an 8-bit RGB PNG with a **per-tile 2nd/98th percentile
stretch** (`generate_rgb_preview_tiles()` in `tiler.py`). The notebook reads
only that PNG (`tile_0_0.png`) and never `.npy` [NB; the code cells contain no
`np.load`]. The model stem takes 3 channels: `encoder.conv1.weight` is
(64, 3, 7, 7) [CK]. NIR/SWIR bands were exported but never reached training
(C41).

**Labels, by builder** [NB cells 11–13; `production_patches_v2.py` header]:

- `sam` — human-assigned labels on SAM-proposed segments, from `annotate.py`
  sessions (`annotations.json`, schema in `annotate.py`'s docstring). Each
  segment is bbox-cropped and resized to 64×64.
- `osm` — major-road centrelines, buffered 2 px. Everything else is IGNORE.
- `osm_generated` / `osm_generated_water` — OSM road / water geometry
  rasterised, capped at 25 per city with farthest-point spreading.
- `sliding_window` — 64×64 windows at stride 32 off a label canvas built from
  the above, keyed by dominant label, with ≥5% labelled pixels and ≤30 per
  label per city.

**Who annotated.** One person, the developer. No second annotator exists,
and no inter-annotator statistic is possible. Item 63's labelling guide is
the substitute the build manual names (`05_BUILD_MANUAL.md` item 63).
`annotate.py` is now frozen and refuses to run (C28 guard at the top of the
file).

**Timeframe.** Pipeline runs are timestamped 2026-07-02 (run ids). The
training notebook was last saved 2026-07-15 00:40. The checkpoint was written
2026-07-15 01:38 (file mtimes; `docs/provenance_reconstruction.md`).

**Ethical review.** None recorded.

## 4. Preprocessing / cleaning / labelling

- Per-tile percentile stretch, then `/255.0`, with no mean/std normalisation
  (`GeoWatchDatasetResNet`) [NB cells 21, 24].
- The bbox-crop-and-resize builders (`sam`, `osm_generated*`) change the
  apparent ground sampling distance per patch. Tiles also differ in degrees
  per pixel (`patch_rebuild_v2.md`, "tile-size observation").
- **Known label defect.** Some builders overwrite other builders' ground
  truth on the shared canvas. This is recorded, with its measured extent, as
  a finding in `08_STATE.md` (classifier-baseline section), and is not
  re-derived here.
- Raw data is kept: `raw.tif`, PNGs and `annotations.json` stay in each run
  directory.

## 5. Uses

**Used for:** the retired checkpoint only.

**Should not be used for:**
- **Any performance claim about current GeoWatch.** The pipeline is retired
  (§RETIRED), and its LOCO figure describes an easier task (C43).
- **Training a successor as-is.** 85.36% of patches are single-label by
  construction [RB]. Boundary decisions are almost absent from the loss
  (C43 §1).
- **Inferring formal/informal status of any place.** City AOIs were not
  drawn on legal status.

## 6. Distribution

**Not distributed.** `data/` and `models/` are git-ignored (`.gitignore`,
"Data and model artifacts" block). The repository is public, but none of
this data is in it. There is no LICENSE file, by decision (`CONTRIBUTING.md`).
Any future release would carry OSM's ODbL share-alike obligations on the
OSM-derived builders. That is a constraint to resolve before release, not a
decision made here.

## 7. Maintenance

**Integrity.** The 11 `annotations.json` files and the checkpoint are hashed
in `ARTIFACT_HASHES.txt`, and all 12 verify `OK` (`shasum -a 256 -c`,
2026-10-28). **The training PNGs (`tile_0_0.png`) are not hashed**, so the
images the model actually saw have no integrity record.

**Maintainer.** None. The dataset is frozen with the retired pipeline and
will not be updated or extended.
