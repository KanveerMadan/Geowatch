"""Item 21 Phase A, part 7 — labelling tooling (LABELLING_GUIDE.md)."""
import copy
import json
import dataclasses
import pathlib
import sys

import numpy as np
import pytest
from shapely.geometry import box, mapping

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from labelling import qc, records, tiles
from labelling.common import OpenNumberUnset, load_config
from labelling.fractions import LabelQCError, tile_fractions

CRS = "EPSG:32643"
X0, Y1 = 272400.0, 2108800.0          # on the 200 m lattice
CFG = load_config()


def grid():
    return tiles.tile_grid(CRS, X0, Y1, 200)


def feat(label, x0, y0, x1, y1, **props):
    return {"type": "Feature", "geometry": mapping(box(X0 + x0, Y1 - y1, X0 + x1, Y1 - y0)),
            "properties": {"label": label, **props}}


def full_tile(label="bare"):
    return [feat(label, 0, 0, 200, 200)]


# ── open numbers stay UNSET ─────────────────────────────────────────────────

def test_all_five_open_numbers_are_unset():
    for k in ("change_test", "max_date_gap_days", "starting_tile_count",
              "agreement_bars", "max_excluded_share_per_cell"):
        assert CFG["open"][k]["status"] == "UNSET", k


def test_decided_numbers_match_the_guide():
    assert CFG["tiles"]["size_m"] == 200
    assert CFG["qc"]["blind_relabel_fraction"] == 0.15
    assert CFG["qc"]["same_labeller_min_gap_days"] == 7
    assert CFG["tiles"]["strata"] == ["dense_informal", "formal", "mixed", "fringe"]


# ── tiles ────────────────────────────────────────────────────────────────────

def test_tile_grid_is_20x20_on_the_s2_lattice():
    g = grid()
    assert (g.width, g.height) == (20, 20)
    assert g.transform[2] % 10 == 0 and g.transform[5] % 10 == 0


def test_tile_origins_only_whole_tiles_on_200m_lattice():
    o = tiles.tile_origins((150, 150, 650, 450), 200)
    assert sorted(o) == [(200, 400), (400, 400)]


def test_frame_stratifies_ranks_and_is_reproducible():
    strata = {"formal": box(0, 0, 1000, 400), "dense_informal": box(0, 400, 1000, 800)}
    f1 = tiles.build_frame("lima", CRS, (0, 0, 1000, 800), strata, CFG)
    f2 = tiles.build_frame("lima", CRS, (0, 0, 1000, 800), strata, CFG)
    assert f1 == f2
    by = {s: [t for t in f1["tiles"] if t["stratum"] == s] for s in strata}
    assert len(by["formal"]) == 10 and len(by["dense_informal"]) == 10
    assert sorted(t["rank_in_stratum"] for t in by["formal"]) == list(range(10))
    assert f1["random_seed"] == CFG["tiles"]["random_seed"]


def test_frame_plurality_and_tie_rules():
    # Second tile (200-400): formal 0.75 vs fringe 0.25 -> formal.
    strata = {"formal": box(0, 0, 350, 200), "fringe": box(350, 0, 400, 200)}
    f = tiles.build_frame("lima", CRS, (0, 0, 400, 200), strata, CFG)
    assert [t["stratum"] for t in f["tiles"]] == ["formal", "formal"]
    tie = {"formal": box(0, 0, 100, 200), "fringe": box(100, 0, 200, 200)}
    f = tiles.build_frame("lima", CRS, (0, 0, 200, 200), tie, CFG)
    assert f["tiles"] == [] and f["ineligible"]["tied_strata"] == 1


def test_frame_excludes_tiles_outside_imagery_footprint():
    strata = {"formal": box(0, 0, 400, 200)}
    f = tiles.build_frame("lima", CRS, (0, 0, 400, 200), strata, CFG,
                          footprint=box(0, 0, 300, 200))
    assert len(f["tiles"]) == 1 and f["ineligible"]["outside_footprint"] == 1


def test_unknown_stratum_refused():
    with pytest.raises(ValueError):
        tiles.build_frame("lima", CRS, (0, 0, 200, 200), {"slum": box(0, 0, 200, 200)}, CFG)


def test_select_refuses_while_tile_count_unset_but_takes_explicit_counts():
    strata = {"formal": box(0, 0, 1000, 200)}
    f = tiles.build_frame("lima", CRS, (0, 0, 1000, 200), strata, CFG)
    with pytest.raises(OpenNumberUnset):
        tiles.select(f, CFG)
    got = tiles.select(f, CFG, counts={"formal": 2})
    assert [t["rank_in_stratum"] for t in got] == [0, 1]


