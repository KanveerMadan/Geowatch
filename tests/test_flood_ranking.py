"""River/waterlogging elevation ranking (susceptibility/flood_ranking.py),
which replaced the learned output on 2026-11-22: score, masks, label."""
import numpy as np

from analysis import contract as C
from analysis import hazards as H
from susceptibility import flood_ranking as R
from tests.analysis_synth import fake_ranking_inputs
from tests.test_flood_taxonomy import MV

SHAPE = (20, 30)


def _inp(**arrays):
    r = fake_ranking_inputs(None, SHAPE, "EPSG:32631", 2025, "t")
    r["arrays"].update(arrays)
    return r


def test_score_is_minus_elevation_so_lower_ground_ranks_higher():
    out = R.compute_flood_ranking(_inp(), SHAPE)
    smap, dem = out["susceptibility_map"], _inp()["arrays"]["dem_glo30"]
    ok = np.isfinite(smap)
    assert np.allclose(smap[ok], -dem[ok])
    assert np.nanmean(smap[:, :3]) > np.nanmean(smap[:, 10:15])
    assert out["method"] == "glo30_elevation_rank"


def test_built_up_permanent_water_and_no_terrain_are_not_assessed():
    occ = np.zeros(SHAPE)
    occ[0, 0] = 95.0
    dem = np.tile(np.linspace(5.0, 40.0, SHAPE[1]), (SHAPE[0], 1))
    dem[5, 5] = np.nan
    out = R.compute_flood_ranking(_inp(jrc_occurrence=occ, dem_glo30=dem), SHAPE)
    smap = out["susceptibility_map"]
    assert np.isnan(smap[:, 15:]).all() and np.isnan(smap[0, 0]) and np.isnan(smap[5, 5])
    assert out["not_assessed"]["built_up_cells"] == 20 * 15
    assert out["not_assessed"]["permanent_water_cells"] == 1


def test_failed_or_empty_inputs_give_no_score_never_zero():
    assert R.compute_flood_ranking(None, SHAPE)["aoi_mean_score"] is None
    nodem = _inp(dem_glo30=np.full(SHAPE, np.nan))
    out = R.compute_flood_ranking(nodem, SHAPE)
    assert out["status"] == "insufficient_evidence" and out["aoi_mean_score"] is None


def test_label_is_experimental_never_validated():
    mod = R.compute_flood_ranking(_inp(), SHAPE)
    ctx = {"ranking_inputs": {"status": "available"}}
    others = {h: {"aoi_mean_score": None, "status": "insufficient_evidence"} for h in H.HAZARDS}
    for verdict in (None, "passed"):            # even a stray verdict cannot validate it
        out = H.hazard_outputs({**others, "flood_ranking": mod}, MV, {"flood_ranking": verdict},
                               has_waterways=False, ctx=ctx)["flood_ranking"]
        assert out["validation_status"] == "experimental"
        assert out["validated_scope"] is None
    assert "flood_ranking" not in C.VALIDATED_CONFIGS


def test_input_stage_timeout_withholds_the_score():
    mod = R.compute_flood_ranking(None, SHAPE)
    ctx = {"ranking_inputs": {"status": "timeout", "error": "stage timed out"}}
    others = {h: {"aoi_mean_score": None, "status": "insufficient_evidence"} for h in H.HAZARDS}
    out = H.hazard_outputs({**others, "flood_ranking": mod}, MV, {}, has_waterways=False,
                           ctx=ctx)["flood_ranking"]
    assert out["status"] == "timeout" and out.get("value") is None


def test_pipeline_emits_the_ranking_and_its_percentile_map():
    from tests import analysis_synth as S
    r, _ = S.run()
    o = r["outputs"]["susceptibility"]["flood_ranking"]
    assert o["status"] == "available" and o["validation_status"] == "experimental"
    assert o["flood_types"] == ["M1", "M3"]
    assert o["method"] == "glo30_elevation_rank"
    assert o["map"]["rendered_as"] == "within-AOI percentile of minus the GLO-30 elevation"
    assert o["not_assessed"]["built_up_cells"] > 0
    assert "learned_flood" not in r["outputs"]["susceptibility"]
