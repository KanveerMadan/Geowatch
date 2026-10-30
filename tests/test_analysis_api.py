"""Phase 2, task 3: permanent result IDs, the never-recompute cache, public
read-only result endpoints, protected analysis-triggering endpoints."""
import json

import pytest

from analysis import contract as C
from analysis import store
from tests import analysis_synth as S

BBOX = S.BBOX


def _counting_runner(calls, **dep_overrides):
    from analysis.run import run_analysis

    def runner(bbox, window, **kw):
        calls.append(window)
        return run_analysis(bbox, window, deps=S.deps(**dep_overrides), **kw)
    return runner


def _analyze(tmp_path, calls, name="synth", producer=None, commit=S.COMMIT, **dep):
    return store.analyze(BBOX, "2026-01-01", "2026-03-31", name=name,
                         producer=producer or S.SynthProducer(), root=str(tmp_path),
                         runner=_counting_runner(calls, **dep), commit=commit)


# ── store ──

def test_same_aoi_dates_version_never_recompute(tmp_path):
    calls = []
    a = _analyze(tmp_path, calls)
    b = _analyze(tmp_path, calls, name="another_label")       # label is not in the key
    assert len(calls) == 1
    assert a["stored"] and not a["cached"] and b["cached"]
    assert a["result_id"] == b["result_id"] and store.valid_id(a["result_id"])
    assert b["result"]["result_id"] == a["result_id"]
    C.check_result(b["result"])


def test_new_version_is_a_new_id_and_the_old_result_stays(tmp_path):
    calls = []
    a = _analyze(tmp_path, calls)
    other = {"commit": "1" * 40, "dirty": False, "diff_sha256": None}
    b = _analyze(tmp_path, calls, commit=other)
    assert len(calls) == 2 and a["result_id"] != b["result_id"]
    assert store.get(a["result_id"], str(tmp_path)) is not None


def test_dates_are_in_the_key():
    v = "v" * 16
    w1 = {"start": "2026-01-01", "end": "2026-03-31"}
    w2 = {"start": "2026-01-02", "end": "2026-03-31"}
    assert store.result_id(BBOX, w1, None, v) != store.result_id(BBOX, w2, None, v)
    assert store.result_id(BBOX, w1, None, v) != store.result_id(BBOX, w1, "wards", v)


def test_stored_results_are_immutable(tmp_path):
    a = _analyze(tmp_path, [])
    with pytest.raises(FileExistsError):
        store.put(a["result_id"], {}, {}, str(tmp_path))


def test_incomplete_run_is_not_stored(tmp_path):
    def broken():
        raise ConnectionError("down")
    calls = []
    a = _analyze(tmp_path, calls, context_fns=S.context_fns({"hand": broken}))
    assert a["stored"] is False and a["result_id"] is None
    assert a["not_stored_because"] == {"context:hand": "failed"}
    assert store.list_results(str(tmp_path)) == []
    _analyze(tmp_path, calls, context_fns=S.context_fns({"hand": broken}))
    assert len(calls) == 2                                      # retried, not served


def test_invalid_ids_never_reach_the_filesystem(tmp_path):
    for bad in ("../x", "r" + "0" * 23, "R" + "0" * 24, "r" + "0" * 24 + "\n"):
        assert not store.valid_id(bad)
        with pytest.raises(ValueError):
            store.get(bad, str(tmp_path))


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


def _key():
    import api
    return api.API_KEY


H = {"X-API-Key": _key()}
REQ = {"west": BBOX[0], "south": BBOX[1], "east": BBOX[2], "north": BBOX[3],
       "start_date": "2026-01-01", "end_date": "2026-03-31", "aoi_label": "synth"}


def test_analyze_is_protected_and_results_are_public(client):
    assert client.post("/api/analyze", json=REQ).status_code == 401
    r = client.post("/api/analyze", json=REQ, headers=H)
    assert r.status_code == 200, r.text
    body = r.json()
    rid = body["result_id"]
    assert body["stored"] and body["url"] == f"/api/results/{rid}"
    assert client.post("/api/analyze", json=REQ, headers=H).json()["cached"] is True

    # public, no key
    lst = client.get("/api/results").json()["results"]
    assert [x["result_id"] for x in lst] == [rid]
    res = client.get(f"/api/results/{rid}")
    assert res.status_code == 200
    C.check_result(res.json())
    assert res.json()["outputs"]["susceptibility"]["pluvial"]["validation_status"] == "placeholder"

    types = client.get(f"/api/results/{rid}/wards").json()["unit_types"]
    assert {"grid", "footprint", "path"} <= set(types)
    page = client.get(f"/api/results/{rid}/wards/grid?offset=0&limit=5").json()
    assert len(page["units"]) == 5 and page["n_units"] == types["grid"]["n_units"]
    for u in page["units"]:
        C.check_result(u)
    one = client.get(f"/api/results/{rid}/wards/grid/{page['units'][0]['unit_id']}")
    assert one.status_code == 200 and one.json()["unit_id"] == page["units"][0]["unit_id"]


def test_public_exemption_is_narrow(client):
    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/demo").status_code == 401
    assert client.get("/runs/anything/result.json").status_code == 401
    assert client.get("/api/resultsX").status_code == 401
    assert client.post("/api/results").status_code == 401
    assert client.post("/api/legacy/analyze", json=REQ).status_code == 401
    assert client.get("/api/results/../runs").status_code in (400, 401, 404)


def test_is_public_read():
    import api
    assert api.is_public_read("GET", "/api/results")
    assert api.is_public_read("GET", "/api/results/r" + "0" * 24 + "/wards/ward:x/12")
    for m, p in (("POST", "/api/results"), ("DELETE", "/api/results/x"),
                 ("GET", "/api/results/../runs"), ("GET", "/api/runs"),
                 ("GET", "/api/results/a.b"), ("GET", "/runs/x")):
        assert not api.is_public_read(m, p), (m, p)


def test_bad_ids_and_paging(client):
    assert client.get("/api/results/nope").status_code == 400
    assert client.get("/api/results/r" + "0" * 24).status_code == 404
    rid = client.post("/api/analyze", json=REQ, headers=H).json()["result_id"]
    assert client.get(f"/api/results/{rid}/wards/grid?limit=0").status_code == 400
    assert client.get(f"/api/results/{rid}/wards/grid?limit=5000").status_code == 400
    assert client.get(f"/api/results/{rid}/wards/nosuchtype").status_code == 404
    assert client.get(f"/api/results/{rid}/wards/grid/99999").status_code == 404


def test_analyze_request_validation(client):
    assert client.post("/api/analyze", json={**REQ, "demo": True}, headers=H).status_code == 400
    assert client.post("/api/analyze", json={**REQ, "end_date": None}, headers=H).status_code == 400
    assert client.post("/api/analyze", json={**REQ, "aoi_label": "../x"}, headers=H).status_code == 400
    assert client.post("/api/analyze", json={**REQ, "boundary_layer_id": "../x"},
                       headers=H).status_code == 400
    assert client.post("/api/analyze", json={**REQ, "boundary_layer_id": "nope"},
                       headers=H).status_code == 400


def test_legacy_route_is_marked_and_reaches_run_pipeline():
    src = open("api.py").read()
    body = src[src.index('@app.post("/api/legacy/analyze")'):src.index('@app.post("/api/analyze_inundation")')]
    assert "from pipeline import run_pipeline" in body and "LEGACY" in body
    new = src[src.index('@app.post("/api/analyze")'):src.index('@app.post("/api/legacy/analyze")')]
    assert "run_pipeline" not in new and "pipeline import" not in new
