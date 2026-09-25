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
    f1 = tiles.build_frame("lima", CRS, (0, 0, 1000, 800), strata, CFG, frame=box(0, 0, 1000, 800))
    f2 = tiles.build_frame("lima", CRS, (0, 0, 1000, 800), strata, CFG, frame=box(0, 0, 1000, 800))
    assert f1 == f2
    by = {s: [t for t in f1["tiles"] if t["stratum"] == s] for s in strata}
    assert len(by["formal"]) == 10 and len(by["dense_informal"]) == 10
    assert sorted(t["rank_in_stratum"] for t in by["formal"]) == list(range(10))
    assert f1["random_seed"] == CFG["tiles"]["random_seed"]


def test_frame_plurality_and_tie_rules():
    # Second tile (200-400): formal 0.75 vs fringe 0.25 -> formal.
    strata = {"formal": box(0, 0, 350, 200), "fringe": box(350, 0, 400, 200)}
    f = tiles.build_frame("lima", CRS, (0, 0, 400, 200), strata, CFG, frame=box(0, 0, 400, 200))
    assert [t["stratum"] for t in f["tiles"]] == ["formal", "formal"]
    tie = {"formal": box(0, 0, 100, 200), "fringe": box(100, 0, 200, 200)}
    f = tiles.build_frame("lima", CRS, (0, 0, 200, 200), tie, CFG, frame=box(0, 0, 200, 200))
    assert f["tiles"] == [] and f["ineligible"]["tied_strata"] == 1


def test_frame_excludes_tiles_outside_imagery_footprint():
    strata = {"formal": box(0, 0, 400, 200)}
    f = tiles.build_frame("lima", CRS, (0, 0, 400, 200), strata, CFG,
                          frame=box(0, 0, 300, 200))
    assert len(f["tiles"]) == 1 and f["ineligible"]["outside_frame"] == 1


def test_unknown_stratum_refused():
    with pytest.raises(ValueError):
        tiles.build_frame("lima", CRS, (0, 0, 200, 200), {"slum": box(0, 0, 200, 200)}, CFG, frame=box(0, 0, 200, 200))


def test_select_refuses_while_tile_count_unset_but_takes_explicit_counts():
    strata = {"formal": box(0, 0, 1000, 200)}
    f = tiles.build_frame("lima", CRS, (0, 0, 1000, 200), strata, CFG, frame=box(0, 0, 1000, 200))
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
                labeller="L1", labelling_date="2026-10-01", guide_version="1.4",
                pct_unsure=0.0, pct_shadow_full=0.0, qc_status="pending")
    base.update(over)
    return records.TileRecord(**base)


def test_every_metadata_field_is_mandatory():
    for f in dataclasses.fields(records.TileRecord):
        if f.name in records.TileRecord.SUN_FIELDS + records.TileRecord.RANGE_FIELDS:
            continue                      # optional, tested below
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
    assert out["per_class"]["built"]["label_limited"] is False      # R5 bar set
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


# ── guide v1.1 (2026-09-25): solar = ground-mounted only ────────────────────

def test_guide_version_is_1_4():
    assert CFG["guide_version"] == "1.4"
    assert "Guide version 1.4" in open(
        pathlib.Path(__file__).resolve().parents[1] / "LABELLING_GUIDE.md").read()


def test_rooftop_solar_is_built_plus_flag():
    fs = [feat("built", 0, 0, 10, 200, rooftop_solar=True), feat("bare", 10, 0, 200, 200)]
    r = tile_fractions(fs, grid(), CFG)
    assert r["fractions"]["built"][0, 0] == pytest.approx(1.0)
    assert r["fractions"]["solar"][0, 0] == 0.0
    assert r["rooftop_solar"][0, 0] == pytest.approx(1.0)


def test_rooftop_flag_on_non_built_is_refused():
    with pytest.raises(LabelQCError, match="only valid on `built`"):
        tile_fractions([feat("solar", 0, 0, 200, 200, rooftop_solar=True)], grid(), CFG)


# ── ruling 2026-09-25 (second round, 5): label_limited ──────────────────────

def _strips(built_w, paved_w):
    """Vertical strips: built from x=0, paved next, bare for the rest."""
    fs = []
    if built_w:
        fs.append(feat("built", 0, 0, built_w, 200))
    if paved_w:
        fs.append(feat("paved", built_w, 0, built_w + paved_w, 200))
    fs.append(feat("bare", built_w + paved_w, 0, 200, 200))
    return fs


def test_impervious_agreement_uses_built_plus_paved():
    # a: 60 m built + 40 m paved; b: 100 m built. Impervious identical.
    out = qc.compare(_strips(60, 40), _strips(100, 0), grid(), CFG)
    assert out["impervious_total"]["fraction_mae"] == 0.0
    assert out["impervious_total"]["fraction_r2"] == pytest.approx(1.0)
    assert out["impervious_total"]["label_limited"] is False
    assert out["per_class"]["built"]["fraction_mae"] > 0      # but built disagrees


