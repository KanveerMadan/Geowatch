"""Flood round 4, step 2: the three new methods on synthetic cases whose
answer is known by construction (PREREGISTRATION_ROUND4.md). No real event
is read here."""
import numpy as np
import pytest

from configs import flash_flood_constants as ffc, pluvial_constants as pc
from configs import waterlogging_constants as wc
from susceptibility import bluespots as B
from susceptibility import flash_flood as FF, pluvial as P, waterlogging as WL
from susceptibility.hydro_rasters import SOURCES, water_history_years
from susceptibility.inputs import surface

PX = 30.0
CELL = PX * PX


def _bowl(n=15, depth=2.0, rim=10.0):
    """A plane at `rim` with one round hollow `depth` deep in the middle."""
    y, x = np.mgrid[0:n, 0:n]
    r2 = (y - n // 2) ** 2 + (x - n // 2) ** 2
    return rim - depth * np.clip(1.0 - r2 / (n // 3) ** 2, 0.0, None)


def _two_bowls():
    """A slope falling east, with an upper and a lower hollow on it."""
    y, x = np.mgrid[0:11, 0:31]
    z = 20.0 - 0.2 * x
    for cx in (8, 22):
        z = z - 1.5 * np.clip(1.0 - ((y - 5) ** 2 + (x - cx) ** 2) / 9.0, 0.0, None)
    return z


def _rasters(**vals):
    shape = next(iter(vals.values())).shape
    return {"status": "available", "shape": shape, "errors": {},
            "layers": {k: surface(v, *SOURCES[k], "experimental") for k, v in vals.items()}}


# ── bluespots and fill-and-spill ──

def test_a_tilted_plane_has_no_bluespot_and_drains_to_the_edge():
    y, x = np.mgrid[0:8, 0:8]
    z = 5.0 + 0.1 * x + 0.05 * y
    F, recv, order = B.priority_flood(z)
    assert np.allclose(F, z)
    assert (B.bluespots(z, F, 0.10) == -1).all()
    assert len(order) == z.size and set(order) == set(range(z.size))


def test_a_hollow_that_must_fill_fills_to_its_spill_level_and_spills():
    z = _bowl()
    # the flat rim drains to the grid edge, so only the hollow's own cells feed it
    fs = B.fill_and_spill(z, np.full(z.shape, 0.9), design_mm=5000.0, pixel_m=PX,
                          min_depth_m=0.10)
    assert fs["n_bluespots"] == 1
    assert fs["stored_m3"][0] == pytest.approx(fs["storage_m3"][0])
    assert fs["spill_m3"][0] > 0
    c = z.shape[0] // 2
    assert fs["ponding_depth_m"][c, c] == pytest.approx(2.0, abs=1e-9)   # full to the rim
    assert fs["ponding_depth_m"][0, 0] == 0.0


def test_a_hollow_that_cannot_fill_holds_exactly_its_inflow_from_the_bottom_up():
    z = _bowl()
    fs = B.fill_and_spill(z, np.full(z.shape, 0.5), design_mm=2.0, pixel_m=PX, min_depth_m=0.10)
    n_in = int((B.bluespots(z, B.priority_flood(z)[0], 0.10) == 0).sum())
    runoff = 0.5 * 2.0 / 1000.0 * CELL * n_in           # the flat rim drains to the edge
    assert fs["inflow_m3"][0] == pytest.approx(runoff)
    assert fs["stored_m3"][0] == pytest.approx(runoff) and fs["spill_m3"][0] == 0.0
    d = fs["ponding_depth_m"]
    assert d.sum() * CELL == pytest.approx(runoff)       # the level holds exactly that
    c = z.shape[0] // 2
    assert 0 < d[c, c] < 2.0 and d[c, c] == d.max()      # deepest at the bottom
    wet = d > 0
    assert wet.sum() < (fs["bluespot_id"] >= 0).sum()    # the rim of the hollow stays dry


def test_the_upper_hollow_spills_into_the_lower_one_and_mass_balances():
    z = _two_bowls()
    c = np.full(z.shape, 0.9)
    fs = B.fill_and_spill(z, c, design_mm=300.0, pixel_m=PX, min_depth_m=0.10)
    assert fs["n_bluespots"] == 2
    ids = fs["bluespot_id"]
    up, low = ids[5, 8], ids[5, 22]
    assert up >= 0 and low >= 0 and up != low
    assert fs["spill_m3"][up] > 0                         # the upper one overflows ...
    local_low = fs["inflow_m3"][low] - fs["spill_m3"][up]
    assert local_low > 0                                  # ... into the lower one
    total = 0.9 * 300.0 / 1000.0 * CELL * z.size
    never_ponded = total - fs["inflow_m3"][up] - local_low   # routed straight to the edge
    assert fs["stored_m3"].sum() + fs["spill_m3"][low] + never_ponded == pytest.approx(total)


def test_a_hollow_shallower_than_the_minimum_is_not_a_bluespot():
    z = _bowl(depth=0.05)
    F, _, _ = B.priority_flood(z)
    assert (B.bluespots(z, F, pc.PLUVIAL_BLUESPOT_MIN_DEPTH_M) == -1).all()


def test_water_level_fills_the_lowest_cells_first():
    z = np.array([0.0, 1.0, 2.0])
    assert B.water_level(z, 3.0, 0.5 * CELL, CELL) == pytest.approx(0.5)
    assert B.water_level(z, 3.0, 1.0 * CELL + 0.5 * CELL, CELL) == pytest.approx(1.25)
    assert B.water_level(z, 3.0, 1e9, CELL) == 3.0
    assert B.water_level(z, 3.0, 0.0, CELL) == -np.inf


def test_no_data_cells_are_outside_the_domain():
    z = _bowl()
    z[0, :] = np.nan
    fs = B.fill_and_spill(z, np.full(z.shape, 0.5), 50.0, PX, 0.10)
    assert np.isnan(fs["ponding_depth_m"][0]).all()
    assert np.isfinite(fs["ponding_depth_m"][1:]).all()


# ── pluvial ──

def _dem(z):
    return surface(z, "FABDEM", "bilinear", "experimental")


def test_pluvial_ranks_the_bottom_of_a_hollow_highest():
    z = _bowl()
    r = P.compute_pluvial_susceptibility(dem=_dem(z), design_storm_mm=100.0)
    m = r["susceptibility_map"]
    c = z.shape[0] // 2
    assert m[c, c] == pytest.approx(np.nanmax(m))
    assert m[c, c] > m[0, 0]
    assert r["method"] == P.METHOD and r["bluespots"]["count"] == 1


def test_impervious_ground_fills_a_hollow_that_pervious_ground_does_not():
    z = _bowl()
    soft = P.components(z, np.zeros(z.shape), 6.0, pc.PLUVIAL_RUNOFF_C_PERVIOUS)
    hard = P.components(z, np.ones(z.shape), 6.0, pc.PLUVIAL_RUNOFF_C_PERVIOUS)
    assert hard["ponding"].max() > soft["ponding"].max()
    assert hard["_fill_and_spill"]["stored_m3"][0] == pytest.approx(
        3.0 * soft["_fill_and_spill"]["stored_m3"][0])      # 0.9 vs 0.3


def test_pluvial_reads_the_design_storm_layer_and_takes_its_inputs_label():
    z = _bowl()
    imp = surface(np.full(z.shape, 0.5), "OB", "footprint_union_area_fraction", "placeholder")
    r = P.compute_pluvial_susceptibility(
        dem=_dem(z), impervious=imp,
        rasters=_rasters(rain_design_day_mm=np.full(z.shape, 120.0)))
    assert r["design_storm_mm"] == 120.0
    assert r["validation_status"] == "placeholder"
    assert set(r["inputs"]) == {"dem", "impervious", "rain_design_day_mm"}


def test_pluvial_without_dem_or_storm_is_insufficient_evidence():
    z = _bowl()
    assert P.compute_pluvial_susceptibility()["status"] == "insufficient_evidence"
    r = P.compute_pluvial_susceptibility(dem=_dem(z), rasters={"errors": {
        "rain_design_day_mm": "TimeoutError"}, "layers": {}})
    assert r["status"] == "insufficient_evidence" and "TimeoutError" in r["reason"]


def test_pluvial_refuses_inputs_on_another_grid():
    z = _bowl()
    imp = surface(np.zeros((3, 3)), "OB", "x", "placeholder")
    with pytest.raises(ValueError, match="grid"):
        P.compute_pluvial_susceptibility(dem=_dem(z), impervious=imp, design_storm_mm=50.0)


# ── flash flood ──

def _valley(n=21):
    """A V-shaped valley: HAND 0 on the channel (middle column) rising 3 m per
    cell up both walls; the channel drains 40 km^2, the walls almost nothing."""
    _, x = np.mgrid[0:n, 0:n]
    off = np.abs(x - n // 2)
    hand = 3.0 * off
    upa = np.where(off <= 1, 40.0, 0.05)
    return hand, upa


def test_a_channel_outscores_its_hillside():
    hand, upa = _valley()
    r = FF.compute_flash_flood_susceptibility(_rasters(
        hand_m=hand, upa_flash_km2=upa, relief_slope_deg=np.full(hand.shape, 20.0),
        rain_intensity_mm_h=np.full(hand.shape, 30.0)))
    m = r["susceptibility_map"]
    c = hand.shape[1] // 2
    assert m[:, c].min() > m[:, c + 2].max()                  # channel above valley wall
    assert (m[:, c + 4:] == 0).all()                          # HAND >= 10 m: a hillside, 0
    assert r["validation_status"] == "experimental"


def test_a_steep_fast_catchment_outscores_a_gentle_slow_one():
    a = np.array([10.0])
    steep, tc_s, i_s, _ = FF.stream_power(a, np.tan(np.radians(25.0)), 30.0)
    gentle, tc_g, i_g, _ = FF.stream_power(a, np.tan(np.radians(2.0)), 30.0)
    assert tc_s[0] < tc_g[0]                                  # faster response ...
    assert i_s[0] >= i_g[0]                                   # ... meets a more intense rain
    assert steep[0] > gentle[0]


def test_response_time_grows_with_catchment_size():
    t = FF.response_time_h(np.array([0.1, 10.0, 1000.0]), 0.1)
    assert t[0] < t[1] < t[2]


def test_without_imerg_the_fallback_is_used_and_said():
    hand, upa = _valley()
    rel = np.full(hand.shape, 20.0)
    with_rain = FF.compute_flash_flood_susceptibility(_rasters(
        hand_m=hand, upa_flash_km2=upa, relief_slope_deg=rel,
        rain_intensity_mm_h=np.full(hand.shape, ffc.FLASH_POWER_INTENSITY_FALLBACK_MM_H)))
    rasters = _rasters(hand_m=hand, upa_flash_km2=upa, relief_slope_deg=rel)
    rasters["errors"] = {"rain_intensity_mm_h": "EEException: computation timed out"}
    without = FF.compute_flash_flood_susceptibility(rasters)
    assert np.allclose(with_rain["susceptibility_map"], without["susceptibility_map"])
    assert any("IMERG unavailable" in e for e in without["components_excluded"])


def test_flash_flood_without_terrain_is_insufficient_evidence():
    assert FF.compute_flash_flood_susceptibility(None)["status"] == "insufficient_evidence"
    hand, _ = _valley()
    assert FF.compute_flash_flood_susceptibility(_rasters(hand_m=hand))["status"] \
        == "insufficient_evidence"


# ── waterlogging ──

def _flat(v, n=6):
    return np.full((n, n), float(v))


def test_ground_that_held_water_before_outscores_ground_that_did_not():
    jrc = _flat(0.0)
    jrc[:, :3] = 0.6
    r = WL.compute_waterlogging_susceptibility(_rasters(
        hand_m=_flat(2.0), upa_near_km2=_flat(50.0), clay_pct=_flat(20.0),
        jrc_water_freq=jrc, s1_water_freq=jrc))
    m = r["susceptibility_map"]
    assert m[:, :3].min() > m[:, 3:].max()


def test_clay_raises_the_score_and_low_land_beside_a_big_river_is_backwater():
    c = WL.components(_rasters(hand_m=np.array([[1.0, 1.0, 1.0]]),
                               upa_near_km2=np.array([[20000.0, 1000.0, 50.0]]),
                               clay_pct=np.array([[50.0, 20.0, 0.0]])))
    assert c["clay"].tolist() == [[1.0, 0.5, 0.0]]
    bw = c["backwater"][0]
    assert bw[0] == pytest.approx(0.8) and bw[1] == pytest.approx(0.4) and bw[2] == 0.0


def test_persistence_averages_whichever_history_exists_per_cell():
    jrc = np.array([[0.2, np.nan, np.nan]])
    s1 = np.array([[0.6, 0.4, np.nan]])
    p = WL.persistence(jrc, s1)
    assert p[0, 0] == pytest.approx(0.4) and p[0, 1] == pytest.approx(0.4)
    assert np.isnan(p[0, 2])
    assert WL.persistence(None, None) is None


def test_water_history_reads_only_years_before_the_event():
    assert water_history_years(2026) == {"jrc_water_freq": (1984, 2021),
                                         "s1_water_freq": (2023, 2025)}
    assert water_history_years(2018) == {"jrc_water_freq": (1984, 2017),
                                         "s1_water_freq": (2015, 2017)}


def test_waterlogging_without_any_input_is_insufficient_evidence():
    assert WL.compute_waterlogging_susceptibility(None)["status"] == "insufficient_evidence"


# ── the pre-registered constants and grids ──

def test_constants_match_the_preregistration():
    assert pc.PLUVIAL_BLUESPOT_MIN_DEPTH_M == 0.10
    assert (pc.PLUVIAL_RUNOFF_C_IMPERVIOUS, pc.PLUVIAL_RUNOFF_C_PERVIOUS) == (0.90, 0.30)
    assert pc.PLUVIAL_PONDING_DEPTH_MAX_M == 1.0 and pc.PLUVIAL_CATCHMENT_MARGIN_M == 1000.0
    assert pc.PLUVIAL_WEIGHTS == {"ponding": 1.0, "runoff_path": 0.5}
    assert len(pc.PLUVIAL_PARAM_GRID) == 12 and pc.PLUVIAL_PARAM_DEFAULT in pc.PLUVIAL_PARAM_GRID
    assert ffc.FLASH_POWER_DRAINAGE_RADIUS_M == 300.0 and ffc.FLASH_POWER_IDF_EXPONENT == 0.6
    assert ffc.FLASH_POWER_PARAMS == {"hand_max_m": 10.0, "power_exponent": 1.0}
    assert len(ffc.FLASH_POWER_PARAM_GRID) == 9 and ffc.FLASH_POWER_PARAMS in ffc.FLASH_POWER_PARAM_GRID
    assert wc.WATERLOGGING_S1_WATER_DB == -18.0 and wc.WATERLOGGING_S1_YEARS == 3
    assert wc.WATERLOGGING_CLAY_MAX_PCT == 40.0 and wc.WATERLOGGING_BACKWATER_HAND_MAX_M == 5.0
    assert len(wc.WATERLOGGING_R4_WEIGHT_GRID) == 36
    assert wc.WATERLOGGING_R4_WEIGHTS in wc.WATERLOGGING_R4_WEIGHT_GRID
