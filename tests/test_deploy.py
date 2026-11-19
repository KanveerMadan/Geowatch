"""
Phase 5 deployment config: the gateway in front of api.py (deploy/asgi.py),
process setup (deploy/runtime.py), the long-job worker stub
(deploy/worker.py) and the deploy files themselves.

Run from the repo root:  pytest tests/test_deploy.py
"""
import asyncio
import importlib
import json
import logging
import os
import re
import types
from pathlib import Path

import pytest

os.environ.setdefault("GEOWATCH_DEPLOY_NO_AUTOBUILD", "1")
from deploy import asgi as A          # noqa: E402
from deploy import runtime as R       # noqa: E402
from deploy import worker as W        # noqa: E402

KEY = "server-key-for-tests"
RID = "r" + "a" * 24


# ── a fake inner app and an ASGI driver ──

class Inner:
    def __init__(self, status=200, headers=()):
        self.calls, self.status, self.headers = [], status, list(headers)

    async def __call__(self, scope, receive, send):
        self.calls.append(scope)
        await send({"type": "http.response.start", "status": self.status,
                    "headers": [(b"content-type", b"application/json"), *self.headers]})
        await send({"type": "http.response.body", "body": b"{}"})


def call(app, method, path, headers=None, client=("10.0.0.1", 1234)):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    scope = {"type": "http", "method": method, "path": path, "client": client,
             "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]}
    asyncio.run(app(scope, receive, send))
    start = next(m for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    hdrs = {k.decode().lower(): v.decode() for k, v in start["headers"]}
    return start["status"], hdrs, body


def gateway(inner=None, limits=None, **kw):
    lim = A.limits_from_env()
    lim.update(limits or {})
    return A.GeoWatchGateway(inner or Inner(), api_key=KEY,
                             cors_origins=kw.pop("cors", ["https://geowatch.example"]),
                             limiter=A.RateLimiter(lim), **kw)


def sent_key(inner):
    return dict(inner.calls[-1]["headers"]).get(b"x-api-key")


# ── health ──

def test_health_is_public_and_never_reaches_the_api():
    inner = Inner()
    st, _, body = call(gateway(inner), "GET", "/health")
    assert st == 200 and json.loads(body)["status"] == "ok"
    assert inner.calls == []


def test_health_reports_degraded_when_the_store_is_not_writable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)                      # no data/results here
    code, body = A.health_check({"code_commit": "abc"})()
    assert code == 503 and body["checks"]["results_store_writable"] is False


# ── partner-only units ──

@pytest.mark.parametrize("path", [f"/api/results/{RID}/wards/footprint",
                                  f"/api/results/{RID}/features/path",
                                  f"/api/results/{RID}/wards/footprint/17"])
def test_building_level_units_need_the_key(path):
    inner = Inner()
    st, _, _ = call(gateway(inner), "GET", path)
    assert st == 403 and inner.calls == []
    st, _, _ = call(gateway(inner), "GET", path, {"X-API-Key": KEY})
    assert st == 200 and len(inner.calls) == 1


def test_wards_and_grid_stay_public_without_a_key():
    inner = Inner()
    for p in (f"/api/results/{RID}/wards/grid", f"/api/results/{RID}/features/ward:mumbai",
              f"/api/results/{RID}"):
        assert call(gateway(inner), "GET", p)[0] == 200
    assert all(b"x-api-key" not in dict(c["headers"]) for c in inner.calls)


# ── the public explorer's protected routes ──

@pytest.mark.parametrize("method,path", [("GET", "/"), ("GET", "/api/boundaries"),
                                         ("GET", "/api/jobs/j" + "0" * 24), ("POST", "/api/jobs"),
                                         ("GET", f"/api/imagery/{RID}"),
                                         ("GET", f"/api/imagery/{RID}/2024")])
def test_explorer_routes_get_the_server_key_added(method, path):
    inner = Inner()
    call(gateway(inner), method, path, {"X-API-Key": "a-wrong-key"})
    assert sent_key(inner) == KEY.encode()


@pytest.mark.parametrize("method,path", [("POST", "/api/analyze"), ("GET", "/api/runs"),
                                         ("POST", "/api/legacy/analyze"),
                                         ("POST", "/api/scheduler/trigger"), ("GET", "/runs/x/y.png"),
                                         ("GET", "/api/vector/coverage")])
def test_everything_else_still_needs_a_real_key(method, path):
    inner = Inner()
    call(gateway(inner), method, path)
    assert sent_key(inner) is None                   # api.py's own gate decides


def test_public_analysis_can_be_switched_off():
    inner = Inner()
    call(gateway(inner, public_jobs=False), "POST", "/api/jobs")
    assert sent_key(inner) is None


# ── rate limits ──

def test_analysis_is_limited_per_client_with_retry_after():
    g = gateway(limits={"analysis": (2, 3600)})
    assert [call(g, "POST", "/api/jobs")[0] for _ in range(2)] == [200, 200]
    st, h, _ = call(g, "POST", "/api/jobs")
    assert st == 429 and int(h["retry-after"]) > 0
    assert call(g, "POST", "/api/jobs", client=("10.0.0.2", 1))[0] == 200   # another client


def test_the_daily_analysis_cap_is_global():
    g = gateway(limits={"analysis_global_day": (2, 86400)})
    codes = [call(g, "POST", "/api/jobs", client=(f"10.0.1.{i}", 1))[0] for i in range(3)]
    assert codes == [200, 200, 429]


def test_forwarded_for_is_used_only_when_the_proxy_is_trusted():
    g = gateway(limits={"read": (1, 60)}, trust_proxy=True)
    assert call(g, "GET", f"/api/results/{RID}", {"X-Forwarded-For": "1.1.1.1, 9.9.9.9"})[0] == 200
    assert call(g, "GET", f"/api/results/{RID}", {"X-Forwarded-For": "2.2.2.2"})[0] == 200
    assert call(g, "GET", f"/api/results/{RID}", {"X-Forwarded-For": "1.1.1.1"})[0] == 429
    g2 = gateway(limits={"read": (1, 60)})            # untrusted: the header is ignored
    call(g2, "GET", f"/api/results/{RID}", {"X-Forwarded-For": "1.1.1.1"})
    assert call(g2, "GET", f"/api/results/{RID}", {"X-Forwarded-For": "2.2.2.2"})[0] == 429


def test_rate_limiter_window_slides():
    t = [0.0]
    lim = A.RateLimiter({"b": (1, 10)}, clock=lambda: t[0])
    assert lim.hit("b", "c") == 0 and lim.hit("b", "c") > 0
    t[0] = 10.5
    assert lim.hit("b", "c") == 0


# ── CORS ──

def test_cors_allows_only_configured_origins():
    inner = Inner(headers=[(b"access-control-allow-origin", b"http://localhost:5173")])
    g = gateway(inner)
    st, h, _ = call(g, "OPTIONS", "/api/jobs", {"Origin": "https://geowatch.example"})
    assert st == 204 and h["access-control-allow-origin"] == "https://geowatch.example"
    assert "x-api-key" in h["access-control-allow-headers"]
    assert call(g, "OPTIONS", "/api/jobs", {"Origin": "https://evil.example"})[0] == 403
    _, h, _ = call(g, "GET", f"/api/results/{RID}", {"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in h       # the inner localhost header is dropped
    _, h, _ = call(g, "GET", f"/api/results/{RID}", {"Origin": "https://geowatch.example"})
    assert h["access-control-allow-origin"] == "https://geowatch.example"


# ── logging ──

def test_access_log_never_contains_the_client_ip(caplog):
    with caplog.at_level(logging.INFO, logger="geowatch.access"):
        call(gateway(), "GET", f"/api/results/{RID}", client=("203.0.113.77", 1))
    rec = [r for r in caplog.records if r.name == "geowatch.access"][-1]
    assert rec.fields["status"] == 200 and rec.fields["path"] == f"/api/results/{RID}"
    assert "203.0.113.77" not in json.dumps(rec.fields)
    assert "203.0.113.77" not in R.JsonFormatter().format(rec)


# ── the real api.py behind the gateway ──

def test_gateway_around_the_real_api(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    monkeypatch.setenv("GEOWATCH_API_KEY", KEY)
    import api
    monkeypatch.setattr(api, "API_KEY", KEY)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "results").mkdir(parents=True)
    g = A.GeoWatchGateway(api.app, api_key=KEY, cors_origins=[], limiter=A.RateLimiter(A.limits_from_env()),
                          health=A.health_check({"code_commit": "abc"}))
    c = TestClient(g)
    assert c.get("/health").status_code == 200
    assert c.get("/").status_code == 200                       # key added by the gateway
    assert c.post("/api/analyze", json={}).status_code == 401  # still key-only
    assert c.get(f"/api/results/{RID}/wards/footprint").status_code == 403
    assert c.get(f"/api/results/{RID}").status_code == 404     # public read, not stored


# ── runtime ──

def test_production_refuses_an_unknown_code_commit(monkeypatch):
    monkeypatch.setenv("GEOWATCH_ENV", "production")
    monkeypatch.delenv("GEOWATCH_CODE_COMMIT", raising=False)
    monkeypatch.delenv("RENDER_GIT_COMMIT", raising=False)
    with pytest.raises(R.DeployConfigError):
        R.ensure_code_commit()
    monkeypatch.setenv("RENDER_GIT_COMMIT", "abc123")
    assert R.ensure_code_commit() == "abc123" and os.environ["GEOWATCH_CODE_COMMIT"] == "abc123"


def test_service_account_wraps_every_initialize(monkeypatch, tmp_path):
    key = tmp_path / "k.json"
    key.write_text(json.dumps({"client_email": "svc@proj.iam.gserviceaccount.com"}))
    calls = []
    fake = types.SimpleNamespace(
        ServiceAccountCredentials=lambda email, key_file: ("CREDS", email, key_file),
        Initialize=lambda credentials="persistent", *a, **k: calls.append((credentials, k)))
    monkeypatch.setenv("GEE_SERVICE_ACCOUNT_KEY_FILE", str(key))
    monkeypatch.setenv("GEE_PROJECT_ID", "proj")
    assert R.install_ee_service_account(fake) == "service_account"
    fake.Initialize(project="proj")                   # what ingestion/gee_client.py does
    fake.Initialize()
    assert calls[0] == (("CREDS", "svc@proj.iam.gserviceaccount.com", str(key)), {"project": "proj"})
    assert calls[1][0][0] == "CREDS" and calls[1][1]["project"] == "proj"
    assert R.install_ee_service_account(fake) == "service_account"   # idempotent


def test_production_needs_a_service_account(monkeypatch):
    monkeypatch.setenv("GEOWATCH_ENV", "production")
    monkeypatch.delenv("GEE_SERVICE_ACCOUNT_KEY_FILE", raising=False)
    with pytest.raises(R.DeployConfigError):
        R.install_ee_service_account(types.SimpleNamespace())
    monkeypatch.setenv("GEE_SERVICE_ACCOUNT_KEY_FILE", "/nonexistent/key.json")
    with pytest.raises(R.DeployConfigError):
        R.install_ee_service_account(types.SimpleNamespace())


def test_geemap_stub_satisfies_gee_client(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "geemap", None)  # behaves as not installed
    assert R.install_geemap_stub() is True
    gc = importlib.reload(importlib.import_module("ingestion.gee_client"))
    with pytest.raises(RuntimeError):
        gc.get_map(0, 0)
    monkeypatch.delitem(sys.modules, "ingestion.gee_client")


# ── worker ──

def test_worker_queue_claims_once_and_records_failures(tmp_path):
    root = str(tmp_path / "q")
    a = W.enqueue("sfincs", {"case": "valencia"}, root)
    b = W.enqueue("ok", {"x": 1}, root)
    W.enqueue("mystery", {}, root)
    handlers = {**W.HANDLERS, "ok": lambda p: {"echo": p["x"]}}
    states = [W.run_one(root, handlers) for _ in range(4)]
    assert states[:3].count("failed") == 2 and states[:3].count("done") == 1 and states[3] is None
    failed = json.loads((Path(root) / "failed" / f"{a}.json").read_text())
    assert "not wired" in failed["error"]
    assert json.loads((Path(root) / "done" / f"{b}.json").read_text())["result"] == {"echo": 1}
    assert not os.listdir(Path(root) / "running")


def test_a_claimed_job_cannot_be_claimed_again(tmp_path):
    root = str(tmp_path / "q")
    W.enqueue("ok", {}, root)
    assert W.claim(root) is not None and W.claim(root) is None


# ── deploy files ──

ROOT = Path(__file__).resolve().parent.parent


def test_api_image_is_slim_non_root_single_process_and_healthchecked():
    d = (ROOT / "deploy" / "Dockerfile.api").read_text()
    assert "FROM python:3.12-slim" in d
    assert re.search(r"^USER geowatch$", d, re.M)
    assert "HEALTHCHECK" in d and "/health" in d
    assert "--workers 1" in d and "deploy.asgi:app" in d
    assert "GEOWATCH_CODE_COMMIT" in d


def test_dockerignore_keeps_secrets_and_data_out():
    ig = (ROOT / ".dockerignore").read_text().split()
    for p in (".env", "data/", ".git", "*service-account*.json", "*.pem", "credentials.json"):
        assert p in ig, p


def test_requirements_are_pinned_and_exclude_the_retired_stack():
    req = [l for l in (ROOT / "deploy" / "requirements-api.txt").read_text().splitlines()
           if l.strip() and not l.startswith("#")]
    assert req and all("==" in l for l in req)
    names = {l.split("==")[0].lower() for l in req}
    assert not names & {"torch", "torchgeo", "segment-anything", "geemap"}


def test_every_env_var_the_code_reads_is_in_env_example():
    example = (ROOT / ".env.example").read_text()
    code = ""
    for d in ("analysis", "vector", "susceptibility", "ingestion", "configs", "deploy"):
        code += "".join(p.read_text() for p in (ROOT / d).rglob("*.py"))
    code += (ROOT / "api.py").read_text()
    names = set(re.findall(r"(?:getenv|environ\.get|_int)\(\s*[\"']([A-Z][A-Z0-9_]+)[\"']", code))
    names |= {"GEOWATCH_API_KEY"}                    # read through API_KEY_ENV_VAR
    web = "".join(p.read_text() for p in (ROOT / "web" / "src").rglob("*.js*"))
    names |= set(re.findall(r"import\.meta\.env\.(VITE_[A-Z_]+)", web))
    missing = [n for n in sorted(names) if n not in example]
    assert not missing, missing


def test_env_example_holds_no_values_for_secrets():
    for line in (ROOT / ".env.example").read_text().splitlines():
        if line.startswith(("GEOWATCH_API_KEY=", "GEE_PROJECT_ID=", "VITE_GEOWATCH_API_KEY=",
                            "GEE_SERVICE_ACCOUNT_KEY_FILE=", "GEE_KEY_FILE_HOST=")):
            assert line.endswith("="), line


def test_render_blueprint_keeps_one_api_instance_and_no_inline_secrets():
    y = (ROOT / "render.yaml").read_text()
    assert "numInstances: 1" in y and "healthCheckPath: /health" in y
    assert "generateValue: true" in y                 # the API key is generated, never written
    assert "/etc/secrets/ee-key.json" in y
    assert "source: /*" in y and "destination: /index.html" in y   # SPA routes
