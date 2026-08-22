"""
Phase 12A: per-ward geometry-only hazard screening.

Scope (locked, see project methodology notes):
    - Per-ward fluvial, coastal, and flash_flood susceptibility, for
      every unit in a stored boundary layer (e.g. the 24 Mumbai BMC
      wards from Phase 11).
    - Uses ONLY existing, already-verified GEE context functions
      (MERIT Hydro, FABDEM, Copernicus DEM, the sat-io shoreline
      dataset, CHIRPS) -- no Sentinel-2, no SAM, no landcover
      inference, no tiling.
    - pluvial and waterlogging are explicitly NOT calculated here --
      they require per-ward landcover inference (Phase 12B).
    - exposure, vulnerability, and risk are explicitly NOT calculated
      here (Phase 12C).

Two real, stated limitations baked into this module's output, not
hidden:

  1. BOUNDING-BOX GEOMETRY, NOT TRUE POLYGON. get_merit_hand_context(),
     get_fabdem_elevation_stats(), get_slope_stats(), and
     get_coastline_context() only accept (west, south, east, north)
     bbox floats -- none accept an ee.Geometry/polygon directly (see
     ingestion/hydrology.py and ingestion/coastal.py). This means
     every per-ward hazard query in this phase actually runs against
     that ward's RECTANGULAR BOUNDING BOX, not its true irregular
     polygon shape. For an elongated or irregular ward, the bbox can
     include a meaningful amount of area outside the real ward
     boundary, which can skew HAND/coastal-distance/slope statistics.
     Every per-ward result below carries `geometry_type_used:
     "bounding_box"` plus `bbox_area_km2` and `ward_area_km2` so this
     is visible, not silently presented as true polygon-precision.

  2. ONE SHARED RAINFALL VALUE, NOT PER-WARD. Rainfall climatology
     (CHIRPS, ~0.05deg/~5km resolution, 30-year climatological mean)
     is fetched ONCE for the whole AOI covering all wards and reused
     identically across every ward's flash_flood computation. This is
     a deliberate methodology decision, not a shortcut: CHIRPS is too
     coarse to meaningfully resolve differences between adjacent
     Mumbai wards, and flash_flood susceptibility here is long-term
     climatological screening, not event-specific hazard -- per-ward
     rainfall values would imply a precision the source data cannot
     support. Every ward's flash_flood block carries
     `rainfall_spatial_treatment: "single_aoi_value_reused_across_wards"`
     to make this explicit rather than silent.
"""

import os
import json
import threading

import geopandas as gpd
from shapely.geometry import box

from ingestion.hydrology import get_merit_hand_context, get_fabdem_elevation_stats, get_slope_stats
from ingestion.coastal import get_coastline_context
from ingestion.rainfall import get_rainfall_climatology
from ingestion.sentinel2 import aoi_from_bbox
from ingestion.gee_client import initialize_gee
from susceptibility.fluvial import compute_fluvial_susceptibility
from susceptibility.coastal import compute_coastal_susceptibility
from susceptibility.flash_flood import compute_flash_flood_susceptibility

NOT_CALCULATED_REASON = (
    "Requires per-ward land-cover classification. Not implemented in Phase 12A."
)

# GEE's Python client (ee.*.getInfo()) has no built-in request timeout --
# confirmed live: get_coastline_context()'s getInfo() call hung for 20+
# minutes on a real ward (F/S) with no error, no retry, and no way to
# distinguish "slow" from "stuck" without killing the process manually.
# This wrapper puts a hard wall-clock ceiling on any single GEE-calling
# function so one bad ward/call can never block the rest of the 24-ward
# loop. A timeout is treated the same as any other real failure --
# surfaced as status=unavailable with an honest reason, never silently
# skipped or retried into infinity.
GEE_CALL_TIMEOUT_SECONDS = 90


