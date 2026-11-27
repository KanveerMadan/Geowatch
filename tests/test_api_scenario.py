"""POST /api/scenario (flood round 5): auth, validation, and a run on injected terrain (no EE)."""
import numpy as np
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_module():
    import api
    return api


def test_requires_api_key(api_module):
    r = TestClient(api_module.app).post("/api/scenario", json={"kind": "debris_flow_glof", "west": 0, "south": 0,
                                                               "east": 0.01, "north": 0.01, "volume_m3": 1e6})
    assert r.status_code in (401, 403)


@pytest.mark.parametrize("body,needle", [
    ({"kind": "snowmelt_ice_jam", "volume_m3": 1e6}, "kind must be"),
    ({"kind": "embankment_dam_breach", "volume_m3": 1e6}, "dam needs its height"),
    ({"kind": "debris_flow_glof", "volume_m3": -5}, "positive volume"),
])
def test_validation(api_module, body, needle):
    c = TestClient(api_module.app, headers={api_module.API_KEY_HEADER_NAME: api_module.API_KEY})
    r = c.post("/api/scenario", json={"west": 0, "south": 0, "east": 0.01, "north": 0.01, **body})
    assert r.status_code == 400 and needle in r.text


def test_run_scenario_on_fixture(api_module):
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("tfm", pathlib.Path(__file__).with_name("test_flood_m678.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    rasters = m.rasters
    req = api_module.ScenarioRequest(kind="embankment_dam_breach", west=0, south=0, east=0.01, north=0.01,
                                     volume_m3=5e7, height_m=20)
    out = api_module.run_scenario(req, fetch=lambda *a, **k: rasters())
    assert out["validation_status"] == "scenario" and "not validated" in out["label_text"]
    assert out["depth_m"]["max"] == pytest.approx(out["stage_m"], rel=0.02)
    assert np.isfinite(out["peak_flow_m3s"])
