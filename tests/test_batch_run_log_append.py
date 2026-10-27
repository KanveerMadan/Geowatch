"""
Build item 59 — `batch_run_log.json` appends, it does not truncate.

`run_batch` started every invocation from an empty list and rewrote the file
after each city, so the 11-city history was clobbered by a later single-city
run. What is on disk today is one `nusantara` entry, which is that clobbering.

`run_pipeline` is replaced with a stub, so no imagery, GEE or Overpass call is
made. What is under test is the log file's lifecycle and nothing else.

Run from the repo root:  pytest tests/test_batch_run_log_append.py
"""

import json

import pytest


@pytest.fixture
def batch(monkeypatch, tmp_path):
    import run_all_cities

    def fake_run_pipeline(**kwargs):
        label = kwargs["aoi_label"]
        if label == "boom":
            raise RuntimeError("simulated integration failure")
        return {"status": "complete", "run_id": f"{label}_20260101_000000",
                "summary": {"total_segments": 1}}

    monkeypatch.setattr(run_all_cities, "run_pipeline", fake_run_pipeline)
    log_path = tmp_path / "pipeline_runs" / "batch_run_log.json"
    monkeypatch.setattr(run_all_cities, "LOG_PATH", str(log_path))
    return run_all_cities, log_path


BBOX = (0.0, 0.0, 0.01, 0.01)


def _read(path):
    return json.loads(path.read_text())


def test_second_invocation_keeps_the_first(batch):
    """The ledger case: an 11-city batch followed by a 1-city batch."""
    mod, log_path = batch
    eleven = {f"city{i}": BBOX for i in range(11)}
    mod.run_batch(eleven)
    mod.run_batch({"nusantara": BBOX})

    log = _read(log_path)
    assert len(log) == 12
    assert [e["city"] for e in log[:11]] == list(eleven)
    assert log[-1]["city"] == "nusantara"


def test_invocations_are_distinguishable(batch):
    mod, log_path = batch
    mod.run_batch({"a": BBOX, "b": BBOX})
    mod.run_batch({"c": BBOX})
    log = _read(log_path)
    ids = [e["batch_id"] for e in log]
    assert ids[0] == ids[1] != ids[2]


def test_legacy_file_without_batch_ids_is_preserved_verbatim(batch):
    """The real file on disk predates batch_id. It must survive untouched."""
    mod, log_path = batch
    legacy = [{"city": "nusantara", "status": "complete",
               "run_id": "nusantara_20260702_165811"}]
    log_path.parent.mkdir(parents=True)
    log_path.write_text(json.dumps(legacy))

    mod.run_batch({"dharavi": BBOX})
    log = _read(log_path)
    assert log[0] == legacy[0]
    assert log[1]["city"] == "dharavi"


def test_unreadable_existing_log_fails_loudly_and_is_not_overwritten(batch):
    """Appending to a file that cannot be parsed would mean replacing it,
    and replacing it is the bug. So the run refuses before any city runs."""
    mod, log_path = batch
    log_path.parent.mkdir(parents=True)
    log_path.write_text("{not json")
    with pytest.raises(ValueError):
        mod.run_batch({"dharavi": BBOX})
    assert log_path.read_text() == "{not json"


def test_log_is_written_after_each_city_including_failures(batch):
    """Crash safety stays as it was: a city's entry is on disk before the
    next city starts, and an exception is logged rather than lost."""
    mod, log_path = batch
    mod.run_batch({"ok": BBOX, "boom": BBOX})
    log = _read(log_path)
    assert [e["status"] for e in log] == ["complete", "exception"]
    assert log[1]["exception_class"] == "RuntimeError"


def test_summary_return_value_is_this_batch_only(batch):
    mod, _ = batch
    mod.run_batch({"a": BBOX, "b": BBOX})
    returned = mod.run_batch({"c": BBOX})
    assert [e["city"] for e in returned] == ["c"]
