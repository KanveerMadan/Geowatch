r"""
C34 + C35 regression tests — path traversal at a READ boundary, and a sink that
bypasses the API boundary entirely.

04_FINDINGS_LEDGER.md C34 [S], build item 47: `GET /api/runs/{run_id}` built
`data/pipeline_runs/{run_id}/result.json` from an unvalidated path parameter.
Same bug class as C16, different sink — a read returning file contents, so the
impact shape is DISCLOSURE rather than directory creation.

The ledger recorded that percent-encoded, mixed-separator and absolute-path
variants were **not** tried during the original finding, and that Starlette
"normalizes some traversal in the URL path, so it is likely weaker — but
untested." This suite is what makes that tested. Several payloads below are
expected to be defeated by Starlette's own normalisation before they ever reach
the handler; they are kept precisely so that a future routing change cannot
quietly remove that protection without a test noticing.

C35 [E]: `WATCHED_AOIS` reaches `run_pipeline` without crossing the API
boundary. All three configured labels pass the whitelist, so there was no
current exposure — but nothing enforced it. Item 47 requires the check to hold
everywhere `run_pipeline` or path construction from a label can be reached, not
only at the two originally-known sinks. See the C35 section at the end.

The property under test is REJECTION, not sanitisation: a fix that stripped the
offending characters and continued would return a run the caller never asked
for. Every assertion checks for a non-200 refusal and that no file outside the
data root is ever read.

Run from the repo root:  pytest tests/test_api_run_id_validation.py
"""

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def api_module():
    import api
    return api


@pytest.fixture
def client(api_module):
    """Authenticated (C40/item 70), so requests reach run_id validation."""
    return TestClient(
        api_module.app,
        headers={api_module.API_KEY_HEADER_NAME: api_module.API_KEY},
    )


# ── Payloads ──
#
# Named so a failure report says which class of attack got through. The three
# classes the ledger flagged as untried are called out by id.
TRAVERSAL_PAYLOADS = [
    pytest.param("../", id="relative-parent"),
    pytest.param("..", id="double-dot-bare"),
    pytest.param("../../../../tmp/pwn", id="c16-exact-payload"),
    pytest.param("../../../etc/passwd", id="traversal-to-etc-passwd"),
    # — untried variant 1: percent-encoded —
    pytest.param("%2e%2e%2f", id="url-encoded-traversal"),
    pytest.param("%2e%2e%2f%2e%2e%2fetc%2fpasswd", id="url-encoded-deep"),
    pytest.param("%252e%252e%252f", id="double-url-encoded"),
    pytest.param("..%2f..%2fetc%2fpasswd", id="mixed-encoded-traversal"),
    # — untried variant 2: mixed separators —
    pytest.param("..\\", id="windows-backslash-parent"),
    pytest.param("..\\..\\windows\\system32", id="windows-deep-traversal"),
    pytest.param("../..\\mixed", id="mixed-separator"),
    pytest.param("..%5c..%5cwindows", id="url-encoded-backslash"),
    # — untried variant 3: absolute paths —
    pytest.param("/etc/passwd", id="absolute-posix"),
    pytest.param("/tmp/pwn", id="absolute-posix-tmp"),
    pytest.param("C:\\Windows\\Temp", id="absolute-windows-drive"),
    pytest.param("\\\\server\\share", id="unc-path"),
    # — other rejects —
    pytest.param("a" * 129, id="over-length-129"),
    pytest.param("a" * 4096, id="over-length-4096"),
    pytest.param("run id", id="space"),
    pytest.param("RUN", id="uppercase"),
    pytest.param("café", id="non-ascii"),
    pytest.param("run;rm -rf /", id="shell-metacharacters"),
]


@pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
def test_traversal_payload_never_returns_200(client, payload):
    """
    No payload yields a successful read.

    Deliberately asserts `!= 200` rather than `== 400`. Some of these never
    reach the handler at all: Starlette normalises certain traversal sequences
    in the URL path and answers 404 from the router, which is a *different*
    mechanism refusing the request. Both outcomes are acceptable refusals; what
    is unacceptable is 200. Pinning 400 here would make the test assert which
    layer refused rather than that the request was refused, and would break on a
    routing change that is not a security regression.
    """
    resp = client.get(f"/api/runs/{payload}")
    assert resp.status_code != 200, (
        f"payload {payload!r} returned 200 — a traversal read succeeded"
    )


