# Reproduce every figure and number

All commands run from the repository root, with the project environment (`geowatch-env`: Python 3.12, numpy, matplotlib 3.11, scikit-learn 1.9).

## A. This pack, from committed results (no network, about 20 s)
```sh
git checkout paper/evidence-fluvial          # code and results as of d1894e4, plus this pack
python paper/evidence/M1_fluvial/build_evidence.py
```

**What it writes:**
- `tables/*.csv`: every number in `EVIDENCE.md` and `LIMITS.md`, each row carrying its source file and commit;
- `data_manifest.csv`;
- `figures/fig_a_*`, `fig_b_*`, `fig_c_*` (PNG at 200 dpi, and SVG).

**What it reads:**
- the committed result files: `experiments/flood_validation/result_*.json`, `experiments/flood_baselines/results/baselines.json`;
- the pre-registrations, and git history (for the hashes and dates);
- the registry `experiments/flood_core/registry/events.json`.

**Figures (b) and (c)** also need the per-cell caches of the baselines run:
- `~/.cache/geowatch/flood_baselines/<unit>.npz`;
- `~/.cache/geowatch/flood_refs/round{2,3,4}`.

They recompute the per-cell scores with `experiments.flood_baselines.score` and check every recomputed AUC against the stored one (`tables/figure_auc_check.csv`: 20 of 20 match). Without those caches, regenerate them with step C first.

**Check that a rebuild reproduces the committed pack:**
```sh
python paper/evidence/M1_fluvial/build_evidence.py && git status --short paper/evidence/M1_fluvial/tables paper/evidence/M1_fluvial/data_manifest.csv   # expect no changes
```

## B. Pre-registration hashes by hand
```sh
shasum -a 256 experiments/flood_validation/PREREGISTRATION_ROUND2.md      # f2ab3c74…f406
git show 3692894:experiments/flood_validation/PREREGISTRATION_ROUND2.md | shasum -a 256
python -c "import json;print(json.load(open('experiments/flood_validation/result_round2_2026-10-28.json'))['preregistration_sha256'])"
git log --format='%h author %aI committer %cI' -1 3692894                # pre-registration
python -c "import json;print(json.load(open('experiments/flood_validation/result_round2_2026-10-28.json'))['run_utc'])"
```
Repeat with `PREREGISTRATION.md`/`78c5031`/`result_2026-10-28.json`, `PREREGISTRATION_ROUND3.md`/`56a875b`/`result_round3_2026-10-29.json`, and `PREREGISTRATION_ROUND4.md`/`a772336`/`result_round4_2026-10-30.json`.

## C. Re-running the underlying experiments (not needed for this pack)
These are the original runs. They need Earth Engine (`GEE_PROJECT_ID` in the environment) and network access to Copernicus EMS, UNOSAT and Overpass. Their outputs are already committed, and **this pack did not re-run them**.

| Result | Command | Notes |
|---|---|---|
| Round 2 (`result_round2_2026-10-28.json`) | `python -m experiments.flood_validation.harness_round2` | held-out events are scored once by design; re-running is a replication, not a new test |
| Round 4 (`result_round4_2026-10-30.json`) | `python -m experiments.flood_validation.harness_round4` | same |
| Baselines (`baselines.json`, `tables.md`) | `caffeinate -i sh experiments/flood_baselines/run_all.sh` | about 7 h on a laptop, most of it pluvial inputs that fluvial does not need. `python -m experiments.flood_baselines.build --qualifying` (pass 1) suffices for fluvial and the three baselines, then `python -m experiments.flood_baselines.score` |
| Baselines unit tests | `python -m pytest -q experiments/flood_baselines/test_baselines.py` | 8 tests, pure |

**Expected differences on a re-run of C:**
- Earth Engine and OSM may return updated data:
  - OSM water edits change `dist_water`;
  - MERIT Hydro v1.0.1 is fixed.
- Everything downstream of the cached arrays is deterministic. The bootstrap seed is 20261114, and the per-unit seeds derive from it.
