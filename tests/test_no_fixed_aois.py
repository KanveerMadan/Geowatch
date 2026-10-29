"""GeoWatch is global: the API serves any AOI and keeps no fixed city list
and no Dharavi default. City labels in tests are fixtures, not defaults."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    import api
    return TestClient(api.app, headers={api.API_KEY_HEADER_NAME: api.API_KEY})


def test_api_keeps_no_watched_city_list(client):
    import api
    for name in ("WATCHED_AOIS", "refresh_all_watched_aois", "_validate_watched_aois"):
        assert not hasattr(api, name), name
    assert "watched_aois" not in client.get("/api/scheduler/status").json()


def test_no_dharavi_demo_endpoint(client):
    import api
    assert not hasattr(api, "get_demo")
    assert client.get("/api/demo").status_code == 404


@pytest.mark.parametrize("route", ["/api/analyze", "/api/legacy/analyze"])
def test_demo_mode_is_refused_not_served_a_fixed_city(client, route):
    r = client.post(route, json={"west": 0, "south": 0, "east": 0.01, "north": 0.01,
                                 "aoi_label": "aoi", "demo": True})
    assert r.status_code == 400
    assert "dharavi" not in r.json()["detail"].lower()
