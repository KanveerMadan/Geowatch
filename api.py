"""
GeoWatch Copilot — FastAPI Backend
====================================
Run: GEOWATCH_API_KEY=<secret> uvicorn api:app --reload --port 8000

Every endpoint requires the `X-API-Key` header (C40, build item 70). The
service refuses to start if GEOWATCH_API_KEY is unset — see _load_api_key().
Generate one with:  python -c "import secrets; print(secrets.token_urlsafe(32))"
"""

import json
import os
import re
import secrets
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv

from configs.legacy_pipeline import RETIRED, legacy_pipeline_marker, mark_retired

# Load .env BEFORE _load_api_key() runs at import, below. Without this the
# module-level API_KEY read happens against the raw process environment and a
# key sitting in .env is invisible — the service would refuse to start while
# the secret was, from the operator's point of view, plainly set.
#
# ingestion/gee_client.py already calls load_dotenv() for GEE_PROJECT_ID, but
# api.py imports pipeline lazily inside handlers, so that call happens long
# after this module's import-time checks. The two entry points each need their
# own load; dotenv is idempotent, so calling it twice is harmless.
load_dotenv()

app = FastAPI(title="GeoWatch Copilot API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API authentication — 04_FINDINGS_LEDGER.md C40 (build item 70) ──
#
# Before this, every endpoint was reachable by anyone who could reach the port.
# CORS above is NOT an access control: it is enforced by browsers, so it is no
# obstacle whatsoever to curl, a script, or any non-browser client. It restricts
# which web origins may *read* a response in a browser; it does not restrict who
# may *send* a request. Do not count it as authentication.
#
# WHY MIDDLEWARE AND NOT `Depends` AT THE ROUTER.
# Build item 70 originally specified a router-level dependency
# (`FastAPI(dependencies=[Depends(...)])`). That was verified insufficient
# during implementation and the item has been amended. An app-level dependency
# covers routes on the app router but does NOT cover `app.mount(...)`, because a
# Mount is a separate ASGI application that FastAPI's dependency system never
# enters. Measured directly: with `FastAPI(dependencies=[Depends(gate)])`, a
# route returned 401 while a mounted StaticFiles path returned 200 and served
# the file. The `/runs` mount below serves everything under
# `data/pipeline_runs/` — landcover rasters, confidence maps, result artifacts —
# which is the same data C34 would disclose. A dependency-only fix would have
# closed the front door and left that one open.
#
# Middleware is therefore the enforcement point: it is the only mechanism that
# sits in front of routes AND mounts, so coverage is a property of the
# perimeter, not of remembering to decorate each new endpoint. That is the
# structural lesson of C35 — the scheduler reached run_pipeline without crossing
# the boundary believed to protect it, because protection lived at call sites
# rather than at the perimeter. One gate, ahead of everything.
#
# Fail loudly at import if the secret is unset, rather than defaulting to a
# development key or disabling auth. A missing-secret default is how an
# "authenticated" service ships unauthenticated. This mirrors gee_client.py's
# loud-failure discipline, and closes the gap archive/AUDIT_FINDINGS.md records
# against it: check that the variable is actually set, do not pass None through.
API_KEY_ENV_VAR = "GEOWATCH_API_KEY"
API_KEY_HEADER_NAME = "X-API-Key"


def _load_api_key() -> str:
    """Read the API secret at import time, or refuse to start."""
    key = os.getenv(API_KEY_ENV_VAR)
    if key is None or not key.strip():
        raise RuntimeError(
            f"{API_KEY_ENV_VAR} is not set. The GeoWatch API refuses to start "
            f"without it: every endpoint runs GEE-backed pipeline work or "
            f"returns run data. Set "
            f"{API_KEY_ENV_VAR} to a high-entropy secret "
            f"(python -c 'import secrets; print(secrets.token_urlsafe(32))') "
            f"and restart."
        )
    return key


API_KEY = _load_api_key()

# Declared so the scheme appears in the OpenAPI document. Enforcement is the
# middleware below, not this object — it is documentation, not a control.
api_key_scheme = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """
    Reject any request without a valid API key, before it reaches a route or a
    mount.

    Registered AFTER CORSMiddleware, which makes it the OUTERMOST layer:
    Starlette builds the stack so the last-added middleware runs first, so an
    unauthenticated request is refused before any other handler sees it.

    CORS preflight is exempt. A browser sends `OPTIONS` without credentials by
    design, so rejecting preflight would break the frontend while protecting
    nothing — the preflight response carries no run data, only the CORS policy
    that is already public in the source. Every non-OPTIONS method is checked.

    `secrets.compare_digest` rather than `==`: constant-time comparison, so the
    duration of a failed request does not leak how much of the key was correct.
    """
    if request.method == "OPTIONS":
        return await call_next(request)
    if is_public_read(request.method, request.url.path):
        return await call_next(request)

    presented = request.headers.get(API_KEY_HEADER_NAME)
    if presented is None or not secrets.compare_digest(presented, API_KEY):
        # The presented value is deliberately not echoed back: it is
        # attacker-controlled and the response is rendered by a browser client.
        # One message for both "missing" and "wrong", so the response does not
        # confirm that a particular key exists.
        return JSONResponse(
            status_code=401,
            content={
                "detail": (
                    f"Missing or invalid API key. Send it in the "
                    f"{API_KEY_HEADER_NAME} header."
                )
            },
        )
    return await call_next(request)

# ── Public read-only results (Phase 2, 2026-10-28) ──
#
# Stored analysis results are public to READ: GET only, and only under
# /api/results. Everything that triggers computation (POST /api/analyze,
# /api/legacy/analyze, /api/analyze_inundation) and everything that serves
# legacy run data (/api/runs, the /runs mount) still needs the key.
# The exemption is a fullmatch on the path, so /api/resultsX or a mount
# cannot ride on it, and it sits in the same middleware as the key check, so
# coverage stays a property of the perimeter (C35).
PUBLIC_READ_METHODS = frozenset({"GET"})
PUBLIC_READ_PATH = re.compile(r"/api/results(/[A-Za-z0-9_:-]+)*")


def is_public_read(method: str, path: str) -> bool:
    return method in PUBLIC_READ_METHODS and PUBLIC_READ_PATH.fullmatch(path) is not None


# ── Static file mount ──
# Serves pipeline run outputs (landcover.png, landcover_confidence.png, etc.)
# so the frontend can load them directly via <ImageOverlay>.
# App.jsx's landcoverImageUrl() assumes exactly this convention:
#   {API}/runs/<run_id>/<filename>
os.makedirs("data/pipeline_runs", exist_ok=True)
app.mount("/runs", StaticFiles(directory="data/pipeline_runs"), name="runs")

# ── AOI area limit — geodesic, in real km², not square-degrees ──
# PREVIOUS BUG: bbox_area = (east-west)*(north-south) is square-degrees,
# not km². Its physical meaning changes with latitude -- one degree of
# longitude shrinks toward the poles, so the same threshold (0.01) let
# through wildly different real-world areas depending on where on Earth
# the AOI sat. Fixed via pyproj.Geod's geodesic polygon area, which is
# latitude-correct everywhere.
MAX_AOI_AREA_KM2 = 100.0  # roughly ~10km x 10km, matches the original intent
# C2 / item 52: this cap is the ONE AOI size limit. tiler.py used to document
# "< 5 sq km", 20x below it. Measured live, the tiler exports and validates at
# least ingestion.tiler.MEASURED_MAX_EXPORT_AREA_KM2 (895 km²), so the
# tiler's docstring was the wrong side and it was corrected. The cap stays at
# 100 because the downstream pipeline above that size was not measured.

# ── AOI label validation — AUDIT_FINDINGS_V2 C16 (path traversal) ──
# `aoi_label` flows from the request body into run_pipeline() /
# run_inundation_analysis(), where it becomes a filesystem path component
# (run_dir = <output_dir>/<aoi_label>_<timestamp>). Unvalidated,
# '../../../../tmp/pwn' normalises to a path outside the data root.
#
# This is the API boundary, so the check belongs here — before any path is
# constructed, and without touching pipeline.py.
#
# Whitelist, not blacklist: enumerating bad sequences ('..', '/', '\\',
# '\x00', unicode separators, encoded variants) is open-ended and has been
# bypassed in every codebase that has tried it. Enumerating the GOOD
# characters is closed by construction.
#
# REJECT, never sanitize-and-continue: a silently rewritten label would hand
# the caller back a run_id they did not ask for, and would quietly collide
# distinct AOIs into one directory (e.g. '../a' and 'a' both becoming 'a').
AOI_LABEL_MAX_LENGTH = 64
AOI_LABEL_PATTERN = re.compile(r"[a-z0-9_-]{1,%d}" % AOI_LABEL_MAX_LENGTH)


def _matches_label_whitelist(label: str) -> bool:
    """
    The whitelist predicate itself, with no opinion about how to complain.

    Split out for C35 (build item 47), so every caller (AOI labels, boundary
    layer ids, get_latest_run) applies one rule and none can drift
    into disagreeing about what a valid label is, which is the failure mode
    that let C35 exist.
    """
    return isinstance(label, str) and AOI_LABEL_PATTERN.fullmatch(label) is not None


def validate_aoi_label(label: str) -> str:
    r"""
    Whitelist-validate an AOI label. Returns it unchanged, or raises
    HTTPException(400).

    Uses re.fullmatch(), NOT re.match() with a trailing '$'. In Python '$'
    also matches immediately before a trailing newline, so
    re.match(r'[a-z0-9_-]+$', 'aoi\n') SUCCEEDS and the newline would
    survive into the path component. fullmatch() requires the entire string
    — trailing newline included — to lie inside the whitelist.

    The rejected value is deliberately not echoed back in `detail`: it is
    attacker-controlled and the response is rendered by a browser client.
    """
    if not _matches_label_whitelist(label):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid aoi_label. Allowed characters: lowercase a-z, "
                "digits 0-9, underscore and hyphen; length 1-"
                f"{AOI_LABEL_MAX_LENGTH}."
            ),
        )
    return label


