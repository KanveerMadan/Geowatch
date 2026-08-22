import geopandas as gpd
import numpy as np
import os
import json
from shapely.geometry import box


def get_osm_features(
    west: float, south: float, east: float, north: float,
    output_dir: str = "data/raw"
) -> dict:
    """
    Fetch OSM road and waterway features for AOI via Overpass API.
    Tries multiple endpoints with exponential backoff before giving up.

    Endpoint priority:
        1. overpass-api.de (primary — more reliable rate limits)
        2. kumi.systems (fallback)

    Returns:
        dict with keys 'roads' and 'waterways' — each a GeoDataFrame or None.
        None means the request failed, not that features are absent.
    """
    import requests
    import time
    from shapely.geometry import LineString

    os.makedirs(output_dir, exist_ok=True)
    result = {"roads": None, "waterways": None}

    ENDPOINTS = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
    ]

    query = (
        "[out:json][timeout:60];"
        "(way[\"highway\"]({s},{w},{n},{e});"
        "way[\"waterway\"]({s},{w},{n},{e});"
        "way[\"natural\"=\"water\"]({s},{w},{n},{e});"
        ");out geom;"
    ).format(s=south, w=west, n=north, e=east)

    data = None
    for endpoint in ENDPOINTS:
        for attempt in range(3):  # 3 attempts per endpoint
            try:
                wait = 2 ** attempt  # 1s, 2s, 4s
                if attempt > 0:
                    print(f"Retrying in {wait}s (attempt {attempt + 1}/3)...")
                    time.sleep(wait)

                print(f"Querying Overpass API ({endpoint})...")
                headers = {
                    "User-Agent": "GeoWatchCopilot/1.0 (kanveermadan@gmail.com)",
                    "Content-Type": "application/x-www-form-urlencoded",
                }
                response = requests.post(
                    endpoint,
                    data={"data": query},
                    headers=headers,
                    timeout=60,
                )
                response.raise_for_status()
                data = response.json()
                print(f"Overpass query succeeded via {endpoint}.")
                break  # success — exit retry loop

            except Exception as e:
                print(f"Attempt {attempt + 1} failed ({endpoint}): {e}")

        if data is not None:
            break  # success — exit endpoint loop
        print(f"All attempts failed for {endpoint}, trying next endpoint...")
        time.sleep(5)  # pause before switching endpoint

    if data is None:
        print("All Overpass endpoints failed. OSM features unavailable for this run.")
        print("road_access_score will be -1. OSM vector labels will be skipped.")
        return result

    roads = []
    waterways = []

    for element in data.get("elements", []):
        if "geometry" not in element:
            continue
        coords = [(pt["lon"], pt["lat"]) for pt in element["geometry"]]
        if len(coords) < 2:
            continue
        from shapely.geometry import LineString as LS
        line = LS(coords)
        tags = element.get("tags", {})

        if "highway" in tags:
            roads.append({
                "geometry": line,
                "highway": tags.get("highway"),
                "name": tags.get("name", ""),
            })
        elif "waterway" in tags or tags.get("natural") == "water":
            waterways.append({
                "geometry": line,
                "type": tags.get("waterway", "water"),
            })

    if roads:
        roads_gdf = gpd.GeoDataFrame(roads, crs="EPSG:4326")
        roads_path = os.path.join(output_dir, "roads.geojson")
        roads_gdf.to_file(roads_path, driver="GeoJSON")
        print(f"Roads saved: {roads_path} ({len(roads_gdf)} segments)")
        result["roads"] = roads_gdf
    else:
        print("No roads found in AOI.")

    if waterways:
        waterways_gdf = gpd.GeoDataFrame(waterways, crs="EPSG:4326")
        waterways_path = os.path.join(output_dir, "waterways.geojson")
        waterways_gdf.to_file(waterways_path, driver="GeoJSON")
        print(f"Waterways saved: {waterways_path} ({len(waterways_gdf)} features)")
        result["waterways"] = waterways_gdf
    else:
        print("No waterways found in AOI.")

    return result

