"""
Build item 58, backend half — what the frontend needs is emitted, so the
frontend does not have to compute it.

The frontend held its own copy of the "unpaved highway" set
(UNPAVED_HIGHWAY_TYPES in App.jsx) to style roads.geojson, duplicating
osm_dem.py's set. That is the C31 shape: two copies of one rule drift
silently. roads.geojson now carries an `unpaved` property computed from the
backend's set, and the frontend reads it.

Overpass is stubbed. Nothing here touches the network.

Run from the repo root:  pytest tests/test_renderer_contract.py
"""

import json

import pytest

from ingestion import osm_dem


def _way(highway, lon0):
    return {"type": "way", "tags": {"highway": highway},
            "geometry": [{"lon": lon0, "lat": 19.04}, {"lon": lon0 + 0.001, "lat": 19.041}]}


@pytest.fixture
def roads_geojson(tmp_path, monkeypatch):
    import requests

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"elements": [_way("track", 72.84), _way("primary", 72.85),
                                 _way("steps", 72.855)]}

    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp())
    osm_dem.get_osm_features(72.836, 19.037, 72.862, 19.06, output_dir=str(tmp_path))
    return json.loads((tmp_path / "roads.geojson").read_text())


def test_roads_geojson_carries_unpaved_flag(roads_geojson):
    flags = {f["properties"]["highway"]: f["properties"]["unpaved"]
             for f in roads_geojson["features"]}
    assert flags == {"track": True, "primary": False, "steps": True}


def test_one_unpaved_set_in_the_backend():
    """The set used to style the map and the set used to label segments
    are the same object, so they cannot disagree."""
    assert osm_dem.UNPAVED_HIGHWAY_TYPES == frozenset({
        "track", "path", "footway", "bridleway",
        "unclassified", "service", "living_street", "steps",
    })
