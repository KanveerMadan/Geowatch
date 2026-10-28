"""
Build item 24 — access indicators from the vector layer alone.

Run from the repo root:  pytest tests/test_vector_access.py
"""
import ast

import pytest
from shapely.geometry import box

from vector import access
from vector_synth import BBOX, M_PER_DEG_LON, _fix_ns, _layer, _way

REF = {"a": 0.19, "b": 1.0, "c": 2.78, "d": 8.35}


def _cross_layer(footprints=()):
    """A primary (asphalt) E-W across the box, nine N-S footways, so
    coverage is adequate and topology is reported."""
    # The primary carries a node at every footway crossing (ids 501..509),
    # as OSM does: crossing ways share their intersection node.
    primary = _way(1, "primary", 72.840, 72.850, 19.045, [500] + [501 + k for k in range(9)] + [510],
                   surface="asphalt")
    primary["geometry"] = [{"lon": 72.840 + 0.001 * i, "lat": 19.045} for i in range(11)]
    ways = [primary]
    for k in range(9):
        w = _way(100 + k, "footway", 0, 0, 0, [1000 + 2 * k, 501 + k, 1001 + 2 * k])
        w["geometry"] = [{"lon": 72.841 + 0.001 * k, "lat": lat} for lat in (19.040, 19.045, 19.050)]
        ways.append(w)
    return _layer(ways, footprints=list(footprints))


def _hut_at(lon, lat, size_m=8):
    d_lon, d_lat = size_m / M_PER_DEG_LON, size_m / 111_320
    return box(lon, lat, lon + d_lon, lat + d_lat)


def test_distance_to_paved_access_is_measured():
    # A hut whose south edge is 100 m north of the primary at 19.045.
    hut = _hut_at(72.8455, 19.045 + 100 / 111_320)
    a = access.access_indicators(_cross_layer([hut]), REF)
    d = a["paved_access"]["value"]["per_building"]
    assert d["median_m"] == pytest.approx(100.0, rel=0.02)
    assert a["paved_access"]["value"]["nearest_paved_on_class_default_share"] == 0.0


def test_footways_are_not_paved_access_by_default():
    """A hut next to a footway, far from the primary, measures to the primary."""
    hut = _hut_at(72.8411, 19.049)          # ~10 m from footway k=0, ~440 m from the primary
    d = access.access_indicators(_cross_layer([hut]), REF)["paved_access"]["value"]["per_building"]
    assert d["median_m"] > 400


def test_per_block_access_uses_the_layer_blocks():
    huts = [_hut_at(72.8405, 19.046), _hut_at(72.8495, 19.041)]
    a = access.access_indicators(_cross_layer(huts), REF)["paved_access"]["value"]
    assert a["blocks_with_buildings"] == 2
    assert a["blocks_total"] == len(_cross_layer(huts).blocks())


def test_connectivity_reported_under_adequate_coverage():
    a = access.access_indicators(_cross_layer(), REF)
    nc = a["network_connectivity"]
    assert a["coverage"]["coverage_regime_flag"] == "adequate"
    assert nc["status"] == "available"
    assert nc["value"]["components"] == 1          # every footway shares its crossing node
    assert 0 < nc["value"]["dead_end_ratio"] < 1


def test_connectivity_suppressed_under_low_coverage_not_silent():
    thin = _layer([_way(1, "primary", 72.840, 72.850, 19.045, [1, 2, 3])],
                  footprints=[_hut_at(72.845, 19.046)])
    a = access.access_indicators(thin, REF)
    assert a["coverage"]["topology_metrics_suppressed"]
    assert a["network_connectivity"]["status"] == "suppressed_low_coverage"
    assert a["network_connectivity"]["value"] is None
    # Distances are still computed, and say how much to trust them.
    assert a["paved_access"]["status"] == "available"
    assert a["paved_access"]["confidence"] in ("reduced", "low")


def test_access_traces_to_the_layer_and_uses_no_imagery():
    layer = _cross_layer([_hut_at(72.8455, 19.046)])
    assert access.access_indicators(layer, REF)["source_layer_id"] == layer.layer_id
    tree = ast.parse(open(access.__file__).read())
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not (mods & {"ee", "rasterio", "ingestion.sentinel2"})


def test_service_dependent_access_is_partial():
    from vector_synth import service_missing_layer
    a = access.access_indicators(service_missing_layer(), REF)
    assert a["network_connectivity"]["status"] == "partial_fetch"
    assert a["paved_access"]["status"] == "partial_fetch"
    assert "UPPER BOUNDS" in a["paved_access"]["fetch"]["note"]