# ── run_id validation and path containment — C34 (build item 47) ──
#
# `GET /api/runs/{run_id}` built `data/pipeline_runs/{run_id}/result.json`
# straight from an unvalidated path parameter. Same bug class as C16, a READ
# sink rather than a write sink, so the impact shape is disclosure (returning
# file contents) rather than directory creation.
#
# A run_id is `<aoi_label>_<timestamp>`, so the alphabet is the same as
# aoi_label's; only the length budget differs (64-char label + '_' + timestamp).
# Same three placement decisions C16 settled, for the same reasons:
#   - whitelist, not blacklist: enumerating bad sequences is open-ended and has
#     been bypassed in every codebase that tried it;
#   - fullmatch(), not match() with '$', because in Python '$' also matches
#     before a trailing newline;
#   - REJECT, never sanitize-and-continue: a rewritten id would return a run the
#     caller did not ask for.
RUN_ID_MAX_LENGTH = 128
RUN_ID_PATTERN = re.compile(r"[a-z0-9_-]{1,%d}" % RUN_ID_MAX_LENGTH)

# The one directory any run artifact may live under. Resolved once at import so
# the containment check below compares two absolute, symlink-free paths.
DATA_ROOT = Path("data/pipeline_runs").resolve()


def validate_run_id(run_id: str) -> str:
    """Whitelist-validate a run id. Returns it unchanged, or raises 400."""
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid run_id. Allowed characters: lowercase a-z, digits 0-9, "
                f"underscore and hyphen; length 1-{RUN_ID_MAX_LENGTH}."
            ),
        )
    return run_id


