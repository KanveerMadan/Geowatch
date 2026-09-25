"""labelling/strata_io.py -- loading hand-drawn strata for tiles.build_frame."""
import json
import pathlib
import sys

import pytest
from shapely.geometry import box, mapping

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from labelling import strata_io, tiles
from labelling.common import load_config

CFG = load_config()
SITE = "makoko"
CRS = CFG["aois"][SITE]["crs"]
X0, Y0 = CFG["aois"][SITE]["box_utm"][:2]


def fc(features, crs=CRS):
    d = {"type": "FeatureCollection", "features": features}
    if crs:
        d["crs"] = {"type": "name", "properties": {"name": f"urn:ogc:def:crs:{crs.replace(':', '::')}"}}
    return d


def poly(stratum, x0, y0, x1, y1):
    return {"type": "Feature", "properties": {"stratum": stratum},
            "geometry": mapping(box(X0 + x0, Y0 + y0, X0 + x1, Y0 + y1))}


def write(tmp_path, d):
    p = tmp_path / "strata.geojson"
    p.write_text(json.dumps(d))
    return str(p)


def test_loads_and_unions_per_stratum(tmp_path):
    p = write(tmp_path, fc([poly("formal", 0, 0, 400, 400), poly("formal", 400, 0, 800, 400),
                            poly("fringe", 0, 400, 800, 800)]))
    strata, rep = strata_io.load_strata(p, SITE, CFG)
    assert set(strata) == {"formal", "fringe"}
    assert strata["formal"].area == pytest.approx(800 * 400)
    assert rep["strata_missing"] == ["dense_informal", "mixed"] and rep["overlaps"] == []


def test_output_feeds_build_frame(tmp_path):
    p = write(tmp_path, fc([poly("formal", 0, 0, 1000, 400), poly("dense_informal", 0, 400, 1000, 800)]))
    strata, _ = strata_io.load_strata(p, SITE, CFG)
    b = (X0, Y0, X0 + 1000, Y0 + 800)
    f = tiles.build_frame(SITE, CRS, b, strata, CFG, frame=box(*b))
    assert {t["stratum"] for t in f["tiles"]} <= {"formal", "dense_informal"}


def test_plain_epsg_crs_name_accepted(tmp_path):
    d = fc([poly("mixed", 0, 0, 200, 200)], crs=None)
    d["crs"] = {"type": "name", "properties": {"name": CRS}}
    strata_io.load_strata(write(tmp_path, d), SITE, CFG)


@pytest.mark.parametrize("crs,match", [(None, "not declared"), ("EPSG:4326", "EPSG:4326"),
                                       ("EPSG:32737", "EPSG:32737")])
def test_wrong_or_missing_crs_rejected(tmp_path, crs, match):
    with pytest.raises(strata_io.StrataError, match=match):
        strata_io.load_strata(write(tmp_path, fc([poly("mixed", 0, 0, 200, 200)], crs=crs)), SITE, CFG)


@pytest.mark.parametrize("value,match", [("slum", "not one of"), (None, "no stratum"),
                                         ("", "no stratum"), ("  ", "no stratum")])
def test_bad_stratum_values_rejected(tmp_path, value, match):
    with pytest.raises(strata_io.StrataError, match=match):
        strata_io.load_strata(write(tmp_path, fc([poly(value, 0, 0, 200, 200)])), SITE, CFG)


def test_missing_stratum_property_rejected(tmp_path):
    f = poly("mixed", 0, 0, 200, 200)
    f["properties"] = {}
    with pytest.raises(strata_io.StrataError, match="no stratum"):
        strata_io.load_strata(write(tmp_path, fc([f])), SITE, CFG)


def test_invalid_geometry_rejected(tmp_path):
    bowtie = {"type": "Feature", "properties": {"stratum": "fringe"},
              "geometry": {"type": "Polygon", "coordinates": [[[X0, Y0], [X0 + 100, Y0 + 100],
                                                               [X0 + 100, Y0], [X0, Y0 + 100], [X0, Y0]]]}}
    with pytest.raises(strata_io.StrataError, match="invalid geometry"):
        strata_io.load_strata(write(tmp_path, fc([bowtie])), SITE, CFG)


def test_null_and_non_polygon_geometry_rejected(tmp_path):
    with pytest.raises(strata_io.StrataError, match="no geometry"):
        strata_io.load_strata(write(tmp_path, fc([{"type": "Feature", "properties": {"stratum": "formal"},
                                                   "geometry": None}])), SITE, CFG)
    line = {"type": "Feature", "properties": {"stratum": "formal"},
            "geometry": {"type": "LineString", "coordinates": [[X0, Y0], [X0 + 10, Y0 + 10]]}}
    with pytest.raises(strata_io.StrataError, match="not a polygon"):
        strata_io.load_strata(write(tmp_path, fc([line])), SITE, CFG)


def test_empty_layer_rejected(tmp_path):
    with pytest.raises(strata_io.StrataError, match="no strata drawn"):
        strata_io.load_strata(write(tmp_path, fc([])), SITE, CFG)


def test_overlap_between_strata_warns_with_area(tmp_path):
    p = write(tmp_path, fc([poly("formal", 0, 0, 400, 400), poly("fringe", 300, 0, 700, 400)]))
    with pytest.warns(strata_io.StrataOverlapWarning, match="overlap by 40000.0 m2"):
        _, rep = strata_io.load_strata(p, SITE, CFG)
    assert rep["overlaps"] == [{"strata": ["formal", "fringe"], "area_m2": 40000.0}]


def test_same_stratum_overlap_is_just_unioned(tmp_path):
    import warnings
    p = write(tmp_path, fc([poly("formal", 0, 0, 400, 400), poly("formal", 300, 0, 700, 400)]))
    with warnings.catch_warnings():
        warnings.simplefilter("error", strata_io.StrataOverlapWarning)
        strata, _ = strata_io.load_strata(p, SITE, CFG)
    assert strata["formal"].area == pytest.approx(700 * 400)
