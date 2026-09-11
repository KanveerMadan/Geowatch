r"""
C14/C20 regression tests — `applicability` gates downstream computation.

04_FINDINGS_LEDGER.md C14 [E], build item 40: `compute_applicability()`
produced a correct out-of-distribution verdict on every run and nothing
consumed it. All 8 `compute_*` functions in `susceptibility/` and `perception/`
were enumerated by AST and none took an applicability argument. Confirmed by
execution at `unknown_pct = 60`: the pipeline returned
`urban_landcover_model: out_of_distribution` in the same dictionary as
`pluvial: applicable` and `waterlogging: applicable`.

C20: it did not gate its own siblings either. 01_DIAGNOSIS.md §4 S2 names the
pattern — *signals computed, then never consumed*, "designed as a router, wired
as a report."

THE ACCEPTANCE CRITERION, from build item 40: given a synthetic result with
`out_of_distribution: true`, every susceptibility / exposure / risk block must
carry the flag. `test_every_block_carries_the_flag` is that assertion.

But "carries the flag" is deliberately not the same as "is marked
out_of_distribution". Item 40 also requires modelling the dependency chain
rather than treating mechanisms as independent branches, and blanket-flagging
would be *wrong*, not merely conservative: `fluvial` reads MERIT Hydro,
`coastal` reads a GEE shoreline dataset, `flash_flood` reads slope and upstream
catchment. None touch the semantic model. So the tests below assert BOTH that
every block carries a flag AND that the flag tells the truth about which
mechanisms the land-cover verdict actually reaches.

Run from the repo root:  pytest tests/test_applicability_gating.py
"""

import inspect

import numpy as np
import pytest

from perception.applicability import compute_applicability, finalize_applicability
from perception.applicability_gate import (
    LANDCOVER_DERIVED,
    LANDCOVER_INDEPENDENT,
    build_flag,
)
from perception.hydrological_surfaces import compute_hydrological_surfaces
from susceptibility.pluvial import compute_pluvial_susceptibility
from susceptibility.fluvial import compute_fluvial_susceptibility
from susceptibility.coastal import compute_coastal_susceptibility
from susceptibility.flash_flood import compute_flash_flood_susceptibility
from susceptibility.waterlogging import compute_waterlogging_susceptibility
from risk.compute import compute_risk


# ── Synthetic inputs ──
#
# unknown_pct = 60 is the exact value the original finding was confirmed at, so
# these tests reproduce the documented failure condition rather than an
# invented one. OOD_UNKNOWN_PCT_THRESHOLD is well below it.
OOD_UNKNOWN_PCT = 60
IN_DIST_UNKNOWN_PCT = 5

HAND_AVAILABLE = {
    "status": "available", "river_connectivity": True,
    "max_upstream_area_km2": 120.0, "buffer_km": 2,
    "mean_hnd_m": 4.0, "min_hnd_m": 0.5, "max_hnd_m": 20.0,
}

# A tiny real raster. compute_pluvial_susceptibility() indexes .shape and
# compares against category indices, so None will not do.
CATEGORIES = ["dense_informal_roofing", "paved_road", "vegetation", "water"]
LANDCOVER_MAP = np.array([[0, 1], [2, 3]], dtype=np.uint8)
WATERWAY_DIST_MAP = np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32)
COASTAL_AVAILABLE = {
    "status": "available", "distance_km": 3.0,
    "coastal_connectivity": True, "search_radius_km": 50,
}
SLOPE_AVAILABLE = {"status": "available", "mean_slope_deg": 3.2}
RAINFALL = {"status": "available", "mean_annual_mm": 1800.0}


def _applicability(unknown_pct):
    """Build a full two-stage applicability block, as the pipeline now does."""
    app = compute_applicability(
        unknown_pct=unknown_pct,
        ambiguous_pct=2,
        hand_context=HAND_AVAILABLE,
        coastal_context=COASTAL_AVAILABLE,
        slope_context=SLOPE_AVAILABLE,
        hydrological_surfaces=None,
    )
    surfaces = compute_hydrological_surfaces({"dense_informal_roofing": 40.0})
    return finalize_applicability(app, surfaces), surfaces