# Payloads that cannot be expressed in an HTTP request at all: httpx refuses to
# build the URL. They are covered at the unit level in DIRECT_REJECTS instead —
# asserting them here would fail inside the client and prove nothing about the
# server.
CLIENT_UNSENDABLE = [
    pytest.param("run\x00.json", id="null-byte-embedded"),
    pytest.param("run\n", id="trailing-newline"),
]


@pytest.mark.parametrize("payload", CLIENT_UNSENDABLE)
def test_unsendable_payloads_are_rejected_by_the_client(client, payload):
    """
    Documents WHY these are not in the HTTP suite: the transport refuses them
    before a server is involved — a non-printable character cannot go in a URL,
    and the over-length case trips the client's own URL limit. Pinned so that if
    a future client stops refusing, the HTTP-level gap is noticed rather than
    silently uncovered. The server-side rule for all three is asserted at the
    unit level in DIRECT_REJECTS.
    """
    import httpx
    with pytest.raises(httpx.InvalidURL):
        client.get(f"/api/runs/{payload}")


@pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
def test_traversal_payload_never_reaches_path_construction(client, payload):
    """
    The handler must never see a hostile value.

    Discriminates by response body, because the two 404s mean opposite things:
    Starlette's router answers `{"detail":"Not Found"}` (refused before the
    handler), while the handler's own miss answers `Run <id> not found.`. If the
    latter appears, path construction ran on the payload — which is the bug.

    This is the assertion that actually demonstrates the fix. See the module
    docstring: most POSIX traversal never reached the handler even unpatched, so
    a status-code-only test would have passed before the fix for several
    payloads.
    """
    resp = client.get(f"/api/runs/{payload}")
    assert "not found." not in resp.text.lower() or "invalid run_id" in resp.text.lower(), (
        f"payload {payload!r} reached the handler: {resp.text[:120]!r}"
    )


@pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
def test_traversal_payload_never_leaks_file_contents(client, payload):
    """
    Stronger than the status code: prove nothing outside the data root came
    back. A 500 that still rendered /etc/passwd into the body would satisfy the
    test above and be a total failure.
    """
    resp = client.get(f"/api/runs/{payload}")
    body = resp.text.lower()
    for marker in ("root:x:", "/bin/bash", "/bin/sh", "[boot loader]"):
        assert marker not in body, (
            f"payload {payload!r} leaked file contents (matched {marker!r})"
        )


# ── The unit-level check, independent of routing ──
#
# These call validate_run_id directly, so they test the control itself rather
# than whatever the router happened to do first. This is the half that cannot be
# masked by Starlette's normalisation.
DIRECT_REJECTS = [
    "../", "..", "../../../../tmp/pwn", "/etc/passwd", "C:\\Windows",
    "%2e%2e%2f", "..\\", "run id", "RUN", "café", "run\n", "run\x00",
    "", ".", "a" * 129, "run/../x", "run;rm -rf /",
]


@pytest.mark.parametrize("bad", DIRECT_REJECTS, ids=lambda v: repr(v)[:40])
def test_validate_run_id_rejects(api_module, bad):
    with pytest.raises(HTTPException) as exc:
        api_module.validate_run_id(bad)
    assert exc.value.status_code == 400


VALID_RUN_IDS = [
    "dharavi_20260629_122047",
    "phase1_multitile_20260820_130117",
    "aoi_20260715_014524",
    "ward-01",
    "a",
    "0",
    "a" * 128,
]


@pytest.mark.parametrize("good", VALID_RUN_IDS)
def test_validate_run_id_accepts_real_ids(api_module, good):
    """
    The positive control. Without it, `return False` for everything would pass
    every rejection test while breaking the endpoint entirely. These are real
    run-id shapes taken from data/pipeline_runs/.
    """
    assert api_module.validate_run_id(good) == good


