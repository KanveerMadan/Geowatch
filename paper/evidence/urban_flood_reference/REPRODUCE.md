# Reproducing the evidence

Run from the repository root in an environment with Python, NumPy, rasterio and affine. The evidence step is offline. Only reviewed DEV product identities are accepted. Preserve the `events`, `refs`, `historical` and `independent` directories beneath the package root.

```sh
python -m unittest discover -s experiments/urban_flood_ref/tests
python -m experiments.urban_flood_ref.handoff --packages "$PACKAGE_ROOT" --out experiments/urban_flood_ref
python paper/evidence/urban_flood_reference/build_evidence.py --packages "$PACKAGE_ROOT" --index experiments/urban_flood_ref/evidence_index.json --out "$EVIDENCE_OUT"
```

The explicit JSON index has one record per eligible package. An event uses `unit=event_id`; a pre-event control uses the same `event_id` and `unit=event_id + "_control"`. Supply `kind` as `event` or `pre_event_control`. Each `references` entry contains a human-readable `name`, `role`, `date` (ISO or unknown), `source` and `path` under `independent/<event_id>/`. The control file is `s2_control.tif`. A unit with no external reference has an empty list. Optional `historical=true` selects the authenticated archived product for that unit. The builder validates the entire index before opening any incident files. With missing data it emits explicit empty metrics. It fails on mismatched grids or checksums and does not resample a reference to conceal misalignment.

The figure and table indices are authoritative for each build. A clean output directory avoids stale reports from a different index. All maps are self-contained SVG with lossless raster panels on the common projected extent. No remote map tiles or fonts are required.

The distributed package root is `experiments/urban_flood_ref/products`. Its SHA256 inventory covers 611 delivered files. The final offline replay used this directory alone, regenerated the handoff manifest, label choices, figure index, tables and figures, and matched the original outputs byte-for-byte. Raw Earth Engine inputs and Maxar source images are unnecessary for that replay.
