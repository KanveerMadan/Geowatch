r"""
C16 regression tests — unauthenticated path traversal via `aoi_label`.

AUDIT_FINDINGS_V2.md C16 (CONFIRMED, Critical): `aoi_label` arrives unvalidated
on the request body and becomes a filesystem path component inside
run_pipeline() / run_inundation_analysis(), which build
`<output_dir>/<aoi_label>_<timestamp>`. The audit verified by path arithmetic
that '../../../../tmp/pwn' normalises to '../../tmp/pwn_<timestamp>', escaping
the data root. Nothing was created during that audit, and nothing is created
here either — these tests never let a request reach the pipeline.

The property under test is REJECTION, not sanitisation. A fix that stripped the
offending characters and continued would still create a run under a label the
caller never asked for, and would collide distinct AOIs onto one directory
('../a' and 'a' both landing on 'a'). So every assertion below checks for HTTP
400 plus the pipeline never being invoked.

Run from the repo root:  pytest tests/test_api_aoi_label_validation.py
"""

import sys
import types

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


# A bbox well inside MAX_AOI_AREA_KM2 (the canonical Dharavi AOI, ~7 km²), so a
# request that is rejected is rejected for the LABEL and nothing else. If the
# bbox were oversized, a 400 would prove nothing about aoi_label.
VALID_BBOX = {"west": 72.836, "south": 19.037, "east": 72.862, "north": 19.060}

INUNDATION_DATES = {
    "pre_event_start": "2025-05-01", "pre_event_end": "2025-05-31",
    "event_start": "2025-07-01", "event_end": "2025-07-31",
}


class _PipelineInvoked(AssertionError):
    """Raised if a rejected request reaches the pipeline. See stub_pipeline."""


@pytest.fixture(autouse=True)
def stub_pipeline(monkeypatch):
    """
    Replace the `pipeline` module with a stub that EXPLODES if called.

    Two jobs. First, it makes "the request never reached path construction" an
    assertable fact rather than an inference — if validation regresses, the
    traversal tests fail loudly instead of silently passing for the wrong
    reason. Second, it keeps the real pipeline (GEE auth, torch, SAM) out of a
    unit test entirely; both endpoints import it lazily inside the handler, so
    injecting into sys.modules is enough.
    """
    calls = []

    def _boom(*args, **kwargs):
        calls.append(kwargs)
        raise _PipelineInvoked(
            f"pipeline was invoked with aoi_label={kwargs.get('aoi_label')!r} "
            f"— validation did not reject it before path construction"
        )

    stub = types.ModuleType("pipeline")
    stub.run_pipeline = _boom
    stub.run_inundation_analysis = _boom
    stub.calls = calls
    monkeypatch.setitem(sys.modules, "pipeline", stub)
    return stub


@pytest.fixture
def client():
    """
    An AUTHENTICATED client. C40 (build item 70) put an API-key check at the
    perimeter, so an unauthenticated request now stops at 401 and never reaches
    aoi_label validation at all. These tests are about the 400, so they must get
    past the 401 first — otherwise every assertion below would pass for entirely
    the wrong reason. C40's own 401 behaviour is covered in
    tests/test_api_authentication.py.
    """
    import api
    return TestClient(api.app, headers={api.API_KEY_HEADER_NAME: api.API_KEY})


# ── The payloads ──
#
# Named so a failure report says which class of attack got through.
TRAVERSAL_PAYLOADS = [
    pytest.param("../", id="relative-parent"),
    pytest.param("../../../../tmp/pwn", id="audit-c16-exact-payload"),
    pytest.param("..\\", id="windows-backslash-parent"),
    pytest.param("..\\..\\windows\\system32", id="windows-deep-traversal"),
    pytest.param("/etc/passwd", id="absolute-posix"),
    pytest.param("/tmp/pwn", id="absolute-posix-tmp"),
    pytest.param("C:\\Windows\\Temp", id="absolute-windows-drive"),
    pytest.param("\\\\server\\share", id="unc-path"),
    pytest.param("aoi\x00.png", id="null-byte-embedded"),
    pytest.param("\x00", id="null-byte-only"),
    pytest.param("a" * 65, id="over-length-65"),
    pytest.param("a" * 4096, id="over-length-4096"),
]