def get_elevation_stats(
    west: float, south: float, east: float, north: float,
    output_dir: str = "data/raw"
) -> dict:
    """
    Get elevation data for AOI using Open Elevation API.
    Samples a 5x5 grid of points and returns basic stats.
    Retained for backward compatibility — HAND is the primary flood metric.

    Returns:
        dict with min/max/mean elevation, flood_risk_flag, and fallback flag
    """
    import requests

    os.makedirs(output_dir, exist_ok=True)

    lats = np.linspace(south, north, 5)
    lons = np.linspace(west, east, 5)
    locations = [
        {"latitude": float(lat), "longitude": float(lon)}
        for lat in lats for lon in lons
    ]

    try:
        print("Fetching elevation data from Open Elevation API...")
        response = requests.post(
            "https://api.open-elevation.com/api/v1/lookup",
            json={"locations": locations},
            timeout=30
        )
        response.raise_for_status()
        results = response.json()["results"]
        elevation_values = [r["elevation"] for r in results]
        print(f"Elevation data received: {len(elevation_values)} sample points.")

        stats = {
            "status": "available",
            "min_elevation_m": float(np.min(elevation_values)),
            "max_elevation_m": float(np.max(elevation_values)),
            "mean_elevation_m": float(np.mean(elevation_values)),
            "elevation_range_m": float(np.max(elevation_values) - np.min(elevation_values)),
            "sample_count": len(elevation_values),
            "flood_risk_flag": float(np.mean(elevation_values)) < 10.0,
            "elevation_fallback": False,
            "error": None,
        }
        print(f"Mean elevation: {stats['mean_elevation_m']}m | Flood risk flag: {stats['flood_risk_flag']}")

    except Exception as e:
        # PHASE 0 FIX: previously substituted 0m for every sample point,
        # which made flood_risk_flag=True (0 < 10) look like real evidence
        # instead of a failed API call. Missing data must never become
        # positive flood evidence. Callers MUST treat flood_risk_flag=None
        # as "not calculated", never as False.
        print(f"Open Elevation API failed: {e}")
        print("WARNING: Elevation data unavailable. Returning status=unavailable, "
              "NOT a 0m substitute.")
        stats = {
            "status": "unavailable",
            "min_elevation_m": None,
            "max_elevation_m": None,
            "mean_elevation_m": None,
            "elevation_range_m": None,
            "sample_count": 0,
            "flood_risk_flag": None,
            "elevation_fallback": True,
            "error": str(e),
        }

    output_path = os.path.join(output_dir, "elevation_stats.json")
    with open(output_path, "w") as f:
        json.dump(stats, f, indent=2)

    print(f"Elevation stats saved: {output_path}")
    return stats

