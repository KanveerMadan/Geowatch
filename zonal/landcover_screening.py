"""
Phase 12B: per-ward pluvial + waterlogging screening.

Unlike Phase 12A (zonal/hazard_screening.py), which is pure bbox/GEE-
scalar and needs no imagery at all, pluvial and waterlogging susceptibility
are computed from real per-pixel land-cover classification
(compute_pluvial_susceptibility / compute_waterlogging_susceptibility in
susceptibility/*.py both consume category_area_pct and per-pixel arrays
derived from run_pipeline()'s SAM+inference output). There is no bbox
shortcut for these two hazards the way there is for fluvial/coastal/
flash_flood in 12A.

Design, in order:
  1. Case 1/2/3 planner (get_or_run_wide_landcover): decide whether to
     reuse a prior wide-AOI run, trigger a fresh one, or give up and
     mark every ward not_calculated.
  2. True-polygon ward rasterization (_rasterize_ward_mask): unlike
     12A's hazard functions (which only accept bbox floats -- a hard
     GEE API constraint), the wide run's landcover_map_full is a local
     numpy array with a known affine mapping. This lets us mask by each
     ward's REAL polygon shape, genuinely fixing 12A's bbox-surrogate
     limitation for these two hazards -- not just inheriting it.
  3. Per-ward extraction + susceptibility computation
     (compute_ward_landcover_screening): slices the wide arrays by each
     ward's mask, computes category_area_pct for that ward alone, then
     runs the existing (unmodified) hydrological-surfaces + pluvial +
     waterlogging functions on that ward-scoped slice.

ASSUMPTIONS FLAGGED FOR VERIFICATION (not confirmed against real code,
since pipeline.py's exact return/save shape for landcover_map_full,
waterway_dist_map, and raster_info was not directly inspected for this
file -- only inferred from tiler.py/inference.py call patterns already
reviewed). Search for "ASSUMPTION:" below before running against the
real repo.
"""

import json
import os
import threading
from datetime import date, datetime, timedelta

import numpy as np
import rasterio
import rasterio.features
import geopandas as gpd

from configs.zonal_constants import (
    LANDCOVER_STALENESS_DAYS,
    MIN_FOOTPRINT_COVERAGE_PCT,
    WIDE_RUN_TIMEOUT_SECONDS,
    WIDE_RUN_DATE_START,
    WIDE_RUN_DATE_END,
    MIN_VALID_OBSERVATION_PCT,
    REQUIRE_LANDCOVER_IN_DISTRIBUTION,
)
from perception.hydrological_surfaces import compute_hydrological_surfaces
from susceptibility.pluvial import compute_pluvial_susceptibility
from susceptibility.waterlogging import compute_waterlogging_susceptibility

# Must match compute_pluvial_susceptibility()'s `unknown_index` default
# (255) and inference.py's UNKNOWN_INDEX. Used to mark out-of-ward pixels
# inside a ward's bounding-box window so they are excluded from the
# ward's score without breaking the 2-D array shape pluvial requires.
PLUVIAL_UNKNOWN_INDEX = 255


def _json_safe(o):
    """
    json.dump() default= hook. Ward ids come from a GeoDataFrame column
    (numpy.int64) and category_area_pct values are numpy.float64 from
    `round(100.0 * count / total, 2)` where count is a numpy integer --
    neither is JSON-serializable, and both reach json.dump() unconverted.
    Converts numpy scalars/arrays to plain Python rather than silently
    dropping them.
    """
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    raise TypeError(f"Object of type {type(o).__name__} is not JSON serializable")

# ASSUMPTION: run_pipeline lives at top-level pipeline.py per the
# already-reviewed dump and exposes this signature (west/south/east/north/
# start/end/label/output_dir), matching the CLI arg names seen in the
# pilot_3ward run's argparse usage line.
from pipeline import run_pipeline


# ── daemon-thread timeout wrapper, mirroring hazard_screening.py's
#    fix for Phase 12A's non-daemon-thread hang, but with its own,
#    much longer ceiling (WIDE_RUN_TIMEOUT_SECONDS vs 12A's 90s) since
#    this times a full SAM+inference run, not a scalar GEE query. ──
class _DaemonThreadResult:
    def __init__(self):
        self.value = None
        self.error = None
        self.completed = False


