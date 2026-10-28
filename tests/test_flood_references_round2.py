"""
Item 26 Phase 1a, task 2: the round-2 flood references
(experiments/flood_validation/references.py), pure parts. Rules
pre-registered in PREREGISTRATION_ROUND2.md §References.

All fail on the old code: references.py did not exist.
"""
import datetime

import numpy as np
import pytest
from rasterio.transform import from_origin
from shapely.geometry import box

from experiments.flood_validation import references as R

T = from_origin(0, 90, 30, 30)        # 3 x 3 grid of 30 m cells, origin (0, 90)


def _ms(day: str, hour: int = 6):
    d = datetime.datetime.fromisoformat(day).replace(hour=hour, tzinfo=datetime.timezone.utc)
    return int(d.timestamp() * 1000)


def test_coverage_is_area_share_and_half_is_flooded():
    # covers the whole of cell (0,0) and exactly half of cell (0,1)
    cov = R.coverage([box(0, 60, 45, 90)], T, (3, 3))
    assert cov[0, 0] == pytest.approx(1.0)
    assert cov[0, 1] == pytest.approx(0.5)
    assert cov[1, 0] == 0.0
    assert (cov >= R.COVER_MIN)[0, 1]          # >= half counts as flooded


def test_flood_trace_counts_as_flooded_and_other_notations_do_not():
    assert R.EMS_FLOODED_NOTATIONS == ("Flooded area", "Flood trace")


def test_ems_polygons_keeps_only_flooded_notations(tmp_path, monkeypatch):
    import json
    fc = {"type": "FeatureCollection", "features": [
        {"properties": {"notation": "Flooded area"}, "geometry": box(0, 0, 1, 1).__geo_interface__},
        {"properties": {"notation": "Flood trace"}, "geometry": box(2, 0, 3, 1).__geo_interface__},
        {"properties": {"notation": "Not Applicable"}, "geometry": box(4, 0, 5, 1).__geo_interface__},
    ]}
    monkeypatch.setattr(R, "CACHE", str(tmp_path))
    path = tmp_path / "ems" / "layers" / "x.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(fc))
    polys, counts, sha = R.ems_polygons({"layer_url": "https://example.invalid/x.json"})
    assert len(polys) == 2
    assert counts == {"Flooded area": 1, "Flood trace": 1, "Not Applicable": 1}
    assert len(sha) == 64


def test_pick_event_date_takes_the_earliest_day_in_the_window():
    ts = [_ms("2019-03-13"), _ms("2019-03-19"), _ms("2019-03-20"), _ms("2019-03-25")]
    assert R.pick_event_date(ts, "2019-03-15", 13) == datetime.date(2019, 3, 19)
    assert R.pick_event_date(ts, "2019-03-15", 3) is None          # round 1's window: empty
    # event day + 12 is the last day of a 13-day window; + 13 is outside it
    assert R.pick_event_date([_ms("2019-03-27")], "2019-03-15", 13) == datetime.date(2019, 3, 27)
    assert R.pick_event_date([_ms("2019-03-28")], "2019-03-15", 13) is None


def test_blocks_aggregate_gfd_cells_to_240_m():
    score = np.arange(16, dtype=float).reshape(4, 4)
    flooded = np.zeros((4, 4), bool)
    flooded[:2, :2] = True                       # one 2x2 block fully flooded
    flooded[2, 2] = True                         # 1 of 4: below half
    valid = np.ones((4, 4), bool)
    valid[0, 2:] = valid[1, 2] = False           # 3 of 4 invalid -> block invalid
    s, f, v = R.blocks(score, flooded, valid, 2)
    assert f.tolist() == [[True, False], [False, False]]
    assert v.tolist() == [[True, False], [True, True]]
    assert s[0, 0] == pytest.approx(np.mean([0, 1, 4, 5]))


def test_cells_drops_invalid_and_unscored():
    score = np.array([[0.1, np.nan], [0.5, 0.9]])
    s, f = R.cells(score, np.array([[1, 1], [0, 1]], bool), np.array([[1, 1], [0, 1]], bool))
    assert s.tolist() == [0.1, 0.9] and f.tolist() == [True, True]


def test_square_bbox_is_4_km():
    w, s, e, n = R.square_bbox(0.0, 0.0)
    assert (n - s) * 111_320 == pytest.approx(4000, rel=1e-3)
    assert (e - w) * 111_320 == pytest.approx(4000, rel=1e-3)
    w, s, e, n = R.square_bbox(60.0, 10.0)
    assert (e - w) * 111_320 * 0.5 == pytest.approx(4000, rel=1e-3)


def test_permanent_water_is_never_valid():
    occ = np.array([[0.0, 79.9, 80.0, np.nan]])
    assert R.not_permanent(occ).tolist() == [[True, True, False, False]]