# Not traversal, but must also be rejected: each would still corrupt the run
# directory name, and the whitelist is what makes that automatic.
ADJACENT_REJECTS = [
    pytest.param("", id="empty"),
    pytest.param(".", id="single-dot"),
    pytest.param("..", id="double-dot-bare"),
    pytest.param("aoi\n", id="trailing-newline"),
    pytest.param("aoi\nrm -rf /", id="embedded-newline"),
    pytest.param("aoi label", id="space"),
    pytest.param("AOI", id="uppercase"),
    pytest.param("aoi/../x", id="traversal-mid-string"),
    pytest.param("aoi;rm -rf /", id="shell-metacharacters"),
    pytest.param("%2e%2e%2f", id="url-encoded-traversal"),
    pytest.param("café", id="non-ascii"),
]

VALID_LABELS = [
    pytest.param("aoi", id="default"),
    pytest.param("dharavi", id="watched-aoi"),
    pytest.param("phase12b_wide_datameet_mumbai_bmc_wards", id="real-underscored"),
    pytest.param("ward-01", id="hyphenated"),
    pytest.param("a", id="single-char-min"),
    pytest.param("0", id="digit"),
    pytest.param("a" * 64, id="exactly-max-length-64"),
]


# ── Unit level: the validator itself ──

@pytest.mark.parametrize("label", TRAVERSAL_PAYLOADS + ADJACENT_REJECTS)
def test_validator_rejects_with_400(label):
    from api import validate_aoi_label
    with pytest.raises(HTTPException) as exc:
        validate_aoi_label(label)
    assert exc.value.status_code == 400
    # Rejected, not rewritten, and the attacker-controlled value is not
    # reflected back: the detail is a fixed constant string. Asserting the
    # constant (rather than `label not in detail`) is what makes this hold for
    # every payload — a bare '.' is a substring of the message's own trailing
    # full stop, so a naive non-reflection check false-fails on it.
    assert str(exc.value.detail) == (
        "Invalid aoi_label. Allowed characters: lowercase a-z, "
        "digits 0-9, underscore and hyphen; length 1-64."
    )


@pytest.mark.parametrize("label", VALID_LABELS)
def test_validator_accepts_valid_labels_unchanged(label):
    """Positive control. Without this, a validator that rejects everything
    would pass every rejection test above."""
    from api import validate_aoi_label
    assert validate_aoi_label(label) == label


def test_validator_returns_label_byte_for_byte():
    """Explicitly asserts the no-sanitise contract: the returned label is the
    input, not a cleaned-up version of it."""
    from api import validate_aoi_label
    assert validate_aoi_label("my-aoi_01") == "my-aoi_01"


def test_length_boundary_is_exactly_64():
    from api import validate_aoi_label
    assert validate_aoi_label("a" * 64) == "a" * 64
    with pytest.raises(HTTPException) as exc:
        validate_aoi_label("a" * 65)
    assert exc.value.status_code == 400


# ── HTTP level: /api/analyze ──

@pytest.mark.parametrize("label", TRAVERSAL_PAYLOADS)
def test_analyze_rejects_traversal_with_400(client, stub_pipeline, label):
    resp = client.post("/api/analyze", json={**VALID_BBOX, "aoi_label": label})
    assert resp.status_code == 400, (
        f"aoi_label={label!r} returned {resp.status_code}, expected 400"
    )
    assert stub_pipeline.calls == [], "pipeline was reached despite rejection"


@pytest.mark.parametrize("label", ADJACENT_REJECTS)
def test_analyze_rejects_adjacent_bad_labels_with_400(client, stub_pipeline, label):
    resp = client.post("/api/analyze", json={**VALID_BBOX, "aoi_label": label})
    assert resp.status_code == 400
    assert stub_pipeline.calls == []