class _DaemonThreadResult:
    """Mirrors zonal/landcover_screening.py's own _call_with_timeout
    pattern exactly -- that file's version works correctly (plain
    threading.Thread with daemon=True set at construction, never
    changed after start()). The earlier ThreadPoolExecutor-subclass
    approach in THIS file was wrong: ThreadPoolExecutor starts its
    worker thread internally before returning control, so setting
    .daemon = True afterward raises "cannot set daemon status of
    active thread" -- confirmed live, every single ward failed
    identically with that exact error. Replaced with the same simple,
    already-proven raw-Thread approach instead of a second broken
    attempt at wrapping the executor."""
    def __init__(self):
        self.value = None
        self.error = None
        self.completed = False


def _call_with_timeout(func, *args, timeout=GEE_CALL_TIMEOUT_SECONDS, **kwargs):
    """
    Run func(*args, **kwargs) in a background daemon thread with a hard
    wall-clock timeout. Returns func's return value on success.

    On timeout, raises TimeoutError identifying which function timed
    out -- the caller converts that into a real, labeled "unavailable"
    result rather than letting it crash the whole run. The underlying
    GEE HTTP call itself is NOT cancelled (Python threads can't be
    killed mid-syscall) -- it keeps running in the background and is
    simply abandoned; daemon=True (set at Thread construction, the
    only point Python allows it) means an abandoned thread can never
    block interpreter shutdown, unlike a non-daemon thread would.
    """
    result = _DaemonThreadResult()

    def _target():
        try:
            result.value = func(*args, **kwargs)
            result.completed = True
        except Exception as e:
            result.error = e
            result.completed = True

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if not result.completed:
        raise TimeoutError(
            f"{func.__name__}() did not return within {timeout}s "
            f"(GEE call likely stalled -- see module docstring)."
        )
    if result.error is not None:
        raise result.error
    return result.value


def _timed_out_context(source_label: str, timeout_seconds: int) -> dict:
    """Shared shape for any context dict replaced by a timeout, so
    downstream compute_*_susceptibility() calls receive a real
    status=unavailable dict (matching what get_merit_hand_context() etc.
    already return on a normal failure) instead of blowing up on a
    missing key."""
    return {
        "status": "unavailable",
        "source": source_label,
        "error": f"GEE call timed out after {timeout_seconds}s.",
    }


def _load_boundary_layer(boundary_layer_id: str, storage_dir: str = "data/boundaries"):
    """
    Load a Phase-11-ingested boundary layer's stored geometry + manifest.
    Reuses the exact storage layout ingest_boundary_layer() writes to
    (boundaries/ingestion.py) -- does not re-validate or re-ingest,
    since that already happened in Phase 11. Fails loudly if the
    boundary layer hasn't been ingested yet, rather than silently
    returning an empty result.
    """
    boundary_path = os.path.join(storage_dir, boundary_layer_id, "boundary.geojson")
    manifest_path = os.path.join(storage_dir, boundary_layer_id, "manifest.json")

    if not os.path.exists(boundary_path):
        raise FileNotFoundError(
            f"No ingested boundary layer found for '{boundary_layer_id}' at "
            f"{boundary_path}. Run boundaries.ingestion.ingest_boundary_layer() "
            f"first (Phase 11) -- this module never ingests boundaries itself."
        )

    with open(manifest_path) as f:
        manifest = json.load(f)

    gdf = gpd.read_file(boundary_path)
    return gdf, manifest


