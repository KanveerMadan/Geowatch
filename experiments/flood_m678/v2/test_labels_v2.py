"""Step 2 synthetic checks: the nearest-to-crest merge (no union across phases), optical first."""
import importlib.util
import os

import numpy as np

spec = importlib.util.spec_from_file_location("v2labels", os.path.join(os.path.dirname(__file__), "labels.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)


def test_nearest_scene_wins_not_union():
    early = np.array([[1, 1], [0, -1]], np.int8)     # at the crest
    late = np.array([[0, 1], [1, 1]], np.int8)       # 60 h later: water elsewhere
    s, fam, idx, off = L.nearest_merge([late, early], [60.0, 0.0], [1, 1])
    assert s.tolist() == [[1, 1], [0, 1]]            # early wins where it observed; late fills only (1,1)
    assert idx.tolist() == [[1, 1], [1, 0]] and off[1, 1] == 60.0


def test_optical_before_radar_even_if_radar_is_closer():
    opt = np.array([[0, -3]], np.int8)
    rad = np.array([[1, 1]], np.int8)
    s, fam, idx, off = L.nearest_merge([rad, opt], [0.0, 30.0], [2, 1])
    assert s.tolist() == [[0, 1]] and fam.tolist() == [[1, 2]]


def test_undecided_cells_keep_permanent_then_ambiguous():
    a = np.array([[-2, -1, -3]], np.int8)
    b = np.array([[-3, -3, -1]], np.int8)
    s, *_ = L.nearest_merge([a, b], [0.0, 1.0], [1, 1])
    assert s.tolist() == [[-2, -3, -3]]


def test_offset_sign():
    from datetime import datetime, timezone
    lo = datetime(2020, 5, 1, 0, tzinfo=timezone.utc)
    hi = datetime(2020, 5, 1, 1, tzinfo=timezone.utc)
    assert L.offset_h("2020-05-01T00:30:00Z", lo, hi) == 0.0
    assert L.offset_h("2020-04-30T22:00:00Z", lo, hi) == -2.0
    assert L.offset_h("2020-05-02T01:00:00Z", lo, hi) == 24.0
