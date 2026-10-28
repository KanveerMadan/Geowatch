"""
Build item 20 — the OSM coverage score.

Synthetic layers, so nothing touches the network. The live reference set and
the Lagos / Khayelitsha scores are recorded in 05_BUILD_MANUAL.md item 20.

Run from the repo root:  pytest tests/test_vector_coverage.py
"""
import json
import math

import pytest

from vector import coverage, roads
from vector_synth import BBOX, _fix_ns, _layer, _way, service_missing_layer

REF = {"a": 0.19, "b": 0.39, "c": 1.29, "d": 2.11, "e": 2.78, "f": 8.35}

FIELDS = {"osm_density_percentile", "coverage_regime_flag", "regime_reasons",
          "narrow_pedestrian_km_per_km2", "broad_pedestrian_km_per_km2",
          "arterial_to_pedestrian_ratio", "footprints_per_road_km", "footprint_count",
          "footprint_source", "topology_metrics_suppressed",
          "footprint_metrics_confidence", "reference_set_size", "source_layer_id",
          "measure", "reference_measured_on"}


def _footways(n):
    """n north-south footways, each ~1.11 km, across the 1.17 km^2 box."""
    return [_fix_ns(_way(100 + k, "footway", 0, 0, 0, [1000 + 3 * k, 1001 + 3 * k, 1002 + 3 * k]))
            for k in range(n)]


def _arterials(n):
    # Spaced to stay inside BBOX (19.040-19.050) for any n up to 30.
    return [_way(200 + k, "primary", 72.840, 72.850, 19.0405 + 0.0003 * k, [2000 + 2 * k, 2001 + 2 * k])
            for k in range(n)]


def _score(ways, **kw):
    return coverage.score_layer(_layer(ways), REF, **kw)


def _no_nulls(obj):
    if obj is None:
        return False
    if isinstance(obj, dict):
        return all(_no_nulls(v) for k, v in obj.items() if k != "reference_measured_on")
    if isinstance(obj, list):
        return all(_no_nulls(v) for v in obj)
    return True


@pytest.mark.parametrize("ways", [[], _footways(1), _footways(9), _arterials(5)],
                         ids=["empty", "one-footway", "dense", "arterial-only"])
def test_every_field_present_and_never_null(ways):
    s = _score(ways)
    assert FIELDS <= set(s)
    assert _no_nulls(s)
    json.dumps(s, allow_nan=False)   # no NaN or inf anywhere


def test_lagos_like_and_khayelitsha_like_score_visibly_differently():
    """The acceptance shape: near-zero pedestrian with good arterials, vs a
    dense pedestrian network."""
    lagos = _score(_arterials(3))                    # 0 km narrow, 3 km arterial
    khaye = _score(_footways(9))                     # ~8.5 km/km^2 narrow
    assert lagos["coverage_regime_flag"] == "very_low"
    assert khaye["coverage_regime_flag"] == "adequate"
    assert khaye["osm_density_percentile"] - lagos["osm_density_percentile"] >= 50
    assert lagos["topology_metrics_suppressed"] and not khaye["topology_metrics_suppressed"]


def test_partial_mapping_signature_flags_low_even_above_density_floor():
    # ~1.9 km/km^2 narrow, but 30 arterial km over it.
    s = _score(_footways(2) + _arterials(30))
    assert s["narrow_pedestrian_km_per_km2"] > coverage.LOW_NARROW_KM_PER_KM2
    assert s["arterial_to_pedestrian_ratio"]["value"] > coverage.PARTIAL_MAPPING_ARTERIAL_TO_PEDESTRIAN
    assert s["coverage_regime_flag"] == "low"
    assert any("partial-mapping" in r for r in s["regime_reasons"])


def test_zero_pedestrian_ratio_is_capped_not_infinite_or_null():
    s = _score(_arterials(2))
    r = s["arterial_to_pedestrian_ratio"]
    assert (r["value"], r["capped"]) == (coverage.RATIO_CAP, True)


