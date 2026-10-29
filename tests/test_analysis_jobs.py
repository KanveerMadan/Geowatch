"""Phase 4: the job API. POST starts an analysis and returns a job id at once;
GET reports per-stage status and each output group as it is final.

    queued -> running -> per stage ok / failed / timeout -> complete
                       -> failed (the run itself raised)

The cache still applies: a stored area is a job born complete."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from analysis import contract as C
from analysis import jobs, store
from tests import analysis_synth as S

BBOX = S.BBOX
START, END = "2026-01-01", "2026-03-31"


def _runner(calls, **dep_overrides):
    from analysis.run import run_analysis

    def runner(bbox, window, **kw):
        calls.append(window)
        return run_analysis(bbox, window, deps=S.deps(**dep_overrides), **kw)
    return runner


def _submit(tmp_path, calls, executor=None, **dep):
    return jobs.submit(BBOX, START, END, name="synth", root=str(tmp_path), executor=executor,
                       producer=S.SynthProducer(), commit=S.COMMIT,
                       runner=_runner(calls, **dep))


def _wait(jid, until, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = jobs.get(jid)
        if until(j):
            return j
        time.sleep(0.02)
    raise AssertionError(f"job never reached the state; last: {jobs.get(jid)['status']}")


def _done(j):
    return j["status"] in ("complete", "failed")


def test_lifecycle_queued_running_stages_partial_complete(tmp_path):
    gate, entered = threading.Event(), threading.Event()

    def held_change(layer, epochs):
        entered.set()
        gate.wait(30)
        return S.fake_change(layer, epochs)

    pool = ThreadPoolExecutor(1)
    calls = []
    first = _submit(tmp_path, calls, executor=pool, run_change=held_change)
    assert first["status"] in ("queued", "running") and jobs.valid_id(first["job_id"])
    assert entered.wait(30)
    # A second job behind it in the one-worker pool waits, queued.
    second = jobs.submit((BBOX[0], BBOX[1], BBOX[2], BBOX[3] + 1e-4), START, END, name="synth",
                         root=str(tmp_path), executor=pool, producer=S.SynthProducer(),
                         commit=S.COMMIT, runner=_runner([]))
    assert jobs.get(second["job_id"])["status"] == "queued"

    mid = jobs.get(first["job_id"])
    assert mid["status"] == "running" and mid["result"] is None
    assert mid["stages"]["road_layer"]["status"] == "ok"
    assert mid["stages"]["s2_composite"]["status"] == "ok"
    assert mid["stages"]["change"]["status"] == "running"
    # Output groups finished before change are already served, in contract shape.
    assert {"fractions", "observability", "susceptibility"} <= set(mid["partial"])
    assert "change" not in mid["partial"]
    for f in mid["partial"]["fractions"].values():
        C.check_output(f)

    gate.set()
    done = _wait(first["job_id"], _done)
    assert done["status"] == "complete" and done["stored"] and not done["cached"]
    assert store.valid_id(done["result_id"]) and done["result"]["result_id"] == done["result_id"]
    assert all(s["status"] == "ok" for s in done["stages"].values())
    C.check_result(done["result"])
    assert _wait(second["job_id"], _done)["status"] == "complete"
    pool.shutdown()


def test_cached_area_is_a_job_born_complete(tmp_path):
    calls = []
    a = _wait(_submit(tmp_path, calls)["job_id"], _done)
    b = _submit(tmp_path, calls)
    assert len(calls) == 1                                   # no second run
    assert b["status"] == "complete" and b["cached"] and b["result_id"] == a["result_id"]
    assert b["result"]["result_id"] == a["result_id"]


def test_failed_stage_completes_unstored(tmp_path):
    def broken():
        raise ConnectionError("down")
    j = _wait(_submit(tmp_path, [], context_fns=S.context_fns({"hand": broken}))["job_id"], _done)
    assert j["status"] == "complete" and j["stored"] is False and j["result_id"] is None
    assert j["stages"]["context:hand"]["status"] == "failed"
    assert j["not_stored_because"] == {"context:hand": "failed"}


def test_timed_out_stage_is_its_own_status(tmp_path, monkeypatch):
    from analysis import stages
    monkeypatch.setitem(stages.STAGE_TIMEOUT_S, "context", 0.3)
    j = _wait(_submit(tmp_path, [], context_fns=S.context_fns({"hand": S.sleeper(2)}))["job_id"],
              _done)
    assert j["status"] == "complete" and j["result_id"] is None
    assert j["stages"]["context:hand"]["status"] == "timeout"


def test_run_that_raises_is_a_failed_job(tmp_path):
    def no_layer(name, bbox):
        raise TimeoutError("overpass")
    j = _wait(_submit(tmp_path, [], load_layer=no_layer)["job_id"], _done)
    assert j["status"] == "failed" and j["result"] is None
    assert j["error"]["exception_class"] == "RuntimeError"      # run.py names the stage
    assert j["stages"]["road_layer"]["status"] == "failed"


def test_progress_never_changes_the_result():
    events = []
    with_p, _ = S.run(progress=events.append)
    without, _ = S.run()
    strip = lambda r: {k: v for k, v in r.items() if k not in ("created_utc", "runtime_s", "_maps")}
    assert strip(with_p)["outputs"] == strip(without)["outputs"]
    assert any(e.get("status") == "running" for e in events)


def test_job_ids_are_validated():
    assert not jobs.valid_id("../x") and not jobs.valid_id("j" + "0" * 23)
    assert jobs.valid_id("j" + "0" * 24)


# ── API ──

@pytest.fixture
def client(tmp_path, monkeypatch):
    import api
    monkeypatch.setattr(api, "RESULTS_ROOT", tmp_path)
    import analysis.run as R
    monkeypatch.setattr(R, "_default_deps", lambda: S.deps())
    from analysis.fractions import StandInFractions
    monkeypatch.setattr(StandInFractions, "fetch_composite", S.SynthProducer.fetch_composite)
    monkeypatch.setattr(StandInFractions, "unobserved_all", False, raising=False)
    from fastapi.testclient import TestClient
    return TestClient(api.app)


def _h():
    import api
    return {"X-API-Key": api.API_KEY}


REQ = {"west": BBOX[0], "south": BBOX[1], "east": BBOX[2], "north": BBOX[3],
       "start_date": START, "end_date": END, "aoi_label": "synth"}


def test_api_job_round_trip(client):
    assert client.post("/api/jobs", json=REQ).status_code == 401
    r = client.post("/api/jobs", json=REQ, headers=_h())
    assert r.status_code == 202, r.text
    jid = r.json()["job_id"]
    assert client.get(f"/api/jobs/{jid}").status_code == 401
    t0 = time.time()
    while time.time() - t0 < 60:
        j = client.get(f"/api/jobs/{jid}", headers=_h()).json()
        if j["status"] in ("complete", "failed"):
            break
        time.sleep(0.05)
    assert j["status"] == "complete" and j["stored"]
    again = client.post("/api/jobs", json=REQ, headers=_h()).json()
    assert again["status"] == "complete" and again["cached"] and again["result_id"] == j["result_id"]


def test_api_job_validation_matches_analyze(client):
    assert client.get("/api/jobs/nope", headers=_h()).status_code == 400
    assert client.get("/api/jobs/j" + "0" * 24, headers=_h()).status_code == 404
    big = {**REQ, "east": REQ["west"] + 1.0, "north": REQ["south"] + 1.0}
    for bad in (big, {**REQ, "aoi_label": "../x"}, {**REQ, "end_date": None},
                {**REQ, "demo": True}, {**REQ, "east": REQ["west"]}):
        assert client.post("/api/jobs", json=bad, headers=_h()).status_code == 400


def test_root_reports_the_aoi_limit(client):
    import api
    assert client.get("/", headers=_h()).json()["max_aoi_area_km2"] == api.MAX_AOI_AREA_KM2


# ── features: drawing data, absent is null ──

def test_features_are_null_where_not_measured_never_zero(client):
    rid = client.post("/api/analyze", json=REQ, headers=_h()).json()["result_id"]
    fc = client.get(f"/api/results/{rid}/features/grid").json()       # public
    assert fc["type"] == "FeatureCollection" and fc["features"]
    units = client.get(f"/api/results/{rid}/wards/grid?limit=1000").json()["units"]
    by_id = {u["unit_id"]: u for u in units}
    seen_null = False
    for ft in fc["features"]:
        p = ft["properties"]
        full = by_id[p["unit_id"]]["outputs"]["fractions"]
        assert ft["geometry"]["type"] in ("Polygon", "MultiPolygon")
        for f in fc["fractions"]:
            assert p[f] == full[f]["value"] and p[f"{f}_status"] == full[f]["status"]
            if p[f] is None:
                seen_null = True
                assert p[f"{f}_status"] in C.ABSENT
    assert seen_null       # impervious_total / paved / bare are not computed