def test_qc_selection_is_about_fifteen_percent():
    ts = [{"tile_id": f"t{i}"} for i in range(40)]
    assert len(tiles.qc_selection(ts, CFG)) == 6


# ── fractions ───────────────────────────────────────────────────────────────

def test_fractions_come_from_polygon_area():
    fs = [feat("built", 0, 0, 5, 200), feat("paved", 5, 0, 10, 200), feat("bare", 10, 0, 200, 200)]
    r = tile_fractions(fs, grid(), CFG)
    assert r["fractions"]["built"][0, 0] == pytest.approx(0.5)
    assert r["fractions"]["paved"][0, 0] == pytest.approx(0.5)
    assert r["fractions"]["bare"][0, 1] == pytest.approx(1.0)


def test_unsure_and_shadow_full_leave_the_cell_denominator():
    fs = [feat("built", 0, 0, 5, 200), feat("unsure", 5, 0, 10, 200), feat("bare", 10, 0, 200, 200)]
    r = tile_fractions(fs, grid(), CFG)
    assert r["excluded_share"][0, 0] == pytest.approx(0.5)
    assert r["fractions"]["built"][0, 0] == pytest.approx(1.0)
    assert r["pct_unsure"] == pytest.approx(0.5 / 400 * 100 * 20)


def test_fully_excluded_cell_is_not_scored_others_undetermined():
    fs = [feat("shadow_full", 0, 0, 10, 10), feat("bare", 10, 0, 200, 200),
          feat("bare", 0, 10, 10, 200)]
    r = tile_fractions(fs, grid(), CFG)
    assert r["scored"][0, 0] is False or r["scored"][0, 0] == False  # noqa: E712
    assert r["scored"][0, 1] is None
    assert np.isnan(r["fractions"]["bare"][0, 0])


def test_partial_shadow_is_a_flag_not_a_label():
    fs = [feat("paved", 0, 0, 10, 200, shadow_partial=True), feat("bare", 10, 0, 200, 200)]
    r = tile_fractions(fs, grid(), CFG)
    assert r["partial_shadow"][0, 0] == pytest.approx(1.0)
    assert r["fractions"]["paved"][0, 0] == pytest.approx(1.0)
    with pytest.raises(LabelQCError, match="not a label"):
        tile_fractions([feat("shadow_partial", 0, 0, 200, 200)], grid(), CFG)


def test_gap_and_overlap_are_qc_errors():
    with pytest.raises(LabelQCError, match="unlabelled"):
        tile_fractions([feat("bare", 0, 0, 200, 199)], grid(), CFG)
    with pytest.raises(LabelQCError, match="doubly"):
        tile_fractions(full_tile() + [feat("built", 0, 0, 10, 10)], grid(), CFG)


def test_unknown_label_refused():
    with pytest.raises(LabelQCError):
        tile_fractions(full_tile("road"), grid(), CFG)


def test_max_excluded_share_applies_when_set():
    fs = [feat("unsure", 0, 0, 3, 200), feat("bare", 3, 0, 200, 200)]
    r = tile_fractions(fs, grid(), CFG, max_excluded_share=0.2)
    assert bool(r["scored"][0, 0]) is False and bool(r["scored"][0, 1]) is True


# ── records ─────────────────────────────────────────────────────────────────

def rec(**over):
    base = dict(site="lima", tile_id="EPSG32643_272400_2108800",
                imagery_source="OpenAerialMap", imagery_acquisition_date="2025-03-17",
                imagery_acquisition_time="10:42", imagery_resolution_m=0.05,
                imagery_licence="CC BY 4.0",
                s2_composite_window={"start": "2025-02-15", "end": "2025-04-15"},
                date_gap_days=12, change_test_result="not run: method UNSET",
                labeller="L1", labelling_date="2026-10-01", guide_version="1.0",
                pct_unsure=0.0, pct_shadow_full=0.0, qc_status="pending")
    base.update(over)
    return records.TileRecord(**base)


def test_every_metadata_field_is_mandatory():
    for f in dataclasses.fields(records.TileRecord):
        bad = rec(**{f.name: "" if f.type == "str" else None})
        with pytest.raises(records.RecordError):
            bad.validate(CFG)


