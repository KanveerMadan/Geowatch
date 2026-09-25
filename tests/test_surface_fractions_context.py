"""Item 21 Phase A, part 6 — OSM sub-type flags, volcano, terrain."""
import copy
import json
import pathlib
import sys

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from surface_fractions import context
from surface_fractions.config import load_config

BBOX = {"west": 10.0, "south": 20.0, "east": 11.0, "north": 21.0}


def layer(status="available", area=None, line=None):
    return {"status": status, "area_fraction": area, "line_touch": line,
            "n_features": {"areas": 1, "lines": 0}, "geometry": "area"}


def all_layers(cfg, **over):
    osm = {}
    for names in cfg["context"]["osm_flags"].values():
        for n in names:
            osm[n] = layer(area=np.zeros((2, 2)))
    osm["salt_flat"] = layer("no_producer")
    osm["dry_lakebed"] = layer("no_producer")
    osm.update(over)
    return osm


def test_flag_is_any_overlap_and_many_coexist_on_one_pixel():
    cfg = load_config()
    park = np.array([[0.1, 0.0], [0.0, 0.0]])
    sand = np.array([[0.5, 0.0], [0.0, 1.0]])
    osm = all_layers(cfg, park=layer(area=park), sand=layer(area=sand))
    out = context.osm_flags(osm, cfg, np.ones((2, 2), bool))
    assert out["arrays"]["osm_park"].tolist() == [[True, False], [False, False]]
    assert out["arrays"]["osm_sand"][0, 0] and out["arrays"]["osm_park"][0, 0]
    assert out["summary"]["bare"]["sand"]["covered_area_share"] == pytest.approx(0.375)


def test_line_layer_flags_touched_pixels():
    cfg = load_config()
    osm = all_layers(cfg, dirt_track=layer(line=np.array([[1, 0], [0, 0]], dtype=np.uint8)))
    out = context.osm_flags(osm, cfg, np.ones((2, 2), bool))
    assert out["arrays"]["osm_dirt_track"].sum() == 1


def test_no_producer_layers_have_no_array():
    cfg = load_config()
    out = context.osm_flags(all_layers(cfg), cfg, np.ones((2, 2), bool))
    assert "osm_salt_flat" not in out["arrays"]
    assert out["summary"]["bare"]["salt_flat"] == {"status": "no_producer"}


def test_pier_quay_is_context_only_not_built():
    cfg = load_config()
    assert "pier_quay" in cfg["context"]["osm_flags"]["other"]
    assert "pier_quay" not in cfg["context"]["osm_flags"]["vegetation"]


def test_volcano_unavailable_without_gvp_file(tmp_path):
    cfg = copy.deepcopy(load_config())
    cfg["context"]["volcano"]["gvp_path"] = str(tmp_path / "missing.geojson")
    v = context.volcano(cfg, BBOX, np.zeros((2, 2)), np.zeros((2, 2)))
    assert v["status"] == "unavailable" and "not present" in v["reason"]


def test_volcano_matches_gvp_points_in_bbox_and_describes_dem(tmp_path):
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [10.5, 20.5]},
         "properties": {"Volcano_Number": 1, "Volcano_Name": "Inside"}},
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [50, 50]},
         "properties": {"Volcano_Number": 2, "Volcano_Name": "Outside"}}]}
    p = tmp_path / "gvp.geojson"
    p.write_text(json.dumps(fc))
    cfg = copy.deepcopy(load_config())
    cfg["context"]["volcano"]["gvp_path"] = str(p)
    dem = np.array([[100.0, 900.0], [300.0, 500.0]])
    v = context.volcano(cfg, BBOX, dem, np.full((2, 2), 12.0))
    assert [m["name"] for m in v["matches"]] == ["Inside"]
    assert v["dem_shape_description"]["elevation_m"]["relief"] == 800.0
    assert v["per_pixel"]["status"] == "not_computed"
    assert "confidence" not in json.dumps(v["matches"])


def test_volcano_reads_csv_export(tmp_path):
    p = tmp_path / "gvp.csv"
    p.write_text("Volcano_Number,Volcano_Name,Latitude,Longitude\n7,Csv,20.1,10.1\n")
    assert context.load_gvp(str(p)) == [{"number": "7", "name": "Csv", "lon": 10.1, "lat": 20.1}]


def test_terrain_not_computed_but_distribution_reported():
    t = context.terrain(load_config(), np.array([[0.0, 10.0]]), np.array([[1.0, 3.0]]))
    assert t["status"] == "not_computed" and t["class_distribution"] is None
    assert t["descriptive_distribution"]["slope_deg"]["p50"] == pytest.approx(2.0)


def test_setting_an_unimplemented_context_criterion_is_refused():
    cfg = copy.deepcopy(load_config())
    context.check_config(cfg)
    cfg["context"]["synthetic_turf_check"]["criterion"] = {"value": 1, "source": "x",
                                                           "status": "UNVALIDATED"}
    with pytest.raises(NotImplementedError):
        context.check_config(cfg)


def test_context_never_touches_fractions_or_denominator():
    cfg = load_config()
    out = context.context_layers(all_layers(cfg), cfg, np.ones((2, 2), bool), BBOX,
                                 np.zeros((2, 2)), np.zeros((2, 2)))
    assert "note" in out["summary"]
    assert not {"built", "paved", "bare", "vegetation", "known"} & set(out["arrays"])
