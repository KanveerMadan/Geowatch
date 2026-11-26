import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def hosted(monkeypatch, tmp_path):
    monkeypatch.setenv("GEOWATCH_DEPLOY_NO_AUTOBUILD", "1")
    monkeypatch.setenv("GEOWATCH_API_KEY", "test-only-hosted")
    monkeypatch.chdir(tmp_path)
    gateway = importlib.import_module("deploy.asgi")
    import api
    wrapper = gateway.GeoWatchGateway(
        api.app, api_key=api.API_KEY, cors_origins=["https://site.example"],
        limiter=gateway.RateLimiter(gateway.limits_from_env()),
    )
    return TestClient(wrapper)


def test_public_site_reads_limits_and_change_routes(hosted):
    assert hosted.get("/").json()["max_aoi_area_km2"] > 0
    assert hosted.get("/api/boundaries").status_code == 200
    missing = "r" + "0" * 24
    assert hosted.get(f"/api/results/{missing}/change/features").status_code == 404
    assert hosted.get("/api/jobs/j" + "0" * 24).status_code == 404


def test_public_site_can_submit_but_cannot_run_admin_routes(hosted):
    assert hosted.post("/api/jobs", json={}).status_code == 422
    assert hosted.post("/api/scheduler/trigger").status_code == 401
    assert hosted.post("/api/analyze", json={}).status_code == 401
    preflight = hosted.options("/api/jobs", headers={"Origin": "https://site.example"})
    assert preflight.headers["access-control-allow-origin"] == "https://site.example"
