"""
Item 26, task 4: DEM hydrology (slope, flow accumulation, topographic
position, drainage connectivity) as pluvial inputs, on synthetic DEMs whose
answers are known by construction.
"""
import numpy as np
import pytest

from configs.pluvial_constants import COMPONENT_QUALITY, COMPONENT_WEIGHTS
from susceptibility.inputs import surface
# the round-1 pluvial method these terrain inputs were built for (retired in
# flood round 4, which routes on the DEM itself: tests/test_flood_round4_methods.py)
from susceptibility.retired_methods.pluvial_round1 import compute_pluvial_susceptibility
from susceptibility.terrain import (TERRAIN_COMPONENTS, d8_receivers, drains_to_edge,
                                    flow_accumulation, slope_deg, terrain_surfaces, tpi)

PX = 30.0


def _tilted(H=6, W=5, drop_per_row=0.3):
    """A plane falling toward the last row."""
    return np.repeat((np.arange(H)[::-1] * drop_per_row)[:, None], W, axis=1).astype(float)


def _bowl(n=7):
    r, c = np.mgrid[0:n, 0:n]
    return ((r - n // 2) ** 2 + (c - n // 2) ** 2).astype(float) * 0.1


def test_slope_of_a_plane():
    s = slope_deg(_tilted(drop_per_row=3.0), PX)
    assert np.allclose(s, np.degrees(np.arctan(3.0 / PX)))


def test_flow_accumulates_down_the_plane():
    dem = _tilted()
    acc = flow_accumulation(dem, d8_receivers(dem, PX))
    assert acc[0].tolist() == [0] * 5            # ridge row: nothing upstream
    assert acc[-1].tolist() == [5] * 5           # each column's five cells above it


def test_plane_drains_to_the_edge_and_bowl_does_not():
    dem = _tilted()
    assert drains_to_edge(dem, d8_receivers(dem, PX)).all()
    bowl = _bowl()
    con = drains_to_edge(bowl, d8_receivers(bowl, PX))
    assert not con[3, 3]                         # the pit
    assert not con[2:5, 2:5].any()               # its interior catchment
    assert con[0].all()                          # the edge itself


def test_tpi_is_negative_in_a_hollow():
    bowl = _bowl()
    t = tpi(bowl, 2)
    assert t[3, 3] < 0
    assert t[3, 3] == t.min()


def test_terrain_surfaces_are_scored_experimental_and_bounded():
    out = terrain_surfaces(_bowl(), PX)
    assert set(out) == set(TERRAIN_COMPONENTS)
    for name, s in out.items():
        assert s["validation_status"] == "experimental"
        r = s["raster"]
        assert np.nanmin(r) >= 0 and np.nanmax(r) <= 1, name
    assert out["drainage_disconnection"]["raster"][3, 3] == 1.0
    assert out["topographic_hollow"]["raster"][3, 3] > 0


def test_nodata_stays_nodata():
    dem = _tilted()
    dem[2, 2] = np.nan
    out = terrain_surfaces(dem, PX)
    for s in out.values():
        assert np.isnan(s["raster"][2, 2])
    recv = d8_receivers(dem, PX)
    assert 2 * 5 + 2 not in recv                 # nothing drains into a no-data cell


def test_every_terrain_component_has_its_own_weight_and_quality():
    for name in TERRAIN_COMPONENTS:
        assert name in COMPONENT_WEIGHTS and name in COMPONENT_QUALITY


def test_pluvial_uses_terrain_and_ranks_the_pit_highest():
    bowl = _bowl()
    flat = surface(np.zeros(bowl.shape), "s", "m", "placeholder")
    r = compute_pluvial_susceptibility(impervious=flat, terrain=terrain_surfaces(bowl, PX))
    assert set(TERRAIN_COMPONENTS) <= set(r["components_used"])
    m = r["susceptibility_map"]
    assert m[3, 3] == pytest.approx(m.max())
    assert r["inputs"]["flow_accumulation"]["validation_status"] == "experimental"
