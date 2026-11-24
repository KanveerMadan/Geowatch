# Urban flood reference maps for GeoWatch

**The study produced usable historical training observations. The new radar detector still misses most confirmed urban flooding.** Its strongest independent test was in San Pedro Sula. On the same day as the radar pass, published human interpretations of 3 m optical images showed 64 completely wet 30 m cells in built-up neighbourhoods. Radar found **1 of 64**. Keep the optical observations for development and keep the radar-only maps in review.

## What Claude Code can use

| Product | Delivered result | Appropriate use |
|---|---:|---|
| Whole-cell optical labels | 2,360 flooded and 4,284 dry 30 m cells across the screened optical chips | Development labels for visible inundation. Sixty-five flooded cells are in the study’s built-up stratum. The dry labels are restricted to open ground. |
| Partial-cell optical labels | 444 positive 30 m neighbourhoods with at least one completely wet 10 m patch in their built-up portion | Train for **some visible flooding within a neighbourhood** if this is the intended target. Unknown everywhere else. These overlap the whole-cell product. |
| Published Weihui urban benchmark | 4,529 positive cells in three previously used tiles from one storm | Optional shared-radar development labels. Using them for training consumes Weihui as a test. |
| Radar candidates | 36 event tiles from 29 non-US storms in 21 countries, with 10 m and 30 m maps | Incident review, diagnostics and future comparison. Each date, orbit and confidence score travels with its map. |
| Pre-event controls | 37 control tiles | Measure repeat detections and compare to independently visible dry surfaces. Exclude from event training. |

All 30 nominated storms occurred before 2022. Bima had a usable control acquisition but no qualifying event acquisition. The six original development tiles and the eight supplemental optical footprints include multiple tiles from the same storms. Each incident counts once. [Event catalogue](experiments/urban_flood_ref/catalog.csv)

The human optical labels used 3 m PlanetScope interpretations from the Urban Flood Observations dataset. Each accepted wet patch required repeated clear-land observations before the event, a known nonpermanent-water history and agreement across the full patch. San Pedro Sula contributed 379 partial-cell positives, Khartoum 40 and Beira 25. Both Can Tho footprints lost all usable labels after screening. Optical imagery can show water exposed between buildings, while roofs can obscure the street below. [Source-specific labels and checksums](experiments/urban_flood_ref/label_options.csv) · [Original annotations](https://doi.org/10.5281/zenodo.19698577)

## What the radar experiment established

- On the 36 event tiles, the detector flagged **234 urban cells**. Its urban brightening rule added **203 candidates** to its own matched darkening baseline. Candidate additions alone do not establish that those cells flooded.
- In Weihui, it recovered **14 of 4,529** published urban-flood cells (0.31%). The matched darkening baseline recovered zero. The actual archived intensity map recovered **107 of 4,529** (2.36%). The 14 newly found cells were outside the archive’s hits. Replacing the archive would lose its 107 hits. The benchmark uses the same satellite, and the three boxes were chosen for their flood content.
- In independent human-interpreted optical data, **64** urban wet cells had a same-day radar observation in San Pedro Sula, which yielded one detection. Khartoum contributed one additional wet urban cell with a one-day mismatch, which radar missed. None of those sites had a defensible urban-dry label under the optical training definition.
- On control dates, radar flagged **12 of 303,484 observed urban cells** (0.004%). Among **56,730** control cells separately identified as visible non-water by Sentinel-2 near the radar dates, it flagged **zero**. The method also emitted **zero confident urban-dry labels**. Most urban cells were ambiguous. These denominators describe detection burden and visible-surface checks; they cannot establish general street-level accuracy.
- The per-event tables report both coverage and agreement, with uncertainty from spatial blocks within a tile. Date offsets are shown for every reference where available. No new held-out flood was scored. [Evidence, tables and maps](paper/evidence/urban_flood_reference/README.md)

## What very-high-resolution imagery added

**Beira, Cyclone Idai (2019).** Two blinded AI readers inspected nine fixed cells in the March 4 and March 26 Maxar images. March 26 matched the radar date, eleven days after the incident anchor. Both readers could identify exposed dry surfaces in two cells. They agreed on zero newly flooded cells. Seven stayed unknown, including one possible flood on which they disagreed. The interpretations are development diagnostics under the Maxar noncommercial terms. [Beira review](experiments/urban_flood_ref/MAXAR_BEIRA.md)

**Marsh Harbour, Hurricane Dorian (2019).** The September 5 image covered all nine sample locations. The April 17 image had no usable pixels in any of the nine, despite its catalogue footprint. The September image also arrived three days after radar. All nine pairs stayed unknown. [Dated review receipt](experiments/urban_flood_ref/products/independent/marsh_harbour_2019/maxar_review.json)

A local river gauge and a flooded street can peak at different times. For example, radar arrived roughly 115 hours after the Marikina city-gauge crest and 111 hours after the gauge crest near Nagano. The maps preserve unknown peak lag wherever a tile-wide peak could not be established. [Gauge checks](experiments/urban_flood_ref/verified_peaks.json)

## Training handoff

Start with the independent optical labels. Load `flooded` only where `valid` is true, preserve unknowns through sampling, and group every tile, source and control from an incident together. Keep the partial-cell and whole-cell targets separate. The next evidence gap is independently observed **dry, visible urban streets** paired with flooded streets at the same acquisition time. The 4,284 open-ground negatives do not fill that gap. No flood model was retrained. [Short handoff](HANDOFF.md) · [Loader and data contract](experiments/urban_flood_ref/LOAD.md)
