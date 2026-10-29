"""
Item 54 amendment — run_pipeline catches at each context-layer boundary.

Items 54/55 made the context-layer sources RAISE on integration and
programmer errors, and nothing in run_pipeline caught them, so one GEE
blip in, say, the slope layer aborted the whole run. The amendment:

  * the sources still raise (unchanged);
  * run_pipeline wraps each context-layer call, and a raise becomes that
    layer's block with status "failed" plus `exception_class`, which is
    distinct from "unavailable" (genuine no-data, `NoDataError`);
  * the run continues and completes.

The pipeline's external dependencies (GEE, export, SAM, the model) are
stubbed. What is under test is run_pipeline's own control flow.

Run from the repo root:  pytest tests/test_pipeline_layer_boundary.py
"""

from unittest.mock import MagicMock

import ee
import numpy as np
import pytest

import pipeline
from ingestion.errors import NoDataError, no_data
from rasterio.transform import Affine
from susceptibility.inputs import surface

BBOX = dict(west=72.836, south=19.037, east=72.862, north=19.06)
W, H = 32, 24
CATEGORIES = ["dense_informal_roofing", "dense_vegetation"]

AVAILABLE = {
    "get_merit_hand_context": {"status": "available", "mean_hnd_m": 3.4, "min_hnd_m": 0.0,
                               "max_hnd_m": 13.3, "max_upstream_area_km2": 75.9,
                               "river_connectivity": True, "error": None},
    "get_fabdem_elevation_stats": {"status": "available", "mean_elevation_m": 4.9,
                                   "min_elevation_m": 0.0, "max_elevation_m": 13.1, "error": None},
    "get_rainfall_climatology": {"status": "available", "mean_annual_mm": 2400.0, "error": None},
    "get_coastline_context": {"status": "available", "distance_km": 1.2,
                              "coastal_connectivity": True, "error": None},
    "get_slope_stats": {"status": "available", "mean_slope_deg": 1.1, "error": None},
    "get_country_iso3_for_aoi": {"status": "available", "iso3": "IND",
                                 "country_name": "India", "error": None},
    "get_inform_vulnerability_context": {
        "status": "available",
        "dimensions": {"vulnerability": {"raw_score": 5.4},
                       "lack_of_coping_capacity": {"raw_score": 4.1}},
        "data_quality": {"lack_of_reliability_score": 3.2, "pct_missing_indicators": 0.12},
        "error": None,
    },
    # item 26: the flood surface inputs, on a 3x4 hydrology grid
    "build_flood_inputs": {
        "status": "available", "validation_status": "placeholder",
        "transform": Affine(30, 0, 272220, 0, -30, 2108880), "shape": (3, 4),
        "crs": "EPSG:32643", "window": {"start": "2026-01-01", "end": "2026-03-31"},
        "impervious": surface(np.full((3, 4), 0.6), "open_buildings_v3 footprints",
                              "footprint_union_area_fraction", "placeholder"),
        "infiltration": surface(np.full((3, 4), 0.1), "S2 NDVI stand-in",
                                "ndvi_threshold_proxy", "placeholder"),
        "conduits": surface(np.full((3, 4), 0.2), "OSM highways",
                            "road_space_area_fraction", "experimental"),
        "terrain": {"low_slope": surface(np.full((3, 4), 0.9), "FABDEM", "1 - slope/5deg",
                                         "experimental")},
    },
    # item 26 Phase 1a: per-pixel hydrology rasters on the same 3x4 grid
    "fetch_hydro_rasters": {
        "status": "available", "transform": Affine(30, 0, 272220, 0, -30, 2108880),
        "shape": (3, 4), "crs": "EPSG:32643", "ref_year": 2026, "errors": {},
        "layers": {k: surface(np.full((3, 4), v), "stub", "stub", "experimental")
                   for k, v in (("hand_m", 3.0), ("upa_near_km2", 20.0), ("slope_deg", 1.0),
                                ("relief_slope_deg", 4.0), ("rain_annual_mm", 2400.0),
                                ("rain_intensity_mm_h", 12.0))},
    },
}


