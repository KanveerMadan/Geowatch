"""SAM-assisted drafting (labelling/sam_draft.py) -- PROPOSAL 2026-09-29. Runs
with a stub predictor, so the 375 MB checkpoint is not needed except for the
hash check (skipped when the checkpoint is absent)."""
import json
import pathlib
import sqlite3
import sys
import xml.etree.ElementTree as ET

import numpy as np
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from labelling import sam_draft as sd
from labelling.gpkg_style import write_gpkg
from labelling.label_style import LAYER, empty_labels_gdf, labels_qml

CRS = "EPSG:32734"


def test_checkpoint_hash_is_recorded_and_verified():
    assert sd.recorded_hash() == "ec2df62732614e57411cdcf32a23ffdf28910380d03139ee0f4fcbe91eb8c912"  # pragma: allowlist secret -- file hash
    if not pathlib.Path(sd.CHECKPOINT).exists():
        pytest.skip("checkpoint not present")
    assert sd.verify_checkpoint() == sd.recorded_hash()


def test_verify_refuses_a_different_file(tmp_path):
    p = tmp_path / "fake.pth"
    p.write_bytes(b"not the model")
    with pytest.raises(sd.SamDraftError, match="does not match"):
        sd.verify_checkpoint(str(p))


def test_window_grid_half_stride_and_pick():
    assert sd.window_starts(4000) == [0, 512, 1024, 1536, 2048, 2560, 2976]
    assert sd.window_starts(800) == [0]
    # a point in the middle of the tile gets a window with >= 256 px margin
    r0, c0, h, w = sd.pick_window(np.array([2000]), np.array([2000]), (4000, 4000))
    assert min(2000 - r0, r0 + h - 1 - 2000, 2000 - c0, c0 + w - 1 - 2000) >= 256
    with pytest.raises(sd.SamDraftError, match="one SAM window"):
        sd.pick_window(np.array([0, 3999]), np.array([0, 3999]), (4000, 4000))


def test_mask_to_polygons_keeps_only_clicked_components():
    from rasterio.transform import from_origin
    m = np.zeros((40, 40), bool)
    m[5:15, 5:15] = True                                   # clicked
    m[25:35, 25:35] = True                                 # not clicked
    t = from_origin(0, 40 * 0.05, 0.05, 0.05)
    polys = sd.mask_to_polygons(m, t, [(0.5, 2.0 - 0.5)], 0.05)
    assert len(polys) == 1 and polys[0].area == pytest.approx(100 * 0.05 ** 2)
    assert sd.mask_to_polygons(m, t, [(1.0, 1.0)], 0.05) == []   # click on background


def test_prompt_style_defaults_next_group_and_positive():
    root = ET.fromstring(sd.prompts_qml().split("\n", 1)[1])
    d = {x.get("field"): x.get("expression") for x in root.iter("default")}
    assert d == {"grp": 'coalesce(maximum("grp"), 0) + 1', "positive": "1"}


class StubPredictor:
    """Stands in for SamPredictor: a fixed 20 x 20 px square mask around the
    first point, score 0.9."""
    def __init__(self):
        import torch
        self.device, self.encoded = "cpu", 0
        self.features = torch.zeros(1)

    def reset_image(self):
        pass

    def set_image(self, img):
        self.encoded += 1
        self.original_size = self.input_size = img.shape[:2]
        self.is_image_set = True

    def predict(self, point_coords, point_labels, multimask_output):
        m = np.zeros(self.original_size, bool)
        x, y = point_coords[0].astype(int)
        m[max(y - 10, 0):y + 10, max(x - 10, 0):x + 10] = True
        n = 3 if multimask_output else 1
        return np.stack([m] * n), np.array([0.9] * n), None