def _call_with_timeout(fn, timeout_seconds, *args, **kwargs):
    result = _DaemonThreadResult()

    def _target():
        try:
            result.value = fn(*args, **kwargs)
            result.completed = True
        except Exception as e:
            result.error = e
            result.completed = True

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout=timeout_seconds)

    if not result.completed:
        print(f"    WARNING: {fn.__name__}() did not return within "
              f"{timeout_seconds}s (wide-run likely stalled).")
        return None, "timeout"
    if result.error is not None:
        print(f"    WARNING: {fn.__name__}() raised: {result.error}")
        return None, str(result.error)
    return result.value, None


# ── Case 1/2/3 planner ──

def _combined_bounds(gdf: "gpd.GeoDataFrame") -> tuple:
    west, south, east, north = gdf.total_bounds
    return float(west), float(south), float(east), float(north)


def _footprint_coverage_pct(prior_bounds: tuple, target_bounds: tuple) -> float:
    """
    What fraction of target_bounds' area is covered by prior_bounds.
    Simple bbox-vs-bbox overlap check -- deliberately not a true
    polygon-intersection (that's what MIN_FOOTPRINT_COVERAGE_PCT's
    generous 99% threshold is for: a bbox-level check this strict is
    already close to requiring true coverage in practice for a
    contiguous ward layer).
    """
    pw, ps, pe, pn = prior_bounds
    tw, ts, te, tn = target_bounds

    ix_w, ix_s = max(pw, tw), max(ps, ts)
    ix_e, ix_n = min(pe, te), min(pn, tn)
    if ix_e <= ix_w or ix_n <= ix_s:
        return 0.0

    intersect_area = (ix_e - ix_w) * (ix_n - ix_s)
    target_area = (te - tw) * (tn - ts)
    if target_area <= 0:
        return 0.0
    return round(100.0 * intersect_area / target_area, 2)


def _find_reusable_wide_run(output_dir: str, target_bounds: tuple,
                             staleness_days: int) -> dict | None:
    """
    Scan output_dir for prior wide-AOI runs' result.json manifests and
    return the newest one that is both fresh enough and covers
    target_bounds sufficiently. Returns None if nothing qualifies
    (Case 2/3 territory).

    CONFIRMED against a real result.json: there is no "aoi_bounds" or
    "run_timestamp" field. AOI is nested at result["aoi"] = {"west":
    ..., "south": ..., "east": ..., "north": ...}. There is no ISO
    timestamp field at all -- run_id embeds it as a string suffix
    (e.g. "pilot_3ward_20260807_162911" -> 2026-08-07 16:29:11),
    parsed here rather than relying on a field that doesn't exist.
    Also requires landcover_map_full.npy + raster_info.json to sit
    alongside result.json (Option A persistence, added to pipeline.py)
    -- a run without those two files cannot be reused regardless of
    how fresh/well-covering its result.json looks, since there is
    nothing to rasterize a ward mask against.
    """
    if not os.path.isdir(output_dir):
        return None

    candidates = []
    cutoff = datetime.now() - timedelta(days=staleness_days)

    for run_name in os.listdir(output_dir):
        run_dir = os.path.join(output_dir, run_name)
        result_path = os.path.join(run_dir, "result.json")
        landcover_path = os.path.join(run_dir, "landcover_map_full.npy")
        raster_info_path = os.path.join(run_dir, "raster_info.json")
        waterway_path = os.path.join(run_dir, "waterway_dist_map_full.npy")

        if not (os.path.isfile(result_path)
                and os.path.isfile(landcover_path)
                and os.path.isfile(raster_info_path)):
            continue
        # waterway_dist_map_full.npy is allowed to be genuinely absent
        # (AOI had no OSM waterway data) -- only landcover_map_full and
        # raster_info are hard requirements for reuse.
        try:
            with open(result_path) as f:
                result = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        aoi = result.get("aoi")
        if aoi is None:
            continue
        run_bounds = (aoi["west"], aoi["south"], aoi["east"], aoi["north"])

        # run_id suffix format: "<label>_YYYYMMDD_HHMMSS"
        run_id = result.get("run_id", "")
        try:
            date_part, time_part = run_id.rsplit("_", 2)[-2:]
            run_time = datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S")
        except (ValueError, IndexError):
            continue

        if run_time < cutoff:
            continue

        coverage = _footprint_coverage_pct(run_bounds, target_bounds)
        if coverage < MIN_FOOTPRINT_COVERAGE_PCT:
            continue

        candidates.append({
            "run_name": run_name,
            "run_dir": run_dir,
            "result_path": result_path,
            "landcover_path": landcover_path,
            "raster_info_path": raster_info_path,
            "waterway_path": waterway_path if os.path.isfile(waterway_path) else None,
            "result": result,
            "run_time": run_time,
            "coverage_pct": coverage,
        })

    if not candidates:
        return None

    candidates.sort(key=lambda c: c["run_time"], reverse=True)
    return candidates[0]


