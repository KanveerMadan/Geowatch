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
    """47 flood_final reserved units; after the one held-out pass (2026-11-20)
    flood_round2 flipped them to dev, exposure 6 (flood_round2 R6). Any still
    reserved must be metadata-only."""
    reg = REG.load()
    ff = [u for u in reg["units"] if any(x.get("round") == "flood_final" and x.get("role") ==
                                          "registered_test" for x in u.get("uses", []))]
    assert len(ff) == 47
    for u in ff:
        if u["role"] == "reserved":
            assert u["geometry"]["type"] == "point_approx" and u["exposure_level"] <= 2
        else:
            assert u["exposure_level"] == 6


def test_no_dev_unit_links_to_any_reserved_unit():
    """No block link ever; an exception link only where flood_round2's
    registration accepted it under rule R7 (main basin only, other storm, > 100 km)."""
    import json
    reg, dev = _final_units("dev")
    reserved = [u for u in reg["units"] if u["role"] == "reserved"]
    p = os.path.join(HERE, "..", "flood_round2", "registry_units_round2.json")
    accepted = {}
    if os.path.exists(p):
        for lg in json.load(open(p))["logs"]:
            accepted.update(lg.get("accepted_exception_links", {}))
    for d in dev:
        for r in reserved:
            for rule, sev in REG.links(d, r):
                assert sev != REG.BLOCK, (d["event_id"], r["event_id"], rule)
                assert rule == "main_basin" and r["event_id"] in accepted, (d["event_id"], r["event_id"], rule)


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
