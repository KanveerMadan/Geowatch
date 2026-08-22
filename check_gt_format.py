"""
Checks, for every city run under data/pipeline_runs/, whether you already
have a dense per-pixel ground-truth label map, or only segment-level
annotations (masks.json + annotations.json) that would need to be
rasterized into one.

USAGE (run from geowatch/ repo root):
    python check_gt_format.py

For each <city>_<timestamp> run directory found, prints:
  - whether raw.tif exists, and its (H, W)
  - whether any file that LOOKS like a dense label map exists (common
    names: label_map.png, gt_mask.png, dense_labels.png, segmentation_gt.*,
    or any single-channel PNG whose size matches raw.tif exactly)
  - if masks.json + annotations.json exist: how many segments have a
    human_label, and what % of the raster's total pixel area those
    labeled segments cover (this tells you how sparse (b)-style
    rasterization would be)

This does NOT modify or create anything -- read-only inspection.
"""

import os
import re
import json
import glob
import numpy as np

try:
    import rasterio
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

from PIL import Image


PIPELINE_RUNS_DIR = "data/pipeline_runs"

DENSE_LABEL_NAME_HINTS = [
    "label_map", "gt_mask", "dense_label", "segmentation_gt",
    "gt.png", "ground_truth", "dense_gt",
]


def get_raster_size(run_dir: str):
    raw_path = os.path.join(run_dir, "raw.tif")
    if not os.path.exists(raw_path):
        return None
    if HAS_RASTERIO:
        with rasterio.open(raw_path) as src:
            return src.height, src.width
    else:
        # Fallback: PIL can usually open single/few-band GeoTIFFs enough
        # to read size, though not all band configs.
        try:
            with Image.open(raw_path) as im:
                w, h = im.size
                return h, w
        except Exception:
            return None


def find_dense_label_candidates(run_dir: str, raster_hw):
    candidates = []
    for path in glob.glob(os.path.join(run_dir, "**", "*"), recursive=True):
        if not os.path.isfile(path):
            continue
        fname = os.path.basename(path).lower()
        name_hint_hit = any(hint in fname for hint in DENSE_LABEL_NAME_HINTS)

        size_match = False
        if raster_hw is not None and path.lower().endswith((".png", ".tif", ".tiff")):
            try:
                with Image.open(path) as im:
                    w, h = im.size
                    if (h, w) == raster_hw:
                        size_match = True
            except Exception:
                pass

        if name_hint_hit or size_match:
            candidates.append((path, name_hint_hit, size_match))
    return candidates


def segment_annotation_coverage(run_dir: str, raster_hw):
    ann_path = os.path.join(run_dir, "annotations.json")
    masks_path = os.path.join(run_dir, "masks.json")
    if not (os.path.exists(ann_path) and os.path.exists(masks_path)):
        return None

    with open(ann_path) as f:
        ann_data = json.load(f)
    anns = ann_data.get("annotations", ann_data) if isinstance(ann_data, dict) else ann_data
    if isinstance(anns, dict):
        anns = anns.get("annotations", [])

    with open(masks_path) as f:
        masks = json.load(f)

    # Build segment_id -> area lookup from masks.json (has 'area' field
    # per the Cape Town schema already confirmed)
    area_by_segment = {}
    for m in masks:
        seg_id = m.get("segment_id")
        if seg_id is not None:
            area_by_segment[seg_id] = m.get("area", 0)

    total_segments = len(anns)
    labeled_segments = 0
    labeled_area = 0
    skipped = 0

    for a in anns:
        seg_id = a.get("segment_id")
        human_label = a.get("human_label")
        if a.get("skipped"):
            skipped += 1
            continue
        if human_label:
            labeled_segments += 1
            labeled_area += area_by_segment.get(seg_id, 0)

    total_raster_px = None
    if raster_hw is not None:
        total_raster_px = raster_hw[0] * raster_hw[1]

    pct_area_labeled = (
        round(100.0 * labeled_area / total_raster_px, 2)
        if total_raster_px else None
    )

    return {
        "total_annotation_records": total_segments,
        "labeled_segments": labeled_segments,
        "skipped_segments": skipped,
        "labeled_pixel_area": labeled_area,
        "total_raster_pixels": total_raster_px,
        "pct_raster_area_labeled": pct_area_labeled,
    }


def main():
    if not os.path.isdir(PIPELINE_RUNS_DIR):
        print(f"'{PIPELINE_RUNS_DIR}' not found -- run this from the geowatch/ repo root.")
        return

    run_dirs = sorted(
        d for d in glob.glob(os.path.join(PIPELINE_RUNS_DIR, "*"))
        if os.path.isdir(d)
    )

    if not run_dirs:
        print(f"No run directories found under {PIPELINE_RUNS_DIR}/.")
        return

    print(f"Found {len(run_dirs)} run directories.\n")

    summary_rows = []

    for run_dir in run_dirs:
        name = os.path.basename(run_dir)
        print("=" * 70)
        print(name)

        raster_hw = get_raster_size(run_dir)
        if raster_hw:
            print(f"  raw.tif size: {raster_hw[0]} x {raster_hw[1]} (H x W)")
        else:
            print("  raw.tif: NOT FOUND or unreadable")

        dense_candidates = find_dense_label_candidates(run_dir, raster_hw)
        if dense_candidates:
            print(f"  Possible DENSE label map file(s) found:")
            for path, name_hit, size_hit in dense_candidates:
                reason = []
                if name_hit:
                    reason.append("name matches common GT naming")
                if size_hit:
                    reason.append("size matches raw.tif exactly")
                print(f"    {path}  ({', '.join(reason)})")
        else:
            print("  No dense label map file found (checked common names + exact-size PNGs/TIFs).")

        coverage = segment_annotation_coverage(run_dir, raster_hw)
        if coverage:
            print(f"  Segment-level annotations found:")
            print(f"    total annotation records: {coverage['total_annotation_records']}")
            print(f"    labeled (human_label set): {coverage['labeled_segments']}")
            print(f"    skipped: {coverage['skipped_segments']}")
            if coverage['pct_raster_area_labeled'] is not None:
                print(f"    labeled segments cover ~{coverage['pct_raster_area_labeled']}% "
                      f"of the raster's total pixel area")
            else:
                print(f"    (couldn't compute % of raster area -- raw.tif size unknown)")
        else:
            print("  No annotations.json / masks.json pair found in this run dir.")

        summary_rows.append({
            "run": name,
            "has_dense_candidate": bool(dense_candidates),
            "pct_area_labeled": coverage["pct_raster_area_labeled"] if coverage else None,
        })

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for row in summary_rows:
        dense_flag = "DENSE-CANDIDATE-FOUND" if row["has_dense_candidate"] else "sparse-only"
        pct = row["pct_area_labeled"]
        pct_str = f"{pct}%" if pct is not None else "unknown"
        print(f"  {row['run']:45s} {dense_flag:24s} labeled-area~{pct_str}")

    print("\nInterpretation:")
    print("  - If any run shows DENSE-CANDIDATE-FOUND, open that file and confirm it's")
    print("    really a per-pixel class-index map (not a color visualization) before")
    print("    trusting it as ground truth.")
    print("  - 'labeled-area~X%' close to 100% means segment annotations already cover")
    print("    most of that raster -- rasterizing (option b) will give near-dense GT.")
    print("  - A low % (e.g. under 30-40%) means only a sparse sample of segments were")
    print("    annotated -- rasterizing will leave most of the raster as ignore_index,")
    print("    which may be too sparse for a statistically meaningful CAAT recompute")
    print("    on that city alone (though pooling across all 11 cities may still work).")


if __name__ == "__main__":
    main()