def _passes_quality_gate(result: dict) -> tuple:
    """
    Returns (passed: bool, reason: str|None). Checked on EVERY wide
    run before its output is accepted for ward extraction -- both a
    freshly triggered Case 3 run and a reused Case 1 run go through
    this, since a prior run being fresh/covering enough doesn't mean
    it was ever quality-checked at save time.

    CONFIRMED against a real result.json: field is
    observation_quality.valid_observation_pct (not "valid_pct"), and
    applicability.urban_landcover_model.status is exactly as assumed.
    """
    obs_quality = result.get("observation_quality", {})
    valid_pct = obs_quality.get("valid_observation_pct")
    if valid_pct is None or valid_pct < MIN_VALID_OBSERVATION_PCT:
        return False, (
            f"observation_quality.valid_observation_pct={valid_pct} below "
            f"MIN_VALID_OBSERVATION_PCT={MIN_VALID_OBSERVATION_PCT}"
        )

    if REQUIRE_LANDCOVER_IN_DISTRIBUTION:
        applicability = result.get("applicability", {})
        landcover_status = applicability.get("urban_landcover_model", {}).get("status")
        if landcover_status == "out_of_distribution":
            return False, (
                "applicability.urban_landcover_model.status="
                "out_of_distribution"
            )

    return True, None


