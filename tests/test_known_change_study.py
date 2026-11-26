import numpy as np

from experiments.change_history import known_change as study


def test_selection_full_support_and_spread():
    labels = np.array([[1, 1, 0, 1], [1, 1, 0, 1]], dtype=float)
    spec = {"minimum_separation_m": 200, "cap_per_transition_per_region": 8}
    rows = study.select_cells(labels, "fixed", 0, 200, "EPSG:32644", spec)
    assert rows == study.select_cells(labels, "fixed", 0, 200, "EPSG:32644", spec)
    assert len(rows) == 2
    assert set(r["expected"] for r in rows) == {"greenness_loss"}


def test_abstention_stays_in_denominator():
    r = study.score({"id": "a", "expected": "open_water_signal_gain"}, [], "water")
    assert r["confirmed"] is False
    assert r["fully_observed"] is False
    assert r["first_usable_in_monitor"] is None
    assert r["confirmation_minus_reference_interval_days"] is None


def test_confirmation_is_directional_even_on_partial_coverage(monkeypatch):
    def fake(*args, **kwargs):
        return {"events":[{"transition":"greenness_gain", "confirmed_on":"2021-02-01"},
                          {"transition":"greenness_loss", "confirmed_on":None},
                          {"transition":"greenness_loss", "confirmed_on":"2021-03-02"}],
                "series":[{"signal":"ndvi", "status":"partial_observation"}]}
    monkeypatch.setattr(study.change_detection, "detect_cell", fake)
    observed = study.score({"id":"cell", "expected":"greenness_loss"}, [], "forest")
    assert observed["confirmed"]
    assert observed["first_confirmation"] == "2021-03-02"
    assert not observed["fully_observed"]
    assert observed["partially_or_fully_observed"]


def test_artifacts_match_pre_score_lock():
    manifest = study.HERE/"known_change_manifest.json"
    lock = study.read(study.HERE/"known_change_lock.json")
    assert lock == {"protocol":study.digest(study.PROTOCOL), "manifest":study.digest(manifest),
                    "implementation":study.digest(study.__file__)}
    cells = [c for r in study.read(manifest)["regions"] for c in r["cells"]]
    assert len({c["id"] for c in cells}) == len(cells)
    assert len(cells) == 140


def test_result_contains_all_and_only_frozen_cases_with_their_original_labels():
    manifest = study.read(study.HERE / "known_change_manifest.json")
    outcome = study.read(study.HERE / "known_change_results.json")
    assert outcome["lock"] == study.read(study.HERE / "known_change_lock.json")
    assert [r["name"] for r in outcome["regions"]] == [r["name"] for r in manifest["regions"]]
    for region, result in zip(manifest["regions"], outcome["regions"], strict=True):
        assert [(c["id"], c["expected"]) for c in result["cells"]] == [
            (c["id"], c["expected"]) for c in region["cells"]]
        assert all(bool(c["first_confirmation"]) == c["confirmed"] for c in result["cells"])
