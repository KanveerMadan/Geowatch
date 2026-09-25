r"""
C40 regression tests — the API had no authentication of any kind.

04_FINDINGS_LEDGER.md C40 (Critical, [S], SURVIVES), build item 70: `api.py`
exposed 8 endpoints plus a StaticFiles mount with zero auth primitives — no
Depends, no HTTPBearer, no APIKeyHeader, nothing. Anyone who could reach the
port had full access. The only control present was CORS, which is
browser-enforced and therefore no obstacle to curl or any script.

The property under test is REFUSAL AT THE PERIMETER: an unauthenticated request
must be rejected with 401 before it reaches any handler, any mount, or any
pipeline call. Two things follow from "at the perimeter" that these tests pin
down explicitly, because both are how this class of fix usually leaks:

  1. COVERAGE IS ENUMERATED FROM THE LIVE ROUTE TABLE, not from a hand-written
     list of endpoints. A hand-written list cannot fail when someone adds an
     endpoint and forgets to protect it — which is precisely the failure mode
     C35 documented, where the scheduler reached run_pipeline without crossing
     the boundary believed to protect it. See test_every_route_requires_auth.

  2. MOUNTS ARE COVERED TOO. An app-level `Depends` does NOT protect
     `app.mount(...)`: a Mount is a separate ASGI app the dependency system
     never enters. Measured during implementation — a route returned 401 while
     a mounted StaticFiles path returned 200 and served the file. `/runs` serves
     everything under data/pipeline_runs/, the same data C34 would disclose, so
     a dependency-only fix would have left it open. See test_static_mount_*.

Run from the repo root:  pytest tests/test_api_authentication.py
"""

import sys
import types

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Mount


VALID_BBOX = {"west": 72.836, "south": 19.037, "east": 72.862, "north": 19.060}

INUNDATION_DATES = {
    "pre_event_start": "2025-05-01", "pre_event_end": "2025-05-31",
    "event_start": "2025-07-01", "event_end": "2025-07-31",
}


class _PipelineInvoked(AssertionError):
    """Raised if an unauthenticated request reaches the pipeline."""


@pytest.fixture(autouse=True)
def stub_pipeline(monkeypatch):
    """
    Replace `pipeline` with a stub that explodes if called.

    Same reasoning as the C16 suite: it makes "the request never reached the
    pipeline" an assertable fact rather than an inference, and keeps GEE auth
    and torch out of a unit test. Both endpoints import pipeline lazily inside
    the handler, so injecting into sys.modules is enough.
    """
    def _boom(*args, **kwargs):
        raise _PipelineInvoked(
            "pipeline was invoked by an unauthenticated request — the "
            "perimeter check did not reject it"
        )

    stub = types.ModuleType("pipeline")
    stub.run_pipeline = _boom
    stub.run_inundation_analysis = _boom
    monkeypatch.setitem(sys.modules, "pipeline", stub)
    return stub


@pytest.fixture
def api_module():
    import api
    return api


@pytest.fixture
def anon(api_module):
    """A client presenting NO credentials."""
    return TestClient(api_module.app)


@pytest.fixture
def authed(api_module):
    """A client presenting the correct key."""
    return TestClient(
        api_module.app,
        headers={api_module.API_KEY_HEADER_NAME: api_module.API_KEY},
    )


# ── Sample requests per route, so POST bodies are valid enough that a 401
#    cannot be mistaken for a 422 validation error. ──
def _request_for(api_module, method: str, path: str):
    bodies = {
        "/api/analyze": {"aoi_label": "dharavi", **VALID_BBOX},
        "/api/analyze_inundation": {
            "aoi_label": "dharavi", **VALID_BBOX, **INUNDATION_DATES
        },
    }
    concrete = path.replace("{run_id}", "dharavi_20260629_122047")
    return method, concrete, bodies.get(path)


