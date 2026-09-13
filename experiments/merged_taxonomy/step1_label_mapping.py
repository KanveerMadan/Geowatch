#!/usr/bin/env python3
"""
STEP 1 of the merged-taxonomy experiment — build the merged label mapping and
report the gaps, before any retraining.

Reproduces 03_EVIDENCE.md §A.5's supervision composition from the live
annotation pool (verified: exact match, 1,345 annotations / 484,796 pixels),
then reports what the proposed merge would actually produce.

Run:  python experiments/merged_taxonomy/step1_label_mapping.py
"""
import collections
import json
import os
import sys

import numpy as np

sys.path.insert(0, ".")
from ingestion.segmentation import decode_mask_rle          # noqa: E402
from recalibrate_caat import TRAINING_CITIES, find_annotated_run_dir  # noqa: E402

# The seven classes the model is trained on. NOTE there is no bare-soil class
# among them; see the report for what that means for the merge.
SEVEN = [
    "dense_informal_roofing", "sparse_informal_roofing", "paved_road",
    "standing_water", "vegetation_clearing", "active_construction",
    "dense_vegetation",
]

# The training pool is all three annotation streams, not just the human one.
# 03_EVIDENCE.md §A.5: "331 human annotations, 976 OSM-generated road, 101
# OSM-generated water." Counting only annotations.json understates the pool by
# 3.25x and hides that paved_road supervision is almost entirely machine-made.
ANNOTATION_FILES = [
    ("annotations.json", "human"),
    ("osm_generated_annotations.json", "osm_road"),
    ("osm_generated_annotations_water.json", "osm_water"),
]

# Mapping A is the merge as proposed in the experiment brief.
MERGE_A = {
    "impervious": ["dense_informal_roofing", "sparse_informal_roofing",
                   "paved_road", "active_construction"],
    "vegetation": ["dense_vegetation", "vegetation_clearing"],
    "water": ["standing_water"],
}

# Mapping B holds active_construction out, which is what the codebase's own
# prior decision implies. configs/applicability_constants.py's
# IMPERVIOUS_CLASS_WEIGHTS contains paved_road/dense_informal/sparse_informal
# and NOT active_construction, and hydrological_surfaces.py states why:
# "active_construction is deliberately excluded from both surfaces -- its
# imperviousness is genuinely variable (bare soil early-stage vs. impervious
# late-stage) and guessing a fixed weight would be worse than omitting it."
MERGE_B = {
    "impervious": ["dense_informal_roofing", "sparse_informal_roofing", "paved_road"],
    "vegetation": ["dense_vegetation", "vegetation_clearing"],
    "water": ["standing_water"],
    "active_construction": ["active_construction"],
}


def collect():
    ann = collections.Counter()
    px = collections.Counter()
    src = collections.Counter()
    per_city = collections.defaultdict(collections.Counter)
    outside = collections.Counter()

    for city in TRAINING_CITIES:
        run_dir = find_annotated_run_dir(city)
        if not run_dir:
            continue
        for filename, source in ANNOTATION_FILES:
            path = os.path.join(run_dir, filename)
            if not os.path.exists(path):
                continue
            raw = json.load(open(path))
            items = raw if isinstance(raw, list) else raw.get("annotations", [])
            for a in items:
                label = a.get("human_label")
                if not label or a.get("skipped"):
                    continue
                if label not in SEVEN:
                    outside[label] += 1
                    continue
                try:
                    n = int(np.asarray(decode_mask_rle(a["mask_rle"])).sum())
                except Exception:
                    n = int(a.get("area") or 0)
                ann[label] += 1
                px[label] += n
                src[(label, source)] += 1
                per_city[city][label] += n
    return ann, px, src, per_city, outside


def main():
    ann, px, src, per_city, outside = collect()
    total_a, total_p = sum(ann.values()), sum(px.values())

    print("=" * 74)
    print("ORIGINAL 7-CLASS SUPERVISION  (compare to 03_EVIDENCE.md §A.5)")
    print(f"  {'class':<26} {'anns':>6} {'ann%':>7} {'pixels':>9} {'pixel%':>8} "
          f"{'human':>6} {'osm':>6}")
    for c, _ in ann.most_common():
        osm = src[(c, "osm_road")] + src[(c, "osm_water")]
        print(f"  {c:<26} {ann[c]:6d} {100*ann[c]/total_a:6.2f}% {px[c]:9d} "
              f"{100*px[c]/total_p:7.2f}% {src[(c,'human')]:6d} {osm:6d}")
    print(f"  {'TOTAL':<26} {total_a:6d} {'':7} {total_p:9d}")

    print("\n  Labels present in the files but OUTSIDE the 7 model classes "
          "(already excluded from training):")
    for k, v in outside.most_common():
        print(f"    {k!r}: {v}")

    for name, mapping in [("A — as proposed", MERGE_A),
                          ("B — active_construction held out", MERGE_B)]:
        print("\n" + "=" * 74)
        print(f"MERGED SUPERVISION, mapping {name}")
        print(f"  {'class':<22} {'anns':>6} {'ann%':>7} {'pixels':>9} {'pixel%':>8}")
        for k, members in mapping.items():
            a = sum(ann.get(m, 0) for m in members)
            p = sum(px.get(m, 0) for m in members)
            print(f"  {k:<22} {a:6d} {100*a/total_a:6.2f}% {p:9d} {100*p/total_p:7.2f}%")

    print("\n" + "=" * 74)
    print("WHAT 'impervious' IS ACTUALLY MADE OF  (mapping A)")
    members = MERGE_A["impervious"]
    ta = sum(ann.get(m, 0) for m in members)
    tp = sum(px.get(m, 0) for m in members)
    print(f"  {'source class':<26} {'anns':>6} {'share':>8} {'pixels':>9} {'share':>8}")
    for m in members:
        print(f"  {m:<26} {ann.get(m,0):6d} {100*ann.get(m,0)/ta:7.2f}% "
              f"{px.get(m,0):9d} {100*px.get(m,0)/tp:7.2f}%")
    osm = sum(v for (lab, s), v in src.items() if lab in members and s != "human")
    print(f"\n  paved_road share of 'impervious' annotations : {100*ann['paved_road']/ta:.1f}%")
    print(f"  OSM-generated share of those annotations     : {osm}/{ta} = {100*osm/ta:.1f}%")

    print("\n" + "=" * 74)
    print("MERGED PIXEL DISTRIBUTION PER CITY  (mapping A)")
    print(f"  {'city':<11} {'impervious':>13} {'vegetation':>13} {'water':>13} {'total':>9}")
    totals = collections.Counter()
    for city in sorted(per_city):
        row = {k: sum(per_city[city].get(m, 0) for m in v) for k, v in MERGE_A.items()}
        t = sum(row.values())
        totals.update(row)
        cells = " ".join(f"{row[k]:8d} {100*row[k]/t:4.1f}%" for k in MERGE_A)
        print(f"  {city:<11} {cells} {t:9d}")
    T = sum(totals.values())
    print(f"  {'ALL':<11} " +
          " ".join(f"{totals[k]:8d} {100*totals[k]/T:4.1f}%" for k in MERGE_A) + f" {T:9d}")


if __name__ == "__main__":
    main()
