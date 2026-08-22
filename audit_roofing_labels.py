"""
audit_roofing_labels.py

Purpose
-------
Hypothesis B audit (GeoWatch Copilot): manually inspect existing
`dense_informal_roofing` / `sparse_informal_roofing` annotated patches to
check how many are actually mislabeled formal/planned housing, rather than
genuine informal-settlement texture.

This script does NOT try to auto-classify formal vs informal — that's not
reliable at 10m and is exactly the judgment call that needs a human eye.
Instead it:
  1. Walks your annotated patch data for one or more cities (Cape Town first).
  2. For every patch labeled dense_informal_roofing or sparse_informal_roofing,
     renders the RGB patch + its mask overlay side by side.
  3. Saves these as numbered image files into an output folder, plus an
     `audit_log.csv` you fill in by hand (verdict + notes columns) while
     looking at the images.
  4. On a second run (after you've filled in audit_log.csv), it will
     summarize your verdicts.

This is meant to be run LOCALLY in your geowatch-env, not in this sandbox,
since your actual patch/annotation data lives on your machine.

------------------------------------------------------------------------
HOW TO ADAPT THIS TO YOUR REAL FILES (read this before running)
------------------------------------------------------------------------
I don't have your actual `annotations.json` / `masks.json` schema in front
of me, so the loader below is written defensively with a few fallbacks and
clearly marked TODOs. Open this file, search for "ADAPT ME", and fix the
2-3 spots to match your real field names. It should take <5 min once you
paste in one real sample record for reference.

Usage:
    python audit_roofing_labels.py --city capetown
    python audit_roofing_labels.py --city capetown --summarize   # after filling in CSV

Requires: pillow, numpy (already in geowatch-env)
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

# ------------------------------------------------------------------
# CONFIG — adjust these paths to match your repo layout
# ------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent  # assume script sits at geowatch/ root; move if needed
PIPELINE_RUNS_DIR = REPO_ROOT / "data" / "pipeline_runs"
OUTPUT_DIR = REPO_ROOT / "audit_output"

TARGET_CATEGORIES = {"dense_informal_roofing", "sparse_informal_roofing"}

# Hardcoded from the project's actual CITY_MAP (confirmed 2026-07-02 run ids)
CITY_RUN_OVERRIDE = {
    "dharavi": "dharavi_20260702_163012",
    "nairobi": "nairobi_20260702_164731",
    "jakarta": "jakarta_20260702_163609",
    "hcmc": "hcmc_20260702_163714",
    "kigali": "kigali_20260702_163814",
    "accra": "accra_20260702_163854",
    "dhaka": "dhaka_20260702_163939",
    "lagos": "lagos_20260702_165430",
    "capetown": "capetown_20260702_164022",
    "guatemala": "guatemala_20260702_164206",
    "nusantara": "nusantara_20260702_165811",
}


def find_city_run_dir(city: str) -> Path:
    """Find the pipeline_runs subdirectory for a given city."""
    if city in CITY_RUN_OVERRIDE:
        candidate = PIPELINE_RUNS_DIR / CITY_RUN_OVERRIDE[city]
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"Override path not found: {candidate}")

    matches = sorted(PIPELINE_RUNS_DIR.glob(f"{city}_*"))
    if not matches:
        # also try exact-name dirs (no timestamp suffix)
        exact = PIPELINE_RUNS_DIR / city
        if exact.exists():
            return exact
        raise FileNotFoundError(
            f"No run directory found for city='{city}' under {PIPELINE_RUNS_DIR}. "
            f"Set CITY_RUN_OVERRIDE in this script if your naming differs."
        )
    if len(matches) > 1:
        print(f"[warn] multiple run dirs found for '{city}', using most recent: {matches[-1]}")
    return matches[-1]


def load_annotations(run_dir: Path):
    """
    Load per-patch annotation records for a run.

    ADAPT ME (2): this assumes annotations.json is a list of dicts, each with
    at minimum: an id/patch reference, a category label, and enough info to
    locate the source tile image + mask. Common shapes seen in projects like
    this are either:
      (a) one record per SAM mask/segment with fields like
          {"patch_id": ..., "tile_path": ..., "category": ..., "mask_rle": ...}
      (b) records nested under a per-tile structure.

    Fix the parsing below to match whatever prints out when you run:
        python -c "import json; d=json.load(open('data/pipeline_runs/<capetown_run>/annotations.json')); print(json.dumps(d[0] if isinstance(d, list) else next(iter(d.values())), indent=2))"
    and paste one real record's shape here.
    """
    ann_path = run_dir / "annotations.json"
    if not ann_path.exists():
        raise FileNotFoundError(f"annotations.json not found in {run_dir}")

    with open(ann_path) as f:
        raw = json.load(f)

    records = raw if isinstance(raw, list) else list(raw.values())
    return records


def rle_to_mask(rle, shape):
    """
    Minimal RLE decoder placeholder.

    ADAPT ME (3): if you're using pycocotools-style RLE (counts + size),
    swap this out for:
        from pycocotools import mask as maskUtils
        return maskUtils.decode(rle)
    This placeholder assumes a simple custom (start, length) pair list,
    which may not match your actual format — replace before trusting output.
    """
    try:
        from pycocotools import mask as maskUtils  # most likely what you're using
        if isinstance(rle, dict) and "counts" in rle:
            return maskUtils.decode(rle)
    except ImportError:
        pass

    # Fallback: assume rle is a flat list of (start, length) run pairs over a
    # flattened boolean array of len(shape[0]*shape[1])
    flat = np.zeros(shape[0] * shape[1], dtype=np.uint8)
    if isinstance(rle, list):
        for start, length in rle:
            flat[start:start + length] = 1
    return flat.reshape(shape)


def make_overlay(rgb_img: Image.Image, mask: np.ndarray, color=(255, 60, 60), alpha=110) -> Image.Image:
    """Overlay a semi-transparent mask on top of an RGB patch."""
    rgb_img = rgb_img.convert("RGBA")
    overlay = Image.new("RGBA", rgb_img.size, (0, 0, 0, 0))
    mask_img = Image.fromarray((mask * 255).astype(np.uint8)).resize(rgb_img.size).convert("L")
    color_layer = Image.new("RGBA", rgb_img.size, color + (alpha,))
    overlay = Image.composite(color_layer, overlay, mask_img)
    return Image.alpha_composite(rgb_img, overlay)


def side_by_side(rgb_img: Image.Image, overlay_img: Image.Image, label: str) -> Image.Image:
    w, h = rgb_img.size
    canvas = Image.new("RGB", (w * 2 + 20, h + 40), (30, 30, 30))
    canvas.paste(rgb_img.convert("RGB"), (0, 40))
    canvas.paste(overlay_img.convert("RGB"), (w + 20, 40))
    draw = ImageDraw.Draw(canvas)
    draw.text((10, 10), label, fill=(255, 255, 255))
    return canvas


def run_audit(city: str):
    run_dir = find_city_run_dir(city)
    records = load_annotations(run_dir)

    out_dir = OUTPUT_DIR / city
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / "audit_log.csv"
    rows = []
    count = 0

    for i, rec in enumerate(records):
        # ADAPT ME: field names below (category, tile_path/patch_path, mask_rle,
        # patch_id) must match your real annotations.json keys.
        category = rec.get("category") or rec.get("label")
        if category not in TARGET_CATEGORIES:
            continue

        patch_id = rec.get("patch_id") or rec.get("id") or f"idx{i}"
        tile_path = rec.get("tile_path") or rec.get("patch_path") or rec.get("image_path")
        mask_rle = rec.get("mask_rle")

        if not tile_path:
            print(f"[skip] record {patch_id}: no tile_path/patch_path field found — check schema")
            continue

        tile_full_path = (run_dir / tile_path) if not os.path.isabs(tile_path) else Path(tile_path)
        if not tile_full_path.exists():
            print(f"[skip] {patch_id}: image not found at {tile_full_path}")
            continue

        rgb_img = Image.open(tile_full_path)

        if mask_rle is not None:
            mask = rle_to_mask(mask_rle, rgb_img.size[::-1])
            overlay_img = make_overlay(rgb_img, mask)
        else:
            overlay_img = rgb_img  # no mask available, just show the raw patch twice

        label = f"{city} | {patch_id} | {category}"
        combined = side_by_side(rgb_img, overlay_img, label)

        out_name = f"{count:04d}_{category}_{patch_id}.png"
        combined.save(out_dir / out_name)

        rows.append({
            "index": count,
            "patch_id": patch_id,
            "category": category,
            "image_file": out_name,
            "verdict": "",   # fill in by hand: "correct" / "mislabeled_formal" / "unsure"
            "notes": "",
        })
        count += 1

    if count == 0:
        print(
            "[warn] No matching records were processed. This almost certainly means "
            "the field names in load_annotations()/run_audit() don't match your real "
            "annotations.json schema. Open this script, search 'ADAPT ME', and fix the "
            "field names — print one real record first to see its actual keys."
        )
        return

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["index", "patch_id", "category", "image_file", "verdict", "notes"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {count} patch images to {out_dir}")
    print(f"Fill in the 'verdict' column in {csv_path} while looking at each image, then rerun with --summarize")


def summarize(city: str):
    csv_path = OUTPUT_DIR / city / "audit_log.csv"
    if not csv_path.exists():
        print(f"No audit_log.csv found at {csv_path} — run without --summarize first.")
        return

    with open(csv_path) as f:
        rows = list(csv.DictReader(f))

    total = len(rows)
    by_verdict = {}
    by_category_verdict = {}
    for r in rows:
        v = (r["verdict"] or "").strip().lower() or "(blank)"
        by_verdict[v] = by_verdict.get(v, 0) + 1
        key = (r["category"], v)
        by_category_verdict[key] = by_category_verdict.get(key, 0) + 1

    print(f"\n=== Audit summary for {city} ({total} patches) ===")
    for v, n in sorted(by_verdict.items(), key=lambda x: -x[1]):
        pct = 100 * n / total if total else 0
        print(f"  {v:20s}  {n:4d}  ({pct:.1f}%)")

    mislabeled = by_verdict.get("mislabeled_formal", 0)
    if total:
        print(f"\nEstimated formal-housing contamination rate: {100*mislabeled/total:.1f}%")
    print("\nBy category:")
    for (cat, v), n in sorted(by_category_verdict.items()):
        print(f"  {cat:28s} {v:20s} {n}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", required=True, help="e.g. capetown")
    parser.add_argument("--summarize", action="store_true", help="Summarize a previously filled-in audit_log.csv")
    args = parser.parse_args()

    if args.summarize:
        summarize(args.city)
    else:
        run_audit(args.city)