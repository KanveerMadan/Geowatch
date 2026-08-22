from ingestion.osm_dem import get_osm_features, get_elevation_stats

# Dharavi bounding box
west, south, east, north = 72.836, 19.037, 72.862, 19.060

# Fetch OSM features
features = get_osm_features(west, south, east, north, output_dir="data/raw/dharavi")

# Fetch elevation
elevation = get_elevation_stats(west, south, east, north, output_dir="data/raw/dharavi")

print("\n── Summary ──")
if features["roads"] is not None:
    print(f"Road segments: {len(features['roads'])}")
if features["waterways"] is not None:
    print(f"Waterway features: {len(features['waterways'])}")
print(f"Elevation range: {elevation['min_elevation_m']}m – {elevation['max_elevation_m']}m")
print(f"Flood risk flag: {elevation['flood_risk_flag']}")