"""
Item 26 Phase 1a, task 1: fluvial, flash flood and waterlogging are per-pixel
maps, not AOI-wide scalars. Method and constants pre-registered in
experiments/flood_validation/PREREGISTRATION_ROUND2.md.

Every test here fails on the old code: susceptibility.hydro_rasters did not
exist, and the three modules took scalar contexts and returned one number.
"""
import numpy as np
import pytest

from configs import flash_flood_constants as ffc
from configs import fluvial_constants as fc
from configs import waterlogging_constants as wc
from susceptibility import flash_flood, fluvial, hydro_rasters, waterlogging
from susceptibility.inputs import surface


def _rasters(shape=(2, 3), **values):
    layers = {k: surface(np.broadcast_to(np.asarray(v, dtype=float), shape).copy(), "test",
                         "test", "experimental") for k, v in values.items()}
    return {"status": "available", "shape": shape, "errors": {}, "layers": layers}


# ── the maps vary per pixel ────────────────────────────────────────────

def test_fluvial_map_follows_hand_per_pixel():
    r = _rasters(hand_m=[[0.0, 15.0, 30.0], [3.0, 6.0, np.nan]])
    out = fluvial.compute_fluvial_susceptibility(r)
    m = out["susceptibility_map"]
    assert m.shape == (2, 3)
    assert np.allclose(m[0], [1.0, 0.5, 0.0])
    assert np.isnan(m[1, 2])
    assert out["aoi_mean_score"] == pytest.approx(np.nanmean(m), abs=1e-4)


def test_flash_flood_reads_surrounding_relief_not_the_cells_own_slope():
    """A flat valley floor under steep ground must outscore the hillside:
    steepness is the relief_slope_deg neighbourhood mean, and slope_deg
    (the cell's own slope) is not an input at all."""
    r = _rasters(hand_m=[[1.0, 25.0, 1.0]], relief_slope_deg=[[15.0, 15.0, 0.0]],
                 slope_deg=[[0.5, 30.0, 0.5]], upa_near_km2=10.0, shape=(1, 3))
    m = flash_flood.compute_flash_flood_susceptibility(r)["susceptibility_map"][0]
    assert m[0] > m[1]          # valley floor beats the hillside
    assert m[0] > m[2]          # and steep surroundings beat flat surroundings
    r2 = _rasters(hand_m=[[1.0, 25.0, 1.0]], relief_slope_deg=[[15.0, 15.0, 0.0]],
                  slope_deg=0.0, upa_near_km2=10.0, shape=(1, 3))
    assert np.allclose(m, flash_flood.compute_flash_flood_susceptibility(r2)["susceptibility_map"][0])


def test_flash_flood_rainfall_is_intensity_not_annual_total():
    base = dict(hand_m=2.0, relief_slope_deg=5.0, upa_near_km2=10.0, shape=(1, 1))
    lo = flash_flood.compute_flash_flood_susceptibility(_rasters(rain_intensity_mm_h=2.0, **base))
    hi = flash_flood.compute_flash_flood_susceptibility(_rasters(rain_intensity_mm_h=18.0, **base))
    assert hi["aoi_mean_score"] > lo["aoi_mean_score"]
    wet = flash_flood.compute_flash_flood_susceptibility(
        _rasters(rain_intensity_mm_h=2.0, rain_annual_mm=4000.0, **base))
    assert wet["aoi_mean_score"] == lo["aoi_mean_score"]
    assert "rainfall_intensity" in hi["components_used"]


def test_flash_flood_without_intensity_records_why():
    r = _rasters(hand_m=2.0, relief_slope_deg=5.0, upa_near_km2=10.0, shape=(1, 1))
    r["errors"] = {"rain_intensity_mm_h": "EETimeout: too slow"}
    out = flash_flood.compute_flash_flood_susceptibility(r)
    assert out["status"] == "experimental"
    assert any("rainfall_intensity (unavailable: EETimeout" in e for e in out["components_excluded"])


def test_waterlogging_reads_impervious_per_cell():
    r = _rasters(hand_m=5.0, slope_deg=1.0, rain_annual_mm=2000.0, shape=(1, 2))
    imp = surface(np.array([[0.0, 0.7]]), "test footprints", "footprint_union_area_fraction",
                  "placeholder")
    out = waterlogging.compute_waterlogging_susceptibility(r, imp)
    m = out["susceptibility_map"][0]
    assert m[1] > m[0]
    assert out["validation_status"] == "placeholder"        # weakest input
    assert out["inputs"]["impervious"]["source"] == "test footprints"


