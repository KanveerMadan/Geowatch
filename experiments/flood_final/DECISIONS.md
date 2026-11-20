# flood_final: decisions and their reasoning

Every judgement call, in order. "Owner" = the repository owner's run brief (2026-11-19), which pre-approved registry edits, pre-registration, splits, event lists, hyperparameters and SFINCS settings.

## D1 (2026-11-19) The 20 EMS activations already opened become DEV, not RESERVED
- Before the owner's full-run brief, references were built and flooded/dry cells counted for 20 activations (experiments/flood_learned/heldout/select.py; 66 AOIs, 56 qualifying). That is exposure level 3 ("reference geometry/counts").
- The brief requires RESERVED events to be "never opened until Phase 7", and the registry test requires reserved units at exposure <= 2. Relaxing that test was refused by the permission system and would weaken the guard.
- So those 20 activations are DEV. RESERVED events are chosen from metadata only (EMS product metadata = level 2; news facts = level 1) and their >= 50/50 qualifying rule is applied once, at scoring (as round 2 did for Nysa and Hue).

## D2 EMSR838 (Pakistan, Aug 2025) is tagged fluvial, not flash
- The activation text says "flash flood", but every AOI EMS mapped (Rasoo Nagar, Sharaqpur, Trimmu, Najabat, Sahuka, Vanike, Wakeel Abad, Daggar, Pir Khalis) lies on the Ravi / Chenab / Jhelum floodplain in Punjab. The mapped water is river flooding of a monsoon plain. DEV only, so the retag affects grouping, not any held-out claim.

