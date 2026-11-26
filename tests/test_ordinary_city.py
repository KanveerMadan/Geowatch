import pytest

from experiments.change_history import ordinary_city as study


def test_locked_frame_has_all_sites_and_months():
    plan = study.lock()
    schedule = [r for s in plan["sites"] for r in study.schedule(s)]
    assert len(schedule) == len({(r["cell"], r["start"]) for r in schedule}) == 2592
    assert all(r["cell"].startswith("EPSG:327") for r in schedule if r["site"] == "jakarta")
    assert {"state", "confirmed", "jrc_before"}.isdisjoint(schedule[0])


def test_reference_requires_paired_complete_observations():
    assert study.ref_direction([24, 0], [25, 25]) is None
    assert study.ref_direction([25, 5], [25, 6]) == "gain"
    assert study.ref_direction([25, 25], [25, 25]) == "stable"


def test_reference_and_adjudication_have_different_denominators():
    rows = [
        dict(site="city", cell=str(i), start="2021-01-01", candidates=0,
             complete=i != 2, water_complete=i != 2,
             confirmed=[["open_water_signal_gain"]] if i != 2 else [],
             jrc_direction=d)
        for i, d in enumerate(("gain", None, "loss"))
    ]
    count = study.metrics(rows)
    assert count["counts"]["jrc_reference_pairs"] == 2
    assert count["water_proxy"]["all_reference"]["loss"]["fn"] == 1
    assert count["water_proxy"]["observable_and_reference"]["loss"]["fn"] == 0
    label = dict(site="city", cell="0", start="2021-01-01", target="water", verdict="stable",
                 prediction_blind=True, evidence_source="survey", evidence_id="id",
                 reviewer="reviewer", independent_of_sentinel2=True)
    joined = study.reviewed_metrics(rows, [label])
    assert joined["water"]["false_alerted_cells_per_plot_month_bounds"] == [1, 2]
    assert joined["water"]["counts"]["unresolved_confirmations"] == 1
    with pytest.raises(ValueError, match="duplicate"):
        study.reviewed_metrics(rows, [label, label])
    with pytest.raises(ValueError, match="independent dated evidence"):
        study.reviewed_metrics(rows, [dict(label, independent_of_sentinel2=False)])


def test_shadow_wall_clock_and_immutable_first_receipt():
    from datetime import datetime, timezone
    import sqlite3
    from experiments.change_history.ordinary_city_shadow import monitoring_dates, record
    start, end, cutoff = monitoring_dates(datetime(2026, 3, 1, 0, 0, tzinfo=timezone.utc))
    assert [d.isoformat() for d in (start, end, cutoff)] == ["2026-02-01","2026-03-01","2026-02-28"]
    with sqlite3.connect(":memory:") as db:
        snap = {"site":"x","acquisition_cutoff":"2026-01-02","received_until_utc":"first"}
        events = [("cell",{"event_id":"a"})]
        assert record(db,snap,events)["newly_logged_signal_episodes"] == 1
        assert record(db,dict(snap,received_until_utc="later"),events)["received_until_utc"] == "first"
        assert record(db,dict(snap,acquisition_cutoff="2026-01-03"),events)["newly_logged_signal_episodes"] == 0


def test_published_ordinary_summaries_can_be_rebuilt_offline():
    from collections import defaultdict
    import gzip
    import json

    from experiments.change_history import ordinary_city_default as default

    for prefix, aggregate, expected in (("ordinary_city", study.metrics, 2592),
                                         ("ordinary_city_default", default.summary, 576)):
        with gzip.open(study.HERE / (prefix + "_predictions.jsonl.gz"), "rt") as stream:
            rows = [json.loads(line) for line in stream]
        result = json.loads((study.HERE / (prefix + "_result.json")).read_text())
        assert len(rows) == len({(r["site"], r["cell"], r["start"]) for r in rows}) == expected
        assert result["pooled"] == aggregate(rows)
        by_site = defaultdict(list)
        for row in rows:
            by_site[row["site"]].append(row)
        assert result["per_site"] == {site:aggregate(sample) for site,sample in by_site.items()}


def test_review_sample_keeps_case_ids_blinded_and_matches_groups():
    from collections import Counter
    import json
    from experiments.change_history import ordinary_city_visual as visual

    rows = visual.sample()
    assert len(rows) == len({visual.blind_id(row) for row in rows}) == 18
    positives = Counter()
    controls = Counter()
    for row in rows:
        group = positives if any(e[0].startswith("open_water_signal") for e in row["confirmed"]) else controls
        group[(row["site"], row["start"])] += 1
    assert positives == controls
    evidence = json.loads((study.HERE / "ordinary_city_visual_result.json").read_text())
    for label in evidence:
        assert label["blind_id"] == visual.blind_id(label)
        if label["verdict"] == "stable":
            assert len({ident[-8:] for ident in label["evidence_id"]["during"]}) >= 2
            assert label["evidence_id"]["prior"]