def test_waterlogging_refuses_impervious_on_another_grid():
    r = _rasters(hand_m=5.0, shape=(2, 2))
    imp = surface(np.zeros((3, 3)), "t", "t", "placeholder")
    with pytest.raises(ValueError, match="grid"):
        waterlogging.compute_waterlogging_susceptibility(r, imp)


def test_waterlogging_without_impervious_is_experimental():
    out = waterlogging.compute_waterlogging_susceptibility(_rasters(hand_m=5.0, slope_deg=1.0))
    assert out["validation_status"] == "experimental"
    assert "impervious (unavailable)" in out["components_excluded"]


@pytest.mark.parametrize("fn", [
    lambda: fluvial.compute_fluvial_susceptibility(None),
    lambda: flash_flood.compute_flash_flood_susceptibility(None),
    lambda: waterlogging.compute_waterlogging_susceptibility(None),
    lambda: flash_flood.compute_flash_flood_susceptibility(_rasters(rain_intensity_mm_h=10.0)),
])
def test_no_spatial_input_is_insufficient_evidence(fn):
    out = fn()
    assert out["status"] == "insufficient_evidence"
    assert "aoi_mean_score" not in out


# ── the combiner ───────────────────────────────────────────────────────

def test_weighted_map_drops_nan_components_per_pixel():
    a, b = np.array([[1.0, np.nan]]), np.array([[0.0, 0.5]])
    m = hydro_rasters.weighted_map({"a": a, "b": b}, {"a": 3.0, "b": 1.0})
    assert np.allclose(m, [[0.75, 0.5]])


def test_weighted_map_zero_weight_is_ignored_and_all_zero_is_none():
    a = np.array([[1.0]])
    assert hydro_rasters.weighted_map({"a": a, "b": None}, {"a": 0.0, "b": 1.0}) is None


def test_utm_grid_covers_the_bbox_in_the_right_zone():
    t, (rows, cols), crs = hydro_rasters.utm_grid((72.836, 19.037, 72.862, 19.060))
    assert crs == "EPSG:32643"
    assert t.a == 30.0 and t.c % 30 == 0 and t.f % 30 == 0
    assert 85 <= rows <= 87 and 92 <= cols <= 96
    assert hydro_rasters.utm_grid((-0.44, 39.41, -0.40, 39.45))[2] == "EPSG:32630"
    assert hydro_rasters.utm_grid((34.83, -19.85, 34.87, -19.81))[2] == "EPSG:32736"


# ── Earth Engine calls carry a deadline; rainfall failure is contained ──

def test_compute_pixels_uses_a_hard_timeout(monkeypatch):
    seen = {}

    def fake_call(fn, timeout, retries, label):
        seen.update(timeout=timeout, retries=retries, label=label)
        return np.zeros((1, 1), dtype=[("hand_m", "f4")])

    import ee
    monkeypatch.setattr("ee_timeout.call", fake_call)
    monkeypatch.setattr(ee.data, "setDeadline", lambda ms: seen.update(deadline_ms=ms))

    class Img:
        def unmask(self, v): return self
        def toFloat(self): return self
    from rasterio.transform import from_origin
    out = hydro_rasters.compute_pixels(Img(), from_origin(0, 30, 30, 30), (1, 1), "EPSG:32643", "t")
    assert seen["timeout"] == hydro_rasters.EE_TIMEOUT_S
    assert seen["deadline_ms"] == hydro_rasters.EE_TIMEOUT_S * 1000
    assert out["hand_m"].shape == (1, 1)


def _fake_terrain(monkeypatch):
    def fake_pixels(img, transform, shape, crs, label):
        return {n: np.ones(shape) for n in ("hand_m", "upa_near_km2", "slope_deg",
                                             "relief_slope_deg")}
    monkeypatch.setattr(hydro_rasters, "compute_pixels", fake_pixels)
    monkeypatch.setattr(hydro_rasters, "_terrain_image", lambda bbox: None)
    monkeypatch.setattr(hydro_rasters, "_rain_images",
                        lambda year: {n: None for n in hydro_rasters.RAIN_LAYERS})
    monkeypatch.setattr("ingestion.gee_client.initialize_gee", lambda: None)