def resolve_within_data_root(*parts: str) -> Path:
    """
    Build a path under DATA_ROOT and prove it stayed there.

    Defence in depth, deliberately kept even though the whitelist above already
    makes traversal unreachable at this sink. The whitelist is the control; this
    is the backstop that does not depend on every future caller remembering to
    apply it. C35 is the argument for having it: a boundary enforced only where
    someone remembered to enforce it is not a boundary.

    Uses Path.resolve() on the FULL candidate path, then re-checks containment,
    so '..' segments, absolute components and symlinks are all normalised away
    before the comparison rather than pattern-matched beforehand.
    """
    candidate = DATA_ROOT.joinpath(*parts).resolve()
    if candidate != DATA_ROOT and DATA_ROOT not in candidate.parents:
        # Deliberately generic: the caller learns nothing about the filesystem.
        raise HTTPException(status_code=400, detail="Invalid path.")
    return candidate


def compute_aoi_geodesics(west: float, south: float, east: float, north: float) -> dict:
    """
    Compute real geodesic area/width/height for a lon/lat bounding box,
    correct at any latitude (unlike raw degree-based area).
    """
    from pyproj import Geod

    geod = Geod(ellps="WGS84")

    # Geodesic area of the rectangle (order matters for the sign, but
    # geometry_area_perimeter/polygon_area_perimeter returns abs() safe
    # via fabs below regardless of winding direction).
    lons = [west, east, east, west]
    lats = [south, south, north, north]
    area_m2, _ = geod.polygon_area_perimeter(lons, lats)
    area_km2 = abs(area_m2) / 1_000_000.0

    # Width/height as geodesic distances along the AOI's edges, evaluated
    # at the AOI's mid-latitude/mid-longitude for a representative value.
    mid_lat = (south + north) / 2.0
    mid_lon = (west + east) / 2.0
    _, _, width_m = geod.inv(west, mid_lat, east, mid_lat)
    _, _, height_m = geod.inv(mid_lon, south, mid_lon, north)

    return {
        "area_km2": round(area_km2, 4),
        "width_km": round(width_m / 1000.0, 4),
        "height_km": round(height_m / 1000.0, 4),
    }

