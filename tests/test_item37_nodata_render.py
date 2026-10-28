"""Item 37 (C22): no-data must not collide with real values. It has its own
render state (transparent), carried from the ingestion observation mask to
the rendered map, and is never a colour on the susceptibility scale."""
import io

import numpy as np
from PIL import Image

from analysis.rasters import NODATA_RENDER, TIER_COLOURS, legend, render_rgba
from tests import analysis_synth as S


def test_nodata_is_transparent_and_zero_is_a_tier_colour():
    rgba = render_rgba(np.array([[np.nan, 0.0, 0.99, 1.0]]))
    assert tuple(rgba[0, 0]) == (0, 0, 0, 0)
    assert tuple(rgba[0, 1]) == (*TIER_COLOURS["very_low"], 255)
    assert tuple(rgba[0, 2]) == (*TIER_COLOURS["very_high"], 255)
    assert tuple(rgba[0, 3]) == (*TIER_COLOURS["very_high"], 255)


def test_nodata_state_is_not_any_tier():
    lg = legend()
    tiers = {tuple(t["rgba"]) for t in lg["tiers"]}
    assert tuple(lg["nodata"]["rgba"]) not in tiers
    assert lg["nodata"]["rgba"][3] == 0 and all(t["rgba"][3] == 255 for t in lg["tiers"])
    assert NODATA_RENDER["label"] == lg["nodata"]["label"]


def test_the_mask_travels_from_ingestion_to_the_rendered_map():
    """The synthetic composite's top-left corner has no clear observation.
    It must be NaN in the pluvial map and transparent in the PNG, and every
    observed cell must be opaque."""
    r, _ = S.run()
    png = r["_maps"]["pluvial_susceptibility"]
    meta = r["maps"]["pluvial_susceptibility"]
    img = np.asarray(Image.open(io.BytesIO(png)))
    assert img.shape == (*meta["shape"], 4)
    alpha = img[..., 3]
    assert (alpha == 0).sum() == meta["nodata_cells"] > 0
    assert alpha[0, 0] == 0                              # the unobserved corner
    assert (alpha[alpha > 0] == 255).all()
    assert r["outputs"]["susceptibility"]["pluvial"]["map"]["nodata_render"] == "alpha 0 (transparent)"


def test_stored_map_is_served_publicly(tmp_path, monkeypatch):
    import api
    from analysis.fractions import StandInFractions
    import analysis.run as R
    monkeypatch.setattr(api, "RESULTS_ROOT", tmp_path)
    monkeypatch.setattr(R, "_default_deps", lambda: S.deps())
    monkeypatch.setattr(StandInFractions, "fetch_composite", S.SynthProducer.fetch_composite)
    monkeypatch.setattr(StandInFractions, "unobserved_all", False, raising=False)
    from fastapi.testclient import TestClient
    c = TestClient(api.app)
    b = S.BBOX
    rid = c.post("/api/analyze", headers={"X-API-Key": api.API_KEY},
                 json={"west": b[0], "south": b[1], "east": b[2], "north": b[3],
                       "start_date": "2026-01-01", "end_date": "2026-03-31"}).json()["result_id"]
    m = c.get(f"/api/results/{rid}/maps/pluvial_susceptibility")
    assert m.status_code == 200 and m.headers["content-type"] == "image/png"
    assert np.asarray(Image.open(io.BytesIO(m.content)))[0, 0, 3] == 0
    assert c.get(f"/api/results/{rid}/maps/nope").status_code == 404
    assert c.get(f"/api/results/{rid}/maps/BAD-name").status_code == 400
    assert "_maps" not in c.get(f"/api/results/{rid}").json()
