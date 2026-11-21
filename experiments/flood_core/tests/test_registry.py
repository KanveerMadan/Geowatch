"""Flood-core prototype: event registry and reuse guard."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "registry"))
import registry as R  # noqa: E402

FV = os.path.join(HERE, "..", "..", "flood_validation")


@pytest.fixture(scope="module")
def reg():
    return R.load()


def scored_names():
    names = set()
    for f in ("result_2026-10-28.json", "result_round2_2026-10-28.json",
              "result_round3_2026-10-29.json", "result_round4_2026-10-30.json"):
        d = json.load(open(os.path.join(FV, f)))
        for v in d["modules"].values():
            names |= {s if isinstance(s, str) else s.get("name") for s in v.get("sites", [])}
            names |= set(v.get("events") or {})
            names |= set(((v.get("tuning") or {}).get("events")) or {})
    return {n for n in names if n}


def test_every_event_any_round_used_is_registered(reg):
    assert scored_names() <= set(R.units(reg))


def test_reserved_units_carry_no_reference_derived_box(reg):
    for u in reg["units"]:
        if u["role"] == "reserved":
            assert u["geometry"]["type"] == "point_approx"
            assert u["exposure_level"] <= 2


def test_known_aliases_are_grouped(reg):
    groups = R.alias_groups(reg)
    flat = {n: tuple(g) for g in groups for n in g}
    assert flat["paiporta"] == flat["valencia_2024"]          # one EMS product
    assert flat["derna"] == flat["derna_2023"]                # overlapping boxes
    assert flat["jakarta"] == flat["jakarta_gfd_3280"]        # identical box
    assert flat["chennai_velachery"] == flat["chennai_2023"]  # one cyclone
    assert flat["hanoi"] == flat["thai_binh"]                 # Typhoon Yagi


def test_name_only_guard_misses_an_alias_the_registry_blocks(reg):
    earlier = set(R.units(reg))
    alias = {"event_id": "valencia_dana_horta_sud", "role": "reserved", "storm_cluster": None,
             "region_cluster": None, "products": ["EMSR773:AOI03"], "exposure_level": 0,
             "geometry": {"type": "point_approx", "point": [-0.45, 39.43]}}
    assert not R.name_only_guard(alias["event_id"], earlier)
    assert R.verdict(reg, alias) == "blocked"


def test_round4b_reserved_verdicts(reg):
    # recorded, not decided: Noakhali links to seen GBM events only through
    # the curated region rule (its MAIN_BAS is the Feni coastal basin, not
    # the GBM); Calais and Redon link to nothing.
    noak = {(c["other"], c["rule"]) for c in R.conflicts(reg, "noakhali_2024")}
    assert all(sev == R.EXCEPTION for sev in
               {c["severity"] for c in R.conflicts(reg, "noakhali_2024")})
    assert ("sylhet_2022", "region") in noak
    assert R.verdict(reg, "noakhali_2024") == "needs_signed_exception"
    assert R.verdict(reg, "calais_2023") == "clear"
    assert R.verdict(reg, "redon_2025") == "clear"


def test_signed_exception_clears_only_exception_links(reg):
    ex = {(c["other"], c["rule"]): "signed: <name, date, reason>"
          for c in R.conflicts(reg, "noakhali_2024")}
    assert R.verdict(reg, "noakhali_2024", ex) == "clear"
    alias = {"event_id": "x", "role": "reserved", "products": ["EMSR773:AOI03"], "exposure_level": 0,
             "geometry": {"type": "point_approx", "point": [-0.45, 39.43]}}
    ex2 = {(c["other"], c["rule"]): "signed" for c in R.conflicts(reg, alias)}
    assert R.verdict(reg, alias, ex2) == "blocked"


def test_hidden_basin_links_are_visible(reg):
    # found by the HydroBASINS lookup, not by names or curated clusters
    links = {c["other"] for c in R.conflicts(reg, R.units(reg)["himachal_2023"])
             if c["rule"] == "main_basin"}
    assert "pakistan_2022" in links              # Beas -> Sutlej -> Indus
    gbm = {c["other"] for c in R.conflicts(reg, R.units(reg)["bihar_2026"]) if c["rule"] == "main_basin"}
    assert {"assam_2026", "sylhet_2022", "dhaka"} <= gbm
