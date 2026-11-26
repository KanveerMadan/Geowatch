"""
The deployed API: api.py's app, wrapped. Serve with exactly ONE process
(job state and rate limits live in memory):

    uvicorn deploy.asgi:app --host 0.0.0.0 --port $PORT --workers 1 --proxy-headers

api.py is not edited. Everything a public deployment needs that a local
tool did not sits in this one wrapper, in front of api.py's own key gate:

  /health            liveness + readiness, public, no key, no Earth Engine call.
  CORS               origins from GEOWATCH_CORS_ORIGINS (comma-separated);
                     api.py's own list is localhost only.
  Public explorer    the browser holds no key. The few routes the explorer
                     needs that api.py protects (GET /, /api/boundaries,
                     /api/jobs, /api/imagery) are forwarded with the server's
                     key added, behind per-client rate limits and a global
                     daily cap on new analyses (GEOWATCH_PUBLIC_JOBS=0 turns
                     public analysis off). Everything else keeps needing a
                     real key: legacy runs, sync /api/analyze, the scheduler.
  Rate limits        per client per window, in memory (one instance).
  Access log         one JSON line per request; the client is a salted hash,
                     never the IP.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
from collections import deque

from deploy import runtime

log = logging.getLogger("geowatch.access")

RESULT_ID = r"r[0-9a-f]{24}"
# (method, path regex) -> (rate bucket, add the server key?)
PUBLIC_WITH_KEY = [
    ("GET", re.compile(r"/"), "read"),
    ("GET", re.compile(r"/api/boundaries"), "read"),
    ("GET", re.compile(r"/api/jobs/j[0-9a-f]{24}"), "poll"),
    ("POST", re.compile(r"/api/jobs"), "analysis"),
    ("GET", re.compile(rf"/api/imagery/{RESULT_ID}(/\d{{4}})?"), "imagery"),
]
PUBLIC_READ = re.compile(r"/api/results(/[A-Za-z0-9_:-]+)*")   # api.py's own exemption


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


def limits_from_env() -> dict:
    """{bucket: (max requests, window seconds)} per client, plus the global
    daily cap on public analyses."""
    return {
        "read": (_int("GEOWATCH_RATE_READ_PER_MIN", 240), 60),
        "poll": (_int("GEOWATCH_RATE_POLL_PER_MIN", 120), 60),
        "imagery": (_int("GEOWATCH_RATE_IMAGERY_PER_HOUR", 60), 3600),
        "analysis": (_int("GEOWATCH_RATE_ANALYSIS_PER_HOUR", 4), 3600),
        # 2026-11-26 (fix/deploy-urgent): 100 -> 20 public analyses a day in total, to bound
        # Earth Engine use on the project while access is keyless.
        "analysis_global_day": (_int("GEOWATCH_ANALYSIS_PER_DAY", 20), 86400),
        "keyed": (_int("GEOWATCH_RATE_KEYED_PER_MIN", 600), 60),
    }


class RateLimiter:
    """Sliding-window counters. `hit` returns 0 when allowed, else the
    seconds until the oldest hit leaves the window."""

    def __init__(self, limits: dict, clock=time.monotonic):
        self.limits, self.clock = limits, clock
        self._hits: dict = {}
        self._lock = threading.Lock()

    def hit(self, bucket: str, key: str) -> int:
        cap, window = self.limits[bucket]
        if cap <= 0:
            return window
        now = self.clock()
        with self._lock:
            q = self._hits.setdefault((bucket, key), deque())
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= cap:
                return max(1, int(q[0] + window - now) + 1)
            q.append(now)
            if len(self._hits) > 50_000:                       # bound memory
                for k in [k for k, v in self._hits.items() if not v][:10_000]:
                    del self._hits[k]
            return 0


def _headers(scope) -> dict:
    return {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}


class GeoWatchGateway:
    def __init__(self, inner, *, api_key: str, cors_origins, limiter: RateLimiter,
                 public_jobs: bool = True, trust_proxy: bool = False, salt: str | None = None,
                 health=None):
        self.inner, self.api_key, self.limiter = inner, api_key, limiter
        self.cors = {o.strip().rstrip("/") for o in cors_origins if o.strip()}
        self.public_jobs, self.trust_proxy = public_jobs, trust_proxy
        self.salt = salt or secrets.token_hex(16)
        self.health = health or (lambda: (200, {"status": "ok"}))

    # ── helpers ──
    def _client(self, scope, h) -> str:
        ip = None
        if self.trust_proxy and h.get("x-forwarded-for"):
            ip = h["x-forwarded-for"].split(",")[0].strip()
        if not ip:
            ip = (scope.get("client") or ("unknown",))[0]
        return hashlib.sha256((self.salt + ip).encode()).hexdigest()[:16]

    def _keyed(self, h) -> bool:
        k = h.get("x-api-key")
        return bool(k) and secrets.compare_digest(k, self.api_key)

    def _cors_headers(self, origin):
        if origin and origin.rstrip("/") in self.cors:
            return [(b"access-control-allow-origin", origin.encode()), (b"vary", b"Origin")]
        return []

    async def _json(self, send, status, body, extra=()):
        data = json.dumps(body).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(data)).encode()), *extra]})
        await send({"type": "http.response.body", "body": data})

    def classify(self, method: str, path: str, keyed: bool):
        """(kind, bucket): kind is health | preflight | public_key |
        public | passthrough."""
        if path == "/health" and method in ("GET", "HEAD"):
            return "health", None
        if method == "OPTIONS":
            return "preflight", None
        if keyed:
            return "passthrough", "keyed"
        for m, rx, bucket in PUBLIC_WITH_KEY:
            if m == method and rx.fullmatch(path):
                if bucket == "analysis" and not self.public_jobs:
                    return "passthrough", "read"
                return "public_key", bucket
        if method == "GET" and PUBLIC_READ.fullmatch(path):
            return "public", "read"
        return "passthrough", "read"

    # ── ASGI ──
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.inner(scope, receive, send)
        t0 = time.monotonic()
        h = _headers(scope)
        method, path = scope["method"], scope["path"]
        keyed = self._keyed(h)
        kind, bucket = self.classify(method, path, keyed)
        client = self._client(scope, h)
        cors = self._cors_headers(h.get("origin"))
        status = {"code": None}

        def done(code):
            log.info("request", extra={"fields": {
                "method": method, "path": path, "status": code, "kind": kind,
                "ms": round((time.monotonic() - t0) * 1000, 1), "client": client}})

        if kind == "health":
            code, body = self.health()
            await self._json(send, code, body, cors)
            return done(code)
        if kind == "preflight":
            if not cors:
                await self._json(send, 403, {"detail": "Origin not allowed."})
                return done(403)
            await send({"type": "http.response.start", "status": 204, "headers": [
                *cors, (b"access-control-allow-methods", b"GET, POST, OPTIONS"),
                (b"access-control-allow-headers", b"content-type, x-api-key"),
                (b"access-control-max-age", b"600")]})
            await send({"type": "http.response.body", "body": b""})
            return done(204)
        retry = self.limiter.hit(bucket, client) if bucket else 0
        if not retry and bucket == "analysis":
            retry = self.limiter.hit("analysis_global_day", "all")
        if retry:
            await self._json(send, 429, {"detail": "Too many requests. Try again later."},
                             [*cors, (b"retry-after", str(retry).encode())])
            return done(429)

        if kind == "public_key":
            scope = dict(scope)
            scope["headers"] = [(k, v) for k, v in scope["headers"] if k.lower() != b"x-api-key"] \
                + [(b"x-api-key", self.api_key.encode())]

        async def send_wrapped(msg):
            if msg["type"] == "http.response.start":
                status["code"] = msg["status"]
                hdrs = [(k, v) for k, v in msg.get("headers", [])
                        if k.lower() not in (b"access-control-allow-origin", b"vary")] + cors
                msg = {**msg, "headers": hdrs}
            await send(msg)

        try:
            await self.inner(scope, receive, send_wrapped)
        finally:
            done(status["code"])


def health_check(info: dict):
    def check():
        results = os.path.join("data", "results")
        ok_results = os.path.isdir(results) and os.access(results, os.R_OK | os.W_OK)
        ee_mode = runtime.ee_credentials_mode()
        ok = ok_results and ee_mode != "service_account_missing"
        return (200 if ok else 503), {
            "status": "ok" if ok else "degraded",
            "code_commit": info.get("code_commit", "unknown")[:12],
            "checks": {"results_store_writable": ok_results, "earth_engine_credentials": ee_mode},
        }
    return check


def build_app():
    info = runtime.setup()
    os.makedirs(os.path.join("data", "results"), exist_ok=True)
    import api                                   # after runtime.setup(): EE + geemap are ready
    origins = os.getenv("GEOWATCH_CORS_ORIGINS", "").split(",")
    return GeoWatchGateway(
        api.app, api_key=api.API_KEY, cors_origins=origins,
        limiter=RateLimiter(limits_from_env()),
        public_jobs=os.getenv("GEOWATCH_PUBLIC_JOBS", "1") == "1",
        trust_proxy=os.getenv("GEOWATCH_TRUST_PROXY", "0") == "1",
        health=health_check(info))


app = build_app() if os.getenv("GEOWATCH_DEPLOY_NO_AUTOBUILD") != "1" else None
