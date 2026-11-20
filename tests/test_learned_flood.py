"""flood_final learned flood output: model export, feature parity, masks,
labels. Parity tests use the experiment caches and skip without them."""
import hashlib
import json
import os

import numpy as np
import pytest

from analysis import contract as C
from analysis import hazards as H
from susceptibility import learned_flood as L

CACHE = os.path.expanduser("~/.cache/geowatch")
PKL = os.path.join(CACHE, "flood_final", "model_v2", "final__open__logreg.pkl")
UNIT = "emsr757_aoi02"          # a DEV unit (never reserved)
from tests.test_flood_taxonomy import MV  # noqa: E402


def test_model_json_is_the_frozen_final_model():
    m = json.load(open(L.MODEL_PATH))
    mc = json.load(open(os.path.join("experiments", "flood_final", "results", "method_choice.json")))
    assert m["source_pickle_sha256"] == mc["final_models"]["open__logreg"]["sha256"]
    assert m["features"] == mc["final_models"]["open__logreg"]["features"]
    assert mc["choice"]["fluvial"]["chosen"] == mc["choice"]["waterlogging"]["chosen"] == "open__logreg"


def test_contract_pins_this_model_file():
    assert C.VALIDATED_CONFIGS["learned_flood"]["config"]["model_sha256"] == L.model_sha256()


@pytest.mark.skipif(not os.path.exists(PKL), reason="flood_final model cache absent")
def test_json_predictions_equal_the_pickle():
    import pickle
    from experiments.flood_learned import features as FT
    f = pickle.load(open(PKL, "rb"))
    t = FT.load(UNIT)
    X = t["X"][:, [FT.FEATURES.index(c) for c in f["features"]]]
    raw, cal = L.predict(L.load_model(), X)
    assert np.allclose(raw, f["model"].predict_proba(X)[:, 1], atol=1e-12)
    assert np.allclose(cal, f["isotonic"].predict(raw), atol=1e-4)


@pytest.mark.skipif(not os.path.exists(os.path.join(CACHE, "flood_learned", "inputs", f"{UNIT}.npz"))
                    and not os.path.exists(os.path.join(CACHE, "flood_learned", "tables", f"{UNIT}.npz")),
                    reason="flood_learned caches absent")
def test_assemble_reproduces_the_training_table():
    from experiments.flood_baselines import build as BUILD
    from experiments.flood_learned import features as FT
    from experiments.flood_learned import fetch as F
    try:
        base, li = BUILD.load(UNIT), F.load(UNIT)
    except (OSError, FileNotFoundError):
        pytest.skip("unit inputs not cached")
    a, La = base["arrays"], li["arrays"]
    inp = {**La, "dist_water_m": a["dist_water_m"], "jrc_occurrence": a["jrc_occurrence"]}
    layers = {k[len("layer_"):]: v for k, v in a.items() if k.startswith("layer_")}
    shape = tuple(base["meta"]["grid"]["shape"])
    model = L.load_model()
    X = L.assemble(model["features"], inp, layers, li["meta"]["margin_cells"], shape)
    t = FT.load(UNIT)
    ref = t["X"][:, [FT.FEATURES.index(c) for c in model["features"]]]
    assert X.shape == ref.shape
    assert np.array_equal(np.isnan(X), np.isnan(ref))
    ok = np.isfinite(ref)
    assert np.allclose(X[ok], ref[ok], rtol=0, atol=1e-5)


def _fake(shape=(20, 30)):
    from tests.analysis_synth import fake_learned_inputs
    return fake_learned_inputs(None, shape, "EPSG:32631", 2025, "t")


def _rasters(shape):
    return {"layers": {k: {"raster": np.full(shape, v)} for k, v in
                       (("rain_intensity_mm_h", 20.0), ("rain_design_day_mm", 80.0),
                        ("rain_annual_mm", 1200.0), ("clay_pct", 25.0))}, "errors": {}}


def test_built_up_and_permanent_water_are_not_assessed():
    shape = (20, 30)
    inp = _fake(shape)
    inp["arrays"]["jrc_occurrence"][0, 0] = 95.0
    out = L.compute_learned_flood(inp, _rasters(shape), shape)
    smap = out["susceptibility_map"]
    assert np.isnan(smap[:, 15:]).all()                 # built share 0.8 >= 0.5
    assert np.isnan(smap[0, 0])                         # permanent water
    assert np.isfinite(smap[1:, :15]).all()
    assert out["not_assessed"]["built_up_cells"] == 20 * 15
    assert out["not_assessed"]["permanent_water_cells"] == 1


