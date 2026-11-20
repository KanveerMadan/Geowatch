"""Checks for dated area evidence, conditional interpretation and sealed evaluation."""
import json

import pytest
from pyproj import CRS
from shapely.geometry import box, mapping

from analysis.change_semantics import Interpreter, attach_interpretations
from analysis.change_surveys import SurveyPairs
from experiments.change_history.validate import evaluate, fit, read_cases


def _feature(role, geom):
    return {"type": "Feature", "properties": {"role": role}, "geometry": mapping(geom)}


def test_gain_loss_on_joint_survey_area(tmp_path):
    for name, coverage, surface in [
        ("a", box(3, 0, 3.003, .001), box(3, 0, 3.0015, .001)),
        ("b", box(3.001, 0, 3.003, .001), box(3.002, 0, 3.003, .001)),
    ]:
        (tmp_path / name).write_text(json.dumps({"type": "FeatureCollection", "features": [
            _feature("coverage", coverage), _feature("surface", surface)]}))
    manifest = tmp_path / "pairs.json"
    manifest.write_text(json.dumps([{"name": "footprints", "source": "synthetic", "license": "test",
                                    "before": {"interval": ["2020-01-01", "2020-01-30"], "file": "a"},
                                    "after": {"date": "2021-03-30", "file": "b"}}]))
    pairs = SurveyPairs(manifest)
    cell = mapping(box(3, 0, 3.004, .001))
    crs = CRS.from_epsg(32631)
    stats = pairs.measure(cell, crs, "2019-12-01", "2021-04-01")["footprints"]
    assert stats["gain_m2"] / stats["joint_area_m2"] == pytest.approx(.5, abs=1e-4)
    assert stats["loss_m2"] / stats["joint_area_m2"] == pytest.approx(.25, abs=1e-4)
    assert stats["net_m2"] == stats["gain_m2"] - stats["loss_m2"]
    assert not pairs.measure(cell, crs, "2020-01-02", "2021-04-01")
    assert not pairs.measure(cell, crs, "2019-12-01", "2021-03-30")


def event(eid, delta, signal="ndvi", day="2023-06-10"):
    return dict(event_id=eid, transition="greenness_loss", detected_on=day, confirmed_on=day,
                last_evidence_on=day, onset={"after": "2023-06-01", "by": day}, detections=2,
                signals=[dict(signal=signal, delta=delta, baseline=.3, threshold=.05, observed_on=day)])


def test_semantics_use_only_context_visible_by_last_observation():
    events = [event("e", -.5), event("r", 1., "vh_db"), event("late", .6, "ndbi", "2023-06-20")]
    attach_interpretations(events, None)
    assert [s["signal"] for s in events[0]["context_signals"]] == ["vh_db"]
    assert not events[-1]["context_signals"]


def test_optional_class_context_compares_the_same_season_track_and_model():
    e = event("x", .5)
    def score(day, orbit, version, value):
        return {"date": day, "source": "dynamic_world", "track": orbit,
                "scenes": [{"dynamicworld_algorithm_version": version}],
                "values": {"dw_bare": value}}
    rows = [score("2022-06-10", "12", "v1", .25), score("2022-05-10", "12", "v1", .8),
            score("2022-06-11", "10", "v1", .75), score("2022-06-11", "12", "v2", .7),
            score("2023-06-10", "12", "v1", .6), score("2023-06-11", "12", "v1", .8)]
    attach_interpretations([e], None, observations=rows, monitoring_start="2023-06-01")
    cover = e["land_cover_context"]["dw_bare"]
    assert cover["seasonal_difference"] == pytest.approx(.35)
    assert cover["dates"] == ["2023-06-10"]


