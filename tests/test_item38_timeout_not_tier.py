"""Item 38 (C27): a timeout produces status "timeout", never a tier.
Acceptance: two runs of the same wards give identical tiers, or explicitly
differing `status` fields explaining why."""
import pytest
from shapely.geometry import box

import zonal.hazard_screening as Z
from analysis import stages
from analysis.wards import materialize, ward_context
from tests import analysis_synth as S

HAND = {"status": "available", "mean_hnd_m": 3.0, "min_hnd_m": 0.0, "max_hnd_m": 9.0,
        "river_connectivity": True, "max_upstream_area_km2": 20.0, "buffer_km": 5}
RAIN = {"status": "available", "mean_annual_mm": 2200.0}


@pytest.fixture
def ward_sources(monkeypatch):
    monkeypatch.setattr(Z, "get_merit_hand_context", lambda *a: dict(HAND))
    monkeypatch.setattr(Z, "get_fabdem_elevation_stats",
                        lambda *a: {"status": "available", "mean_elevation_m": 8.0})
    monkeypatch.setattr(Z, "get_coastline_context",
                        lambda *a: {"status": "available", "distance_km": 1.0,
                                    "coastal_connectivity": True})
    # item 26 Phase 1a: fluvial and flash flood read per-pixel rasters
    monkeypatch.setattr(Z, "fetch_hydro_rasters",
                        lambda bbox, t, shape, crs, year, rainfall=True:
                        S.fake_hydro_rasters(bbox, t, shape, crs, year))
    real = Z._call_with_timeout
    timeouts = set()

    def call(func, *a, **k):
        if func.__name__ in timeouts or getattr(func, "_name", None) in timeouts:
            raise TimeoutError(f"{func.__name__}() did not return within 90s")
        return real(func, *a, **k)
    monkeypatch.setattr(Z, "_call_with_timeout", call)
    return timeouts


def _ward():
    return Z.compute_ward_hazard_screening(1, "G/N", box(72.84, 19.04, 72.85, 19.05), dict(RAIN))


def _consistent(a, b):
    """The acceptance: same tier, or statuses that differ and say why."""
    for h in ("fluvial", "coastal", "flash_flood"):
        x, y = a["hazards"][h], b["hazards"][h]
        assert x["tier"] == y["tier"] or (x["status"] != y["status"] and
                                          "timeout" in (x["status"], y["status"])), h


def test_ward_timeout_is_a_status_not_a_tier(ward_sources):
    clean = _ward()
    ward_sources.add("<lambda>")            # every source is a lambda here: time out all
    timed = _ward()
    for h in ("fluvial", "coastal", "flash_flood"):
        b = timed["hazards"][h]
        assert b["status"] == "timeout" and b["tier"] is None and b["score"] is None, h
        assert "timed out" in b["error"]
    _consistent(clean, timed)


def test_partial_timeout_cannot_mint_a_different_tier(ward_sources, monkeypatch):
    """The per-pixel rasters alone time out (item 26 Phase 1a: they are
    fluvial's and flash flood's only scored input). Neither may emit a tier;
    coastal, which does not read them, keeps the clean run's tier."""
    clean = _ward()
    monkeypatch.setattr(Z, "fetch_hydro_rasters", _named(lambda *a, **k: None, "slow_rasters"))
    ward_sources.add("slow_rasters")
    timed = _ward()
    for h in ("fluvial", "flash_flood"):
        b = timed["hazards"][h]
        assert b["status"] == "timeout" and b["tier"] is None, h
        assert b["timed_out_inputs"] == ["hydro_rasters"], h
    assert timed["hazards"]["coastal"]["tier"] == clean["hazards"]["coastal"]["tier"]
    _consistent(clean, timed)


def test_unavailable_input_keeps_its_error_at_the_ward_boundary(ward_sources, monkeypatch):
    monkeypatch.setattr(Z, "get_merit_hand_context",
                        lambda *a: {"status": "unavailable", "error": "no MERIT tiles"})
    fl = _ward()["hazards"]["fluvial"]
    assert fl["input_status"]["merit_hand"] == {"status": "unavailable", "error": "no MERIT tiles"}
    assert fl["status"] != "timeout"


def _named(fn, name):
    fn.__name__ = name
    return fn


# ── the analysis pipeline ──

def test_pipeline_context_timeout_is_a_status_everywhere(monkeypatch):
    """Item 26 Phase 1a: fluvial, flash flood and waterlogging read the
    per-pixel hydro_rasters stage; its timeout withholds all three -- and,
    since flood round 4, pluvial too (its design storm is a raster layer)."""
    import time
    monkeypatch.setitem(stages.STAGE_TIMEOUT_S, "hydro_rasters", 0.3)

    def slow(*a):
        time.sleep(2.0)
        return S.fake_hydro_rasters(*a)
    r, units = S.run(deps=S.deps(fetch_hydro_rasters=slow))
    s = r["outputs"]["susceptibility"]
    for h in ("fluvial", "flash_flood", "waterlogging", "pluvial"):
        assert s[h]["status"] == "timeout" and s[h]["value"] is None and s[h]["tier"] is None, h
        assert s[h]["incomplete_inputs"]["hydro_rasters"]["status"] == "timeout"
    assert s["coastal"]["status"] == "available"
    assert r["stages"]["hydro_rasters"]["status"] == "timeout"
    ctx = ward_context(r)
    for t, b in units.items():
        m = materialize(b["units"][0], t, ctx)
        assert m["outputs"]["susceptibility"]["fluvial"]["status"] == "timeout"
        assert m["outputs"]["susceptibility"]["fluvial"]["tier"] is None


def test_pipeline_dem_timeout_withholds_pluvial_and_its_units(monkeypatch):
    import time
    monkeypatch.setitem(stages.STAGE_TIMEOUT_S, "dem", 0.3)

    def slow_dem(*a):
        time.sleep(2.0)
    r, units = S.run(deps=S.deps(fetch_dem=slow_dem))
    p = r["outputs"]["susceptibility"]["pluvial"]
    assert p["status"] == "timeout" and p["tier"] is None and "map" not in p
    ctx = ward_context(r)
    u = materialize(units["grid"]["units"][0], "grid", ctx)
    assert u["outputs"]["susceptibility"]["pluvial"]["status"] == "timeout"


def test_two_runs_identical_tiers_or_explicit_status(monkeypatch):
    a, _ = S.run()
    monkeypatch.setitem(stages.STAGE_TIMEOUT_S, "context", 0.3)
    b, _ = S.run(deps=S.deps(context_fns=S.context_fns({"slope": S.sleeper(2.0)})))
    for h, x in a["outputs"]["susceptibility"].items():
        y = b["outputs"]["susceptibility"][h]
        assert x["tier"] == y["tier"] or (y["status"] == "timeout" and y["tier"] is None), h