def test_low_ground_near_water_ranks_higher():
    shape = (20, 30)
    out = L.compute_learned_flood(_fake(shape), _rasters(shape), shape)
    smap = out["susceptibility_map"]
    assert np.nanmean(smap[:, :3]) > np.nanmean(smap[:, 10:15])


def test_failed_inputs_give_no_score_never_zero():
    out = L.compute_learned_flood(None, None, (5, 5))
    assert out["aoi_mean_score"] is None and out["susceptibility_map"] is None


def test_verdict_is_read_from_the_pinned_heldout_result():
    assert C.flood_final_verdict() == "passed"
    assert C.flood_verdicts()["learned_flood"] == "passed"
    with pytest.raises(C.ContractError):
        C.flood_final_verdict(expected_sha256="0" * 64)


def test_learned_output_is_validated_only_with_its_exact_config():
    shape = (20, 30)
    mod = L.compute_learned_flood(_fake(shape), _rasters(shape), shape)
    ctx = {"hydro_rasters": {"status": "available"}, "learned_inputs": {"status": "available"}}
    v = {"learned_flood": "passed"}
    others = {h: {"aoi_mean_score": None, "status": "insufficient_evidence"} for h in H.HAZARDS}
    out = H.hazard_outputs({**others, "learned_flood": mod}, MV, v,
                           has_waterways=False, ctx=ctx)["learned_flood"]
    assert out["validation_status"] == "validated"
    assert out["validated_scope"]["flood_types"] == ["fluvial", "waterlogging"]
    changed = {**mod, "model_sha256": "x"}
    out2 = H.hazard_outputs({**others, "learned_flood": changed}, MV, v,
                            has_waterways=False, ctx=ctx)["learned_flood"]
    assert out2["validation_status"] != "validated"


def test_input_stage_timeout_withholds_the_score():
    shape = (20, 30)
    mod = L.compute_learned_flood(None, _rasters(shape), shape)
    ctx = {"hydro_rasters": {"status": "available"},
           "learned_inputs": {"status": "timeout", "error": "stage timed out"}}
    others = {h: {"aoi_mean_score": None, "status": "insufficient_evidence"} for h in H.HAZARDS}
    out = H.hazard_outputs({**others, "learned_flood": mod}, MV,
                           {"learned_flood": "passed"}, has_waterways=False, ctx=ctx)["learned_flood"]
    assert out["status"] == "timeout" and out.get("value") is None


def test_failed_types_are_not_in_the_validated_scope():
    sc = C.VALIDATED_CONFIGS["learned_flood"]["scope"]
    assert set(sc["flood_types"]) == {"fluvial", "waterlogging"}
    for t in ("pluvial", "flash flood", "coastal", "compound"):
        assert t in sc["note"]
    hv = json.load(open(C.FLOOD_FINAL_HELDOUT_RESULT))["verdicts"]
    assert {t for t, v in hv.items() if v.get("verdict") == "passed"} == set(sc["flood_types"])
    assert hashlib.sha256(open(C.FLOOD_FINAL_HELDOUT_RESULT, "rb").read()).hexdigest() \
        == C.FLOOD_FINAL_HELDOUT_SHA256


def test_percentile_map_keeps_nodata_and_spans_zero_to_one():
    m = np.array([[0.1, np.nan], [0.3, 0.2]], np.float32)
    p = H.percentile_map(m)
    assert np.isnan(p[0, 1])
    assert p[0, 0] == 0.0 and p[1, 0] == 1.0 and p[1, 1] == 0.5


def test_pipeline_emits_the_learned_output_and_its_percentile_map():
    from tests import analysis_synth as S
    r, _ = S.run()
    o = r["outputs"]["susceptibility"]["learned_flood"]
    assert o["status"] == "available" and o["validation_status"] == "validated"
    assert o["flood_types"] == ["M1", "M3"]
    assert o["map"]["rendered_as"] == "within-AOI percentile of the learned score"
    assert o["not_assessed"]["built_up_cells"] > 0
