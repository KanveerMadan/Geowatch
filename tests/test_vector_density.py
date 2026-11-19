"""
Build item 23 — density metrics from the vector layer alone.

Synthetic layers. The live pre-registered separation test (Chandigarh vs
Dharavi) is recorded in 05_BUILD_MANUAL.md item 23.

Run from the repo root:  pytest tests/test_vector_density.py
"""
import ast
import math

import networkx as nx
import numpy as np
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


# ── built masses and separation test v2 (item 23 fix, 2026-11-20) ──

def test_touching_footprints_are_one_mass_and_a_lane_separates_them():
    a, b = box(0, 0, 10, 10), box(10, 0, 20, 10)          # shared wall
    c = box(23, 0, 33, 10)                                 # 3 m lane
    m = density.built_masses([a, b, c])
    assert sorted(m["areas"].tolist()) == [100.0, 200.0]
    assert sorted(m["counts"].tolist()) == [1, 2]
    assert m["gaps"].tolist() == pytest.approx([3.0, 3.0])


def test_a_seam_under_the_gap_is_bridged_a_lane_is_not():
    a, b = box(0, 0, 10, 10), box(10.5, 0, 20, 10)         # 0.5 m segmentation seam
    assert len(density.built_masses([a, b])["areas"]) == 1
    c = box(11.5, 0, 20, 10)                               # 1.5 m: a passage
    assert len(density.built_masses([a, c])["areas"]) == 2


def test_mass_metrics_do_not_change_when_a_building_is_cut_into_fragments():
    """The defect behind v1's failure: Open Buildings cuts one house into
    several polygons. Per-footprint size changes; mass metrics must not."""
    whole = [box(x, 0, x + 12, 12) for x in (0, 30, 60)]
    cut = [p for x in (0, 30, 60) for p in (box(x, 0, x + 6, 12), box(x + 6, 0, x + 12, 6),
                                            box(x + 6, 6, x + 12, 12))]
    mw, mc = density._mass_block(whole, "full")["value"], density._mass_block(cut, "full")["value"]
    for k in ("n_masses", "area_weighted_mean_m2", "median_mass_m2", "largest_mass_share", "median_gap_m"):
        assert mw[k] == pytest.approx(mc[k]), k
    assert np.median([p.area for p in cut]) != np.median([p.area for p in whole])


def test_density_metrics_report_built_masses():
    m = density.density_metrics(_dense_layer(), REF)
    v = m["built_mass"]["value"]
    assert m["built_mass"]["status"] == "available"
    assert v["gap_m"] == density.MASS_GAP_M == 1.0
    # The synthetic huts stand 3 m apart: every hut is its own mass.
    assert v["n_masses"] == 40 and v["footprints_per_mass"] == 1.0
    assert v["median_gap_m"] == pytest.approx(3.0, rel=0.05)


def test_separation_test_v1_is_unchanged():
    t = density.SEPARATION_TEST
    assert [(p[1], p[2], p[3]) for p in t["predictions"]] == [
        (("footprint_size_m2", "median"), "formal_over_informal_ratio", 2.0),
        (("footprint_density",), "informal_over_formal_ratio", 2.0),
        (("footprint_spacing_m", "median"), "formal_over_informal_ratio", 1.5),
        (("orthogonality",), "formal_minus_informal", 0.10)]


def test_separation_test_v2_is_fixed_as_preregistered():
    t = density.SEPARATION_TEST_V2
    assert (t["formal"], t["informal"], t["min_holding"]) == ("chandigarh_central", "dharavi", 3)
    assert [(p[1], p[2], p[3]) for p in t["predictions"]] == [
        (("built_mass", "area_weighted_mean_m2"), "informal_over_formal_ratio", 2.0),
        (("built_area_share",), "informal_over_formal_ratio", 1.5),
        (("built_mass", "median_gap_m"), "formal_over_informal_ratio", 1.5),
        (("orthogonality",), "formal_minus_informal", 0.10)]
    assert "consistency check" in t["status"]


def _m2(awm, share, gap, phi):
    return {"built_mass": {"value": {"area_weighted_mean_m2": awm, "median_gap_m": gap}, "status": "available"},
            "built_area_share": {"value": share, "status": "available"},
            "orthogonality": {"value": phi, "status": "available"}}


def test_separation_v2_evaluates_with_the_same_rule():
    ok = density.evaluate_separation(_m2(300, 0.2, 6, 0.8), _m2(5000, 0.5, 2, 0.1),
                                     density.SEPARATION_TEST_V2)
    assert ok["result"] == "PASS" and ok["holding"] == 4
    bad = density.evaluate_separation(_m2(300, 0.2, 6, 0.8), _m2(200, 0.5, 2, 0.1),
                                      density.SEPARATION_TEST_V2)
    assert bad["reversed"] == 1 and bad["result"] == "FAIL"
