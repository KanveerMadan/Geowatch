r"""
C10 regression tests — deployed CAAT thresholds had no provenance.

04_FINDINGS_LEDGER.md C10 [E], build item 45: a live run logged
`Loaded CAAT thresholds (source_checkpoint=?, verified_sanity_check_miou=?)`.
Two loaders existed:

  * `ingestion/inference.py:load_caat_thresholds` — what pipeline.py:262 actually
    called. Checked category alignment, and for provenance merely PRINTED
    `data.get('source_checkpoint', '?')`. That `?` is the finding.
  * `ingestion/resnet_classifier.py:load_production_model` — required
    `source_checkpoint` and compared it against the checkpoint being loaded, and
    would have rejected the deployed file. Dead code; nothing imported it.

Item 45's decided fork: promote the strict one, delete the weak one, do not
maintain both. Two validators is how a run logs `source_checkpoint=?` in the
first place.

WHY A MISMATCH IS DANGEROUS RATHER THAN MERELY WRONG. CAAT thresholds are
quantiles of one model's confidence distribution. Applied to a different model
they still produce plausible per-class numbers and never throw — they shift the
unknown/confident boundary silently, so the damage presents as a property of the
scene. Nothing downstream can detect it. That is why this refuses rather than
warns.

THE CHECK IS A CONTENT HASH, NOT A FILENAME. The dead validator compared
`os.path.basename(source_checkpoint)`, which passes for any file sharing a name
— including a retrained checkpoint written to the same path, which is the
realistic failure. Hashing the 133 MB production checkpoint takes 0.07s.

THE DEPLOYED FILE IS EXPECTED TO FAIL. models/production/caat_thresholds.json
carries no `source_checkpoint` key at all, and its own caveat records that it
"derived from 11 separate LOCO fold models (each missing one city), NOT from the
production checkpoint." test_deployed_caat_file_is_refused asserts that refusal
as CORRECT BEHAVIOUR. If that test ever starts failing because someone relaxed
the validator, that is the regression — not the refusal.

Run from the repo root:  pytest tests/test_caat_provenance.py
"""

import json
import os

import numpy as np
import pytest

from ingestion.inference import (
    CAAT_SOURCE_HASH_KEY,
    CaatProvenanceError,
    load_caat_thresholds,
    sha256_file,
)

CATEGORIES = [
    "dense_informal_roofing", "sparse_informal_roofing", "paved_road",
    "standing_water", "vegetation_clearing", "active_construction",
    "dense_vegetation",
]
THRESHOLDS = {c: 0.1 * (i + 1) for i, c in enumerate(CATEGORIES)}

DEPLOYED_CAAT = "models/production/caat_thresholds.json"
PRODUCTION_CKPT = "models/production/geowatch_production_model.pth"


@pytest.fixture
def fake_ckpt(tmp_path):
    """A stand-in checkpoint. Only its bytes matter — the loader hashes, not loads."""
    p = tmp_path / "model.pth"
    p.write_bytes(b"pretend-checkpoint-weights-v1")
    return str(p)


@pytest.fixture
def other_ckpt(tmp_path):
    """A DIFFERENT checkpoint that happens to share the same basename."""
    d = tmp_path / "retrained"
    d.mkdir()
    p = d / "model.pth"
    p.write_bytes(b"pretend-checkpoint-weights-v2-RETRAINED")
    return str(p)


def _caat(tmp_path, name="caat.json", **extra):
    p = tmp_path / name
    p.write_text(json.dumps({"thresholds": dict(THRESHOLDS), **extra}))
    return str(p)


# ── The item's stated test ──

def test_matching_checkpoint_loads_cleanly(tmp_path, fake_ckpt):
    path = _caat(tmp_path, source_checkpoint=fake_ckpt,
                 **{CAAT_SOURCE_HASH_KEY: sha256_file(fake_ckpt)})
    arr = load_caat_thresholds(path, CATEGORIES, checkpoint_path=fake_ckpt)
    assert isinstance(arr, np.ndarray)
    assert arr.dtype == np.float32
    assert len(arr) == len(CATEGORIES)