## D3 Same-storm rule for EMS activations not in the registry
- The registry knows storms only for its own units. Activations of the same storm as a registry unit are excluded from RESERVED by hand from date and place: EMSR789 (= milagro's Feb 2025 Ecuador rain), EMSR757 / EMSR758 / EMSR759 / EMSR761 / EMSR763 / EMSR764 / EMSR766 / EMSR755 (Storm Boris, Sept 2024 = registry storm boris_2024 via nysa), EMSR697 (Thessaly, 27 Sept 2023, same plain as volos), EMSR772 (first wave of EMSR779).
- A DEV unit may share a storm with a registry DEV unit (DEV-DEV links are allowed; the cluster bootstrap and leave-cluster-out keep them together).

## D4 EMSR708 (West Flanders, 10 Nov 2023) is not used at all
- Same storm series (Ciarán/Domingos) as round-4b reserved calais_2023 (EMSR706, 7 Nov 2023). Using it as DEV would train on round 4b's storm. It was opened before this was noticed; it is dropped, neither DEV nor RESERVED.

## D5 EMSR843 (Milan, Sept 2025) is not used: no AOI qualifies (Seveso 33 flooded cells; Blevio no flooded polygon in its extent).

## D6 Two South Asian monsoon-plain river events are reserved despite basin links
- The brief asks for held-out river events inside South Asian monsoon plains as well as outside. Any such event shares the Ganges-Brahmaputra-Meghna main basin with DEV units (dhaka, bihar_2026, assam_2026, sylhet_2022), an exception-severity registry link.
- Accepted for s1_assam_morigaon_2024 (Morigaon, about 280 km from the assam_2026 box) and s1_sunamganj_2024 (Sunamganj, about 75 km from sylhet_2022) only. Block-severity links (product, box, proximity within 20 km, storm) are never accepted. They are reported as a separate "South Asia, basin-linked" group as well as in the pooled river result.

## D7 Registry guard drops (dry run, 2026-11-19)
- RESERVED EMSR768 (Kupa/Korana, Oct 2024) shares the Danube main basin with 6 new DEV units (EMSR757 Morava x2, EMSR680 Slovenia x3, EMSR770 AOI03). Dropping the reserved activation keeps 6 DEV units, 4 of them flash floods, which DEV has few of. Europe keeps 2 reserved river activations (EMSR712, EMSR861).
- RESERVED s1_bor_2024 (Sudd) shares the Nile main basin with DEV kigali (and new DEV EMSR662 Uganda). Dropped; waterlogging RESERVED is then 2 events (EMSR856, s1_yenagoa_2022), fewer than the 5 the brief targets. Recorded, not padded.

## D8 The pluvial module's own inputs are not built for the 38 new DEV units
- They take up to an hour per unit (flood_baselines pass 3), and the pluvial recipe is a comparator, not a candidate the evidence suggests (it is below HAND on batch 0: −0.068 [−0.108, −0.021]).
- The pluvial module is scored on the batch-0 DEV units, where its inputs exist. On RESERVED it is scored only where its inputs build within the 1 h limit (PREREGISTRATION §4).

## D9 New features for all units: distance to the sat-io shoreline (capped at the coastal module's 50 km search radius), GLO-30 absolute elevation, and GHSL 2020 built-up share
- The brief lists distance to coast, coastal elevation and a second built-up source (Open Buildings / GHSL). GHSL GHS_BUILT_S 2020 is used because it is one global image in Earth Engine, which keeps one consistent source. Open Buildings' footprint layer exists only where the pluvial inputs were built.
- Appended at the end of the feature list, so batch-0 column indices and cached predictions are unchanged.

## D10 Urban-capable reference: UrbanSARFloods' published coherence-based labels, not a detector built here
- A Sentinel-1 coherence detector needs SLC data. Earth Engine has only GRD. The SLC portals (ASF, Copernicus Data Space) need an account (a hard stop in the brief). Processing SLC into coherence also needs an InSAR processor (SNAP / ISCE) that is not installed.
- UrbanSARFloods (Zhao et al. 2024, CVPRW; CC BY 4.0; huggingface.co/datasets/S1Floodbenchmark/UrbanSARFloods_v1) publishes coherence + intensity labels: NF non-flood, FO flooded open area, FU flooded urban. Full-scene labels are public for 4 events only (the rest are 512 x 512 chips in a 38 GB archive).
- **Used: Weihui, China (27 Jul 2021)**, the test scene with the most flooded-urban tiles (135). Not used:
  - Nova Kakhovka (dam breach, M7);
  - Jubba (10–13 urban tiles);
  - **Lokoja 2022, which is a RESERVED unit (s1_lokoja_2022)**: its UrbanSARFloods data are not opened.
- Weihui is a DEV diagnostic **outside the registry**. Adding it would change `events.json`, whose SHA256 the pre-registration pins. It was checked read-only with the registry guard against every reserved unit before use.
- Fewer than the 3–5 city events the brief targets: one full-scene urban event is all that is public without an account. Recorded, not padded.

## D11 What the urban test decides, fixed before looking at it
- On Weihui boxes (4 km, centred on flooded-urban pixels by the round-4 box rule), compare:
  - (i) how many FU cells the round-4 Sentinel-1 VV-drop reference (the method behind 10 DEV and 7 RESERVED references) marks as flooded;
  - (ii) the learned model's within-box AUC with FO-only labels vs FO + FU labels.
- **Reading, fixed now:**
  - If the VV-drop method misses most FU cells and the model's AUC falls when FU cells count as flooded, the cropland signal is at least partly a reference blind spot.
  - If the model ranks FU cells as high as FO cells, it is not.
- **Label policy for RESERVED is already fixed** by the pre-registration (§3): primary labels are unchanged. Urban labels can only be a secondary analysis, and none exist for any reserved unit, so the held-out verdicts do not depend on this test.

## D12 DEV units tagged compound (M9)
- valencia_2024 / paiporta (rain + Poyo ravine river + Albufera lagoon level, flood_core screening B1), and the five batch-0 cyclone units with rain and surge documented in their activations: beira (Idai), black_river (Melissa), fort_myers_beach (Ian), kyaukpyu and sittwe (Mocha). New DEV units carry no compound tag (none of their activation texts names two drivers).

## D13 Where a production module competes in the DEV method choice
- A module competes for a type only where its score is defined on every DEV unit of that type. Comparing on a subset would compare a module and the learned model on different events.
- So the pluvial module does not compete for pluvial: its inputs do not exist for the new DEV pluvial units (D8). It is still reported on batch-0 units, and on RESERVED where its inputs build (PREREGISTRATION §4).

## D14 Valencia rain members bracket the storm; neither is "the" forcing
- IMERG V07's largest 24 h total anywhere in the 42 x 26 km domain is 131 mm. AEMET's Turís gauge recorded 771.8 mm in 24 h.
- So member `imerg` is a lower bracket. Member `gauge` (the whole field x 5.87, so that the domain maximum equals Turís) is an upper bracket: it also over-rains the plain, where gauges recorded far less than the core.
- Results are reported for both. A gauge-interpolated field (AEMET station network) would be better; AEMET's open-data API needs a key (an account), so it is skipped (hard stop) and logged.

## D15 (before any reserved data) Which output the AUC verdict uses
- The pre-registration (§4, §6) applies isotonic calibration to the reserved predictions and uses within-event AUC as the primary metric, but does not say which of the two outputs the AUC is computed on.
- Isotonic regression is monotone but piecewise constant: it merges distinct scores into plateaus, which adds ties and can only keep or lower a within-event AUC. The ranking it tests is the model's raw score.
- So the verdict AUC uses the raw score (`learned_raw:<method>`). The calibrated output's AUC is reported beside it, and the calibrated output is what the calibration check (probability vs score) uses.
- Fixed on 2026-11-19, before the freeze tag and before any reserved reference, input or score was read.

## D16 Valencia SFINCS ensemble cut to 4 members (base, gauge, glo30, lidar_e1)
- The base member took 3.5 h (12,733 s wall, 7,401 s solver; 478 MiB peak; 256 MB). That is 11.7 s and 0.23 MB per km², under amd64 emulation, so 10 members would take ~35 h.
- The brief caps a case at ~13 h and forbids running SFINCS and model training together. So the ensemble covers one member per uncertainty dimension (rain bracket, DEM source, LiDAR error) instead of 10 terrain realisations. `lagoon1m`, `lidar_e2` and `lidar_e3` are not run.
- Base result (IMERG lower-bracket rain), max depth vs the EMS AOI03 references: valencia_2024 AUC 0.785 (HAND 0.706), paiporta 0.608 (HAND 0.501). The snapshot at +57 h scores near chance (0.593, 0.499) because most water had drained. EMS "flood trace" polygons are a maximum-extent proxy, so max depth is the comparable field.

## D17 Valencia ensemble result; the coastal/compound SFINCS case is deferred until after the held-out pass
- All 4 Valencia members are done (sfincs/results/valencia_sfincs.json). Max-depth AUC vs the EMS AOI03 references:
  - base: 0.785 / 0.608 (valencia_2024 / paiporta)
  - gauge: 0.834 / 0.651
  - glo30: 0.753 / 0.710
  - lidar_e1: 0.790 / 0.598
  - HAND: 0.706 / 0.501
- Every member beats HAND on both. The gauge member wets 62% of the domain against 16% observed (IoU 0.24), which confirms that it over-rains the plain (D14).
- Wall time per member: 1.4–3.5 h; disk ~0.25 MB per km².
- The coastal/compound case is the critical-path tail:
  - it would take ~13 h of Docker CPU;
  - the brief forbids running it alongside model training;
  - it does not feed the pre-registered method choice or the held-out pass.
- So it runs after Phase 7, on a DEV unit only, with sources that need no account:
  - surge forcing from NOAA CO-OPS water levels (public API, no key), e.g. Fort Myers 8725520 for fort_myers_beach (Ian 2022);
  - the DEM from USGS 3DEP.
- If time runs out it is reported as not done, never as a result.