@pytest.fixture
def ood():
    """An applicability block whose land-cover verdict is out_of_distribution."""
    app, surfaces = _applicability(OOD_UNKNOWN_PCT)
    assert app["urban_landcover_model"]["status"] == "out_of_distribution"
    return app, surfaces


@pytest.fixture
def in_dist():
    app, surfaces = _applicability(IN_DIST_UNKNOWN_PCT)
    assert app["urban_landcover_model"]["status"] == "in_distribution"
    return app, surfaces


def _all_blocks(app, surfaces):
    """
    Every susceptibility / exposure / risk block, computed the way pipeline.py
    computes them. Exposure is stubbed rather than called, because
    compute_exposure_for_layer() needs a live ee.Geometry; its gating is
    asserted separately in test_exposure_is_gated.
    """
    pluvial = compute_pluvial_susceptibility(
        landcover_map=LANDCOVER_MAP, categories=CATEGORIES,
        waterway_dist_map=WATERWAY_DIST_MAP,
        relative_elevation_score=0.5, rainfall_mean_annual_mm=1800.0,
        applicability=app,
    )
    blocks = {
        "pluvial": pluvial,
        "fluvial": compute_fluvial_susceptibility(HAND_AVAILABLE, applicability=app),
        "coastal": compute_coastal_susceptibility(COASTAL_AVAILABLE, None, applicability=app),
        "flash_flood": compute_flash_flood_susceptibility(
            SLOPE_AVAILABLE, HAND_AVAILABLE, RAINFALL, applicability=app),
        "waterlogging": compute_waterlogging_susceptibility(
            HAND_AVAILABLE, surfaces, RAINFALL, applicability=app),
    }
    exposure = {"status": "available", "applicability": build_flag("exposure", app)}
    blocks["exposure"] = exposure
    for key in ("pluvial", "fluvial", "coastal", "flash_flood", "waterlogging"):
        blocks[f"risk_{key}"] = compute_risk(
            hazard=blocks[key], exposure=exposure, vulnerability=None)
    return blocks


# ── The acceptance criterion from build item 40 ──

def test_every_block_carries_the_flag(ood):
    """
    THE acceptance assertion: with out_of_distribution true, every
    susceptibility / exposure / risk block carries the applicability flag.

    This is the test that would have failed before item 40 for all 11 blocks --
    none of the consumers accepted an applicability argument, so none could
    have carried anything.
    """
    app, surfaces = ood
    blocks = _all_blocks(app, surfaces)
    assert len(blocks) == 11, f"expected 11 blocks, got {sorted(blocks)}"

    missing = [name for name, b in blocks.items() if "applicability" not in b]
    assert not missing, f"blocks with no applicability flag: {missing}"

    for name, b in blocks.items():
        flag = b["applicability"]
        for field in ("status", "trust", "out_of_distribution",
                      "degraded", "depends_on", "degraded_by", "gate"):
            assert field in flag, f"{name}: flag missing {field!r}"
        assert flag["gate"] != "not_wired", (
            f"{name}: gate reports not_wired — applicability did not reach it"
        )


def test_hydrological_surfaces_carries_the_flag(ood):
    """
    The surfaces are a weighted sum of the model's own category_area_pct, so
    they are downstream of the verdict too. C21's own site.
    """
    app, surfaces = ood
    from perception.applicability_gate import annotate
    annotate(surfaces, app, "waterlogging")
    assert surfaces["applicability"]["out_of_distribution"] is True


# ── The dependency chain: the flag must tell the truth ──

