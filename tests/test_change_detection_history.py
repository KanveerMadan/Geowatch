"""The screening contract is chronological and references observed, stable support."""
from datetime import date, timedelta
import json
import math

import pytest

from vector.change_detection import DetectionConfig, detect_cell

START = date(2023, 1, 1)
END = START + timedelta(days=160)


def _value(d, phase=0.0):
    phase += 2 * math.pi * (d - START).days / 365.2425
    return 0.50 + 0.22 * math.cos(phase) - 0.11 * math.sin(2 * phase) + 0.015 * (d - START).days / 365.2425


def _records(shift=None, *, phase=0, source="sentinel2", track="A", support="cell", duration=165):
    shift = shift or (lambda d: 0.0)
    rows = []
    for step in range(-1460, duration, 10):
        day = START + timedelta(days=step)
        rows.append({"date": day.isoformat(), "source": source, "track": track,
                     "support_id": support, "values": {"ndvi": _value(day, phase) + shift(step)}})
    return rows


def _run(rows, **kw):
    kw.setdefault("start", START.isoformat())
    kw.setdefault("end", END.isoformat())
    out = detect_cell("grid/100/200", rows, **kw)
    json.dumps(out, allow_nan=False)
    return out


@pytest.mark.parametrize("phase", [0.0, 2.12])
def test_local_seasons_and_long_term_trend_are_learned_separately(phase):
    out = _run(_records(phase=phase))
    assert out["state"] == "no_change_detected"
    assert out["series"][0]["baseline_trend_per_year"] == pytest.approx(0.015)
    assert out["series"][0]["calibration_count"] > 20


def test_persistent_change_direction_onset_and_rerun_identity():
    rows = _records(lambda d: -0.23 if d >= 10 else 0)
    first = _run(rows, as_of="2023-01-11")["events"][0]
    final = _run(rows)["events"][0]
    assert first["lifecycle"] == "candidate"
    assert final["event_id"] == first["event_id"]
    assert final["transition"] == "greenness_loss"
    assert final["lifecycle"] == "persistent"
    assert final["onset"] == {"after": "2023-01-01", "by": "2023-01-11"}
    assert final["signals"][0]["delta"] == pytest.approx(-0.23)
    assert final["trajectory"] == "sustained"
    assert "area" not in final


def test_same_day_and_common_lineage_cannot_confirm_an_episode():
    rows = _records(lambda d: 0.2 if d == 0 else 0)
    dup = [{**r, "source": "derived", "lineage": "sentinel2"} for r in rows]
    out = _run(rows + list(reversed(rows)) + dup)
    assert out["state"] == "candidate_change"
    assert all(e["detections"] == 1 and e["confirmed_on"] is None for e in out["events"])


def test_independent_sources_confirm_same_signal_same_day():
    a = _records(lambda d: 0.2 if d == 0 else 0)
    b = _records(lambda d: 0.2 if d == 0 else 0, source="landsat8")
    out = _run(a + b)
    e, = out["events"]
    assert e["lifecycle"] == "recovered"
    assert e["confirmed_on"] == START.isoformat()
    assert e["sources"] == ["landsat8", "sentinel2"]
    assert len(e["signals"]) == 2
    assert e["detections"] == 1


def test_missing_dates_and_disjoint_support_abstain():
    rows = _records()
    historical = [r for r in rows if r["date"] < START.isoformat()]
    assert _run(historical)["state"] == "insufficient_observation"
    recent = [{**r, "support_id": "different"} for r in rows if r["date"] >= START.isoformat()]
    assert _run(historical + recent)["state"] == "insufficient_observation"
    recent = [{**r, "coverage": 0} for r in rows if r["date"] >= START.isoformat()]
    assert _run(historical + recent)["state"] == "insufficient_observation"
    sparse = [r for r in rows if r["date"] < START.isoformat() or r["date"] == START.isoformat()]
    assert _run(sparse)["state"] == "insufficient_observation"


def test_annual_confidence_is_context_and_never_building_area():
    rows = [{**r, "source": "open_buildings", "values": {"building_presence": 0.9}}
            for r in _records()]
    out = _run(rows)
    assert out["state"] == "insufficient_observation"
    assert out["series"][0]["status"] == "context_only"
    assert not out["events"]


def test_leap_year_and_sparse_training():
    assert _run([], start="2024-02-29", end="2024-03-31")["state"] == "insufficient_observation"
    winter = [r for r in _records() if int(r["date"][5:7]) < 5 or r["date"] >= START.isoformat()]
    out = _run(winter)
    assert out["series"][0]["reason"] == "incomplete_seasonal_history"


