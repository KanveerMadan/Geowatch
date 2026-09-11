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
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

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
            f"returns run data, and POST /api/scheduler/trigger fans one "
            f"request out into a pipeline run per watched AOI. Set "
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

# ── Static file mount ──
# Serves pipeline run outputs (landcover.png, landcover_confidence.png, etc.)
# so the frontend can load them directly via <ImageOverlay>.
# App.jsx's landcoverImageUrl() assumes exactly this convention:
#   {API}/runs/<run_id>/<filename>
os.makedirs("data/pipeline_runs", exist_ok=True)
app.mount("/runs", StaticFiles(directory="data/pipeline_runs"), name="runs")

# ── Watched AOIs — refreshed automatically every 5 days ──
WATCHED_AOIS = [
    {"label": "dharavi", "west": 72.836,  "south": 19.037,  "east": 72.862,  "north": 19.060},
    {"label": "nairobi", "west": 36.775,  "south": -1.320,  "east": 36.810,  "north": -1.290},
    {"label": "jakarta", "west": 106.820, "south": -6.140,  "east": 106.870, "north": -6.090},
]
# ── AOI area limit — geodesic, in real km², not square-degrees ──
# PREVIOUS BUG: bbox_area = (east-west)*(north-south) is square-degrees,
# not km². Its physical meaning changes with latitude -- one degree of
# longitude shrinks toward the poles, so the same threshold (0.01) let
# through wildly different real-world areas depending on where on Earth
# the AOI sat. Fixed via pyproj.Geod's geodesic polygon area, which is
# latitude-correct everywhere.
MAX_AOI_AREA_KM2 = 100.0  # roughly ~10km x 10km, matches the original intent

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
    if not isinstance(label, str) or not AOI_LABEL_PATTERN.fullmatch(label):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid aoi_label. Allowed characters: lowercase a-z, "
                "digits 0-9, underscore and hyphen; length 1-"
                f"{AOI_LABEL_MAX_LENGTH}."
            ),
        )
    return label


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

def get_latest_run(aoi_label: str) -> dict | None:
    """Return the most recent result.json for a given AOI label, or None."""
    runs_dir = Path("data/pipeline_runs")
    matching = sorted([
        d for d in runs_dir.iterdir()
        if d.is_dir() and d.name.startswith(aoi_label)
    ])
    if not matching:
        return None
    result_path = matching[-1] / "result.json"
    if not result_path.exists():
        return None
    with open(result_path) as f:
        return json.load(f)


def refresh_all_watched_aois():
    """Background job — re-runs pipeline for all watched AOIs with latest imagery."""
    print(f"[Scheduler] Starting refresh at {datetime.now().isoformat()}")
    from pipeline import run_pipeline
    for aoi in WATCHED_AOIS:
        try:
            run_pipeline(
                west=aoi["west"], south=aoi["south"],
                east=aoi["east"], north=aoi["north"],
                start_date=None, end_date=None,  # triggers get_latest_image()
                aoi_label=aoi["label"],
            )
            print(f"[Scheduler] {aoi['label']} refreshed OK.")
        except Exception as e:
            print(f"[Scheduler] {aoi['label']} failed: {e}")


# Start background scheduler — refreshes every 5 days
scheduler = BackgroundScheduler()
scheduler.add_job(refresh_all_watched_aois, "interval", days=5, id="auto_refresh")
scheduler.start()
print("[Scheduler] Auto-refresh scheduler started — interval: 5 days.")


class AnalyzeRequest(BaseModel):
    west: float
    south: float
    east: float
    north: float
    start_date: str = None
    end_date: str = None
    aoi_label: str = "aoi"
    demo: bool = False


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
    next_run = scheduler.get_job("auto_refresh").next_run_time
    return {
        "status": "GeoWatch Copilot API running",
        "version": "1.0",
        "scheduler": "active",
        "next_auto_refresh": next_run.isoformat() if next_run else "unknown",
    }


@app.get("/api/demo")
def get_demo():
    """Always serves the most recent Dharavi result — auto-updated by scheduler."""
    data = get_latest_run("dharavi")
    if not data:
        raise HTTPException(status_code=404, detail="No Dharavi run found. Run pipeline first.")
    data["_demo_mode"] = True
    return data


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    # C16: validate first, unconditionally, and OUTSIDE the try/except below.
    # That block catches bare `Exception`, and HTTPException IS an Exception,
    # so a 400 raised inside it would be swallowed and re-raised as a 500.
    # Unconditional (before the `demo` short-circuit) so there is no request
    # shape that reaches path construction with an unchecked label.
    validate_aoi_label(req.aoi_label)
    if req.demo:
        return get_demo()
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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/runs")
def list_runs():
    runs_dir = Path("data/pipeline_runs")
    if not runs_dir.exists():
        return {"runs": []}
    runs = []
    for run_dir in sorted(runs_dir.iterdir(), reverse=True):
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
            })
    return {"runs": runs}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    result_path = Path(f"data/pipeline_runs/{run_id}/result.json")
    if not result_path.exists():
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")
    with open(result_path) as f:
        return json.load(f)


@app.get("/api/scheduler/status")
def scheduler_status():
    """Check auto-refresh scheduler status."""
    job = scheduler.get_job("auto_refresh")
    return {
        "scheduler_running": scheduler.running,
        "next_run": job.next_run_time.isoformat() if job and job.next_run_time else "unknown",
        "watched_aois": [a["label"] for a in WATCHED_AOIS],
    }


@app.post("/api/scheduler/trigger")
def trigger_refresh():
    """Manually trigger a refresh of all watched AOIs (admin use)."""
    scheduler.modify_job("auto_refresh", next_run_time=datetime.now())
    return {"status": "refresh triggered", "message": "All watched AOIs queued for refresh."}


@app.on_event("shutdown")
def shutdown():
    scheduler.shutdown()