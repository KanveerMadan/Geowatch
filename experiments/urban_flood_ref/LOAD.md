# Loading development references

Each event has `events/<unit>/reference_10m.tif`, `reference_30m.tif`, `manifest.json` and an exact copy of the model input at `refs/<unit>.npz`. The GeoTIFFs have the same upper-left corner, footprint and projected CRS. Each 30 m cell contains nine aligned 10 m cells. A 10 m pixel spacing describes the sampling grid. Adjacent SAR samples share a larger radar response.

Read the compatibility array with the existing flood-final semantics.

```python
import json
import numpy as np

with np.load(reference_path, allow_pickle=False) as z:
    meta = json.loads(str(z["meta"]))
    flooded, valid = z["flooded"], z["valid"]
    labels = np.full(valid.shape, -1, dtype=np.int8)
    labels[valid] = flooded[valid].astype(np.int8)
```

The two Boolean arrays have shape `meta["grid"]["shape"]`. Label 1 is confidently flooded, 0 is confidently dry and −1 is unavailable for training. `valid` includes only these two confident classes. The scientific maps retain *why* other cells were withheld. The existing learned model intersects `valid` with its own permanent-water mask before training. A unit whose confident cells contain only one class can support descriptive evidence. Include both classes and independently checked examples before fitting or evaluating a binary classifier.

The NPZ is compatible with `experiments.flood_baselines.events.reference` and `experiments.flood_learned.events.labels` on flood-final commit `1c3fa9c470d87759e1d4184ebf1f8f17e88a3c50`. The flood session owns future integration. To rehearse a load, construct an entry with `{"unit": unit, "path": str(reference_path), "meta": meta, "round": "flood_final", "split": "dev", "modules": [], "uses": []}`. Its normal `build_units.entry` additionally requires a registered DEV identifier and reads `flood_learned/heldout/refs/<unit>.npz` under the flood cache. For retraining, register a distinct derivative identifier through that session, keep the incident and spatial group of its original, and use the corresponding reference filename. The cached build, feature table and split logic key on unit name. Keep variations of one flood in the same fold. The three Weihui windows represent one incident. Control runs are diagnostic products with a `_control` suffix. The machine-readable manifests identify their role. Existing archived labels, fitted models and reserved data are separate.

## Scientific bands

All bands use float32 for a common lossless GeoTIFF layout. Read categorical fields as integer codes. The nodata sentinel is −9999. The state band uses 0 unobserved/excluded, 1 confidently dry, 2 confidently flooded, 3 ambiguous. The confidence band is an uncalibrated evidence score. The method bitmask uses 1 for darkening, 2 for urban VV brightening, 4 for verified coherence loss, 8 for stable open-ground dry evidence, 16 for independently measured dry support and 32 for nearby water-darkening support. Method bits can describe inconclusive evidence in ambiguous cells. A method bit alone is insufficient for a training label. The `baseline_state` band is the matched intensity-only ablation. The `urban` band identifies the detector’s urban stratum.

The observed and flooded fractions use all nine children as the denominator. Unobserved area contributes no confidently mapped flood, and its status remains explicit in the observed fraction. For 30 m confidence, all nine children must have observations, at least five must agree on wet or dry and none may carry the opposite confident state. Otherwise the cell is ambiguous, or unobserved if all nine are unobserved. The five-cell requirement is a strict native-pixel majority. The full observation and zero-conflict requirements protect training labels at boundaries. The 30 m urban stratum also uses a strict majority.

Pre-first, pre-last and post dates are integer UTC days since 1970-01-01. A median pre-event radar composite spans several dates. The pre bands give the earliest and latest valid contributing pre-scene for each pixel. If date coverage is incomplete, its bounds stay unknown. Time from peak is signed days only when an independently sourced peak date is supplied. The event anchor and its offset are separate metadata. Failed scene acquisition cannot supply a dry label.

The manifest carries the input dates and source lineage, grid, confidence summary and SHA256 of each artifact. A publish interrupted between the event directory and the downstream link can resume with `recover_reference(package_root, unit)`. This checks all three files before restoring the link. Verify manifest digests when copying outputs across systems.

These are experimental development labels. Feature and label provenance matter: a classifier offered the same SAR-change, built-up and water-history inputs used by the reference generator may reproduce the reference recipe. Test performance against independently interpreted change observations in different incidents.