def get_or_run_wide_landcover(boundary_layer_id: str, storage_dir: str,
                               output_dir: str, force_refresh: bool = False) -> dict:
    """
    Case 1/2/3 planner. Returns a dict shaped either:
      {"status": "available", "case": "reused"|"triggered", "result": {...},
       "run_dir": "...", "quality_gate_reason": None}
    or:
      {"status": "not_calculated", "case": "no_valid_run",
       "reason": "..."}

    Never raises on a missing/degraded run -- degradation is always
    returned as a visible status, same pattern as every other
    status-carrying function in this project (get_rainfall_climatology,
    get_fabdem_elevation_stats, etc.).
    """
    boundary_path = os.path.join(storage_dir, boundary_layer_id, "boundary.geojson")
    gdf = gpd.read_file(boundary_path)
    target_bounds = _combined_bounds(gdf)

    # ── Case 1: reuse ──
    if not force_refresh:
        reusable = _find_reusable_wide_run(
            output_dir, target_bounds, LANDCOVER_STALENESS_DAYS
        )
        if reusable is not None:
            passed, reason = _passes_quality_gate(reusable["result"])
            if passed:
                print(f"Case 1 (reuse): using prior run "
                      f"'{reusable['run_name']}' "
                      f"(coverage={reusable['coverage_pct']}%, "
                      f"age<{LANDCOVER_STALENESS_DAYS}d)")
                landcover_map_full = np.load(reusable["landcover_path"])
                with open(reusable["raster_info_path"]) as f:
                    raster_info = json.load(f)
                result = dict(reusable["result"])
                result["landcover_map_full"] = landcover_map_full
                result["raster_info"] = raster_info
                if reusable["waterway_path"] is not None:
                    result["waterway_dist_map_full"] = np.load(reusable["waterway_path"])
                else:
                    # Genuinely no waterways in this AOI (confirmed by
                    # the patch's explicit None-on-disk signal, not a
                    # missing file from a pre-patch run -- those runs
                    # were already excluded above by the hard landcover_
                    # path/raster_info_path requirement, so reaching
                    # here always means "no waterways," never "unknown."
                    result["waterway_dist_map_full"] = None
                return {
                    "status": "available",
                    "case": "reused",
                    "result": result,
                    "run_dir": reusable["run_dir"],
                    "quality_gate_reason": None,
                }
            else:
                print(f"Case 1 candidate '{reusable['run_name']}' found "
                      f"but FAILED quality gate: {reason}. Falling "
                      f"through to Case 3.")

    # ── Case 3: trigger a fresh wide run ──
    print("Triggering fresh wide-AOI run for landcover-dependent "
          "per-ward screening...")
    west, south, east, north = target_bounds
    label = f"phase12b_wide_{boundary_layer_id}"

    run_kwargs = dict(
        west=west, south=south, east=east, north=north,
        aoi_label=label, output_dir=output_dir,
        start_date=WIDE_RUN_DATE_START, end_date=WIDE_RUN_DATE_END,
    )
    result, error = _call_with_timeout(
        run_pipeline, WIDE_RUN_TIMEOUT_SECONDS, **run_kwargs
    )

    if error is not None:
        return {
            "status": "not_calculated",
            "case": "no_valid_run",
            "reason": f"wide run failed or timed out: {error}",
        }

    passed, reason = _passes_quality_gate(result)
    if not passed:
        return {
            "status": "not_calculated",
            "case": "no_valid_run",
            "reason": f"fresh wide run completed but failed quality "
                      f"gate: {reason}",
        }

    # run_pipeline()'s returned dict does NOT include landcover_map_full/
    # raster_info/waterway_dist_map_full -- confirmed against the real
    # pipeline.py: those are local variables inside run_pipeline(),
    # never merged into result via result.update(). Only the Option A
    # patch's separate .npy/.json files on disk carry them. So even for
    # a just-triggered Case 3 run, load from disk the same way Case 1
    # does -- there is no in-memory shortcut here despite this being
    # the same process that just computed them.
    fresh_run_dir = os.path.join(output_dir, result["run_id"])
    landcover_map_path = os.path.join(fresh_run_dir, "landcover_map_full.npy")
    raster_info_path = os.path.join(fresh_run_dir, "raster_info.json")
    waterway_path = os.path.join(fresh_run_dir, "waterway_dist_map_full.npy")

    if not (os.path.isfile(landcover_map_path) and os.path.isfile(raster_info_path)):
        return {
            "status": "not_calculated",
            "case": "no_valid_run",
            "reason": "fresh wide run completed and passed the quality "
                      "gate, but landcover_map_full.npy/raster_info.json "
                      "were not found on disk afterward -- the Option A "
                      "persistence patch may not be applied to this "
                      "pipeline.py, or failed silently.",
        }

    result["landcover_map_full"] = np.load(landcover_map_path)
    with open(raster_info_path) as f:
        result["raster_info"] = json.load(f)
    result["waterway_dist_map_full"] = (
        np.load(waterway_path) if os.path.isfile(waterway_path) else None
    )

    print("Case 3 (triggered): fresh wide run passed quality gate.")
    return {
        "status": "available",
        "case": "triggered",
        "result": result,
        "run_dir": fresh_run_dir,
        "quality_gate_reason": None,
    }


# ── True-polygon ward rasterization ──

def _rasterize_ward_mask(ward_geometry, raster_info: dict) -> np.ndarray:
    """
    Convert a ward's real polygon into a boolean pixel mask against the
    wide run's raster grid.

    CONFIRMED against ingestion/tiler.py's generate_rgb_preview_tiles():
    raster_info = {"width": int, "height": int,
                    "bounds": (west, south, east, north), "crs": str}
    -- NOT an affine transform directly. Built here via
    rasterio.transform.from_bounds(), which is exact and lossless for
    an unrotated raster (true of every GEE-exported image in this
    pipeline).

    CONFIRMED against the real pipeline.py: this IS the same raster_info
    used for landcover_map_full -- full_width/full_height are read
    directly off it two lines after generate_rgb_preview_tiles() runs,
    and landcover_map_full is allocated at exactly those dimensions.
    No separate raw-tile raster space in play.
    """
    from rasterio.transform import from_bounds

    width = raster_info["width"]
    height = raster_info["height"]
    west, south, east, north = raster_info["bounds"]
    transform = from_bounds(west, south, east, north, width, height)

    mask = rasterio.features.geometry_mask(
        [ward_geometry],
        out_shape=(height, width),
        transform=transform,
        invert=True,  # True = inside the ward polygon
    )
    return mask