def test_rejected_run_id_is_not_echoed(client):
    """
    The 400 body must not reflect an attacker-controlled value: the response is
    rendered by a browser client. Same reasoning already applied to
    validate_aoi_label's 400.
    """
    marker = "aaa<script>alert(1)</script>"
    resp = client.get(f"/api/runs/{marker}")
    assert resp.status_code != 200
    assert "<script>" not in resp.text


def test_valid_but_absent_run_id_is_404_not_400(client):
    """
    A well-formed id that simply does not exist must read as 404. Otherwise the
    whitelist would be indistinguishable from "everything is invalid", and the
    rejection tests above would pass vacuously.
    """
    resp = client.get("/api/runs/definitely_not_a_real_run_20990101_000000")
    assert resp.status_code == 404


# ── Path containment, the defence-in-depth backstop ──

def test_resolve_within_data_root_accepts_a_child(api_module):
    p = api_module.resolve_within_data_root("some_run", "result.json")
    assert api_module.DATA_ROOT in p.parents


@pytest.mark.parametrize(
    "parts",
    [
        pytest.param(("..",), id="parent"),
        pytest.param(("..", "..", "etc", "passwd"), id="deep-traversal"),
        pytest.param(("/etc/passwd",), id="absolute"),
        pytest.param(("run", "..", "..", "..", "tmp"), id="traversal-mid-path"),
    ],
)
def test_resolve_within_data_root_rejects_escapes(api_module, parts):
    """
    The backstop refuses independently of the whitelist. This is what protects a
    FUTURE sink whose author forgets to call validate_run_id — which is exactly
    how C34 came to exist after C16 was fixed.
    """
    with pytest.raises(HTTPException) as exc:
        api_module.resolve_within_data_root(*parts)
    assert exc.value.status_code == 400


# ── C35 — the boundary must hold where the API is not involved ──

def test_watched_aois_all_pass_the_whitelist(api_module):
    """The configured labels are valid — the state C35 observed but nothing enforced."""
    for aoi in api_module.WATCHED_AOIS:
        assert api_module._matches_label_whitelist(aoi["label"]), aoi["label"]


def test_watched_aoi_validation_raises_on_a_bad_label(api_module, monkeypatch):
    """
    A bad label in WATCHED_AOIS stops the service at import.

    This is the actual C35 fix: not "the current three labels are fine", but
    "a future edit cannot introduce a bad one silently". Startup failure rather
    than a warning, because a mistyped watched label should not quietly drop one
    city's refresh and leave a five-day gap nobody notices.
    """
    monkeypatch.setattr(
        api_module, "WATCHED_AOIS",
        [{"label": "../../../tmp/pwn", "west": 0, "south": 0, "east": 1, "north": 1}],
    )
    with pytest.raises(RuntimeError, match="WATCHED_AOIS"):
        api_module._validate_watched_aois()


@pytest.mark.parametrize(
    "bad_label",
    [
        pytest.param("../../../tmp/pwn", id="traversal"),
        pytest.param("/etc/passwd", id="absolute"),
        pytest.param("Dharavi", id="uppercase"),
        pytest.param("dharavi ward", id="space"),
        pytest.param("", id="empty"),
        pytest.param(None, id="none"),
    ],
)
def test_watched_aoi_validation_rejects_each_bad_shape(api_module, monkeypatch, bad_label):
    monkeypatch.setattr(
        api_module, "WATCHED_AOIS",
        [{"label": bad_label, "west": 0, "south": 0, "east": 1, "north": 1}],
    )
    with pytest.raises(RuntimeError):
        api_module._validate_watched_aois()


def test_scheduler_skips_an_invalid_label_instead_of_running_it(api_module, monkeypatch):
    """
    The runtime half of the C35 fix. WATCHED_AOIS is a mutable module-level
    list, so the import-time assertion proves the CONFIGURED value was good, not
    that the value in use right now is. The loop re-checks, and must skip the
    bad entry without invoking run_pipeline on it.
    """
    import sys
    import types

    invoked = []
    stub = types.ModuleType("pipeline")
    stub.run_pipeline = lambda *a, **k: invoked.append(k.get("aoi_label"))
    monkeypatch.setitem(sys.modules, "pipeline", stub)
    monkeypatch.setattr(
        api_module, "WATCHED_AOIS",
        [
            {"label": "../../../tmp/pwn", "west": 0, "south": 0, "east": 1, "north": 1},
            {"label": "dharavi", "west": 72.836, "south": 19.037, "east": 72.862, "north": 19.060},
        ],
    )
    api_module.refresh_all_watched_aois()
    assert "../../../tmp/pwn" not in invoked, (
        "the scheduler invoked run_pipeline with a label that fails the whitelist"
    )
    assert "dharavi" in invoked, "a valid AOI was skipped alongside the bad one"