def test_analyze_rejects_traversal_even_in_demo_mode(client, stub_pipeline):
    """
    `demo: true` short-circuits to get_demo() and never uses aoi_label, so it
    would be tempting to validate after that branch. Validating before it means
    no request shape at all can carry an unchecked label into the handler —
    fail closed, with no exempt path to reason about later.
    """
    resp = client.post(
        "/api/analyze",
        json={**VALID_BBOX, "aoi_label": "../../../../tmp/pwn", "demo": True},
    )
    assert resp.status_code == 400


def test_analyze_400_is_not_masked_as_500(client, stub_pipeline):
    """
    The handler wraps run_pipeline in `except Exception -> HTTPException(500)`.
    HTTPException is itself an Exception, so a validation raised INSIDE that
    try block would be swallowed and re-emitted as a 500. This asserts the
    check sits outside it. A 500 here means the fix was placed wrongly, even
    though the request was still (accidentally) refused.
    """
    resp = client.post(
        "/api/analyze", json={**VALID_BBOX, "aoi_label": "../../../../tmp/pwn"}
    )
    assert resp.status_code == 400
    assert resp.status_code != 500


def test_analyze_valid_label_passes_validation_and_reaches_pipeline(client, stub_pipeline):
    """
    Positive control at the HTTP layer: a well-formed label must get PAST
    validation. The stub raises _PipelineInvoked on call, which the handler's
    except-Exception converts to a 500 — so a 500 carrying the stub's message
    is proof the label was accepted and forwarded, and that the 400s above are
    about the label rather than a blanket refusal.
    """
    resp = client.post("/api/analyze", json={**VALID_BBOX, "aoi_label": "dharavi"})
    assert resp.status_code == 500
    assert "validation did not reject it" in resp.json()["detail"]
    assert stub_pipeline.calls[0]["aoi_label"] == "dharavi"


# ── HTTP level: /api/analyze_inundation ──
#
# The second, easily-forgotten sink. It takes aoi_label on its own request
# model and passes it to run_inundation_analysis(), which builds a run
# directory the same way.

@pytest.mark.parametrize("label", TRAVERSAL_PAYLOADS)
def test_analyze_inundation_rejects_traversal_with_400(client, stub_pipeline, label):
    resp = client.post(
        "/api/analyze_inundation",
        json={**VALID_BBOX, **INUNDATION_DATES, "aoi_label": label},
    )
    assert resp.status_code == 400, (
        f"aoi_label={label!r} returned {resp.status_code}, expected 400"
    )
    assert stub_pipeline.calls == [], "pipeline was reached despite rejection"


def test_analyze_inundation_valid_label_reaches_pipeline(client, stub_pipeline):
    resp = client.post(
        "/api/analyze_inundation",
        json={**VALID_BBOX, **INUNDATION_DATES, "aoi_label": "dharavi"},
    )
    assert resp.status_code == 500
    assert stub_pipeline.calls[0]["aoi_label"] == "dharavi"


# ── The concrete escape the audit described ──

def test_audit_payload_cannot_escape_data_root():
    """
    Demonstrates the bug C16 reported, then asserts the boundary now stops it.

    The first half is pure path arithmetic on a string — it creates nothing —
    and documents WHY the label matters: joined into the runs directory and
    normalised, it lands outside the data root.
    """
    import os
    from api import validate_aoi_label

    payload = "../../../../tmp/pwn"
    data_root = os.path.abspath("data/pipeline_runs")
    escaped = os.path.abspath(os.path.join(data_root, f"{payload}_20260822_000000"))

    # Precondition: this really does escape. If this ever stops holding, the
    # test below is no longer proving anything.
    assert not escaped.startswith(data_root + os.sep), (
        "payload no longer escapes the data root; this regression test is stale"
    )

    # And the API boundary refuses it before any such join can happen.
    with pytest.raises(HTTPException) as exc:
        validate_aoi_label(payload)
    assert exc.value.status_code == 400
