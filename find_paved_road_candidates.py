import os
import sys
import json
import glob

sys.path.insert(0, ".")

PIPELINE_RUNS_DIR = "data/pipeline_runs"
QUEUE_DIR = "data/annotation_queues"
TRAINING_CITIES = [
    "accra", "capetown", "dhaka", "dharavi", "guatemala",
    "hcmc", "jakarta", "kigali", "lagos", "nairobi", "nusantara",
]

MIN_ELONGATION = 1.8   # loosened from 2.5
MAX_COMPACTNESS = 0.85  # loosened from 0.55 -- diagnostic showed 0 segments
MIN_AREA = 30           # ignore tiny noise segments


def find_annotated_run_dir(city: str) -> str:
    candidates = []
    for run_dir in sorted(glob.glob(os.path.join(PIPELINE_RUNS_DIR, f"{city}_*"))):
        if not os.path.isdir(run_dir):
            continue
        tile_path = os.path.join(run_dir, "tiles", "tile_0_0.png")
        ann_path = os.path.join(run_dir, "annotations.json")
        masks_path = os.path.join(run_dir, "masks.json")
        if os.path.exists(tile_path) and os.path.exists(ann_path) and os.path.exists(masks_path):
            candidates.append(run_dir)
    return candidates[-1] if candidates else None


def main():
    os.makedirs(QUEUE_DIR, exist_ok=True)
    total_candidates = 0

    for city in TRAINING_CITIES:
        run_dir = find_annotated_run_dir(city)
        if run_dir is None:
            print(f"{city}: no qualifying run dir, skipping.")
            continue

        with open(os.path.join(run_dir, "annotations.json")) as f:
            ann_data = json.load(f)
        anns = ann_data["annotations"] if isinstance(ann_data, dict) else ann_data
        already_annotated_ids = {a.get("segment_id") for a in anns if not a.get("skipped")}
        # segments explicitly skipped are still "handled" -- don't re-queue them
        already_handled_ids = {a.get("segment_id") for a in anns}

        with open(os.path.join(run_dir, "masks.json")) as f:
            masks = json.load(f)

        candidates = []
        for m in masks:
            seg_id = m.get("segment_id")
            if seg_id in already_handled_ids:
                continue

            bbox = m.get("bbox")
            area = m.get("area", 0)
            if bbox is None or area < MIN_AREA:
                continue

            _, _, w, h = bbox
            if w <= 0 or h <= 0:
                continue

            long_side = max(w, h)
            short_side = max(min(w, h), 1)
            elongation = long_side / short_side
            compactness = area / (w * h)

            # no filtering -- just surface every unhandled segment, ranked
            # by elongation as a soft hint (more road-like shapes first),
            # but nothing is excluded
            candidates.append({
                "segment_id": seg_id,
                "bbox": bbox,
                "area": area,
                "elongation": round(elongation, 2),
                "compactness": round(compactness, 3),
                "score": round(elongation, 3),
            })
            

        candidates.sort(key=lambda c: -c["score"])

        queue = {
            "city": city,
            "run_dir": run_dir,
            "tile_path": os.path.join(run_dir, "tiles", "tile_0_0.png"),
            "target_label": "paved_road",
            "candidates": candidates,
            "reviewed_segment_ids": [],  # annotate_queue.py appends here as you go
        }

        out_path = os.path.join(QUEUE_DIR, f"{city}_paved_road_queue.json")
        with open(out_path, "w") as f:
            json.dump(queue, f, indent=2)

        print(f"{city:<15} {len(candidates):>3} candidate segments -> {out_path}")
        total_candidates += len(candidates)

    print(f"\nTotal candidates queued across all cities: {total_candidates}")
    print("\nNext: run annotate_queue.py <city> to review ONLY these candidates,")
    print("one at a time. It saves a crop image for you to look at, you type the")
    print("real label (paved_road / something else / skip), and it writes directly")
    print("into that city's real annotations.json -- existing annotations are never")
    print("touched, and each segment is marked reviewed so re-running the queue")
    print("never shows it again.")


if __name__ == "__main__":
    main()