def _ward_bbox_and_areas(ward_geometry) -> dict:
    """
    Derive a ward's (west, south, east, north) bounding box, plus the
    real ward polygon area and the bbox area, in km^2 -- so callers can
    see exactly how much extra area a bbox query covers beyond the
    ward's true shape (see module docstring, limitation 1).

    Areas are computed via an equal-area-ish reprojection (matches the
    approach already used elsewhere in this project for real length/area
    calculations on lon/lat geometry, e.g. get_osm_road_length()'s
    estimate_utm_crs() pattern) -- EPSG:4326 degrees are not directly
    usable as area.
    """
    minx, miny, maxx, maxy = ward_geometry.bounds
    bbox_geom = box(minx, miny, maxx, maxy)

    # Build a tiny single-row GeoDataFrame just to reuse estimate_utm_crs(),
    # the same metric-reprojection approach already used in this project
    # (ingestion/exposure_sources.py's get_osm_road_length()).
    tmp = gpd.GeoDataFrame(
        {"geometry": [ward_geometry, bbox_geom]}, crs="EPSG:4326"
    )
    metric = tmp.to_crs(tmp.estimate_utm_crs())
    ward_area_km2 = float(metric.geometry.iloc[0].area) / 1e6
    bbox_area_km2 = float(metric.geometry.iloc[1].area) / 1e6

    return {
        "west": minx, "south": miny, "east": maxx, "north": maxy,
        "ward_area_km2": round(ward_area_km2, 4),
        "bbox_area_km2": round(bbox_area_km2, 4),
        "bbox_area_excess_pct": (
            round((bbox_area_km2 - ward_area_km2) / ward_area_km2 * 100, 1)
            if ward_area_km2 > 0 else None
        ),
    }


def _tier_from_score(score: float) -> str:
    """
    Shared categorical tier mapping -- matches the very_low..very_high
    scale already used throughout susceptibility/*.py's aoi_mean_class
    output (see confirmed live values: e.g. fluvial 0.8866 -> very_high,
    pluvial 0.5942 -> moderate). Reimplemented here only because the
    per-ward output format in this module reports "tier" directly
    rather than "aoi_mean_class" -- not a new scale, just a renamed
    field for the ward-screening schema.
    """
    if score is None:
        return None
    if score < 0.2:
        return "very_low"
    if score < 0.4:
        return "low"
    if score < 0.6:
        return "moderate"
    if score < 0.8:
        return "high"
    return "very_high"