# C17 / item 56: run directories are named `<label>_%Y%m%d_%H%M%S` by
# pipeline.py, and labels may themselves contain underscores, so the timestamp
# is the trailing pair and nothing else.
_RUN_DIR_TIMESTAMP = re.compile(r"_(\d{8}_\d{6})$")

# `*_test_*` runs are excluded from "latest" selection outright. C17 was a test
# artifact served as the demo; out-ranking it by time is not enough, because a
# test run made later would be served again.
_TEST_RUN_MARKER = "_test_"

# Item 56, finished: `startswith(label)` also matches the inundation and
# event-hazard runs pipeline.py writes as `<label>_inundation_<ts>` and
# `<label>_eventhazard_<ts>`. Their result shape is not the land-cover
# result the demo renders, so they are never "latest" candidates either.
_EXCLUDED_FROM_LATEST = (_TEST_RUN_MARKER, "_inundation_", "_eventhazard_")


def run_dir_timestamp(name: str) -> datetime | None:
    """Parse the trailing timestamp of a run directory name, or None.

    None means the directory has no position in chronological order. It is
    never guessed into one -- under string order an undated name like
    `dharavi_zzz` would have sorted above every real run.
    """
    m = _RUN_DIR_TIMESTAMP.search(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def get_latest_run(aoi_label: str) -> dict | None:
    """Return the most recent result.json for a given AOI label, or None.

    "Most recent" is by the parsed run timestamp (C17), never by string order,
    and `*_test_*`, `*_inundation_*` and `*_eventhazard_*` runs are never
    candidates.
    """
    # C35 sweep (build item 47): a label reaching a filesystem operation, so it
    # is checked here too. Traversal is not reachable through this particular
    # function -- it filters directory names with startswith() rather than
    # building a path from the label -- but "not reachable through today's
    # implementation" is exactly the reasoning that left C35 open. The check is
    # on the label's validity, not on the current shape of the code below it.
    if not _matches_label_whitelist(aoi_label):
        raise HTTPException(
            status_code=400,
            detail="Invalid aoi_label.",
        )
    runs_dir = Path("data/pipeline_runs")
    dated = []
    for d in runs_dir.iterdir():
        if not (d.is_dir() and d.name.startswith(aoi_label)):
            continue
        if any(marker in d.name for marker in _EXCLUDED_FROM_LATEST):
            continue
        ts = run_dir_timestamp(d.name)
        if ts is None:
            continue
        dated.append((ts, d))
    if not dated:
        return None
    result_path = max(dated)[1] / "result.json"
    if not result_path.exists():
        return None
    with open(result_path) as f:
        return json.load(f)


# The 5-day auto-refresh scheduler was REMOVED 2026-09-25 (C46): it ran the
# retired 7-class pipeline unattended over a fixed list of three cities. The
# list and its refresh loop were removed 2026-10-29: GeoWatch serves any AOI.
SCHEDULER_DISABLED_REASON = (
    "Auto-refresh disabled 2026-09-25 (C46): it ran the retired, unvalidated "
    "7-class pipeline. Stored results are served as they are."
)


class AnalyzeRequest(BaseModel):
    west: float
    south: float
    east: float
    north: float
    start_date: str = None
    end_date: str = None
    aoi_label: str = "aoi"
    demo: bool = False


class AnalysisRequest(BaseModel):
    west: float
    south: float
    east: float
    north: float
    start_date: str | None = None
    end_date: str | None = None
    aoi_label: str = "aoi"
    # An ingested boundary layer (data/boundaries/<id>) whose wards become an
    # extra aggregation unit type. Whitelisted like aoi_label: it is a path
    # component.
    boundary_layer_id: str | None = None
    demo: bool = False


def validate_boundary_layer_id(bid: str) -> str:
    if not _matches_label_whitelist(bid):
        raise HTTPException(status_code=400, detail="Invalid boundary_layer_id.")
    if not (Path("data/boundaries") / bid / "manifest.json").exists():
        raise HTTPException(status_code=400, detail="Unknown boundary_layer_id.")
    return bid


class InundationRequest(BaseModel):
    """Phase 8: separate request shape, deliberately NOT reusing
    AnalyzeRequest's single start_date/end_date pair, per the master
    spec's rule against overloading one date range with multiple
    meanings."""
    west: float
    south: float
    east: float
    north: float
    pre_event_start: str
    pre_event_end: str
    event_start: str
    event_end: str
    aoi_label: str = "aoi"
    # Optional: standing_water % from an existing run_pipeline() run over
    # (ideally) the same event window, for cross-check display only.
    optical_standing_water_pct: float = None

@app.get("/")
def root():
    return {
        "status": "GeoWatch Copilot API running",
        "version": "1.0",
        "scheduler": "disabled",
        "next_auto_refresh": None,
        "scheduler_note": SCHEDULER_DISABLED_REASON,
        "max_aoi_area_km2": MAX_AOI_AREA_KM2,
    }


# Demo mode served one fixed city's stored run. Removed 2026-10-29: there is
# no default AOI. Refused, not ignored, so `demo: true` cannot silently run.
DEMO_REMOVED_DETAIL = "demo mode is removed: there is no default AOI. Send a bounding box."


def validate_analysis_request(req: AnalysisRequest) -> None:
    """Shared by /api/analyze and /api/jobs: everything is refused here, before
    any run starts."""
    validate_aoi_label(req.aoi_label)
    if req.boundary_layer_id is not None:
        validate_boundary_layer_id(req.boundary_layer_id)
    if req.demo:
        raise HTTPException(status_code=400, detail=DEMO_REMOVED_DETAIL)
    if req.west >= req.east or req.south >= req.north:
        raise HTTPException(status_code=400, detail="Invalid bounding box.")
    aoi_geo = compute_aoi_geodesics(req.west, req.south, req.east, req.north)
    if aoi_geo["area_km2"] > MAX_AOI_AREA_KM2:
        raise HTTPException(status_code=400, detail=(
            f"AOI too large: {aoi_geo['area_km2']:.2f} km². Keep under {MAX_AOI_AREA_KM2} km²."))
    from analysis.run import resolve_window
    try:
        resolve_window(req.start_date, req.end_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid dates: {e}")


@app.post("/api/analyze")
def analyze(req: AnalysisRequest):
    """The analysis pipeline (analysis/run.py): no 7-class classifier. Serves
    a stored result when the same AOI + dates + version was run before."""
    validate_analysis_request(req)
    from analysis import store
    try:
        out = store.analyze((req.west, req.south, req.east, req.north), req.start_date,
                            req.end_date, name=req.aoi_label, boundary_id=req.boundary_layer_id,
                            root=str(RESULTS_ROOT))
    except Exception as e:
        # Items 54/55: name the class at the HTTP boundary.
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    if out["result_id"]:
        out["url"] = f"/api/results/{out['result_id']}"
    return out


@app.post("/api/jobs", status_code=202)
def start_job(req: AnalysisRequest):
    """The analysis pipeline as a job (analysis/jobs.py): returns at once with
    a job id. A stored area comes back already complete."""
    validate_analysis_request(req)
    from analysis import jobs
    return jobs.submit((req.west, req.south, req.east, req.north), req.start_date, req.end_date,
                       name=req.aoi_label, boundary_id=req.boundary_layer_id,
                       root=str(RESULTS_ROOT))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """Per-stage status and each output group as it is final; the full
    result once complete."""
    from analysis import jobs
    if not jobs.valid_id(job_id):
        raise HTTPException(status_code=400, detail="Invalid job id.")
    j = jobs.get(job_id)
    if j is None:
        raise HTTPException(status_code=404, detail="Unknown job (jobs are kept in memory only).")
    return j


@app.post("/api/legacy/analyze")
def legacy_analyze(req: AnalyzeRequest):
    """LEGACY: the retired 7-class pipeline (08_STATE.md §RETIRED), kept
    reachable only here. Every block of its result is labelled "retired".
    It currently fails at CAAT loading (CaatProvenanceError, C62)."""
    # C16: validate first, unconditionally, and OUTSIDE the try/except below.
    # That block catches bare `Exception`, and HTTPException IS an Exception,
    # so a 400 raised inside it would be swallowed and re-raised as a 500.
    # Unconditional (before the `demo` short-circuit) so there is no request
    # shape that reaches path construction with an unchecked label.
    validate_aoi_label(req.aoi_label)
    if req.demo:
        raise HTTPException(status_code=400, detail=DEMO_REMOVED_DETAIL)
    if req.west >= req.east or req.south >= req.north:
        raise HTTPException(status_code=400, detail="Invalid bounding box.")

    aoi_geo = compute_aoi_geodesics(req.west, req.south, req.east, req.north)
    if aoi_geo["area_km2"] > MAX_AOI_AREA_KM2:
        raise HTTPException(
            status_code=400,
            detail=(
                f"AOI too large: {aoi_geo['area_km2']:.2f} km² "
                f"(width {aoi_geo['width_km']:.2f} km x height {aoi_geo['height_km']:.2f} km). "
                f"Keep under {MAX_AOI_AREA_KM2} km²."
            ),
        )
    try:
        from pipeline import run_pipeline
        result = run_pipeline(
            west=req.west, south=req.south,
            east=req.east, north=req.north,
            start_date=req.start_date,
            end_date=req.end_date,
            aoi_label=req.aoi_label,
        )
        return result
    except Exception as e:
        # Items 54/55: the right broad catch at the HTTP boundary, so it
        # names the class. "EEException: quota" and "KeyError: 'hnd'" are
        # different failures and must not read the same.
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")

@app.post("/api/analyze_inundation")
def analyze_inundation(req: InundationRequest):
    """Phase 8: JRC Global Surface Water baseline + Sentinel-1 SAR
    change detection, kept fully separate from /api/analyze's stable
    land-cover pipeline."""
    # C16: same reasoning as /api/analyze — this endpoint passes aoi_label
    # into run_inundation_analysis(), which builds a run directory from it.
    validate_aoi_label(req.aoi_label)
    if req.west >= req.east or req.south >= req.north:
        raise HTTPException(status_code=400, detail="Invalid bounding box.")

    aoi_geo = compute_aoi_geodesics(req.west, req.south, req.east, req.north)
    if aoi_geo["area_km2"] > MAX_AOI_AREA_KM2:
        raise HTTPException(
            status_code=400,
            detail=(
                f"AOI too large: {aoi_geo['area_km2']:.2f} km². "
                f"Keep under {MAX_AOI_AREA_KM2} km²."
            ),
        )
    try:
        from pipeline import run_inundation_analysis
        result = run_inundation_analysis(
            west=req.west, south=req.south, east=req.east, north=req.north,
            pre_event_start=req.pre_event_start, pre_event_end=req.pre_event_end,
            event_start=req.event_start, event_end=req.event_end,
            aoi_label=req.aoi_label,
            optical_standing_water_pct=req.optical_standing_water_pct,
        )
        return result
    except Exception as e:
        # Items 54/55: the right broad catch at the HTTP boundary, so it
        # names the class. "EEException: quota" and "KeyError: 'hnd'" are
        # different failures and must not read the same.
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")


@app.get("/api/runs")
def list_runs():
    runs_dir = Path("data/pipeline_runs")
    if not runs_dir.exists():
        return {"runs": []}
    runs = []
    # Item 56: newest first by parsed timestamp, not reverse string order
    # (which grouped by label and put `dharavi_t...` above `dharavi_2...`).
    # Undated directories are still listed, after every dated one, in name
    # order, because they have no chronological position to guess.
    def _order(d):
        ts = run_dir_timestamp(d.name)
        return (0, -ts.timestamp(), d.name) if ts else (1, 0, d.name)

    for run_dir in sorted(runs_dir.iterdir(), key=_order):
        result_path = run_dir / "result.json"
        if result_path.exists():
            with open(result_path) as f:
                data = json.load(f)
            runs.append({
                "run_id": data.get("run_id"),
                "aoi": data.get("aoi"),
                "date_range": data.get("date_range"),
                "status": data.get("status"),
                "imagery": data.get("imagery"),
                "observation_quality": data.get("observation_quality"),
                "dominant_category": data.get("summary", {}).get("dominant_category"),
                "total_segments": data.get("summary", {}).get("total_segments"),
                "relative_elevation_proxy_score": data.get("relative_elevation_proxy", {}).get("score"),
                # Every run listed here is a legacy 7-class run (or an
                # inundation run beside them); none is a current result.
                "validation_status": RETIRED if _is_legacy_result(data) else None,
            })
    return {"runs": runs}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    # C34: validate BEFORE any path is constructed, and outside any try/except.
    # Same placement reasoning as C16 — this handler has no try block today, and
    # the check is kept ahead of path construction so adding one later cannot
    # swallow the 400 into a 500.
    validate_run_id(run_id)
    result_path = resolve_within_data_root(run_id, "result.json")
    if not result_path.exists():
        # The run_id is echoed here only because it has already been proved to
        # match the whitelist, so it cannot carry markup or separators.
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    with open(result_path) as f:
        data = json.load(f)
    if _is_legacy_result(data):
        # Stored runs predating the marker and the label get both here; the
        # file on disk is not modified.
        data.setdefault("legacy_pipeline", legacy_pipeline_marker())
        mark_retired(data)
    return data


def _is_legacy_result(data: dict) -> bool:
    """A run_pipeline() result: it carries the marker, or (before the marker
    existed) the 7-class `landcover` block."""
    return isinstance(data, dict) and ("legacy_pipeline" in data or "landcover" in data)


@app.get("/api/vector/coverage")
def vector_coverage():
    """Item 20: the newest stored OSM coverage report, one block per vector
    AOI. Served verbatim: the regime, warning and partial-fetch statuses are
    decided by vector.coverage, and neither this route nor the UI re-derives
    them. Built offline by `python -m vector.coverage_report`."""
    from vector.coverage_report import latest_report
    found = latest_report()
    if found is None:
        raise HTTPException(
            status_code=404,
            detail="No item 20 coverage report stored. Run: python -m vector.coverage_report",
        )
    path, report = found
    return {**report, "source_file": path}


# ── Results: public, read-only (Phase 2) ──

RESULTS_ROOT = Path("data/results")
WARD_PAGE_MAX = 1000


def _load_result(result_id: str) -> dict:
    from analysis import store
    if not store.valid_id(result_id):
        raise HTTPException(status_code=400, detail="Invalid result id.")
    r = store.get(result_id, str(RESULTS_ROOT))
    if r is None:
        raise HTTPException(status_code=404, detail=f"Result {result_id} not found.")
    return r


def _load_unit_type(result_id: str, unit_type: str):
    from analysis import store
    from analysis.wards import ward_context
    r = _load_result(result_id)
    units = store.get_units(result_id, str(RESULTS_ROOT)) or {}
    if unit_type not in units:
        raise HTTPException(status_code=404, detail="Unknown unit type for this result.")
    return r, units[unit_type], ward_context(r)


@app.get("/api/results")
def list_results():
    from analysis import store
    return {"results": store.list_results(str(RESULTS_ROOT))}


@app.get("/api/results/{result_id}")
def get_result(result_id: str):
    return _load_result(result_id)


@app.get("/api/results/{result_id}/maps/{name}")
def get_result_map(result_id: str, name: str):
    """A stored map as RGBA PNG. No-data is alpha 0 (item 37); the legend is
    in the result's `maps` block."""
    from fastapi.responses import Response
    from analysis import store
    _load_result(result_id)
    try:
        png = store.get_map(result_id, name, str(RESULTS_ROOT))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid map name.")
    if png is None:
        raise HTTPException(status_code=404, detail="Unknown map for this result.")
    return Response(content=png, media_type="image/png")


@app.get("/api/results/{result_id}/wards")
def get_result_wards(result_id: str):
    """The unit types of a result: item 22's grid / footprint / path units,
    and ward:<boundary_id> when a boundary layer was given."""
    r = _load_result(result_id)
    return {"result_id": result_id, "unit_types": r["wards"]}


@app.get("/api/results/{result_id}/wards/{unit_type}")
def get_result_ward_page(result_id: str, unit_type: str, offset: int = 0, limit: int = 100):
    from analysis.wards import materialize
    if offset < 0 or not (1 <= limit <= WARD_PAGE_MAX):
        raise HTTPException(status_code=400, detail=f"offset >= 0, 1 <= limit <= {WARD_PAGE_MAX}.")
    r, block, ctx = _load_unit_type(result_id, unit_type)
    page = block["units"][offset:offset + limit]
    return {"result_id": result_id, "unit_type": unit_type, "status": block["status"],
            "n_units": block["n_units"], "offset": offset, "limit": limit,
            "osm_coverage": block.get("osm_coverage"),
            "units": [materialize(u, unit_type, ctx) for u in page]}


@app.get("/api/results/{result_id}/features/{unit_type}")
def get_result_features(result_id: str, unit_type: str):
    """Every unit of one type as a GeoJSON FeatureCollection, for drawing:
    each fraction's value where it was measured and null (with its status)
    where it was not. The full contract per unit stays at .../wards/..."""
    from analysis.wards import feature
    r, block, ctx = _load_unit_type(result_id, unit_type)
    return {"type": "FeatureCollection", "result_id": result_id, "unit_type": unit_type,
            "status": block["status"], "fractions": list(ctx["fractions"]),
            "features": [feature(u, ctx) for u in block["units"]]}


@app.get("/api/results/{result_id}/buildings")
def get_result_buildings(result_id: str):
    """The building outlines the run used (item 19 layer), for drawing, read
    from the vector cache ONLY: a public read never fetches. 404 when this
    server has no cached copy. Item 22's "footprint" units are a Voronoi
    partition of the AOI, not outlines, so they cannot stand in."""
    from fastapi.responses import FileResponse
    from vector.sources import CACHE_DIR, bbox_key
    r = _load_result(result_id)
    key = bbox_key(r["request"]["aoi_label"], r["request"]["bbox"])
    src = r.get("footprint_source")
    if src == "open_buildings_v3":
        path = Path(CACHE_DIR) / "open_buildings" / f"{key}.geojson"
        if path.exists():
            return FileResponse(path, media_type="application/geo+json")
    elif src == "osm_building":
        path = Path(CACHE_DIR) / "osm" / f"{key}__building.json"
        if path.exists():
            with open(path) as fh:
                elements = json.load(fh)
            elements = elements.get("elements", elements) if isinstance(elements, dict) else elements
            feats = [{"type": "Feature", "properties": {},
                      "geometry": {"type": "Polygon", "coordinates": [[[p["lon"], p["lat"]]
                                                                        for p in el["geometry"]]]}}
                     for el in elements if len(el.get("geometry") or []) >= 4]
            return {"type": "FeatureCollection", "features": feats}
    raise HTTPException(status_code=404, detail="No building outlines cached for this result.")


@app.get("/api/results/{result_id}/wards/{unit_type}/{unit_id}")
def get_result_ward(result_id: str, unit_type: str, unit_id: str):
    from analysis.wards import materialize
    r, block, ctx = _load_unit_type(result_id, unit_type)
    for u in block["units"]:
        if str(u.get("unit_id")) == unit_id:
            return materialize(u, unit_type, ctx)
    raise HTTPException(status_code=404, detail="Unknown unit for this result.")


@app.get("/api/scheduler/status")
def scheduler_status():
    """Auto-refresh status: disabled since 2026-09-25 (C46)."""
    return {
        "scheduler_running": False,
        "status": "disabled",
        "reason": SCHEDULER_DISABLED_REASON,
        "next_run": None,
    }


RETIRED_PIPELINE_DETAIL = (
    "The legacy 7-class pipeline is retired and not validated "
    "(08_STATE.md; finding C46). POST /api/scheduler/trigger and the 5-day "
    "auto-refresh are disabled. "
    "POST /api/legacy/analyze still runs it, and its results are marked "
    "'legacy_pipeline' and labelled 'retired'."
)


@app.post("/api/scheduler/trigger")
def trigger_refresh():
    """DISABLED 2026-09-25 (C46): would fan out a run of the retired 7-class
    pipeline for every watched AOI. Returns 410 Gone with the reason. The
    5-day auto-refresh job it used to reschedule was removed the same day."""
    raise HTTPException(status_code=410, detail=RETIRED_PIPELINE_DETAIL)
