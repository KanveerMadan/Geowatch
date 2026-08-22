#!/usr/bin/env python3
"""
GeoWatch Copilot — Mask integrity verification
================================================
Run this AFTER the batch pipeline run, BEFORE annotating any city.

Checks, per city run directory:
    1. masks.json exists and is valid JSON
    2. Every entry has a non-empty mask_rle (not just bbox)
    3. Number of masks.json entries matches segments in result.json
    4. Each mask_rle actually decodes to a boolean array whose shape
       matches its stated "size", and whose runs sum to h*w (a corrupt
       RLE — mismatched run-length sum — would silently produce a
       garbage/blank mask without this check)
    5. Decoded mask area (pixel count) is in the same ballpark as the
       "area" field already stored — catches encode/decode drift early,
       before it's baked into 11 cities of annotations

Usage:
    python verify_masks.py                          # check all runs in data/pipeline_runs
    python verify_masks.py --dir data/pipeline_runs  # explicit dir
    python verify_masks.py --run dharavi_20260702_...  # single run only
"""

import argparse
import json
import os
import sys

# Reuse the exact decoder from segmentation.py so verification uses the
# same logic annotate.py and the notebook will use — no reimplementation
# drift between "what we check" and "what we actually use".
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from ingestion.segmentation import decode_mask_rle
except ImportError:
    print("WARNING: could not import decode_mask_rle from ingestion.segmentation — "
          "falling back to a local copy. Verify this matches your actual encoder.")

    def decode_mask_rle(rle: dict):
        import numpy as np
        h, w = rle["size"]
        counts = rle["counts"]
        flat = np.zeros(h * w, dtype=bool)
        idx = 0
        val = False
        for c in counts:
            if val:
                flat[idx:idx + c] = True
            idx += c
            val = not val
        return flat.reshape(w, h).T


def verify_run(run_dir: str) -> dict:
    """Verify one city's run directory. Returns a report dict."""
    run_id = os.path.basename(run_dir.rstrip("/"))
    report = {"run_id": run_id, "run_dir": run_dir, "ok": True, "issues": []}

    result_path = os.path.join(run_dir, "result.json")
    masks_path = os.path.join(run_dir, "masks.json")

    # ── 1. Files exist ──
    if not os.path.exists(result_path):
        report["ok"] = False
        report["issues"].append("result.json missing")
        return report

    if not os.path.exists(masks_path):
        report["ok"] = False
        report["issues"].append("masks.json missing — pipeline run predates the mask fix, or save_masks() failed")
        return report

    # ── 2. Valid JSON ──
    try:
        with open(result_path) as f:
            result = json.load(f)
    except json.JSONDecodeError as e:
        report["ok"] = False
        report["issues"].append(f"result.json invalid JSON: {e}")
        return report

    try:
        with open(masks_path) as f:
            masks = json.load(f)
    except json.JSONDecodeError as e:
        report["ok"] = False
        report["issues"].append(f"masks.json invalid JSON: {e}")
        return report

    segments = result.get("segments", [])
    n_segments = len(segments)
    n_masks = len(masks)
    report["n_segments"] = n_segments
    report["n_masks"] = n_masks

    # ── 3. Count relationship ──
    # masks.json (raw SAM output) is allowed to have MORE entries than
    # result.json (classified segments) -- classify_tile() in classifier.py
    # deliberately skips segments with bbox w<8 or h<8 (too small for
    # meaningful CLIP classification). This is intentional, not a bug.
    # What's NOT allowed: result.json having a segment with no matching
    # mask entry at all -- that's checked separately below.
    if n_masks < n_segments:
        report["ok"] = False
        report["issues"].append(
            f"masks.json has FEWER entries ({n_masks}) than result.json segments ({n_segments}) "
            f"-- this direction is never expected and means real masks are missing"
        )
    elif n_masks > n_segments:
        report["issues"].append(
            f"masks.json has {n_masks - n_segments} more entries than result.json "
            f"(expected -- likely sub-8px segments filtered by classify_tile(); not an error)"
        )

    # ── 4/5. Per-mask checks ──
    n_missing_rle = 0
    n_decode_fail = 0
    n_area_drift = 0
    masks_by_id = {}

    for m in masks:
        sid = m.get("segment_id")
        masks_by_id[sid] = m

        if "mask_rle" not in m or not m["mask_rle"]:
            n_missing_rle += 1
            continue

        rle = m["mask_rle"]
        try:
            h, w = rle["size"]
            expected_total = h * w
            actual_total = sum(rle["counts"])
            if actual_total != expected_total:
                n_decode_fail += 1
                continue

            decoded = decode_mask_rle(rle)
            if decoded.shape != (h, w):
                n_decode_fail += 1
                continue

            decoded_area = int(decoded.sum())
            stated_area = m.get("area", decoded_area)
            if stated_area > 0:
                drift = abs(decoded_area - stated_area) / stated_area
                if drift > 0.05:  # >5% mismatch between decoded mask and stored area
                    n_area_drift += 1

        except Exception:
            n_decode_fail += 1

    if n_missing_rle:
        report["ok"] = False
        report["issues"].append(f"{n_missing_rle}/{n_masks} masks missing mask_rle entirely")

    if n_decode_fail:
        report["ok"] = False
        report["issues"].append(f"{n_decode_fail}/{n_masks} masks fail to decode or shape-mismatch")

    if n_area_drift:
        report["issues"].append(
            f"{n_area_drift}/{n_masks} masks have >5% area drift between decoded mask and stored 'area' field "
            f"(not fatal, but worth a spot check)"
        )

    # ── Cross-check every segment in result.json actually has a corresponding mask ──
    segment_ids = {s.get("segment_id") for s in segments}
    mask_ids = set(masks_by_id.keys())
    missing_for_segments = segment_ids - mask_ids
    if missing_for_segments:
        report["ok"] = False
        report["issues"].append(
            f"{len(missing_for_segments)} segment_ids in result.json have no matching entry in masks.json: "
            f"{sorted(missing_for_segments)[:10]}{'...' if len(missing_for_segments) > 10 else ''}"
        )

    return report


