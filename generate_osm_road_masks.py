"""
Generates real, geometrically-correct paved_road training masks directly
from OpenStreetMap road-vector geometry, instead of hoping SAM's
class-agnostic segments happen to isolate roads cleanly (they usually
don't -- SAM fragments/merges thin linear features unpredictably).

Method:
  1. Load the city's raw.tif to get its real CRS + affine transform
     (this is what lets us go from "pixel coordinates in this tile" to
     "real lat/lon on earth" and back -- get this wrong and every mask
     is silently misaligned).
  2. Query OSM road ways inside that tile's bounding box via the Overpass
     API (same data source your pipeline already uses elsewhere).
  3. Buffer each road line by a realistic real-world width in meters,
     looked up per OSM `highway` tag (a residential street is not the
     same width as a primary road or a footpath -- using one flat
     buffer width for everything would be a real, avoidable error).
  4. Rasterize the buffered road polygons onto the tile's actual pixel
     grid (10m/pixel, Sentinel-2 resolution) using the SAME transform
     as raw.tif, so it lines up exactly with the imagery.
  5. Convert the rasterized road mask into the same mask_rle format your
     annotations.json/masks.json already use, and write new entries
     labeled human_label="paved_road", tagged with
     annotation_priority="osm_road_generated" so you can always tell
     these apart from human-reviewed SAM-segment labels later.
  6. Clips to tile_0_0.png's actual pixel extent (512 wide or less, per
     the Cape Town case where the raw raster wasn't an exact multiple
     of 512) -- so this only touches the pixel region you're actually
     training on, matching what tile_0_0.png covers.

IMPORTANT -- verify before trusting this for training:
  After running, use check_generated_road_mask.py (companion script) to
  visually confirm the generated road mask actually lines up with real
  roads in the tile image before merging into your training set. Do NOT
  skip this check -- a CRS/transform mistake will silently produce masks
  that are offset by several pixels, which at 10m resolution is a real,
  meaningful misalignment.

USAGE (run from geowatch/ repo root):
    python generate_osm_road_masks.py <city>
    python generate_osm_road_masks.py accra

Requires: rasterio, shapely, geopandas, requests
Install if missing:
    pip install rasterio shapely geopandas requests --break-system-packages
"""

import os
import sys
import json
import glob
import time

import numpy as np
import requests
import rasterio
from rasterio.features import rasterize
from rasterio.warp import transform_bounds
from shapely.geometry import LineString, mapping
from shapely.ops import transform as shapely_transform
import pyproj

PIPELINE_RUNS_DIR = "data/pipeline_runs"
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

# Realistic real-world road width in meters, by OSM highway tag.
# Conservative middle-of-range values -- err slightly narrow rather than
# wide, since an overly generous buffer risks bleeding into adjacent
# rooftops/vegetation and mislabeling THOSE pixels as paved_road instead,
# which would reintroduce exactly the kind of contamination we're trying
# to avoid.
HIGHWAY_WIDTH_M = {
    "motorway": 12, "trunk": 10, "primary": 9, "secondary": 8,
    "tertiary": 7, "residential": 5, "unclassified": 5,
    "living_street": 5, "service": 4, "track": 3,
    "path": 1.5, "footway": 1.5, "pedestrian": 3,
    "cycleway": 2,
}
DEFAULT_WIDTH_M = 5  # fallback for untagged/unknown highway types
# NOTE: 'track', 'path', 'footway' are intentionally narrow/unpaved-leaning
# tags -- if you want ONLY genuinely paved roads (not dirt tracks/footpaths,
# which your schema already has a separate unpaved_dirt_road OSM category
# for), consider excluding these tags entirely rather than including them
# at a narrow width. See EXCLUDE_UNPAVED_TAGS below.
EXCLUDE_UNPAVED_TAGS = {"track", "path", "footway", "bridleway"}


def find_run_dir(city):
    matches = sorted(glob.glob(os.path.join(PIPELINE_RUNS_DIR, f"{city}_*")))
    return matches[-1] if matches else None


