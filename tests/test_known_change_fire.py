from datetime import date

from experiments.change_history import known_change_fire as fires


def test_fire_scene_identification_rejects_sentinel_and_bad_dates():
    assert fires.parse_scene("804403220200708") == ("8", "LC08_044032_20200708", date(2020, 7, 8))
    assert fires.parse_scene("B13TEK20230725_30m") is None
    assert fires.parse_scene("904403220220230") is None


def test_incident_sampling_is_order_independent_within_geography():
    rows = [{"id":f"incident-{n}","stratum":f"group-{n%2}"} for n in range(14)]
    rows += [{"id":"sole-incident","stratum":"third"}]
    selected = fires.assignment([r.copy() for r in rows])
    assert selected == fires.assignment([r.copy() for r in reversed(rows)])
    assert sum(r["split"]=="test" for r in selected) == 7
    assert [r["split"] for r in selected if r["id"]=="sole-incident"] == ["test"]


def test_fire_no_measurement_is_unresolved_and_retained():
    outcome = fires.score({"id":"x","stratum":"east_north","name":"test","ignition":"2022-07-01"}, [])
    assert outcome["first_usable"] is None
    assert outcome["days_since_ignition"] is None
    assert not outcome["confirmed"] and not outcome["partially_or_fully_observed"]


def test_amended_fire_receipts_preserve_incidents_and_validate_physical_cells():
    from experiments.change_history import fire_support_replay as replay

    original = [row for row in fires.paired.read(fires.MANIFEST)["incidents"] if row["split"] == "test"]
    manifest = fires.paired.read(replay.MANIFEST)
    outcome = fires.paired.read(replay.RESULT)
    assert manifest["seal"] == replay.seal()
    assert outcome["manifest_sha256"] == fires.paired.digest(replay.MANIFEST)
    for old, ref, result in zip(original, manifest["incidents"], outcome["incidents"], strict=True):
        assert old["id"] == ref["id"] == result["id"]
        assert ref["original_xy"] == old["xy"]
        assert old["ignition"] == result["ignition"]
        if result["reference_eligible"]:
            assert ref["verified"] == {"count": 25, "inside": True}
            assert all(v % 100 == 0 for v in ref["xy"])
        else:
            assert ref["xy"] is None
            assert result["confirmed"] is False
