"""flood_final guards.  python -m pytest -q experiments/flood_final/test_final.py"""
import hashlib
import os

import pytest

from experiments.flood_core.registry import registry as REG
from experiments.flood_final import heldout_pass as HP
from experiments.flood_learned import events as LE

HERE = os.path.dirname(os.path.abspath(__file__))


def _final_units(role):
    reg = REG.load()
    return reg, [u for u in reg["units"] if u["role"] == role
                 and any(x.get("round") == "flood_final" for x in u.get("uses", []))]


def test_prereg_hash_matches_companion():
    sha = hashlib.sha256(open(HP.PREREG, "rb").read()).hexdigest()
    assert sha in open(HP.HASHFILE).read()


def test_reserved_units_are_metadata_only():
    _, res = _final_units("reserved")
    assert len(res) == 47
    for u in res:
        assert u["geometry"]["type"] == "point_approx" and u["exposure_level"] <= 2


def test_no_dev_unit_links_to_any_reserved_unit():
    reg, dev = _final_units("dev")
    reserved = [u for u in reg["units"] if u["role"] == "reserved"]
    for d in dev:
        for r in reserved:
            assert not REG.links(d, r), (d["event_id"], r["event_id"])


def test_reserved_block_links_never_accepted():
    reg, res = _final_units("reserved")
    dev = [u for u in reg["units"] if u["role"] == "dev"]
    for r in res:
        for d in dev:
            assert all(sev != REG.BLOCK for _, sev in REG.links(r, d)), (r["event_id"], d["event_id"])


def test_heldout_pass_refuses_before_freeze():
    if HP._git("rev-list", "-n", "1", HP.FREEZE_TAG):
        pytest.skip("freeze tag exists")
    with pytest.raises(SystemExit):
        HP.preflight(scoring=True)


def test_dev_set_excludes_jrc_circular_and_folds_are_clean():
    from experiments.flood_baselines import events as BE
    from experiments.flood_final import model_v2 as V
    names, region, _ = V.dev_units()
    assert not set(names) & set(LE.JRC_REFERENCE_UNITS)
    cl = BE.clusters(names, REG.load())
    seen = {}
    for n in names:
        assert seen.setdefault(cl[n], region[n]) == region[n]
