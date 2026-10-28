"""
Item 26 Phase 1a, task 5: the round-2 harness's evaluation rules, pure.
Pre-registered in experiments/flood_validation/PREREGISTRATION_ROUND2.md.

Fail on the old code: harness_round2.py did not exist.
"""
import numpy as np
import pytest

from experiments.flood_validation import harness_round2 as H
from susceptibility.hydro_rasters import weighted_map


def _event(score_good, n=100):
    """A synthetic event: component `good` ranks flooded above dry,
    component `bad` ranks them the other way."""
    flooded = np.zeros((2, n), bool)
    flooded[0] = True
    good = np.where(flooded, 0.9, 0.1)
    bad = 1.0 - good
    valid = np.ones_like(flooded)
    return {"good": good, "bad": bad}, flooded, valid, 1


def test_event_auc_needs_fifty_of_each():
    c, f, v, b = _event(True, n=49)
    assert H.event_auc(c["good"], f, v)["qualifies"] is False
    c, f, v, b = _event(True, n=50)
    e = H.event_auc(c["good"], f, v)
    assert e["qualifies"] and e["auc"] == 1.0


def test_choose_weights_picks_the_best_tuning_mean():
    grid = [{"good": 0.0, "bad": 1.0}, {"good": 1.0, "bad": 0.0}, {"good": 1.0, "bad": 1.0}]
    sel = H.choose_weights(grid, grid[2], {"a": _event(True), "b": _event(True)}, weighted_map)
    assert sel["chosen"] == {"good": 1.0, "bad": 0.0}
    assert sel["best_tuning_mean_auc"] == 1.0


def test_choose_weights_ties_go_to_the_default_then_grid_order():
    grid = [{"good": 1.0}, {"good": 2.0}, {"good": 3.0}]          # all rank identically
    t = {"a": _event(True)}
    assert H.choose_weights(grid, grid[1], t, weighted_map)["chosen"] is grid[1]
    assert H.choose_weights(grid, {"good": 9.0}, t, weighted_map)["chosen"] is grid[0]


def test_choose_weights_without_a_qualifying_tuning_event_keeps_the_default():
    c, f, v, b = _event(True, n=10)
    d = {"good": 1.0}
    sel = H.choose_weights([{"good": 2.0}], d, {"a": (c, f, v, b)}, weighted_map)
    assert sel["chosen"] is d and "default kept" in sel["reason"]


def test_heldout_needs_two_qualifying_events_and_uses_the_bar():
    q = {"qualifies": True, "auc": 0.8}
    no = {"qualifies": False, "auc": None}
    assert H.heldout_verdict({"a": q, "b": no})["verdict"] == "not-run"
    assert H.heldout_verdict({"a": q, "b": {"qualifies": True, "auc": 0.6}}) == \
        {"verdict": "validated", "auc": 0.7, "qualifying_events": 2}
    assert H.heldout_verdict({"a": q, "b": {"qualifies": True, "auc": 0.59}})["verdict"] == "failed"


def test_heldout_events_are_scored_only_with_the_chosen_weights(monkeypatch):
    """The tuning table never contains a held-out event, and held-out events
    are evaluated exactly once."""
    calls = []
    real = H.event_auc

    def spy(score, flooded, valid, block=1):
        calls.append(score.shape)
        return real(score, flooded, valid, block)

    monkeypatch.setattr(H, "event_auc", spy)
    good = _event(True)
    held_shape = (2, 120)
    hc, hf, hv, _ = _event(True, n=120)

    def comps_for(module, arrays):
        return {"low_hand": arrays["c"], "river_size": 1 - arrays["c"]}, weighted_map

    monkeypatch.setattr(H, "components_for", comps_for)
    built = {
        "t1": {"arrays": {"c": good[0]["good"], "flooded": good[1], "valid": good[2]},
               "meta": {"block": 1}},
        "h1": {"arrays": {"c": hc["good"], "flooded": hf, "valid": hv}, "meta": {"block": 1}},
        "h2": {"arrays": {"c": hc["good"], "flooded": hf, "valid": hv}, "meta": {"block": 1}},
    }
    events = {"t1": {"split": "tuning"}, "h1": {"split": "held-out"},
              "h2": {"split": "held-out"}}
    out = H.evaluate_module("fluvial", events, built)
    assert all(set(t["per_event"]) == {"t1"} for t in out["tuning"]["table"])
    assert calls.count(held_shape) == 2              # h1 and h2, once each
    assert out["held_out"]["verdict"] == "validated"


# ── the registry is the pre-registered one ────────────────────────────

def test_event_registry_matches_the_preregistration():
    E = H.EVENTS
    split = {m: {s: sorted(n for n, e in ev.items() if e["split"] == s)
                 for s in ("tuning", "held-out")} for m, ev in E.items()}
    assert split["pluvial"] == {"tuning": ["dharavi"],
                                "held-out": ["belize_city", "hai_phong", "milagro"]}
    assert split["fluvial"] == {"tuning": ["encantado", "faenza"],
                                "held-out": ["hanoi", "hue", "kolonnawa", "nysa"]}
    assert split["flash_flood"] == {"tuning": ["bad_neuenahr", "derna", "paiporta"],
                                    "held-out": ["choloma", "kastelli", "volos"]}
    assert split["coastal"] == {"tuning": ["kyaukpyu"],
                                "held-out": ["beira", "black_river", "fort_myers_beach", "sittwe"]}
    assert split["waterlogging"]["held-out"] == ["jakarta_gfd_3280", "nam_dinh", "thai_binh"]
    assert "jakarta" not in split["waterlogging"]["tuning"]
    assert len(split["waterlogging"]["tuning"]) == 8
    assert E["coastal"]["beira"]["ref"] == ("s1", "coastal")
    assert E["flash_flood"]["derna"]["ref"] == ("s1", "default")
    assert E["flash_flood"]["volos"]["ref"] == ("ems", "EMSR692", 1, 3)


def test_no_firewalled_city_is_used():
    names = {n for ev in H.EVENTS.values() for n in ev}
    assert not names & {"lagos", "nairobi", "rio", "rocinha", "kibera", "makoko"}


def test_round1_sites_are_never_held_out():
    round1 = {"dharavi", "derna", "bad_neuenahr", "paiporta", "hcmc", "kigali", "accra",
              "dhaka", "capetown", "guatemala", "nusantara", "jakarta"}
    for m, ev in H.EVENTS.items():
        for n, e in ev.items():
            if n in round1:
                assert e["split"] == "tuning", (m, n)


def test_bar_and_minimums_are_round_1s():
    assert H.AUC_MIN == 0.70 and H.MIN_FLOODED_CELLS == 50 and H.MIN_DRY_CELLS == 50
    assert H.MIN_HELDOUT_EVENTS == 2


def test_built_paint_is_fetched_in_strips_that_tile_the_grid():
    """HCMC's whole-box 2 m paint is over Earth Engine's request limit; the
    strips must cover every row exactly once, each at its own offset."""
    from rasterio.transform import from_origin
    t = from_origin(600000, 1200000, 30, 30)
    rows = H.strip_rows(370, 30.0)
    assert rows * 370 * 225 <= H.STRIP_MAX_PAINT_PX
    strips = H.row_strips(t, (370, 370), rows)
    covered = np.concatenate([np.arange(r0, r1) for r0, r1, _ in strips])
    assert covered.tolist() == list(range(370))
    r0, r1, ts = strips[1]
    assert ts.f == 1200000 - 30 * r0 and ts.c == 600000
