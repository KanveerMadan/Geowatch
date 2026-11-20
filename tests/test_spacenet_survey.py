"""SpaceNet coverage comes from the monthly mask and the surveyed image extent."""
import json

import numpy as np
import pytest
import rasterio
from rasterio.enums import ColorInterp
from rasterio.transform import from_origin
from shapely.geometry import box, mapping

from analysis.change_surveys import SurveyPairs
from experiments.change_history.spacenet_survey import (
    _reproject, epoch_features, month_interval,
)


def _epoch(root, month, alpha, buildings, unusable):
    path = root / f"{month}.tif"
    with rasterio.open(path, "w", driver="GTiff", width=2, height=2, count=4, dtype="uint8",
                       crs="EPSG:3857", transform=from_origin(0, 20, 10, 10)) as image:
        image.write(np.zeros((4, 2, 2), dtype="uint8"))
        image.colorinterp = (ColorInterp.red, ColorInterp.green, ColorInterp.blue, ColorInterp.alpha)
        image.write(np.array(alpha, dtype="uint8"), 4)
    files = {"image": path}
    for name, polys in (("buildings", buildings), ("unusable", unusable)):
        files[name] = root / f"{month}_{name}.json"
        files[name].write_text(json.dumps({
            "type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:3857"}},
            "features": [{"type": "Feature", "properties": {}, "geometry": mapping(g)} for g in polys],
        }))
    return epoch_features(files)


def test_months_kept_as_intervals_and_losses_exclude_missing_data(tmp_path):
    clear = [[255, 255], [255, 255]]
    first, bounds = _epoch(tmp_path, "2018_01", clear, [box(0, 0, 20, 10)], [])
    # Only the left column is clear, and its lower pixel is flagged by the UDM.
    last, _ = _epoch(tmp_path, "2020_01", [[255, 0], [255, 0]], [box(0, 10, 10, 20)], [box(0, 0, 10, 10)])
    (tmp_path / "before.json").write_text(json.dumps(first))
    (tmp_path / "after.json").write_text(json.dumps(last))
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps([{"name": "buildings", "source": "fixture", "license": "test",
                                 "before": {"interval": month_interval("2018_01"), "file": "before.json"},
                                 "after": {"interval": month_interval("2020_01"), "file": "after.json"}}]))
    pair = SurveyPairs(path)
    table = pair.measure(mapping(bounds), "EPSG:3857", "2018-01-01", "2020-02-01")["buildings"]
    assert table["joint_area_m2"] == pytest.approx(100)
    assert table["gain_m2"] == pytest.approx(100)
    assert table["loss_m2"] == pytest.approx(0)
    assert pair.measure(mapping(bounds), "EPSG:3857", "2018-01-01", "2020-01-15") == {}
    unseen = _reproject(box(12, 12, 18, 18), "EPSG:3857", "EPSG:4326")
    assert pair.measure(mapping(unseen), "EPSG:3857", "2018-01-01", "2020-02-01") == {}


def test_fully_masked_epoch_is_unknown(tmp_path):
    fc, _ = _epoch(tmp_path, "masked", [[0, 0], [0, 0]], [], [])
    assert fc is None