def test_mismatched_checkpoint_raises(tmp_path, fake_ckpt, other_ckpt):
    """
    Thresholds recorded against one checkpoint, a different checkpoint loaded.
    Note both files are named model.pth — so this ALSO proves the check is not
    the basename comparison the dead validator used.
    """
    path = _caat(tmp_path, source_checkpoint=fake_ckpt,
                 **{CAAT_SOURCE_HASH_KEY: sha256_file(fake_ckpt)})
    assert os.path.basename(fake_ckpt) == os.path.basename(other_ckpt), "precondition"
    with pytest.raises(CaatProvenanceError, match="MISMATCH"):
        load_caat_thresholds(path, CATEGORIES, checkpoint_path=other_ckpt)


def test_mismatch_error_names_both_hashes(tmp_path, fake_ckpt, other_ckpt):
    path = _caat(tmp_path, source_checkpoint=fake_ckpt,
                 **{CAAT_SOURCE_HASH_KEY: sha256_file(fake_ckpt)})
    with pytest.raises(CaatProvenanceError) as exc:
        load_caat_thresholds(path, CATEGORIES, checkpoint_path=other_ckpt)
    msg = str(exc.value)
    assert sha256_file(fake_ckpt) in msg, "must report what the file claims"
    assert sha256_file(other_ckpt) in msg, "must report what was actually loaded"
    assert "recalibrate_caat.py" in msg, "must say how to fix it"


# ── The deployed file: refusal is the correct outcome ──

@pytest.mark.skipif(not os.path.exists(DEPLOYED_CAAT), reason="deployed CAAT absent")
def test_deployed_caat_file_has_no_provenance():
    """The measured fact this item rests on."""
    data = json.loads(open(DEPLOYED_CAAT).read())
    assert "source_checkpoint" not in data, (
        "the deployed file now records provenance — if it was recalibrated, "
        "update this test and test_deployed_caat_file_is_refused"
    )
    assert "caveat" in data
    assert "NOT from the production checkpoint" in data["caveat"]


@pytest.mark.skipif(
    not (os.path.exists(DEPLOYED_CAAT) and os.path.exists(PRODUCTION_CKPT)),
    reason="production artifacts absent",
)
def test_deployed_caat_file_is_refused():
    """
    EXPECTED FAILURE, ASSERTED AS CORRECT. The deployed thresholds cannot be
    proved to match the production checkpoint, so the loader refuses them.

    This test passing means the validator works. If someone weakens the
    validator so the current file loads, THIS test fails — which is the intended
    tripwire, because that weakening would silently restore C10.
    """
    with pytest.raises(CaatProvenanceError, match="records no 'source_checkpoint'"):
        load_caat_thresholds(DEPLOYED_CAAT, CATEGORIES,
                             checkpoint_path=PRODUCTION_CKPT)


# ── The states between "verified" and "wrong" ──

def test_missing_source_checkpoint_raises(tmp_path, fake_ckpt):
    path = _caat(tmp_path)
    with pytest.raises(CaatProvenanceError, match="records no 'source_checkpoint'"):
        load_caat_thresholds(path, CATEGORIES, checkpoint_path=fake_ckpt)


def test_path_without_hash_raises(tmp_path, fake_ckpt):
    """
    A filename is not provenance. This is precisely the gap between the dead
    validator's basename check and a real one.
    """
    path = _caat(tmp_path, source_checkpoint=fake_ckpt)
    with pytest.raises(CaatProvenanceError, match=CAAT_SOURCE_HASH_KEY):
        load_caat_thresholds(path, CATEGORIES, checkpoint_path=fake_ckpt)


def test_no_checkpoint_path_warns_rather_than_passing_silently(tmp_path, capsys):
    """
    Omitting checkpoint_path skips the check — but says so. A silent skip is
    exactly what C10 was: an unvalidated load indistinguishable from a validated
    one.
    """
    path = _caat(tmp_path, source_checkpoint="whatever")
    load_caat_thresholds(path, CATEGORIES)
    out = capsys.readouterr().out
    assert "NOT CHECKED" in out
    assert "C10" in out


def test_missing_checkpoint_file_raises(tmp_path):
    path = _caat(tmp_path, source_checkpoint="/nope/model.pth",
                 **{CAAT_SOURCE_HASH_KEY: "0" * 64})
    with pytest.raises(FileNotFoundError, match="checkpoint not found"):
        load_caat_thresholds(path, CATEGORIES, checkpoint_path="/nope/model.pth")