def test_zero_roads_footprint_ratio_is_capped():
    from shapely.geometry import box
    layer = _layer([], footprints=[box(72.841, 19.041, 72.8411, 19.0411)])
    s = coverage.score_layer(layer, REF)
    assert s["footprint_count"] == 1
    assert s["footprints_per_road_km"]["capped"] is True


def test_unretrieved_pedestrian_clause_is_not_measurable_not_zero():
    layer = _layer(_footways(9))
    layer.fetch["unavailable"] = ["narrow_pedestrian"]
    s = coverage.score_layer(layer, REF)
    assert s["coverage_regime_flag"] == "not_measurable"
    assert s["topology_metrics_suppressed"]


def test_region_scoring_uses_the_same_layer():
    from shapely.geometry import box
    layer = _layer(_footways(9))
    minx, miny, maxx, maxy = layer.aoi.bounds
    half = box(minx, miny, (minx + maxx) / 2, maxy)
    s = coverage.score_layer(layer, REF, region=half)
    assert s["source_layer_id"] == layer.layer_id


def test_never_named_a_completeness_rate():
    s = _score(_footways(1))
    assert s["measure"] == "peer_relative_density_rank"
    assert not any("completeness" in k for k in s)


def test_low_threshold_is_the_negative_space_trigger():
    assert coverage.LOW_NARROW_KM_PER_KM2 == roads.NEGATIVE_SPACE_TRIGGER_KM_PER_KM2


def test_percentile_rank_bounds():
    assert coverage.percentile_rank(0.0, REF.values()) == 0.0
    assert coverage.percentile_rank(100.0, REF.values()) == 100.0


def test_reference_set_is_populated_and_has_formal_anchors():
    ref = coverage.REFERENCE_NARROW_KM_PER_KM2
    assert ref, "the measured reference set must be committed"
    assert {"barcelona_eixample", "chandigarh_central"} <= set(ref)
    from vector.aois import BASELINE_AOIS
    assert set(BASELINE_AOIS) <= set(ref)
    assert coverage.REFERENCE_MEASURED_ON


def _fake_fetch(unavailable):
    def fetch(name, bbox):
        return {"ways": [w for w in _footways(2)], "clauses": {}, "unavailable": list(unavailable)}
    return fetch


def test_reference_refuses_a_lower_bound():
    with pytest.raises(RuntimeError, match="lower bound"):
        coverage.measure_reference({"x": BBOX}, fetch=_fake_fetch(["narrow_pedestrian"]))


def test_reference_unaffected_by_an_unrelated_missing_clause():
    ref = coverage.measure_reference({"x": BBOX}, fetch=_fake_fetch(["service"]))
    assert ref["x"] == pytest.approx(2 * 1.112 / _layer([]).area_km2, rel=0.02)


# ── Partial fetch: HCMC's service clause was not retrieved (live, 2026-10-27).
# Every metric built from service roads must say so; none may silently report
# the lower value as if complete. ──

def test_service_dependent_coverage_fields_are_partial():
    s = coverage.score_layer(service_missing_layer(), REF)
    assert s["footprints_per_road_km"]["fetch"]["status"] == "partial_fetch"
    assert s["footprints_per_road_km"]["fetch"]["missing_clauses"] == ["service"]
    assert s["road_length_fetch"]["all"]["status"] == "partial_fetch"
    assert s["road_length_fetch"]["broad_pedestrian"]["status"] == "partial_fetch"
    assert "LOWER BOUND" in s["road_length_fetch"]["all"]["note"]


def test_metrics_not_built_from_service_stay_complete():
    """arterial = motorway..tertiary, pedestrian = footway/path/pedestrian/steps:
    the ratio reads neither the service clause nor anything it contains."""
    s = coverage.score_layer(service_missing_layer(), REF)
    assert s["arterial_to_pedestrian_ratio"]["fetch"]["status"] == "complete"
    assert s["road_length_fetch"]["narrow_pedestrian"]["status"] == "complete"
    assert s["road_length_fetch"]["arterial"]["status"] == "complete"
    assert s["coverage_regime_flag"] != "not_measurable"


def test_complete_fetch_is_reported_complete():
    s = coverage.score_layer(_layer(_footways(9)), REF)
    assert all(v["status"] == "complete" and "note" not in v for v in s["road_length_fetch"].values())