def _live_routes(api_module):
    """
    Every (method, path) pair actually registered on the app, read from the
    live route table. Adding an endpoint automatically adds a test case; that
    is the point.
    """
    out = []
    for route in api_module.app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        for method in sorted(methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            out.append(pytest.param(method, path, id=f"{method}-{path}"))
    return out


def _route_params():
    import api
    return _live_routes(api)


# ── The core property ──

@pytest.mark.parametrize("method,path", _route_params())
def test_every_route_requires_auth(anon, api_module, method, path):
    """
    NO route answers an unauthenticated caller.

    Enumerated from app.routes, not hand-listed, so a future endpoint cannot
    silently escape the check — it shows up here as a failing case the moment
    it is registered.
    """
    verb, concrete, body = _request_for(api_module, method, path)
    resp = anon.request(verb, concrete, json=body)
    assert resp.status_code == 401, (
        f"{verb} {concrete} answered {resp.status_code} without credentials; "
        f"expected 401"
    )


@pytest.mark.parametrize("method,path", _route_params())
def test_every_route_accepts_the_valid_key(authed, api_module, method, path):
    """
    The positive control. Without this, a fix that 401s unconditionally — or a
    broken key comparison — would pass every test above while making the API
    entirely unusable. Any status EXCEPT 401 proves the key was accepted; the
    handler's own outcome (200, 404, 500 from a stubbed pipeline) is not this
    test's business.
    """
    verb, concrete, body = _request_for(api_module, method, path)
    resp = authed.request(verb, concrete, json=body)
    assert resp.status_code != 401, (
        f"{verb} {concrete} rejected a VALID key — auth is broken closed"
    )


# ── The mount, which a Depends-based fix would have missed ──

def test_app_actually_has_a_mount(api_module):
    """
    Guards the test below. If /runs stops being a Mount, the mount test could
    start passing vacuously, so assert the precondition it depends on.
    """
    mounts = [r for r in api_module.app.routes if isinstance(r, Mount)]
    assert mounts, "expected at least one Mount (/runs) on the app"
    assert any(m.path == "/runs" for m in mounts), (
        f"expected a /runs mount, found {[m.path for m in mounts]}"
    )


def test_static_mount_requires_auth(anon):
    """
    /runs serves data/pipeline_runs/ — landcover rasters, confidence maps, run
    artifacts: the same data C34 would disclose. An app-level Depends does not
    cover a Mount, so this is the case that distinguishes a real perimeter from
    a decorated router.

    404 would be a FAILING outcome here, not a passing one: it would mean the
    request reached StaticFiles and was answered on the merits.
    """
    resp = anon.get("/runs/anything.png")
    assert resp.status_code == 401, (
        f"the /runs mount answered {resp.status_code} without credentials; "
        f"expected 401. An unauthenticated caller must not reach StaticFiles."
    )


def test_static_mount_traversal_attempt_also_requires_auth(anon):
    """A traversal attempt at the mount is refused for lack of auth, first."""
    resp = anon.get("/runs/../../../../etc/passwd")
    assert resp.status_code == 401


# ── Credential handling ──

@pytest.mark.parametrize(
    "bad_key",
    [
        pytest.param("", id="empty-string"),
        pytest.param("wrong", id="plain-wrong"),
        pytest.param("test-key-not-a-real-secre", id="correct-prefix-truncated"),
        pytest.param("test-key-not-a-real-secret ", id="trailing-space"),
        pytest.param(" test-key-not-a-real-secret", id="leading-space"),
        pytest.param("TEST-KEY-NOT-A-REAL-SECRET", id="case-flipped"),
    ],
)
def test_wrong_key_rejected(api_module, bad_key):
    """
    A near-miss key is rejected as firmly as a missing one. The truncated-prefix
    case matters specifically: it is the shape a timing oracle would leak, and
    the reason the implementation uses secrets.compare_digest rather than ==.
    """
    client = TestClient(api_module.app, headers={api_module.API_KEY_HEADER_NAME: bad_key})
    assert client.get("/api/runs").status_code == 401


def test_error_body_does_not_echo_the_presented_key(api_module):
    """
    The rejected value is attacker-controlled and the response is rendered by a
    browser client, so it must not come back in the body. Same reasoning already
    applied to validate_aoi_label's 400.
    """
    marker = "cnary-<script>alert(1)</script>"
    client = TestClient(api_module.app, headers={api_module.API_KEY_HEADER_NAME: marker})
    resp = client.get("/api/runs")
    assert resp.status_code == 401
    assert marker not in resp.text


def test_error_body_does_not_reveal_the_real_key(api_module):
    """The 401 body must not leak the expected secret."""
    resp = TestClient(api_module.app).get("/api/runs")
    assert resp.status_code == 401
    assert api_module.API_KEY not in resp.text


def test_missing_and_wrong_are_indistinguishable(api_module):
    """
    Both produce the same status and body, so a prober cannot learn whether a
    particular key exists from the difference.
    """
    missing = TestClient(api_module.app).get("/api/runs")
    wrong = TestClient(
        api_module.app, headers={api_module.API_KEY_HEADER_NAME: "nope"}
    ).get("/api/runs")
    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == wrong.json()


# ── The amplification path, called out by name in build item 70 ──

def test_scheduler_trigger_requires_auth(anon):
    """
    POST /api/scheduler/trigger was docstringed "(admin use)" and wide open.
    "(admin use)" is a docstring, not a control.

    This is the amplification path and the reason C40 is rated Critical: one
    unauthenticated request fires run_pipeline across every entry in
    WATCHED_AOIS — three GEE-backed runs on metered quota, from one HTTP call.
    """
    assert anon.post("/api/scheduler/trigger").status_code == 401


def test_scheduler_trigger_does_not_reschedule_when_unauthenticated(anon, api_module):
    """
    Stronger than the status code: prove the side effect cannot happen. A 401
    that still moved the job would be a fix in name only.

    Since 2026-09-25 (C46) there is no auto-refresh job at all, so the side
    effect is impossible by construction: the check is that the endpoint
    still refuses an anonymous caller and that no scheduler exists to move.
    """
    assert anon.post("/api/scheduler/trigger").status_code == 401
    assert not hasattr(api_module, "scheduler"), (
        "a scheduler object exists again -- the 5-day auto-refresh was removed (C46)"
    )


def test_scheduler_status_requires_auth(anon):
    """It leaks the watched-AOI list and scheduler state."""
    assert anon.get("/api/scheduler/status").status_code == 401


def test_root_requires_auth(anon):
    """`/` reports scheduler state and next refresh time. Not public."""
    assert anon.get("/").status_code == 401


# ── CORS must not be mistaken for access control ──

def test_cors_allowed_origin_does_not_bypass_auth(api_module):
    """
    A request from an ALLOWED CORS origin still needs the key. CORS decides
    which browser origins may read a response; it never decides who may send a
    request. If this ever returns 200, someone has confused the two.
    """
    client = TestClient(api_module.app)
    resp = client.get("/api/runs", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 401


def test_cors_preflight_is_exempt(api_module):
    """
    OPTIONS preflight must NOT be 401. Browsers send preflight without
    credentials by design, so rejecting it would break the frontend while
    protecting nothing — the preflight response carries only the CORS policy,
    which is already public in the source.
    """
    client = TestClient(api_module.app)
    resp = client.options(
        "/api/analyze",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code != 401, "CORS preflight must not require credentials"


def test_preflight_exemption_does_not_leak_data(api_module):
    """
    The preflight exemption is method-scoped, not a hole: OPTIONS returns CORS
    headers, never run data. Guards against someone widening the exemption.
    """
    client = TestClient(api_module.app)
    resp = client.options(
        "/api/runs",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "dharavi" not in resp.text.lower()


# ── Startup discipline ──

def test_missing_env_var_refuses_to_start(api_module, monkeypatch):
    """
    No silent development default. A missing-secret fallback is how an
    "authenticated" service ships unauthenticated, so _load_api_key must raise.
    """
    monkeypatch.delenv(api_module.API_KEY_ENV_VAR, raising=False)
    with pytest.raises(RuntimeError, match=api_module.API_KEY_ENV_VAR):
        api_module._load_api_key()


@pytest.mark.parametrize(
    "blank", [pytest.param("", id="empty"), pytest.param("   ", id="whitespace-only")]
)
def test_blank_env_var_refuses_to_start(api_module, monkeypatch, blank):
    """An empty or whitespace-only key is treated as unset, not as a valid key."""
    monkeypatch.setenv(api_module.API_KEY_ENV_VAR, blank)
    with pytest.raises(RuntimeError):
        api_module._load_api_key()
