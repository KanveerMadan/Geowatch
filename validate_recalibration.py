"""
Final validation of the recalibrated CAAT thresholds.

Does NOT touch caat_thresholds.json (production file untouched). Just runs
the real, full run_inference() pipeline -- the exact function pipeline.py
calls in production -- twice per tile: once with the OLD thresholds, once
with the NEW (recalibrated) ones. Reports unknown% for both, side by side,
on every tile you pass in.

USAGE:
    python validate_recalibration.py <checkpoint_path> <tile_path> [<tile_path> ...]

Example (Cape Town + Dharavi, the two tiles used earlier this session):
    python validate_recalibration.py \
      models/production/geowatch_production_model.pth \
      data/pipeline_runs/capetown_20260702_164022/tiles/tile_0_0.png \
      data/pipeline_runs/dharavi_20260702_163012/tiles/tile_0_0.png

Reads thresholds from:
    models/production/caat_thresholds.json               (OLD, current production)
    models/production/caat_thresholds_recalibrated.json   (NEW, from recalibrate_caat.py)
"""

import sys
import json
import numpy as np

sys.path.insert(0, ".")

from ingestion.inference import load_production_model, run_inference, PATCH_SIZE


OLD_CAAT_PATH = "models/production/caat_thresholds.json"
NEW_CAAT_PATH = "models/production/caat_thresholds_recalibrated.json"


def load_thresholds_array(path: str, categories: list) -> np.ndarray:
    with open(path) as f:
        data = json.load(f)
    raw = data["thresholds"]
    return np.array([raw[c] for c in categories], dtype=np.float32)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    checkpoint_path = sys.argv[1]
    tile_paths = sys.argv[2:]

    print("=" * 70)
    print("Loading model...")
    model, categories, num_classes = load_production_model(checkpoint_path)

    old_thresholds = load_thresholds_array(OLD_CAAT_PATH, categories)
    new_thresholds = load_thresholds_array(NEW_CAAT_PATH, categories)

    results = []

    for tile_path in tile_paths:
        print("\n" + "=" * 70)
        print(f"TILE: {tile_path}")

        print("\n--- OLD (isolated-patch-calibrated) thresholds ---")
        old_result = run_inference(
            tile_path, model, categories, old_thresholds,
            patch_size=PATCH_SIZE, stride=PATCH_SIZE // 2,
        )

        print("\n--- NEW (sliding-window-recalibrated) thresholds ---")
        new_result = run_inference(
            tile_path, model, categories, new_thresholds,
            patch_size=PATCH_SIZE, stride=PATCH_SIZE // 2,
        )

        delta = old_result["unknown_pct"] - new_result["unknown_pct"]
        results.append({
            "tile": tile_path,
            "old_unknown_pct": old_result["unknown_pct"],
            "new_unknown_pct": new_result["unknown_pct"],
            "delta": delta,
        })

        print(f"\n  unknown%  OLD: {old_result['unknown_pct']:.2f}%   "
              f"NEW: {new_result['unknown_pct']:.2f}%   "
              f"DROP: {delta:+.2f} percentage points")

    print("\n" + "=" * 70)
    print("SUMMARY -- all tiles")
    print(f"  {'tile':<70} {'old%':>8} {'new%':>8} {'drop':>8}")
    for r in results:
        print(f"  {r['tile']:<70} {r['old_unknown_pct']:8.2f} "
              f"{r['new_unknown_pct']:8.2f} {r['delta']:+8.2f}")

    mean_old = np.mean([r["old_unknown_pct"] for r in results])
    mean_new = np.mean([r["new_unknown_pct"] for r in results])
    print(f"\n  Mean unknown%: OLD {mean_old:.2f}%  ->  NEW {mean_new:.2f}%  "
          f"(drop of {mean_old - mean_new:.2f} points)")

    print("\nNOTE: NEW thresholds were calibrated on pooled labeled pixels from")
    print("these same annotated tiles (plus 9 others), so this number is a")
    print("consistency check, not independent held-out validation -- the true")
    print("unknown% on a genuinely new AOI (e.g. a fresh, unannotated run) may")
    print("differ somewhat. Still, this confirms whether the recalibration")
    print("does what it's supposed to do on the data we have.")


if __name__ == "__main__":
    main()