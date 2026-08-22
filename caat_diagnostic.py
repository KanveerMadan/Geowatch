"""
CAAT recalibration diagnostic — tests Hypothesis A from the session summary:

    "CAAT thresholds were computed from isolated single-patch forward passes,
    but production inference does sliding-window overlapping-window
    softmax-averaged inference, which systematically lowers confidence."

ASSUMPTION (flag if wrong): this script imports run_inference() from
ingestion/inference.py (the module whose docstring/aggregation logic matches
the master prompt's description of what pipeline.py actually calls). A second,
non-identical module (resnet_classifier.py, run_pixel_inference()) also exists
in the repo with a different load_production_model() signature. If pipeline.py
actually imports resnet_classifier.py instead, re-run this diagnostic against
that module's functions — the averaging math is equivalent so results should
match, but confirm before trusting this output as authoritative.

USAGE:
    python caat_diagnostic.py <tile_path> <checkpoint_path> <caat_json_path>

Example:
    python caat_diagnostic.py \
        data/pipeline_runs/capetown_20260702_164022/tiles/tile_0_0.png \
        models/production/geowatch_production_model.pth \
        models/production/caat_thresholds.json

WHAT IT DOES:
  1. Runs inference TWICE on the same tile:
       (a) "production" mode  — stride = patch_size // 2 (current live config,
           overlapping windows, softmax-averaged)
       (b) "isolated" mode    — stride = patch_size (no overlap — each pixel
           covered by exactly one window, closest approximation to how CAAT
           was originally computed from single-patch forward passes)
  2. For every pixel currently flagged `unknown` in production mode, looks up
     its confidence under isolated mode and reports how close it sits to its
     class's CAAT threshold.
  3. Reports whether unknown-flagged pixels cluster just below threshold
     (supports Hypothesis A) or are low-confidence under both modes
     (points away from it — more consistent with Hypothesis B, missing
     category / genuine uncertainty).
  4. Sweeps candidate thresholds and reports unknown% at each, so you have a
     defensible "unknown% vs. threshold" table/number for the panel.

This script does NOT modify caat_thresholds.json or retrain anything — it's
read-only diagnostics. Any recalibration decision based on this output is a
separate, deliberate follow-up step.
"""

import sys
import json
import numpy as np

sys.path.insert(0, ".")  # run from geowatch/ repo root

from ingestion.inference import (
    load_production_model,
    load_caat_thresholds,
    run_inference,
    PATCH_SIZE,
)


