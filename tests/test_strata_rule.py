"""labelling/strata_rule.py (the fabric-strata draft rule) and the .gpkg side
of labelling/strata_io.py (loading, draft-vs-final report)."""
import copy
import pathlib
import sqlite3
import sys

import geopandas as gpd
import pytest
from shapely.geometry import box

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from labelling import strata_io, strata_rule
from labelling.common import load_config
from labelling.strata_style import strata_qml

CFG = load_config()
R = CFG["strata_rule"]
SITE = "kibera"
CRS = CFG["aois"][SITE]["crs"]
X0, Y0 = CFG["aois"][SITE]["box_utm"][:2]


def m(n=50, cov=0.2, med=70.0, cv=0.9):
    return {"n": n, "coverage": cov, "area_median": med, "area_cv": cv}


# ── the rule ────────────────────────────────────────────────────────────────

def test_thresholds_are_the_approved_values_each_with_a_reason():
    want = {"unassigned_min_buildings": 5, "fringe_coverage_max": 0.10,
            "dense_informal_coverage_min": 0.35, "dense_informal_median_area_max_m2": 80.0,
            "formal_median_area_min_m2": 100.0, "formal_area_cv_max": 0.5}
    for k, v in want.items():
        assert R[k]["value"] == v, k
        assert len(R[k]["reason"]) > 20, k
    assert "merges adjoining informal roofs" in R["dense_informal_median_area_max_m2"]["reason"]
    assert R["empty_stratum_policy"] == "skip_per_site_require_across_training_set"


@pytest.mark.parametrize("metrics,want", [
    (m(n=4, cov=0.9, med=30), "unassigned"),                 # too few, whatever else
    (m(n=5, cov=0.09), "fringe"),
    (m(cov=0.35, med=79.9), "dense_informal"),               # 0.35 inclusive, 80 exclusive
    (m(cov=0.35, med=80.0, cv=0.9), "mixed"),
    (m(cov=0.20, med=100.0), "formal"),                      # 100 inclusive
    (m(cov=0.20, med=60.0, cv=0.5), "formal"),               # cv 0.5 inclusive
    (m(cov=0.20, med=60.0, cv=0.51), "mixed"),
    (m(cov=0.10, med=60.0, cv=0.9), "mixed"),                # 0.10 is not fringe
    (m(cov=0.50, med=30.0, cv=0.3), "dense_informal"),       # dense wins over formal (order)
    (m(cov=0.20, med=60.0, cv=None), "mixed"),
])
def test_rule_branches_boundaries_and_order(metrics, want):
    assert strata_rule.assign(metrics, CFG) == want


def test_frame_tiles_only_whole_tiles_inside_the_frame():
    frame = box(0, 0, 500, 400)
    assert sorted(strata_rule.frame_tiles(frame)) == [(0, 200), (0, 400), (200, 200), (200, 400)]


# ── draft -> gpkg ───────────────────────────────────────────────────────────

