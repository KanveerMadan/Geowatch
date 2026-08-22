"""
Reviews ONLY the candidate segments queued by find_paved_road_candidates.py
for one city. Saves a crop image (bbox region of the tile, with the segment
mask outlined) to disk so you can look at it, then asks you to type the
real label. Writes the result into that city's real annotations.json using
the existing schema (so training code needs zero special-casing later).

Resumable: every segment you decide on (labeled OR skipped) gets its
segment_id appended to the queue file's "reviewed_segment_ids" list and is
never shown again, even if you stop and re-run this script tomorrow, or
re-run find_paved_road_candidates.py to regenerate the queue (as long as
you don't delete the queue file first).

USAGE (run from geowatch/ repo root):
    python annotate_queue.py <city>

Example:
    python annotate_queue.py capetown

Controls at each prompt:
    p       -> label as paved_road
    <text>  -> type any other real category name to label it as that instead
               (e.g. "dense_informal_roofing", "unpaved_dirt_road", etc.)
    s       -> skip (marks reviewed, but does NOT add an annotation --
               use this for junk/ambiguous segments you don't want to label
               either way)
    q       -> quit (saves progress so far, queue picks up here next time)

Requires: pillow, numpy. Uses pycocotools if installed (faster/more robust
RLE decode); falls back to a manual COCO-RLE decoder if pycocotools isn't
available, so this works even without that dependency.
"""

import os
import sys
import json
from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageDraw

QUEUE_DIR = "data/annotation_queues"
CROP_PREVIEW_PATH = "data/annotation_queues/_current_candidate_preview.png"


def decode_rle(mask_rle):
    """Decode a COCO-style RLE mask ({'size': [h, w], 'counts': [...]})
    into a 2D boolean numpy array. Tries pycocotools first, falls back to
    a manual decoder if it's not installed."""
    h, w = mask_rle["size"]
    counts = mask_rle["counts"]

    if isinstance(counts, list):
        try:
            from pycocotools import mask as maskUtils
            rle = maskUtils.frPyObjects({"size": [h, w], "counts": counts}, h, w)
            return maskUtils.decode(rle).astype(bool)
        except ImportError:
            pass
        # manual decode: counts is a flat run-length list, column-major
        # (Fortran order), alternating background/foreground starting
        # with background, matching pycocotools' uncompressed RLE.
        flat = np.zeros(h * w, dtype=bool)
        idx = 0
        val = False
        for c in counts:
            if val:
                flat[idx:idx + c] = True
            idx += c
            val = not val
        return flat.reshape((w, h)).T
    else:
        # already-compressed string RLE -- requires pycocotools
        from pycocotools import mask as maskUtils
        return maskUtils.decode(mask_rle).astype(bool)


def load_queue(city):
    path = os.path.join(QUEUE_DIR, f"{city}_paved_road_queue.json")
    if not os.path.exists(path):
        print(f"No queue file found at {path}.")
        print("Run find_paved_road_candidates.py first.")
        sys.exit(1)
    with open(path) as f:
        return path, json.load(f)


def save_queue(path, queue):
    with open(path, "w") as f:
        json.dump(queue, f, indent=2)


def load_masks_by_id(run_dir):
    with open(os.path.join(run_dir, "masks.json")) as f:
        masks = json.load(f)
    return {m["segment_id"]: m for m in masks}


def load_annotations(run_dir):
    path = os.path.join(run_dir, "annotations.json")
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return path, data, data["annotations"]
    else:
        # some runs store a bare list -- normalize access but write back
        # in the same shape we found it
        return path, None, data


def save_annotations(path, wrapper, anns):
    if wrapper is None:
        with open(path, "w") as f:
            json.dump(anns, f, indent=2)
    else:
        wrapper["annotations"] = anns
        with open(path, "w") as f:
            json.dump(wrapper, f, indent=2)


