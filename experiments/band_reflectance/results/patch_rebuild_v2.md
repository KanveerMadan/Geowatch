# Patch rebuild, second attempt — the reconstruction works

Ported the five patch builders and the assembly step from
`notebooks/archive/geowatch_water_loco_with_diagnostics (2).ipynb` at `ecfe370`
— the notebook `archive/AUDIT_FINDINGS.md:689` identifies as the source of the
deployed checkpoint, not the `_UPDATED` notebook `ingestion/resnet_model.py`
cites (C42).

**Result: the rebuild reconstructs. 1,414 patches against the checkpoint's
1,413, every class within 1.9 sd, and a reachable split reproduces the stored
class weights to max |Δ| 0.0083.** Arm A then trains normally.

## The gate, and why its target got sharper

The brief's gate was "the checkpoint weights, total near 1413". That is
necessary but loose — inverse-frequency weights are scale-free, so they pin the
class *ratios* and say nothing about the total.

But the formula inverts. Counts are proportional to 1/weight, so the stored
weights plus an assumed total recover the counts they were computed from:

| assumed total | implied per-class counts | integral? |
|---|---|---|
| 1413 | 161.06, 33.32, 578.85, 201.04, 73.31, 94.41, 271.01 | no, residual 0.411 |
| **1272** | **145.00, 30.00, 521.09, 180.98, 65.99, 84.99, 243.97** | **yes, residual 0.090** |

So the deployed weights were computed on the **1,272-patch train split**, not on
all 1,413. That is exactly what cell 39 does — `full_counts =
Counter(p['label'] for p in train_patches)` — overriding cell 18's earlier
`all_patches` version. Feeding `[145, 30, 521, 181, 66, 85, 244]` back through
the formula returns the checkpoint's weights to **max |Δ| 5e-5**.

This makes the naive comparison confounded: weights on the rebuilt
`all_patches` are not the same statistic as weights on a random 90% draw from
it. On a class with 30 members a ±3 swing moves that class's weight by 5%. So
the gate asks the decidable question instead — *is the checkpoint's train split
a plausible draw from this rebuild?*

## What the rebuild produced

    sliding_window   502        rebuilt total   1414
    osm              275        checkpoint      1413   (1272 + 141)
    osm_generated    274        delta             +1
    sam              268
    osm_gen_water     95

| class | rebuilt | target (1413-scaled) | Δ | need in train | have | z |
|---|---:|---:|---:|---:|---:|---:|
| dense_informal_roofing | 161 | 161.1 | −0.1 | 145 | 161 | +0.05 |
| sparse_informal_roofing | 30 | 33.3 | −3.3 | 30 | 30 | +1.85 |
| paved_road | 588 | 578.9 | +9.1 | 521 | 588 | −1.43 |
| standing_water | 202 | 201.0 | +1.0 | 181 | 202 | −0.18 |
| vegetation_clearing | 70 | 73.3 | −3.3 | 66 | 70 | +1.24 |
| active_construction | 91 | 94.4 | −3.4 | 85 | 91 | +1.13 |
| dense_vegetation | 272 | 271.0 | +1.0 | 244 | 272 | −0.15 |

Every class is reachable and within 1.9 sd. Over 20,000 random 1272-of-1414
draws, the **best** reproduces all seven checkpoint weights to **0.0083**
(median 0.1343). The naive all_patches comparison gives max |Δ| 0.1397 with
correlation 0.9996, and the 0.1397 is almost entirely `sparse_informal_roofing`
— 30 members, so a 3-patch swing is a 5% weight swing.

**The +1 is not explained.** One patch out of 1,414. It matters only in that the
checkpoint's `n_train = 1272` forces its `all_patches` to have been exactly
1,413: at 1,414, `int(1414 * 0.10) = 141` leaves 1,273. So this is a
near-reconstruction, not a bit-exact one, and the original shuffle seed is not
recoverable regardless.

## The `paved_road` over-generation: the earlier suspicion was wrong

`patch_rebuild_verification.md` recorded `paved_road` at 2.75× and suspected
`sample_stride = max(20, aoi_km2 * 2)` interacting with tile size, since 3 of 11
tiles are 512-px crops of larger rasters.