def compute_relative_elevation_proxy(
    west: float, south: float, east: float, north: float,
) -> dict:
    """
    Compute a RELATIVE-ELEVATION flood susceptibility proxy for the AOI,
    using Copernicus DEM GLO-30 via Google Earth Engine.

    *** THIS IS NOT REAL HAND. *** (Corrected 2026-07 -- the docstring
    previously, incorrectly, described this as computing HAND via flow
    direction -> flow accumulation -> drainage network. It does not. The
    `flow_dir` and `slope` variables below are computed and NEVER used in
    the actual score. The real formula just rescales each pixel's elevation
    against this AOI's own p10/p90 elevation range and inverts it.

    Consequence: this score measures "how low is this pixel relative to the
    highest/lowest points WITHIN THIS SPECIFIC AOI BOX", not "how close is
    this pixel to a real drainage channel". A uniformly low-lying, genuinely
    flood-prone area (e.g. a floodplain settlement) will NOT reliably score
    high here, because the metric only responds to internal elevation
    spread inside the box, not absolute flood exposure. This is very likely
    why Dharavi -- a textbook flood-prone site -- scored 0.4581, under the
    0.6 "risk" threshold.

    TODO (needs a real fix, tracked separately, not a threshold tweak):
    replace this with true HAND using a real drainage network -- e.g.
    derive it from MERIT Hydro's flow-direction / upstream-drainage-area
    bands (confirmed available in GEE as MERIT/Hydro/v1_0_1), or import a
    precomputed HAND raster. This requires a design decision (build vs.
    import) before implementation.

    CRITICAL CAVEAT: Copernicus DEM GLO-30 is a DSM (Digital Surface Model),
    not a DTM. Building heights are embedded in the elevation values, which
    biases HAND upward in dense urban areas even after a real HAND fix.
    This must appear in all scientific outputs citing these results.

    Returns:
        dict with:
            susceptibility_score  float [0,1] -- mean RELATIVE-ELEVATION
                                   susceptibility over AOI (NOT real HAND,
                                   see caveat above)
            flood_risk_flag       bool -- True if susceptibility_score > 0.6
                                   (this threshold has NOT been validated
                                   against real flood outcomes; treat as
                                   provisional until real HAND replaces this)
            elevation_fallback    bool -- True if GEE call failed (crude fallback used)
            dsm_caveat            bool -- always True; reminder that GLO-30 is DSM not DTM
            method                str  -- always "relative_elevation_proxy_not_real_hand"
    """
    try:
        import ee
        from ingestion.gee_client import initialize_gee

        initialize_gee()

        aoi = ee.Geometry.Rectangle([west, south, east, north])

        dem = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1") \
            .filterBounds(aoi) \
            .mosaic() \
            .select("DEM") \
            .clip(aoi)
        
        # Flow direction using D8 algorithm (GEE terrain analysis)
        flow_dir = ee.Terrain.fillMinima(dem)

        # Flow accumulation — proxy for drainage network delineation
        # Use slope as a proxy where flow accumulation isn't directly available
        terrain = ee.Terrain.products(dem)
        slope = terrain.select("slope")

        # HAND approximation: low slope + low elevation relative to AOI min = high susceptibility
        # True HAND requires hydrological routing; this is a GEE-feasible approximation
        aoi_stats = dem.reduceRegion(
            reducer=ee.Reducer.percentile([10, 50, 90]),
            geometry=aoi,
            scale=30,
            maxPixels=1e8,
        ).getInfo()

        elev_p10 = aoi_stats.get("DEM_p10", None)
        elev_p90 = aoi_stats.get("DEM_p90", None)

        if elev_p10 is None or elev_p90 is None:
            raise ValueError("Could not extract DEM percentiles from GEE.")

        elev_range = float(elev_p90) - float(elev_p10)
        if elev_range < 1.0:
            elev_range = 1.0  # flat terrain — avoid division by zero

        # HAND proxy: normalise elevation to [0,1] relative to AOI range,
        # then invert so low-lying areas (near drainage) score high susceptibility
        hand_proxy = dem.subtract(elev_p10).divide(elev_range).clamp(0, 1)
        hand_susceptibility = ee.Image(1).subtract(hand_proxy)

        # Mean susceptibility over AOI
        mean_result = hand_susceptibility.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=aoi,
            scale=30,
            maxPixels=1e8,
        ).getInfo()

        susceptibility_score = mean_result.get("constant", None)
        if susceptibility_score is None:
            raise ValueError("Relative-elevation reduction returned no value.")

        susceptibility_score = float(susceptibility_score)

        print(f"Relative-elevation proxy score: {susceptibility_score:.3f} (NOT real HAND, unvalidated threshold)")
        print("NOTE: Copernicus DEM GLO-30 is DSM not DTM — proxy biased in dense urban areas.")

        return {
            "status": "experimental",
            "score": round(susceptibility_score, 4),
            "method": "aoi_relative_p10_p90_inverted",
            "true_hand": False,
            "hydrologically_conditioned": False,
            "dem_source": "COPERNICUS/DEM/GLO30_2024_1",
            "dem_type": "DSM",
            "validated": False,
            "threshold_used": None,
            "error": None,
        }

    except Exception as e:
        print(f"Relative-elevation proxy computation failed: {e}")
        return {
            "status": "unavailable",
            "score": None,
            "method": "aoi_relative_p10_p90_inverted",
            "true_hand": False,
            "hydrologically_conditioned": False,
            "dem_source": "COPERNICUS/DEM/GLO30_2024_1",
            "dem_type": "DSM",
            "validated": False,
            "threshold_used": None,
            "error": str(e),
        }