def test_get_latest_run_rejects_a_bad_label(api_module):
    """
    get_latest_run filters directory names with startswith() rather than
    building a path, so traversal is not reachable through today's
    implementation. It is checked anyway: "not reachable through the current
    code" is precisely the reasoning that left C35 open.
    """
    with pytest.raises(HTTPException) as exc:
        api_module.get_latest_run("../../../etc")
    assert exc.value.status_code == 400


def test_one_predicate_governs_both_boundaries(api_module):
    """
    The HTTP boundary and the startup check must agree on what a valid label is,
    by construction. If someone reimplements one of them, this catches the
    drift — the divergence C35 warned about.
    """
    for label in ["dharavi", "ward-01", "a_b", "../x", "UPPER", "", "sp ace"]:
        predicate_ok = api_module._matches_label_whitelist(label)
        try:
            api_module.validate_aoi_label(label)
            boundary_ok = True
        except HTTPException:
            boundary_ok = False
        assert predicate_ok == boundary_ok, f"disagreement on {label!r}"


# ── What the unpatched endpoint actually did ──
#
# The ledger left this open: "Starlette normalizes some traversal in the URL
# path, so it is likely weaker — but untested." Measured against the unpatched
# endpoint, recording the exact string the handler passed to Path():
#
#   POSIX traversal — '../', '../../../etc/passwd', '%2e%2e%2f', double-encoded,
#   '/etc/passwd'
#       -> the handler NEVER RAN. Starlette normalised or rejected the URL path
#          before routing. The ledger's hypothesis was RIGHT for this class, and
#          C34 was not exploitable through it on this stack.
#
#   Backslash variants — '..\', '..\..\windows\system32', 'C:\Windows\Temp'
#       -> REACHED THE HANDLER with the hostile string intact, e.g.
#          Path('data/pipeline_runs/..\..\windows\system32/result.json').
#          Inert on POSIX, where a backslash is an ordinary filename character.
#          Real traversal on Windows. Nothing in the code was platform-guarded,
#          so the protection was a property of the host OS, not of the code.
#
#   'x/../<real_run_id>' returned 200, but NOT because traversal succeeded: the
#       URL was normalised to '/api/runs/<real_run_id>' before routing and the
#       handler received the clean id. An ordinary request, not an escape.
#
# Net: C34's practical severity on POSIX was lower than the ledger feared, and
# the mitigation was incidental — the router plus the host OS, neither of which
# is a control this codebase owns. The whitelist makes the refusal explicit,
# platform-independent, and testable, which is why the fix is the whitelist
# rather than a documented reliance on normalisation.

HANDLER_REACHING_PAYLOADS = [
    pytest.param("..\\", id="backslash-parent"),
    pytest.param("..\\..\\windows\\system32", id="backslash-deep"),
    pytest.param("..%5c..%5cwindows", id="encoded-backslash"),
    pytest.param("C:\\Windows\\Temp", id="windows-drive"),
    pytest.param("run id", id="space-in-id"),
]


@pytest.mark.parametrize("payload", HANDLER_REACHING_PAYLOADS)
def test_payloads_that_used_to_reach_the_handler_are_now_rejected(client, payload):
    """
    These are the payloads MEASURED to reach the unpatched handler with the
    hostile string intact. They are the ones that actually demonstrate the fix;
    the POSIX traversal cases were already refused by the router and so could
    never have demonstrated anything.

    Must now be 400 from validate_run_id — refused before any path is built, on
    every platform rather than only on the ones where a backslash happens to be
    harmless.
    """
    resp = client.get(f"/api/runs/{payload}")
    assert resp.status_code == 400, (
        f"{payload!r} returned {resp.status_code}; expected 400 from "
        f"validate_run_id before any path was built"
    )
    assert "invalid run_id" in resp.text.lower()