def test_labels_are_versioned_never_overwritten(tmp_path):
    store = records.LabelStore(str(tmp_path), CFG)
    p1 = store.save(rec(), full_tile(), reason="initial")
    with pytest.raises(records.RecordError, match="reason"):
        store.save(rec(), full_tile(), reason=" ")
    p2 = store.save(rec(), full_tile("vegetation"), reason="corrected class")
    assert p1.endswith("v1.json") and p2.endswith("v2.json")
    assert store.load_training("lima", rec().tile_id, 1)["features"] == \
        json.loads(json.dumps(full_tile()))
    assert store.load_training("lima", rec().tile_id)["reason"] == "corrected class"


def test_dropped_tile_is_never_relabelled(tmp_path):
    store = records.LabelStore(str(tmp_path), CFG)
    store.drop("lima", rec().tile_id, "beyond max gap")
    with pytest.raises(records.RecordError, match="dropped"):
        store.save(rec(), full_tile(), reason="initial")


def test_validation_labels_are_sealed(tmp_path):
    store = records.LabelStore(str(tmp_path), CFG)
    r = rec(site="kibera")
    with pytest.raises(records.SealedError):
        store.save(r, full_tile(), reason="initial")          # no batch
    store.save(r, full_tile(), reason="initial", batch=1)
    with pytest.raises(records.SealedError):
        store.load_training("kibera", r.tile_id)
    with pytest.raises(records.SealedError):
        store.unseal("kibera", r.tile_id, batch=1, purpose="")
    got = store.unseal("kibera", r.tile_id, batch=1, purpose="batch 1 scoring after LOCO")
    assert got["version"] == 1
    assert (tmp_path / "unseal_log.jsonl").read_text().count("batch 1 scoring") == 1


def test_time_gap_decision_needs_open_numbers():
    with pytest.raises(OpenNumberUnset):
        records.time_gap_decision("lima", 10, False, CFG)
    cfg = copy.deepcopy(CFG)
    cfg["open"]["max_date_gap_days"] = {"status": "SET", "per_site": {"lima": 30}}
    assert records.time_gap_decision("lima", 45, None, cfg) == "drop"
    with pytest.raises(OpenNumberUnset):
        records.time_gap_decision("lima", 10, False, cfg)      # change test still UNSET


def test_same_labeller_relabel_waits_a_week():
    a = rec(labelling_date="2026-10-01")
    assert not records.relabel_gap_ok(a, rec(labelling_date="2026-10-05"), CFG)
    assert records.relabel_gap_ok(a, rec(labelling_date="2026-10-08"), CFG)
    assert records.relabel_gap_ok(a, rec(labeller="L2", labelling_date="2026-10-02"), CFG)


# ── QC comparison ───────────────────────────────────────────────────────────

def test_identical_labellings_agree_perfectly():
    fs = [feat("built", 0, 0, 100, 200), feat("bare", 100, 0, 200, 200)]
    out = qc.compare(fs, fs, grid(), CFG)
    assert out["per_class"]["built"]["polygon_iou"] == 1.0
    assert out["per_class"]["built"]["fraction_mae"] == 0.0
    assert out["per_class"]["built"]["meets_agreement_bar"] is None
    assert out["per_class"]["built"]["label_limited"] is None
    assert "UNSET" in out["agreement_bars"]


def test_disagreement_measured_at_both_levels():
    a = [feat("built", 0, 0, 100, 200), feat("bare", 100, 0, 200, 200)]
    b = [feat("built", 0, 0, 50, 200), feat("bare", 50, 0, 200, 200)]
    out = qc.compare(a, b, grid(), CFG)["per_class"]
    assert out["built"]["polygon_iou"] == pytest.approx(0.5)
    assert out["built"]["fraction_mae"] == pytest.approx(0.25)
    assert out["water"]["polygon_iou"] is None


def test_agreement_bar_must_name_its_metric():
    cfg = copy.deepcopy(CFG)
    cfg["open"]["agreement_bars"] = {"status": "SET", "per_class": {
        "built": {"metric": "polygon_iou", "value": 0.6}}}
    a = [feat("built", 0, 0, 100, 200), feat("bare", 100, 0, 200, 200)]
    b = [feat("built", 0, 0, 50, 200), feat("bare", 50, 0, 200, 200)]
    assert qc.compare(a, b, grid(), cfg)["per_class"]["built"]["meets_agreement_bar"] is False
    cfg["open"]["agreement_bars"]["per_class"]["built"]["metric"] = "vibes"
    with pytest.raises(ValueError):
        qc.compare(a, b, grid(), cfg)