def find_run_dirs(base_dir: str) -> list:
    """Find all run directories (anything containing a result.json)."""
    run_dirs = []
    if not os.path.isdir(base_dir):
        return run_dirs
    for entry in sorted(os.listdir(base_dir)):
        full = os.path.join(base_dir, entry)
        if os.path.isdir(full) and os.path.exists(os.path.join(full, "result.json")):
            run_dirs.append(full)
    return run_dirs


def main():
    parser = argparse.ArgumentParser(description="Verify masks.json integrity across pipeline runs")
    parser.add_argument("--dir", default="data/pipeline_runs", help="Base directory containing run folders")
    parser.add_argument("--run", default=None, help="Verify a single run directory name only")
    args = parser.parse_args()

    if args.run:
        run_dirs = [os.path.join(args.dir, args.run)]
    else:
        run_dirs = find_run_dirs(args.dir)

    if not run_dirs:
        print(f"No pipeline runs found under {args.dir}")
        sys.exit(1)

    print(f"\n{'='*70}")
    print(f"Verifying {len(run_dirs)} run(s)")
    print(f"{'='*70}\n")

    reports = []
    for run_dir in run_dirs:
        report = verify_run(run_dir)
        reports.append(report)

        status = "✓ OK" if report["ok"] else "✗ ISSUES"
        n_seg = report.get("n_segments", "?")
        n_mask = report.get("n_masks", "?")
        print(f"{status:10s} {report['run_id']:35s} segments={n_seg} masks={n_mask}")
        for issue in report["issues"]:
            print(f"           - {issue}")

    # ── Summary ──
    ok_runs = [r for r in reports if r["ok"]]
    bad_runs = [r for r in reports if not r["ok"]]

    print(f"\n{'='*70}")
    print(f"SUMMARY: {len(ok_runs)}/{len(reports)} runs clean")
    print(f"{'='*70}")

    if bad_runs:
        print(f"\nDO NOT annotate these cities until fixed:")
        for r in bad_runs:
            print(f"  ✗ {r['run_id']}")
        print(f"\nLikely fix: re-run pipeline.py for these cities after confirming "
              f"segmentation.py/pipeline.py changes are actually saved and imported correctly.")
    else:
        print("\nAll runs have valid, complete masks. Safe to start annotating.")

    # Save machine-readable report too
    out_path = os.path.join(args.dir, "mask_verification_report.json")
    with open(out_path, "w") as f:
        json.dump(reports, f, indent=2)
    print(f"\nFull report saved to: {out_path}")

    sys.exit(0 if not bad_runs else 1)


if __name__ == "__main__":
    main()