def test_rainfall_failure_loses_only_that_layer(monkeypatch):
    _fake_terrain(monkeypatch)

    def fake_rain(img, name, bbox, transform, shape, crs):
        if name == "rain_intensity_mm_h":
            raise TimeoutError("IMERG percentile too slow")
        return np.ones(shape)

    monkeypatch.setattr(hydro_rasters, "_rain_layer", fake_rain)
    out = hydro_rasters.fetch_hydro_rasters((0, 0, 1, 1), None, (2, 2), "EPSG:32631", 2024)
    assert set(out["layers"]) == set(hydro_rasters.LAYERS) - {"rain_intensity_mm_h"}
    assert "TimeoutError" in out["errors"]["rain_intensity_mm_h"]


def test_only_the_requested_rainfall_layers_are_fetched(monkeypatch):
    _fake_terrain(monkeypatch)
    asked = []
    monkeypatch.setattr(hydro_rasters, "_rain_layer",
                        lambda img, name, *a: asked.append(name) or np.ones((2, 2)))
    out = hydro_rasters.fetch_hydro_rasters((0, 0, 1, 1), None, (2, 2), "EPSG:32631", 2024,
                                            rainfall=("rain_intensity_mm_h",))
    assert asked == ["rain_intensity_mm_h"]
    assert out["errors"] == {"rain_annual_mm": "not requested"}


def test_rainfall_maps_nearest_from_its_native_grid():
    """A 30 m cell takes the value of the 0.1 deg cell its centre falls in."""
    bbox = (-0.44, 39.41, -0.40, 39.45)                    # Paiporta, straddles 39.4
    x0, y1, cols, rows = hydro_rasters.native_grid(bbox, 0.1)
    assert (round(x0, 6), round(y1, 6), cols, rows) == (-0.5, 39.5, 1, 1)
    # the native grid is sized from the hydrology grid's own footprint, which
    # reaches past the lon/lat bbox; every 30 m cell then gets a value
    t, shape, crs = hydro_rasters.utm_grid((-0.44, 39.35, -0.40, 39.45))
    x0, y1, cols, rows = hydro_rasters.native_grid(
        hydro_rasters.grid_lonlat_bounds(t, shape, crs), 0.1)
    assert (rows, cols) == (2, 2)                          # crosses 39.4 N and 0.4 W
    v = np.array([[5.0, 6.0], [7.0, 8.0]])
    out = hydro_rasters.nearest_from_native(v, x0, y1, 0.1, t, shape, crs)
    assert np.isfinite(out).all()
    assert set(np.unique(out)) == {5.0, 6.0, 7.0, 8.0}
    assert out[0, 0] == 5.0 and out[-1, 0] == 7.0 and out[0, -1] == 6.0


# ── the constants are the pre-registered ones ──────────────────────────

def test_constants_match_the_preregistration():
    assert fc.FLUVIAL_UPSTREAM_AREA_NORMALIZATION_MAX_KM2 == 10000.0
    assert fc.FLUVIAL_DRAINAGE_SEARCH_RADIUS_M == 1000.0
    assert ffc.FLASH_FLOOD_HAND_NORMALIZATION_MAX_M == 10.0
    assert ffc.FLASH_FLOOD_RELIEF_RADIUS_M == 1000.0
    assert ffc.FLASH_FLOOD_INTENSITY_PERCENTILE == 99.9
    assert ffc.FLASH_FLOOD_INTENSITY_NORMALIZATION_MAX_MM_H == 20.0
    assert wc.WATERLOGGING_SLOPE_NORMALIZATION_MAX_DEG == 5.0
    # the unchanged round-1 ceilings
    assert fc.HAND_NORMALIZATION_MAX_M == 30.0
    assert ffc.FLASH_FLOOD_SLOPE_NORMALIZATION_MAX_DEG == 15.0
    assert ffc.FLASH_FLOOD_SMALL_CATCHMENT_MAX_KM2 == 50.0
    assert wc.WATERLOGGING_HAND_NORMALIZATION_MAX_M == 15.0


def test_weight_grids_are_the_preregistered_ones():
    assert len(fc.FLUVIAL_WEIGHT_GRID) == 4
    assert len(ffc.FLASH_FLOOD_WEIGHT_GRID) == 18
    assert len(wc.WATERLOGGING_WEIGHT_GRID) == 26
    assert all(g["rainfall_intensity"] == 1.0 for g in ffc.FLASH_FLOOD_WEIGHT_GRID)
    assert all(g["rainfall_climatology"] == 1.0 for g in wc.WATERLOGGING_WEIGHT_GRID)
