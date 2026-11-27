"""Flood round 5 (M6-M8) product module on fixture grids: no Earth Engine login needed."""
import numpy as np
import pytest

from configs import m678_constants as K
from ingestion import m678_context as MC
from susceptibility import conditional_flood as CF


def rasters(n=40, river_col=20, slope=0.5, nan_frac=0.0, seed=0):
    """A valley: elevation rises away from a trunk river column; one side tributary."""
    rng = np.random.default_rng(seed)
    c = np.arange(n)[None, :].repeat(n, 0)
    r = np.arange(n)[:, None].repeat(n, 1)
    elev = 100 + slope * np.abs(c - river_col) + 0.05 * r + rng.normal(0, 0.01, (n, n))
    upa = np.full((n, n), 0.5)
    upa[:, river_col] = 500.0 + r[:, 0]            # trunk
    hand = np.abs(c - river_col) * slope
    if n > 10:
        upa[10, :5] = 20.0                         # a side stream far up the slope
        hand[10, :5] = 0.0                         # HAND drains the side stream too
    lay = {"elev_m": elev, "upa_km2": upa, "hand_m": hand}
    if nan_frac:
        m = rng.random((n, n)) < nan_frac
        for v in lay.values():
            v[m] = np.nan
    return {"status": "available", "layers": {k: {"raster": v, "source": "fixture", "method": "synthetic",
                                                  "validation_status": "experimental"} for k, v in lay.items()}}


CTX = {"glacial_lakes": {"count_within_km": 2}, "snow": {"snow_days_per_year": 120.0}}


@pytest.mark.parametrize("kind", CF.KINDS)
def test_computed_map_is_a_percentile(kind):
    out = CF.compute(kind, rasters(), CTX)
    assert out["status"] == "computed"
    m = out["susceptibility_map"]
    assert np.nanmin(m) == 0.0 and np.nanmax(m) == 1.0
    assert out["flood_type"] == K.FLOOD_TYPE_ID[kind]
    assert out["validation_status"] in ("experimental", "validated")
    assert any("does not" in s or "not" in s for s in out["limitations"])


def test_no_lake_is_absent_not_zero():
    out = CF.compute("debris_flow_glof", rasters(), {"glacial_lakes": {"count_within_km": 0}})
    assert out["status"] == "not_applicable"
    assert out["aoi_mean_score"] is None and out["susceptibility_map"] is None
    assert "not a zero risk" in out["reason"]


def test_unknown_context_is_not_a_zero_either():
    for kind in ("debris_flow_glof", "snowmelt_ice_jam"):
        out = CF.compute(kind, rasters(), {})
        assert out["status"] == "not_applicable" and out["aoi_mean_score"] is None
        assert "not checked" in out["reason"]


def test_snow_rare_is_absent():
    out = CF.compute("snowmelt_ice_jam", rasters(), {"snow": {"snow_days_per_year": 3.0}})
    assert out["status"] == "not_applicable" and "rare" in out["reason"]


def test_missing_rasters_insufficient_evidence():
    out = CF.compute("embankment_dam_breach", None, CTX)
    assert out["status"] == "insufficient_evidence" and out["susceptibility_map"] is None


def test_partial_nodata_kept_as_nan():
    out = CF.compute("embankment_dam_breach", rasters(nan_frac=0.2), CTX)
    m = out["susceptibility_map"]
    assert np.isnan(m).mean() == pytest.approx(0.2, abs=0.05) and np.isfinite(m).any()


def test_tiny_box():
    out = CF.compute("embankment_dam_breach", rasters(n=2, river_col=1), CTX)
    assert out["status"] == "computed"


def test_trunk_height_ignores_side_stream():
    h, d = CF.trunk_height(rasters()["layers"]["elev_m"]["raster"], rasters()["layers"]["upa_km2"]["raster"])
    assert h[10, 0] > 5.0                           # high above the trunk, though HAND is 0 there
    assert abs(h[5, 20]) < 1e-6 and d[5, 20] == 0


def test_no_trunk_channel():
    r = rasters()
    r["layers"]["upa_km2"]["raster"][:] = 1.0       # below MIN_TRUNK_UPA_KM2
    assert CF.trunk_height(r["layers"]["elev_m"]["raster"], r["layers"]["upa_km2"]["raster"]) == (None, None)
    assert CF.score_map("phys_main", r) is None


def test_steep_flat_terrain_still_ranks():
    for slope in (0.0, 30.0):
        out = CF.compute("embankment_dam_breach", rasters(slope=slope), CTX)
        assert out["status"] == "computed"


def test_scenario_is_labelled_and_physical():
    r = rasters()
    s = CF.scenario_depth("embankment_dam_breach", r, volume_m3=5e7, height_m=20)
    assert s["validation_status"] == "scenario"
    assert s["peak_flow_m3s"] == pytest.approx(0.607 * 5e7 ** 0.295 * 20 ** 1.24, rel=1e-3)
    assert np.nanmax(s["depth_map_m"]) == pytest.approx(s["stage_m"], rel=1e-2)
    assert s["depth_map_m"][10, 0] == 0.0           # side stream high above the trunk stays dry
    g = CF.scenario_depth("debris_flow_glof", r, volume_m3=2e7)
    assert g["peak_flow_m3s"] == pytest.approx(1100 * 20 ** 0.44, rel=1e-3)
    with pytest.raises(ValueError):
        CF.peak_flow_m3s("embankment_dam_breach", 1e6)        # a dam needs its height
    with pytest.raises(ValueError):
        CF.peak_flow_m3s("snowmelt_ice_jam", 1e6)


def test_glacial_lake_context_offline():
    near = MC.glacial_lakes(-134.62, 58.38, -134.52, 58.46)      # Juneau / Mendenhall
    assert near["count_within_km"] > 0
    assert MC.glacial_lakes(-84.3, 43.55, -84.2, 43.62)["count_within_km"] == 0   # Midland
    polar = MC.glacial_lakes(20.0, 89.0, 21.0, 89.5)
    assert polar["status"] == "available"
    anti = MC.glacial_lakes(179.8, 51.0, 179.99, 51.1)
    assert anti["status"] == "available"


def test_haversine_across_antimeridian():
    assert MC._km(0, 179.9, 0, -179.9) == pytest.approx(22.2, abs=0.5)


def test_validation_label_comes_only_from_test_file(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "TEST_RESULT", str(tmp_path / "none.json"))
    assert K.validation_status("debris_flow_glof") == "experimental"
    p = tmp_path / "t.json"
    p.write_text('{"by_type": {"M7": {"verdict": "pass", "clusters": 5}, "M8": {"verdict": "too_few_events", "reason": "only 3"}}}')
    monkeypatch.setattr(K, "TEST_RESULT", str(p))
    assert K.validation_status("embankment_dam_breach") == "validated"
    assert K.validation_status("snowmelt_ice_jam") == "experimental"
    assert "only 3" in K.trust_note("snowmelt_ice_jam")
