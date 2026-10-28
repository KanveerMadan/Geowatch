"""
Build item 23 — density metrics from the vector layer alone.

Synthetic layers. The live pre-registered separation test (Chandigarh vs
Dharavi) is recorded in 05_BUILD_MANUAL.md item 23.

Run from the repo root:  pytest tests/test_vector_density.py
"""
import ast
import math

import networkx as nx
import pytest
from shapely.geometry import box

from vector import density
from vector_synth import BBOX, M_PER_DEG_LON, _fix_ns, _layer, _rows_of_huts, _way

REF = {"a": 0.19, "b": 1.0, "c": 2.78, "d": 8.35}


def _graph(segments):
    G = nx.Graph()
    for i, ((x0, y0), (x1, y1)) in enumerate(segments):
        a, b = 2 * i, 2 * i + 1
        G.add_node(a, xy=(x0, y0)); G.add_node(b, xy=(x1, y1))
        G.add_edge(a, b, length_m=math.hypot(x1 - x0, y1 - y0))
    return G


def test_orientation_order_perfect_grid_is_one():
    G = _graph([((0, 0), (0, 100)), ((0, 0), (100, 0))])
    assert density.orientation_order(G) == pytest.approx(1.0)


def test_orientation_order_uniform_is_zero():
    segs = [((0, 0), (100 * math.sin(math.radians(10 * k)),
                      100 * math.cos(math.radians(10 * k)))) for k in range(18)]
    assert density.orientation_order(_graph(segs)) == pytest.approx(0.0, abs=1e-9)


def test_orientation_order_is_axial():
    north = _graph([((0, 0), (0, 100))])
    south = _graph([((0, 100), (0, 0))])
    assert density.orientation_order(north) == density.orientation_order(south)


def _dense_layer():
    ways = [_fix_ns(_way(100 + k, "footway", 0, 0, 0, [1000 + 3 * k, 1001 + 3 * k, 1002 + 3 * k]))
            for k in range(9)]
    ways += [_way(300, "primary", 72.840, 72.850, 19.045, [3000, 3001])]
    return _layer(ways, footprints=_rows_of_huts())


def test_every_metric_is_a_value_status_block():
    m = density.density_metrics(_dense_layer(), REF)
    for k in ("footprint_density", "built_area_share", "footprint_size_m2",
              "footprint_spacing_m", "orthogonality", "impervious_total"):
        assert {"value", "status"} <= set(m[k]), k
    for k in m["road_length_per_area"].values():
        assert {"value", "status"} <= set(k)


def test_footprint_metrics_match_the_synthetic_huts():
    m = density.density_metrics(_dense_layer(), REF)
    assert m["footprint_size_m2"]["value"]["median"] == pytest.approx(64.0, rel=0.03)
    assert m["footprint_density"]["value"] == pytest.approx(40 / _dense_layer().area_km2, rel=0.01)
    # 8 m huts, 3 m gap: centroid spacing 11 m within a row.
    assert m["footprint_spacing_m"]["value"]["median"] == pytest.approx(11.0, rel=0.05)


def test_impervious_total_is_not_computed_never_zero():
    m = density.density_metrics(_dense_layer(), REF)
    assert m["impervious_total"]["status"] == "not_computed"
    assert m["impervious_total"]["value"] is None


def test_orthogonality_is_suppressed_under_low_coverage():
    thin = _layer([_way(300, "primary", 72.840, 72.850, 19.045, [3000, 3001])],
                  footprints=_rows_of_huts())
    m = density.density_metrics(thin, REF)
    assert m["coverage"]["topology_metrics_suppressed"]
    assert m["orthogonality"]["status"] == "suppressed_low_coverage"
    assert m["orthogonality"]["value"] is None
    # ...while footprint metrics are still computed, flagged.
    assert m["footprint_density"]["status"] == "available"
    assert m["footprint_density"]["confidence"] in ("reduced", "low")


def test_no_spectral_inputs():
    """Item 23's acceptance: separation without any spectral input. The
    module may not import imagery code at all."""
    tree = ast.parse(open(density.__file__).read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    banned = {"ee", "rasterio", "ingestion.sentinel2", "ingestion.tiler", "ingestion.inference"}
    assert not (names & banned), names & banned
    assert density.density_metrics(_dense_layer(), REF)["spectral_inputs"] == []


def test_metrics_trace_to_the_layer():
    layer = _dense_layer()
    assert density.density_metrics(layer, REF)["source_layer_id"] == layer.layer_id


# ── the pre-registered separation test ──

def _m(median_area, fp_density, spacing, phi):
    return {
        "footprint_size_m2": {"value": {"median": median_area}, "status": "available"},
        "footprint_density": {"value": fp_density, "status": "available"},
        "footprint_spacing_m": {"value": {"median": spacing}, "status": "available"},
        "orthogonality": ({"value": phi, "status": "available"} if phi is not None
                          else {"value": None, "status": "suppressed_low_coverage"}),
    }


def test_separation_passes_when_predictions_hold():
    r = density.evaluate_separation(_m(300, 2000, 25, 0.6), _m(40, 15000, 8, 0.1))
    assert r["result"] == "PASS" and r["holding"] == 4


def test_separation_fails_on_any_reversal_even_with_three_holding():
    r = density.evaluate_separation(_m(300, 2000, 25, 0.1), _m(40, 15000, 8, 0.3))
    assert r["holding"] == 3 and r["reversed"] == 1
    assert r["result"] == "FAIL"


def test_suppressed_metric_is_not_tested_not_counted():
    r = density.evaluate_separation(_m(300, 2000, 25, None), _m(40, 15000, 8, 0.1))
    assert [x["outcome"] for x in r["rows"]][-1] == "not_tested"
    assert r["holding"] == 3 and r["result"] == "PASS"


def test_separation_test_is_fixed_and_names_its_aois():
    t = density.SEPARATION_TEST
    assert (t["formal"], t["informal"]) == ("chandigarh_central", "dharavi")
    assert t["min_holding"] == 3 and len(t["predictions"]) == 4


def test_service_dependent_density_metrics_are_partial():
    """A missing `service` clause: road length (all, broad) and the graph
    behind orthogonality are partial; narrow pedestrian length is not."""
    from vector_synth import service_missing_layer
    d = density.density_metrics(service_missing_layer(), REF)
    assert d["road_length_per_area"]["all"]["status"] == "partial_fetch"
    assert d["road_length_per_area"]["all"]["fetch"]["missing_clauses"] == ["service"]
    assert d["road_length_per_area"]["broad_pedestrian"]["status"] == "partial_fetch"
    assert d["road_length_per_area"]["narrow_pedestrian"]["status"] == "available"
    assert d["orthogonality"]["status"] == "partial_fetch"
