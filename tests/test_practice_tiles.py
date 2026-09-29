"""Item 21 §9 pilot C practice tiles (data/practice_tiles/<tile>/): outside
every frame, marked PRACTICE, refused by the label store, with an empty
label layer whose QGIS style is the default."""
import json
import pathlib
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest
from shapely.geometry import box

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "experiments" / "item21_sites"))

from labelling import records
from labelling.common import load_config
from labelling.label_style import COLOURS, FIELDS, LAYER, labels_qml
import prepare_practice_tiles as ppt

CFG = load_config()
LABELS = CFG["labels"]["scored"] + CFG["labels"]["excluded"]
ROOT = REPO / "data" / "practice_tiles"
TILES = sorted(ppt.TILES)


def test_label_qml_value_map_colours_and_checkboxes():
    root = ET.fromstring(labels_qml(LABELS).split("\n", 1)[1])
    assert root.find("renderer-v2").get("attr") == "label"
    assert [c.get("value") for c in root.iter("category")] == LABELS
    vmap = [o.get("name") for o in root.find(".//editWidget[@type='ValueMap']").iter("Option")
            if o.get("type") == "QString"]
    assert vmap == LABELS
    assert {s.get("alpha") for s in root.iter("symbol")} == {"0.4"}
    assert set(LABELS) <= set(COLOURS)
    boxes = [f.get("name") for f in root.iter("field") if f.find("editWidget").get("type") == "CheckBox"]
    assert boxes == ["shadow_partial", "rooftop_solar"]
    assert root.find(".//constraint").get("field") == "label"


def test_practice_tiles_lie_outside_every_box():
    for spec in ppt.TILES.values():
        ppt.check_outside_every_frame(box(spec["x0"], spec["y1"] - 200, spec["x0"] + 200, spec["y1"]), CFG)
    a = CFG["aois"]["cape_town"]
    with pytest.raises(ValueError, match="cape_town"):
        x0, y0 = a["box_utm"][0], a["box_utm"][1]
        ppt.check_outside_every_frame(box(x0, y0, x0 + 200, y0 + 200), CFG)


def test_practice_site_is_refused_by_the_label_store():
    with pytest.raises(records.RecordError, match="not in the item 21 site list"):
        records.site_role("practice", CFG)


@pytest.mark.parametrize("name", TILES)
def test_prepared_tile_metadata_and_empty_styled_label_layer(name):
    d = ROOT / name
    if not (d / "metadata.json").exists():
        pytest.skip("practice tiles not prepared")
    meta = json.loads((d / "metadata.json").read_text())
    assert meta["site"] == "practice" and meta["tile_id"].startswith("PRACTICE_")
    assert meta["qc_status"] == "PRACTICE" and "never scored, never used in training" in meta["purpose"]
    import pyogrio
    info = pyogrio.read_info(str(d / "labels.gpkg"), layer=LAYER)
    assert list(info["fields"]) == FIELDS and info["geometry_type"] == "Polygon"
    assert info["crs"] == ppt.CRS
    con = sqlite3.connect(str(d / "labels.gpkg"))
    try:
        (default, qml), = con.execute("SELECT useAsDefault, styleQML FROM layer_styles WHERE f_table_name = ?",
                                      (LAYER,))
        assert (default, qml) == (1, labels_qml(LABELS))
        assert con.execute("SELECT 1 FROM gpkg_contents WHERE table_name='layer_styles'").fetchone()
    finally:
        con.close()


def test_only_label_layer_and_metadata_are_tracked():
    tracked = subprocess.run(["git", "ls-files", "data/practice_tiles"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout.split()
    assert all(pathlib.PurePath(p).name in {"labels.gpkg", "metadata.json"} for p in tracked)
