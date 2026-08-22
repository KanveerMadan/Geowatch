#!/usr/bin/env python3
"""
GeoWatch Copilot — Batch pipeline runner
=========================================
Runs run_pipeline() across all 11 city AOIs in sequence, so you don't have
to babysit 11 manual invocations. Catches per-city failures (GEE timeout,
Overpass 429, no imagery, etc.) so one bad city doesn't kill the whole batch.

FILL IN CITIES BELOW before running — bounding boxes must be (west, south,
east, north) in decimal degrees. Pull these from your original result.json
files (the "aoi" field) if you want the same AOIs as your first 3-5 city runs.

Usage:
    python run_all_cities.py                  # run all cities
    python run_all_cities.py --only dharavi nairobi   # run a subset
    python run_all_cities.py --skip jakarta    # run all except these
"""

import argparse
import json
import os
import time
import traceback
from datetime import datetime

from pipeline import run_pipeline

# ============================================================
# Real AOIs — pulled directly from each city's existing (pre-fix)
# result.json "aoi" field, so the re-run covers the exact same
# ground truth area as your original annotations. Do not edit
# unless you intend to change the AOI.
# Format: "label": (west, south, east, north)
# ============================================================
CITIES = {
    "dharavi":   (72.836,  19.037,  72.862,  19.060),    # dharavi_20260629_122047
    "nairobi":   (36.778,  -1.318,  36.812,  -1.284),    # nairobi_20260629_125735
    "jakarta":   (106.78,  -6.13,   106.85,  -6.08),     # jakarta_20260629_131228
    "hcmc":      (106.58,  10.78,   106.68,  10.88),     # hcmc_20260629_142501
    "kigali":    (30.058,  -1.975,  30.082,  -1.952),    # kigali_20260629_134131
    "accra":     (-0.225,  5.54,    -0.19,   5.57),      # accra_20260701_133652
    "dhaka":     (90.385,  23.765,  90.425,  23.795),    # dhaka_20260701_133207
    "lagos":     (3.37,    6.475,   3.41,    6.51),      # lagos_20260701_133536
    "capetown":  (18.66,   -34.075, 18.71,   -34.03),    # capetown_20260701_133746
    "guatemala": (-90.54,  14.61,   -90.5,   14.65),     # guatemala_20260701_133908
    "nusantara": (116.7,   -1.0,    116.76,  -0.945),    # nusantara_20260701_152835
}

OUTPUT_DIR = "data/pipeline_runs"
LOG_PATH = "data/pipeline_runs/batch_run_log.json"


def run_batch(cities_to_run: dict, start_date: str = None, end_date: str = None,
              cloud_cover_threshold: int = 20):
    results_log = []
    print(f"\n{'#'*60}")
    print(f"# GeoWatch batch run — {len(cities_to_run)} cities")
    if start_date and end_date:
        print(f"# Date range: {start_date} to {end_date} (manual)")
    else:
        print(f"# Date range: latest 90 days (auto)")
    print(f"# Cloud cover threshold: {cloud_cover_threshold}%")
    print(f"{'#'*60}\n")

    for i, (label, bbox) in enumerate(cities_to_run.items(), 1):
        west, south, east, north = bbox
        print(f"\n{'='*60}")
        print(f"[{i}/{len(cities_to_run)}] Starting: {label}")
        print(f"AOI: {bbox}")
        print(f"{'='*60}")

        entry = {
            "city": label,
            "bbox": bbox,
            "started_at": datetime.now().isoformat(),
        }

        t0 = time.time()
        try:
            result = run_pipeline(
                west=west, south=south, east=east, north=north,
                start_date=start_date,
                end_date=end_date,
                cloud_cover_threshold=cloud_cover_threshold,
                aoi_label=label,
                output_dir=OUTPUT_DIR,
            )
            elapsed = time.time() - t0
            entry.update({
                "status": result.get("status", "unknown"),
                "run_id": result.get("run_id"),
                "elapsed_seconds": round(elapsed, 1),
                "total_segments": result.get("summary", {}).get("total_segments"),
                "error": result.get("error"),
            })
            print(f"\n✓ {label} done in {elapsed:.1f}s — status: {entry['status']}")

        except Exception as e:
            elapsed = time.time() - t0
            entry.update({
                "status": "exception",
                "elapsed_seconds": round(elapsed, 1),
                "error": str(e),
                "traceback": traceback.format_exc(),
            })
            print(f"\n✗ {label} FAILED after {elapsed:.1f}s: {e}")
            print("Continuing to next city...")

        results_log.append(entry)

        # Save log after every city — crash-safe, same philosophy as annotate.py
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "w") as f:
            json.dump(results_log, f, indent=2)

    # ── Final summary ──
    print(f"\n{'#'*60}")
    print("# BATCH RUN SUMMARY")
    print(f"{'#'*60}")
    ok = [r for r in results_log if r["status"] == "complete"]
    failed = [r for r in results_log if r["status"] != "complete"]

    print(f"\nCompleted: {len(ok)}/{len(results_log)}")
    for r in ok:
        print(f"  ✓ {r['city']:12s} run_id={r['run_id']}  segments={r['total_segments']}  {r['elapsed_seconds']}s")

    if failed:
        print(f"\nFailed: {len(failed)}/{len(results_log)}")
        for r in failed:
            print(f"  ✗ {r['city']:12s} status={r['status']}  error={r['error']}")

    print(f"\nFull log saved to: {LOG_PATH}")
    return results_log


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch-run GeoWatch pipeline across cities")
    parser.add_argument("--only", nargs="+", help="Only run these city labels")
    parser.add_argument("--skip", nargs="+", help="Skip these city labels")
    parser.add_argument("--start", type=str, default=None,
                        help="Explicit start date YYYY-MM-DD. Use when a city has no "
                             "cloud-free imagery in the latest-90-days auto window "
                             "(e.g. rainy season) — omit for auto mode.")
    parser.add_argument("--end", type=str, default=None,
                        help="Explicit end date YYYY-MM-DD. Must be paired with --start.")
    parser.add_argument("--cloud-threshold", type=int, default=20,
                        help="Max CLOUDY_PIXEL_PERCENTAGE per Sentinel-2 image (default 20). "
                             "Raise to 40-60 for persistently cloudy AOIs (e.g. equatorial "
                             "regions like Lagos, Nusantara) where 0 images pass the default.")
    args = parser.parse_args()

    if (args.start is None) != (args.end is None):
        print("Error: --start and --end must be provided together.")
        exit(1)

    cities_to_run = dict(CITIES)

    if args.only:
        missing = [c for c in args.only if c not in CITIES]
        if missing:
            print(f"Unknown city labels: {missing}. Available: {list(CITIES.keys())}")
            exit(1)
        cities_to_run = {k: v for k, v in CITIES.items() if k in args.only}

    if args.skip:
        cities_to_run = {k: v for k, v in cities_to_run.items() if k not in args.skip}

    run_batch(cities_to_run, start_date=args.start, end_date=args.end,
              cloud_cover_threshold=args.cloud_threshold)