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