@pytest.fixture
def tile(tmp_path):
    import rasterio
    from rasterio.transform import from_origin
    d = tmp_path / "PRACTICE_x"
    d.mkdir()
    with rasterio.open(d / "hr.tif", "w", driver="GTiff", width=200, height=200, count=3, dtype="uint8",
                       crs=CRS, transform=from_origin(0, 10, 0.05, 0.05)) as dst:
        dst.write(np.full((3, 200, 200), 128, np.uint8))
    write_gpkg(str(d / "labels.gpkg"), empty_labels_gdf(CRS), LAYER, labels_qml(["built"]), geometry_type="Polygon")
    (d / "metadata.json").write_text(json.dumps({"tile_id": "PRACTICE_x"}))
    sd.add_sam_layers(str(d / "labels.gpkg"), CRS)
    return d


def _add_points(d, pts):
    import geopandas as gpd
    import pyogrio
    from shapely.geometry import Point
    g = gpd.GeoDataFrame({"grp": [p[0] for p in pts], "positive": [p[1] for p in pts]},
                         geometry=[Point(p[2], p[3]) for p in pts], crs=CRS)
    pyogrio.write_dataframe(g, str(d / "labels.gpkg"), layer=sd.PROMPTS, append=True)


def test_setup_adds_styled_layers_and_refuses_twice(tile):
    import pyogrio
    gpkg = str(tile / "labels.gpkg")
    assert {r[0] for r in pyogrio.list_layers(gpkg)} == {LAYER, sd.PROMPTS, sd.CANDIDATES, "layer_styles"}
    con = sqlite3.connect(gpkg)
    styled = {r[0] for r in con.execute("SELECT f_table_name FROM layer_styles WHERE useAsDefault = 1")}
    con.close()
    assert styled == {LAYER, sd.PROMPTS, sd.CANDIDATES}
    with pytest.raises(ValueError, match="already exists"):
        sd.add_sam_layers(gpkg, CRS)


def test_draft_writes_candidates_never_labels(tile):
    import pyogrio
    _add_points(tile, [(1, 1, 2.0, 8.0), (2, 1, 7.0, 3.0), (2, 0, 8.0, 3.0)])
    pr = StubPredictor()
    r = sd.draft(str(tile), predictor=pr)
    assert r == {"drafted": [1, 2], "failed": [], "polygons": 2}
    gpkg = str(tile / "labels.gpkg")
    c = pyogrio.read_dataframe(gpkg, layer=sd.CANDIDATES)
    assert c["grp"].tolist() == [1, 2] and c["n_points"].tolist() == [1, 2]
    assert (c["model_sha256"] == sd.recorded_hash()).all()
    assert c.area.round(3).tolist() == [1.0, 1.0]         # 20 x 20 px at 0.05 m
    assert len(pyogrio.read_dataframe(gpkg, layer=LAYER)) == 0
    meta = json.loads((tile / "metadata.json").read_text())
    assert meta["tracing_method"] == "sam_assisted" and meta["sam_assist"]["groups_drafted"] == 2
    # already-drafted groups are not redrafted; the window encoding is cached
    assert sd.draft(str(tile), predictor=pr) == {"drafted": [], "failed": [], "polygons": 0}
    _add_points(tile, [(3, 1, 3.0, 6.0)])
    sd.draft(str(tile), predictor=pr)
    assert pr.encoded == 1 and len(list((tile / "sam_embeddings").iterdir())) == 1


def test_missed_click_is_reported_not_written(tile):
    import pyogrio

    class Empty(StubPredictor):
        def predict(self, point_coords, point_labels, multimask_output):
            return np.zeros((1,) + tuple(self.original_size), bool), np.array([0.5]), None

    _add_points(tile, [(1, 1, 2.0, 8.0)])
    assert sd.draft(str(tile), predictor=Empty()) == {"drafted": [], "failed": [1], "polygons": 0}
    assert len(pyogrio.read_dataframe(str(tile / "labels.gpkg"), layer=sd.CANDIDATES)) == 0
    assert "tracing_method" not in json.loads((tile / "metadata.json").read_text())


def test_group_without_positive_point_refused(tile):
    _add_points(tile, [(1, 0, 2.0, 8.0)])
    with pytest.raises(sd.SamDraftError, match="no positive point"):
        sd.draft(str(tile), predictor=StubPredictor())
