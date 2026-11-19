"""
The public site's honesty page and gallery are generated from code
(product/site_data.py). These tests fail when the committed page data and
the code disagree: a changed verdict, scope, label, run record or gallery
entry must be regenerated (python -m product.site_data) and committed.

Run from the repo root:  pytest tests/test_site_data.py
"""
import json
import os

import pytest

from analysis import contract as C
from product import site_data as S

GEN = os.path.join("web", "src", "generated")


def _committed(name):
    with open(os.path.join(GEN, name)) as fh:
        return json.load(fh)


@pytest.mark.parametrize("name", ["honesty.json", "gallery.json"])
def test_committed_page_data_equals_a_fresh_build(name):
    fresh = json.loads(S._dump(S.build()[name]))
    assert _committed(name) == fresh, f"{name} is stale: run python -m product.site_data"


def test_check_mode_passes_on_the_committed_files():
    assert S.main(["--check"]) == 0


def test_every_flood_type_is_on_the_page_with_the_contracts_verdict():
    h = _committed("honesty.json")
    assert [r["id"] for r in h["flood"]] == list(C.FLOOD_TAXONOMY)
    verdicts = C.flood_verdicts()
    for r in h["flood"]:
        if r["built"]:
            assert r["verdict"] == verdicts[r["module"]]
            assert r["label"] == ("failed" if C.verdict_label(r["verdict"]) == "failed"
                                  else "validated" if r["module"] in C.VALIDATED_CONFIGS
                                  and C.verdict_label(r["verdict"]) == "validated"
                                  else "experimental")
        else:
            status, label, reason = C.UNBUILT_FLOOD_TYPES[r["module"]]
            assert (r["status"], r["label"], r["reason"]) == (status, label, reason)


def test_validated_scope_is_the_contracts_scope_word_for_word():
    h = _committed("honesty.json")
    for r in h["flood"]:
        if r.get("label") == "validated":
            assert r["scope"] == C.VALIDATED_CONFIGS[r["module"]]["scope"]
            C.check_scope(r["scope"])


def test_a_disagreeing_round_file_stops_generation(monkeypatch):
    """The page picks the round it shows by the contract's rule; if that ever
    gives a different verdict from flood_verdicts(), generation must fail."""
    real = C.flood_verdicts()
    monkeypatch.setattr(C, "flood_verdicts", lambda: {**real, "fluvial": "failed"})
    with pytest.raises(C.ContractError):
        S.honesty()


def test_gallery_values_are_the_stored_run_records():
    g = _committed("gallery.json")
    cfg = json.load(open(S.GALLERY_CONFIG))
    assert [c["key"] for c in g["cities"]] == [e["key"] for e in cfg["cities"]]
    for card, entry in zip(g["cities"], cfg["cities"]):
        run = json.load(open(entry["run_record"]))["cities"][entry["run_key"]]
        assert card["result_id"] == run["result_id"]
        for f in card["fractions"]:
            v = run["headline"]["fractions"][f["key"]]
            assert [f["value"], f["status"], f["label"]] == v
            if f["value"] is None:
                assert f["status"] in C.ABSENT          # absent is never 0
        for f in card["flood"]:
            assert [f["value"], f["tier"], f["status"], f["label"]] == \
                run["headline"]["susceptibility"][f["key"]]


def test_gallery_never_names_a_settlement_type():
    text = json.dumps(_committed("gallery.json")).lower() + open(S.GALLERY_CONFIG).read().lower()
    for word in ("slum", "informal", "settlement", "shanty", "squatter"):
        assert word not in text
