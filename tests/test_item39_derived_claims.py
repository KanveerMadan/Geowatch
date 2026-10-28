"""Item 39 (C15): a claim is derived from the outcome, never latched ahead
of it. C15: result.json could claim road_access_scores_reliable: true and
road_score_method: "distance_transform" while every score was the -1.0
sentinel."""
import numpy as np

from pipeline import ROAD_ACCESS_SENTINEL, derive_osm_context
from tests import analysis_synth as S


class _Roads(list):
    pass


def test_all_sentinel_scores_cannot_claim_reliability():
    roads = _Roads([1, 2, 3])                       # roads WERE fetched
    segs = [{"road_access_score": ROAD_ACCESS_SENTINEL}] * 4
    c = derive_osm_context(roads, np.zeros((2, 2)), segs)
    assert c["osm_available"] is True
    assert c["road_access_scores_reliable"] is False
    assert c["road_score_method"] == "unavailable"
    assert c["road_access_sentinel_segments"] == 4


def test_missing_distance_map_cannot_claim_distance_transform():
    c = derive_osm_context(_Roads([1]), None, [{"road_access_score": 0.4}])
    assert c["road_access_scores_reliable"] is False and c["road_score_method"] == "unavailable"


def test_real_scores_and_map_are_reliable():
    c = derive_osm_context(_Roads([1]), np.zeros((2, 2)),
                           [{"road_access_score": 0.4}, {"road_access_score": -1.0}])
    assert c["road_access_scores_reliable"] is True
    assert c["road_score_method"] == "distance_transform"
    assert (c["road_access_scored_segments"], c["road_access_sentinel_segments"]) == (1, 1)


def test_legacy_pipeline_uses_the_derived_claim():
    src = open("pipeline.py").read()
    body = src[src.index("def run_pipeline("):src.index("def run_inundation_analysis(")]
    assert '"road_access_scores_reliable": osm_available' not in body
    assert "derive_osm_context(roads_gdf, full_dist_map, segments)" in body


def test_analysis_pipeline_claims_follow_the_outcome():
    r, _ = S.run()
    c = r["outputs"]["osm_coverage"]["osm_claims"]
    assert c["osm_available"] is True and c["road_conduits_used_by_pluvial"] is True
    assert c["claims_derived_from"].startswith("outcome")


def test_no_roads_retrieved_means_no_claim():
    from tests.test_item34_insufficient_evidence import _unknown_everything
    r, _ = S.run(deps=_unknown_everything())
    c = r["outputs"]["osm_coverage"]["osm_claims"]
    assert c["osm_available"] is False
    assert c["road_conduits_used_by_pluvial"] is False
    assert c["highway_fetch"]["status"] == "partial_fetch"
