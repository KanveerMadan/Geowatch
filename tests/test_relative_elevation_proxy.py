"""
Phase 0, requirement B: fake-HAND rename + honest metadata.
"""
from ingestion import osm_dem


def test_deprecated_wrapper_still_callable(canonical_dharavi_bbox, mock_gee_proxy_success):
    """Old callers using the pre-Phase-0 name must not hard-crash during
    migration -- the deprecated wrapper should delegate cleanly."""
    result = osm_dem.compute_hand_flood_susceptibility(**canonical_dharavi_bbox)
    assert result["status"] == "experimental"
    assert result["true_hand"] is False


def test_new_name_returns_honest_metadata(canonical_dharavi_bbox, mock_gee_proxy_success):
    result = osm_dem.compute_relative_elevation_proxy(**canonical_dharavi_bbox)

    assert result["true_hand"] is False
    assert result["hydrologically_conditioned"] is False
    assert result["validated"] is False
    assert result["method"] == "aoi_relative_p10_p90_inverted"
    assert result["dem_type"] == "DSM"
    assert result["dem_source"] == "COPERNICUS/DEM/GLO30_2024_1"


def test_proxy_failure_returns_unavailable_not_default_score(canonical_dharavi_bbox, monkeypatch):
    """Tests osm_dem's own failure handling directly, by breaking the
    real GEE call it makes internally -- the pipeline-level
    mock_gee_proxy_failure fixture doesn't apply here since this test
    calls osm_dem.compute_relative_elevation_proxy() directly, not
    through pipeline.py. initialize_gee is imported inside the function
    body from ingestion.gee_client, so we patch it at the source."""
    def broken_initialize_gee():
        raise Exception("EEException: Earth Engine client not initialized.")

    monkeypatch.setattr("ingestion.gee_client.initialize_gee", broken_initialize_gee)

    result = osm_dem.compute_relative_elevation_proxy(**canonical_dharavi_bbox)
    assert result["status"] == "unavailable"
    assert result["score"] is None
    assert result["error"] is not None