def compute_ward_hazard_screening(
    ward_id, ward_name, ward_geometry, rainfall_climatology: dict,
) -> dict:
    """
    Compute fluvial, coastal, and flash_flood susceptibility for ONE
    ward. pluvial and waterlogging are always returned as
    not_calculated (see module docstring).

    Args:
        ward_id: this ward's unit_id (from the boundary layer's
            unit_id_field, e.g. `gid`).
        ward_name: this ward's unit_name (e.g. `name`, a BMC ward code
            like "G/N").
        ward_geometry: shapely geometry for this ward (from the
            ingested boundary GeoDataFrame).
        rainfall_climatology: ONE shared rainfall context dict,
            computed once for the whole AOI and reused across every
            ward (see module docstring, limitation 2) -- output of
            ingestion.rainfall.get_rainfall_climatology().

    Returns:
        dict matching the locked Phase 12A per-ward schema.
    """
    geo = _ward_bbox_and_areas(ward_geometry)
    west, south, east, north = geo["west"], geo["south"], geo["east"], geo["north"]

    geometry_note = {
        "geometry_type_used": "bounding_box",
        "ward_area_km2": geo["ward_area_km2"],
        "bbox_area_km2": geo["bbox_area_km2"],
        "bbox_area_excess_pct": geo["bbox_area_excess_pct"],
        "limitation": (
            "Hazard context was queried against this ward's rectangular "
            "bounding box, not its true polygon shape -- the underlying "
            "GEE context functions (MERIT Hydro, FABDEM, Copernicus DEM, "
            "shoreline distance) only accept bbox coordinates. For an "
            "irregular or elongated ward, the bbox may cover meaningfully "
            "more area than the ward itself (see bbox_area_excess_pct), "
            "which can skew these statistics."
        ),
    }

    # ── Fluvial: MERIT Hydro HAND + FABDEM bare-earth elevation ──
    # Each GEE-calling function below is wrapped with a hard timeout
    # (see _call_with_timeout() docstring) -- a stalled call for one
    # ward is caught here and turned into an honest unavailable
    # context, rather than freezing the whole 24-ward loop the way a
    # real live run against F/S ward did (20+ minute hang, no error,
    # required a manual Ctrl-C).
    try:
        hand_context = _call_with_timeout(get_merit_hand_context, west, south, east, north)
    except TimeoutError as e:
        print(f"    WARNING: {e}")
        hand_context = _timed_out_context("MERIT/Hydro/v1_0_1", GEE_CALL_TIMEOUT_SECONDS)

    try:
        fabdem_elevation = _call_with_timeout(get_fabdem_elevation_stats, west, south, east, north)
    except TimeoutError as e:
        print(f"    WARNING: {e}")
        fabdem_elevation = _timed_out_context(
            "projects/sat-io/open-datasets/FABDEM", GEE_CALL_TIMEOUT_SECONDS
        )

    fluvial_result = compute_fluvial_susceptibility(hand_context)
    fluvial_block = {
        "status": fluvial_result.get("status", "not_calculated"),
        "score": fluvial_result.get("aoi_mean_score"),
        "tier": fluvial_result.get("aoi_mean_class"),
        "method": "merit_hand_context",
        "source": "MERIT Hydro + FABDEM elevation",
        **geometry_note,
    }

    # ── Coastal: shoreline distance + FABDEM elevation ──
    try:
        coastal_context = _call_with_timeout(get_coastline_context, west, south, east, north)
    except TimeoutError as e:
        print(f"    WARNING: {e}")
        coastal_context = _timed_out_context(
            "projects/sat-io/open-datasets/shoreline", GEE_CALL_TIMEOUT_SECONDS
        )
        coastal_context["distance_km"] = None
        coastal_context["coastal_connectivity"] = None

    coastal_result = compute_coastal_susceptibility(coastal_context, fabdem_elevation)
    coastal_block = {
        "status": coastal_result.get("status", "not_calculated"),
        "score": coastal_result.get("aoi_mean_score"),
        "tier": coastal_result.get("aoi_mean_class"),
        "method": "coastline_context",
        "source": "GEE sat-io Global Shoreline Dataset + FABDEM elevation",
        "coastline_distance_km": coastal_context.get("distance_km"),
        **geometry_note,
    }

    # ── Flash flood: slope + HAND + ONE shared rainfall value ──
    try:
        slope_context = _call_with_timeout(get_slope_stats, west, south, east, north)
    except TimeoutError as e:
        print(f"    WARNING: {e}")
        slope_context = _timed_out_context("COPERNICUS/DEM/GLO30_2024_1", GEE_CALL_TIMEOUT_SECONDS)

    flash_flood_result = compute_flash_flood_susceptibility(
        slope_context, hand_context, rainfall_climatology
    )
    flash_flood_block = {
        "status": flash_flood_result.get("status", "not_calculated"),
        "score": flash_flood_result.get("aoi_mean_score"),
        "tier": flash_flood_result.get("aoi_mean_class"),
        "method": "slope_hand_rainfall",
        "source": "Copernicus DEM GLO-30 (slope) + MERIT Hydro (HAND) + CHIRPS (rainfall)",
        "rainfall_source": "CHIRPS",
        "rainfall_resolution": "0.05_deg_approx_5km",
        "rainfall_temporal_basis": "30_year_climatology",
        "rainfall_spatial_treatment": "single_aoi_value_reused_across_wards",
        "rainfall_mean_annual_mm": rainfall_climatology.get("mean_annual_mm"),
        "limitation": (
            "Localized storm intensity and microclimatic variation within "
            "the AOI are not captured -- one climatological rainfall value "
            "is reused across every ward (see module docstring)."
        ),
        **geometry_note,
    }

    return {
        "unit_id": ward_id,
        "unit_name": ward_name,
        "hazards": {
            "fluvial": fluvial_block,
            "coastal": coastal_block,
            "flash_flood": flash_flood_block,
            "pluvial": {"status": "not_calculated", "reason": NOT_CALCULATED_REASON},
            "waterlogging": {"status": "not_calculated", "reason": NOT_CALCULATED_REASON},
        },
    }