def compute_hand_flood_susceptibility(west, south, east, north) -> dict:
    """DEPRECATED (Phase 0): renamed to compute_relative_elevation_proxy()
    because this was never real HAND. This wrapper exists only so old
    callers don't hard-crash during migration — update callers to use
    the new name and the new dict keys (status/score, not
    susceptibility_score/flood_risk_flag)."""
    print("DEPRECATION WARNING: compute_hand_flood_susceptibility() is "
          "renamed to compute_relative_elevation_proxy(). Update the caller.")
    return compute_relative_elevation_proxy(west, south, east, north)

def compute_road_distance_map(
    roads_gdf,
    west: float, south: float, east: float, north: float,
    img_width: int, img_height: int,
) -> np.ndarray:
    """
    Rasterize OSM road geometries onto the tile pixel grid and compute a
    normalized distance transform map.

    The key fix: road geometries are in lon/lat (EPSG:4326). Pixel coordinates
    from SAM bboxes are in image pixel space. This function converts road
    geometries to pixel space using the tile's geographic extent, so that
    compute_road_access_score() can compare them correctly.

    Algorithm:
        1. For each road LineString, convert lon/lat vertices to pixel coords
           using the tile's geographic extent (west/east/south/north).
        2. Rasterize all road lines onto a binary pixel grid (1 = road, 0 = not).
        3. Run scipy distance_transform_edt on the inverted grid to get
           per-pixel distance (in pixels) to the nearest road.
        4. Normalize to [0,1] where 0 = on a road, 1 = maximally far.

    Args:
        roads_gdf: GeoDataFrame with road LineString geometries in EPSG:4326
        west, south, east, north: tile geographic extent in decimal degrees
        img_width, img_height: tile dimensions in pixels

    Returns:
        np.ndarray of shape (img_height, img_width), dtype float32
        Values in [0,1]: 0.0 = road pixel, 1.0 = farthest from any road.
        Returns None if roads_gdf is None or empty.
    """
    from scipy.ndimage import distance_transform_edt

    if roads_gdf is None or (hasattr(roads_gdf, "empty") and roads_gdf.empty):
        return None

    lon_per_px = (east - west) / img_width
    lat_per_px = (north - south) / img_height

    def lon_to_px(lon):
        return (lon - west) / lon_per_px

    def lat_to_py(lat):
        # Image y=0 is at north; lat increases southward in pixel space
        return (north - lat) / lat_per_px

    # Binary road mask: 1 where road exists, 0 elsewhere
    road_mask = np.zeros((img_height, img_width), dtype=np.uint8)

    for geom in roads_gdf.geometry:
        if geom is None:
            continue
        try:
            coords = list(geom.coords)
        except Exception:
            continue

        for i in range(len(coords) - 1):
            x0, y0 = lon_to_px(coords[i][0]), lat_to_py(coords[i][1])
            x1, y1 = lon_to_px(coords[i + 1][0]), lat_to_py(coords[i + 1][1])

            # Bresenham-style line rasterization via linspace
            n_steps = max(int(np.hypot(x1 - x0, y1 - y0)) * 2 + 1, 2)
            xs = np.linspace(x0, x1, n_steps)
            ys = np.linspace(y0, y1, n_steps)

            for x, y in zip(xs, ys):
                xi, yi = int(round(x)), int(round(y))
                if 0 <= xi < img_width and 0 <= yi < img_height:
                    road_mask[yi, xi] = 1

    road_px_count = int(road_mask.sum())
    print(f"Road mask: {road_px_count} road pixels rasterized onto {img_width}x{img_height} grid.")

    if road_px_count == 0:
        print("Warning: OSM roads returned but rasterized to 0 pixels — AOI extent mismatch?")
        return None

    # Distance transform: per-pixel distance to nearest road pixel
    # distance_transform_edt operates on the INVERSE: 0=road → distance from non-road to road
    inverted = 1 - road_mask
    dist_px = distance_transform_edt(inverted).astype(np.float32)

    # Normalize to [0, 1]
    max_dist = dist_px.max()
    if max_dist > 0:
        dist_map = dist_px / max_dist
    else:
        dist_map = dist_px  # all zeros — entire tile is road

    return dist_map

