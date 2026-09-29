"""Item 21 Stage 1 tiles prepared for tracing (data/stage1/tiles/): one per
selected tile, an empty styled label layer, and a tile record that carries
the frozen change-test result and the acquisition-time handling."""
import json
import pathlib
import sqlite3
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from labelling.common import load_config
from labelling.label_style import FIELDS, LAYER, labels_qml

CFG = load_config()
SEL = REPO / "data" / "stage1" / "selection.json"
ROOT = REPO / "data" / "stage1" / "tiles"


def _tiles():
    if not SEL.exists():
        return []
    sel = json.loads(SEL.read_text())
    return [(site, r["chosen"]) for site, s in sel["sites"].items() for r in s["strata"].values()]


@pytest.mark.parametrize("site,chosen", _tiles(), ids=lambda v: v if isinstance(v, str) else v["tile_id"])
def test_prepared_tile(site, chosen):
    d = ROOT / site / chosen["tile_id"]
    if not (d / "metadata.json").exists():
        pytest.skip("tile not prepared")
    meta = json.loads((d / "metadata.json").read_text())
    assert (meta["site"], meta["tile_id"], meta["stratum"]) == (site, chosen["tile_id"], chosen["stratum"])
    assert meta["tile_utm"]["crs"] == CFG["aois"][site]["crs"]
    assert (meta["tile_utm"]["x0"], meta["tile_utm"]["y1"]) == (chosen["x0"], chosen["y1"])
    assert meta["guide_version"] == CFG["guide_version"] and meta["tracing_method"] == "manual"
    assert meta["change_test_result"].startswith("kept:")
    assert meta["date_gap_days"] <= CFG["open"]["max_date_gap_days"]["per_site"][site]
    assert meta["s2_clear_scenes"] >= CFG["open"]["max_date_gap_days"]["min_clear_scenes"]
    assert meta["hr_valid_share"] > 0
    # time: publisher metadata (Karachi), else sun from shadows (v1.6: OAM
    # uploader windows are not publisher metadata)
    if site == "karachi":
        assert meta["sun_geometry_required"] is False and meta["imagery_acquisition_time"]
    else:
        assert meta["sun_geometry_required"] is True and (d / "sun.gpkg").exists()
        assert meta["imagery_acquisition_time"] is None
    if site in ("lima", "monrovia"):
        assert meta["uploader_window_utc"] and not meta["published_times"]
    if site == "karachi":
        assert "BASE" in meta["labelling_note"]
    import pyogrio
    info = pyogrio.read_info(str(d / "labels.gpkg"), layer=LAYER)
    assert list(info["fields"]) == FIELDS and info["crs"] == CFG["aois"][site]["crs"]
    con = sqlite3.connect(str(d / "labels.gpkg"))
    try:
        (qml,), = con.execute("SELECT styleQML FROM layer_styles WHERE f_table_name = ? AND useAsDefault = 1",
                              (LAYER,))
    finally:
        con.close()
    assert qml == labels_qml(CFG["labels"]["scored"] + CFG["labels"]["excluded"])


def test_only_labeller_layers_and_records_are_tracked():
    tracked = subprocess.run(["git", "ls-files", "data/stage1/tiles"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout.split()
    assert all(pathlib.PurePath(p).name in {"labels.gpkg", "metadata.json", "sun.gpkg"} for p in tracked)
