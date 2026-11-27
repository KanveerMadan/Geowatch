# M6–M8 pre-registration (flood round 5)

Written after the DEV comparison and before any reserve label, feature or score exists. The freeze tag `m678-freeze` points to the commit that adds this file. Nothing below changes after the tag. DECISIONS_M678.md stays append-only.

## 1. The sealed reserve

- **Selection:** `reserve_m678.json`, sealed at commit `fb73a2e` (tag `m678-reserve-seal`). Its sha256 is in `RESERVE_HASH_M678.txt`, and it was chosen from metadata only by `select_m678.py`.
- **Criteria:** `RESERVE_CRITERIA_M678.md` with its 2026-11-27 addendum.
- **Clusters:**
  - M6: Mendenhall, Skaftá (Sveinstindur), Taku, Kenai (Snow Lake), Salmon (Summit Lake), Kennicott (Hidden Creek);
  - M7: Kakhovka (Kherson), Orsk, Pajaro, Al-Tlul, Tutaekuri (Gabrielle), Ussuriysk;
  - M8: Red River, Hay River, Muonio (Kallio), Ottawa, Saint John, Upper Mississippi, Yukon (Galena).
- **Round-3 reconciliation:** `overlap.py` at round-3 commit f28d714, 20 km search squares. Rutland (M8) is excluded because it overlaps a round-3 flash candidate.

## 2. Labels (identical for DEV and reserve)

- **Code:** `labels_m678.py` as of the freeze tag.
- **States:**
  - 1 flooded;
  - 0 dry;
  - −1 unobserved;
  - −2 permanent or normal water;
  - −3 ambiguous.
  Only 1 and 0 are scored.
- **Optical first** (Landsat C2 L2, Sentinel-2 L2A, Sentinel-2 L1C with s2cloudless where no L2A exists):
  - water needs the sensor's water class (or a second index) AND MNDWI > 0;
  - dry needs a clear land class, MNDWI < 0 and NDVI ≤ 0.3;
  - new water only: there must be a clear pre-event land view in [t0 − 60 d, t0 − 6 d];
  - built-up cells are unobserved;
  - every screened clear scene counts (maximum extent).
- **Sentinel-1 radar fills where optical is cloudy** (owner rule, recorded before any reserve label). A cell takes the optical state when optical is flooded or dry; otherwise it takes the radar state from the screened same-orbit passes with a baseline. Radar uses round 3's R3-S1-1..4 and R3-O-1..4 unchanged: −3 dB drop AND ≤ −15 dB; baseline [t0 − 60, t0 − 6] d or the year before; HAND > 15 m, built-up and slope > 20° unobserved; JRC ≥ 80 % permanent.
- **Snow and ice:** MODIS MOD10A1 snow on the image day makes a cell unobserved.
- **Timing:** only the screened scenes inside each incident's window:
  - M6, M7 and ice jams: [crest − 24 h, crest + 48 h] for every possible crest time;
  - sustained melt: [crest − 24 h, crest + 72 h];
  - levee breaches: also after the breach.
  Every scene's lag to the crest interval is recorded in hours.
- **Box:** round 4's flood-centre rule on the label of the 20 km search square, then an 8 km box.
- **Usable unit:** ≥ 50 flooded and ≥ 50 dry cells. A unit without a box, or with fewer cells, is a dropout. Dropouts are listed and never replaced.
- **Label QA:** agreement between the optical and radar labels where both observe a cell (κ), reported per event.

## 3. Features

- Round 2/3's own feature pipeline (`build_r3._features`), unchanged, on the 8 km box (`features_m678.py`).
- Event features (`dev_cv_m678.feats`):
  - round 3's GEOGloWS stage proxy (M7 levee breaches and M8 only; GEOGloWS does not simulate dam or lake failures);
  - the trunk-channel height and distance;
  - M6's LAHARZ score with the volume in `lake_volumes_m678.json` (rules a–e in `m6_physics.py`, resolved from metadata before this file).

## 4. The bar (unchanged from round 3)

Per type, on the usable reserve units:
- within-event AUC with the 990 m blocked bootstrap (`model_r3.gain_lower_bound`, the flood_baselines scorer);
- the chosen method's gain over the better of elevation and HAND must have a 95 % lower bound > 0. A baseline method is compared with the other baseline (round 3's convention);
- mean AUC ≥ 0.70;
- ≥ 5 usable independent clusters.

Verdicts: `pass`, `fail`, `too_few_events`. The test is `score_m678.py test`, run once. It refuses to run a second time.

## 5. What counts as failure, and what the product shows

- `fail` or `too_few_events` → the product label stays `experimental`, with the reason shown in words.
- `pass` → `validated`, with a scope note naming the held-out events.
- A type is never shown as zero where its event cannot happen: no inventoried lake (M6) or rare snow (M8) means "not computed", with the reason.
- The M6 and M7 scenario mode ("what if this lake or dam fails") is always labelled `scenario`.

## 6. Method per type and power

(filled from `results/dev_cv_m678.json` below)

Source: `results/dev_cv_m678.json` (leave-cluster-out, DEV only) and `results/power_m678.json`. Choice: round 3's `model_r3.choose`. When the best 95 % lower bound is ≤ 0, the type keeps its better DEV baseline (the `model_r3` docstring).

| type | DEV units / clusters | best non-baseline (lower bound) | chosen method | compared with | DEV mean AUC (chosen) |
|---|---|---|---|---|---|
| M6 | 1 / 1 (Grímsvötn) | not compared: one cluster | **`phys_laharz`**: physics only, owner instruction; LAHARZ-style routed inundation from lake volume (`m6_physics.py`, volumes in `lake_volumes_m678.json`) | the better of elevation and HAND | 0.561 on Grímsvötn (elevation 0.410, HAND 0.474); that label is unverified |
| M7 | 5 / 4 | `elev_hand_lr` −0.0094, CI [−0.0222, +0.0070]; anchored learners λ ≈ 0 | **`elev`** (minus GLO-30 elevation) | HAND (round 3's convention for a baseline method) | 0.795 (HAND 0.616) |
| M8 | 3 / 3 | `elev_hand_lr` +0.0123, CI [−0.0019, +0.0358] | **`elev`** | HAND | 0.863 (HAND 0.752) |

**Power at the sealed reserve** (round 3's formula, Δ = the DEV gain of elevation over HAND per cluster, floored at 0.03):

| type | DEV gain over HAND | SD over clusters | clusters for 90 % power | sealed clusters | achieved power |
|---|---|---|---|---|---|
| M7 | +0.161 | 0.252 | 34 | 6 | 0.35 |
| M8 | +0.112 | 0.195 | 42 | 7 | 0.33 |
| M6 | not estimable (one DEV unit) | – | – | 6 | – |

- Each type is under-powered at the size the sources allow. If a type fails or has too few events, that is what is reported. A larger fresh reserve under the same rules is the next round (Phase H). The bar is not changed.
- The learned candidates add nothing on DEV (λ = 0 in 7 of 8 outer folds), so no learned model is frozen. `results/frozen_models/SHA256.json` records that.
- The DEV labels are small and partly uncertain:
  - Gandak's radar label may include monsoon paddy;
  - Grímsvötn's December radar label is unverified;
  - Fort McMurray's optical QA lags by 47 h.
