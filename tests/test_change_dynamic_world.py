"""The optional land-cover scores retain their parent sensor, track, dates and masks."""
from datetime import datetime, timezone

import pytest

from analysis import change_cli
from tests.test_change_observations import layer
from vector import change_observations as obs


def test_score_bands_preserve_source_mask_and_metadata():
    class Image:
        def __init__(self, path):
            self.path = path

        def select(self, names, renamed):
            assert self.path == "GOOGLE/DYNAMICWORLD/V1/granule"
            assert "label" not in names and tuple(names) == obs.DYNAMIC_WORLD_BANDS
            assert list(renamed) == ["dw_" + k for k in names] and len(renamed) == 9
            return "source with native band masks"

    from types import SimpleNamespace
    out = obs._scene(SimpleNamespace(Image=Image), "dynamic_world", {"system:index": "granule"})
    assert out == "source with native band masks"
    day = datetime(2021, 4, 2, tzinfo=timezone.utc).timestamp() * 1000
    meta = {"system:index": "granule", "system:time_start": day, "SENSING_ORBIT_NUMBER": 21,
            "dynamicworld_algorithm_version": "model-1", "qa_algorithm_version": "qa-2"}
    rows = [meta, {**meta, "system:index": "another-tile"}, {**meta, "system:index": "missing-parent",
            "SENSING_ORBIT_NUMBER": None}, {**meta, "system:index": "failed-geometry", "GEOMETRIC_QUALITY": "FAILED"}]
    errors = []
    record, = obs._groups("dynamic_world", rows, "2021-04-02", "2021-04-03", errors=errors)
    assert errors and "1 Dynamic World granules" in errors[0]
    assert len(record["scenes"]) == 2 and record["context_only"]
    assert record["track"] == "MSI:21" and record["date"] == "2021-04-02"
    assert record["resolution_m"] == 10 and record["sample_spacing_m"] == 20
    assert record["lineage"] == "sentinel2" and record["license"] == "CC BY 4.0"
    assert record["scenes"][0]["qa_algorithm_version"] == "qa-2"


def test_dw_is_enabled_by_explicit_source_choice_only(tmp_path, monkeypatch):
    assert len(obs.open_history(layer(), "2021-01-01", "2021-01-02").sources) == 5
    assert "dynamic_world" not in obs.DEFAULT_SOURCES
    explicit = obs.open_history(layer(), "2021-01-01", "2021-01-02", sources=["dynamic_world"])
    assert explicit.sources == ("dynamic_world",)
    class FetchIntercepted(Exception):
        pass
    captured = []
    def intercept(*args, **kwargs):
        captured.append(kwargs["sources"])
        raise FetchIntercepted
    monkeypatch.setattr("analysis.change_history.run_history", intercept)
    args = ["run", "--bbox", "72.9", "19.01", "72.901", "19.011", "--start", "2021-01-01",
            "--end", "2021-05-01", "--out", str(tmp_path / "test")]
    for flags in ([], ["--sources", "sentinel2", "dynamic_world"]):
        with pytest.raises(FetchIntercepted):
            change_cli.main(args + flags)
    assert captured == [obs.DEFAULT_SOURCES, ("sentinel2", "dynamic_world")]
