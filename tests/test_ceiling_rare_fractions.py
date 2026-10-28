"""Tests for the rare-fraction ceiling checks (ceiling_rare_fractions.py) and
the endmember measurement script (measure_rare_endmembers.py).

The ceiling script restates helpers from modules that initialise Earth Engine
on import, so these tests pin the restatement to the original: the base
endmembers must equal ceiling_built_fraction.EM literally, and the controls
must reproduce the 06_UNMIXING_CEILING.md numbers.
"""

import ast
import json
import pathlib
import re

import numpy as np
import pytest

import ceiling_rare_fractions as crf

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _literal(path, name):
    tree = ast.parse((ROOT / path).read_text())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


def test_base_endmembers_are_the_06_set_verbatim():
    assert crf.EM_BASE == _literal("ceiling_built_fraction.py", "EM")
    assert crf.ORDER_BASE == _literal("ceiling_built_fraction.py", "ORDER")


def test_angles_reproduce_06_table():
    e = crf.EM_BASE
    assert crf.spectral_angle(e["built_fabric"], e["paved"]) == pytest.approx(
        1.70, abs=0.01)
    assert crf.spectral_angle(e["veg"], e["water"]) == pytest.approx(
        60.66, abs=0.01)
    assert crf.spectral_angle(e["paved"], e["bare"]) == pytest.approx(
        3.45, abs=0.01)


def test_controls_reproduce_06_ceilings():
    ok, veg, built = crf.run_controls(("ridge",))
    assert ok
    assert veg["ridge"][0] == pytest.approx(0.974, abs=0.001)
    assert built["ridge"][0] == pytest.approx(0.490, abs=0.001)


@pytest.mark.parametrize("r2,expected", [
    (0.70, "LABEL IT"), (0.95, "LABEL IT"),
    (0.6999, "INDETERMINATE"), (0.50, "INDETERMINATE"),
    (0.4999, "DON'T LABEL IT"), (-0.2, "DON'T LABEL IT"),
])
def test_verdict_bands(r2, expected):
    assert crf.verdict(r2) == expected


def test_rule_constants_are_the_pre_registered_ones():
    assert crf.RECOVERABLE_MIN == 0.70
    assert crf.UNIDENTIFIABLE_MAX == 0.50
    assert crf.NOISE_PRIMARY == 0.005
    assert {0.005, 0.010, 0.020} <= set(crf.NOISE_SWEEP)


def test_hull_residual_flags_a_mixture_of_base_endmembers():
    e = crf.EM_BASE
    mix = 0.4 * np.array(e["veg"]) + 0.6 * np.array(e["water"])
    res, coef = crf.hull_residual(mix, crf.base_matrix())
    assert res < 1e-4
    assert coef.sum() == pytest.approx(1.0, abs=1e-3)
    # Snow-like: bright visible, dark SWIR -- outside the base simplex.
    snow = [0.85, 0.85, 0.83, 0.75, 0.10, 0.08]
    res2, _ = crf.hull_residual(snow, crf.base_matrix())
    assert crf.noise_units(res2) > 10


def test_simulate_rare_shares_sum_to_one_and_target_is_rare_share():
    rng = np.random.default_rng(0)
    sites = [[0.05, 0.06, 0.06, 0.08, 0.10, 0.09]]
    X, B, R = crf.simulate_rare(500, 0.0, rng, [sites])
    np.testing.assert_allclose(B.sum(1) + R.sum(1), 1.0, atol=1e-9)
    np.testing.assert_allclose(
        X, B @ crf.base_matrix() + R[:, :1] * np.array(sites[0]), atol=1e-12)


def test_simulate_share_respects_s_max():
    rng = np.random.default_rng(0)
    sites = [[0.05, 0.06, 0.06, 0.08, 0.10, 0.09]]
    X, B, r = crf.simulate_share(1000, 0.0, rng, sites, 0.25)
    assert r.max() <= 0.25 and r.min() >= 0.0
    np.testing.assert_allclose(B.sum(1) + r, 1.0, atol=1e-9)


def test_a_mixture_endmember_cannot_be_recovered():
    """Self-test of the method on a known-unidentifiable case: a 'rare'
    class that is exactly half vegetation, half water must score low."""
    e = crf.EM_BASE
    fake = (0.5 * np.array(e["veg"]) + 0.5 * np.array(e["water"])).tolist()
    rows = crf.ceiling_for([fake], noise_sweep=[0.005])
    assert rows[0]["ridge"][0] < crf.UNIDENTIFIABLE_MAX


def test_result_is_experimental_never_validated():
    res = crf.build_result({}, [], {}, {}, [], None, {}, {}, {}, {})
    assert res["validation_status"] == "experimental"
    assert "validated" != res["validation_status"]


def test_load_endmembers_drops_failed_sites(tmp_path, monkeypatch):
    p = tmp_path / "em.json"
    p.write_text(json.dumps({"sites": [
        {"name": "a", "fraction": "solar", "subtype": "utility",
         "status": "ok", "mean": [0.1] * 6},
        {"name": "b", "fraction": "solar", "subtype": "rooftop",
         "status": "failed", "mean": [0.2] * 6},
    ]}))
    _, groups = crf.load_endmembers(str(p))
    assert [s["name"] for s in groups["solar"]] == ["a"]
    assert groups["snow_ice"] == []


# ---------------------------------------------------- measurement script

def test_every_ee_request_goes_through_the_timeout_wrapper():
    src = (ROOT / "measure_rare_endmembers.py").read_text()
    # getInfo appears exactly once: inside _get, which wraps ee_timeout.call.
    assert len(re.findall(r"\.getInfo\(", src)) == 1
    assert "lambda: obj.getInfo()" in src
    assert "ee.data.setDeadline" in src
    for fn in ("computePixels", "computeFeatures", "getDownloadURL"):
        assert fn not in src


def test_sites_come_from_mapped_references_not_spectral_thresholds():
    import measure_rare_endmembers as m
    kinds = {s["ref"][0] for s in m.SITES}
    assert kinds <= {"osm_element", "osm_rooftop", "glims_wc", "mangrove",
                     "marsh", "tidal_flat"}
    src = (ROOT / "measure_rare_endmembers.py").read_text()
    assert "normalizedDifference" not in src
    fracs = {s["fraction"] for s in m.SITES}
    assert fracs == set(crf.RARE_FRACTIONS)


def test_osm_polygons_builds_way_and_multipolygon():
    import measure_rare_endmembers as m
    sq = [{"lon": 0, "lat": 0}, {"lon": 1, "lat": 0}, {"lon": 1, "lat": 1},
          {"lon": 0, "lat": 1}, {"lon": 0, "lat": 0}]
    way = {"type": "way", "geometry": sq}
    rel = {"type": "relation", "members": [
        {"role": "outer", "geometry": sq[:3]},
        {"role": "outer", "geometry": sq[2:]},
        {"role": "inner", "geometry": [
            {"lon": .2, "lat": .2}, {"lon": .4, "lat": .2},
            {"lon": .4, "lat": .4}, {"lon": .2, "lat": .2}]},
    ]}
    polys = m.osm_polygons([way, rel])
    assert len(polys) == 2
    assert polys[0].area == pytest.approx(1.0)
    assert polys[1].area == pytest.approx(1.0 - 0.02)
