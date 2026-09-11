"""
Shared fixtures for Phase 0 flood-safety tests.
"""
import os

import pytest
import numpy as np

# C40 / build item 70: api.py refuses to import without GEOWATCH_API_KEY, by
# design — a missing-secret default is how an "authenticated" service ships
# unauthenticated. Tests need a value present before `import api` runs at
# collection time, and conftest is imported first, so it is set here.
# setdefault, not assignment: a real key in the environment is left alone.
TEST_API_KEY = "test-key-not-a-real-secret"
os.environ.setdefault("GEOWATCH_API_KEY", TEST_API_KEY)


@pytest.fixture
def canonical_dharavi_bbox():
    """The canonical apples-to-apples test AOI used across the project."""
    return {"west": 72.836, "south": 19.037, "east": 72.862, "north": 19.060}


@pytest.fixture
def mock_open_elevation_success(monkeypatch):
    """Simulates a healthy Open Elevation API response."""
    class MockResponse:
        def raise_for_status(self):
            pass
        def json(self):
            return {"results": [{"elevation": 6.08} for _ in range(25)]}

    def mock_post(*args, **kwargs):
        return MockResponse()

    monkeypatch.setattr("requests.post", mock_post)


@pytest.fixture
def mock_open_elevation_failure(monkeypatch):
    """Simulates the 504 Gateway Timeout seen in real pipeline runs."""
    def mock_post(*args, **kwargs):
        import requests
        raise requests.exceptions.HTTPError("504 Server Error: Gateway Timeout")

    monkeypatch.setattr("requests.post", mock_post)


@pytest.fixture
def mock_gee_proxy_success(monkeypatch):
    def mock_proxy(west, south, east, north):
        return {
            "status": "experimental",
            "score": 0.4581,
            "method": "aoi_relative_p10_p90_inverted",
            "true_hand": False,
            "hydrologically_conditioned": False,
            "dem_source": "COPERNICUS/DEM/GLO30_2024_1",
            "dem_type": "DSM",
            "validated": False,
            "threshold_used": None,
            "error": None,
        }
    monkeypatch.setattr("pipeline.compute_relative_elevation_proxy", mock_proxy)


@pytest.fixture
def mock_gee_proxy_failure(monkeypatch):
    def mock_proxy(west, south, east, north):
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
            "error": "EEException: Earth Engine client not initialized.",
        }
    monkeypatch.setattr("pipeline.compute_relative_elevation_proxy", mock_proxy)