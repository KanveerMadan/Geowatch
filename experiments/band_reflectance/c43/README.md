# C43 — patch-construction investigation

Everything behind **C43** (closed) and **C45** (untriaged) in
`04_FINDINGS_LEDGER.md`, and the **G1** gate result it follows from.

All scripts are **read-only** with respect to the repo: they rebuild the patch
set in memory from `data/pipeline_runs/` and write only under
`../results/c43/`. None of them modifies a builder, a config or a checkpoint.

Run with the `geowatch-env` interpreter (needs `geopandas`, `torch`):

    ./geowatch-env/bin/python experiments/band_reflectance/c43/<script>.py

## Measurement

| script | answers |
|---|---|
| `patch_audit.py` | per-patch class count, labelled-pixel fraction, crop geometry → the 85.4% / 63.3% / scale numbers |
| `boundary_audit.py` | what fraction of *scored* pixels sit on a class-to-class boundary (0.14%) |
| `overwrite_audit.py` | **C45** — OSM builders painting over human labels, pixel-aligned to the SAM canvas |
| `scarcity.py` → `scarcity_an.py` | the multi-class ceiling over every native 64×64 window position on all 11 canvases; the artifact-vs-scarcity split |
| `scarcity2.py` | window-size sweep, stride sweep, and the `osm` windows' discarded context |

## Correction arms

Each builds a variant patch set differing from the baseline **only in mask
pixels or geometry** — patch count, order and `label` strings are preserved, so
class weights are identical and the arms are paired fold-for-fold.

| script | arm | change |
|---|---|---|
| `fix_build.py` | **B**, **C** | B: bad overwrites → IGNORE. C: → the human label |
| `fix_build_d.py` | **D** | C, plus re-cut those patches at native 64×64 |
| `fix_build_e.py` | **E** | all 912 non-`sliding_window` patches → native windows with real multi-class canvas masks (85.4% → 47.7% single-class) |

## Probes

| script | runs | budget |
|---|---|---|
| `fix_probe.py` → `fix_an.py` | arms A/B/C, 3 cities × 1 seed | 1,600 steps |
| `fix_probe2.py` → `fix_an2.py` | arm D against the cached A/C | 1,600 steps |
| `fix_probe3.py` → `armE_an.py` | arms A/E, 4 cities × 2 seeds, dual yardstick | 3,200 steps |

Probes resume from their raw JSON, so a stopped run restarts where it left off.

## Result

All four arms are zero-to-negative; arm E is **significantly worse**
(−0.1041 mIoU, p=0.013) because removing bbox magnification costs 31% of the
supervised pixel budget. `armE_raw.json` holds **10 of 16** planned folds —
seed 1337 complete across all four cities, plus dharavi at seed 7. The run was
stopped before the remaining six; `fix_probe3.py` will resume them.
