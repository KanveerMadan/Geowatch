# Handoff to GeoWatch flood Round 3

Use branch `exp/urban-flood-ref`. Set the data root to `experiments/urban_flood_ref/products`. All incidents are non-US and pre-2022.

1. Start with `manual_refs/` for observed whole-cell inundation. It contains 2,360 flooded and 4,284 dry labels. Sixty-five of the flooded cells are in built-up neighbourhoods. The dry cells are open-ground examples.
2. Use `partial_water_refs/` only for a **water present somewhere in a built-up 30 m cell** target. It contains 444 positive neighbourhoods. Zero coverage and unknown remain unlabelled. These positives overlap the whole-cell examples.
3. `benchmark_refs/` contains 4,529 published positive Weihui cells from a shared radar source. Keep the three tiles in a single incident group. Treat the primary radar `refs/` as candidates and keep the controls out of training.
4. The reader accepts boolean `flooded` and `valid`. Sample only where `valid` is true. Group by `incident`, across data sources and AOIs, before constructing train/test splits.

[Every candidate incident and acquisition](experiments/urban_flood_ref/catalog.csv) · [Every radar file and control](experiments/urban_flood_ref/handoff_manifest.csv) · [Every optical and benchmark label file with counts, licence and checksum](experiments/urban_flood_ref/label_options.csv) · [Reader example](experiments/urban_flood_ref/LOAD.md)
