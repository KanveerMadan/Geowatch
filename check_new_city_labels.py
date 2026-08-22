"""
Run this from your geowatch project root (where data/pipeline_runs/ lives).
Checks label distribution across the 6 newly annotated cities to see whether
active_construction / standing_water / sparse_informal_roofing /
vegetation_clearing actually gained real examples, or are still thin.

Usage:
    python check_new_city_labels.py
"""
import json
from pathlib import Path
from collections import Counter

NEW_RUNS = {
    "dhaka":     "dhaka_20260701_133207",
    "lagos":     "lagos_20260701_133536",
    "accra":     "accra_20260701_133652",
    "capetown":  "capetown_20260701_133746",
    "guatemala": "guatemala_20260701_133908",
    "nusantara": "nusantara_20260701_152835",
}

RESOLVABLE = {
    "dense_informal_roofing", "sparse_informal_roofing", "paved_road",
    "standing_water", "vegetation_clearing", "active_construction",
    "dense_vegetation",
}
OSM_ONLY = {"unpaved_dirt_road", "open_drainage_channel", "open_waste"}

combined = Counter()
per_city = {}

for city, run_id in NEW_RUNS.items():
    path = Path(f"data/pipeline_runs/{run_id}/annotations.json")
    if not path.exists():
        print(f"[{city}] MISSING: {path}")
        continue

    with open(path) as f:
        data = json.load(f)

    labels = []
    skipped = 0
    unknown = 0
    for ann in data.get("annotations", []):
        if ann.get("skipped"):
            skipped += 1
            continue
        label = ann.get("human_label")
        if label is None:
            continue
        if label == "unknown":
            unknown += 1
            continue
        labels.append(label)

    city_counts = Counter(labels)
    per_city[city] = city_counts
    combined.update(city_counts)

    print(f"\n--- {city.upper()} ---  (skipped={skipped}, unknown={unknown})")
    for cat in sorted(RESOLVABLE | OSM_ONLY):
        c = city_counts.get(cat, 0)
        marker = " [OSM-only, should NOT come from annotate.py]" if cat in OSM_ONLY and c > 0 else ""
        print(f"  {cat:<28} {c:>3}{marker}")

print("\n" + "=" * 60)
print("COMBINED ACROSS 6 NEW CITIES")
print("=" * 60)
for cat in sorted(RESOLVABLE):
    print(f"  {cat:<28} {combined.get(cat, 0):>3}")

print("\nOSM-only categories manually labeled (should be ~0, these belong to OSM vector pipeline):")
for cat in sorted(OSM_ONLY):
    print(f"  {cat:<28} {combined.get(cat, 0):>3}")

print("\n" + "-" * 60)
print("RUNNING TOTAL: these new counts + your prior 101 (3-city) baseline")
print("-" * 60)
# Prior baseline from master prompt Section 14 (Dharavi/Nairobi/Jakarta, 101 total)
# NOTE: exact per-category breakdown of the original 101 isn't in this script —
# pull it the same way from those 3 cities' annotations.json if you want a true
# grand total per class.
for cat in sorted(RESOLVABLE):
    print(f"  {cat:<28} +{combined.get(cat, 0):>3} from new cities (check original 3-city annotations.json separately for prior counts)")