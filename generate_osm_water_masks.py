"""
Generates real, geometrically-correct standing_water training masks
directly from OpenStreetMap water geometry -- now covering BOTH:

  Pass 1 (original): `waterway=*` LINE features (river/stream/canal/drain
           centerlines), buffered by a realistic width per tag -- good
           for canals, drains, narrow rivers.
  Pass 2 (NEW): `natural=water` / `water=*` POLYGON features (actual
           mapped water body extents -- lakes, ponds, reservoirs, and
           critically, wide river banks) -- rasterized directly, no
           buffering needed since these are already area geometry.

WHY THIS EXTENSION EXISTS:
  Confirmed via visual spot-check this session: Dhaka's tile has an
  unmistakably large river dominating the frame, but Pass-1-only
  produced just 148 pixels (0.1% of tile) nowhere near it. Wide rivers
  are very often mapped in OSM as `natural=water` polygon extents
  (the actual riverbank-to-riverbank area), not as a `waterway=river`
  centerline -- exactly the gap this script's own original docstring
  flagged as "a real, worthwhile follow-up, not covered by this script."
  This version covers it.

IMPORTANT CAVEAT, CARRIED FORWARD HONESTLY:
  Some large water bodies are mapped as OSM RELATIONS (multipolygons),
  not simple ways -- e.g. a lake with an island cut out of it needs a
  relation to represent the hole correctly. This script queries `way`
  geometry only (mirroring the original road/water line scripts), the
  same way build_osm_generated_patches did for roads. Multipolygon
  relations are NOT fetched here. This means some complex water bodies
  may still be under-represented. If a city's water_pct still looks
  suspiciously low after this fix, checking for missed multipolygon
  relations would be the next real thing to investigate -- flagging
  this now rather than presenting the fix as fully complete.

Method:
  1. Load the city's raw.tif to get its real CRS + affine transform.
  2. Query OSM waterway LINES (Pass 1, unchanged from before).
  3. Query OSM natural=water / water=* POLYGONS (Pass 2, NEW).
  4. Buffer Pass-1 lines by realistic width; use Pass-2 polygons as-is.
  5. Rasterize BOTH onto the tile's actual pixel grid, same transform,
     combined into one boolean mask (logical OR).
  6. Convert into the same mask_rle format, human_label="standing_water".
     meta.json now separately reports pixel counts contributed by each
     pass, so you can see which source is doing the work per city --
     never hiding which part of "standing_water" pixels came from
     which query, consistent with the project's provenance standard.
  7. Clips to tile_0_0.png's actual pixel extent, same as before.

USAGE (run from geowatch/ repo root):
    python generate_osm_water_masks.py <city>
    python generate_osm_water_masks.py dhaka

RE-RUN NOTE: safe to re-run on cities you already processed (accra,
capetown, etc.) -- it will overwrite water_mask.npy/meta.json with the
new, more complete version. Recommended to re-run ALL 11 cities with
this version rather than only Dhaka, since Pass 2 may add meaningful
signal elsewhere too (e.g. Jakarta/Lagos/Nusantara's docks/canals may
have adjacent natural=water polygons not caught by Pass 1 alone).

Requires: rasterio, shapely, geopandas, requests, pyproj
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
from shapely.geometry import LineString, Polygon, mapping
from shapely.ops import transform as shapely_transform
import pyproj

PIPELINE_RUNS_DIR = "data/pipeline_runs"
# Shared endpoint list + retry policy (C44). This module previously kept its
# OWN copy of the URL list, which is how the two drifted apart.
from ingestion.overpass import (            # noqa: E402
    OVERPASS_URLS, run_query, OverpassQueryTooHeavy,
)

WATERWAY_WIDTH_M = {
    "river": 15, "canal": 8, "stream": 3, "drain": 2, "ditch": 1.5,
    "tidal_channel": 10,
}
DEFAULT_WIDTH_M = 3


def find_run_dir(city):
    matches = sorted(glob.glob(os.path.join(PIPELINE_RUNS_DIR, f"{city}_*")))
    return matches[-1] if matches else None


def query_overpass(query, retries=None):
    """See `ingestion.overpass.run_query`. `retries` kept for compatibility."""
    try:
        return run_query(query)
    except OverpassQueryTooHeavy:
        print("  Overpass hit its own time limit on this bbox -- split the AOI "
              "or raise the [timeout:] value. Retrying as-is will not help.")
        raise


def query_overpass_waterway_lines(min_lon, min_lat, max_lon, max_lat):
    query = f"""
    [out:json][timeout:60];
    (
      way["waterway"]({min_lat},{min_lon},{max_lat},{max_lon});
    );
    out geom;
    """
    return query_overpass(query)


def query_overpass_water_polygons(min_lon, min_lat, max_lon, max_lat):
    """NEW: query natural=water and water=* polygon ways -- actual mapped
    water body extents (lakes, ponds, reservoirs, wide river banks),
    as opposed to waterway centerlines. Ways only (see caveat above about
    multipolygon relations not being covered)."""
    query = f"""
    [out:json][timeout:60];
    (
      way["natural"="water"]({min_lat},{min_lon},{max_lat},{max_lon});
      way["water"]({min_lat},{min_lon},{max_lat},{max_lon});
    );
    out geom;
    """
    return query_overpass(query)


def get_utm_crs(lon, lat):
    zone = int((lon + 180) / 6) + 1
    hemisphere = 326 if lat >= 0 else 327
    epsg_code = f"EPSG:{hemisphere}{zone:02d}"
    return epsg_code


def main():
    if len(sys.argv) != 2:
        print("Usage: python generate_osm_water_masks.py <city>")
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
        print(f"raw.tif: {src.height}x{src.width}, CRS={raw_crs}")

    from PIL import Image
    tile_img = Image.open(tile_path)
    tile_w, tile_h = tile_img.size
    print(f"tile_0_0.png actual size: {tile_w}x{tile_h}")

    tile_bounds_native = rasterio.windows.bounds(
        rasterio.windows.Window(0, 0, tile_w, tile_h), raw_transform
    )
    min_lon, min_lat, max_lon, max_lat = transform_bounds(
        raw_crs, "EPSG:4326", *tile_bounds_native
    )
    print(f"tile bbox (WGS84): lon=[{min_lon:.5f},{max_lon:.5f}] "
          f"lat=[{min_lat:.5f},{max_lat:.5f}]")

    utm_crs = get_utm_crs((min_lon + max_lon) / 2, (min_lat + max_lat) / 2)
    to_utm = pyproj.Transformer.from_crs(
        "EPSG:4326", utm_crs, always_xy=True
    ).transform
    to_raw_crs = pyproj.Transformer.from_crs(
        utm_crs, raw_crs, always_xy=True
    ).transform

    # ---------- PASS 1: waterway lines (original behavior) ----------
    print("\n--- PASS 1: waterway lines (rivers/streams/canals/drains) ---")
    print("Querying Overpass for waterway lines in this tile...")
    line_elements = query_overpass_waterway_lines(min_lon, min_lat, max_lon, max_lat)
    line_ways = [e for e in line_elements if e.get("type") == "way" and "geometry" in e]
    print(f"Found {len(line_ways)} waterway ways from OSM.")

    line_polys = []
    line_tag_counts = {}
    for way in line_ways:
        tags = way.get("tags", {})
        waterway_type = tags.get("waterway", "")
        line_tag_counts[waterway_type] = line_tag_counts.get(waterway_type, 0) + 1
        width_m = WATERWAY_WIDTH_M.get(waterway_type, DEFAULT_WIDTH_M)

        coords = [(pt["lon"], pt["lat"]) for pt in way["geometry"]]
        if len(coords) < 2:
            continue
        line_wgs84 = LineString(coords)
        line_utm = shapely_transform(to_utm, line_wgs84)
        buffered_utm = line_utm.buffer(width_m / 2)
        buffered_raw_crs = shapely_transform(to_raw_crs, buffered_utm)
        line_polys.append(buffered_raw_crs)

    print(f"Buffered {len(line_polys)} waterway line segments.")
    print(f"Tag breakdown: {line_tag_counts}")

    # ---------- PASS 2 (NEW): natural=water / water=* polygons ----------
    print("\n--- PASS 2 (NEW): natural=water / water=* polygons ---")
    print("Querying Overpass for water body polygons in this tile...")
    poly_elements = query_overpass_water_polygons(min_lon, min_lat, max_lon, max_lat)
    poly_ways = [e for e in poly_elements if e.get("type") == "way" and "geometry" in e]
    print(f"Found {len(poly_ways)} water polygon ways from OSM.")

    water_polys = []
    poly_tag_counts = {}
    skipped_unclosed = 0
    for way in poly_ways:
        tags = way.get("tags", {})
        water_type = tags.get("water", tags.get("natural", "unknown"))
        poly_tag_counts[water_type] = poly_tag_counts.get(water_type, 0) + 1

        coords = [(pt["lon"], pt["lat"]) for pt in way["geometry"]]
        if len(coords) < 3:
            continue
        # OSM area ways should be closed rings (first coord == last);
        # if not, this way is likely part of a multipolygon relation
        # rather than a standalone closed polygon -- skip it rather than
        # guess at closing it, since a wrongly-closed ring could produce
        # a silently wrong polygon shape.
        if coords[0] != coords[-1]:
            skipped_unclosed += 1
            continue
        try:
            poly_wgs84 = Polygon(coords)
            if not poly_wgs84.is_valid or poly_wgs84.is_empty:
                skipped_unclosed += 1
                continue
        except Exception:
            skipped_unclosed += 1
            continue
        # Reproject WGS84 polygon directly to raw.tif's CRS (no meter
        # buffering needed here -- polygon is already real-world area).
        to_raw_direct = pyproj.Transformer.from_crs(
            "EPSG:4326", raw_crs, always_xy=True
        ).transform
        poly_raw_crs = shapely_transform(to_raw_direct, poly_wgs84)
        water_polys.append(poly_raw_crs)

    print(f"Kept {len(water_polys)} closed water polygons "
          f"(skipped {skipped_unclosed} unclosed/invalid -- likely "
          f"multipolygon relation members, not covered by this script).")
    print(f"Tag breakdown: {poly_tag_counts}")

    # ---------- Combine and rasterize ----------
    all_shapes = [(mapping(p), 1) for p in line_polys] + \
                 [(mapping(p), 1) for p in water_polys]

    if not all_shapes:
        print("\nNothing to rasterize from either pass -- no water "
              "signal found in this tile at all.")
        line_mask = np.zeros((tile_h, tile_w), dtype=bool)
        poly_mask = np.zeros((tile_h, tile_w), dtype=bool)
        combined_mask = np.zeros((tile_h, tile_w), dtype=bool)
    else:
        tile_transform = raw_transform

        line_mask = rasterize(
            [(mapping(p), 1) for p in line_polys],
            out_shape=(tile_h, tile_w), transform=tile_transform,
            fill=0, dtype=np.uint8,
        ).astype(bool) if line_polys else np.zeros((tile_h, tile_w), dtype=bool)

        poly_mask = rasterize(
            [(mapping(p), 1) for p in water_polys],
            out_shape=(tile_h, tile_w), transform=tile_transform,
            fill=0, dtype=np.uint8,
        ).astype(bool) if water_polys else np.zeros((tile_h, tile_w), dtype=bool)

        combined_mask = line_mask | poly_mask

    line_px = int(line_mask.sum())
    poly_px = int(poly_mask.sum())
    overlap_px = int((line_mask & poly_mask).sum())
    combined_px = int(combined_mask.sum())

    print(f"\n--- COMBINED RESULT ---")
    print(f"Pass 1 (waterway lines) pixels: {line_px}")
    print(f"Pass 2 (water polygons) pixels: {poly_px}")
    print(f"Overlap between passes: {overlap_px}")
    print(f"Combined (union) pixels: {combined_px} "
          f"({100*combined_px/(tile_h*tile_w):.2f}% of tile)")

    if combined_px == 0:
        print("Combined mask is still empty -- if you can visually see "
              "water in this tile, this may indicate a multipolygon "
              "relation gap (see caveat above), not a bug in this script.")

    out_dir = os.path.join(run_dir, "osm_water_mask")
    os.makedirs(out_dir, exist_ok=True)
    np.save(os.path.join(out_dir, "water_mask.npy"), combined_mask)
    # Keep the individual pass masks too, for debugging / transparency --
    # lets you visually check which pass contributed what, per the
    # project's own standard of not hiding data provenance.
    np.save(os.path.join(out_dir, "water_mask_pass1_lines.npy"), line_mask)
    np.save(os.path.join(out_dir, "water_mask_pass2_polygons.npy"), poly_mask)

    meta = {
        "city": city,
        "run_dir": run_dir,
        "tile_shape": [tile_h, tile_w],
        "raw_crs": str(raw_crs),
        "pass1_waterway_lines": {
            "num_osm_ways_used": len(line_polys),
            "tag_breakdown": line_tag_counts,
            "pixels": line_px,
        },
        "pass2_water_polygons": {
            "num_osm_ways_used": len(water_polys),
            "num_skipped_unclosed_or_invalid": skipped_unclosed,
            "tag_breakdown": poly_tag_counts,
            "pixels": poly_px,
            "note": "way-only query; multipolygon relations not fetched, "
                    "see script docstring caveat",
        },
        "overlap_pixels_between_passes": overlap_px,
        "combined_total_water_pixels": combined_px,
        "pct_of_tile": round(100 * combined_px / (tile_h * tile_w), 2),
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print(f"\nSaved combined mask to {out_dir}/water_mask.npy")
    print(f"Saved pass-1-only mask to {out_dir}/water_mask_pass1_lines.npy")
    print(f"Saved pass-2-only mask to {out_dir}/water_mask_pass2_polygons.npy")
    print(f"Saved meta.json with per-pass breakdown")
    print("\nNEXT STEP -- do not skip: run "
          f"'python check_generated_water_mask.py {city}' to visually "
          "confirm the COMBINED mask actually lines up with real water "
          "features in the tile image before merging it into training data.")


if __name__ == "__main__":
    main()