# ── Per-ward extraction + susceptibility ──

def compute_ward_landcover_screening(ward_id, ward_name: str,
                                      ward_mask: np.ndarray,
                                      landcover_map_full: np.ndarray,
                                      waterway_dist_map_full: np.ndarray,
                                      wide_result: dict) -> dict:
    """
    Slice the wide run's arrays to one ward's true-polygon pixels,
    compute that ward's own category_area_pct, and run the existing
    (unmodified) hydrological-surfaces + pluvial + waterlogging
    functions on the ward-scoped slice.

    If the ward's mask contains zero pixels (e.g. a ward entirely
    outside the wide run's actual raster footprint despite passing the
    bbox coverage check -- possible for an irregularly-shaped ward
    near the wide AOI's edge), returns not_calculated rather than
    dividing by zero or fabricating a result.
    """
    pixel_count = int(ward_mask.sum())
    if pixel_count == 0:
        return {
            "ward_id": ward_id,
            "ward_name": ward_name,
            "pluvial": {"status": "not_calculated",
                        "reason": "zero pixels in ward mask "
                                  "(ward likely outside wide run's actual "
                                  "raster footprint despite bbox coverage "
                                  "check passing)"},
            "waterlogging": {"status": "not_calculated",
                              "reason": "zero pixels in ward mask"},
        }

    # compute_pluvial_susceptibility() does `H, W = landcover_map.shape`
    # and builds per-pixel rasters -- it requires a 2-D array on the same
    # grid as waterway_dist_map. Boolean-mask indexing
    # (landcover_map_full[ward_mask]) returns a FLAT 1-D array and raises
    # "not enough values to unpack (expected 2, got 1)". Confirmed by
    # execution against a real wide run before this fix.
    #
    # Instead: crop to the ward's bounding-box window (keeps this O(ward)
    # rather than O(full raster) per ward), then set every pixel OUTSIDE
    # the true ward polygon to UNKNOWN_INDEX within that window. pluvial
    # already excludes unknown_index pixels from aoi_mean_score
    # (`unknown_mask = landcover_map == unknown_index`), so out-of-ward
    # pixels contribute nothing to the score while the array keeps the
    # 2-D shape and the waterway grid alignment the function needs.
    rows = np.any(ward_mask, axis=1)
    cols = np.any(ward_mask, axis=0)
    r0, r1 = int(np.argmax(rows)), int(len(rows) - np.argmax(rows[::-1]))
    c0, c1 = int(np.argmax(cols)), int(len(cols) - np.argmax(cols[::-1]))

    win_mask = ward_mask[r0:r1, c0:c1]
    ward_landcover_2d = landcover_map_full[r0:r1, c0:c1].copy()
    ward_landcover_2d[~win_mask] = PLUVIAL_UNKNOWN_INDEX

    # 1-D vector of in-ward pixels only, used for category_area_pct
    ward_landcover = landcover_map_full[ward_mask]

    # waterway_dist_map_full may be genuinely None (AOI had no OSM
    # waterway data at all, per the Option A patch's explicit signal)
    # -- distinct from the earlier hard-fail case in
    # run_ward_landcover_screening(), which catches "never loaded."
    # Sliced to the SAME window so the two rasters stay aligned; values
    # outside the ward are irrelevant because those pixels are unknown.
    ward_waterway_dist = (
        waterway_dist_map_full[r0:r1, c0:c1]
        if waterway_dist_map_full is not None else None
    )

    # CORRECTED against real pipeline.py signatures (previous version of
    # this file called both functions with fabricated argument names
    # that don't exist -- category_area_pct/impervious_fraction_pct --
    # and never checked pipeline.py's actual call sites):
    #   compute_pluvial_susceptibility(landcover_map, categories,
    #       waterway_dist_map, relative_elevation_score,
    #       rainfall_mean_annual_mm)
    #   compute_waterlogging_susceptibility(hand_context,
    #       hydrological_surfaces, rainfall_climatology)
    #
    # IMPORTANT LIMITATION, not hidden: relative_elevation_score,
    # rainfall_mean_annual_mm, and hand_context are AOI-WIDE SCALARS in
    # the current architecture -- computed once against the wide run's
    # full bbox, with no per-pixel/per-ward variant existing anywhere
    # in this codebase yet. That means every ward screened here shares
    # the IDENTICAL rainfall/elevation/HAND context; only the land-cover
    # component (landcover_map, category_area_pct via
    # hydrological_surfaces) genuinely varies per ward. This is
    # surfaced explicitly in the output below (shared_aoi_context) so a
    # reviewer isn't misled into thinking these are independently
    # measured per ward.
    categories = wide_result.get("landcover", {}).get("categories")
    unique, counts = np.unique(ward_landcover, return_counts=True)
    total = ward_landcover.size
    category_area_pct = {}
    for idx, count in zip(unique, counts):
        if categories is not None and 0 <= idx < len(categories):
            cat_name = categories[idx]
            category_area_pct[cat_name] = round(100.0 * count / total, 2)

    hydro_surfaces = compute_hydrological_surfaces(category_area_pct)

    relative_elevation_score = (
        wide_result.get("terrain_context", {})
        .get("relative_elevation_proxy", {}).get("score")
    )
    rainfall_climatology = wide_result.get("rainfall_climatology", {})
    hand_context = wide_result.get("terrain_context", {}).get("fluvial_hand_context", {})

    pluvial = compute_pluvial_susceptibility(
        landcover_map=ward_landcover_2d,
        categories=categories,
        waterway_dist_map=ward_waterway_dist,
        relative_elevation_score=relative_elevation_score,
        rainfall_mean_annual_mm=rainfall_climatology.get("mean_annual_mm"),
    )
    # pluvial returns a full per-pixel `susceptibility_map` ndarray, which
    # is not JSON-serializable. pipeline.py strips it before writing
    # result.json (`pluvial_result_serializable = {k: v for k, v in ...
    # if k != "susceptibility_map"}`); this file did not, so json.dump()
    # raised "Object of type ndarray is not JSON serializable". Mirror
    # pipeline.py's behaviour rather than inventing a new one. The map is
    # dropped, not saved to disk, because 12B's unit of output is the
    # per-ward scalar -- a per-ward PNG is a Phase 12C/13 concern.
    pluvial = {k: v for k, v in pluvial.items() if k != "susceptibility_map"}
    waterlogging = compute_waterlogging_susceptibility(
        hand_context=hand_context,
        hydrological_surfaces=hydro_surfaces,
        rainfall_climatology=rainfall_climatology,
    )

    return {
        "ward_id": ward_id,
        "ward_name": ward_name,
        "pixel_count": pixel_count,
        "category_area_pct": category_area_pct,
        "hydrological_surfaces": hydro_surfaces,
        "pluvial": pluvial,
        "waterlogging": waterlogging,
        # Explicit, not hidden: rainfall/elevation/HAND inputs to both
        # susceptibility functions are AOI-wide scalars, identical
        # across every ward in this run -- only category_area_pct
        # (and therefore hydrological_surfaces) genuinely varies per
        # ward. A reviewer comparing wards should know pluvial/
        # waterlogging differences here are driven by land-cover alone.
        "shared_aoi_context": {
            "relative_elevation_score": relative_elevation_score,
            "rainfall_mean_annual_mm": rainfall_climatology.get("mean_annual_mm"),
            "hand_mean_m": hand_context.get("mean_hnd_m"),
            "note": "identical across all wards in this run -- not "
                    "independently measured per ward",
        },
        # source-run quality context carried alongside every ward's
        # result -- not just the numbers, so a reviewer can see what
        # quality of imagery produced them without cross-referencing
        # a separate file. See point 3 from the pilot-run debrief.
        "source_observation_quality": wide_result.get("observation_quality"),
        "source_run_id": wide_result.get("run_id"),
    }