def compute_waterway_distance_map(
    waterways_gdf,
    west: float, south: float, east: float, north: float,
    img_width: int, img_height: int,
) -> np.ndarray:
    """
    Same algorithm as compute_road_distance_map(), applied to OSM
    waterway geometry instead of roads. Used for the standing_water
    proximity confidence adjustment (Phase 3 item #3) -- same rationale
    as the road version, but weaker expected effect, since OSM water
    body coverage (especially small/seasonal ponds) is less complete
    than road coverage. See master doc Phase 3 discussion.
    """
    from scipy.ndimage import distance_transform_edt

    if waterways_gdf is None or (hasattr(waterways_gdf, "empty") and waterways_gdf.empty):
        return None

    lon_per_px = (east - west) / img_width
    lat_per_px = (north - south) / img_height

    def lon_to_px(lon):
        return (lon - west) / lon_per_px

    def lat_to_py(lat):
        return (north - lat) / lat_per_px

    water_mask = np.zeros((img_height, img_width), dtype=np.uint8)

    for geom in waterways_gdf.geometry:
        if geom is None:
            continue
        try:
            coords = list(geom.coords)
        except Exception:
            continue

        for i in range(len(coords) - 1):
            x0, y0 = lon_to_px(coords[i][0]), lat_to_py(coords[i][1])
            x1, y1 = lon_to_px(coords[i + 1][0]), lat_to_py(coords[i + 1][1])
            n_steps = max(int(np.hypot(x1 - x0, y1 - y0)) * 2 + 1, 2)
            xs = np.linspace(x0, x1, n_steps)
            ys = np.linspace(y0, y1, n_steps)
            for x, y in zip(xs, ys):
                xi, yi = int(round(x)), int(round(y))
                if 0 <= xi < img_width and 0 <= yi < img_height:
                    water_mask[yi, xi] = 1

    water_px_count = int(water_mask.sum())
    print(f"Waterway mask: {water_px_count} waterway pixels rasterized onto {img_width}x{img_height} grid.")

    if water_px_count == 0:
        return None

    inverted = 1 - water_mask
    dist_px = distance_transform_edt(inverted).astype(np.float32)
    max_dist = dist_px.max()
    return dist_px / max_dist if max_dist > 0 else dist_px