def test_development_fit_and_target_specific_evaluation():
    cases = []
    for i, delta in enumerate([-.8, -.7, -.6, .05, .06, .09]):
        row = {"split": "development", "id": str(i), "region": "r0", "block": "b0",
               "reference": "test", "independent": True, "state": "changed",
               "event_labels": {str(i): "clearing" if delta < 0 else "other"}}
        cases.append((row, {"cell_id": str(i), "period": ["2022-01-01", "2022-12-01"],
                            "events": [event(str(i), delta)]}))
    model = Interpreter(fit(cases))
    assert model.predict(event("x", -0.71))["label"] == "clearing"
    assert model.predict(event("x", -1.4))["label"] == "unknown"
    c = {"split": "heldout", "region": "r1", "block": "b1", "independent": True,
         "state": "stable", "target": "open_water_signal_loss"}
    d = {"period": ["2023-01-01","2024-01-01"], "events": [], "series": [
        {"signal": "vh_db", "status": "observed"}], "cell_id": "unseen"}
    summary = evaluate([(c, d)], model)["overall"]
    assert summary["stable_false_positive_rate_among_judged"] is None
    assert summary["judged_share"] == 0
    with pytest.raises(ValueError, match="overlaps"):
        evaluate([({**c, "region": "r0"}, d)], model)


def test_fit_reads_only_registered_development_detail(tmp_path):
    row = {"id": "a", "cell_id": "c", "region": "r1", "block": "b1", "split": "development",
           "state": "stable", "target": "any", "period": ["2019-01-01", "2020-01-01"],
           "independent": True, "reference": "dated independent survey", "license": "test", "detail": "dev.json"}
    detail = {"cell_id": "c", "period": row["period"], "mode": "prospective", "as_of": "2019-12-31"}
    (tmp_path / "dev.json").write_text(json.dumps(detail))
    sealed = {**row, "id": "b", "cell_id": "d", "region": "r2", "block": "b2", "split": "heldout",
              "period": ["2020-01-01","2021-01-01"], "detail": "intentionally_absent.json"}
    path = tmp_path / "registry.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in (row, sealed)))
    assert len(read_cases(path, "development")) == 1
    path.write_text("\n".join(json.dumps(r) for r in (row, {**sealed, "region": "r1"})))
    with pytest.raises(ValueError, match="region"):
        read_cases(path, "development")



def test_archived_survey_clips_inside_reporting_boundary(tmp_path):
    from types import SimpleNamespace
    from analysis.change_cli import _area
    from analysis.change_history import run_history, zone_summary
    from vector.change_observations import _spatial_tiles
    layer = _area((3., 0., 3.004, .001))
    coverage = box(*layer.bbox)
    for name, footprint in (("a", box(3., 0., 3.001, .001)), ("b", box(3.002, 0., 3.003, .001))):
        data = {"type": "FeatureCollection", "features": [_feature("coverage", coverage),
                                                          _feature("surface", footprint)]}
        (tmp_path / name).write_text(json.dumps(data))
    manifest = tmp_path / "survey.json"
    manifest.write_text(json.dumps([{"name": "buildings", "source": "fixture", "license": "fixture",
                                     "before": {"date": "2020-01-01", "file": "a"},
                                     "after": {"date": "2021-01-01", "file": "b"}}]))
    pairs = SurveyPairs(manifest)
    def provider(*args, **kwargs):
        return SimpleNamespace(tiles=lambda: ({**tile, "observations": [], "diagnostics": []}
                                               for tile in _spatial_tiles(layer)))
    epochs = {"s2": (("2015-01-01", "2016-01-01"), ("2020-01-01", "2022-01-01"))}
    result = run_history(layer, epochs, open_provider=provider, surveys=pairs)
    with result["archive"] as directory:
        geometry = mapping(box(3.002, 0., 3.0025, .001))
        zone = zone_summary(result["block"], geometry, directory + "/history.sqlite", pairs.provenance)
        area = zone["survey_measurements"]["buildings"]
        assert area["gain_m2"] == pytest.approx(zone["zone_area_m2"], rel=1e-5)
        assert area["gain_m2"] == pytest.approx(area["joint_area_m2"])
        assert area["loss_m2"] == 0
