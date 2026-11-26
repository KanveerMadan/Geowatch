"""Quality, identity, temporal leakage and cache regressions independent of EE."""
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest
from pyproj import CRS
from shapely.geometry import box

from vector import change_observations as obs


def layer(polygon=None):
    return SimpleNamespace(crs=CRS.from_epsg(32643), bbox=(72, 18, 72.03, 18.03),
                           aoi=polygon if polygon is not None else box(300000, 2100000, 300200, 2100100))


def test_stable_support_and_clipped_cells():
    first = next(obs._spatial_tiles(layer()))["cells"]
    subset = next(obs._spatial_tiles(layer(box(300070, 2100000, 300200, 2100100))))["cells"]
    assert [c["cell_id"] for c in first] == [c["cell_id"] for c in subset]
    assert first[1]["support_id"] == subset[1]["support_id"]
    assert first[0]["support_id"] != subset[0]["support_id"]
    assert subset[0]["area_m2"] == 3000
    assert first[0]["geometry"]["type"] == "Polygon"


def test_spatial_support_checks_each_acquisition_independently():
    cube = np.array([[[0.4, 0.2, 0.0], [0.2, 0.1, 0.0], [0.96, np.nan, 1]]], dtype=np.float32)
    got = obs._sanitise(cube)
    assert np.isnan(got[0, :2, :2]).all()
    assert (got[0, :2, 2] == 0).all()
    assert got[0, -1].tolist() == pytest.approx([0.96, 0, 1])


def test_no_future_buildings_and_independent_radar_geometry():
    t = datetime(2020, 6, 1, tzinfo=timezone.utc).timestamp()
    row = {"system:index": "a", "system:time_start": t * 1000, "inference_time_epoch_s": t,
           "imagery_start_time_epoch_s": t - 300000, "imagery_end_time_epoch_s": t + 86400}
    assert not obs._groups("open_buildings", [row], "2020-01-01", "2020-06-02")
    item, = obs._groups("open_buildings", [row], "2020-01-01", "2020-06-03")
    assert (item["date"], item["inference_date"],item["lineage"]) == ("2020-06-02","2020-06-01","sentinel2")
    base = {"system:index": "1", "system:time_start": t * 1000, "relativeOrbitNumber_start": 42,
            "platform_number": "A", "orbitProperties_pass": "ASCENDING"}
    rows = [base, dict(base, **{"system:index": "2"}), dict(base, **{"system:index": "3", "platform_number": "B"}),
            dict(base, **{"system:index": "4", "relativeOrbitNumber_start": 9})]
    groups = obs._groups("sentinel1", rows, "2020-06-01", "2020-06-10")
    assert len(groups) == 3
    assert sorted(len(record["scenes"]) for record in groups) == [1, 1, 2]


def test_cache_depends_on_scene_versions_support_and_processing(monkeypatch, tmp_path):
    aoi = layer()
    tile = next(obs._spatial_tiles(aoi))
    records = [{"date": "2020-01-01", "source": "sentinel1", "scenes": [{"version": 1}]}]
    calls = []
    def fake(ee, layer, tile, batch):
        calls.append(True)
        return np.ones((len(batch), 3, len(tile["indices"])),dtype=np.float32)
    monkeypatch.setattr(obs, "_block_pixels", fake)
    for _ in range(2):
        obs._cached_block(None, aoi, tile, records, tmp_path)
    assert len(calls) == 1
    records[0]["scenes"][0]["version"] = 2
    obs._cached_block(None, aoi, tile, records, tmp_path)
    assert len(calls) == 2
    path = next(tmp_path.rglob("*.npz"))
    path.write_bytes(b"interrupted")
    for version in (1, 2):
        records[0]["scenes"][0]["version"] = version
        obs._cached_block(None, aoi, tile, records, tmp_path)
    assert len(calls) == 3


def test_date_windows_sources_and_cancellation():
    assert list(obs._calendar_years("2020-12-30","2021-01-10")) == [
        ("2020-12-30","2021-01-01"),("2021-01-01","2021-01-10")]
    with pytest.raises(ValueError):
        obs.open_history(layer(),"2020-12-30","2020-12-30")
    with pytest.raises(ValueError):
        obs.open_history(layer(),"2020-12-30","2021-01-10",sources=["other"])
    hist = obs.open_history(layer(),"2020-12-30","2021-01-10",cancelled=lambda:True)
    with pytest.raises(TimeoutError):
        hist._check()


def test_cached_inventory_never_mistakes_an_outage_for_no_acquisitions(tmp_path, monkeypatch):
    clock = [20_000.0]
    monkeypatch.setattr(obs.time, "time", lambda: clock[0])
    monkeypatch.setattr(obs, "_catalog", lambda *a: [{"system:index": "A"}])
    args = ("landsat8", (0, 0, 1, 1), "2020-01-01", "2021-01-01", tmp_path)
    expected = ([{"system:index": "A"}], None)
    assert obs._cached_catalog(*args, lambda: None) == expected
    def outage():
        raise OSError("offline")
    assert obs._cached_catalog(*args, outage) == expected
    clock[0] += 86401
    rows, warning = obs._cached_catalog(*args, outage)
    assert rows == expected[0] and "stale" in warning
