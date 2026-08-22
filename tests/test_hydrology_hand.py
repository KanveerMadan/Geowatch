"""
Phase 5: tests for ingestion.hydrology -- MERIT Hydro HAND context and
FABDEM bare-earth elevation. Mirrors tests/test_relative_elevation_proxy.py's
pattern: verify honest failure behavior, never a fabricated value.
"""

import pytest
from unittest.mock import patch, MagicMock

from ingestion.hydrology import get_merit_hand_context, get_fabdem_elevation_stats


DHARAVI_BBOX = dict(west=72.836, south=19.037, east=72.862, north=19.06)


class TestMeritHandContext:

    def test_gee_failure_returns_unavailable_not_fabricated(self):
        """If MERIT Hydro/GEE call fails, status must be 'unavailable' and
        every numeric field must be None -- never a substituted value."""
        with patch("ingestion.hydrology.initialize_gee",
                   side_effect=Exception("simulated GEE failure")):
            result = get_merit_hand_context(**DHARAVI_BBOX)

        assert result["status"] == "unavailable"
        assert result["mean_hnd_m"] is None
        assert result["min_hnd_m"] is None
        assert result["max_hnd_m"] is None
        assert result["max_upstream_area_km2"] is None
        assert result["river_connectivity"] is None
        assert result["error"] is not None

    def test_success_path_returns_true_hand_flags(self):
        """When available, must be explicitly labeled true_hand=True and
        hydrologically_conditioned=True -- unlike relative_elevation_proxy,
        which must always report these as False."""
        fake_reduce_result = {"hnd_mean": 3.403, "hnd_min": 0.0, "hnd_max": 13.3}
        fake_upa_result = {"upa": 75.941}

        mock_image = MagicMock()
        mock_image.select.return_value = mock_image
        mock_image.reduceRegion.return_value.getInfo.side_effect = [
            fake_reduce_result, fake_upa_result,
        ]

        with patch("ingestion.hydrology.initialize_gee"), \
             patch("ingestion.hydrology.ee.Image", return_value=mock_image), \
             patch("ingestion.hydrology.ee.Geometry"), \
             patch("ingestion.hydrology.ee.Reducer"):
            result = get_merit_hand_context(**DHARAVI_BBOX)

        assert result["status"] == "available"
        assert result["true_hand"] is True
        assert result["hydrologically_conditioned"] is True
        assert result["spatial"] is False
        assert result["mean_hnd_m"] == 3.403
        assert result["river_connectivity"] is True  # 75.941 >= threshold

    def test_river_connectivity_false_below_threshold(self):
        """A tiny upstream area must NOT be flagged as river-connected."""
        fake_reduce_result = {"hnd_mean": 20.0, "hnd_min": 15.0, "hnd_max": 25.0}
        fake_upa_result = {"upa": 0.05}  # below RIVER_CONNECTIVITY threshold

        mock_image = MagicMock()
        mock_image.select.return_value = mock_image
        mock_image.reduceRegion.return_value.getInfo.side_effect = [
            fake_reduce_result, fake_upa_result,
        ]

        with patch("ingestion.hydrology.initialize_gee"), \
             patch("ingestion.hydrology.ee.Image", return_value=mock_image), \
             patch("ingestion.hydrology.ee.Geometry"), \
             patch("ingestion.hydrology.ee.Reducer"):
            result = get_merit_hand_context(**DHARAVI_BBOX)

        assert result["river_connectivity"] is False

    def test_upstream_area_key_is_unsuffixed(self):
        """Regression test for the confirmed bug: a single (uncombined)
        ee.Reducer.max() call names its output key by the BAND NAME alone
        ('upa'), not 'upa_max'. This test locks in the correct key so a
        future refactor can't silently reintroduce the always-None bug."""
        fake_reduce_result = {"hnd_mean": 3.4, "hnd_min": 0.0, "hnd_max": 13.3}
        fake_upa_result = {"upa": 42.0}  # correct key, no _max suffix

        mock_image = MagicMock()
        mock_image.select.return_value = mock_image
        mock_image.reduceRegion.return_value.getInfo.side_effect = [
            fake_reduce_result, fake_upa_result,
        ]

        with patch("ingestion.hydrology.initialize_gee"), \
             patch("ingestion.hydrology.ee.Image", return_value=mock_image), \
             patch("ingestion.hydrology.ee.Geometry"), \
             patch("ingestion.hydrology.ee.Reducer"):
            result = get_merit_hand_context(**DHARAVI_BBOX)

        assert result["max_upstream_area_km2"] == 42.0


class TestFabdemElevationStats:

    def test_gee_failure_returns_unavailable_not_fabricated(self):
        with patch("ingestion.hydrology.initialize_gee",
                   side_effect=Exception("simulated GEE failure")):
            result = get_fabdem_elevation_stats(**DHARAVI_BBOX)

        assert result["status"] == "unavailable"
        assert result["mean_elevation_m"] is None
        assert result["error"] is not None

    def test_success_path_reports_bare_earth_flags(self):
        fake_stats = {"b1_mean": 4.859, "b1_min": 0.0, "b1_max": 13.1}

        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.mosaic.return_value = mock_collection
        mock_collection.clip.return_value = mock_collection
        mock_collection.reduceRegion.return_value.getInfo.return_value = fake_stats

        with patch("ingestion.hydrology.initialize_gee"), \
             patch("ingestion.hydrology.ee.ImageCollection", return_value=mock_collection), \
             patch("ingestion.hydrology.ee.Geometry"), \
             patch("ingestion.hydrology.ee.Reducer"):
            result = get_fabdem_elevation_stats(**DHARAVI_BBOX)

        assert result["status"] == "available"
        assert result["bare_earth"] is True
        assert result["building_bias_reduced"] is True
        assert result["mean_elevation_m"] == 4.859
        assert "CC BY-NC-SA" in result["license"]

    def test_never_conflated_with_merit_hand_source_field(self):
        """FABDEM's source string must be distinguishable from MERIT
        Hydro's -- guards against future code accidentally merging the
        two into one 'terrain_source' field without attribution."""
        fake_stats = {"b1_mean": 4.859, "b1_min": 0.0, "b1_max": 13.1}
        mock_collection = MagicMock()
        mock_collection.filterBounds.return_value = mock_collection
        mock_collection.mosaic.return_value = mock_collection
        mock_collection.clip.return_value = mock_collection
        mock_collection.reduceRegion.return_value.getInfo.return_value = fake_stats

        with patch("ingestion.hydrology.initialize_gee"), \
             patch("ingestion.hydrology.ee.ImageCollection", return_value=mock_collection), \
             patch("ingestion.hydrology.ee.Geometry"), \
             patch("ingestion.hydrology.ee.Reducer"):
            result = get_fabdem_elevation_stats(**DHARAVI_BBOX)

        assert "FABDEM" in result["source"]
        assert "MERIT" not in result["source"]