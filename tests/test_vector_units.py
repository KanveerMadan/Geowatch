"""
Build item 22 — aggregation units.

Synthetic fraction rasters on a synthetic layer. The live AOI run is recorded
in 05_BUILD_MANUAL.md item 22.

Run from the repo root:  pytest tests/test_vector_units.py
"""
import numpy as np
import pytest

from vector import fractions, units
from vector_synth import _fix_ns, _layer, _rows_of_huts, _way

OSM_COV = {"coverage_regime_flag": "adequate", "osm_density_percentile": 60.0, "basis": "aoi"}


@pytest.fixture
def layer():
    ways = [_way(1, "primary", 72.840, 72.850, 19.045, [1, 2, 3])]
    ways.append(_fix_ns(_way(2, "footway", 0, 0, 0, [4, 2, 5])))
    return _layer(ways, footprints=_rows_of_huts())


def _fr(layer, observed_all=True):
    tr, shape = fractions.grid_for(layer)
    rng = np.random.default_rng(0)
    veg = (rng.random(shape) > 0.7).astype(np.float32)
    water = np.zeros(shape, dtype=np.float32)
    water[:5, :] = 1.0
    veg[:5, :] = 0.0
    obs = np.ones(shape, dtype=bool)
    if not observed_all:
        obs[:, : shape[1] // 2] = False          # cloud over the west half
        veg[~obs] = np.nan
        water[~obs] = np.nan
    return {"rasters": {"built": fractions.built_raster(layer, tr, shape), "vegetation": veg, "water": water},
            "observed": {"built": np.ones(shape, bool), "vegetation": obs, "water": obs},
            "transform": tr, "shape": shape, "method": fractions.PROXY_METHOD,
            "producer": fractions.PRODUCER}


def test_three_unit_types_each_carry_value_status_coverage(layer):
    out = units.build_units(layer, _fr(layer), OSM_COV)
    for t in units.UNIT_TYPES:
        block = out["by_type"][t]
        assert block["status"] == "available", t
        assert block["n_units"] > 0
        for u in block["units"]:
            for f in fractions.FRACTIONS:
                assert set(u[f]) == {"value", "status", "coverage"}
            assert u["osm_coverage"] == OSM_COV


def test_impervious_total_is_not_computed_never_zero(layer):
    out = units.build_units(layer, _fr(layer), OSM_COV)
    for t in units.UNIT_TYPES:
        for u in out["by_type"][t]["units"]:
            assert u["impervious_total"] == {"value": None, "status": "not_computed", "coverage": 0.0}


def test_consistency_same_totals_across_unit_types(layer):
    out = units.build_units(layer, _fr(layer), OSM_COV)
    c = out["consistency"]
    assert c["result"] == "PASS"
    assert set(c["unit_types_compared"]) == set(units.UNIT_TYPES)
    for t, share in c["unit_area_over_aoi_area"].items():
        assert share == pytest.approx(1.0, abs=0.01), t


def test_built_total_matches_footprint_area(layer):
    out = units.build_units(layer, _fr(layer), OSM_COV)
    built_m2 = out["by_type"]["grid"]["totals"]["built"]["fraction_area_m2"]
    assert built_m2 == pytest.approx(sum(p.area for p in layer.footprints), rel=0.05)


def test_consistency_fails_when_a_partition_drops_area(layer):
    fr = _fr(layer)
    grid = units.grid_units(layer, fr["transform"])
    full = units.aggregate(grid, fr, OSM_COV)
    broken = units.aggregate(grid[: len(grid) // 2], fr, OSM_COV)
    by_type = {"grid": {"status": "available", **full}, "path": {"status": "available", **broken}}
    assert units.consistency_check(by_type, layer.aoi.area)["result"] == "FAIL"


def test_unobserved_area_is_insufficient_not_zero(layer):
    out = units.build_units(layer, _fr(layer, observed_all=False), OSM_COV)
    statuses = [u["vegetation"]["status"] for u in out["by_type"]["grid"]["units"]]
    assert "insufficient_observation" in statuses
    west = [u for u in out["by_type"]["grid"]["units"] if u["vegetation"]["coverage"] == 0.0]
    assert west and all(u["vegetation"]["value"] is None for u in west)
    # built is footprint-derived, unaffected by cloud.
    assert all(u["built"]["status"] == "available" for u in out["by_type"]["grid"]["units"])


def test_footprint_units_one_per_building(layer):
    assert len(units.footprint_units(layer)) == len(layer.footprints)


def test_path_units_are_the_layer_blocks(layer):
    assert len(units.path_units(layer)) == len(layer.blocks())


def test_units_trace_to_the_layer_and_say_what_produced_veg_water(layer):
    out = units.build_units(layer, _fr(layer), OSM_COV)
    assert out["source_layer_id"] == layer.layer_id
    assert "PROXY" in out["producer"]["vegetation"] and "PROXY" in out["producer"]["water"]


def test_classify_indices_unobserved_is_nan_not_zero():
    ndvi = np.array([[0.5, 0.1], [0.5, np.nan]], dtype=np.float32)
    mndwi = np.array([[-0.2, 0.3], [-0.2, -0.2]], dtype=np.float32)
    obs = np.array([[5, 5], [1, 5]])
    c = fractions.classify_indices(ndvi, mndwi, obs)
    assert c["vegetation"][0, 0] == 1 and c["water"][0, 1] == 1 and c["vegetation"][0, 1] == 0
    assert np.isnan(c["vegetation"][1, 0]) and np.isnan(c["water"][1, 1])


def test_path_units_are_partial_when_a_clause_is_missing():
    from vector_synth import service_missing_layer
    layer = service_missing_layer()
    u = units.build_units(layer, _fr(layer), OSM_COV)
    assert u["by_type"]["path"]["status"] == "partial_fetch"
    assert u["by_type"]["path"]["fetch"]["missing_clauses"] == ["service"]
    assert u["by_type"]["grid"]["status"] == "available"
