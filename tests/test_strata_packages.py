"""QGIS strata-drawing packages (data/strata_packages/<site>/): the tracked
templates are well-formed, match the config, and only they are tracked."""
import json
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from labelling.strata_style import COLOURS, strata_qml
from labelling.common import load_config

CFG = load_config()
STRATA = CFG["tiles"]["strata"]
SITES = [s for s, a in CFG["aois"].items() if a.get("frame_scene")]
PKG = REPO / "data" / "strata_packages"


def _qml(text):
    root = ET.fromstring(text.split("\n", 1)[1])          # drop the DOCTYPE line
    cats = [c.get("value") for c in root.iter("category")]
    alphas = {s.get("name"): float(s.get("alpha")) for s in root.iter("symbol")}
    colours = [o.get("value") for o in root.iter("Option") if o.get("name") == "color"]
    vmap = [o.get("name") for o in root.find(".//editWidget[@type='ValueMap']").iter("Option")
            if o.get("type") == "QString"]
    return root, cats, alphas, colours, vmap


def test_generated_qml_value_map_and_styles():
    root, cats, alphas, colours, vmap = _qml(strata_qml(STRATA))
    assert root.find("renderer-v2").get("attr") == "stratum"
    assert cats == STRATA + ["unassigned"] and vmap == STRATA + ["unassigned"]
    assert [alphas[str(i)] for i in range(len(STRATA))] == [0.4] * len(STRATA)
    fills = colours[:len(STRATA)]
    assert len(set(fills)) == len(STRATA) == len(COLOURS)
    assert colours[len(STRATA)] == "0,0,0,0"                   # unassigned: outline only
    c = root.find(".//constraint[@field='stratum']")
    assert c.get("notnull_strength") == "1"


@pytest.mark.parametrize("site", SITES)
def test_committed_package_files_match_config(site):
    import geopandas as gpd
    qml = PKG / site / "strata.qml"
    assert qml.exists(), f"{site}: run build_strata_packages.py"
    assert qml.read_text() == strata_qml(STRATA)
    assert not (PKG / site / "strata.geojson").exists()       # superseded by strata.gpkg
    for name in ("strata_draft.gpkg", "strata.gpkg"):
        g = gpd.read_file(PKG / site / name, layer="strata", engine="pyogrio")
        assert g.crs.to_epsg() == int(CFG["aois"][site]["crs"].split(":")[1]), (site, name)
        assert set(g["stratum"]) <= set(STRATA) | {"unassigned"}, (site, name)


def test_only_templates_are_tracked():
    # `git check-ignore` exits 0 even when the deciding pattern is a negation
    # (`!...`), so ask git which files in a built package it actually ignores.
    pkg = PKG / "makoko"
    if not (pkg / "preview.tif").exists():                  # previews are not tracked
        pytest.skip("package not built here; run build_strata_packages.py")
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "--others", "--ignored",
                          "--exclude-standard", "--", str(pkg)],
                         capture_output=True, text=True, check=True).stdout.split()
    ignored = {pathlib.Path(p).name for p in out}
    assert ignored == {"preview.tif", "frame.geojson", "box.geojson", "tile_metrics.json"}
    assert subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q",
                           "data/pipeline_runs/x/result.json"]).returncode == 0   # rest of data/ ignored
