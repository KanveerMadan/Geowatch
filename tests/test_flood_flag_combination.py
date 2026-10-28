"""
Phase 0, requirement D + the critical wrong-subsystem bug fix: the
flood assessment must check EACH source's own status independently.
Before the fix, the code checked flood_susceptibility["elevation_fallback"]
(the GEE proxy's own flag) to decide whether to trust elevation's flag --
meaning a successful GEE call + a FAILED Open Elevation call still fed
elev_flag=True (from the 0m substitute) into the OR.
"""
import pytest

import pipeline
from ingestion.osm_dem import get_elevation_stats
from pipeline import run_pipeline
# The maintained stub of every external dependency (item 54). The old local
# fixture patched functions pipeline.py no longer has (get_best_image,
# save_masks, get_imagery_acquisition_date) and errored at setup.
from tests.test_pipeline_layer_boundary import stub_pipeline  # noqa: F401


@pytest.fixture
def mock_full_pipeline_deps(stub_pipeline, monkeypatch):
    """Everything stubbed except the flood-logic path: the real Open
    Elevation source runs (requests.post is mocked by conftest), and the
    relative-elevation proxy is set by the mock_gee_proxy_* fixture, which
    must be requested after this one."""
    monkeypatch.setattr(pipeline, "get_elevation_stats", get_elevation_stats)


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