def compute_road_access_score(
    segment_bbox: list,
    roads_gdf,
    west: float = None,
    south: float = None,
    east: float = None,
    north: float = None,
    img_width: int = None,
    img_height: int = None,
    dist_map: np.ndarray = None,
) -> float:
    """
    Compute a graded road access score for a segment bounding box.

    Uses the precomputed distance transform map (dist_map) when available.
    Falls back to -1.0 if OSM is unavailable.

    The score is the mean of (1 - normalized_distance) over all pixels
    in the segment bbox, so:
        1.0 = segment entirely on roads
        0.0 = segment maximally far from all roads
       -1.0 = OSM data unavailable

    label_source in the returned context is "distance_transform" when
    dist_map is used, "unavailable" otherwise.

    Args:
        segment_bbox: [x, y, w, h] in pixel coordinates (from SAM)
        roads_gdf: GeoDataFrame or None
        west/south/east/north: tile geographic extent (needed if dist_map is None)
        img_width/img_height: tile dimensions (needed if dist_map is None)
        dist_map: precomputed distance map from compute_road_distance_map()

    Returns:
        float: -1.0 (unavailable), or 0.0–1.0 (graded proximity score)
    """
    if roads_gdf is None or (hasattr(roads_gdf, "empty") and roads_gdf.empty):
        return -1.0

    # Build dist_map on the fly if not precomputed (fallback path)
    if dist_map is None:
        if None in (west, south, east, north, img_width, img_height):
            return -1.0
        dist_map = compute_road_distance_map(
            roads_gdf, west, south, east, north, img_width, img_height
        )
        if dist_map is None:
            return -1.0

    x, y, w, h = segment_bbox
    x, y, w, h = int(x), int(y), int(w), int(h)

    h_map, w_map = dist_map.shape

    # Clamp bbox to map bounds
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(w_map, x + w)
    y2 = min(h_map, y + h)

    if x2 <= x1 or y2 <= y1:
        return 0.0

    region = dist_map[y1:y2, x1:x2]
    # Score = mean proximity (1 - normalized distance)
    score = float(1.0 - region.mean())
    return round(max(0.0, min(1.0, score)), 4)


