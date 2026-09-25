"""
Item 21 Phase A, part 1 — input assembly.

No Earth Engine here: the grid arithmetic, local coverage rasterisation, OSM
geometry handling, the explicit-grid export switch and the read-boundary
checks are all tested on synthetic inputs. The live Dharavi run is the
smoke test, not a unit test.
"""
import pathlib
import sys

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine
from shapely.geometry import LineString, Polygon, box

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from ingestion import tiler
from ingestion.overpass import OverpassUnreachable
from surface_fractions import inputs, osm_layers
from surface_fractions.config import load_config
from surface_fractions.grid import (Grid, grid_from_bounds, line_touch,
                                    polygon_coverage, snap_bounds)

UTM = "EPSG:32643"


def _grid(w=4, h=3, x0=600000.0, y1=2100000.0):
    return Grid(crs=UTM, transform=(10.0, 0.0, x0, 0.0, -10.0, y1), width=w, height=h)


# ── grid arithmetic ──────────────────────────────────────────────────────────

def test_snap_bounds_expands_outward_to_lattice():
    assert snap_bounds(600003, 2099981, 600037, 2099999, 10, 600000, 2200020) == \
        (600000, 2099980, 600040, 2100000)


def test_snap_bounds_keeps_edges_already_on_lattice():
    assert snap_bounds(600000, 2099980, 600040, 2100000, 10, 0, 0) == \
        (600000, 2099980, 600040, 2100000)


def test_snap_bounds_respects_non_zero_origin():
    # S2 tile origins are multiples of 10 m, but the lattice must follow the
    # scene's origin rather than assume (0, 0).
    x0, y0, x1, y1 = snap_bounds(12.0, 12.0, 38.0, 38.0, 10, 5, 5)
    assert (x0, y0, x1, y1) == (5, 5, 45, 45)


def test_grid_from_bounds_shape_and_transform():
    g = grid_from_bounds(UTM, (600003, 2099981, 600037, 2099999), 10, 600000, 2200020)
    assert (g.width, g.height) == (4, 2)
    assert g.transform == (10, 0.0, 600000, 0.0, -10, 2100000)
    assert g.bounds == (600000, 2099980, 600040, 2100000)


# ── local coverage ───────────────────────────────────────────────────────────

def test_polygon_coverage_exact_fractions():
    g = _grid()
    # Left half of the top-left pixel, and all of the pixel to its right.
    geoms = [box(600000, 2099990, 600005, 2100000), box(600010, 2099990, 600020, 2100000)]
    cov = polygon_coverage(geoms, g)
    assert cov.shape == (3, 4)
    assert cov[0, 0] == pytest.approx(0.5)
    assert cov[0, 1] == pytest.approx(1.0)
    assert cov[1:].sum() == 0 and cov[0, 2:].sum() == 0


def test_polygon_coverage_overlaps_count_once():
    g = _grid()
    p = box(600000, 2099990, 600010, 2100000)
    assert polygon_coverage([p, p], g)[0, 0] == pytest.approx(1.0)


def test_polygon_coverage_empty_is_zero_array():
    assert polygon_coverage([], _grid()).sum() == 0


def test_line_touch_flags_touched_pixels_only():
    g = _grid()
    t = line_touch([LineString([(600001, 2099995), (600019, 2099995)])], g)
    assert t[0].tolist() == [1, 1, 0, 0]
    assert t[1:].sum() == 0


# ── OSM geometry ─────────────────────────────────────────────────────────────

def _pts(coords):
    return [{"lon": x, "lat": y} for x, y in coords]


