"""
Item 26 follow-ups: the round-3 harness's box rule and registry, pure.
Pre-registered in experiments/flood_validation/PREREGISTRATION_ROUND3.md.

Fail on the old code: harness_round3.py did not exist.
"""
import numpy as np
import pytest
from shapely.geometry import Point, box

from experiments.flood_validation import harness_round2 as H2
from experiments.flood_validation import harness_round3 as H3
from experiments.flood_validation import references as R


def test_centre_is_the_flood_centroid_when_it_lies_on_the_flood():
    lat, lon = H3.flood_extent_centre([box(10.0, 20.0, 10.02, 20.02)], box(9, 19, 11, 21))
    assert lat == pytest.approx(20.01, abs=1e-4) and lon == pytest.approx(10.01, abs=1e-4)


def test_centre_snaps_to_the_nearest_flooded_point_when_the_centroid_is_off_flood():
    ring = box(10.0, 20.0, 10.04, 20.04).difference(box(10.005, 20.005, 10.035, 20.035))
    lat, lon = H3.flood_extent_centre([ring], box(9, 19, 11, 21))
    assert ring.buffer(1e-6).contains(Point(lon, lat))
    two = [box(10.0, 20.0, 10.01, 20.01), box(10.05, 20.0, 10.06, 20.01)]   # patches apart
    lat, lon = H3.flood_extent_centre(two, box(9, 19, 11, 21))
    assert any(p.buffer(1e-6).contains(Point(lon, lat)) for p in two)


def test_flood_outside_the_product_extent_does_not_move_the_centre():
    inside, outside = box(10.0, 20.0, 10.01, 20.01), box(10.5, 20.5, 10.6, 20.6)
    lat, lon = H3.flood_extent_centre([inside, outside], box(9.9, 19.9, 10.1, 20.1))
    assert inside.buffer(1e-6).contains(Point(lon, lat))
    assert H3.flood_extent_centre([outside], box(9.9, 19.9, 10.1, 20.1)) is None
    assert H3.flood_extent_centre([], box(9, 19, 11, 21)) is None


def test_registry_matches_the_preregistration():
    names = {m: sorted(H3.events_for(m, {})) for m in H3.MODULES}
    assert names == {"pluvial": ["belize_city", "hai_phong", "milagro"],
                     "flash_flood": ["choloma", "kastelli", "volos"],
                     "waterlogging": ["nam_dinh", "thai_binh"]}
    assert "jakarta_gfd_3280" in H3.EXCLUDED["waterlogging"]
    assert H3.BOX_SIDE_M == 4000.0 and H2.MIN_HELDOUT_EVENTS == 2
    ev = H3.events_for("pluvial", {"milagro": (-2.1, -79.6)})
    assert ev["milagro"]["bbox"] == R.square_bbox(-2.1, -79.6, 4000.0)
    assert ev["milagro"]["veg_window"] == H2.EVENTS["pluvial"]["milagro"]["veg_window"]
    assert ev["hai_phong"]["bbox"] is None                  # no centre -> dropped, not guessed
    for m, seen in H3.SEEN_IN_ROUND2.items():
        assert set(seen) <= set(names[m])


def test_weights_are_round2s_and_nothing_is_tuned():
    w = H3.frozen_weights()
    assert w["pluvial"] is None
    assert set(w) == set(H3.MODULES)


def test_evaluate_scores_frozen_weights_and_reports_the_unseen_diagnostic():
    n = 100
    flooded = np.zeros((2, n), bool)
    flooded[0] = True
    good = np.where(flooded, 0.9, 0.1)

    def ev(score):
        return {"arrays": {"score": score, "flooded": flooded, "valid": np.ones_like(flooded)},
                "meta": {"block": 1}}
    res = H3.evaluate("pluvial", {"milagro": ev(good), "hai_phong": ev(1 - good),
                                  "belize_city": {"error": "boom"}}, None)
    assert res["held_out"] == {"verdict": "failed", "auc": 0.5, "qualifying_events": 2}
    assert res["dropped"] == {"belize_city": "boom"}
    assert res["unseen_events_mean_auc_diagnostic"] == {"events": ["hai_phong"], "mean_auc": 0.0}
