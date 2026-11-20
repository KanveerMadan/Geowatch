"""The real detector, scheduler, immutable result store and public reads, with synthetic acquisitions."""
from datetime import date, timedelta

import numpy as np
import pytest

from analysis import change_history as history, store
from analysis.run import change_epochs
from tests import analysis_synth as synth


class Acquisitions:
    def __init__(self, layer, start, end, *, partial=False, empty=False):
        self.layer, self.start, self.end = layer, date.fromisoformat(start), date.fromisoformat(end)
        self.partial, self.empty = partial, empty

    def tiles(self):
        from vector.change_observations import _spatial_tiles
        cells = next(_spatial_tiles(self.layer))["cells"][:2]
        rows = []
        for days in range(0, (self.end - self.start).days, 7):
            day = self.start + timedelta(days=days)
            signal = 0.3 + 0.1 * np.cos(2 * np.pi * days / 365.2425)
            if day >= date(2026, 1, 15):
                signal -= 0.65
            if not self.empty:
                rows.append({"date": day.isoformat(), "source": "sentinel2", "track": "MSI:12",
                             "id": f"test/{day}", "lineage": "sentinel2", "coverage": np.array([1., 0.]),
                             "values": {"ndvi": np.array([signal, np.nan])}})
        yield {"cells": cells, "observations": rows,
               "diagnostics": [{"source": "sentinel2",
                                "status": "partial" if self.partial else "available" if rows else "no_acquisitions",
                                "errors": ["temporarily unavailable"] if self.partial else []}]}


def _provider(partial, empty):
    return lambda layer, start, end, **_: Acquisitions(layer, start, end, partial=partial, empty=empty)


def _run(tmp_path, **kwargs):
    return history.run_history(synth.synth_layer(), change_epochs(synth.WINDOW), archive_root=tmp_path,
                               open_provider=_provider(False, False), **kwargs)


def test_monitor_compare_and_storage_api(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import api
    from tests.test_analysis_api import _analyze
    run = lambda layer, epochs: history.run_history(layer, epochs, open_provider=_provider(False, False))
    monkeypatch.setattr(api, "RESULTS_ROOT", tmp_path)
    body = _analyze(tmp_path, [], run_change=run)
    rid, result = body["result_id"], body["result"]
    assert result["request"]["aoi_label"] == "synth"
    assert result["change_epochs"]["monitoring"] == ("2026-01-01", "2026-03-31")
    output = result["outputs"]["change"]["history"]
    assert body["stored"] and output["validation_status"] == "experimental"
    assert output["value"]["counts"]["change_detected"] == output["value"]["counts"]["insufficient_observation"] == 1
    assert "_change_archive" not in result
    client = TestClient(api.app)
    base = f"/api/results/{rid}/change"
    cells = client.get(base + "/features").json()["features"]
    assert len(cells) == 2 and {c["properties"]["state"] for c in cells} == {"change_detected", "insufficient_observation"}
    detail = client.get(base + "/cells/0").json()
    assert len(detail["events"]) and detail["period"] == ["2026-01-01", "2026-03-31"]
    assert detail["observations"][0]["support_id"] == cells[0]["properties"]["support_id"]
    assert client.get(base + "/cells/-1").status_code == 404
    query = {"before_start": "2025-02-01", "before_end": "2025-03-01",
             "after_start": "2026-02-01", "after_end": "2026-03-01", "signal": "ndvi"}
    comparison = client.get(base + "/compare", params=query).json()["features"]
    assert comparison[0]["properties"]["delta"] == pytest.approx(-0.65, abs=.015)
    assert comparison[1]["properties"]["delta"] is None
    assert client.get(base + "/compare", params={**query, "before_start": "bad"}).status_code == 400
    assert client.get(base + "/compare", params={**query, "signal": "misspelled"}).status_code == 400
    assert client.get(base + "/summary/grid/0").status_code == 200
    assert client.get(base + "/summary/grid/nonexistent").status_code == 404
    assert _analyze(tmp_path, [], run_change=run)["cached"]


def test_transient_source_failure_does_not_poison_canonical_cache(tmp_path):
    from tests.test_analysis_api import _analyze
    def analysis(partial):
        return lambda layer, epochs: history.run_history(layer, epochs, open_provider=_provider(partial, False))
    first = _analyze(tmp_path, [], run_change=analysis(True))
    second = _analyze(tmp_path, [], run_change=analysis(False))
    assert first["stored"] and second["stored"] and not second["cached"]
    assert first["result_id"] != second["result_id"]
    assert store.get(first["result_id"], tmp_path)["outputs"]["change"]["history"]["summary"]["source_status"][0]["status"] == "partial"


def test_zero_evidence_and_time_limit_clean_up(tmp_path):
    from analysis.run import _change_outputs
    layer, epochs = synth.synth_layer(), change_epochs(synth.WINDOW)
    run = history.run_history(layer, epochs, open_provider=_provider(False, True), archive_root=tmp_path)
    try:
        assert run["summary"]["counts"]["insufficient_observation"] == 2
        wrapper = _change_outputs(run, {"status": "ok"}, epochs, {}, dict.fromkeys(("code_commit","artifact_hash","version_id"), "test"))
        assert wrapper["history"]["status"] == "insufficient_observation" and wrapper["history"]["value"] is None
        assert history.cell_detail(f"{run['archive'].name}/history.sqlite", 1)["observations"] == []
    finally:
        run["archive"].cleanup()
    with pytest.raises(TimeoutError):
        _run(tmp_path, timeout_s=0)
    assert not list(tmp_path.iterdir())


def test_comparison_never_crosses_tracks_or_double_counts_one_day():
    catalogue = [{"source": "s", "track": t, "date": d} for t,d in
                 [("A","2020-01-01"), ("A","2020-01-01"), ("B","2020-03-01"), ("A","2020-03-02")]]
    samples = np.array([[1.,1.], [3.,1.], [5.,2.], [2.,np.nan]])
    a,b = history._comparison(catalogue, samples, (("2020-01-01","2020-02-01"),("2020-03-01","2020-04-01")), 2)
    assert a["state"] == "unchanged" and a["n_before"] == 1
    assert b["state"] == "insufficient_observation"
    assert b["n_before"] + b["n_after"] == 1


def test_comparison_keeps_land_cover_model_generations_separate():
    records = [{"source": "dynamic_world", "track": "MSI:4", "date": day,
                "scenes": [{"dynamicworld_algorithm_version": version}]}
               for day, version in (("2020-01-15", "1"), ("2020-03-15", "2"))]
    result, = history._comparison(records, np.array([[.1], [.9]]),
                                  (("2020-01-01", "2020-02-01"), ("2020-03-01", "2020-04-01")), 1)
    assert result["delta"] is None and result["state"] == "insufficient_observation"
