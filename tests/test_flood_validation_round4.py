"""Flood round 4 harness (experiments/flood_validation/harness_round4.py): the
pure parts -- the box rule on a Sentinel-1 reference, the margin window, the
tuning / test separation and the choice rule. No Earth Engine."""
import numpy as np
import pytest
from rasterio.transform import from_origin

from experiments.flood_validation import harness_round4 as H4


def test_no_tuning_event_is_a_test_event():
    H4.check_disjoint(H4.TEST_EVENTS, H4.tuning_events())
    with pytest.raises(ValueError, match="tuning events used as test events"):
        H4.check_disjoint({"pluvial": {"volos": {}}}, {"flash_flood": {"volos": {}}})


def test_tuning_boxes_are_round3s_exactly():
    import json
    t = H4.tuning_events()
    r3 = json.load(open(H4.ROUND3_RESULT))["modules"]
    for module, evs in t.items():
        for n, ev in evs.items():
            assert list(ev["centre"]) == r3[module]["events"][n]["centre"]


def test_chennai_is_not_run_before_any_score():
    ev = H4.TEST_EVENTS["pluvial"]["chennai_2023"]
    assert ev["ref"] == ("none",) and "no usable reference" in ev["not_run"]
    built = H4.build_all("test", "pluvial", {"chennai_2023": ev}, evaluate_only=False)
    assert built["chennai_2023"]["error"].startswith("not-run")


def test_s1_centre_is_the_flood_centroid_or_the_nearest_flooded_cell():
    t = from_origin(500000, 1000000 + 300, 30, 30)       # UTM 32643, 10 x 10 cells
    f = np.zeros((10, 10), bool)
    f[2:4, 2:4] = True
    lat, lon = H4.s1_flood_centre(f, np.ones_like(f), t, "EPSG:32643")
    from pyproj import Transformer
    x, y = Transformer.from_crs(4326, "EPSG:32643", always_xy=True).transform(lon, lat)
    assert x == pytest.approx(500000 + 3 * 30, abs=0.01)  # centre of the 2 x 2 patch
    assert y == pytest.approx(1000300 - 3 * 30, abs=0.01)
    ring = np.zeros((10, 10), bool)                        # two patches: centroid falls between
    ring[0, 0] = ring[9, 9] = True
    lat, lon = H4.s1_flood_centre(ring, np.ones_like(ring), t, "EPSG:32643")
    x, y = Transformer.from_crs(4326, "EPSG:32643", always_xy=True).transform(lon, lat)
    assert (round(x - 500000), round(1000300 - y)) in {(15, 15), (285, 285)}
    assert H4.s1_flood_centre(np.zeros((3, 3), bool), np.ones((3, 3), bool), t,
                              "EPSG:32643") is None


def test_the_box_sits_inside_its_margin_grid_on_one_lattice():
    from experiments.flood_validation import references as R
    from susceptibility.hydro_rasters import utm_grid
    lat, lon = 25.2048, 55.2708
    tb, sb, crs = utm_grid(R.square_bbox(lat, lon, 4000))
    to, so, crs_o = utm_grid(R.square_bbox(lat, lon, 6000))
    assert crs == crs_o
    r0, c0 = H4.window_in(to, so, tb, sb)
    assert 30 <= r0 <= 36 and 30 <= c0 <= 36               # ~1 km margin
    with pytest.raises(ValueError):
        H4.window_in(tb, sb, to, so)


def test_choice_rule_prefers_the_default_among_ties_and_ignores_unqualified_events():
    flooded = np.zeros((10, 10), bool)
    flooded[:, :5] = True
    hand = np.tile(np.arange(10.0), (10, 1))                # low HAND where it flooded
    upa = np.full((10, 10), 10.0)
    rel = np.full((10, 10), 10.0)
    arrays = {"layer_hand_m": hand, "layer_upa_flash_km2": upa,
              "layer_relief_slope_deg": rel, "flooded": flooded,
              "valid": np.ones((10, 10), bool)}
    grid = [{"hand_max_m": 20.0, "power_exponent": 1.0},
            {"hand_max_m": 10.0, "power_exponent": 1.0}]
    sel = H4.choose("flash_flood", grid, grid[1], {"a": {"arrays": arrays}})
    assert sel["chosen"] == grid[1] and sel["best_tuning_mean_auc"] == 1.0
    tiny = dict(arrays, flooded=np.zeros((10, 10), bool))   # 0 flooded cells: unqualified
    sel = H4.choose("flash_flood", grid, grid[0], {"a": {"arrays": tiny}})
    assert sel["chosen"] == grid[0] and "default kept" in sel["reason"]
