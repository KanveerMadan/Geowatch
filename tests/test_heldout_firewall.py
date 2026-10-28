"""
Build item 27 -- the held-out firewall.

Acceptance: the split is recorded in a file, hashed, and the training path
raises if it reads a held-out record. Held out by validation site: the
hand-traced fraction tiles of Makoko, Kibera and Rocinha (sealed batches 1
and 2), and anything naming their host cities Lagos, Nairobi and Rio.

Nothing here reads real label or tile data: record paths are path strings
only, and the training-path tests build their tiles in tmp_path.

Run from the repo root:  pytest tests/test_heldout_firewall.py
"""
import hashlib
import json

import pytest

from experiments.harness import firewall
from experiments.harness.firewall import HeldOutError, SplitHashError

# The 8 Stage 1 training tiles (data/stage1/selection.json), as <site>/<tile_id>.
STAGE1 = [("cape_town", "EPSG32734_282400_6233800"), ("cape_town", "EPSG32734_284000_6234600"),
          ("karachi", "EPSG32642_297600_2761800"), ("karachi", "EPSG32642_297800_2761000"),
          ("lima", "EPSG32718_290000_8659000"), ("lima", "EPSG32718_290600_8659200"),
          ("monrovia", "EPSG32629_300800_699600"), ("monrovia", "EPSG32629_301000_699800")]
CLEAN = [f"data/stage1/tiles/{s}/{t}/labels.gpkg" for s, t in STAGE1] + [
    {"site": "lima", "tile_id": "EPSG32718_290000_8659000"},
    {"city": "cape_town"},
]

HELD_OUT = [
    pytest.param("data/stage1/tiles/kibera/EPSG32737_256000_9854000/labels.gpkg", id="kibera-tile"),
    pytest.param("/elsewhere/gw-x/data/stage1/tiles/makoko/EPSG32631_541000_720000", id="makoko-other-root"),
    pytest.param("labels/validation/rocinha/batch_2/EPSG32723_682000_7457000/v1.json", id="rocinha-batch-2"),
    pytest.param("labels/validation/somewhere/batch_1/x/v1.json", id="any-sealed-batch"),
    pytest.param({"site": "Makoko", "tile_id": "EPSG32631_541000_720000"}, id="makoko-record"),
    pytest.param({"tile_id": "EPSG32737_256000_9854000"}, id="kibera-tile-id-alone"),
    pytest.param("data/stage1/tiles/cape_town/EPSG32723_682000_7457000/labels.gpkg", id="rocinha-tile-misfiled"),
    pytest.param({"city": "nairobi"}, id="host-city"),
]


# ── The split file is recorded and hashed ──────────────────────────────

def test_split_matches_its_recorded_hash():
    raw = firewall.SPLIT_PATH.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == firewall.recorded_hash()
    split = firewall.load_split()
    assert set(split["sites"]) == {"makoko", "kibera", "rocinha"}


def test_edited_split_is_refused(tmp_path):
    edited = tmp_path / "heldout_split.json"
    split = json.loads(firewall.SPLIT_PATH.read_text())
    split["path_patterns"].remove("kibera")
    edited.write_text(json.dumps(split))
    with pytest.raises(SplitHashError):
        firewall.load_split(edited)


def test_split_without_a_recorded_hash_is_refused(tmp_path):
    hashes = tmp_path / "ARTIFACT_HASHES.txt"
    hashes.write_text("0" * 64 + "  models//sam/sam_vit_b.pth\n")
    with pytest.raises(SplitHashError):
        firewall.load_split(hashes_path=hashes)


def test_split_documents_the_full_raster_rule():
    """08_STATE.md §RETIRED, carried lesson 1."""
    notes = " ".join(firewall.load_split()["notes"])
    assert "FULL RASTER, not from annotated segments" in notes


# ── One held-out record raises; a clean set passes ─────────────────────

@pytest.mark.parametrize("record", HELD_OUT)
def test_training_set_with_one_held_out_record_raises(record):
    with pytest.raises(HeldOutError):
        firewall.assert_training_set(CLEAN + [record])


def test_clean_training_set_passes():
    firewall.assert_training_set(CLEAN)


def test_names_that_only_resemble_a_held_out_site_pass():
    firewall.assert_training_set(["data/notes/kibera_reading_list.md",
                                  {"site": "makoko_practice"}])


# ── The training path raises ───────────────────────────────────────────

def _tiles(root, pairs):
    """Stage 1-layout tile dirs, each with an (empty) labels.gpkg."""
    dirs = []
    for site, tid in pairs:
        d = root / "data" / "stage1" / "tiles" / site / tid
        d.mkdir(parents=True)
        (d / "labels.gpkg").write_bytes(b"")
        dirs.append(d)
    return dirs


def test_training_on_the_stage1_tiles_passes(tmp_path):
    out = firewall.training_tiles(_tiles(tmp_path, STAGE1))
    assert [(r["site"], r["tile_id"]) for r in out] == STAGE1


@pytest.mark.parametrize("site,tid", [("kibera", "EPSG32737_256000_9854000"),
                                      ("rocinha", "EPSG32723_682000_7457000"),
                                      ("makoko", "EPSG32631_541000_720000"),
                                      ("lima", "EPSG32631_541000_720000")])
def test_training_on_a_set_with_one_validation_tile_raises(tmp_path, site, tid):
    dirs = _tiles(tmp_path, STAGE1 + [(site, tid)])
    with pytest.raises(HeldOutError):
        firewall.training_tiles(dirs)


def test_training_refuses_a_sealed_batch_tile(tmp_path):
    clean = _tiles(tmp_path, STAGE1)
    sealed = tmp_path / "labels" / "validation" / "rocinha" / "batch_1" / "EPSG32723_682000_7457000"
    sealed.mkdir(parents=True)
    (sealed / "labels.gpkg").write_bytes(b"")
    with pytest.raises(HeldOutError):
        firewall.training_tiles(clean + [sealed])


def test_a_held_out_tile_is_refused_before_any_file_is_touched(tmp_path):
    """The set is checked before labels are looked for: a held-out tile with
    no labels raises HeldOutError, not FileNotFoundError."""
    missing = tmp_path / "data" / "stage1" / "tiles" / "kibera" / "EPSG32737_256000_9854000"
    with pytest.raises(HeldOutError):
        firewall.training_tiles(_tiles(tmp_path, STAGE1) + [missing])