def test_radar_tracks_are_separate_and_geometry_is_required():
    rows = _records(lambda d: 0.2 if d >= 0 else 0)
    rows = [{**r, "source": "sentinel1", "track": "" if i % 2 else "descending",
             "values": {"vv_db": r["values"]["ndvi"] - 10}} for i, r in enumerate(rows)]
    out = _run(rows)
    assert all(s["track"] == "descending" for s in out["series"])
    assert "radar_vv_backscatter" in out["events"][0]["transition"]
    assert out["events"][0]["signals"][0]["unit"] == "dB"


def test_future_data_only_changes_lifecycle_when_retrospective_is_requested():
    rows = _records(lambda d: 0.2 if 0 <= d < 30 else (0.22 if d >= 100 else 0))
    cutoff = (START + timedelta(days=30)).isoformat()
    projected = _run(rows, end=cutoff, as_of=END.isoformat())
    assert projected["events"][0]["lifecycle"] == "corroborated"
    assert projected["as_of"] == "2023-01-30"
    retro = _run(rows, end=cutoff, mode="retrospective", as_of=END.isoformat())
    e, = retro["events"]
    assert e["lifecycle"] == "recovered" and e["trajectory"] == "temporary"
    assert e["recovered_on"] == "2023-02-10"
    assert e["event_id"] == projected["events"][0]["event_id"]
    assert _run(rows, end=cutoff, mode="retrospective")["events"] == projected["events"]


def test_large_gaps_break_continuity_and_cannot_confirm_persistence():
    rows = _records(lambda d: 0.1 if d >= 0 else 0)
    rows = [r for r in rows if r["date"] <= START.isoformat()
            or r["date"] == (START + timedelta(days=100)).isoformat()]
    out = _run(rows)
    assert out["state"] == "candidate_change"
    assert len(out["events"]) == 2
    assert out["series"][0]["status"] == "partial_observation"


def test_progressive_departure_is_distinguished_from_an_abrupt_step():
    rows = _records(lambda d: max(0, d) / 1100)
    e, = _run(rows)["events"]
    assert e["lifecycle"] == "persistent" and e["trajectory"] == "gradual"


def test_concurrent_signal_directions_share_neither_meaning_nor_units():
    rows = _records(lambda d: -0.23 if d > 0 else 0)
    for row in rows:
        d = date.fromisoformat(row["date"])
        row["values"]["mndwi"] = _value(d) + (0.25 if d > START else 0)
    assert {e["transition"] for e in _run(rows)["events"]} == {"open_water_signal_gain", "greenness_loss"}


def test_bad_config_and_date_range():
    with pytest.raises(ValueError):
        DetectionConfig(confirmations=1)
    with pytest.raises(ValueError):
        _run([], start="2023-01-03", end="2023-01-01")


def test_noise_then_a_quiet_observation_then_noise_is_not_confirmation():
    out = _run(_records(lambda d: -0.2 if d in (0, 20) else 0))
    assert out["state"] == "candidate_change"
    assert [e["detections"] for e in out["events"]] == [1, 1]


def test_an_ongoing_shift_cannot_be_redated_as_a_new_query_onset():
    rows = _records(lambda d: 0.20 if -25 <= d < 0 else (0.3 if d >= 0 else 0))
    out = _run(rows)
    assert out["series"][0]["ongoing_at_start"]
    assert out["events"] == []


def test_values_at_a_flat_quantization_floor_do_not_establish_sensitivity():
    rows = _records()
    for r in rows:
        r["values"]["ndvi"] = 0.0 if r["date"] < START.isoformat() else 0.000001
    out = _run(rows)
    assert out["state"] == "insufficient_observation"
    assert out["series"][0]["reason"] == "uninformative_flat_training_signal"


def test_freezing_multichannel_screen_requires_only_past_data():
    rows = _records(lambda d: 0.35 if d >= 20 else 0)
    future = [{**r, "source": "new_sensor"} for r in rows if r["date"] >= "2023-04"]
    before = _run(rows, as_of="2023-02-20")
    after = _run(rows + future)
    assert before["diagnostics"] == after["diagnostics"]
    assert before["events"][0]["confirmed_on"] == after["events"][0]["confirmed_on"]


def test_incomplete_cutoff_and_incompatible_support():
    rows = _records(lambda d: 0.2 if d == 0 else 0)
    b = _records(lambda d: 0.2 if d == 0 else 0, source="landsat8", support="other half")
    assert _run(rows + b)["state"] == "candidate_change"
    assert _run(_records(), as_of="2023-01-25")["state"] == "insufficient_observation"
