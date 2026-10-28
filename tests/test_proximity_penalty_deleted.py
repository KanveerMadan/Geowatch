"""
Item 26, task 2: the road-proximity penalty (C7, C11) ceases to exist.

It was applied at inference (ingestion/inference.py) but never during
calibration (C11), and its strength had no stable physical meaning because
the distance map is normalised per AOI (C7).
"""
import inspect
import subprocess
import pathlib

import ingestion.inference as inference

REPO = pathlib.Path(__file__).resolve().parent.parent


def test_run_inference_takes_no_distance_maps():
    params = inspect.signature(inference.run_inference).parameters
    assert "road_dist_map" not in params
    assert "waterway_dist_map" not in params


def test_penalty_constants_are_gone():
    assert not hasattr(inference, "ROAD_PROXIMITY_PENALTY_STRENGTH")
    assert not hasattr(inference, "WATERWAY_PROXIMITY_PENALTY_STRENGTH")


def test_no_penalty_code_left_in_the_tree():
    out = subprocess.run(
        ["git", "grep", "-n", "-E", r"PROXIMITY_PENALTY|road_dist_map|waterway_dist_map=tile",
         "--", "*.py", ":!archive", ":!tests/test_proximity_penalty_deleted.py"],
        cwd=REPO, capture_output=True, text=True)
    assert out.stdout == "", f"penalty code remains:\n{out.stdout}"
