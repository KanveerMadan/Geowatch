"""Phase 4 Step B: what the Flood and Change tabs draw.

Every flood type with a per-pixel map has a stored map and per-unit values
(not only pluvial); coastal stays an AOI-wide scalar and says so. Change
verdicts are stored per cell on change's own grid. The swipe's imagery is a
cached picture; the boundary list tells the UI where wards exist."""
import json

import numpy as np
import pytest

from analysis import contract as C
from analysis.wards import HAZARDS, change_cells, materialize, spatial_hazards, ward_context
from tests import analysis_synth as S

SPATIAL = ("pluvial", "fluvial", "flash_flood", "waterlogging")


@pytest.fixture(scope="module")
def run():
    return S.run()


def test_the_five_modules_share_one_set_of_tier_breaks():
    from configs import (coastal_constants, flash_flood_constants, fluvial_constants,
                         pluvial_constants, waterlogging_constants)
    ref = pluvial_constants.SUSCEPTIBILITY_CLASS_BREAKS
    assert fluvial_constants.FLUVIAL_CLASS_BREAKS == ref
    assert flash_flood_constants.FLASH_FLOOD_CLASS_BREAKS == ref
    assert waterlogging_constants.WATERLOGGING_CLASS_BREAKS == ref
    assert coastal_constants.COASTAL_CLASS_BREAKS == ref


def test_every_per_pixel_flood_type_has_a_map_and_unit_values(run):
    result, units = run
    s = result["outputs"]["susceptibility"]
    for h in SPATIAL:
        assert s[h]["per_unit"] is True, h
        assert f"{h}_susceptibility" in result["maps"] and f"{h}_susceptibility" in result["_maps"]
        if s[h]["status"] == "available":
            assert s[h]["map"]["url_path"] == f"maps/{h}_susceptibility"
    assert "per_unit" not in s["coastal"] and "map" not in s["coastal"]
    assert spatial_hazards(result) == SPATIAL
    ctx = ward_context(result)
    for t, b in units.items():
        m = materialize(b["units"][0], t, ctx)
        hz = m["outputs"]["susceptibility"]
        assert set(hz) == set(HAZARDS)
        for h in SPATIAL:
            assert hz[h]["spatial"] is True and hz[h]["validation_status"] == s[h]["validation_status"]
        assert hz["coastal"]["spatial"] is False
        assert "applied uniformly" in hz["coastal"]["coverage"]["basis"]


def test_unit_flood_values_vary_where_the_map_does(run):
    """The synthetic HAND rises west to east, so fluvial differs across grid
    units: a per-unit value, not the AOI scalar copied."""
    result, units = run
    ctx = ward_context(result)
    vals = {materialize(u, "grid", ctx)["outputs"]["susceptibility"]["fluvial"]["value"]
            for u in units["grid"]["units"]}
    assert len({v for v in vals if v is not None}) > 1


def test_features_carry_each_flood_type_null_where_not_measured(run, tmp_path):
    from analysis.wards import feature
    result, units = run
    ctx = ward_context(result)
    for u in units["grid"]["units"]:
        p = feature(u, ctx)["properties"]
        for h in SPATIAL:
            v, st = p[f"flood_{h}"], p[f"flood_{h}_status"]
            assert (v is None) == (st != "available"), (h, v, st)
            if v is None:
                assert st in C.ABSENT
        assert "flood_coastal" not in p


def test_a_result_stored_before_step_b_still_materializes(run):
    """Old results have no per_unit flag and only pluvial in their units."""
    result, units = run
    old = json.loads(json.dumps({k: v for k, v in result.items() if not k.startswith("_")}))
    for h in HAZARDS:
        old["outputs"]["susceptibility"][h].pop("per_unit", None)
    assert spatial_hazards(old) == ("pluvial",)
    ctx = ward_context(old)
    u = {k: v for k, v in units["grid"]["units"][0].items()
         if not k.endswith("_susceptibility") or k == "pluvial_susceptibility"}
    hz = materialize(u, "grid", ctx)["outputs"]["susceptibility"]
    assert hz["pluvial"]["spatial"] is True and hz["fluvial"]["spatial"] is False


# ── change cells ──

def test_change_cells_name_a_verdict_per_fraction(run):
    cells = run[0]["_change_cells"]
    assert cells["status"] == "available" and cells["grid_cell_m"] == 100.0
    assert set(cells["fractions"]) == {"built", "vegetation", "water"}
    seen = set()
    for c in cells["cells"]:
        assert c["geometry"]["type"] in ("Polygon", "MultiPolygon")
        for f in cells["fractions"]:
            seen.add(c[f])
            judged = c[f] in ("increase", "decrease", "no_detectable_change")
            assert (c[f"{f}_delta"] is not None) == judged
    assert {"increase", "decrease"} <= seen


def test_change_cells_without_a_change_stage_are_unavailable():
    assert change_cells(S.synth_layer(), None)["status"] == "unavailable"
    assert change_cells(S.synth_layer(), {"fractions": {}})["cells"] == []


def test_unjudged_cells_carry_no_delta():
    from vector import change, fractions, units
    layer = S.synth_layer()
    n = len(units.grid_units(layer, fractions.grid_for(layer)[0]))
    r = change.detect("water", np.zeros(n), np.ones(n), np.zeros(n), np.ones(n), 0.05)
    c = change_cells(layer, {"fractions": {"water": r}})
    assert all(x["water"] == "insufficient_observation" and x["water_delta"] is None
               for x in c["cells"])