def confidence_histogram(conf_values: np.ndarray, thresholds_used: np.ndarray, bins=10):
    """Bucket (confidence - own_threshold) to see clustering near zero."""
    diffs = conf_values - thresholds_used
    hist, edges = np.histogram(diffs, bins=bins)
    print("\n  Distance-to-threshold histogram (confidence - own CAAT threshold):")
    print("  (negative = below threshold i.e. correctly flagged unknown here;")
    print("   values near 0 from below = 'just missed it')")
    for i in range(len(hist)):
        bar = "#" * int(60 * hist[i] / max(hist.max(), 1))
        print(f"    [{edges[i]:+.3f}, {edges[i+1]:+.3f}) {hist[i]:7d}  {bar}")


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)

    tile_path, checkpoint_path, caat_path = sys.argv[1:4]

    print("=" * 70)
    print("Loading model + CAAT thresholds...")
    model, categories, num_classes = load_production_model(checkpoint_path)
    caat_thresholds = load_caat_thresholds(caat_path, categories)

    print("\n" + "=" * 70)
    print("PASS 1/2: production-config inference (stride = patch_size // 2, overlapping)")
    prod_result = run_inference(
        tile_path, model, categories, caat_thresholds,
        patch_size=PATCH_SIZE, stride=PATCH_SIZE // 2,
    )

    print("\n" + "=" * 70)
    print("PASS 2/2: isolated-patch inference (stride = patch_size, no overlap)")
    iso_result = run_inference(
        tile_path, model, categories, caat_thresholds,
        patch_size=PATCH_SIZE, stride=PATCH_SIZE,
    )

    prod_map, prod_conf = prod_result["landcover_map"], prod_result["confidence_map"]
    iso_map, iso_conf = iso_result["landcover_map"], iso_result["confidence_map"]
    UNKNOWN_INDEX = 255

    print("\n" + "=" * 70)
    print("HEADLINE NUMBERS")
    print(f"  Production (overlapping, averaged) unknown%: {prod_result['unknown_pct']:.2f}%")
    print(f"  Isolated (no overlap)             unknown%: {iso_result['unknown_pct']:.2f}%")
    delta = prod_result['unknown_pct'] - iso_result['unknown_pct']
    print(f"  Difference: {delta:+.2f} percentage points")
    if delta > 5:
        print("  -> Sliding-window averaging is meaningfully INCREASING the unknown rate.")
        print("     This supports Hypothesis A (CAAT/inference-mode mismatch).")
    elif delta < -5:
        print("  -> Isolated mode actually has MORE unknowns than production. Unexpected —")
        print("     re-check window coverage/edge handling before concluding anything.")
    else:
        print("  -> Difference is small. Hypothesis A is likely NOT the primary driver")
        print("     of the ~50% unknown rate — points toward Hypothesis B (missing")
        print("     category / genuine model uncertainty) as the bigger factor.")

    # Pixels flagged unknown in PRODUCTION mode — what does isolated mode say about them?
    prod_unknown_mask = (prod_map == UNKNOWN_INDEX)
    n_prod_unknown = int(prod_unknown_mask.sum())
    print(f"\n  Pixels unknown in production mode: {n_prod_unknown}")

    if n_prod_unknown > 0:
        iso_conf_at_prod_unknown = iso_conf[prod_unknown_mask]
        # own threshold = the threshold for whatever class production predicted
        # before being CAAT-rejected. We don't have prod's pre-threshold class
        # directly (landcover_map already collapsed it to 255), so recompute:
        prod_conf_at_prod_unknown = prod_conf[prod_unknown_mask]

        recovered_in_iso = int((iso_map[prod_unknown_mask] != UNKNOWN_INDEX).sum())
        pct_recovered = 100.0 * recovered_in_iso / n_prod_unknown
        print(f"  Of those, {recovered_in_iso} ({pct_recovered:.1f}%) become CONFIDENT "
              f"(non-unknown) under isolated-patch inference.")
        if pct_recovered > 30:
            print("  -> Strong support for Hypothesis A: a large share of 'unknown' pixels")
            print("     are only unknown because of window-averaging, not genuine uncertainty.")
        else:
            print("  -> Most of these pixels remain unknown even without averaging —")
            print("     suggests genuine low confidence, not a calibration artifact.")

        print(f"\n  Confidence comparison for production-unknown pixels:")
        print(f"    mean production confidence: {prod_conf_at_prod_unknown.mean():.4f}")
        print(f"    mean isolated  confidence: {iso_conf_at_prod_unknown.mean():.4f}")

    # Threshold sweep on production-mode (sliding-window-averaged) confidences.
    # run_inference() only returns the post-CAAT map + winning-class confidence,
    # not raw per-class mean_probs, so the cleanest way to sweep is to re-run
    # with a flat candidate threshold substituted for the real per-class CAAT
    # array each time. This is a flat/uniform threshold for a simple,
    # presentable curve — not a proposal to replace per-class CAAT itself.
    print("\n" + "=" * 70)
    print("THRESHOLD SWEEP (production/sliding-window confidences, flat threshold)")
    print("  (real CAAT thresholds vary 0.595-0.992 per class; this sweep applies")
    print("   one flat candidate threshold across all classes for a simple curve)")
    for cand in [0.30, 0.40, 0.50, 0.60, 0.70]:
        flat_thresholds = np.full(num_classes, cand, dtype=np.float32)
        sweep_result = run_inference(
            tile_path, model, categories, flat_thresholds,
            patch_size=PATCH_SIZE, stride=PATCH_SIZE // 2,
        )
        print(f"    flat threshold {cand:.2f} -> unknown% = {sweep_result['unknown_pct']:.2f}%")

    # Distance-to-threshold histogram for production-unknown pixels. Since
    # run_inference() doesn't expose each pixel's specific predicted class
    # (only its confidence), we approximate "own threshold" as the mean CAAT
    # threshold across classes. This is coarse — a class-exact version would
    # require modifying run_inference() to also return predicted_idx — but is
    # good enough to see whether confidences cluster near the threshold band.
    if n_prod_unknown > 0:
        approx_threshold = np.full(n_prod_unknown, float(np.mean(caat_thresholds)), dtype=np.float32)
        confidence_histogram(prod_conf[prod_unknown_mask], approx_threshold)

    print("\n" + "=" * 70)
    print("Done. Recommended next step based on the headline delta above:")
    print("  - If delta was large / recovery% was high: rebuild caat_thresholds.json")
    print("    using confidences computed under the PRODUCTION sliding-window config,")
    print("    not isolated patches (this is the actual fix for Hypothesis A).")
    print("  - If delta was small: treat the ~50% unknown rate as reflecting real")
    print("    model uncertainty / Hypothesis B (missing category, e.g. formal")
    print("    housing), and prioritize that investigation instead.")


if __name__ == "__main__":
    main()