"""C46 (2026-09-25): POST /api/scheduler/trigger is disabled with an explicit
HTTP error naming the retired 7-class pipeline. POST /api/analyze is NOT
disabled (the UI's Analyze button depends on it); its results are marked."""
import pathlib
import sys
import types

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
REPO = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def stub_pipeline(monkeypatch):
    stub = types.ModuleType("pipeline")
    stub.run_pipeline = lambda **kw: {"run_id": "stub", "legacy_pipeline": {"retired": True}}
    stub.run_inundation_analysis = lambda **kw: pytest.fail("not under test")
    monkeypatch.setitem(sys.modules, "pipeline", stub)


@pytest.fixture
def authed():
    import api
    return api, TestClient(api.app, headers={api.API_KEY_HEADER_NAME: api.API_KEY})


def test_trigger_returns_410_with_the_reason(authed):
    api, client = authed
    before = api.scheduler.get_job("auto_refresh").next_run_time
    r = client.post("/api/scheduler/trigger")
    assert r.status_code == 410
    assert "7-class pipeline is retired" in r.json()["detail"]
    assert "C46" in r.json()["detail"]
    # Nothing was queued: the job's next run time is untouched.
    assert api.scheduler.get_job("auto_refresh").next_run_time == before


def test_trigger_still_requires_auth_first():
    import api
    assert TestClient(api.app).post("/api/scheduler/trigger").status_code == 401


def test_analyze_is_not_disabled(authed):
    api, client = authed
    r = client.post("/api/analyze", json={"aoi_label": "dharavi", "west": 72.836,
                                          "south": 19.037, "east": 72.862, "north": 19.060})
    assert r.status_code == 200
    assert r.json()["legacy_pipeline"]["retired"] is True


def test_run_pipeline_marks_every_result():
    src = (REPO / "pipeline.py").read_text()
    block = src[src.index("def run_pipeline("):src.index("def run_inundation_analysis(")]
    assert '"legacy_pipeline": {' in block
    assert '"notice": "Legacy 7-class pipeline — retired, not validated."' in block
