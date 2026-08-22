from ingestion.osm_dem import apply_osm_vector_labels
import geopandas as gpd
from shapely.geometry import LineString


def test_waterway_proximity_no_longer_assigns_open_waste():
    waterways_gdf = gpd.GeoDataFrame(
        [{"geometry": LineString([(72.8375, 19.058), (72.838, 19.059)]), "type": "river"}],
        crs="EPSG:4326",
    )
    osm_features = {"roads": None, "waterways": waterways_gdf}

    segments = [{
        "segment_id": 0,
        "bbox": [10, 10, 20, 20],
        "category": "unknown",
    }]

    result = apply_osm_vector_labels(
        segments, osm_features,
        west=72.836, south=19.037, east=72.862, north=19.060,
        img_width=291, img_height=257,
    )

    assert result[0]["category"] == "unknown"
    assert result[0].get("near_mapped_waterway") is True