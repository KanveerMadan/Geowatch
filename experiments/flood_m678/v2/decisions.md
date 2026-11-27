# M6–M8 v2 decisions (append-only)

2026-11-27. **Step 0 (protect the evidence).**
- **Branches:**
  - Implementation branch `feat/m678-v2-impl` from `origin/design/m678-v2` at **bfa85d0d207ee6d19619085e21a280b2a52abce7**.
  - The design is based on v1 at f8e0777. v1 has one later commit, a0bfe89, the reserve-labeller defect note. It is reconciled below.
- **Pins** (`registry.py`):
  - v1 seal `fb73a2e` (tag `m678-reserve-seal`);
  - v1 freeze `222c904` (tag `m678-freeze`);
  - round 3 at `5ca318f`, which includes R35 (no baseline exemption).
  v2 imports round 3's code from a detached worktree at that SHA (`~/gw-r3pin-r35`), never from a moving branch.
- **v1 quarantine, forever:**
  - Every v1 reserve cluster (19 type:cluster keys, 70 incidents including the pre-2022 ones withheld from DEV and those refused by the per-cluster cap) is excluded from v2 training and testing.
  - The 18 v1 reserve labels that were built before v1 stopped are moved to `~/.cache/geowatch/flood_m678/QUARANTINE_v1_reserve`, mode 000. Nobody scored or inspected them beyond the label-builder's own count line.
  - The v1 labeller defect (6 incidents) is moot: v1 never runs its one-shot test.
  - v1 scoring is disabled in this workflow: v2 never imports or calls `score_m678.py` or `chain_reserve.sh`.
- **v1 DEV incidents** (14) were inspected. In v2 they are DEV-only, never reserve.
- **Round 3:**
  - Its 449 DEV units (burned and Sentinel-1-route catalogues) are the only round-3 tables that `transfer.py` may read.
  - Its registries, candidate pools and DEV footprints (961 footprints) exclude any v2 reserve candidate that touches them (20 km rule, as v1).
  - Round 3's own reserve is not sealed yet. v2 reserve selection rechecks its metadata at v2 seal time.
- **Storage:**
  - DEV data under `~/.cache/geowatch/m678v2/dev`.
  - Reserve under `~/.cache/geowatch/m678v2/reserve`, created mode 000. Only `score_once` (step 6) may unseal it, after verifying seal, freeze and power receipts.
  - Unit tests use synthetic data only (`test_step0.py`).
- **Owner additions recorded:**
  - **Priority:** M7 first, then M8 sustained melt, then M8 ice jam. M6 ships as a labelled scenario (water release and debris runout separate) unless its own evidence qualifies.
  - **Resources:**
    - the Earth Engine lock is held exclusively for heavy calls;
    - one heavy worker;
    - pause below 20 % free memory;
    - stop downloads below 15 GB free disk;
    - caffeinate, checkpoint and resume.
  - **Reporting:** STATUS.md after each step, a push after each step, and a PR to master only for product changes.
