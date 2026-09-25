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

from experiments.item21_sites.build_strata_packages import COLOURS, strata_qml
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
    assert cats == STRATA and vmap == STRATA
    assert set(alphas.values()) == {0.4}
    assert len(set(colours)) == len(STRATA) == len(COLOURS)
    c = root.find(".//constraint[@field='stratum']")
    assert c.get("notnull_strength") == "1"


@pytest.mark.parametrize("site", SITES)
def test_committed_templates_match_config(site):
    qml = PKG / site / "strata.qml"
    tmpl = PKG / site / "strata.geojson"
    assert qml.exists() and tmpl.exists(), f"{site}: run build_strata_packages.py"
    assert qml.read_text() == strata_qml(STRATA)
    fc = json.loads(tmpl.read_text())
    assert fc["type"] == "FeatureCollection" and fc["features"] == []
    want = CFG["aois"][site]["crs"].replace(":", "::")
    assert fc["crs"]["properties"]["name"] == f"urn:ogc:def:crs:{want}"


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
    assert ignored == {"preview.tif", "frame.geojson", "box.geojson"}
    assert subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q",
                           "data/pipeline_runs/x/result.json"]).returncode == 0   # rest of data/ ignored
