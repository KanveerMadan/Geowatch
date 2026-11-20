"""Change-only CLI uses the production history and grid with offline observations."""
import json

import pytest

from analysis import change_cli as cli
from tests.test_change_history_api import Acquisitions


def _run(path, *extra):
    return ["run", "--bbox", "72.901", "19.013", "72.905", "19.017",
            "--start", "2026-01-01", "--end", "2026-03-31",
            "--sources", "sentinel2", "--out", str(path), *extra]


def _provider(monkeypatch, calls, partial=False):
    def open_source(layer, start, end, **kwargs):
        calls.append((layer, start, end, kwargs))
        return Acquisitions(layer, start, end, partial=partial)
    monkeypatch.setattr("vector.change_observations.open_history", open_source)
    def unexpected(*args, **kwargs):
        pytest.fail("standalone change invoked the full pipeline or road loader")
    monkeypatch.setattr("analysis.run.run_analysis", unexpected)
    monkeypatch.setattr("vector.roads.load_road_layer", unexpected)


def test_run_and_export_usable_for_review(tmp_path, monkeypatch, capsys):
    from experiments.change_history.validate import read_cases
    out = tmp_path / "result"
    calls = []
    _provider(monkeypatch, calls)
    cli.main(_run(out, "--history-years", "4", "--cache", str(tmp_path / "cache")))
    assert sorted(p.name for p in out.iterdir()) == ["cells.geojson", "history.sqlite", "summary.json"]
    assert len(calls) == 1
    layer, start, end, options = calls[0]
    assert start == "2022-01-01" and end == "2026-03-31"
    assert options["sources"] == ("sentinel2",) and options["cache_dir"] == tmp_path / "cache"
    summary = json.loads((out / "summary.json").read_text())
    assert summary["bbox"] == list(layer.bbox) and summary["crs"] == layer.crs.to_string()
    assert summary["operating_parameters"]["history_years"] == 4
    assert list(summary["sources"]) == ["sentinel2"] and summary["sources"]["sentinel2"]["license"]
    fc = json.loads((out / "cells.geojson").read_text())
    assert len(fc["features"]) == 2
    dest = tmp_path / "cell-0.json"
    cli.main(["cell", str(out), "0", "--out", str(dest)])
    saved = dest.read_bytes()
    detail = json.loads(saved)
    assert detail["observations"] and detail["period"] == summary["period"]
    case = {"id": "fixture", "region": "r", "block": "b", "split": "development",
            "cell_id": fc["features"][0]["properties"]["cell_id"], "period": summary["period"],
            "detail": dest.name, "reference": "test", "license": "test fixture",
            "target": "greenness_loss", "state": "unobserved", "independent": False}
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(json.dumps(case))
    assert read_cases(manifest)[0][1]["cell_id"] == detail["cell_id"]
    capsys.readouterr()
    cli.main(["cell", str(out), "0", "--start", "2025-01-01", "--end", "2025-02-01",
              "--mode", "retrospective", "--as-of", "2025-03-01"])
    replay = json.loads(capsys.readouterr().out)
    assert replay["period"] == ["2025-01-01", "2025-02-01"] and replay["as_of"] == "2025-03-01"
    assert all(r["date"] <= replay["as_of"] for r in replay["observations"])
    with pytest.raises(SystemExit):
        cli.main(["cell", str(out), "0", "--out", str(dest)])
    assert dest.read_bytes() == saved
    with pytest.raises(SystemExit):
        cli.main(_run(out))
    assert len(calls) == 1


def test_retryable_failure_and_exclusive_publish(tmp_path, monkeypatch):
    out = tmp_path / "result"
    _provider(monkeypatch, [], partial=True)
    with pytest.raises(SystemExit):
        cli.main(_run(out))
    assert list(tmp_path.iterdir()) == []
    _provider(monkeypatch, [])
    cli.main(_run(out))
    assert (out / "summary.json").is_file()
    other = tmp_path / "other"
    other.mkdir()
    # Even an empty directory created by another writer is preserved.
    with pytest.raises(FileExistsError):
        cli._publish_directory(out, other)
    assert (out / "history.sqlite").is_file() and not list(other.iterdir())


def test_bad_bounds_fail_before_network_or_writes(tmp_path, monkeypatch):
    calls = []
    _provider(monkeypatch, calls)
    args = _run(tmp_path / "archive")
    args[2:6] = ["-1", "0", "1", "10"]
    with pytest.raises(SystemExit):
        cli.main(args)
    assert not calls and not list(tmp_path.iterdir())
