"""
Quick check: for each of the 11 cities, does waterways.geojson actually
contain real geometry, or is it empty/missing? This determines whether
the "free win" approach that worked for paved_road (rasterizing OSM
vector geometry directly into masks) is viable for standing_water too.

USAGE (run from geowatch/ repo root):
    python check_waterways_coverage.py
"""

import os
import json
import glob

PIPELINE_RUNS_DIR = "data/pipeline_runs"
TRAINING_CITIES = [
    "accra", "capetown", "dhaka", "dharavi", "guatemala",
    "hcmc", "jakarta", "kigali", "lagos", "nairobi", "nusantara",
]


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


def summarize_geometry(geojson_path: str) -> dict:
    """Counts features and geometry types in a geojson file."""
    with open(geojson_path) as f:
        data = json.load(f)

    features = data.get("features", [])
    n_features = len(features)

    geom_types = {}
    total_coords = 0
    for feat in features:
        geom = feat.get("geometry", {})
        gtype = geom.get("type", "unknown")
        geom_types[gtype] = geom_types.get(gtype, 0) + 1

        coords = geom.get("coordinates", [])
        # rough coordinate-count proxy for "how much geometry" -- not exact
        # for nested structures but good enough for a sanity check
        def count_coords(c):
            if isinstance(c, (list, tuple)):
                if len(c) > 0 and isinstance(c[0], (int, float)):
                    return 1
                return sum(count_coords(x) for x in c)
            return 0
        total_coords += count_coords(coords)

    return {
        "n_features": n_features,
        "geom_types": geom_types,
        "total_coords": total_coords,
    }


def main():
    print(f"{'city':<12} {'waterways.geojson':<20} {'n_features':>10} {'geom_types'}")
    print("-" * 80)

    results = []
    for city in TRAINING_CITIES:
        run_dir = find_annotated_run_dir(city)
        if run_dir is None:
            print(f"{city:<12} {'NO RUN DIR FOUND':<20}")
            results.append((city, None))
            continue

        # waterways.geojson is copied to data/{city}/waterways.geojson in
        # your Colab loading cell, sourced from run_dir/osm/waterways.geojson
        # -- check the LOCAL run_dir source, not the Colab copy, since this
        # runs on your Mac.
        wf_path = os.path.join(run_dir, "osm", "waterways.geojson")
        if not os.path.exists(wf_path):
            print(f"{city:<12} {'MISSING FILE':<20}")
            results.append((city, 0))
            continue

        try:
            summary = summarize_geometry(wf_path)
        except Exception as e:
            print(f"{city:<12} {'PARSE ERROR: ' + str(e)}")
            results.append((city, None))
            continue

        status = "OK" if summary["n_features"] > 0 else "EMPTY (0 features)"
        print(f"{city:<12} {status:<20} {summary['n_features']:>10}  {summary['geom_types']}")
        results.append((city, summary["n_features"]))

    print("\n" + "=" * 70)
    print("SUMMARY")
    usable = [c for c, n in results if n is not None and n > 0]
    empty = [c for c, n in results if n == 0]
    missing = [c for c, n in results if n is None]

    print(f"  Cities with usable waterway data: {len(usable)} -> {usable}")
    print(f"  Cities with EMPTY waterways.geojson: {len(empty)} -> {empty}")
    print(f"  Cities missing/error: {len(missing)} -> {missing}")

    print("\nINTERPRETATION")
    if len(usable) >= 7:
        print("  -> Good coverage. The OSM-waterway-rasterization approach (same")
        print("     pattern as build_osm_generated_patches for paved_road) is viable")
        print("     as a real, low-effort fix for standing_water scarcity.")
    elif len(usable) >= 3:
        print("  -> Partial coverage. Still worth doing -- will help some cities'")
        print("     standing_water representation, but won't fully solve the class")
        print("     scarcity on its own; may still need some manual annotation too.")
    else:
        print("  -> Low coverage. OSM waterway data alone won't meaningfully fix")
        print("     standing_water scarcity -- manual annotation is likely required,")
        print("     same as active_construction and sparse_informal_roofing.")


if __name__ == "__main__":
    main()