"""flood_round2 guards.  python -m pytest -q experiments/flood_round2/test_round2.py"""
import json
import os

from experiments.flood_core.registry import registry as REG

HERE = os.path.dirname(os.path.abspath(__file__))


def _r2(role):
    reg = REG.load()
    return reg, [u for u in reg["units"] if u["role"] == role
                 and any(x.get("round") == "flood_round2" for x in u.get("uses", []))]


def test_round2_reserved_are_metadata_only():
    _, res = _r2("reserved")
    assert len(res) >= 30
    for u in res:
        assert u["geometry"]["type"] == "point_approx" and u["exposure_level"] <= 2


def test_round2_reserved_never_block_linked_to_dev():
    reg, res = _r2("reserved")
    dev = [u for u in reg["units"] if u["role"] == "dev"]
    log = json.load(open(os.path.join(HERE, "registry_units_round2.json")))["logs"]
    accepted = {k for lg in log for k in lg.get("accepted_exception_links", {})}
    for r in res:
        for d in dev:
            for rule, sev in REG.links(r, d):
                assert sev != REG.BLOCK, (r["event_id"], d["event_id"], rule)
                assert rule == "main_basin" and r["event_id"] in accepted


def test_round1_reserved_are_now_dev():
    reg = REG.load()
    for u in reg["units"]:
        if any(x.get("round") == "flood_final" and x.get("role") == "registered_test" for x in u.get("uses", [])):
            assert u["role"] == "dev" and u["exposure_level"] == 6