def test_group_clause_map_matches_the_clause_partition():
    """Every class in a grouping must come from a clause listed for it."""
    import re
    from vector import roads, sources
    def clause_of(hw):
        for g, c in sources.HIGHWAY_CLAUSES.items():
            ok = True
            for op, pat in re.findall(r'\["highway"(=|~|!~)"([^"]+)"\]', c):
                if (op == "=" and hw != pat) or (op == "~" and not re.search(pat, hw)) \
                        or (op == "!~" and re.search(pat, hw)):
                    ok = False
            if ok:
                return g
    for group, classes in (("arterial", roads.ARTERIAL_CLASSES),
                           ("narrow_pedestrian", roads.NARROW_PEDESTRIAN_CLASSES),
                           ("broad_pedestrian", roads.BROAD_PEDESTRIAN_CLASSES)):
        assert {clause_of(h) for h in classes} <= roads.GROUP_CLAUSES[group], group
    assert roads.ALL_CLAUSES == set(sources.HIGHWAY_CLAUSES)


# ── Footprint count method (deviation recorded 2026-10-28) ──

def test_server_count_overrides_and_is_labelled():
    s = coverage.score_layer(_layer(_footways(2)), REF, footprint_count=112_264)
    assert s["footprint_count"] == 112_264
    assert s["footprint_count_method"] == "open_buildings_server_count"
    assert s["footprints_per_road_km"]["value"] == pytest.approx(112_264 / (2 * 1.112), rel=0.02)


def test_server_count_cannot_score_a_region():
    from shapely.geometry import box
    layer = _layer(_footways(2))
    with pytest.raises(ValueError):
        coverage.score_layer(layer, REF, footprint_count=10, region=box(*layer.aoi.bounds))


def test_layer_count_method_is_labelled_when_not_overridden():
    assert coverage.score_layer(_layer(_footways(2)), REF)["footprint_count_method"] == "layer_footprints"


def test_open_buildings_download_has_a_deadline(monkeypatch, tmp_path):
    """The 2026-10-27 stall: a download with no deadline hung for 23 h."""
    import ee
    from unittest.mock import MagicMock
    from vector import sources
    calls = []

    def stall(*_a, **_k):
        raise TimeoutError("deadline exceeded")

    monkeypatch.setattr(ee.data, "setDeadline", lambda ms: calls.append(ms))
    monkeypatch.setattr(ee.data, "computeFeatures", stall)
    monkeypatch.setattr(ee, "FeatureCollection", MagicMock())
    monkeypatch.setattr(ee.Geometry, "Rectangle", MagicMock())
    monkeypatch.setattr("ingestion.gee_client.initialize_gee", lambda: None)
    monkeypatch.setattr(sources, "CACHE_DIR", str(tmp_path))
    with pytest.raises(TimeoutError):
        sources.fetch_open_buildings("t", BBOX)
    assert calls == [sources.OPEN_BUILDINGS_DEADLINE_MS, 0]     # set, then restored


def test_reference_member_is_ranked_leave_one_out():
    """Found live: Khayelitsha ranked against its own rounded entry scored
    92.3 or 88.5 depending on the 4th decimal. It now excludes itself."""
    ref = {"t": 8.348, "a": 0.19, "b": 2.0, "c": 37.8}
    layer = _layer(_footways(9))          # name "t", ~8.5 km/km^2
    s = coverage.score_layer(layer, ref)
    assert s["percentile_basis"] == "leave_one_out"
    assert s["reference_set_size"] == 3
    assert s["osm_density_percentile"] == pytest.approx(100 * 2 / 3, abs=0.1)
    nudged = coverage.score_layer(layer, {**ref, "t": 8.3480001})
    assert nudged["osm_density_percentile"] == s["osm_density_percentile"]


def test_non_member_is_ranked_against_the_full_reference():
    s = coverage.score_layer(_layer(_footways(9)), {"a": 0.19, "b": 2.0, "c": 37.8})
    assert s["percentile_basis"] == "full_reference" and s["reference_set_size"] == 3