SQUARE = [(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]


def test_closed_way_is_area_open_way_dropped_for_area_mode():
    els = [{"type": "way", "geometry": _pts(SQUARE)},
           {"type": "way", "geometry": _pts([(0, 0), (1, 1)])}]
    areas, lines = osm_layers.elements_to_geometries(els, "area")
    assert len(areas) == 1 and lines == []


def test_area_or_line_splits_closed_and_open():
    els = [{"type": "way", "geometry": _pts(SQUARE)},
           {"type": "way", "geometry": _pts([(0, 0), (1, 1)])}]
    areas, lines = osm_layers.elements_to_geometries(els, "area_or_line")
    assert len(areas) == 1 and len(lines) == 1


def test_multipolygon_relation_subtracts_inner_and_joins_split_outer():
    outer_a = _pts([(0, 0), (0, 4), (4, 4)])
    outer_b = _pts([(4, 4), (4, 0), (0, 0)])
    inner = _pts([(1, 1), (1, 2), (2, 2), (2, 1), (1, 1)])
    rel = {"type": "relation", "tags": {"type": "multipolygon"},
           "members": [{"type": "way", "role": "outer", "geometry": outer_a},
                       {"type": "way", "role": "outer", "geometry": outer_b},
                       {"type": "way", "role": "inner", "geometry": inner}]}
    areas, _ = osm_layers.elements_to_geometries([rel], "area")
    assert len(areas) == 1
    assert areas[0].area == pytest.approx(16 - 1)


def test_build_query_ors_filters_over_ways_and_relations():
    q = osm_layers.build_query(['["a"="b"]', '["c"="d"]'],
                               {"south": 1, "west": 2, "north": 3, "east": 4})
    assert q.count("way[") == 2 and q.count("relation[") == 2
    assert "(1,2,3,4)" in q and q.endswith("out geom;")


def test_no_producer_layer_has_no_array_not_zeros(tmp_path):
    spec = {"geometry": "area", "filters": [], "status": "no_producer"}
    fetched = osm_layers.fetch_layer("salt_flat", spec, {}, str(tmp_path),
                                     query_fn=lambda q: pytest.fail("queried"))
    out = osm_layers.rasterise_layer(fetched, spec, _grid())
    assert out["status"] == "no_producer" and out["area_fraction"] is None


def test_overpass_failure_is_unavailable_and_not_cached(tmp_path):
    spec = {"geometry": "area", "filters": ['["x"="y"]']}
    bbox = {"south": 0, "west": 0, "north": 1, "east": 1}

    def boom(q):
        raise OverpassUnreachable("all endpoints down")

    fetched = osm_layers.fetch_layer("park", spec, bbox, str(tmp_path), query_fn=boom)
    assert fetched["status"] == "unavailable" and "all endpoints down" in fetched["error"]
    assert list(tmp_path.iterdir()) == []
    out = osm_layers.rasterise_layer(fetched, spec, _grid())
    assert out["area_fraction"] is None and out["error"]


def test_available_layer_with_no_features_is_zeros_not_none(tmp_path):
    spec = {"geometry": "area", "filters": ['["x"="y"]']}
    bbox = {"south": 0, "west": 0, "north": 1, "east": 1}
    fetched = osm_layers.fetch_layer("park", spec, bbox, str(tmp_path), query_fn=lambda q: [])
    out = osm_layers.rasterise_layer(fetched, spec, _grid())
    assert out["status"] == "available"
    assert out["area_fraction"] is not None and out["area_fraction"].sum() == 0


def test_fetch_layer_uses_cache_on_second_call(tmp_path):
    spec = {"geometry": "area", "filters": ['["x"="y"]']}
    bbox = {"south": 0, "west": 0, "north": 1, "east": 1}
    calls = []
    osm_layers.fetch_layer("park", spec, bbox, str(tmp_path),
                           query_fn=lambda q: calls.append(q) or [])
    second = osm_layers.fetch_layer("park", spec, bbox, str(tmp_path),
                                    query_fn=lambda q: pytest.fail("not cached"))
    assert len(calls) == 1 and second["cached"]


def test_config_no_producer_groups_are_explicit():
    cfg = load_config()
    for name in ("salt_flat", "dry_lakebed"):
        assert cfg["osm_layers"][name]["status"] == "no_producer"
        assert cfg["osm_layers"][name]["filters"] == []
    assert cfg["footprints"]["open_buildings"]["min_confidence"] == 0.7


# ── export_image_local: explicit grid, default path unchanged ───────────────

class _FakeEEList:
    def __init__(self, v):
        self.v = v

    def getInfo(self):
        return self.v


class _FakeAOI:
    def __init__(self, coords):
        self.coords = coords

    def bounds(self, *a):
        return _FakeEEList({"coordinates": [self.coords]}) if not a else \
            _FakeEEList({"coordinates": [[[0, 0], [30, 0], [30, 20], [0, 20]]]})


class _FakeImage:
    def bandNames(self):
        return _FakeEEList(list(tiler.BAND_NAMES))


def _capture_export(monkeypatch, tmp_path):
    import geemap
    calls = []

    def fake_export(image, **kw):
        calls.append(kw)
        with rasterio.open(kw["filename"], "w", driver="GTiff", width=3, height=2,
                           count=6, dtype="float32", crs=UTM,
                           transform=Affine(10, 0, 0, 0, -10, 20)) as dst:
            dst.write(np.zeros((6, 2, 3), dtype="float32"))

    monkeypatch.setattr(geemap, "ee_export_image", fake_export)
    stamped = []
    real_stamp = tiler.stamp_band_descriptions
    monkeypatch.setattr(tiler, "stamp_band_descriptions",
                        lambda p, names=None: stamped.append(names) or real_stamp(p, names))
    return calls, stamped


def test_default_export_call_is_unchanged(monkeypatch, tmp_path):
    """The pre-Phase-A call, exactly: same kwargs, no crs, stamped with the
    default BAND_NAMES. Proves the default path is byte-identical."""
    calls, stamped = _capture_export(monkeypatch, tmp_path)
    aoi = _FakeAOI([[72.836, 19.037], [72.862, 19.037], [72.862, 19.06], [72.836, 19.06]])
    out = str(tmp_path / "raw.tif")
    tiler.export_image_local(_FakeImage(), aoi, out, scale=10)
    assert calls == [{"filename": out, "scale": 10, "region": aoi, "file_per_band": False}]
    assert stamped == [None]
    with rasterio.open(out) as src:
        assert list(src.descriptions) == list(tiler.BAND_NAMES)


def test_explicit_grid_export_passes_crs_and_transform(monkeypatch, tmp_path):
    calls, _ = _capture_export(monkeypatch, tmp_path)
    aoi = _FakeAOI(None)
    out = str(tmp_path / "stack.tif")
    tiler.export_image_local(_FakeImage(), aoi, out, crs=UTM,
                             crs_transform=[10, 0, 0, 0, -10, 20],
                             band_names=list(tiler.BAND_NAMES))
    assert calls == [{"filename": out, "crs": UTM, "crs_transform": [10, 0, 0, 0, -10, 20],
                      "region": aoi, "file_per_band": False}]
    assert "scale" not in calls[0]


def test_crs_without_transform_is_refused(tmp_path):
    with pytest.raises(ValueError, match="together"):
        tiler.export_image_local(_FakeImage(), None, str(tmp_path / "x.tif"), crs=UTM)


# ── read boundary ────────────────────────────────────────────────────────────

def _write_stack(path, grid, names, values=None, transform=None):
    data = values if values is not None else \
        np.ones((len(names), grid.height, grid.width), dtype="float32")
    with rasterio.open(path, "w", driver="GTiff", width=grid.width, height=grid.height,
                       count=len(names), dtype="float32", crs=grid.crs,
                       transform=Affine(*(transform or grid.transform))) as dst:
        dst.write(data)
        dst.descriptions = tuple(names)
    return str(path)


def test_read_stack_maps_nodata_to_nan(tmp_path):
    g = _grid()
    names = ["a", "b"]
    vals = np.ones((2, 3, 4), dtype="float32")
    vals[1, 0, 0] = inputs.NODATA
    got = inputs.read_stack(_write_stack(tmp_path / "s.tif", g, names, vals), g, names)
    assert np.isnan(got["b"][0, 0]) and np.isfinite(got["a"]).all()


def test_read_stack_refuses_shifted_grid(tmp_path):
    g = _grid()
    shifted = (10.0, 0.0, 600005.0, 0.0, -10.0, 2100000.0)
    path = _write_stack(tmp_path / "s.tif", g, ["a"], transform=shifted)
    with pytest.raises(inputs.GridMismatchError, match="transform"):
        inputs.read_stack(path, g, ["a"])


def test_read_stack_refuses_wrong_band_order(tmp_path):
    g = _grid()
    path = _write_stack(tmp_path / "s.tif", g, ["b", "a"])
    with pytest.raises(tiler.BandOrderError):
        inputs.read_stack(path, g, ["a", "b"])


def test_stack_band_list_is_complete_and_unique():
    assert len(set(inputs.STACK_BANDS)) == len(inputs.STACK_BANDS)
    assert inputs.STACK_BANDS[:6] == [f"s2_{b}" for b in tiler.BAND_NAMES]
    assert {"ob_cov", "ms_cov", "dem_elevation", "dem_slope_deg", "s2_observed"} <= \
        set(inputs.STACK_BANDS)
