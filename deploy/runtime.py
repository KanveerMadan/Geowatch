"""
Process setup for the hosted GeoWatch API. Runs BEFORE api.py (or
any pipeline module) is imported, so nothing in the pipeline has to know it
is deployed:

  * code_commit   in a container there is no git, so analysis/contract.py
                  reads GEOWATCH_CODE_COMMIT. Left unset it would be
                  "unknown" for every build, and results computed by
                  different code would share a version_id and a cache key.
                  Production refuses to start without it.
  * Earth Engine  a service-account key file (GEE_SERVICE_ACCOUNT_KEY_FILE,
                  mounted as a secret file, never in the image or the repo).
                  ee.Initialize() is wrapped so the pipeline's existing
                  `ee.Initialize(project=...)` calls use it.
  * geemap        imported by ingestion/gee_client.py for a development map
                  helper only; it drags in the Jupyter stack. Replaced by a
                  stub when not installed.
  * logging       one JSON line per record on stdout, level from
                  GEOWATCH_LOG_LEVEL.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import types

log = logging.getLogger("geowatch.deploy")


class DeployConfigError(RuntimeError):
    pass


def production() -> bool:
    return os.getenv("GEOWATCH_ENV", "development").lower() == "production"


# ── logging ─────────────────────────────────────────────────────────────

class JsonFormatter(logging.Formatter):
    def format(self, record):
        out = {"t": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname,
               "logger": record.name, "msg": record.getMessage()}
        for k, v in getattr(record, "fields", {}).items():
            out[k] = v
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def configure_logging() -> None:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [h]
    root.setLevel(os.getenv("GEOWATCH_LOG_LEVEL", "INFO").upper())


# ── code commit ─────────────────────────────────────────────────────────

def ensure_code_commit() -> str:
    """GEOWATCH_CODE_COMMIT, else the platform's commit (Render's
    RENDER_GIT_COMMIT: HEAD, so any commit changes version_id -- more cache
    misses, never a stale hit). Production refuses "unknown"."""
    c = os.getenv("GEOWATCH_CODE_COMMIT", "").strip()
    if not c:
        c = os.getenv("RENDER_GIT_COMMIT", "").strip()
        if c:
            os.environ["GEOWATCH_CODE_COMMIT"] = c
            log.warning("GEOWATCH_CODE_COMMIT unset; using RENDER_GIT_COMMIT (HEAD)")
    if not c and production():
        raise DeployConfigError(
            "GEOWATCH_CODE_COMMIT is not set. Without it every build has version 'unknown' and "
            "results from different code would share a cache key. Set GEOWATCH_CODE_COMMIT "
            "or use the platform-provided RENDER_GIT_COMMIT.")
    return c or "unknown"


# ── geemap ──────────────────────────────────────────────────────────────

def install_geemap_stub() -> bool:
    """True when the stub was installed (geemap missing)."""
    try:
        import geemap  # noqa: F401
        return False
    except ImportError:
        pass
    stub = types.ModuleType("geemap")

    class Map:  # noqa: D401 -- the annotation target in gee_client.get_map
        def __init__(self, *a, **k):
            raise RuntimeError("geemap is not installed on the server (development map helper only)")

    stub.Map = Map
    stub.__geowatch_stub__ = True
    sys.modules["geemap"] = stub
    return True


# ── Earth Engine ────────────────────────────────────────────────────────

def ee_credentials_mode() -> str:
    path = os.getenv("GEE_SERVICE_ACCOUNT_KEY_FILE", "").strip()
    if path:
        return "service_account" if os.path.isfile(path) else "service_account_missing"
    return "default"


def install_ee_service_account(ee_module=None) -> str:
    """Make every ee.Initialize() call use the service account named by
    GEE_SERVICE_ACCOUNT_KEY_FILE. Returns the mode. Unset -> "default"
    (the developer's own `earthengine authenticate` credentials)."""
    path = os.getenv("GEE_SERVICE_ACCOUNT_KEY_FILE", "").strip()
    if not path:
        if production():
            raise DeployConfigError("GEE_SERVICE_ACCOUNT_KEY_FILE is not set (production needs a "
                                    "service account; see DEPLOY.md)")
        return "default"
    if not os.path.isfile(path):
        raise DeployConfigError(f"GEE_SERVICE_ACCOUNT_KEY_FILE points to a missing file")
    with open(path) as fh:
        email = json.load(fh).get("client_email")
    if not email:
        raise DeployConfigError("the service-account key file has no client_email")
    ee = ee_module
    if ee is None:
        import ee
    if getattr(ee.Initialize, "__geowatch_wrapped__", False):
        return "service_account"
    creds = ee.ServiceAccountCredentials(email, key_file=path)
    real = ee.Initialize
    project = os.getenv("GEE_PROJECT_ID") or None

    def initialize(credentials="persistent", *a, **k):
        if credentials in (None, "persistent"):
            credentials = creds
        if not k.get("project") and not (a and a[0]):
            k["project"] = project
        return real(credentials, *a, **k)

    initialize.__geowatch_wrapped__ = True
    ee.Initialize = initialize
    log.info("earth engine: service account", extra={"fields": {"account_domain": email.split("@")[-1]}})
    return "service_account"


def setup() -> dict:
    """Everything above, in order. Returns what was configured (for /health)."""
    configure_logging()
    info = {"code_commit": ensure_code_commit(), "geemap_stub": install_geemap_stub(),
            "ee": install_ee_service_account()}
    log.info("runtime ready", extra={"fields": {k: v for k, v in info.items()}})
    return info