def run_ward_hazard_screening(
    boundary_layer_id: str, storage_dir: str = "data/boundaries",
) -> dict:
    """
    Phase 12A entry point: compute fluvial/coastal/flash_flood
    susceptibility for every ward in an ingested boundary layer.

    Rainfall climatology is fetched ONCE, for the bounding box of the
    boundary layer's FULL extent (all wards combined), and reused
    identically across every ward -- see module docstring, limitation 2.
    This is a deliberate, stated methodology decision, not an oversight.

    exposure, vulnerability, and risk are NOT computed here (Phase 12C).

    Returns:
        dict with status, boundary_layer_id, unit_count, units (list of
        compute_ward_hazard_screening() results), and the rainfall
        context actually used (for full transparency/reproducibility).
    """
    initialize_gee()

    gdf, manifest = _load_boundary_layer(boundary_layer_id, storage_dir)
    unit_id_field = manifest["unit_id_field"]
    unit_name_field = manifest["unit_name_field"]

    # One shared rainfall climatology value for the whole boundary
    # layer's extent -- computed once, reused across all wards.
    minx, miny, maxx, maxy = gdf.total_bounds
    full_extent_aoi = aoi_from_bbox(minx, miny, maxx, maxy)
    rainfall_climatology = get_rainfall_climatology(full_extent_aoi)

    print(f"Phase 12A: hazard screening for boundary layer '{boundary_layer_id}' "
          f"({len(gdf)} units). Rainfall climatology (shared across all wards): "
          f"{rainfall_climatology.get('mean_annual_mm')} mm/year "
          f"(status={rainfall_climatology.get('status')})")

    units = []
    for _, row in gdf.iterrows():
        ward_id = row[unit_id_field]
        ward_name = row[unit_name_field]
        print(f"  Ward {ward_id} ({ward_name})...")
        try:
            unit_result = compute_ward_hazard_screening(
                ward_id, ward_name, row.geometry, rainfall_climatology,
            )
        except Exception as e:
            print(f"  Ward {ward_id} ({ward_name}) FAILED: {e}")
            unit_result = {
                "unit_id": ward_id,
                "unit_name": ward_name,
                "status": "failed",
                "error": str(e),
                "hazards": {
                    "fluvial": {"status": "not_calculated", "reason": f"Ward computation failed: {e}"},
                    "coastal": {"status": "not_calculated", "reason": f"Ward computation failed: {e}"},
                    "flash_flood": {"status": "not_calculated", "reason": f"Ward computation failed: {e}"},
                    "pluvial": {"status": "not_calculated", "reason": NOT_CALCULATED_REASON},
                    "waterlogging": {"status": "not_calculated", "reason": NOT_CALCULATED_REASON},
                },
            }
        units.append(unit_result)

    print(f"Phase 12A complete: {len(units)} units processed.")

    return {
        "status": "available",
        "analysis_mode": "ward_hazard_screening",
        "phase": "12A",
        "boundary_layer_id": boundary_layer_id,
        "unit_count": len(units),
        "rainfall_climatology_used": {
            "mean_annual_mm": rainfall_climatology.get("mean_annual_mm"),
            "status": rainfall_climatology.get("status"),
            "spatial_treatment": "single_value_computed_over_full_boundary_layer_extent",
        },
        "not_calculated_in_this_phase": ["pluvial", "waterlogging", "exposure", "vulnerability", "risk"],
        "units": units,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 12A: per-ward hazard screening")
    parser.add_argument("--boundary-layer-id", type=str, required=True,
                         help="e.g. datameet_mumbai_bmc_wards")
    parser.add_argument("--storage-dir", type=str, default="data/boundaries")
    parser.add_argument("--output", type=str, default=None,
                         help="Optional path to save the result JSON")
    args = parser.parse_args()

    result = run_ward_hazard_screening(args.boundary_layer_id, args.storage_dir)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"Saved: {args.output}") 