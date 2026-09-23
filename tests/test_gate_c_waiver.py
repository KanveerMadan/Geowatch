r"""
C23/C24 regression tests — the Gate C waiver must survive every output path.

04_FINDINGS_LEDGER.md C23 [E], build item 42: `compute_exposure_for_layer()`'s
`not_calculated` path returned exactly `['label','layer_id','reason','status']`.
`product_validation_status` was absent, so `.get()` returned `None`.

WHY `None` IS THE BUG, not merely untidy. `None` is also what a caller sees
once Gate C is PASSED and the waiver field is removed. So "this output has
never been reviewed by a real user" and "this output has been reviewed and
cleared" arrived as the same value. The waiver did not weaken — it inverted.

That path was never exercised: the ledger records that all five layers took the
success path on the real runs, and surfacing it naturally needs an inland AOI.
So these tests force it directly.

C24 [S]: the frontend never read the field — zero occurrences in App.jsx. That
half is covered in tests/test_gate_c_ui.mjs.

SCOPE NOTE. C23 names the exposure module. While fixing it, `risk/compute.py`
was found to have the identical defect one level up, and worse: four return
paths, only the last carrying `exposure_product_validation_status`. The three
early returns are the ones that actually fire in Phase 10A, because the fusion
methodology is deliberately undefined — so the waiver disappeared on every real
run, at the layer that module's own docstring calls "the most consequential
output this system produces". Fixed in the same pass and asserted here.

Run from the repo root:  pytest tests/test_gate_c_waiver.py
"""

import pytest

from exposure.compute import (
    EvidenceLayer,
    GATE_C_STATUS,
    GATE_C_STATUS_NO_PRODUCT,
    compute_exposure_for_layer,
)
from risk.compute import compute_risk


def _layer(status):
    return EvidenceLayer(
        layer_id="fluvial_susceptibility",
        label="Fluvial susceptibility",
        evidence_type="long_term_screening",
        status=status,
        mask_source="aoi_wide_scalar",
        threshold_or_score=None,
        temporal_scope="static/contextual",
        limitations=[],
    )


# Statuses that send compute_exposure_for_layer() down the not_calculated path.
# These are real susceptibility statuses, not invented ones -- a fluvial or
# coastal layer reports insufficient_evidence on an inland AOI.
NOT_CALCULATED_STATUSES = [
    pytest.param("insufficient_evidence", id="insufficient-evidence"),
    pytest.param("not_calculated", id="not-calculated"),
    pytest.param("not_applicable", id="not-applicable"),
    pytest.param("unavailable", id="unavailable"),
    pytest.param("low_relevance", id="low-relevance"),
]


# ── C23: the exposure module ──

@pytest.mark.parametrize("status", NOT_CALCULATED_STATUSES)
def test_not_calculated_path_carries_the_waiver(status):
    """
    The exact assertion C23 describes. Before item 42 this returned four keys
    and `.get()` gave None.
    """
    result = compute_exposure_for_layer(_layer(status), None, population_context=None)
    assert result["status"] == "not_calculated", "precondition: this is the dropped path"
    assert "product_validation_status" in result, (
        "C23: the waiver field is absent on the not_calculated path"
    )
    assert result["product_validation_status"] is not None


@pytest.mark.parametrize("status", NOT_CALCULATED_STATUSES)
def test_not_calculated_waiver_is_indistinguishable_from_nothing_no_longer(status):
    """
    The property that actually matters: a caller can tell "waived" from
    "passed". If Gate C is ever passed, the field changes or disappears; while
    it is waived, it must say so out loud.
    """
    result = compute_exposure_for_layer(_layer(status), None, population_context=None)
    assert result.get("product_validation_status") == GATE_C_STATUS


def test_success_and_failure_paths_agree_on_the_field_name():
    """
    Both paths must use the same key, or a consumer reading one would silently
    miss the other -- which is the shape of the original bug.
    """
    failed = compute_exposure_for_layer(_layer("insufficient_evidence"), None,
                                        population_context=None)
    # The success path's constant is asserted directly rather than by running
    # it, because the success path needs a live ee.Geometry.
    assert "product_validation_status" in failed
    assert GATE_C_STATUS == "waived_pending_real_user_validation"


def test_waiver_string_is_not_hardcoded_at_the_call_site():
    """
    exposure/compute.py's docstring: GATE_C_STATUS "is the single source of
    truth for Gate C's status -- read it here, do not hardcode the string
    'waived...' anywhere else." A second literal would be S3 (a contract
    enforced only by prose) and would drift the day Gate C is passed.
    """
    import inspect
    import exposure.compute as mod
    src = inspect.getsource(mod.compute_exposure_for_layer)
    assert '"waived_pending_real_user_validation"' not in src, (
        "the waiver string is hardcoded inside the function; use GATE_C_STATUS"
    )


# ── The same defect one level up: risk ──

RISK_PATHS = [
    pytest.param({}, id="no-hazard"),
    pytest.param({"hazard": {"status": "experimental"}}, id="no-exposure"),
    pytest.param(
        {"hazard": {"status": "experimental"},
         "exposure": {"status": "available", "product_validation_status": GATE_C_STATUS}},
        id="no-vulnerability"),
    pytest.param(
        {"hazard": {"status": "experimental"},
         "exposure": {"status": "available", "product_validation_status": GATE_C_STATUS},
         "vulnerability": {"status": "available"}},
        id="all-available"),
]


@pytest.mark.parametrize("kwargs", RISK_PATHS)
def test_every_risk_path_reports_gate_c(kwargs):
    """
    All four return paths, not just the last. risk/compute.py's own docstring
    requires the field be propagated "rather than silently disappearing two
    layers up the stack"; it was carried on one path out of four.
    """
    result = compute_risk(**kwargs)
    assert "exposure_product_validation_status" in result, (
        "a risk path dropped Gate C's status"
    )
    assert result["exposure_product_validation_status"] is not None


def test_risk_propagates_the_real_waiver_when_exposure_has_one():
    result = compute_risk(
        hazard={"status": "experimental"},
        exposure={"status": "available", "product_validation_status": GATE_C_STATUS},
        vulnerability=None,
    )
    assert result["exposure_product_validation_status"] == GATE_C_STATUS


@pytest.mark.parametrize(
    "exposure",
    [pytest.param(None, id="none"),
     pytest.param({}, id="empty-dict"),
     pytest.param({"status": "not_calculated"}, id="no-field")],
)
def test_risk_says_no_product_rather_than_none(exposure):
    """
    When there is no exposure product at all, that is a THIRD state -- neither
    "waived" nor "passed" -- and it gets its own string. Returning None here
    would reintroduce C23 at the risk layer.
    """
    result = compute_risk(hazard=None, exposure=exposure)
    assert result["exposure_product_validation_status"] == GATE_C_STATUS_NO_PRODUCT


def test_the_three_gate_c_values_are_all_distinct():
    """
    'waived', 'no product', and absent must be three distinguishable things.
    C23 was the collapse of the first and third into one.
    """
    assert GATE_C_STATUS != GATE_C_STATUS_NO_PRODUCT
    assert GATE_C_STATUS is not None
    assert GATE_C_STATUS_NO_PRODUCT is not None


def test_risk_does_not_crash_when_exposure_is_none():
    """The pre-fix success path called exposure.get() directly; None would raise."""
    result = compute_risk(hazard={"status": "experimental"}, exposure=None)
    assert result["status"] == "not_calculated"
