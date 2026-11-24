# Urban flood development references

Start with [the handoff](HANDOFF.md), [label choices](label_options.csv) and [the report](../../REPORT.md). The distributed package is in [products](products). From the repository root, use `experiments/urban_flood_ref/products` as the package root. Files in the manifests are relative to this directory.

| Directory | Meaning |
|---|---|
| `manual_refs/` | Previously dry, then visibly wet areas from published human interpretations of 3 m PlanetScope images, plus conservatively supported open-ground negatives. |
| `partial_water_refs/` | Positive-only presence of at least one 10 m newly wet patch in the built-up portion of a 30 m neighbourhood. Keep this target distinct from whole-cell inundation. |
| `benchmark_refs/` | Published radar-based Weihui urban flood positives for development. One storm across three enriched boxes. |
| `refs/`, `events/` | Experimental radar maps and pre-event controls. The model-format NPZ keeps confidently wet and dry cells. The two GeoTIFFs retain all four states. |
| `independent/`, `historical/` | Time-stamped evidence and original intensity comparator where available. Consult source-specific terms and timing. |

The receiving team can check the hashes in `products/SHA256.json` and use the model reader described in [LOAD.md](LOAD.md). Keep all tiles and label sources from each incident together in a train/development split. Receipts identify source, licence, timing and the meaning of each class. Confidence scores are uncalibrated. Grouping by incident prevents a Beira optical chip from becoming a test for a model trained on a neighbouring Beira tile.

## Reproduce

Use Python 3.12 and the packages in `requirements.txt`. Offline evidence can be rebuilt from the published package. [Evidence instructions](../../paper/evidence/urban_flood_reference/REPRODUCE.md)

To rebuild satellite measurements, the caller supplies an already-authorized Earth Engine project through `GEE_PROJECT_ID`. The historical guard reads the pinned registry before opening data. `batch` runs the SAR and independent Sentinel-2 computations serially and resumes from the per-product manifests. Example for one development unit:

```sh
python -m experiments.urban_flood_ref.batch --output /tmp/geowatch-urban-dev usf_weihui_1
```

On macOS, prepend `caffeinate -i` for long runs. New historical images, including an additional train/test split, require a new guard review. The catalogue uses documented incident reports and the flood registries; scene availability and an observed urban flood are separate outcomes. See [catalogue](catalog.csv), [sources](SOURCES.md), and [decisions](../../DECISIONS.md).