@pytest.fixture
def stub_pipeline(monkeypatch, tmp_path):
    """Stub every external dependency. Returns `layers`, a dict the test
    edits to make a context layer raise or report no-data."""
    p = "pipeline."
    monkeypatch.setattr(p + "initialize_gee", lambda: None)
    monkeypatch.setattr(p + "aoi_from_bbox", lambda *a, **k: object())
    monkeypatch.setattr(p + "ee", MagicMock())
    monkeypatch.setattr(p + "get_sentinel2_median_composite", lambda *a, **k: {
        "image": object(),
        "provenance": {"source_image_count": 3,
                       "requested_period": {"start": "2026-01-01", "end": "2026-03-31"}},
        "observation_quality": {"status": "available", "valid_observation_pct": 90.0,
                                "cloud_pct": 5.0, "cloud_shadow_pct": 5.0},
    })
    monkeypatch.setattr(p + "export_image_local", lambda **k: None)
    monkeypatch.setattr(p + "generate_rgb_preview_tiles", lambda **k: (
        [{"path": str(tmp_path / "tile_0_0.png"), "col_off": 0, "row_off": 0,
          "width": W, "height": H}],
        {"width": W, "height": H, "bounds": (0, 0, 1, 1), "crs": "EPSG:4326"},
    ))
    monkeypatch.setattr(p + "get_osm_features", lambda *a, **k: {"roads": None, "waterways": None})
    monkeypatch.setattr(p + "compute_relative_elevation_proxy",
                        lambda *a, **k: {"status": "experimental", "score": 0.46})
    monkeypatch.setattr(p + "get_elevation_stats",
                        lambda *a, **k: {"status": "available", "mean_elevation_m": 6.1})
    monkeypatch.setattr(p + "get_device", lambda: "cpu")
    monkeypatch.setattr(p + "load_production_model", lambda *a, **k: (object(), CATEGORIES, 2))
    monkeypatch.setattr(p + "load_caat_thresholds", lambda *a, **k: [0.5, 0.5])
    monkeypatch.setattr(p + "load_sam", lambda *a, **k: object())
    monkeypatch.setattr(p + "segment_tile", lambda *a, **k: [])
    monkeypatch.setattr(p + "run_inference", lambda *a, **k: {
        "landcover_map": np.zeros((H, W), dtype=np.uint8),
        "confidence_map": np.ones((H, W), dtype=np.float32),
        "ambiguity_map": np.zeros((H, W), dtype=np.uint8),
    })
    monkeypatch.setattr(p + "build_segments_with_landcover", lambda *a, **k: [])
    monkeypatch.setattr(p + "_apply_osm_labels_to_segments", lambda segs, *a, **k: segs)
    monkeypatch.setattr(p + "save_landcover_outputs", lambda *a, **k: {
        "map_path": "landcover.png", "confidence_map_path": "landcover_confidence.png"})
    monkeypatch.setattr(p + "save_pluvial_susceptibility_output", lambda *a, **k: "pluvial.png")
    monkeypatch.setattr(p + "get_population_context",
                        lambda *a, **k: {"status": "unavailable", "error": "stub"})
    monkeypatch.setattr(p + "get_builtup_reference",
                        lambda *a, **k: {"status": "unavailable", "error": "stub"})
    monkeypatch.setattr(p + "get_osm_road_length",
                        lambda *a, **k: {"status": "unavailable", "error": "stub"})
    monkeypatch.setattr(p + "get_osm_facilities",
                        lambda *a, **k: {"status": "unavailable", "error": "stub", "facilities": []})
    monkeypatch.setattr(p + "PRODUCTION_MODEL_PATH", str(tmp_path / "absent.pth"))

    layers = {name: dict(v) for name, v in AVAILABLE.items()}

    def make(name):
        def fn(*a, **k):
            v = layers[name]
            if isinstance(v, BaseException):
                raise v
            return dict(v)
        return fn

    for name in AVAILABLE:
        monkeypatch.setattr(p + name, make(name))
    return layers


def _run(tmp_path):
    return pipeline.run_pipeline(**BBOX, aoi_label="t", output_dir=str(tmp_path / "runs"))


def test_harness_baseline_completes(stub_pipeline, tmp_path):
    r = _run(tmp_path)
    assert r["status"] == "complete"
    assert r["terrain_context"]["fluvial_hand_context"]["status"] == "available"


def test_one_failing_layer_does_not_abort_the_run(stub_pipeline, tmp_path):
    stub_pipeline["get_slope_stats"] = ee.EEException("User memory limit exceeded.")
    r = _run(tmp_path)
    assert r["status"] == "complete"


@pytest.mark.parametrize("fn,path", [
    ("get_merit_hand_context", ("terrain_context", "fluvial_hand_context")),
    ("get_fabdem_elevation_stats", ("terrain_context", "fabdem_bare_earth")),
    ("get_coastline_context", ("terrain_context", "coastal_context")),
    ("get_rainfall_climatology", ("rainfall_climatology",)),
    ("get_inform_vulnerability_context", ("vulnerability",)),
])
def test_failing_layer_shows_failed_with_its_class(stub_pipeline, tmp_path, fn, path):
    stub_pipeline[fn] = ee.EEException("quota")
    r = _run(tmp_path)
    block = r
    for k in path:
        block = block[k]
    assert r["status"] == "complete"
    assert block["status"] == "failed"
    assert block["exception_class"] == "EEException"
    assert block["status"] != "unavailable"