**That was wrong.** The stride expression is byte-identical between the two
notebooks. One constant differs:

    _UPDATED.ipynb                  PAVED_ROAD_CAP_PER_CITY = 180
    water_loco_with_diagnostics     PAVED_ROAD_CAP_PER_CITY = 25

11 × 180 = 1,980 against 11 × 25 = 275. The earlier rebuild measured 1,563 OSM
road patches; this one produced exactly 275, because the cap binds in all 11
cities. Tile size never entered into it — the cap binds before stride can
matter.

**The tile-size observation is separately true, and is a real data-availability
gap.** `lon_per_px` ranges from 89.3e-6 (Dharavi, Accra, Nairobi, Dhaka, Lagos,
Guatemala, Kigali) to 195.3e-6 (HCMC), with Jakarta 136.7e-6, Nusantara
117.2e-6 and Cape Town 97.7e-6. Those four tiles cover more ground per pixel —
they are coarser representations of larger AOIs, not native-resolution crops.
That affects what the sliding-window builder can see in those cities and it
would have mattered had the cap not bound first. It is worth keeping on record;
it is not the explanation for this.

`standing_water` under-weighting *was* explained as recorded: the missing
`build_osm_generated_water_patches` supplies 95 patches here, and its
per-city counts match the notebook docstring's own tally exactly (Nusantara 25
capped from 31, Dhaka 22, Dharavi 17, Lagos 8, Jakarta 7, Cape Town 5, Nairobi
4, Accra 3, Guatemala 2, HCMC 2, Kigali 0). That is an independent fidelity
check that nothing in the gate looks at.

## Fidelity run — Arm A with the separation loss, Accra

Cell 35's `run_loco_fold` re-executed from ported code: 30 epochs, patience 8,
batch 16, AdamW encoder 1e-5 / decoder 3e-4, cosine to 1e-6, 0.5·CE(fold
weights) + 0.5·Dice + 0.25·separation(margin 2.0), grad-clip 1.0, encoder BN
frozen.

    fold mIoU              0.3925 @ epoch 17 (early stop at 25)
    checkpoint LOCO        0.313 +/- 0.0564 over 11 folds
    broken probe's Arm A   0.0221, six of seven classes at exactly zero

| class | IoU | val px |
|---|---:|---:|
| paved_road | 0.7096 | 52,113 |
| dense_vegetation | 0.4671 | 6,247 |
| vegetation_clearing | 0.4225 | 4,177 |
| standing_water | 0.3964 | 15,645 |
| dense_informal_roofing | 0.2793 | 15,081 |
| active_construction | 0.2596 | 18,534 |
| sparse_informal_roofing | 0.2128 | 13,022 |

**Seven of seven classes non-zero**, loss falling monotonically from 1.4054 to
0.2285, separation term falling 1.2470 → 0.0892. The control trains.

**On 0.3925 sitting above the ±1 sd band.** The gate script prints "OUTSIDE",
which is a cruder verdict than the number deserves in either direction. ±1 sd
describes the spread of the 11 fold values, so ~32% of folds are expected to
fall outside it and ~16% above — one fold landing above the band is ordinary,
not evidence of a mismatch. What it also is not is proof: Accra may simply be an
easier fold than average, this is one fold and one seed, the patch set is one
over, and the split differs from the original. The defensible claim is that
**the reconstruction reproduces the training behaviour the 0.313 run describes**
— not that it reproduces that run.

Note also what 0.3925 is measured on: the held-out city's *production-style*
patches, 85.4% of them single-class and many bbox-cropped and resized. It
inherits C43's qualification exactly as 0.313 does.

## Status

Gate passed. Fidelity run done. The four-arm comparison on production patch
geometry, without the separation loss, is in `comparison_accra.md` — D − B =
−0.0033, replicating the broken probe's only surviving signal on a working
control, with a per-class reshuffle the mean hides and an early-stopping
asymmetry to fix before scaling up.

The 11-fold paired run remains unrun, as does the
`experiments/harness/loco.py` validation run.
