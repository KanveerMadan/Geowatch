from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from experiments.urban_flood_ref.optical_catalog import _public_cog_url, collect
from experiments.urban_flood_ref.optical_reference import evidence_windows, optical_states, unanimous_30m


class TestOpticalReference(unittest.TestCase):
    def test_masks_revisit_transitions_and_conflicts(self):
        baseline = np.array([[4, 5, 4, 6, 4, 4, 4, 4]], dtype=np.uint8)
        post1 = np.array([[6, 4, 9, 6, 4, 0, 6, 2]], dtype=np.uint8)
        post2 = np.array([[6, 5, 3, 6, 6, 7, 6, 2]], dtype=np.uint8)
        duplicate = np.array([[4, 4, 4, 4, 4, 4, 6, 4]], dtype=np.uint8)
        before = [("2020-01-01", baseline), ("2020-01-02", baseline), ("2020-01-02", duplicate)]
        during = [("2020-02-01", post1), ("2020-02-02", post2)]
        value = optical_states(before, during, baseline.shape)
        self.assertEqual(value.tolist(), [[1, 0, 255, 255, 255, 255, 255, 255]])

    def test_duplicate_granules_do_not_create_two_pre_dates(self):
        land, wet = np.full((1, 1), 5), np.full((1, 1), 6)
        self.assertEqual(optical_states([("2020-01-01", land)]*2, [("2020-02-01", wet)], (1, 1)).item(), 255)
        self.assertEqual(optical_states([], [], (1, 1)).item(), 255)

    def test_homogeneous_support(self):
        raster = np.ones((3, 9), dtype=np.uint8)
        raster[:, 0:3] = 0
        raster[0, 7] = 255
        self.assertEqual(unanimous_30m(raster).tolist(), [[0, 1, 255]])
        with self.assertRaises(ValueError):
            unanimous_30m(raster[:2])

    def test_restrict_search_to_approved_ranges(self):
        value = evidence_windows("2020-03-01", "2020-03-06", "2020-03-01", "2020-02-14", "2020-03-06")
        self.assertEqual(value["pre"], ("2020-02-14", "2020-02-21"))
        self.assertEqual(value["post"], ("2020-03-01", "2020-03-03"))
        with self.assertRaises(ValueError):
            evidence_windows("2020-03-01", "2020-03-06", "2020-03-07", "2020-02-14", "2020-03-09")

    def test_leakage_guard_runs_before_io(self):
        def deny(*args):
            raise PermissionError("reserved")
        with tempfile.TemporaryDirectory() as tmp, patch("pathlib.Path.mkdir", side_effect=AssertionError("premature IO")), patch("urllib.request.urlopen", side_effect=AssertionError("network access")):
            with self.assertRaises(PermissionError):
                collect("fictional", {"shape":[5,5], "crs":"EPSG:32631", "transform":[30,0,500000,0,-30,5540000]},
                        "2020-03-01", "2020-03-06", "2020-03-02", "2020-01-01", "2020-03-09", deny, Path(tmp)/"out")

    def test_assets_must_be_public_readonly_sentinel_cogs(self):
        self.assertEqual(_public_cog_url("s3://sentinel-cogs/fake.tif"), "https://sentinel-cogs.s3.us-west-2.amazonaws.com/fake.tif")
        with self.assertRaises(ValueError):
            _public_cog_url("https://localhost/.credentials")


if __name__ == "__main__":
    unittest.main()