def metrics_grid():
    x0 = (int(X0) // 200 + 1) * 200
    y1 = (int(Y0) // 200 + 3) * 200
    return [dict(x0=x0, y1=y1, **m(n=100, cov=0.5, med=40)),
            dict(x0=x0 + 200, y1=y1, **m(n=100, cov=0.2, med=150)),
            dict(x0=x0, y1=y1 - 200, **m(n=2)),
            dict(x0=x0 + 200, y1=y1 - 200, **m(n=30, cov=0.05))]


def write_pair(tmp_path):
    gdf = strata_rule.draft_frame(SITE, CFG, metrics_grid())
    d = strata_rule.write_strata_gpkg(str(tmp_path / "strata_draft.gpkg"), gdf, strata_qml(CFG["tiles"]["strata"]))
    f = strata_rule.write_strata_gpkg(str(tmp_path / "strata.gpkg"), gdf, strata_qml(CFG["tiles"]["strata"]))
    return d, f


def test_gpkg_layer_fields_crs_and_default_style(tmp_path):
    d, _ = write_pair(tmp_path)
    g = gpd.read_file(d, layer="strata", engine="pyogrio")
    assert list(g.columns) == strata_rule.FIELDS + ["geometry"]
    assert g.crs.to_epsg() == int(CRS.split(":")[1])
    assert list(g["stratum"]) == ["dense_informal", "formal", "unassigned", "fringe"]
    assert (g["stratum"] == g["draft_stratum"]).all()
    con = sqlite3.connect(d)
    name, default, qml = con.execute("SELECT f_table_name, useAsDefault, styleQML FROM layer_styles").fetchone()
    registered = con.execute("SELECT data_type FROM gpkg_contents WHERE table_name='layer_styles'").fetchone()
    con.close()
    assert (name, default, registered) == ("strata", 1, ("attributes",))
    assert 'editWidget type="ValueMap"' in qml and 'value="unassigned"' in qml


# ── strata_io on gpkg ───────────────────────────────────────────────────────

def test_load_gpkg_excludes_unassigned(tmp_path):
    _, f = write_pair(tmp_path)
    strata, rep = strata_io.load_strata(f, SITE, CFG)
    assert sorted(strata) == ["dense_informal", "formal", "fringe"]
    assert rep["unassigned_features"] == 1 and rep["strata_missing"] == ["mixed"]


def test_gpkg_in_wrong_crs_rejected(tmp_path):
    gdf = strata_rule.draft_frame(SITE, CFG, metrics_grid()).to_crs("EPSG:4326")
    p = strata_rule.write_strata_gpkg(str(tmp_path / "strata.gpkg"), gdf, "")
    with pytest.raises(strata_io.StrataError, match="EPSG:4326"):
        strata_io.load_strata(p, SITE, CFG)


def test_all_unassigned_rejected(tmp_path):
    gdf = strata_rule.draft_frame(SITE, CFG, [dict(x0=1000.0, y1=1200.0, **m(n=0))])
    p = strata_rule.write_strata_gpkg(str(tmp_path / "strata.gpkg"), gdf.set_crs(CRS, allow_override=True), "")
    with pytest.raises(strata_io.StrataError, match="nothing to sample"):
        strata_io.load_strata(p, SITE, CFG)


def test_bad_stratum_value_in_gpkg_rejected(tmp_path):
    gdf = strata_rule.draft_frame(SITE, CFG, metrics_grid())
    gdf.loc[0, "stratum"] = "slum"
    p = strata_rule.write_strata_gpkg(str(tmp_path / "strata.gpkg"), gdf, "")
    with pytest.raises(strata_io.StrataError, match="not one of"):
        strata_io.load_strata(p, SITE, CFG)


def test_draft_vs_final_report(tmp_path):
    d, f = write_pair(tmp_path)
    g = gpd.read_file(f, layer="strata", engine="pyogrio")
    g.loc[g["stratum"] == "dense_informal", "stratum"] = "formal"      # small formal housing
    g.loc[g["stratum"] == "unassigned", "stratum"] = "fringe"
    strata_rule.write_strata_gpkg(f, g, "")
    rep = strata_io.compare_draft_final(d, f, SITE, CFG)
    assert rep["tiles"] == 4 and rep["changed"] == 2
    assert rep["transitions"] == {"dense_informal -> formal": 1, "unassigned -> fringe": 1}
    assert rep["added"] == rep["removed"] == rep["geometry_changed"] == []


def test_identical_draft_and_final_report_no_change(tmp_path):
    d, f = write_pair(tmp_path)
    assert strata_io.compare_draft_final(d, f, SITE, CFG)["changed"] == 0


def test_rewrite_refuses_to_clobber_a_hand_edited_final(tmp_path, monkeypatch):
    d, f = write_pair(tmp_path)
    g = gpd.read_file(f, layer="strata", engine="pyogrio")
    g.loc[0, "stratum"] = "mixed"
    strata_rule.write_strata_gpkg(f, g, "")
    monkeypatch.setattr(strata_rule, "_package", lambda site: str(tmp_path))
    monkeypatch.setattr(strata_rule, "compute_tile_metrics",
                        lambda *a, **k: pytest.fail("must refuse before recomputing"))
    with pytest.raises(RuntimeError, match="hand edits"):
        strata_rule.write_site(SITE, CFG)