def make_preview(tile_path, bbox, mask_bool):
    tile = Image.open(tile_path).convert("RGB")
    x, y, w, h = bbox
    pad = 20
    left = max(x - pad, 0)
    top = max(y - pad, 0)
    right = min(x + w + pad, tile.width)
    bottom = min(y + h + pad, tile.height)

    overlay = tile.copy()
    mask_img = Image.fromarray((mask_bool * 255).astype(np.uint8)).convert("L")
    red = Image.new("RGB", tile.size, (255, 60, 60))
    overlay = Image.composite(red, overlay, mask_img.point(lambda p: p * 0.4))

    draw = ImageDraw.Draw(overlay)
    draw.rectangle([x, y, x + w, y + h], outline=(255, 255, 0), width=2)

    crop = overlay.crop((left, top, right, bottom))
    # upscale small crops so they're actually visible
    scale = max(1, 300 // max(crop.width, crop.height))
    if scale > 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.NEAREST)
    crop.save(CROP_PREVIEW_PATH)


def main():
    if len(sys.argv) != 2:
        print("Usage: python annotate_queue.py <city>")
        sys.exit(1)
    city = sys.argv[1]

    queue_path, queue = load_queue(city)
    run_dir = queue["run_dir"]
    tile_path = queue["tile_path"]
    candidates = queue["candidates"]
    reviewed = set(queue.get("reviewed_segment_ids", []))

    masks_by_id = load_masks_by_id(run_dir)
    ann_path, ann_wrapper, anns = load_annotations(run_dir)

    pending = [c for c in candidates if c["segment_id"] not in reviewed]
    print(f"{city}: {len(pending)} candidates left to review "
          f"({len(reviewed)} already done).")
    if not pending:
        print("Nothing left in this queue. Re-run find_paved_road_candidates.py "
              "if you've done new SAM/annotation work and want to check for more.")
        return

    labeled_count = 0
    for i, cand in enumerate(pending):
        seg_id = cand["segment_id"]
        m = masks_by_id.get(seg_id)
        if m is None:
            print(f"[warn] segment_id {seg_id} in queue but missing from "
                  f"masks.json, marking reviewed and skipping.")
            reviewed.add(seg_id)
            continue

        mask_bool = decode_rle(m["mask_rle"])
        make_preview(tile_path, cand["bbox"], mask_bool)

        print(f"\n--- {city} [{i+1}/{len(pending)}] segment_id={seg_id} "
              f"score={cand['score']} elongation={cand['elongation']} "
              f"compactness={cand['compactness']} ---")
        print(f"Preview saved to: {CROP_PREVIEW_PATH}  (open it, then answer below)")

        choice = input("Label [p=paved_road / type another label / s=skip / q=quit]: ").strip()

        if choice.lower() == "q":
            break
        elif choice.lower() == "s":
            reviewed.add(seg_id)
            queue["reviewed_segment_ids"] = sorted(reviewed)
            save_queue(queue_path, queue)
            continue

        label = "paved_road" if choice.lower() == "p" else choice
        new_ann = {
            "segment_id": seg_id,
            "bbox": cand["bbox"],
            "area": cand["area"],
            "mask_rle": m["mask_rle"],
            "human_label": label,
            "skipped": False,
            "annotated_at": datetime.now(timezone.utc).isoformat(),
            "annotation_priority": "paved_road_queue_review",
        }
        # keep any fields the original schema expects but this queue tool
        # doesn't compute (crop_confidence, crop_top_category, etc.) --
        # fill with None rather than omit, so downstream code that expects
        # the key to exist doesn't KeyError.
        for k in ("crop_confidence", "crop_top_category", "tile_confidence",
                  "tile_suggested_label"):
            new_ann.setdefault(k, None)

        anns.append(new_ann)
        save_annotations(ann_path, ann_wrapper, anns)

        reviewed.add(seg_id)
        queue["reviewed_segment_ids"] = sorted(reviewed)
        save_queue(queue_path, queue)

        labeled_count += 1
        print(f"Saved label '{label}' for segment_id {seg_id}.")

    print(f"\nDone for now. Labeled {labeled_count} new segments this session.")
    print(f"Remaining in queue: {len(candidates) - len(reviewed)}")


if __name__ == "__main__":
    main()