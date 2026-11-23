# What the radar detector measures

This experiment maps flood-compatible changes at the instant of one Sentinel-1 acquisition. Darkness can indicate smooth open water. In built-up areas some water–wall combinations return more energy to the satellite, with the effect depending on the orientation of the wall. A bright roof can also hide a flooded street. A pixel here describes an apparent scattering change over a radar footprint. Interferometric coherence provides a separate measurement only when complex observations are available. The literature motivates these mechanisms. All numeric operating choices below are hypotheses for this development experiment. [Mason et al.](https://centaur.reading.ac.uk/110425/8/016507_1.pdf) · [Pelich et al.](https://iris.uniroma1.it/bitstream/11573/1578145/2/Pelich_Mapping_2021.pdf) · [UrbanSARFloods](https://openaccess.thecvf.com/content/CVPR2024W/EarthVision/html/Zhao_UrbanSARFloods_Sentinel-1_SLC-Based_Benchmark_Dataset_for_Urban_and_Open-Area_Flood_CVPRW_2024_paper.html)

## Inputs

Supply co-registered VV and VH backscatter in decibels on a square metric grid, using a single post-event acquisition and matched pre-event acquisitions. Validate the acquisition IDs, dates, platform, polarization, imaging mode, relative orbit, pass and usable scene footprint in the acquisition driver. Count distinct acquisitions, including both channels on the same pixels. Combine adjacent slices from one pass before counting dates. Exclude mismatched or missing data. Keep the post date in the output metadata.

`detect` accepts stacks shaped [date, y, x]. `detect_summary` accepts paired pre-event medians, raw median absolute deviations and a per-pixel paired count, followed by both event bands. It computes a noise scale per channel as 1.4826 × MAD, the Gaussian-consistent robust scale estimate. Short or seasonally mismatched histories can underestimate or mischaracterize normal variability. Include a margin of at least 110 m plus one working pixel when computing on adjacent tiles, then crop to the core. Missing external context at a study boundary can suppress a detection.

Supply historical built fraction from 0 to 1, slope in degrees, and historical water occurrence in percent. A supplied terrain visibility mask requires an explicit 1. Use actual radar geometry when available. Slope and a coarse DEM cannot establish which streets are visible between buildings. Exclude permanent water at occurrence ≥80% under the study contract. Record the time span of each ancillary dataset. A retrospective water-history product spanning the event year is inappropriate for a claim of prospective operation.

## Decision rules

Let ΔVV and ΔVH be event minus pre-event median in decibels. Define the VV gate as the greater of 3 dB and 2.5 times its noise scale. Define the VH gate analogously with a 1.5 dB floor.

| Decision | Operating choice and basis |
|---|---|
| Eligible | At least three pre-event dates permit an estimate of temporal spread. Slope ≤10° screens steep terrain where wet-looking imagery may be topographic. Both gates trade coverage for interpretability. Missing required inputs, unsuitable terrain and permanent water produce the unobserved/excluded state. |
| Open-water darkening | Both channels fall by their individual gates. Event VV ≤−16 dB and VH ≤−22 dB. At least one pre-event median must have been brighter than its corresponding level. The absolute levels select a dark end state. The 3 dB change is approximately a halving of VV power, and 1.5 dB requires corroboration in VH. The 2.5 scale multiplier raises the bar in variable pixels. Wind, vegetation and surface roughness can hide water. |
| Urban brightening candidate | Built fraction ≥0.10, ΔVV reaches the VV gate and ΔVV−ΔVH ≥3 dB. The built-fraction floor admits mixed settlement pixels. The differential gate seeks a roughly twofold rise in the co-/cross-polar power ratio and screens simple two-channel brightening. Moisture, storm damage and changes in the scatterers may still mimic it. |
| Optional coherence candidate | Pre-event coherence ≥0.65 and loss ≥0.25 in built pixels. Both inputs must lie in [0,1]. The pair must have a comparable temporal baseline, geometry, polarization and spatial estimation window. The engineering cutoffs seek a previously coherent target and a substantial absolute decline. A coherence drop by itself does not establish floodwater. |
| Spatial support | For each signal separately, the center and at least two other cells in its 3×3 neighborhood must pass. Darkening then qualifies. Urban brightening requires grouped darkening within 110 m or grouped coherence loss at the same location. Grouped coherence loss qualifies with either neighboring grouped darkening or grouped brightening. The 110 m radius is eleven working-grid intervals at 10 m. It gives local context and can miss an isolated flooded street or connect unrelated surface changes. |
| Open-land dry proxy | Require a positive pre-event open-land mask, built fraction <0.10, zero historical occurrence, event VV >−12 dB and VH >−18 dB, both temporal changes <1.5 dB in absolute value, noise scales ≤1.5 dB, and no neighboring grouped wet darkening. These gates reserve dry labels for persistently bright, quiet terrain. The land-cover mask has its own resolution and errors. |
| Independently observed dry | Explicit, geolocated and contemporaneous dry evidence plus quiet radar and no nearby grouped darkening or coherence loss can permit a dry decision even in a built pixel. A supplied dry observation conflicting with a wet anomaly yields ambiguity. Independent evidence used here cannot be reused as the validation target for the same pixels. |

Seasonal wetland changes, vegetation, agriculture, rainfall and construction can generate apparent changes. Date mismatch, speckle and terrain introduce further uncertainty. “Dry” on open land is an evidence-based proxy with errors to be measured. A stable urban radar return on its own yields ambiguity.

## Output and comparison

| Field | Meaning |
|---|---|
| `state` | uint8. 0 unobserved/excluded, 1 dry, 2 flooded candidate, 3 observed but ambiguous. Only 1 and 2 yield binary supervision. |
| `baseline_state` | Same four-state eligibility and conservative dry policy. Only the grouped dual-polarization darkening path supplies positives. The difference reveals the contribution of urban signaling under the same coverage rules. |
| `method` | uint8 bit mask. 1 darkening, 2 urban brightening, 4 grouped coherence loss, 8 stable open land, 16 measured dry, 32 proximity to grouped wet darkening alongside grouped urban evidence. Some bits can occur in ambiguous cells. Interpret them alongside the state. |
| `confidence` | float32 heuristic signal strength. Missing on state 0 and zero on state 3. For a wet cell take the strongest qualifying signal's margin above its change gates. For a dry cell use the limiting quietness margin. Clip the margin to [0,100] and compute m/(1+m). A marginal qualifying signal has score 0.5. No probabilistic calibration is claimed. |
| `urban` | Boolean built-fraction stratification. Apply the state/coverage mask before computing strata or rates. |

An increase in labeled urban pixels measures coverage. Independent event-timed evidence and an accounting of ambiguous and excluded pixels are needed to measure accuracy. Shared terrain, built masks or other predictor inputs create dependence that must be recorded during downstream model evaluation.

## Coherence availability

Earth Engine's Sentinel-1 GRD collection supplies detected power and lacks the phase used by interferometry. VV/VH anomalies or texture are intensity measurements. An external SLC source can supply precomputed coherence to the optional inputs. The UrbanSARFloods authors provide a finite, preprocessed benchmark. Eligibility for a particular event, geometry, licence and independent evaluation must be established separately before accessing its data. [Earth Engine processing guide](https://developers.google.com/earth-engine/guides/sentinel1) · [UrbanSARFloods authors' repository](https://github.com/aliecen/UrbanSARFloods_Dataset)

The synthetic tests exercise darkening, urban corroboration, conflicting dry evidence, isolated speckle, cloud-independent operation, missing channels, open-land opt-in, edge behavior and agreement between the two entry points. They establish the software's response to constructed observations. They provide no estimate of error on real cities.
