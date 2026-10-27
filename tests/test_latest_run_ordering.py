"""
C17 / build item 56 — "latest run" is chosen by parsed timestamp, not by
string order, and `*_test_*` runs never reach the demo endpoint.

04_FINDINGS_LEDGER.md C17 [E]: `get_latest_run("dharavi")` took the
lexicographic last directory. That was `dharavi_test_20260806_114208`, because
`'2' < 't'` puts every `dharavi_2026...` run below every `dharavi_t...` run —
so no future run could ever sort above the test artifact, and `/api/demo`
served it indefinitely.

The fixtures below rebuild that exact shape in a temporary runs directory, so
the failure is the one the ledger measured, not a synthetic cousin of it.

Run from the repo root:  pytest tests/test_latest_run_ordering.py
"""

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_module():
    import api
    return api


def _make_run(runs_dir, name, payload=None):
    d = runs_dir / name
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps(payload or {"run_id": name}))
    return d


@pytest.fixture
def runs_root(tmp_path, monkeypatch):
    """A data/pipeline_runs tree under tmp_path, with cwd pointed at it."""
    runs_dir = tmp_path / "data" / "pipeline_runs"
    runs_dir.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    return runs_dir


# The ledger's three names, verbatim.
LEDGER_TEST_RUN = "dharavi_test_20260806_114208"
LEDGER_NEWEST_BY_TIME = "dharavi_phase11_postfix_20260807_125913"
LEDGER_PLAIN_OLD = "dharavi_20260702_163012"


def test_ledger_case_newest_by_timestamp_wins(api_module, runs_root):
    """The exact C17 shape: the newest run must win, not the 't...' name."""
    for name in (LEDGER_PLAIN_OLD, LEDGER_TEST_RUN, LEDGER_NEWEST_BY_TIME):
        _make_run(runs_root, name)
    assert api_module.get_latest_run("dharavi")["run_id"] == LEDGER_NEWEST_BY_TIME


def test_a_future_plain_run_can_sort_above_any_named_run(api_module, runs_root):
    """C17's consequence: under string order no `dharavi_2026...` run could
    ever beat `dharavi_t...`. A run made later must now be served."""
    _make_run(runs_root, "dharavi_phase11_postfix_20260807_125913")
    _make_run(runs_root, "dharavi_20261026_090000")
    assert api_module.get_latest_run("dharavi")["run_id"] == "dharavi_20261026_090000"


def test_test_runs_are_excluded_even_when_newest(api_module, runs_root):
    """`*_test_*` runs are excluded outright, not merely out-ranked."""
    _make_run(runs_root, LEDGER_PLAIN_OLD)
    _make_run(runs_root, "dharavi_test_20991231_235959")
    assert api_module.get_latest_run("dharavi")["run_id"] == LEDGER_PLAIN_OLD


def test_only_test_runs_means_no_run(api_module, runs_root):
    _make_run(runs_root, LEDGER_TEST_RUN)
    assert api_module.get_latest_run("dharavi") is None


def test_demo_endpoint_never_serves_a_test_run(api_module, runs_root):
    _make_run(runs_root, LEDGER_TEST_RUN)
    client = TestClient(
        api_module.app,
        headers={api_module.API_KEY_HEADER_NAME: api_module.API_KEY},
    )
    assert client.get("/api/demo").status_code == 404


def test_demo_endpoint_serves_newest_non_test_run(api_module, runs_root):
    for name in (LEDGER_PLAIN_OLD, LEDGER_TEST_RUN, LEDGER_NEWEST_BY_TIME):
        _make_run(runs_root, name)
    client = TestClient(
        api_module.app,
        headers={api_module.API_KEY_HEADER_NAME: api_module.API_KEY},
    )
    r = client.get("/api/demo")
    assert r.status_code == 200
    assert r.json()["run_id"] == LEDGER_NEWEST_BY_TIME


def test_undated_directory_is_not_guessed_into_first_place(api_module, runs_root):
    """A directory with no parseable trailing timestamp has no position in a
    chronological order, so it must not be served as 'latest'."""
    _make_run(runs_root, LEDGER_PLAIN_OLD)
    _make_run(runs_root, "dharavi_zzz_undated")
    assert api_module.get_latest_run("dharavi")["run_id"] == LEDGER_PLAIN_OLD


@pytest.mark.parametrize("name,expected", [
    ("dharavi_20260702_163012", (2026, 7, 2, 16, 30, 12)),
    ("dharavi_phase11_postfix_20260807_125913", (2026, 8, 7, 12, 59, 13)),
    ("dharavi_gate_b_inundation_20260801_133511", (2026, 8, 1, 13, 35, 11)),
    ("dharavi_zzz_undated", None),
    ("dharavi_20261399_000000", None),   # month 13: not a real timestamp
])
def test_run_timestamp_parsing(api_module, name, expected):
    ts = api_module.run_dir_timestamp(name)
    if expected is None:
        assert ts is None
    else:
        assert ts.timetuple()[:6] == expected


# ── Item 56, finished: other run kinds, and /api/runs ordering ───────────
#
# `startswith("dharavi")` also matches the inundation and event-hazard runs,
# whose result shape is not the land-cover result the demo renders. They are
# excluded outright, like test runs.

@pytest.mark.parametrize("name", [
    "dharavi_gate_b_inundation_20991231_235959",
    "dharavi_p9_event_eventhazard_20991231_235959",
])
def test_other_run_kinds_are_never_the_demo(api_module, runs_root, name):
    _make_run(runs_root, LEDGER_PLAIN_OLD)
    _make_run(runs_root, name)
    assert api_module.get_latest_run("dharavi")["run_id"] == LEDGER_PLAIN_OLD


def _client(api_module):
    return TestClient(
        api_module.app,
        headers={api_module.API_KEY_HEADER_NAME: api_module.API_KEY},
    )


def test_api_runs_is_newest_first_by_parsed_timestamp(api_module, runs_root):
    """Reverse string order put every `dharavi_t...` above `dharavi_2...` and
    grouped by label before time. The list is now chronological."""
    names = [
        "accra_20260701_131955",
        "dharavi_test_20260806_114208",
        "dharavi_phase11_postfix_20260807_125913",
        "zzz_20250101_000000",
        "dharavi_20261026_090000",
    ]
    for n in names:
        _make_run(runs_root, n)
    got = [r["run_id"] for r in _client(api_module).get("/api/runs").json()["runs"]]
    assert got == [
        "dharavi_20261026_090000",
        "dharavi_phase11_postfix_20260807_125913",
        "dharavi_test_20260806_114208",
        "accra_20260701_131955",
        "zzz_20250101_000000",
    ]


def test_api_runs_lists_undated_directories_last(api_module, runs_root):
    """Listing is not "latest" selection: an undated run is still listed,
    but it has no chronological position, so it goes after every dated run
    rather than being guessed into one."""
    _make_run(runs_root, "dharavi_20260702_163012")
    _make_run(runs_root, "zz_undated")
    _make_run(runs_root, "aa_undated")
    got = [r["run_id"] for r in _client(api_module).get("/api/runs").json()["runs"]]
    assert got == ["dharavi_20260702_163012", "aa_undated", "zz_undated"]
