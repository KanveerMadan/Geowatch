"""
Build item 20, the UI half: the stored coverage report and the route that
serves it. The UI renders this report and computes nothing, so everything it
needs to decide how loudly to speak must already be in it.

Synthetic layers and a fake input builder, so nothing touches the network.
The UI half is tested in tests/test_coverage_ui.mjs.

Run from the repo root:  pytest tests/test_vector_coverage_report.py
"""
import json
import time

import pytest
from fastapi.testclient import TestClient

from vector import coverage, coverage_report, roads, sources
from vector.aois import BASELINE_AOIS, MORPHOLOGY_AOIS
from vector_synth import BBOX, _fix_ns, _highways, _layer, _way

REF = {"a": 0.19, "b": 0.39, "c": 1.29, "d": 2.11, "e": 2.78, "f": 8.35}


def _footways(n):
    return [_fix_ns(_way(100 + k, "footway", 0, 0, 0, [1000 + 3 * k, 1001 + 3 * k, 1002 + 3 * k]))
            for k in range(n)]


# ── The per-block warning field ──

@pytest.mark.parametrize("ways,regime,warn", [
    ([], "very_low", True),
    (_footways(9), "adequate", False),
], ids=["very_low", "adequate"])
def test_block_carries_the_low_coverage_warning(ways, regime, warn):
    s = coverage.score_layer(_layer(ways), REF)
    assert s["coverage_regime_flag"] == regime
    assert s["low_coverage_warning"] is warn
    assert s["scored"] is True


def test_not_measurable_block_warns():
    layer = roads.build_road_layer("t", BBOX, highways=_highways(_footways(9),
                                   unavailable=["narrow_pedestrian"]),
                                   footprints_4326=[], footprint_source="none")
    s = coverage.score_layer(layer, REF)
    assert s["coverage_regime_flag"] == "not_measurable"
    assert s["low_coverage_warning"] is True


def test_warning_regimes_are_the_suppression_regimes():
    """One list: the regimes that suppress topology are the ones that warn."""
    assert coverage.LOW_COVERAGE_REGIMES == {"low", "very_low", "not_measurable"}
    assert coverage.SUPPRESS_TOPOLOGY_IN == coverage.LOW_COVERAGE_REGIMES
    assert coverage.LOW_COVERAGE_REGIMES <= set(coverage.REGIMES)


def test_unscorable_block_has_no_number():
    b = coverage.not_measurable_block("EEException: boom")
    assert b["coverage_regime_flag"] == "not_measurable"
    assert b["low_coverage_warning"] is True and b["scored"] is False
    assert b["validation_status"] == "experimental"
    assert not any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in b.values())


# ── The report ──

def test_report_covers_every_vector_aoi():
    aois = coverage_report.report_aois()
    assert set(aois) == set(BASELINE_AOIS) | set(MORPHOLOGY_AOIS)
    assert set(aois) == set(coverage.REFERENCE_NARROW_KM_PER_KM2)
    assert aois["lagos"]["morphology"] == "dense_informal"


def _fake_inputs(name, bbox):
    if name == "broken":
        raise RuntimeError("Earth Engine down")
    n = {"thin": 0, "dense": 9}[name]
    return _layer(_footways(n)), None


def test_report_keeps_a_failed_aoi_as_not_measurable():
    aois = {"thin": {"bbox": BBOX}, "dense": {"bbox": BBOX}, "broken": {"bbox": BBOX}}
    r = coverage_report.build_report(aois, inputs=_fake_inputs)
    by = {row["aoi"]: row["coverage"] for row in r["aois"]}
    assert [row["aoi"] for row in r["aois"]] == ["thin", "dense", "broken"]
    assert by["thin"]["coverage_regime_flag"] == "very_low"
    assert by["dense"]["low_coverage_warning"] is False
    assert by["broken"]["coverage_regime_flag"] == "not_measurable"
    assert "RuntimeError: Earth Engine down" in by["broken"]["regime_reasons"][0]
    assert r["validation_status"] == "experimental"
    assert all(row["coverage"]["validation_status"] != "validated" for row in r["aois"])
    json.dumps(r, allow_nan=False)


def test_report_round_trips_and_newest_wins(tmp_path):
    import datetime as dt
    aois = {"dense": {"bbox": BBOX}}
    for day in (27, 28):
        r = coverage_report.build_report(
            aois, inputs=_fake_inputs, now=dt.datetime(2026, 10, day, tzinfo=dt.timezone.utc))
        coverage_report.write_report(r, str(tmp_path))
    path, loaded = coverage_report.latest_report(str(tmp_path))
    assert path.endswith("result_2026-10-28.json")
    assert loaded["generated_at"].startswith("2026-10-28")
    assert coverage_report.latest_report(str(tmp_path / "none")) is None


# ── The route ──

@pytest.fixture
def client():
    import api
    return TestClient(api.app, headers={api.API_KEY_HEADER_NAME: api.API_KEY})


def test_route_serves_the_stored_report_verbatim(client, tmp_path, monkeypatch):
    r = coverage_report.build_report({"thin": {"bbox": BBOX}}, inputs=_fake_inputs)
    coverage_report.write_report(r, str(tmp_path))
    monkeypatch.setattr(coverage_report, "REPORT_DIR", str(tmp_path))
    res = client.get("/api/vector/coverage")
    assert res.status_code == 200
    body = res.json()
    assert body.pop("source_file").endswith(".json")
    assert body == json.loads(json.dumps(r))


def test_route_404s_when_no_report(client, tmp_path, monkeypatch):
    monkeypatch.setattr(coverage_report, "REPORT_DIR", str(tmp_path))
    res = client.get("/api/vector/coverage")
    assert res.status_code == 404
    assert "vector.coverage_report" in res.json()["detail"]


# ── Earth Engine timeout on the footprint count ──

def test_open_buildings_count_has_a_timeout(monkeypatch):
    """count_open_buildings called getInfo() with no deadline; a stalled
    count would hang the report build. It now goes through ee_timeout."""
    import ee
    import ee_timeout
    from unittest.mock import MagicMock

    fc = MagicMock()
    fc.filterBounds.return_value.size.return_value.getInfo.side_effect = \
        lambda: (time.sleep(1.0), 7)[1]
    monkeypatch.setattr("ingestion.gee_client.initialize_gee", lambda: None)
    monkeypatch.setattr(ee, "FeatureCollection", MagicMock(return_value=fc))
    monkeypatch.setattr(ee.Geometry, "Rectangle", MagicMock())
    monkeypatch.setattr(sources, "OPEN_BUILDINGS_COUNT_TIMEOUT_S", 0.1, raising=False)
    t0 = time.time()
    with pytest.raises(ee_timeout.EETimeout):
        sources.count_open_buildings(BBOX)
    assert time.time() - t0 < 0.9