@pytest.mark.parametrize("mechanism", sorted(LANDCOVER_DERIVED))
def test_landcover_derived_mechanisms_are_flagged_ood(ood, mechanism):
    """
    pluvial, waterlogging and exposure consume the semantic model, so an OOD
    verdict reaches them and must be recorded, with the cause named.
    """
    app, _ = ood
    flag = build_flag(mechanism, app)
    assert flag["out_of_distribution"] is True, f"{mechanism} should inherit OOD"
    assert flag["degraded_by"] == ["urban_landcover_model"]
    assert flag["depends_on"]["urban_landcover_model"] == "out_of_distribution"


@pytest.mark.parametrize("mechanism", sorted(LANDCOVER_INDEPENDENT))
def test_landcover_independent_mechanisms_are_not_flagged_ood(ood, mechanism):
    """
    fluvial / coastal / flash_flood read MERIT Hydro, a GEE shoreline dataset,
    and DEM slope. The semantic model's failure says nothing about them, and
    claiming otherwise would be false.

    This is the test that stops a later 'simplification' into blanket-flagging.
    A flag that fires everywhere carries no information -- the same way C33's
    `{pct ? ... : '0.0%'}` taught readers that 0.0% means nothing in particular.
    """
    app, _ = ood
    flag = build_flag(mechanism, app)
    assert flag["out_of_distribution"] is False, (
        f"{mechanism} does not consume the semantic model and must not be "
        f"marked out_of_distribution by it"
    )
    assert flag["degraded_by"] == []


def test_risk_inherits_from_what_it_consumed(ood):
    """
    compute_risk() has no applicability entry of its own; its trust is a
    function of the hazard and exposure it was handed. A landcover-derived
    hazard must drag risk down with it, and the reason must survive the hop
    rather than flattening to a bare boolean.
    """
    app, surfaces = ood
    blocks = _all_blocks(app, surfaces)
    wl_risk = blocks["risk_waterlogging"]["applicability"]
    assert wl_risk["gate"] == "inherited"
    assert wl_risk["out_of_distribution"] is True
    assert "urban_landcover_model" in wl_risk["degraded_by"]


def test_in_distribution_run_flags_nothing_ood(in_dist):
    """
    The negative control. Without it, a flag hardcoded to True would pass every
    assertion above while destroying the signal's meaning.
    """
    app, surfaces = in_dist
    blocks = _all_blocks(app, surfaces)
    flagged = [n for n, b in blocks.items() if b["applicability"]["out_of_distribution"]]
    assert not flagged, f"nothing should be OOD on a clean run, got {flagged}"


def test_degraded_is_distinct_from_out_of_distribution():
    """
    `degraded` (ambiguous_pct over threshold) and `out_of_distribution`
    (unknown_pct over threshold) are different verdicts and must not collapse
    into one another -- that collapse is S1, the system's inability to hold
    more than two epistemic states at once.
    """
    app = compute_applicability(
        unknown_pct=IN_DIST_UNKNOWN_PCT, ambiguous_pct=95,
        hand_context=HAND_AVAILABLE, coastal_context=None,
        slope_context=None, hydrological_surfaces=None,
    )
    assert app["urban_landcover_model"]["status"] == "degraded"
    flag = build_flag("pluvial", app)
    assert flag["degraded"] is True
    assert flag["out_of_distribution"] is False


# ── Ordering: the gate must run before the thing it gates ──

def test_applicability_is_computed_before_hydrological_surfaces():
    """
    C14's structural half. The verdict on the semantic model must be reached
    before surfaces are derived from that model, otherwise the router runs
    after the routing decision -- S2's "designed as a router, wired as a
    report".

    Asserted against pipeline.py's source, because this is a statement about
    call order that no unit-level call can demonstrate.
    """
    import pipeline
    src = inspect.getsource(pipeline.run_pipeline)
    i_app = src.index("applicability = compute_applicability(")
    i_surf = src.index("hydrological_surfaces = compute_hydrological_surfaces(")
    assert i_app < i_surf, (
        "compute_applicability() must be called before "
        "compute_hydrological_surfaces() — the gate runs before what it gates"
    )


