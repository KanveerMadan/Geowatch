"""Item 33 (C19): known-pixel denominator, observed_fraction as a mandatory
sibling, each observability cause its own field, estimate quality kept off
the denominator."""
import inspect

import numpy as np
import pytest

from analysis import contract as C
from analysis import observability as OB
from analysis.fractions import StandInFractions
from tests import analysis_synth as S


@pytest.fixture(scope="module")
def run():
    return S.run()[0]


def test_observed_fraction_is_emitted_and_is_the_fractions_denominator(run):
    of = run["outputs"]["observability"]["observed_fraction"]
    assert of["status"] == "available" and 0.9 < of["value"] < 1.0
    for f in ("vegetation", "water"):
        cov = run["outputs"]["fractions"][f]["coverage"]["observed_fraction"]
        assert abs(cov - of["value"]) < 0.02, f       # same denominator, two rasterisations


def test_each_cause_is_its_own_field_and_none_is_merged(run):
    obs = run["outputs"]["observability"]
    assert set(obs) == {"observed_fraction", "cloud_nodata", "fully_shadowed",
                        "transient_snow", "fire_smoke", "ships"}
    assert abs(obs["cloud_nodata"]["value"] - 2 / 12) < 1e-6
    assert 0.0 < obs["fully_shadowed"]["value"] < 1 / 12
    assert obs["transient_snow"]["value"] == 0.0 and obs["transient_snow"]["status"] == "available"
    for c in ("fire_smoke", "ships"):
        assert obs[c]["status"] == "not_computed" and obs[c]["validation_status"] == "placeholder"
    for banned in ("unknown", "unknown_pct", "unobserved", "non_observation_total"):
        assert banned not in obs


def test_estimate_quality_is_separate_and_never_touches_the_denominator(run):
    eq = run["outputs"]["estimate_quality"]
    assert set(eq["prediction_interval"]) == {"built", "vegetation", "water",
                                              "impervious_total", "paved", "bare"}
    for o in [*eq["prediction_interval"].values(), eq["paved_derivation_uncertainty"]]:
        assert o["status"] == "not_computed" and o["touches_denominator"] is False
        assert o["group"] == "estimate_quality"
    # Structural: the denominator reads only the clear-observation count.
    assert list(inspect.signature(OB.observed_fraction).parameters) == ["valid_obs", "inside"]


def test_denominator_ignores_estimate_quality_inputs():
    inside = np.ones((4, 4), bool)
    v = np.array([[5, 5, 0, 0]] * 4)
    assert OB.observed_fraction(v, inside) == 0.5


def test_no_derived_quantity_without_its_coverage_sibling(run):
    for path, o in C.walk_outputs(run["outputs"]):
        of = o["coverage"]["observed_fraction"]
        assert isinstance(of, float) and 0.0 <= of <= 1.0, path


def test_shadow_and_snow_leave_the_composite():
    p = StandInFractions()
    assert p.collection_filter is OB.occlusion_filter
    assert {3, 11} <= set(p.artifact()["params"]["occlusion"]["masked_scl"])
    off = StandInFractions(mask_occlusion=False)
    assert off.artifact()["sha256"] != p.artifact()["sha256"]   # a different version


def test_cause_shares_are_not_summed_into_one_number():
    inside = np.ones((2, 2), bool)
    counts = {"n_scene": np.full((2, 2), 10.0), "cloud_nodata": np.full((2, 2), 3.0),
              "fully_shadowed": np.full((2, 2), 3.0), "transient_snow": np.zeros((2, 2))}
    sh = OB.cause_shares(counts, inside)
    assert sh == {"cloud_nodata": 0.3, "fully_shadowed": 0.3, "transient_snow": 0.0}


def test_failed_observability_stage_is_named_and_not_stored(tmp_path):
    def boom(*a):
        raise TimeoutError("ee")
    r, _ = S.run(deps=S.deps(fetch_cause_counts=boom))
    obs = r["outputs"]["observability"]
    for c in OB.SCL_CAUSES:
        assert obs[c]["status"] == "failed" and obs[c]["value"] is None
    assert obs["observed_fraction"]["status"] == "available"
    from analysis.store import incomplete_stages
    assert incomplete_stages(r) == {"observability": "failed"}