def test_renamed_but_identical_checkpoint_is_noted_not_refused(tmp_path, capsys):
    """
    Same bytes, different path. The hash settles identity, so a basename
    difference only means the file moved — worth saying, not worth refusing.
    The dead validator would have raised here, wrongly.
    """
    a = tmp_path / "a.pth"; a.write_bytes(b"same-bytes")
    b = tmp_path / "b.pth"; b.write_bytes(b"same-bytes")
    path = _caat(tmp_path, source_checkpoint=str(a),
                 **{CAAT_SOURCE_HASH_KEY: sha256_file(str(a))})
    load_caat_thresholds(path, CATEGORIES, checkpoint_path=str(b))
    assert "moved or renamed" in capsys.readouterr().out


# ── Behaviour preserved from the loader being replaced ──

def test_category_mismatch_still_raises(tmp_path, fake_ckpt):
    path = _caat(tmp_path, source_checkpoint=fake_ckpt,
                 **{CAAT_SOURCE_HASH_KEY: sha256_file(fake_ckpt)})
    with pytest.raises(ValueError, match="missing categories"):
        load_caat_thresholds(path, CATEGORIES + ["a_new_category"],
                             checkpoint_path=fake_ckpt)


def test_threshold_order_follows_categories(tmp_path, fake_ckpt):
    """
    The weak loader's one real job, which the promotion must not lose: array
    order must match model output channels, or every threshold is misapplied.
    """
    path = _caat(tmp_path, source_checkpoint=fake_ckpt,
                 **{CAAT_SOURCE_HASH_KEY: sha256_file(fake_ckpt)})
    reordered = list(reversed(CATEGORIES))
    arr = load_caat_thresholds(path, reordered, checkpoint_path=fake_ckpt)
    assert list(arr) == pytest.approx([THRESHOLDS[c] for c in reordered])


def test_missing_thresholds_key_raises(tmp_path, fake_ckpt):
    p = tmp_path / "bad.json"
    p.write_text(json.dumps({"source_checkpoint": fake_ckpt}))
    with pytest.raises(CaatProvenanceError, match="no 'thresholds' key"):
        load_caat_thresholds(str(p), CATEGORIES, checkpoint_path=fake_ckpt)


# ── One loader, not two ──

def test_the_dead_duplicate_validator_is_deleted():
    src = open("ingestion/resnet_classifier.py").read()
    assert "def load_production_model(" not in src, (
        "the duplicate validator is back; item 45 required promoting it and "
        "deleting it, not maintaining both"
    )
    assert "C10 / build item 45" in src, "the deletion should be recorded in place"


def test_only_one_caat_loader_exists():
    """
    Item 45: do not maintain both. Scans source only -- tests/ is excluded
    because this very file mentions the definition line as a string.
    """
    import pathlib
    needle = "def load_caat_" + "thresholds"   # split so this file is not a hit
    hits = []
    for path in pathlib.Path(".").rglob("*.py"):
        parts = set(path.parts)
        if parts & {"geowatch-env", "venv", ".venv", "node_modules", "tests"}:
            continue
        if needle in path.read_text():
            hits.append(str(path))
    assert hits == ["ingestion/inference.py"], (
        f"expected exactly one CAAT loader in ingestion/inference.py, found: {hits}"
    )


def test_no_question_mark_provenance_log_remains():
    """
    The literal string from the finding. `source_checkpoint=?` meant a missing
    provenance record read as a cosmetic gap.
    """
    src = open("ingestion/inference.py").read()
    assert "source_checkpoint={data.get('source_checkpoint', '?')}" not in src


def test_pipeline_passes_the_checkpoint_path():
    src = open("pipeline.py").read()
    assert "checkpoint_path=PRODUCTION_MODEL_PATH" in src, (
        "pipeline.py must pass the checkpoint, or the loader only warns"
    )


def test_recalibrate_records_the_hash():
    """Future CAAT files must be loadable, or the validator blocks forever."""
    src = open("recalibrate_caat.py").read()
    assert '"source_checkpoint_sha256": checkpoint_sha256' in src
    assert "sha256_file" in src


@pytest.mark.skipif(not os.path.exists(PRODUCTION_CKPT), reason="checkpoint absent")
def test_hash_matches_the_artifact_manifest():
    """
    Cross-check against ARTIFACT_HASHES.txt — an independent record of the same
    bytes, so a corrupted checkpoint is caught rather than hashed confidently.
    """
    recorded = None
    for line in open("ARTIFACT_HASHES.txt"):
        if "geowatch_production_model.pth" in line:
            recorded = line.split()[0]
            break
    assert recorded, "the manifest has no entry for the production checkpoint"
    assert sha256_file(PRODUCTION_CKPT) == recorded