def test_impervious_label_limited_when_worse_than_floor():
    # a: 100 m impervious; b: 20 m. Most cells swap 1 <-> 0: MAE 0.4 > 0.15.
    out = qc.compare(_strips(100, 0), _strips(20, 0), grid(), CFG)
    assert out["impervious_total"]["fraction_mae"] == pytest.approx(0.4)
    assert out["impervious_total"]["label_limited"] is True


def test_built_bar_is_r5_and_stricter_than_impervious():
    b, i = CFG["model_pass_bars"]["built"], CFG["model_pass_bars"]["impervious_total"]
    assert (b["fraction_mae_max"], b["fraction_r2_min"], b["coverage_bias_abs_max"]) == \
        (0.10, 0.5, 0.05)
    assert b["fraction_mae_max"] < i["fraction_mae_max"]
    assert b["fraction_r2_min"] > i["fraction_r2_min"]


def test_built_label_limited_uses_all_three_gates_others_none():
    out = qc.compare(_strips(100, 0), _strips(20, 0), grid(), CFG)
    assert out["per_class"]["built"]["label_limited"] is True        # MAE 0.4
    assert out["per_class"]["built"]["coverage_bias"] == pytest.approx(0.4)
    assert all(v["label_limited"] is None for k, v in out["per_class"].items()
               if k != "built")


def test_built_bias_alone_can_make_it_label_limited():
    from labelling.qc import _label_limited
    bar = CFG["model_pass_bars"]["built"]
    ok = {"fraction_mae": 0.05, "fraction_r2": 0.9, "coverage_bias": 0.02}
    assert _label_limited(ok, bar) is False
    assert _label_limited({**ok, "coverage_bias": -0.06}, bar) is True


def test_impervious_bars_match_item_21_floors():
    b = CFG["model_pass_bars"]["impervious_total"]
    assert (b["fraction_mae_max"], b["fraction_r2_min"]) == (0.15, 0.3)


def test_frame_saved_with_seed_in_run_metadata_and_never_overwritten(tmp_path):
    f = tiles.build_frame("lima", CRS, (0, 0, 400, 200), {"formal": box(0, 0, 400, 200)}, CFG, frame=box(0, 0, 400, 200))
    p = tiles.save_frame(f, str(tmp_path / "frame.json"), CFG)
    meta = json.load(open(p))["run_metadata"]
    assert meta["tile_sampler_seed"] == CFG["tiles"]["random_seed"]
    assert meta["guide_version"] == CFG["guide_version"] and len(meta["labelling_config_sha256"]) == 64
    with pytest.raises(FileExistsError):
        tiles.save_frame(f, p, CFG)



# ── guide v1.2: acquisition time OR measured sun geometry ───────────────────

SUN = dict(sun_azimuth_deg=312.0, sun_elevation_deg=58.5,
           sun_geometry_method="shadow-tip vectors on the VHR mosaic",
           sun_geometry_n_buildings=4)


def test_time_alone_is_enough():
    rec().validate(CFG)


def test_sun_geometry_stands_in_for_unpublished_time():
    rec(imagery_acquisition_time=None, **SUN).validate(CFG)


def test_neither_time_nor_complete_sun_geometry_refused():
    with pytest.raises(records.RecordError, match="incomplete"):
        rec(imagery_acquisition_time=None).validate(CFG)
    with pytest.raises(records.RecordError, match="sun_geometry_method"):
        rec(imagery_acquisition_time=None, **{**SUN, "sun_geometry_method": " "}).validate(CFG)


def test_sun_geometry_needs_three_buildings():
    with pytest.raises(records.RecordError, match=">= 3"):
        rec(imagery_acquisition_time=None, **{**SUN, "sun_geometry_n_buildings": 2}).validate(CFG)


def test_sun_angles_range_checked():
    with pytest.raises(records.RecordError, match="azimuth"):
        rec(imagery_acquisition_time=None, **{**SUN, "sun_azimuth_deg": 360.0}).validate(CFG)
    with pytest.raises(records.RecordError, match="elevation"):
        rec(imagery_acquisition_time=None, **{**SUN, "sun_elevation_deg": 0.0}).validate(CFG)


def test_marrakech_removed_from_site_list():
    assert "marrakech" not in CFG["sites"]["training"]
    with pytest.raises(records.RecordError, match="not in the item 21 site list"):
        records.site_role("marrakech", CFG)



# ── labelling frame = approved box ∩ chosen scene footprint (2026-09-25) ────

def test_frame_is_box_intersect_scene_and_tiles_must_be_fully_inside():
    frame = tiles.labelling_frame(box(0, 0, 3000, 3000), box(1000, 0, 5000, 3000))
    assert frame.bounds == (1000, 0, 3000, 3000)
    f = tiles.build_frame("lima", CRS, (0, 0, 3000, 3000), {"formal": box(0, 0, 3000, 3000)},
                          CFG, frame=frame)
    assert all(t["x0"] >= 1000 for t in f["tiles"])
    assert len(f["tiles"]) == 10 * 15 and f["ineligible"]["outside_frame"] == 5 * 15


