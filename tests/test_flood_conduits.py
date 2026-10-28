"""
Item 26, task 3: roads enter flood susceptibility as rasterised vector
conduits from item 19's layer, at hydrology resolution.
"""
import numpy as np
import pytest

from configs.pluvial_constants import HYDROLOGY_PIXEL_M
from susceptibility.inputs import hydrology_grid, road_conduits, surface
from susceptibility.pluvial import compute_pluvial_susceptibility
from tests.vector_synth import _layer, _rows_of_huts, grid_layer  # noqa: F401


def test_conduits_are_on_the_hydrology_grid(grid_layer):
    t, shape = hydrology_grid(grid_layer)
    c = road_conduits(grid_layer, t, shape)
    assert abs(t.a) == HYDROLOGY_PIXEL_M == 30.0
    assert c["raster"].shape == shape


def test_conduit_area_matches_item19_road_space(grid_layer):
    """Area-preserving: the cells' road fractions add up to item 19's road
    space, so a 1.5 m footway is a sliver of a 30 m cell, not a whole one."""
    t, shape = hydrology_grid(grid_layer)
    c = road_conduits(grid_layer, t, shape)
    area = float(c["raster"].sum()) * HYDROLOGY_PIXEL_M ** 2
    expect = grid_layer.road_space(include_negative_space=False).area
    assert area == pytest.approx(expect, rel=0.03)
    assert 0 < c["raster"].max() <= 1.0


def test_conduits_declare_item19_and_are_experimental(grid_layer):
    t, shape = hydrology_grid(grid_layer)
    c = road_conduits(grid_layer, t, shape)
    assert grid_layer.layer_id in c["source"]
    assert c["validation_status"] == "experimental"


def test_footprint_negative_space_is_not_a_conduit():
    layer = _layer([], _rows_of_huts())
    t, shape = hydrology_grid(layer)
    assert road_conduits(layer, t, shape)["raster"].sum() == 0.0


def test_pluvial_scores_road_conduits():
    imp = surface(np.zeros((1, 2)), "s", "m", "placeholder")
    roads = surface(np.array([[0.0, 1.0]]), "OSM", "road_space_area_fraction", "experimental")
    r = compute_pluvial_susceptibility(impervious=imp, conduits=roads)
    assert "road_conduit" in r["components_used"]
    assert r["inputs"]["conduits"]["validation_status"] == "experimental"
    m = r["susceptibility_map"]
    assert m[0, 1] > m[0, 0]