def test_failed_hydro_rasters_reach_the_per_pixel_modules_as_not_available(stub_pipeline,
                                                                           tmp_path):
    """Item 26 Phase 1a: fluvial and flash flood read only the per-pixel
    rasters. Their failure is named and stops both from being scored as if
    the terrain were known; waterlogging keeps only its impervious input."""
    stub_pipeline["fetch_hydro_rasters"] = TimeoutError("read timed out")
    r = _run(tmp_path)
    assert r["status"] == "complete"
    assert r["hydro_rasters"]["status"] == "failed"
    assert r["hydro_rasters"]["exception_class"] == "TimeoutError"
    for m in ("fluvial", "flash_flood"):
        assert r["susceptibility"][m]["status"] == "insufficient_evidence", m
        assert "aoi_mean_score" not in r["susceptibility"][m]
    # round 2's tuned waterlogging weights give impervious 0, so with no
    # rasters nothing it weights is left
    assert r["susceptibility"]["waterlogging"]["status"] == "insufficient_evidence"


def test_hydro_rasters_make_three_per_pixel_maps(stub_pipeline, tmp_path):
    r = _run(tmp_path)
    for m in ("fluvial", "flash_flood", "waterlogging"):
        b = r["susceptibility"][m]
        assert b["spatial"] is True and b["map_path"] == "pluvial.png", m   # stubbed saver
        assert "susceptibility_map" not in b, m
    assert r["hydro_rasters"]["inputs"]["hand_m"]["source"] == "stub"


def test_programmer_error_is_also_contained_and_named(stub_pipeline, tmp_path):
    stub_pipeline["get_merit_hand_context"] = NameError("name 'hnd_stast' is not defined")
    r = _run(tmp_path)
    block = r["terrain_context"]["fluvial_hand_context"]
    assert block["status"] == "failed"
    assert block["exception_class"] == "NameError"


def test_data_absent_layer_still_shows_unavailable(stub_pipeline, tmp_path):
    stub_pipeline["get_fabdem_elevation_stats"] = no_data(
        NoDataError("FABDEM reduction returned no value for this AOI."),
        mean_elevation_m=None)
    r = _run(tmp_path)
    block = r["terrain_context"]["fabdem_bare_earth"]
    assert block["status"] == "unavailable"
    assert block["exception_class"] == "NoDataError"


def test_failed_country_lookup_makes_vulnerability_failed_not_unavailable(stub_pipeline, tmp_path):
    """Without this, INFORM would report "no ISO3 provided" as unavailable,
    which reads as a data gap when the real cause is a broken lookup."""
    stub_pipeline["get_country_iso3_for_aoi"] = ConnectionError("network unreachable")
    r = _run(tmp_path)
    v = r["vulnerability"]
    assert v["status"] == "failed"
    assert v["exception_class"] == "ConnectionError"
    assert v["failed_upstream"] == "country_lookup"


def test_flood_inputs_reach_pluvial_and_waterlogging_with_provenance(stub_pipeline, tmp_path):
    """Item 26: pluvial and waterlogging read the declared surface inputs,
    and say where they came from."""
    r = _run(tmp_path)
    pl, wl = r["susceptibility"]["pluvial"], r["susceptibility"]["waterlogging"]
    assert pl["inputs"]["impervious"]["method"] == "footprint_union_area_fraction"
    # The legacy result labels every block "retired" (2026-10-28); the
    # module's own label survives as validation_status_superseded.
    assert pl["validation_status"] == "retired"
    assert pl["validation_status_superseded"] == "placeholder"
    assert wl["impervious_fraction_pct"] == 60.0
    assert "impervious" not in wl["inputs"]      # unweighted: not a listed input
    # round 2's tuned weights give impervious 0, so the placeholder input is
    # declared but does not set the module's own label (round 3: failed); the
    # legacy result still labels the block "retired"
    assert "impervious (weight 0)" in wl["components_excluded"]
    assert wl["validation_status"] == "retired"
    assert wl["validation_status_superseded"] == "failed"
    assert r["flood_inputs"]["grid"]["crs"] == "EPSG:32643"


def test_failed_flood_inputs_do_not_abort_and_are_named(stub_pipeline, tmp_path):
    stub_pipeline["build_flood_inputs"] = ee.EEException("quota")
    r = _run(tmp_path)
    assert r["status"] == "complete"
    assert r["flood_inputs"]["status"] == "failed"
    assert "impervious" not in r["susceptibility"]["pluvial"].get("inputs", {})
    # no hydrology grid -> no per-pixel rasters and no impervious surface
    assert r["hydro_rasters"]["status"] == "unavailable"
    assert r["susceptibility"]["waterlogging"]["status"] == "insufficient_evidence"