def test_frame_required_and_non_overlapping_scene_refused():
    with pytest.raises(ValueError, match="frame"):
        tiles.build_frame("lima", CRS, (0, 0, 400, 200), {"formal": box(0, 0, 400, 200)}, CFG, None)
    with pytest.raises(ValueError, match="does not overlap"):
        tiles.labelling_frame(box(0, 0, 10, 10), box(20, 20, 30, 30))


def test_approved_site_boxes_are_3km_and_pending_ones_refused():
    for site, a in CFG["aois"].items():
        if a["status"] == "approved":
            crs, b = tiles.site_box(site, CFG)
            w, s_, e, n = b.bounds
            assert (round(e - w, 3), round(n - s_, 3)) == (3000.0, 3000.0), site
            # frame_scene is the imagery-source choice: unset unless made.
            assert a["frame_scene"] is None or a["frame_scene"].strip(), site
        else:
            with pytest.raises(ValueError, match="not approved"):
                tiles.site_box(site, CFG)
    assert "2025Jan" in CFG["aois"]["cape_town"]["frame_scene"]   # not 2026Jan (not final)



# ── guide v1.4: acquisition date may be a range with a recorded reason ──────

IPP = dict(imagery_acquisition_date="2024-01-01", imagery_acquisition_date_end="2024-06-30",
           imagery_acquisition_date_range_reason="IPP Mosaico_2024 publishes only '1st half 2024'",
           imagery_acquisition_time=None, **SUN)


def test_single_date_still_valid_and_range_is_a_point():
    r = rec()
    r.validate(CFG)
    assert r.acquisition_range[0] == r.acquisition_range[1]


def test_date_range_with_reason_is_valid():
    r = rec(site="rocinha", **IPP)
    r.validate(CFG)
    from datetime import date
    assert r.acquisition_range == (date(2024, 1, 1), date(2024, 6, 30))


def test_range_needs_both_end_and_reason():
    with pytest.raises(records.RecordError, match="both its end"):
        rec(**{**IPP, "imagery_acquisition_date_range_reason": None}).validate(CFG)
    with pytest.raises(records.RecordError, match="both its end"):
        rec(**{**IPP, "imagery_acquisition_date_end": None}).validate(CFG)


def test_range_end_must_follow_start_and_dates_must_be_iso():
    with pytest.raises(records.RecordError, match="not after"):
        rec(**{**IPP, "imagery_acquisition_date_end": "2023-12-31"}).validate(CFG)
    with pytest.raises(records.RecordError, match="ISO"):
        rec(imagery_acquisition_date="1st half 2024").validate(CFG)


def test_rocinha_preregistration_in_config():
    r = CFG["aois"]["rocinha"]
    assert r["imagery_acquisition_range"]["start"] == "2024-01-01"
    assert r["imagery_acquisition_range"]["end"] == "2024-06-30"
    assert r["imagery_acquisition_range"]["reason"]
    assert r["s2_composite_window"] == {"start": "2024-01-01", "end": "2024-06-30"}
    assert r["acquisition_time"] == "sun_geometry_from_shadows"
    assert r["date_gap"] == {"rule": "worst_case_across_range", "computation": "PENDING"}


# ── imagery source choices, 2026-09-25 ──────────────────────────────────────

def test_source_choices_recorded_all_sites_on_the_data_frame():
    a = CFG["aois"]
    for site in ("makoko", "kibera", "rocinha", "lima", "monrovia", "cape_town", "karachi"):
        assert a[site]["frame_scene"], site
        assert a[site]["frame_basis"] == "data", site
        fp, dt = a[site]["frame_footprint"], a[site]["frame_data"]
        assert dt["area_km2"] <= fp["area_km2"] and dt["tiles_200m"] <= fp["tiles_200m"], site
        assert fp["tiles_200m"] <= 196, site


def test_kibera_time_and_sun_geometry_from_maxar():
    k = CFG["aois"]["kibera"]
    assert k["imagery_acquisition_time_utc"] == "2023-11-30T08:00:58Z"
    assert k["sun_geometry"]["elevation_deg"] == 61.8
    assert "104001008E063C00" in k["frame_scene"]


def test_lima_low_s2_overlap_flagged_and_makoko_built_only():
    assert "1 / 2 / 3" in CFG["aois"]["lima"]["known_risk"]
    assert CFG["aois"]["makoko"]["validates"] == ["built"]



def test_karachi_choice_off_nadir_and_base_tracing_note():
    k = CFG["aois"]["karachi"]
    assert "10300100D13F6500" in k["frame_scene"]
    assert k["off_nadir_deg"]["recorded"] == 27.0
    assert k["off_nadir_deg"]["over_box_tiles"] == [25.7, 26.2]
    assert "BASE" in k["labelling_note"] and "wall-ground" in k["labelling_note"]
    assert k["frame_data"]["tiles_200m"] == 196


def test_kibera_data_frame_matches_the_ard_tile_extent():
    # Two independent routes: valid pixels of the OAM file (126 tiles) and the
    # Maxar ARD tile boundaries it repackages (126 tiles, frames.json).
    assert CFG["aois"]["kibera"]["frame_data"]["tiles_200m"] == 126
