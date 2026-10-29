"""(b) Every block of a legacy 7-class pipeline result is labelled
validation_status "retired" -- on new runs, and on stored runs as served."""
import copy
import json
import os

import pytest

from configs.legacy_pipeline import RETIRED, legacy_blocks, mark_retired

FIXTURES = [os.path.join("tests", "fixtures", f) for f in sorted(os.listdir(os.path.join("tests", "fixtures")))
            if f.startswith("result_")] + ["dharavi_latest_result.json"]


def _load(p):
    with open(p) as fh:
        return json.load(fh)


def _synthetic_current_result():
    """The shape run_pipeline() emits today, with the labels item 26 gave it."""
    return {
        "run_id": "dharavi_20261028_000000", "status": "complete",
        "aoi": {"west": 1, "south": 1, "east": 2, "north": 2},
        "legacy_pipeline": {"retired": True, "validated": False, "notice": "x"},
        "landcover": {"categories": ["a"], "category_area_pct": {"a": 50.0},
                      "palette": {"a": "#fff"}, "model_provenance": {"loco_mean_miou": 0.313}},
        "applicability": {"pluvial": {"status": "applicable", "reason": None},
                          "urban_landcover_model": {"status": "in_distribution", "reason": None}},
        "susceptibility": {
            "pluvial": {"status": "experimental", "validation_status": "placeholder",
                        "inputs": {"impervious": {"source": "OB", "method": "m",
                                                  "validation_status": "placeholder"}},
                        "applicability": {"status": "applicable", "trust": "in_distribution"}},
            "fluvial": {"status": "experimental", "validation_status": "failed"},
        },
        "exposure": {"status": "available",
                     "by_evidence_layer": {"pluvial": {"status": "available"}}},
        "terrain_context": {"coastal_context": {"status": "available", "distance_km": 1.0}},
        "hydrological_surfaces": {"impervious_fraction_pct": 40.0},
        "segments": [{"segment_id": 0}],
    }


def _assert_all_retired(r):
    blocks = list(legacy_blocks(r))
    assert blocks
    for path, b in blocks:
        assert b.get("validation_status") == RETIRED, path


def test_every_block_of_a_current_result_is_retired():
    r = mark_retired(_synthetic_current_result())
    _assert_all_retired(r)
    paths = {p for p, _ in legacy_blocks(r)}
    for must in ("landcover", "hydrological_surfaces", "susceptibility.pluvial",
                 "susceptibility.fluvial", "susceptibility.pluvial.inputs.impervious",
                 "susceptibility.pluvial.applicability", "exposure",
                 "exposure.by_evidence_layer.pluvial", "terrain_context.coastal_context",
                 "applicability.pluvial", "legacy_pipeline"):
        assert must in paths, must


def test_retired_outranks_and_keeps_the_earlier_label():
    r = mark_retired(_synthetic_current_result())
    assert r["susceptibility"]["fluvial"]["validation_status_superseded"] == "failed"
    assert r["susceptibility"]["pluvial"]["validation_status_superseded"] == "placeholder"
    from analysis.contract import worst
    assert worst("failed", RETIRED) == RETIRED


def test_maps_of_blocks_and_plain_data_gain_no_phantom_member():
    r = mark_retired(_synthetic_current_result())
    assert set(r["susceptibility"]) == {"pluvial", "fluvial"}       # no "validation_status" hazard
    assert set(r["applicability"]) == {"pluvial", "urban_landcover_model"}
    assert set(r["landcover"]["category_area_pct"]) == {"a"}        # no phantom category
    assert r["segments"] == [{"segment_id": 0}]


@pytest.mark.parametrize("path", FIXTURES)
def test_stored_results_are_retired_too(path):
    r = mark_retired(_load(path))
    _assert_all_retired(r)


def test_run_pipeline_stamps_before_writing():
    src = open("pipeline.py").read()
    body = src[src.index("def run_pipeline("):src.index("def run_inundation_analysis(")]
    assert body.index("mark_retired(result)") < body.index("json.dump(result")
    assert "return mark_retired(result)" in body      # the no-tiles early return too


@pytest.fixture
def client(tmp_path, monkeypatch):
    import api
    run = tmp_path / "dharavi_20260101_000000"
    run.mkdir()
    (run / "result.json").write_text(json.dumps(_load("tests/fixtures/result_clean.json")))
    monkeypatch.setattr(api, "DATA_ROOT", tmp_path.resolve())
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "pipeline_runs").mkdir(parents=True)
    (tmp_path / "data" / "pipeline_runs" / "dharavi_20260101_000000").symlink_to(run)
    from fastapi.testclient import TestClient
    return TestClient(api.app)


def test_served_legacy_runs_are_retired(client):
    import api
    h = {"X-API-Key": api.API_KEY}
    r = client.get("/api/runs/dharavi_20260101_000000", headers=h)
    assert r.status_code == 200
    _assert_all_retired(r.json())
    assert r.json()["legacy_pipeline"]["retired"] is True
    rows = client.get("/api/runs", headers=h).json()["runs"]
    assert rows and all(row["validation_status"] == RETIRED for row in rows)