def apply_osm_vector_labels(
    classifications: list,
    osm_features: dict,
    west: float,
    south: float,
    east: float,
    north: float,
    img_width: int,
    img_height: int,
    road_proximity_px: float = 15.0,
    waterway_proximity_px: float = 10.0,
) -> list:
    """
    Post-process classifications to tag segments with OSM-derived labels
    for the 3 categories that are physically unresolvable at 10m Sentinel-2:

        unpaved_dirt_road     — segment bbox overlaps OSM unpaved/track highway
        open_drainage_channel — segment bbox near OSM waterway (drain/canal)
        open_waste            — segment bbox near OSM landuse=landfill or amenity=waste*

    Only overrides segments currently labeled 'unknown' or whose existing ML
    label is one of the 3 unresolvable categories. Never overrides a segment
    that has a confident ML label for a resolvable category.

    Sets label_source = "osm_vector" on any overridden segment.

    OSM highway types mapped to unpaved_dirt_road:
        track, path, footway, bridleway, unclassified, service (unpaved surface tag)

    Args:
        classifications: list of segment dicts from classify_tile()
        osm_features: dict from get_osm_features() — keys 'roads', 'waterways'
        west/south/east/north: tile geographic extent
        img_width/img_height: tile dimensions in pixels
        road_proximity_px: pixel buffer for unpaved road proximity check
        waterway_proximity_px: pixel buffer for waterway proximity check

    Returns:
        classifications list with label_source="osm_vector" segments updated in-place
    """
    roads_gdf = osm_features.get("roads")
    waterways_gdf = osm_features.get("waterways")

    if roads_gdf is None and waterways_gdf is None:
        print("OSM vector labels: no OSM data available, skipping.")
        return classifications

    lon_per_px = (east - west) / img_width
    lat_per_px = (north - south) / img_height

    def bbox_centroid_lonlat(bbox):
        x, y, w, h = bbox
        cx_px = x + w / 2.0
        cy_px = y + h / 2.0
        lon = west + cx_px * lon_per_px
        lat = north - cy_px * lat_per_px
        return lon, lat

    def bbox_to_geo_box(bbox, buffer_px=0):
        x, y, w, h = bbox
        buf_lon = buffer_px * lon_per_px
        buf_lat = buffer_px * lat_per_px
        x_west  = west  + x * lon_per_px - buf_lon
        x_east  = west  + (x + w) * lon_per_px + buf_lon
        y_north = north - y * lat_per_px + buf_lat
        y_south = north - (y + h) * lat_per_px - buf_lat
        return box(x_west, y_south, x_east, y_north)

    # Unpaved road highway types at 10m resolution
    UNPAVED_HIGHWAY_TYPES = {
        "track", "path", "footway", "bridleway",
        "unclassified", "service", "living_street", "steps",
    }

    # Filter roads to unpaved types only
    unpaved_roads_gdf = None
    if roads_gdf is not None and not roads_gdf.empty:
        mask = roads_gdf["highway"].isin(UNPAVED_HIGHWAY_TYPES)
        if mask.any():
            unpaved_roads_gdf = roads_gdf[mask].copy()
            print(f"OSM vector: {len(unpaved_roads_gdf)} unpaved road segments available.")

    # Drain/canal waterways for open_drainage_channel
    drain_gdf = None
    if waterways_gdf is not None and not waterways_gdf.empty:
        if "type" in waterways_gdf.columns:
            drain_mask = waterways_gdf["type"].isin({"drain", "canal", "ditch", "stream"})
            if drain_mask.any():
                drain_gdf = waterways_gdf[drain_mask].copy()
                print(f"OSM vector: {len(drain_gdf)} drain/canal features available.")

    # Categories eligible for OSM vector override
    OVERRIDABLE = {"unknown", "unpaved_dirt_road", "open_drainage_channel", "open_waste"}

    osm_tagged_count = 0

    for seg in classifications:
        if seg.get("category") not in OVERRIDABLE:
            continue

        bbox = seg["bbox"]

        # ── Check unpaved_dirt_road ──
        if unpaved_roads_gdf is not None:
            seg_geo = bbox_to_geo_box(bbox, buffer_px=road_proximity_px)
            try:
                intersects = unpaved_roads_gdf.geometry.intersects(seg_geo)
                if intersects.any():
                    seg["category"] = "unpaved_dirt_road"
                    seg["label_source"] = "osm_vector"
                    seg["osm_feature_type"] = "highway_unpaved"
                    osm_tagged_count += 1
                    continue
            except Exception as e:
                print(f"OSM vector road check error (seg {seg['segment_id']}): {e}")

        # ── Check open_drainage_channel ──
        if drain_gdf is not None:
            seg_geo = bbox_to_geo_box(bbox, buffer_px=waterway_proximity_px)
            try:
                intersects = drain_gdf.geometry.intersects(seg_geo)
                if intersects.any():
                    seg["category"] = "open_drainage_channel"
                    seg["label_source"] = "osm_vector"
                    seg["osm_feature_type"] = "waterway_drain"
                    osm_tagged_count += 1
                    continue
            except Exception as e:
                print(f"OSM vector waterway check error (seg {seg['segment_id']}): {e}")

       # ── open_waste proximity inference DISABLED (Phase 0) ──
        # Waterway proximity is not evidence of waste — tagging a segment
        # open_waste from proximity alone was an unsafe inference per
        # Phase 0's ethical constraints (never infer open_waste merely
        # because a segment is near a waterway). Replaced with neutral
        # metadata only; category is left untouched.
        if waterways_gdf is not None and not waterways_gdf.empty:
            if seg.get("category") == "unknown":
                seg_geo = bbox_to_geo_box(bbox, buffer_px=waterway_proximity_px * 2)
                try:
                    intersects = waterways_gdf.geometry.intersects(seg_geo)
                    if intersects.any():
                        seg["near_mapped_waterway"] = True
                except Exception as e:
                    print(f"OSM vector waterway-proximity check error (seg {seg['segment_id']}): {e}")

    print(f"OSM vector labels applied: {osm_tagged_count} segments re-tagged.")
    return classifications