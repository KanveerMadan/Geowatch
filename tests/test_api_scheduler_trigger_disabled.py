"""C46 (2026-09-25): POST /api/scheduler/trigger is disabled with an explicit
HTTP error naming the retired 7-class pipeline, and the 5-day auto-refresh job
that ran run_pipeline is removed. POST /api/analyze is NOT disabled (the UI's
Analyze button depends on it); its results are marked. /api/demo serves the
last stored result, marked."""
import json
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
    r = client.post("/api/scheduler/trigger")
    assert r.status_code == 410
    assert "7-class pipeline is retired" in r.json()["detail"]
    assert "C46" in r.json()["detail"]


def test_no_scheduler_runs_the_pipeline_on_a_timer():
    import api
    assert not hasattr(api, "scheduler")
    src = (REPO / "api.py").read_text()
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    for banned in ("BackgroundScheduler", "add_job", "apscheduler"):
        assert banned not in code, banned


def test_root_and_status_report_disabled(authed):
    _, client = authed
    root = client.get("/").json()
    assert root["scheduler"] == "disabled" and root["next_auto_refresh"] is None
    st = client.get("/api/scheduler/status").json()
    assert st["scheduler_running"] is False and st["status"] == "disabled"
    assert "C46" in st["reason"]


def test_demo_serves_stored_result_marked_without_touching_it(authed, tmp_path, monkeypatch):
    api, client = authed
    stored = {"run_id": "dharavi_20260101_000000", "landcover": {}}      # pre-marker run
    monkeypatch.setattr(api, "get_latest_run", lambda label: dict(stored))
    body = client.get("/api/demo").json()
    assert body["legacy_pipeline"]["notice"] == "Legacy 7-class pipeline — retired, not validated."
    assert body["_demo_mode"] is True and "C46" in body["_auto_refresh"]
    assert "legacy_pipeline" not in stored                                 # source untouched


def test_demo_keeps_an_existing_marker(authed, monkeypatch):
    api, client = authed
    marker = {"retired": True, "validated": False, "notice": "from the run"}
    monkeypatch.setattr(api, "get_latest_run", lambda label: {"legacy_pipeline": marker})
    assert client.get("/api/demo").json()["legacy_pipeline"] == marker


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
    assert '"legacy_pipeline": legacy_pipeline_marker(),' in block


def test_one_marker_wording_for_backend_and_ui():
    from configs.legacy_pipeline import LEGACY_PIPELINE_NOTICE, legacy_pipeline_marker
    ui = (REPO / "geowatch-ui" / "src" / "legacyPipeline.js").read_text()
    assert f"'{LEGACY_PIPELINE_NOTICE}'" in ui
    assert legacy_pipeline_marker() == {"retired": True, "validated": False,
                                        "notice": LEGACY_PIPELINE_NOTICE}
