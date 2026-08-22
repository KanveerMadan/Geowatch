"""
Re-tiles all 11 cities' raw.tif (already confirmed 6-band) into
tile_0_0.npy (and any additional tiles if raw.tif > 512px) using the
existing, already-correct generate_tiles() from tiler.py.

Run locally: python3 retile_all_cities_6band.py
"""

import os
from ingestion.tiler import generate_tiles

CITY_MAP = {
    'dharavi': 'dharavi_20260702_163012',
    'nairobi': 'nairobi_20260702_164731',
    'jakarta': 'jakarta_20260702_163609',
    'hcmc': 'hcmc_20260702_163714',
    'kigali': 'kigali_20260702_163814',
    'accra': 'accra_20260702_163854',
    'dhaka': 'dhaka_20260702_163939',
    'lagos': 'lagos_20260702_165430',
    'capetown': 'capetown_20260702_164022',
    'guatemala': 'guatemala_20260702_164206',
    'nusantara': 'nusantara_20260702_165811',
}

DATA_ROOT = 'data/pipeline_runs'

results = {}

for city, run_id in CITY_MAP.items():
    run_dir = os.path.join(DATA_ROOT, run_id)
    raw_tif = os.path.join(run_dir, 'raw.tif')
    tiles_out = os.path.join(run_dir, 'tiles')

    if not os.path.exists(raw_tif):
        print(f"[{city}] MISSING raw.tif at {raw_tif} -- skipping")
        results[city] = 'missing_raw_tif'
        continue

    print(f"[{city}] tiling {raw_tif} -> {tiles_out}")
    try:
        tile_paths = generate_tiles(raw_tif, tiles_out)
        results[city] = f"OK -- {len(tile_paths)} tiles"
    except Exception as e:
        print(f"[{city}] FAILED: {e}")
        results[city] = f"FAILED: {e}"

print("\n=== SUMMARY ===")
for city, status in results.items():
    print(f"{city:12s} -> {status}")
