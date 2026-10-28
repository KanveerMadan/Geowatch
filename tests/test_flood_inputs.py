"""
Item 26, task 1: susceptibility is decoupled from the retired 7-class map.

The 7-class pipeline is retired (08_STATE.md §RETIRED). These tests prove no
susceptibility module reads its land-cover map, and that the replacement
inputs declare their source and are placeholders.
"""
import ast
import inspect
import pathlib
from types import SimpleNamespace

import numpy as np
import pytest
from shapely.geometry import box

import susceptibility
from susceptibility.inputs import (block_nanmean, impervious_built_area, mean_pct, surface,
                                   to_grid)
from susceptibility.pluvial import compute_pluvial_susceptibility
from susceptibility.waterlogging import compute_waterlogging_susceptibility

SUSC_DIR = pathlib.Path(susceptibility.__file__).parent

# Every name through which the 7-class map reaches a consumer.
SEVEN_CLASS_NAMES = {
    "landcover_map", "landcover_map_full", "categories", "category_area_pct",
    "hydrological_surfaces", "compute_hydrological_surfaces",
    "IMPERVIOUS_CLASS_WEIGHTS", "INFILTRATION_CLASS_WEIGHTS", "unknown_index",
}


def _names(path):
    tree = ast.parse(path.read_text())
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.arg):
            out.add(node.arg)
        elif isinstance(node, ast.alias):
            out.add(node.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module.split(".")[-1])
    return out


@pytest.mark.parametrize("path", sorted(SUSC_DIR.glob("*.py")), ids=lambda p: p.name)
def test_no_susceptibility_module_reads_the_7class_map(path):
    hits = _names(path) & (SEVEN_CLASS_NAMES | {"hydrological_surfaces", "inference"})
    assert not hits, f"{path.name} still reaches the retired 7-class map via {sorted(hits)}"


IMP = surface(np.array([[0.5, 1.0], [0.0, np.nan]]), "test footprints",
              "footprint_union_area_fraction", "placeholder")
INF = surface(np.array([[0.0, 0.0], [1.0, np.nan]]), "test NDVI", "ndvi_threshold_proxy",
              "placeholder")


def test_pluvial_refuses_an_undeclared_raster():
    with pytest.raises(ValueError, match="declared surface"):
        compute_pluvial_susceptibility(impervious=np.zeros((2, 2)), infiltration=INF)


def test_pluvial_refuses_inputs_on_different_grids():
    with pytest.raises(ValueError, match="one grid"):
        compute_pluvial_susceptibility(impervious=IMP, infiltration=INF,
                                       waterway_dist_map=np.zeros((3, 3)))


def test_pluvial_declares_its_inputs_and_is_placeholder():
    r = compute_pluvial_susceptibility(impervious=IMP, infiltration=INF)
    assert r["inputs"]["impervious"] == {"source": "test footprints",
                                         "method": "footprint_union_area_fraction",
                                         "validation_status": "placeholder"}
    assert r["inputs"]["infiltration"]["validation_status"] == "placeholder"
    assert r["validation_status"] == "placeholder"


def test_pluvial_leaves_unobserved_cells_out_of_the_mean():
    r = compute_pluvial_susceptibility(impervious=IMP, infiltration=INF)
    m = r["susceptibility_map"]
    assert np.isnan(m[1, 1])
    assert r["aoi_mean_score"] == pytest.approx(float(np.mean(m[np.isfinite(m)])), abs=1e-4)


def test_pluvial_with_no_spatial_input_is_insufficient_evidence():
    r = compute_pluvial_susceptibility(rainfall_mean_annual_mm=2000.0)
    assert r["status"] == "insufficient_evidence"


def test_waterlogging_reads_the_declared_impervious_share():
    # explicit weights: the tuned defaults (round 2) give impervious weight 0
    r = compute_waterlogging_susceptibility(None, IMP, weights={"impervious": 1.0})
    assert r["impervious_fraction_pct"] == 50.0           # mean of 0.5, 1.0, 0.0
    assert r["inputs"]["impervious"]["source"] == "test footprints"
    assert r["validation_status"] == "placeholder"


def test_waterlogging_signature_takes_no_7class_surfaces():
    params = inspect.signature(compute_waterlogging_susceptibility).parameters
    assert "hydrological_surfaces" not in params


def _layer(footprints):
    return SimpleNamespace(footprints=footprints, footprint_source="open_buildings_v3",
                           layer_id="abc")


def test_impervious_is_union_area_not_count():
    """Open Buildings fragments houses (item 23, Chandigarh). Splitting one
    20 x 20 m roof into four pieces, plus a duplicate overlapping one, must
    give the same built area as the single roof."""
    from rasterio.transform import from_origin
    t, shape = from_origin(0, 30, 30, 30), (1, 1)
    whole = impervious_built_area(_layer([box(0, 0, 20, 20)]), t, shape)
    split = impervious_built_area(_layer([box(0, 0, 10, 10), box(10, 0, 20, 10),
                                          box(0, 10, 10, 20), box(10, 10, 20, 20),
                                          box(0, 0, 20, 20)]), t, shape)
    assert whole["raster"][0, 0] == pytest.approx(400 / 900, abs=0.01)
    assert split["raster"][0, 0] == pytest.approx(whole["raster"][0, 0])
    assert whole["validation_status"] == "placeholder"
    assert whole["method"] == "footprint_union_area_fraction"


def test_surface_rejects_an_unknown_validation_label():
    with pytest.raises(ValueError):
        surface(np.zeros((1, 1)), "s", "m", "validated-ish")


def test_block_nanmean_ignores_unobserved_subcells():
    a = np.array([[1, np.nan, 0, 0], [1, 1, 0, 0]], dtype=np.float32)
    assert block_nanmean(a, 2).tolist() == [[1.0, 0.0]]


def test_mean_pct_is_none_when_nothing_observed():
    assert mean_pct(surface(np.full((2, 2), np.nan), "s", "m", "placeholder")) is None


def test_to_grid_reprojects_onto_the_hydrology_grid():
    from rasterio.transform import from_origin
    inputs = {"shape": (4, 4), "transform": from_origin(272400, 2107000, 30, 30),
              "crs": "EPSG:32643"}
    out = to_grid(np.full((50, 50), 0.25, dtype=np.float32),
                  (72.836, 19.037, 72.862, 19.06), inputs)
    assert out.shape == (4, 4)
    assert np.allclose(out[np.isfinite(out)], 0.25) and np.isfinite(out).all()
    assert to_grid(None, (0, 0, 1, 1), inputs) is None