def test_finalize_runs_after_surfaces_exist():
    """Stage 2 resolves the one status that genuinely needed the surfaces."""
    import pipeline
    src = inspect.getsource(pipeline.run_pipeline)
    i_surf = src.index("hydrological_surfaces = compute_hydrological_surfaces(")
    i_fin = src.index("applicability = finalize_applicability(")
    assert i_surf < i_fin


def test_two_stage_split_preserves_original_behaviour():
    """
    The reorder must not change any verdict. The original single call took
    hydrological_surfaces directly; the two-stage form must produce an
    identical block for every combination of inputs.
    """
    import itertools
    hs_cases = [None, {"impervious_fraction_pct": 12.3},
                {"impervious_fraction_pct": 0.0}, {}]
    hand_cases = [None, HAND_AVAILABLE, {"status": "unavailable"}]
    for u, a, hs, hc in itertools.product(
        [IN_DIST_UNKNOWN_PCT, OOD_UNKNOWN_PCT], [2, 95], hs_cases, hand_cases
    ):
        one = compute_applicability(
            unknown_pct=u, ambiguous_pct=a, hand_context=hc,
            coastal_context=COASTAL_AVAILABLE, slope_context=SLOPE_AVAILABLE,
            hydrological_surfaces=hs)
        one.pop("_hand_context_available", None)
        two = finalize_applicability(
            compute_applicability(
                unknown_pct=u, ambiguous_pct=a, hand_context=hc,
                coastal_context=COASTAL_AVAILABLE, slope_context=SLOPE_AVAILABLE,
                hydrological_surfaces=None),
            hs)
        assert one == two, f"two-stage diverged at {(u, a, hs, hc)}"


# ── Consumers must actually accept the gate ──

CONSUMERS = [
    compute_pluvial_susceptibility, compute_fluvial_susceptibility,
    compute_coastal_susceptibility, compute_flash_flood_susceptibility,
    compute_waterlogging_susceptibility,
]


@pytest.mark.parametrize("fn", CONSUMERS, ids=lambda f: f.__name__)
def test_consumer_accepts_applicability(fn):
    """
    The original finding enumerated all 8 compute_* functions by AST and found
    none took an applicability argument. This asserts the opposite now holds.
    """
    assert hasattr(fn, "__gated_mechanism__"), (
        f"{fn.__name__} is not gated — it cannot receive the applicability verdict"
    )


def test_exposure_is_gated():
    from exposure.compute import compute_exposure_for_layer
    assert getattr(compute_exposure_for_layer, "__gated_mechanism__", None) == "exposure"


def test_risk_is_gated():
    assert getattr(compute_risk, "__gated_mechanism__", None) == "risk"


def test_omitting_applicability_is_reported_not_silently_trusted(ood):
    """
    A consumer called without the gate must say so. Silently presenting an
    ungated result as trustworthy is precisely C14, and a fix that reintroduced
    it through the back door would be worse than the original -- the flag would
    be present and wrong.
    """
    r = compute_fluvial_susceptibility(HAND_AVAILABLE)
    assert r["applicability"]["gate"] == "not_wired"
    assert r["applicability"]["trust"] == "unknown"


def test_compute_and_flag_not_refuse_to_compute(ood):
    """
    Item 40 rule 3: prefer compute-and-flag. An OOD verdict must not suppress
    the computed value -- refusing loses information, flagging preserves it
    honestly, and a withheld value would add a fourth ambiguous state for
    downstream code to guess about (S1 again).
    """
    app, surfaces = ood
    wl = compute_waterlogging_susceptibility(
        HAND_AVAILABLE, surfaces, RAINFALL, applicability=app)
    assert wl["applicability"]["out_of_distribution"] is True
    assert wl.get("status") != "withheld"
    assert "aoi_mean_score" in wl, (
        "the value was withheld rather than flagged — item 40 requires "
        "compute-and-flag"
    )
