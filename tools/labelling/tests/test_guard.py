import json
from pathlib import Path

import pytest

from tools.labelling import guard


@pytest.mark.parametrize("tail", ["Makoko/x", "test/NAIROBI/x", "test/Rio/x",
    "VALIDATION/karachi/batch_2/x", "karachi/EPSG32631_1200_1200", "Lagos/x",
    "rocinha/x", "kibera/x", "karachi/EPSG32723_200_200"])
def test_firewall_blocks_before_reading_tile_or_raster(tmp_path, monkeypatch, tail):
    p=tmp_path/tail
    p.mkdir(parents=True)
    monkeypatch.setattr(guard,"inspect_raster_header",lambda *args: pytest.fail("opened image"))
    with pytest.raises(guard.TileRefused,match="firewall"):
        guard.authorize_tile(p)


def test_fake_training_identity_or_image_is_refused(tmp_path,monkeypatch):
    name="PRACTICE_formal"
    p=tmp_path/name
    p.mkdir()
    meta=guard.load(guard.ROOT/"data/practice_tiles"/name/"metadata.json")
    (p/"metadata.json").write_text(json.dumps(dict(meta,source_site="makoko")))
    with pytest.raises(guard.TileRefused,match="firewall"):
        guard.authorize_tile(p)
    (p/"metadata.json").write_text(json.dumps(meta))
    monkeypatch.setattr(guard,"inspect_raster_header",lambda _:("EPSG:32631",(0,0,200,200)))
    with pytest.raises(guard.TileRefused,match="footprint"):
        guard.authorize_tile(p)


def test_new_registry_and_symlink_cannot_bypass(tmp_path,monkeypatch):
    p=tmp_path/"PRACTICE_formal"
    p.mkdir()
    q=tmp_path/"configs"
    q.mkdir()
    rules=guard.load(guard.HERE/"heldout_split.json")
    rules["tile_id_patterns"].append("PRACTICE_formal")
    (q/"heldout_split.json").write_text(json.dumps(rules))
    with pytest.raises(guard.TileRefused,match="firewall"):
        guard.authorize_tile(p)
    (q/"heldout_split.json").write_text(json.dumps(guard.load(guard.HERE/"heldout_split.json")))
    (p/"hr.tif").symlink_to(tmp_path/"somewhere_else.tif")
    with pytest.raises(guard.TileRefused,match="linked"):
        guard.authorize_tile(p)