# ── Entry point ──

def run_ward_landcover_screening(boundary_layer_id: str, storage_dir: str,
                                  output: str, wide_run_output_dir: str = None,
                                  force_refresh: bool = False):
    wide_run_output_dir = wide_run_output_dir or "data/pipeline_runs"

    planner_result = get_or_run_wide_landcover(
        boundary_layer_id, storage_dir, wide_run_output_dir, force_refresh
    )

    boundary_path = os.path.join(storage_dir, boundary_layer_id, "boundary.geojson")
    gdf = gpd.read_file(boundary_path)

    if planner_result["status"] != "available":
        print(f"No usable wide run ({planner_result['reason']}). "
              f"Marking all {len(gdf)} wards not_calculated.")
        ward_results = []
        for _, row in gdf.iterrows():
            ward_results.append({
                "ward_id": row["gid"],
                "ward_name": row["name"],
                "pluvial": {"status": "not_calculated",
                            "reason": planner_result["reason"]},
                "waterlogging": {"status": "not_calculated",
                                  "reason": planner_result["reason"]},
            })
    else:
        wide_result = planner_result["result"]
        # ASSUMPTION: these two arrays are available either directly on
        # the in-memory result dict (Case 3, same process) or re-loadable
        # from files under run_dir (Case 1, reused from disk) -- exact
        # persistence mechanism (npy files? embedded in result.json?
        # separate landcover_map.npy alongside landcover.png?) not
        # confirmed. This needs verification against pipeline.py's real
        # save behavior before this file will actually run.
        landcover_map_full = wide_result.get("landcover_map_full")
        waterway_dist_map_full = wide_result.get("waterway_dist_map_full")
        raster_info = wide_result.get("raster_info")

        if landcover_map_full is None or raster_info is None:
            raise NotImplementedError(
                "landcover_map_full/raster_info not found on the wide "
                "run's result. If this was a Case 1 (reused) run, check "
                "that the Option A persistence patch actually ran on "
                "the prior pipeline.py invocation being reused (pre-"
                "patch runs won't have landcover_map_full.npy / "
                "raster_info.json on disk and are already excluded from "
                "reuse by _find_reusable_wide_run's file-existence check "
                "-- this branch means Case 3 itself failed to produce "
                "them, which points at a bug in the patch, not a stale "
                "prior run)."
            )
        # NOTE: waterway_dist_map_full being None here is NOT an error
        # by itself -- it's the legitimate "no OSM waterways in this "
        # AOI" case, which compute_ward_landcover_screening() already
        # handles per-ward. No hard-fail check needed for it.

        print(f"Phase 12B: per-ward landcover screening for "
              f"'{boundary_layer_id}' ({len(gdf)} units), using "
              f"{planner_result['case']} wide run.")

        ward_results = []
        for i, row in gdf.iterrows():
            ward_id, ward_name = row["gid"], row["name"]
            print(f"  Ward {ward_id} ({ward_name})...")
            ward_mask = _rasterize_ward_mask(row.geometry, raster_info)
            ward_results.append(
                compute_ward_landcover_screening(
                    ward_id, ward_name, ward_mask,
                    landcover_map_full, waterway_dist_map_full, wide_result,
                )
            )

    output_payload = {
        "boundary_layer_id": boundary_layer_id,
        "generated_at": datetime.now().isoformat(),
        "wide_run_case": planner_result.get("case"),
        "wide_run_status": planner_result["status"],
        "wards": ward_results,
    }

    with open(output, "w") as f:
        json.dump(output_payload, f, indent=2, default=_json_safe)

    n_available = sum(
        1 for w in ward_results if w.get("pluvial", {}).get("status") != "not_calculated"
    )
    print(f"Phase 12B complete: {n_available}/{len(ward_results)} wards "
          f"with usable pluvial/waterlogging screening. Saved: {output}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--boundary-layer-id", required=True)
    parser.add_argument("--storage-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--wide-run-output-dir", default="data/pipeline_runs")
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()

    run_ward_landcover_screening(
        args.boundary_layer_id, args.storage_dir, args.output,
        args.wide_run_output_dir, args.force_refresh,
    )