def query_overpass_roads(min_lon, min_lat, max_lon, max_lat, retries=4):
    query = f"""
    [out:json][timeout:60];
    (
      way["highway"]({min_lat},{min_lon},{max_lat},{max_lon});
    );
    out geom;
    """
    headers = {
        "User-Agent": "GeoWatchCopilot/1.0 (research project, contact: local dev)",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    for attempt in range(retries):
        url = OVERPASS_URLS[attempt % len(OVERPASS_URLS)]
        try:
            print(f"  trying {url} ...")
            resp = requests.post(url, data={"data": query},
                                  headers=headers, timeout=90)
            resp.raise_for_status()
            return resp.json()["elements"]
        except Exception as e:
            wait = 15 * (attempt + 1)  # longer backoff: 15s, 30s, 45s
            print(f"  Overpass query failed (attempt {attempt+1}/{retries}): {e}")
            print(f"  waiting {wait}s before retry...")
            time.sleep(wait)
    raise RuntimeError("Overpass query failed after retries.")


def get_utm_crs(lon, lat):
    """Return the correct UTM CRS (as an EPSG string) for a given lon/lat,
    so we can buffer roads in real meters correctly instead of guessing."""
    zone = int((lon + 180) / 6) + 1
    hemisphere = 326 if lat >= 0 else 327  # 326xx = northern, 327xx = southern
    epsg_code = f"EPSG:{hemisphere}{zone:02d}"
    return epsg_code


def main():
    if len(sys.argv) != 2:
        print("Usage: python generate_osm_road_masks.py <city>")
        sys.exit(1)
    city = sys.argv[1]

    run_dir = find_run_dir(city)
    if run_dir is None:
        print(f"No run dir found for {city}")
        sys.exit(1)

    raw_tif_path = os.path.join(run_dir, "raw.tif")
    tile_path = os.path.join(run_dir, "tiles", "tile_0_0.png")
    if not os.path.exists(raw_tif_path):
        print(f"raw.tif not found at {raw_tif_path}")
        sys.exit(1)

    with rasterio.open(raw_tif_path) as src:
        raw_crs = src.crs
        raw_transform = src.transform
        raw_h, raw_w = src.height, src.width
        raw_bounds = src.bounds
        print(f"raw.tif: {raw_h}x{raw_w}, CRS={raw_crs}")

    # tile_0_0.png's real pixel extent -- may be smaller than 512 if the
    # raw raster isn't an exact multiple (confirmed real case: Cape Town
    # was 502x557, tile_0_512 was a 45px sliver, only tile_0_0 was used)
    from PIL import Image
    tile_img = Image.open(tile_path)
    tile_w, tile_h = tile_img.size
    print(f"tile_0_0.png actual size: {tile_w}x{tile_h}")

    # Get this tile's real-world bounding box in WGS84 (lon/lat) for the
    # Overpass query -- Overpass needs lat/lon regardless of raw.tif's CRS
    tile_bounds_native = rasterio.windows.bounds(
        rasterio.windows.Window(0, 0, tile_w, tile_h), raw_transform
    )  # (left, bottom, right, top) in raw.tif's own CRS
    min_lon, min_lat, max_lon, max_lat = transform_bounds(
        raw_crs, "EPSG:4326", *tile_bounds_native
    )
    print(f"tile bbox (WGS84): lon=[{min_lon:.5f},{max_lon:.5f}] "
          f"lat=[{min_lat:.5f},{max_lat:.5f}]")

    print("Querying Overpass for roads in this tile...")
    elements = query_overpass_roads(min_lon, min_lat, max_lon, max_lat)
    ways = [e for e in elements if e.get("type") == "way" and "geometry" in e]
    print(f"Found {len(ways)} road ways from OSM.")

    if not ways:
        print("No roads found in this tile from OSM -- nothing to generate.")
        return

    # Build shapely LineStrings in WGS84, then buffer in a proper LOCAL
    # METRIC CRS (UTM), since raw.tif's CRS here is EPSG:4326 (geographic,
    # degrees) -- buffering directly in degrees would be wrong, a degree
    # of longitude is not a fixed real-world distance and varies by
    # latitude. UTM is chosen automatically based on this tile's centroid.
    utm_crs = get_utm_crs((min_lon + max_lon) / 2, (min_lat + max_lat) / 2)
    print(f"Using {utm_crs} for meter-accurate buffering "
          f"(raw.tif CRS is geographic: {raw_crs})")

    to_utm = pyproj.Transformer.from_crs(
        "EPSG:4326", utm_crs, always_xy=True
    ).transform
    to_raw_crs = pyproj.Transformer.from_crs(
        utm_crs, raw_crs, always_xy=True
    ).transform

    buffered_polys = []
    excluded_count = 0
    for way in ways:
        tags = way.get("tags", {})
        highway_type = tags.get("highway", "")
        if highway_type in EXCLUDE_UNPAVED_TAGS:
            excluded_count += 1
            continue
        width_m = HIGHWAY_WIDTH_M.get(highway_type, DEFAULT_WIDTH_M)

        coords = [(pt["lon"], pt["lat"]) for pt in way["geometry"]]
        if len(coords) < 2:
            continue
        line_wgs84 = LineString(coords)
        line_utm = shapely_transform(to_utm, line_wgs84)
        buffered_utm = line_utm.buffer(width_m / 2)
        # reproject the buffered polygon back to raw.tif's own CRS so it
        # rasterizes correctly onto the tile's actual pixel grid
        buffered_raw_crs = shapely_transform(to_raw_crs, buffered_utm)
        buffered_polys.append(buffered_raw_crs)

    print(f"Buffered {len(buffered_polys)} road segments "
          f"(excluded {excluded_count} unpaved-tagged ways).")

    if not buffered_polys:
        print("Nothing left to rasterize after filtering.")
        return

    # Rasterize onto the TILE's pixel grid specifically (not the full
    # raw.tif) -- same transform, just windowed to the tile's extent
    tile_transform = raw_transform  # tile_0_0 starts at raw.tif's origin
    road_mask = rasterize(
        [(mapping(p), 1) for p in buffered_polys],
        out_shape=(tile_h, tile_w),
        transform=tile_transform,
        fill=0,
        dtype=np.uint8,
    ).astype(bool)

    total_road_px = road_mask.sum()
    print(f"Rasterized road mask: {total_road_px} pixels "
          f"({100*total_road_px/(tile_h*tile_w):.1f}% of tile)")

    if total_road_px == 0:
        print("Rasterized mask is empty -- roads may fall outside the "
              "tile's actual pixel extent, or there's a CRS mismatch. "
              "Run check_generated_road_mask.py to inspect visually "
              "before assuming this worked.")

    # Save the raw boolean mask + metadata for the next script to consume
    # and for you to visually verify before merging into annotations.json
    out_dir = os.path.join(run_dir, "osm_road_mask")
    os.makedirs(out_dir, exist_ok=True)
    np.save(os.path.join(out_dir, "road_mask.npy"), road_mask)

    meta = {
        "city": city,
        "run_dir": run_dir,
        "tile_shape": [tile_h, tile_w],
        "raw_crs": str(raw_crs),
        "num_osm_ways_used": len(buffered_polys),
        "num_osm_ways_excluded_unpaved": excluded_count,
        "total_road_pixels": int(total_road_px),
        "pct_of_tile": round(100 * total_road_px / (tile_h * tile_w), 2),
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nSaved to {out_dir}/road_mask.npy and meta.json")
    print("NEXT STEP -- do not skip: run "
          f"'python check_generated_road_mask.py {city}' to visually "
          "confirm this mask actually lines up with real roads in the "
          "tile image before merging it into training data.")


if __name__ == "__main__":
    main()