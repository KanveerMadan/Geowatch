"""Item 34 (C21): a synthetic all-unknown AOI produces insufficient_evidence
throughout, never `score: 0.0, class: "very_low"`. The two once-dead
branches -- waterlogging "not_calculated" in applicability (stage 1 and
stage 2) and waterlogging.py's insufficient_evidence -- are reachable."""
import numpy as np
import pytest

from perception.applicability import compute_applicability, finalize_applicability
from perception.hydrological_surfaces import compute_hydrological_surfaces
from susceptibility.waterlogging import compute_waterlogging_susceptibility
from tests import analysis_synth as S

HAND_DOWN = {"status": "unavailable", "error": "MERIT unavailable"}


@pytest.mark.parametrize("cat", [{}, {"dense_informal_roofing": 0.0, "paved_road": 0.0}])
def test_all_unknown_surfaces_have_a_failure_path(cat):
    hs = compute_hydrological_surfaces(cat)
    assert hs["status"] == "insufficient_evidence"
    assert hs["impervious_fraction_pct"] is None and hs["infiltration_proxy_pct"] is None


def test_classified_surfaces_say_available():
    hs = compute_hydrological_surfaces({"dense_informal_roofing": 40.0})
    assert hs["status"] == "available" and hs["impervious_fraction_pct"] > 0


def test_legacy_chain_is_insufficient_evidence_throughout():
    hs = compute_hydrological_surfaces({})
    # stage 1, single-call form (applicability.py, the waterlogging branch)
    app1 = compute_applicability(unknown_pct=100.0, ambiguous_pct=0.0, hand_context=HAND_DOWN,
                                 hydrological_surfaces=hs)
    assert app1["waterlogging"]["status"] == "not_calculated"
    # stage 2 (finalize_applicability, the same branch)
    app2 = compute_applicability(unknown_pct=100.0, ambiguous_pct=0.0, hand_context=HAND_DOWN)
    app2 = finalize_applicability(app2, hs)
    assert app2["waterlogging"]["status"] == "not_calculated"
    # waterlogging.py's insufficient_evidence branch
    w = compute_waterlogging_susceptibility(HAND_DOWN, impervious=None)
    assert w["status"] == "insufficient_evidence"
    assert "aoi_mean_score" not in w and w.get("aoi_mean_class") != "very_low"


def test_before_the_fix_the_same_input_read_as_very_low():
    """The C21 shape, reproduced against a zero impervious surface: this is
    what an all-unknown AOI produced when the producer had no failure path."""
    from susceptibility.inputs import surface
    zero = surface(np.zeros((3, 3)), "x", "y", "placeholder")
    w = compute_waterlogging_susceptibility(HAND_DOWN, impervious=zero)
    assert w["aoi_mean_score"] == 0.0 and w["aoi_mean_class"] == "very_low"


def _unknown_everything():
    unavailable = {k: (lambda: {"status": "unavailable", "error": "down"})
                   for k in S.context_fns()}
    from vector import roads
    from tests.vector_synth import BBOX
    empty = roads.build_road_layer("t", BBOX, highways={"ways": [], "clauses": {
        g: None for g in ("arterial", "residential", "service", "narrow_pedestrian", "other")},
        "unavailable": ["arterial", "residential", "service", "narrow_pedestrian", "other"]},
        footprints_4326=[], footprint_source="none")
    return S.deps(context_fns=unavailable, load_layer=lambda n, b: empty,
                  fetch_dem=lambda *a: np.full(a[2], np.nan),
                  fetch_waterways=lambda n, b: {"ways": [], "unavailable": ["waterway"]})


def test_new_pipeline_all_unknown_aoi_is_insufficient_throughout():
    r, units = S.run(producer=S.SynthProducer(unobserved_all=True), deps=_unknown_everything())
    o = r["outputs"]
    for name, h in o["susceptibility"].items():
        assert h["value"] is None, name
        assert h["status"] in ("insufficient_evidence", "not_applicable"), (name, h["status"])
        assert h["tier"] is None, name
    for f, v in o["fractions"].items():
        assert v["value"] is None and v["status"] in ("insufficient_observation", "not_computed"), f
    assert o["observability"]["observed_fraction"]["value"] == 0.0
    for t, b in units.items():
        for u in b["units"]:
            for f in ("built", "vegetation", "water"):
                assert u[f]["status"] != "available", (t, f)
