"""
Build item 57 — dead code is deleted, and nothing live depended on it.

Each deletion was preceded by a repo-wide import grep, which was also run on
every other branch. What item 57 listed but this change KEEPS, and why:

  * ingestion/resnet_model.py — live importers: tests/test_encoder_band_contract.py
    and three experiments/band_reflectance scripts.
  * the "duplicate" GeoWatchResNetSeg — the two classes are NOT duplicates.
    resnet_model.py's loads pretrained weights and runs
    assert_encoder_band_contract(); inference.py's uses weights=None. Merging
    them changes behaviour on one side, so it is not a deletion.

The structural tests below are the point of the item ("is it gone"), and the
import tests are its safety net ("did anything live need it").

Run from the repo root:  pytest tests/test_dead_code_removed.py
"""

import ast
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("path", [
    "ingestion/resnet_classifier.py",
    "ingestion/classifier.py",
    "test_classifier.py",   # the RemoteCLIP smoke script, its only importer
])
def test_dead_file_is_deleted(path):
    assert not (ROOT / path).exists()


def _defs(path):
    tree = ast.parse((ROOT / path).read_text())
    return [n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.ClassDef))]


def test_run_event_hazard_analysis_is_deleted():
    assert "run_event_hazard_analysis" not in _defs("pipeline.py")


def test_verify_masks_has_no_private_rle_decoder():
    """The fallback decoder reshaped as (w, h).T, a different layout from
    segmentation.decode_mask_rle, behind a print-only warning. A verifier
    that can silently check with a different decoder is not verifying."""
    assert "decode_mask_rle" not in _defs("verify_masks.py")


def test_only_one_decode_mask_rle_outside_experiments():
    owners = [p for p in ROOT.glob("*.py") if "decode_mask_rle" in _defs(p.name)]
    owners += [p for p in (ROOT / "ingestion").glob("*.py")
               if "decode_mask_rle" in _defs(f"ingestion/{p.name}")]
    assert [p.name for p in owners] == ["segmentation.py"]


@pytest.mark.parametrize("module", [
    "pipeline", "api", "ingestion.inference", "ingestion.resnet_model",
    "ingestion.segmentation",
])
def test_live_modules_still_import(module):
    importlib.import_module(module)


def test_verify_masks_still_imports():
    import runpy
    runpy.run_path(str(ROOT / "verify_masks.py"), run_name="not_main")
