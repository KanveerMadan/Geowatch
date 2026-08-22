"""
Phase 0, requirement D + the critical wrong-subsystem bug fix: the
flood assessment must check EACH source's own status independently.
Before the fix, the code checked flood_susceptibility["elevation_fallback"]
(the GEE proxy's own flag) to decide whether to trust elevation's flag --
meaning a successful GEE call + a FAILED Open Elevation call still fed
elev_flag=True (from the 0m substitute) into the OR.
"""
import pytest
from pipeline import run_pipeline


@pytest.fixture
def mock_full_pipeline_deps(monkeypatch, tmp_path):
    """Stubs every external dependency except the flood-logic path itself,
    so this test exercises only pipeline.py's combination logic."""
    monkeypatch.setattr("pipeline.initialize_gee", lambda: None)
    monkeypatch.setattr("pipeline.aoi_from_bbox", lambda *a, **k: object())
    monkeypatch.setattr("pipeline.get_best_image", lambda *a, **k: object())
    monkeypatch.setattr("pipeline.get_latest_image", lambda *a, **k: object()) 
    monkeypatch.setattr("pipeline.get_imagery_acquisition_date", lambda *a, **k: "unknown")
    monkeypatch.setattr("pipeline.export_image_local", lambda **k: None)
    monkeypatch.setattr(
        "pipeline.generate_rgb_preview_tiles",
        lambda **k: [str(tmp_path / "tile_0_0.png")],
    )
    # produce a real tiny PNG so PIL.Image.open() succeeds
    from PIL import Image
    Image.new("RGB", (64, 64)).save(tmp_path / "tile_0_0.png")

    monkeypatch.setattr("pipeline.load_sam", lambda *a, **k: object())
    monkeypatch.setattr("pipeline.segment_tile", lambda *a, **k: [])
    monkeypatch.setattr("pipeline.save_masks", lambda *a, **k: None)
    monkeypatch.setattr("pipeline.get_osm_features", lambda *a, **k: {"roads": None, "waterways": None})
    monkeypatch.setattr("pipeline.compute_road_distance_map", lambda *a, **k: None)
    monkeypatch.setattr("pipeline.compute_waterway_distance_map", lambda *a, **k: None)
    monkeypatch.setattr("pipeline.compute_road_access_score", lambda *a, **k: -1.0)
    monkeypatch.setattr(
        "pipeline.load_production_model",
        lambda *a, **k: (object(), ["dense_informal_roofing"], 1),
    )
    monkeypatch.setattr("pipeline.load_caat_thresholds", lambda *a, **k: [0.5])
    monkeypatch.setattr(
        "pipeline.run_inference",
        lambda *a, **k: {
            "landcover_map": None, "confidence_map": None, "ambiguity_map": None,
            "category_area_pct": {"dense_informal_roofing": 100.0},
            "unknown_pct": 0.0, "ambiguous_pct": 0.0, "ambiguous_pct_by_pair": {},
        },
    )
    monkeypatch.setattr(
        "pipeline.save_landcover_outputs",
        lambda *a, **k: {"map_path": "landcover.png", "confidence_map_path": "landcover_confidence.png"},
    )
    monkeypatch.setattr("pipeline.build_segments_with_landcover", lambda *a, **k: [])
    monkeypatch.setattr("pipeline._apply_osm_labels_to_segments", lambda segs, *a, **k: segs)


def test_open_elevation_failure_alone_does_not_produce_positive_flag(
    canonical_dharavi_bbox, mock_full_pipeline_deps,
    mock_open_elevation_failure, mock_gee_proxy_success,
    tmp_path,
):
    """THE regression test for the wrong-subsystem bug. GEE succeeds,
    Open Elevation fails. Before the fix: elev_flag=True (0m fallback)
    fed into the OR because the code checked the WRONG subsystem's
    fallback flag. After the fix: elevation's own unavailable status
    must be excluded from the assessment entirely."""
    result = run_pipeline(**canonical_dharavi_bbox, aoi_label="test", output_dir=str(tmp_path))

    assert result["status"] == "complete"
    fa = result["flood_assessment"]

    # elevation is unavailable; GEE proxy succeeded -- must NOT be
    # "insufficient_evidence" (that's only when BOTH fail), but the
    # elevation component specifically must show unavailable, and no
    # combined boolean flag should exist anywhere in the output.
    assert fa["status"] == "experimental_screening_only"
    assert fa["terrain_context"]["absolute_elevation"]["status"] == "unavailable"
    assert fa["terrain_context"]["absolute_elevation"]["mean_m"] is None
    assert fa["terrain_context"]["absolute_elevation"]["below_10m_unvalidated"] is None
    assert fa["terrain_context"]["relative_elevation_proxy"]["status"] == "experimental"

    # the deprecated field must be neutralized, not silently True
    assert result["summary"]["flood_risk_flag"] is None


def test_both_sources_failing_returns_insufficient_evidence(
    canonical_dharavi_bbox, mock_full_pipeline_deps,
    mock_open_elevation_failure, mock_gee_proxy_failure,
    tmp_path,
):
    result = run_pipeline(**canonical_dharavi_bbox, aoi_label="test", output_dir=str(tmp_path))
    assert result["flood_assessment"]["status"] == "insufficient_evidence"


def test_both_sources_succeeding_produces_full_experimental_context(
    canonical_dharavi_bbox, mock_full_pipeline_deps,
    mock_open_elevation_success, mock_gee_proxy_success,
    tmp_path,
):
    result = run_pipeline(**canonical_dharavi_bbox, aoi_label="test", output_dir=str(tmp_path))
    fa = result["flood_assessment"]
    assert fa["status"] == "experimental_screening_only"
    assert fa["terrain_context"]["absolute_elevation"]["status"] == "available"
    assert fa["terrain_context"]["relative_elevation_proxy"]["status"] == "experimental"