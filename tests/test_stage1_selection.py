"""Item 21 Stage 1 selection record (data/stage1/selection.json): the plan
decided 2026-09-29, the frozen sampler and the frozen change test."""
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "experiments" / "item21_sites"))

from labelling.common import load_config

CFG = load_config()
SEL = REPO / "data" / "stage1" / "selection.json"


@pytest.fixture(scope="module")
def sel():
    if not SEL.exists():
        pytest.skip("stage 1 selection not made")
    return json.loads(SEL.read_text())


def test_eight_tiles_by_the_plan(sel):
    plan = CFG["stage1_tiles"]["strata_per_site"]
    assert set(sel["sites"]) == set(plan)
    chosen = [r["chosen"] for s in sel["sites"].values() for r in s["strata"].values()]
    assert len(chosen) == CFG["stage1_stop_rule"]["details"]["evaluate_once_after_tiles"] == 8
    for site, s in sel["sites"].items():
        assert list(s["strata"]) == plan[site]
        assert s["random_seed"] == CFG["tiles"]["random_seed"]
        for stratum, r in s["strata"].items():
            assert r["chosen"]["stratum"] == stratum
            assert r["eligible"] >= CFG["stage1_tiles"]["min_eligible_per_stratum"]


def test_rank_walk_skips_only_change_test_drops(sel):
    for s in sel["sites"].values():
        for r in s["strata"].values():
            drops = r["dropped_by_change_test"]
            assert all(d["change_test"]["dropped"] for d in drops)
            assert r["chosen"]["change_test"]["dropped"] is False
            assert r["chosen"]["change_test"]["share"] <= CFG["open"]["change_test"][
                "drop_tile_if_changed_share_above"]
            # the chosen tile is the first rank not dropped
            assert [d["rank_in_stratum"] for d in drops] == list(range(len(drops)))
            assert r["chosen"]["rank_in_stratum"] == len(drops)


def test_frames_recorded_with_seed_and_guide(sel):
    for site, s in sel["sites"].items():
        f = json.loads((REPO / s["frame_file"]).read_text())
        assert f["run_metadata"]["tile_sampler_seed"] == CFG["tiles"]["random_seed"]
        ids = {t["tile_id"] for t in f["frame"]["tiles"]}
        assert all(r["chosen"]["tile_id"] in ids for r in s["strata"].values())
    assert sel["guide_version"] == CFG["guide_version"]


def test_pick_replaces_dropped_with_next_rank():
    import stage1_select as st
    ranked = [{"tile_id": "a", "rank_in_stratum": 0}, {"tile_id": "b", "rank_in_stratum": 1},
              {"tile_id": "c", "rank_in_stratum": 2}]
    d = {"a": {"dropped": True}, "b": {"dropped": False}, "c": {"dropped": False}}
    chosen, dropped = st.pick(ranked, d)
    assert chosen["tile_id"] == "b" and [x["tile_id"] for x in dropped] == ["a"]
    with pytest.raises(RuntimeError, match="no change-test decision"):
        st.pick(ranked, {"a": {"dropped": None}})


def test_records_are_tracked():
    tracked = subprocess.run(["git", "ls-files", "data/frames", "data/stage1"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout.split()
    assert all(p.endswith("_frame.json") or p.endswith("selection.json") for p in tracked)