def test_change_cells_that_do_not_match_the_grid_are_refused():
    r = {"units": [{"status": "increase", "delta": 0.5}]}
    assert change_cells(S.synth_layer(), {"fractions": {"built": r}})["status"] == "unavailable"


# ── API ──

@pytest.fixture
def client(tmp_path, monkeypatch):
    import api
    import analysis.run as R
    from analysis.fractions import StandInFractions
    monkeypatch.setattr(api, "RESULTS_ROOT", tmp_path / "results")
    monkeypatch.setattr(api, "IMAGERY_ROOT", tmp_path / "imagery")
    monkeypatch.setattr(api, "BOUNDARY_ROOT", tmp_path / "boundaries")
    monkeypatch.setattr(R, "_default_deps", lambda: S.deps())
    monkeypatch.setattr(StandInFractions, "fetch_composite", S.SynthProducer.fetch_composite)
    monkeypatch.setattr(StandInFractions, "unobserved_all", False, raising=False)
    from fastapi.testclient import TestClient
    return TestClient(api.app)


def _h():
    import api
    return {"X-API-Key": api.API_KEY}


REQ = {"west": S.BBOX[0], "south": S.BBOX[1], "east": S.BBOX[2], "north": S.BBOX[3],
       "start_date": S.WINDOW["start"], "end_date": S.WINDOW["end"], "aoi_label": "synth"}


def test_api_serves_every_flood_map_and_the_change_cells(client):
    rid = client.post("/api/analyze", json=REQ, headers=_h()).json()["result_id"]
    for h in SPATIAL:
        r = client.get(f"/api/results/{rid}/maps/{h}_susceptibility")       # public
        assert r.status_code == 200 and r.headers["content-type"] == "image/png", h
    fc = client.get(f"/api/results/{rid}/features/grid").json()
    assert all(f"flood_{h}" in fc["features"][0]["properties"] for h in SPATIAL)
    ch = client.get(f"/api/results/{rid}/change/features")                   # public
    assert ch.status_code == 200
    ch = ch.json()
    assert ch["type"] == "FeatureCollection" and ch["features"]
    assert "change_cells" not in client.get(f"/api/results/{rid}").json()
    assert "_change_cells" not in client.get(f"/api/results/{rid}").json()
    # change cells are not a unit type
    assert client.get(f"/api/results/{rid}/features/change").status_code == 404


def test_imagery_is_protected_cached_and_honest_about_gaps(client, monkeypatch):
    from analysis import imagery
    rid = client.post("/api/analyze", json=REQ, headers=_h()).json()["result_id"]
    calls = []

    def fake_fetch(bbox, start, end):
        calls.append((start, end))
        return (None, 0) if start.startswith("2019") else (b"\x89PNG fake", 3)

    monkeypatch.setattr(imagery, "fetch_png", fake_fetch)
    assert client.get(f"/api/imagery/{rid}").status_code == 401
    info = client.get(f"/api/imagery/{rid}", headers=_h()).json()
    end_year = int(S.WINDOW["end"][:4])
    assert info["years"][0] == imagery.FIRST_YEAR and info["years"][-1] == end_year
    assert info["compared"][1] == end_year
    y = info["years"][-1]
    a = client.get(f"/api/imagery/{rid}/{y}", headers=_h())
    b = client.get(f"/api/imagery/{rid}/{y}", headers=_h())
    assert a.status_code == b.status_code == 200 and a.content == b"\x89PNG fake"
    assert len(calls) == 1                                       # served from the cache
    assert calls[0][1][:4] == str(y)
    gap = client.get(f"/api/imagery/{rid}/2019", headers=_h())
    assert gap.status_code == 404 and "no Sentinel-2 scene" in gap.json()["detail"]
    assert client.get(f"/api/imagery/{rid}/2019", headers=_h()).status_code == 404
    assert len(calls) == 2                                       # the gap is cached too
    assert client.get(f"/api/imagery/{rid}/1990", headers=_h()).status_code == 400


def test_window_in_moves_the_calendar_window():
    from analysis.imagery import window_in
    w = {"start": "2026-07-30", "end": "2026-10-28"}
    assert window_in(w, 2021) == ("2021-07-30", "2021-10-28")
    assert window_in({"start": "2023-12-01", "end": "2024-02-29"}, 2022) == ("2021-12-01", "2022-02-28")


def test_boundary_layers_are_listed_with_their_extent(client, tmp_path):
    d = tmp_path / "boundaries" / "test_wards"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps({"name": "Test wards", "unit_type": "ward",
                                                 "feature_count": 1}))
    (d / "boundary.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [
            [[72.8, 18.9], [72.9, 18.9], [72.9, 19.0], [72.8, 19.0], [72.8, 18.9]]]}}]}))
    assert client.get("/api/boundaries").status_code == 401
    b = client.get("/api/boundaries", headers=_h()).json()["boundaries"]
    assert b == [{"boundary_layer_id": "test_wards", "name": "Test wards", "unit_type": "ward",
                  "feature_count": 1, "bbox": [72.8, 18.9, 72.9, 19.0]}]
