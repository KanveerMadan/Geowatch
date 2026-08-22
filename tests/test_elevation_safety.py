"""
Phase 0, requirement A: Open Elevation failure must never produce a
0m substitute or a boolean flood_risk_flag. This is the single most
important test in Phase 0 -- it's the live bug the whole phase exists
to close.
"""
import pytest
from ingestion.osm_dem import get_elevation_stats


def test_elevation_success_returns_real_values(canonical_dharavi_bbox, mock_open_elevation_success, tmp_path):
    stats = get_elevation_stats(**canonical_dharavi_bbox, output_dir=str(tmp_path))

    assert stats["status"] == "available"
    assert stats["mean_elevation_m"] == pytest.approx(6.08)
    assert stats["sample_count"] == 25
    assert stats["flood_risk_flag"] is True  # 6.08 < 10, real evidence
    assert stats["elevation_fallback"] is False
    assert stats["error"] is None


def test_elevation_failure_returns_unavailable_not_zero(canonical_dharavi_bbox, mock_open_elevation_failure, tmp_path):
    """THE core Phase 0 regression test. Before the fix, this scenario
    produced mean_elevation_m=0.0 and flood_risk_flag=True from a
    failed API call -- missing data masquerading as flood evidence."""
    stats = get_elevation_stats(**canonical_dharavi_bbox, output_dir=str(tmp_path))

    assert stats["status"] == "unavailable"
    assert stats["mean_elevation_m"] is None
    assert stats["min_elevation_m"] is None
    assert stats["max_elevation_m"] is None
    assert stats["sample_count"] == 0
    assert stats["flood_risk_flag"] is None       # NEVER True, NEVER False
    assert stats["elevation_fallback"] is True
    assert stats["error"] is not None


def test_elevation_failure_writes_honest_json_to_disk(canonical_dharavi_bbox, mock_open_elevation_failure, tmp_path):
    """Confirms the persisted elevation_stats.json also reflects the
    honest failure state, since pipeline.py reads this back from disk
    in some code paths."""
    import json
    get_elevation_stats(**canonical_dharavi_bbox, output_dir=str(tmp_path))

    with open(tmp_path / "elevation_stats.json") as f:
        saved = json.load(f)

    assert saved["status"] == "unavailable"
    assert saved["flood_risk_flag"] is None