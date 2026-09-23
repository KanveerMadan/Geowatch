import os
import json
import argparse
from datetime import datetime, date, timedelta


from ingestion.gee_client import initialize_gee
from ingestion.sentinel2 import aoi_from_bbox, get_sentinel2_median_composite, get_latest_image
from ingestion.tiler import export_image_local, generate_rgb_preview_tiles
from ingestion.segmentation import load_sam, segment_tile, encode_mask_rle
from perception.applicability import compute_applicability, finalize_applicability
from perception.applicability_gate import annotate as annotate_applicability
from configs.palette import palette_for_result
from perception.hydrological_surfaces import compute_hydrological_surfaces
from ingestion.rainfall import get_rainfall_climatology
from susceptibility.pluvial import compute_pluvial_susceptibility, save_pluvial_susceptibility_output
from ingestion.hydrology import get_merit_hand_context, get_fabdem_elevation_stats
from susceptibility.fluvial import compute_fluvial_susceptibility
from ingestion.coastal import get_coastline_context
from susceptibility.coastal import compute_coastal_susceptibility
from ingestion.hydrology import get_slope_stats
from susceptibility.flash_flood import compute_flash_flood_susceptibility
from susceptibility.waterlogging import compute_waterlogging_susceptibility
from ingestion.inundation import get_permanent_water_context, get_sentinel1_change_context
from perception.observed_inundation import compute_observed_inundation
from ingestion.event_hazard import get_event_rainfall, get_discharge_proxy
from susceptibility.event_hazard import (
    compute_pluvial_event_hazard, compute_fluvial_event_hazard, compute_coastal_event_hazard,
)
from ingestion.exposure_sources import (
    get_population_context, get_builtup_reference, get_osm_road_length, get_osm_facilities,
)
from exposure.compute import EvidenceLayer, compute_exposure_for_layer
from risk.compute import compute_risk
from ingestion.vulnerability_sources import (
    get_country_iso3_for_aoi, get_inform_vulnerability_context,
)
from ingestion.osm_dem import (
    get_osm_features, get_elevation_stats,
    compute_relative_elevation_proxy,
    compute_road_distance_map, compute_waterway_distance_map, compute_road_access_score,
    apply_osm_vector_labels,
)
from ingestion.inference import (
    load_production_model, load_caat_thresholds,
    run_inference, save_landcover_outputs,
    build_segments_with_landcover, compute_area_stats, get_device,
)

import numpy as np
import ee


# ── Production model artifact paths — fixed locations, see Section 8a ──
PRODUCTION_MODEL_PATH = "models/production/geowatch_production_model.pth"
CAAT_THRESHOLDS_PATH = "models/production/caat_thresholds.json"




def _apply_osm_labels_to_segments(segments: list, osm_features: dict,
                                   west: float, south: float, east: float, north: float,
                                   tile_width: int, tile_height: int) -> list:
    """
    Compatibility shim for apply_osm_vector_labels().

    That function was written against Path A's segment schema — it reads
    and writes seg["category"] directly (see osm_dem.py: OVERRIDABLE =
    {"unknown", "unpaved_dirt_road", "open_drainage_channel", "open_waste"},
    and every branch does seg.get("category") / seg["category"] = ...).

    Path B's segments use "dominant_landcover_category" instead. Rather
    than editing osm_dem.py's internals (which risks touching working,
    unrelated OSM-fetch/HAND/road-distance code), this shim temporarily
    aliases the field, runs the existing function unmodified, then maps
    the result back onto the new field name.

    "unknown" segments here means Path B's CAAT-thresholded UNKNOWN_INDEX
    result — build_segments_with_landcover() already resolves that to the
    literal string "unknown" for exactly this reason (see inference.py).

    label_source / osm_feature_type are real, useful provenance info
    (distinguishes "the model said this" vs "OSM proximity said this") —
    kept on the final segment dict as a deliberate, explicit addition
    beyond the original schema draft, not a leftover Path A field.
    """
    for seg in segments:
        seg["category"] = seg.pop("dominant_landcover_category")

    segments = apply_osm_vector_labels(
        segments, osm_features,
        west, south, east, north,
        tile_width, tile_height,
    )

    for seg in segments:
        seg["dominant_landcover_category"] = seg.pop("category")

    return segments


def run_pipeline(
    west: float,
    south: float,
    east: float,
    north: float,
    start_date: str = None,   # None = use latest imagery automatically
    end_date: str = None,
    cloud_cover_threshold: int = 20,
    aoi_label: str = "aoi",
    output_dir: str = "data/pipeline_runs",
) -> dict:
    """
    Full Phase 1 perception pipeline — single entry point.
    Takes an AOI bounding box + optional date range, returns structured JSON.

    If start_date and end_date are None, automatically fetches the most recent
    90-day cloud-free composite (used by the background scheduler).

    result.json contract (SCHEMA v2.0 — do not change without updating
    all consumers: App.jsx, any other result.json readers):
        schema_version, run_id, aoi, date_range, status,
        imagery, observation_quality, tile_dimensions,
        total_tiles, landcover, segments, summary, elevation,
        relative_elevation_proxy, flood_assessment, osm_context

    "landcover" (NEW) is now the primary classification output — a
    per-pixel map, not tile-level or per-segment ML scores. "segments"
    is now a slimmed convenience layer for the frontend's clickable
    spatial units (dominant_landcover_category / landcover_purity_pct /
    road_access_score only) — it is a lookup into "landcover", not a
    second source of truth. See ingestion/inference.py for the model
    that produces "landcover".
    """
    run_id = f"{aoi_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = os.path.join(output_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"GeoWatch Pipeline Run: {run_id}")
    print(f"AOI: ({west}, {south}) to ({east}, {north})")

    # ── Resolve date range ──
    if start_date and end_date:
        date_range_used = {"start": start_date, "end": end_date, "mode": "manual"}
        print(f"Date range: {start_date} to {end_date}")
    else:
        end_auto = date.today().isoformat()
        start_auto = (date.today() - timedelta(days=90)).isoformat()
        date_range_used = {"start": start_auto, "end": end_auto, "mode": "latest_auto"}
        print(f"Date range: auto (latest 90 days: {start_auto} → {end_auto})")

    print(f"{'='*60}\n")

    result = {
        "run_id": run_id,
        "aoi": {"west": west, "south": south, "east": east, "north": north},
        "date_range": date_range_used,
        "status": "running",
    }

    # ── Step 1: Sentinel-2 ingestion ──
    print("[1/7] Sentinel-2 ingestion...")
    initialize_gee()
    aoi = aoi_from_bbox(west, south, east, north)

    if date_range_used["mode"] == "manual":
        s2_start, s2_end = start_date, end_date
    else:
        s2_end = date.today().isoformat()
        s2_start = (date.today() - timedelta(days=90)).isoformat()

    s2_bundle = get_sentinel2_median_composite(aoi, s2_start, s2_end, cloud_cover_threshold)
    image = s2_bundle["image"]
    imagery_provenance = s2_bundle["provenance"]
    observation_quality = s2_bundle["observation_quality"]

    print(f"Composite: {imagery_provenance['source_image_count']} source images, "
          f"{imagery_provenance['requested_period']['start']} to "
          f"{imagery_provenance['requested_period']['end']}")
    print(f"Observation quality: valid={observation_quality.get('valid_observation_pct')}%, "
          f"cloud={observation_quality.get('cloud_pct')}%, "
          f"shadow={observation_quality.get('cloud_shadow_pct')}%")

    result["imagery"] = imagery_provenance
    result["observation_quality"] = observation_quality
    result["imagery_acquisition_date"] = "deprecated_see_imagery_block"

    # ── Step 2: Download + tile ──
    print("\n[2/7] Downloading and tiling imagery...")
    raw_path = os.path.join(run_dir, "raw.tif")
    export_image_local(image=image, aoi=aoi, output_path=raw_path, scale=10)

    tile_dir = os.path.join(run_dir, "tiles")
    tiles, raster_info = generate_rgb_preview_tiles(image_path=raw_path, output_dir=tile_dir)

    if not tiles:
        result["status"] = "failed"
        result["error"] = "No tiles generated — AOI may be too small or imagery unavailable."
        return result

    full_width = raster_info["width"]
    full_height = raster_info["height"]
    print(f"Full AOI raster: {full_width}x{full_height}px across {len(tiles)} tile(s).")
    # NOTE (Phase 2): the old hard "exactly one tile" guard is REMOVED here —
    # this whole section now loops over every tile and mosaics results into
    # a full-AOI canvas. Single-tile AOIs (e.g. canonical Dharavi) go through
    # this exact same loop with col_off=row_off=0 and should produce
    # identical output to before. Multi-tile AOIs are UNVERIFIED until
    # tested against a real >1-tile AOI — do not trust this path in
    # production for large AOIs until that test has actually been run.

    # ── Step 3: OSM features (moved up — distance maps now need to be
    # built ONCE against the full AOI raster, not per-tile) ──
    print("\n[3/7] Fetching OSM features...")
    osm_dir = os.path.join(run_dir, "osm")
    osm_features = get_osm_features(west, south, east, north, output_dir=osm_dir)

    roads_gdf = osm_features.get("roads")
    osm_available = roads_gdf is not None

    if osm_available:
        print("Building full-AOI road distance map...")
        full_dist_map = compute_road_distance_map(
            roads_gdf, west, south, east, north, full_width, full_height
        )
        print("Road distance map built.")
    else:
        full_dist_map = None

    waterways_gdf = osm_features.get("waterways")
    if waterways_gdf is not None:
        print("Building full-AOI waterway distance map...")
        full_waterway_dist_map = compute_waterway_distance_map(
            waterways_gdf, west, south, east, north, full_width, full_height
        )
        print("Waterway distance map built.")
    else:
        full_waterway_dist_map = None

    # ── Step 4: relative-elevation proxy (unchanged, AOI-wide already) ──
    print("\n[4/7] Computing relative-elevation proxy...")
    relative_elevation = compute_relative_elevation_proxy(west, south, east, north)
    print("Computing fluvial HAND context (MERIT Hydro)...")
    hand_context = get_merit_hand_context(west, south, east, north)
    print("Computing bare-earth elevation (FABDEM)...")
    fabdem_elevation = get_fabdem_elevation_stats(west, south, east, north)
    elevation = get_elevation_stats(west, south, east, north, output_dir=osm_dir)
    print("Fetching rainfall climatology (CHIRPS)...")
    rainfall_climatology = get_rainfall_climatology(aoi)
    print("Computing coastline context (GEE Global Shoreline Dataset)...")
    coastal_context = get_coastline_context(west, south, east, north)
    print("Computing terrain slope (Phase 7)...")
    slope_context = get_slope_stats(west, south, east, north)

    # ── Step 5/6: SAM segmentation + per-pixel inference, PER TILE,
    # mosaicked into full-AOI canvases ──
    print("\n[5/7] Running SAM segmentation + per-pixel inference per tile...")

    device = get_device()
    model, categories, num_classes = load_production_model(PRODUCTION_MODEL_PATH, device=device)
    # C10 / item 45: the checkpoint path is passed so the loader can PROVE these
    # thresholds were computed for this model. Without it the loader warns and
    # skips, which is the unvalidated load C10 described.
    caat_thresholds = load_caat_thresholds(
        CAAT_THRESHOLDS_PATH, categories, checkpoint_path=PRODUCTION_MODEL_PATH
    )
    mask_generator = load_sam("models/sam/sam_vit_b.pth")

    landcover_map_full = np.full((full_height, full_width), 255, dtype=np.uint8)  # UNKNOWN_INDEX
    confidence_map_full = np.zeros((full_height, full_width), dtype=np.float32)
    ambiguity_map_full = np.zeros((full_height, full_width), dtype=np.uint8)

    all_segments = []
    all_masks_serializable = []
    next_segment_id = 0
    next_mask_id = 0

    for tile_idx, tile in enumerate(tiles):
        tile_path = tile["path"]
        col_off, row_off = tile["col_off"], tile["row_off"]
        t_w, t_h = tile["width"], tile["height"]

        print(f"  Tile {tile_idx + 1}/{len(tiles)}: {os.path.basename(tile_path)} "
              f"(offset col={col_off}, row={row_off}, size={t_w}x{t_h})")

        # Crop the full-AOI distance maps down to this tile's window —
        # NOT recomputed per tile, just sliced, so proximity values are
        # identical to what a single full-raster computation would give.
        tile_dist_map = (
            full_dist_map[row_off:row_off + t_h, col_off:col_off + t_w]
            if full_dist_map is not None else None
        )
        tile_waterway_dist_map = (
            full_waterway_dist_map[row_off:row_off + t_h, col_off:col_off + t_w]
            if full_waterway_dist_map is not None else None
        )

        masks = segment_tile(tile_path, mask_generator)

        inference_result = run_inference(
            tile_path, model, categories, caat_thresholds, device=device,
            road_dist_map=tile_dist_map,
            waterway_dist_map=tile_waterway_dist_map,
        )

        # Place this tile's per-pixel outputs into the full mosaic canvas.
        # Tiles are non-overlapping (confirmed in tiler.py's plain
        # range(0, height, tile_size) loop) so this is a straight
        # placement, no blending needed.
        landcover_map_full[row_off:row_off + t_h, col_off:col_off + t_w] = inference_result["landcover_map"]
        confidence_map_full[row_off:row_off + t_h, col_off:col_off + t_w] = inference_result["confidence_map"]
        ambiguity_map_full[row_off:row_off + t_h, col_off:col_off + t_w] = inference_result["ambiguity_map"]

        # Road access scores: computed against THIS tile's cropped distance
        # map using each mask's tile-local bbox — same math as before,
        # just scoped per tile instead of assuming one tile = whole AOI.
        road_access_scores = {}
        for i, m in enumerate(masks):
            w, h = m["bbox"][2], m["bbox"][3]
            if w < 8 or h < 8:
                continue
            road_access_scores[i] = compute_road_access_score(
                m["bbox"], roads_gdf,
                dist_map=tile_dist_map,
            )

        tile_segments = build_segments_with_landcover(
            masks, inference_result["landcover_map"], categories,
            road_access_scores=road_access_scores,
            ambiguity_map=inference_result["ambiguity_map"],
        )

        # Offset bboxes to GLOBAL (full-raster) pixel space and assign
        # globally-unique segment_ids, so the frontend's existing
        # tile_dimensions-based lon/lat projection (now set to the FULL
        # raster's width/height below) stays correct across tile counts.
        #
        # This applies to SEGMENT GEOMETRY ONLY. The base image does NOT
        # come along: there is no full-AOI RGB raster on disk, only the
        # per-tile PNGs, so a viewer that draws one tile under full-raster
        # coordinates misplaces everything outside it. That mismatch was
        # C13, and item 46 resolved it by REMOVING the `primary_tile`
        # field rather than by manufacturing a basemap -- so do not
        # reintroduce a single-tile base-image pointer here.
        for seg in tile_segments:
            x, y, w, h = seg["bbox"]
            seg["bbox"] = [x + col_off, y + row_off, w, h]
            seg["segment_id"] = next_segment_id
            seg["source_tile"] = tile_idx
            next_segment_id += 1
            all_segments.append(seg)

        # Save ALL raw SAM masks (unfiltered by the w/h<8 rule that
        # build_segments_with_landcover applies) — same as the old
        # single-tile masks.json behavior, just extended across tiles.
        # tile_col_off/tile_row_off are stored explicitly so a future
        # consumer decoding mask_rle (which stays TILE-LOCAL in shape)
        # knows how to place it back into full-AOI space — bbox alone
        # is global, but the decoded mask array itself is not.
        for m in masks:
            entry = {
                "segment_id": next_mask_id,
                "source_tile": tile_idx,
                "tile_col_off": col_off,
                "tile_row_off": row_off,
                "area": int(m["area"]),
                "bbox": [m["bbox"][0] + col_off, m["bbox"][1] + row_off, m["bbox"][2], m["bbox"][3]],
                "predicted_iou": float(m["predicted_iou"]),
                "stability_score": float(m["stability_score"]),
            }
            if "segmentation" in m and isinstance(m["segmentation"], np.ndarray):
                entry["mask_rle"] = encode_mask_rle(m["segmentation"])
            all_masks_serializable.append(entry)
            next_mask_id += 1

    masks_output_path = os.path.join(run_dir, "masks.json")
    with open(masks_output_path, "w") as f:
        json.dump(all_masks_serializable, f, indent=2)
    print(f"Mask metadata + RLE masks saved: {masks_output_path} ({len(all_masks_serializable)} masks across {len(tiles)} tile(s))")

    # ── Phase 12B: persist landcover_map_full + waterway_dist_map_full +
    # raster_info so future wide-AOI runs can be reused by
    # zonal/landcover_screening.py's Case 1 planner instead of always
    # re-running SAM+inference. Without this, both arrays only ever
    # existed in this process's memory and were lost on exit.
    landcover_map_path = os.path.join(run_dir, "landcover_map_full.npy")
    np.save(landcover_map_path, landcover_map_full)

    if full_waterway_dist_map is not None:
        waterway_dist_map_path = os.path.join(run_dir, "waterway_dist_map_full.npy")
        np.save(waterway_dist_map_path, full_waterway_dist_map)
    else:
        # No waterways in this AOI's OSM data -- explicit None on disk,
        # not a missing file, so a reuse check can tell "genuinely no
        # waterways here" apart from "this run predates the patch."
        waterway_dist_map_path = None

    raster_info_path = os.path.join(run_dir, "raster_info.json")
    with open(raster_info_path, "w") as f:
        json.dump(raster_info, f)

    print(f"Saved landcover_map_full: {landcover_map_path}")
    print(f"Saved waterway_dist_map_full: {waterway_dist_map_path}")
    print(f"Saved raster_info: {raster_info_path}")

    segments = all_segments

    print("\nApplying OSM vector labels for unresolvable categories...")
    segments = _apply_osm_labels_to_segments(
        segments, osm_features,
        west, south, east, north,
        full_width, full_height,
    )

    # ── Full-AOI stats, computed ONCE on the mosaic — not per-tile ──
    stats = compute_area_stats(landcover_map_full, ambiguity_map_full, categories)
    inference_result = {
        "landcover_map": landcover_map_full,
        "confidence_map": confidence_map_full,
        "ambiguity_map": ambiguity_map_full,
        **stats,
    }
    landcover_paths = save_landcover_outputs(inference_result, categories, run_dir)

    # ── C14/C20 (build item 40): the gate runs BEFORE the thing it gates ──
    #
    # Previously hydrological_surfaces was computed first and applicability
    # second, which is backwards: hydrological_surfaces is a weighted sum of
    # the semantic model's own category_area_pct, and applicability is what
    # says whether that model can be trusted for this scene. Computing the
    # router after the thing it routes is 01_DIAGNOSIS.md §4 S2 exactly --
    # "designed as a router, wired as a report."
    #
    # compute_applicability() also read hydrological_surfaces, for one check
    # (does waterlogging have any usable input), so this is a real cycle rather
    # than a simple mis-ordering. It is broken in two stages; see
    # finalize_applicability(). Verified behaviour-preserving across all 192
    # input combinations before the reorder landed.
    applicability = compute_applicability(
        unknown_pct=inference_result["unknown_pct"],
        ambiguous_pct=inference_result["ambiguous_pct"],
        hand_context=hand_context,
        coastal_context=coastal_context,
        slope_context=slope_context,
        hydrological_surfaces=None,   # stage 2 resolves the one status needing it
    )

    hydrological_surfaces = compute_hydrological_surfaces(inference_result["category_area_pct"])
    # Surfaces are derived from the model applicability just judged, so they
    # carry that verdict rather than being presented as unconditional fact.
    annotate_applicability(hydrological_surfaces, applicability, "waterlogging")

    # Stage 2: resolve waterlogging, the only status that genuinely needed
    # hydrological_surfaces to exist.
    applicability = finalize_applicability(applicability, hydrological_surfaces)

    
    print("\nComputing pluvial susceptibility baseline...")
    pluvial_result = compute_pluvial_susceptibility(
        landcover_map=landcover_map_full,
        categories=categories,
        waterway_dist_map=full_waterway_dist_map,
        relative_elevation_score=relative_elevation.get("score"),
        rainfall_mean_annual_mm=rainfall_climatology.get("mean_annual_mm"),
        applicability=applicability,
    )
    pluvial_map_filename = None
    if pluvial_result.get("susceptibility_map") is not None:
        pluvial_map_filename = save_pluvial_susceptibility_output(
            pluvial_result["susceptibility_map"], run_dir
        )
    pluvial_result_serializable = {k: v for k, v in pluvial_result.items() if k != "susceptibility_map"}
    if pluvial_map_filename:
        pluvial_result_serializable["map_path"] = pluvial_map_filename

    # C14/C20: every consumer now receives the gate. compute-and-flag, not
    # refuse-to-compute -- each still returns its real value, with the trust
    # verdict attached rather than the value withheld.
    fluvial_result = compute_fluvial_susceptibility(hand_context, applicability=applicability)
    coastal_result = compute_coastal_susceptibility(coastal_context, fabdem_elevation, applicability=applicability)
    flash_flood_result = compute_flash_flood_susceptibility(slope_context, hand_context, rainfall_climatology, applicability=applicability)
    waterlogging_result = compute_waterlogging_susceptibility(hand_context, hydrological_surfaces, rainfall_climatology, applicability=applicability)
    susceptibility_block = {
        "pluvial": pluvial_result_serializable,
        "fluvial": fluvial_result,
        "coastal": coastal_result,
        "flash_flood": flash_flood_result,
        "waterlogging": waterlogging_result,
    }

# ── Phase 10B: vulnerability context (INFORM Risk Index) — resolved
    # BEFORE the exposure/risk loop, since risk_layers needs it inside
    # the loop. Previously this was computed AFTER the loop, which meant
    # vulnerability_block didn't exist yet when the loop referenced it —
    # a NameError on every run. ──
    print("\nComputing vulnerability context (Phase 10B — INFORM Risk)...")
    country_context = get_country_iso3_for_aoi(west, south, east, north)
    vulnerability_block = get_inform_vulnerability_context(country_context.get("iso3"))
    vulnerability_block["country_lookup"] = country_context

    # ── Phase 10A: exposure, computed SEPARATELY per evidence layer.
    # Never auto-merged into a "highest available hazard" figure -- see
    # exposure/compute.py module docstring for why. ──
    print("\nComputing exposure (Phase 10A)...")
    aoi_geometry = ee.Geometry.Rectangle([west, south, east, north])
    # Uses the same dynamically-resolved ISO3 as vulnerability, instead
    # of a hardcoded "IND" -- keeps population and vulnerability from
    # silently disagreeing on which country's data they're using for any
    # AOI outside India.
    population_context = get_population_context(
        west, south, east, north, country_iso3=country_context.get("iso3")
    )
    builtup_reference = get_builtup_reference(west, south, east, north)
    road_length_context = get_osm_road_length(roads_gdf)
    facilities_context = get_osm_facilities(west, south, east, north, output_dir=osm_dir)

    landcover_builtup_pct = round(
        inference_result["category_area_pct"].get("dense_informal_roofing", 0)
        + inference_result["category_area_pct"].get("sparse_informal_roofing", 0)
        + inference_result["category_area_pct"].get("paved_road", 0),
        3,
    )

    exposure_layers = {}
    risk_layers = {}
    for layer_key, susc_result in susceptibility_block.items():
        evidence_layer = EvidenceLayer(
            layer_id=f"{layer_key}_susceptibility",
            label=f"{layer_key.replace('_', ' ').title()} susceptibility",
            evidence_type="long_term_screening",
            status=susc_result.get("status", "not_calculated"),
            mask_source="aoi_wide_scalar",
            threshold_or_score=susc_result.get("aoi_mean_score"),
            temporal_scope="static/contextual",
            limitations=[
                f"Exposure computed against the FULL AOI, not a spatial "
                f"hazard footprint -- {layer_key} susceptibility is an "
                f"AOI-wide scalar (spatial=false), not a per-pixel raster.",
                "This is not event-specific exposure and does not indicate "
                "current flooding.",
            ],
        )
        # Single call per layer -- the previous version called
        # compute_exposure_for_layer()/compute_risk() twice per layer
        # (identical args except the second compute_risk() silently
        # overwrote the first with vulnerability=None), doubling GEE
        # calls for no reason and discarding the real vulnerability input.
        exposure_result = compute_exposure_for_layer(
            evidence_layer, aoi_geometry,
            population_context=population_context,
            builtup_reference=builtup_reference,
            road_length_context=road_length_context,
            facilities_context=facilities_context,
            landcover_builtup_pct=landcover_builtup_pct,
            applicability=applicability,
        )
        exposure_layers[layer_key] = exposure_result
        risk_layers[layer_key] = compute_risk(
            hazard=susc_result, exposure=exposure_result, vulnerability=vulnerability_block,
        )

    exposure_block = {
        "status": "available",
        "by_evidence_layer": exposure_layers,
    }
    risk_block = {
        "status": "not_calculated",
        "reason": "Risk requires hazard, exposure, and vulnerability. Exposure "
                  "is available per evidence layer above; vulnerability has "
                  "not been calculated (see vulnerability block).",
        "by_evidence_layer": risk_layers,
    }
    tile_width, tile_height = full_width, full_height

    # ── Step 7: Assemble structured output (NEW SCHEMA) ──
    print("\n[7/7] Assembling structured output...")

    elev_available = elevation.get("status") == "available"
    proxy_available = relative_elevation.get("status") == "experimental"

    if not elev_available and not proxy_available:
        flood_assessment = {
            "status": "insufficient_evidence",
            "reason": "Both elevation sources unavailable.",
        }
    else:
        flood_assessment = {
            "status": "experimental_screening_only",
            "terrain_context": {
                "absolute_elevation": {
                    "status": elevation.get("status"),
                    "mean_m": elevation.get("mean_elevation_m"),
                    "below_10m_unvalidated": elevation.get("flood_risk_flag"),
                },
                "relative_elevation_proxy": {
                    "status": relative_elevation.get("status"),
                    "score": relative_elevation.get("score"),
                    "method": relative_elevation.get("method"),
                    "true_hand": False,
                    "dem_type": relative_elevation.get("dem_type"),
                },
            },
            "limitations": [
                "Relative elevation proxy is NOT true HAND -- measures AOI-relative "
                "elevation, not distance to drainage.",
                "Copernicus DEM GLO-30 is a DSM (includes building heights), not a DTM.",
                "No rainfall, river discharge, coastal, or event forcing data used.",
                "No temporal change detection -- single-snapshot only.",
                "Elevation sampled at only 25 points; may miss local variation.",
                "Thresholds (10m, 0.6) are unvalidated constants, not used to "
                "produce a binary flag in this schema version.",
            ],
        }

    training_cities = []
    loco_mean_miou = None
    loco_std_miou = None
    loco_n_folds = None
    try:
        import torch as _torch
        _ckpt = _torch.load(PRODUCTION_MODEL_PATH, map_location="cpu")
        training_cities = _ckpt.get("training_cities", [])
        loco_mean_miou = _ckpt.get("loco_mean_miou")
        loco_std_miou = _ckpt.get("loco_std_miou")
        loco_n_folds = _ckpt.get("loco_n_folds")
    except Exception as e:
        print(f"Could not re-read checkpoint provenance metadata for result.json: {e}")

    landcover_block = {
        "map_path": landcover_paths["map_path"],
        "confidence_map_path": landcover_paths["confidence_map_path"],
        "categories": categories,
        "unknown_index": 255,
        # C31 / build item 43: the palette travels WITH the result, so the
        # frontend has no colour map of its own to drift from. This is the
        # mechanism that makes the drift structurally impossible rather than
        # merely currently-absent -- changing a colour in configs/palette.py
        # changes the rendered legend with zero frontend edits.
        "palette": palette_for_result(),
        "category_area_pct": inference_result["category_area_pct"],
        "unknown_pct": inference_result["unknown_pct"],
        "ambiguous_pct": inference_result["ambiguous_pct"],
        "ambiguous_pct_by_pair": inference_result["ambiguous_pct_by_pair"],
        "model_provenance": {
            "architecture": "GeoWatchResNetSeg (ResNet50 SSL4EO-S12 MoCo + DeepLabV3+)",
            "training_cities": training_cities,
            "loco_mean_miou": loco_mean_miou,
            "loco_std_miou": loco_std_miou,
            "loco_n_folds": loco_n_folds,
        },
    }
   

    result.update({
        "schema_version": "2.0",
        "status": "complete",
        "tile_dimensions": {"width": tile_width, "height": tile_height},
        "total_tiles": len(tiles),
        "landcover": landcover_block,
        "applicability": applicability,
        "hydrological_surfaces": hydrological_surfaces,
        "susceptibility": susceptibility_block,
        "rainfall_climatology": rainfall_climatology,
        "segments": segments,
        "summary": {
            "total_segments": len(segments),
            "unknown_segments": sum(1 for s in segments if s["dominant_landcover_category"] == "unknown"),
            "dominant_category": max(
                inference_result["category_area_pct"].items(), key=lambda kv: kv[1]
            )[0] if inference_result["category_area_pct"] else "unknown",
            "standing_water_segment_count": sum(
                1 for s in segments
                if s["dominant_landcover_category"] in ("standing_water", "open_drainage_channel")
            ),
            "flood_risk_flag": None,
            "flood_risk_flag_basis": "deprecated_see_flood_assessment",
        },
        "elevation": elevation,
        "terrain_context": {
            "relative_elevation_proxy": relative_elevation,   # existing, Copernicus DSM
            "fabdem_bare_earth": fabdem_elevation,             # Phase 5
            "fluvial_hand_context": hand_context,              # Phase 5
            "coastal_context": coastal_context,                # Phase 6
        },
        "flood_assessment": flood_assessment,
        "exposure": exposure_block,
        "vulnerability": vulnerability_block,
        "risk": risk_block,
        "observed_inundation": {
            "status": "not_calculated",
            "reason": "This run used the stable land-cover pipeline (run_pipeline), "
                      "which does not include Sentinel-1/JRC observed-inundation "
                      "analysis. Use run_inundation_analysis() / POST "
                      "/api/analyze_inundation for that, with a matching event "
                      "window.",
        },
        "osm_context": {
            "osm_available": osm_available,
            "road_segments": len(roads_gdf) if roads_gdf is not None else 0,
            "waterway_features": (
                len(osm_features.get("waterways"))
                if osm_features.get("waterways") is not None else 0
            ),
            "road_access_scores_reliable": osm_available,
            "road_score_method": "distance_transform" if osm_available else "unavailable",
        },
    })

    output_path = os.path.join(run_dir, "result.json")
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    proxy_score = relative_elevation.get("score")
    proxy_str = f"{proxy_score:.3f}" if proxy_score is not None else "N/A (unavailable)"

    print(f"\n{'='*60}")
    print(f"Pipeline complete. Result saved: {output_path}")
    print(f"Imagery: {imagery_provenance['source_image_count']} source images, "
          f"{imagery_provenance['requested_period']['start']} to "
          f"{imagery_provenance['requested_period']['end']}")
    print(f"Date mode: {date_range_used['mode']}")
    print(f"Tile dimensions: {tile_width}x{tile_height}px")
    print(f"Dominant category: {result['summary']['dominant_category']}")
    print(f"Total segments: {result['summary']['total_segments']}")
    print(f"Unknown segments: {result['summary']['unknown_segments']}")
    print(f"Unknown pixels: {inference_result['unknown_pct']}%")
    print(f"Standing water segment count: {result['summary']['standing_water_segment_count']}")
    print(f"Relative-elevation proxy score: {proxy_str} (status={relative_elevation.get('status')})")
    print(f"Elevation status: {elevation.get('status')} | "
          f"Relative-elevation proxy status: {relative_elevation.get('status')}")
    print(f"Flood assessment status: {flood_assessment.get('status')}")
    print(f"Applicability: urban_landcover_model={applicability['urban_landcover_model']['status']}, pluvial={applicability['pluvial']['status']}")
    print(f"Hydrological surfaces: impervious={hydrological_surfaces['impervious_fraction_pct']}%, infiltration={hydrological_surfaces['infiltration_proxy_pct']}%")
    print(f"Rainfall climatology: {rainfall_climatology.get('mean_annual_mm')} mm/year (status={rainfall_climatology.get('status')})")
    print(f"Pluvial susceptibility: {pluvial_result.get('aoi_mean_class')} (score={pluvial_result.get('aoi_mean_score')}, status={pluvial_result.get('status')})")
    print(f"Fluvial susceptibility: {fluvial_result.get('aoi_mean_class')} (score={fluvial_result.get('aoi_mean_score')}, status={fluvial_result.get('status')})")
    print(f"Coastal susceptibility: {coastal_result.get('aoi_mean_class')} (score={coastal_result.get('aoi_mean_score')}, status={coastal_result.get('status')})")
    print(f"Coastline distance: {coastal_context.get('distance_km')}km (status={coastal_context.get('status')})")
    print(f"MERIT HAND: mean={hand_context.get('mean_hnd_m')}m, river_connected={hand_context.get('river_connectivity')} (status={hand_context.get('status')})")
    print(f"Flash-flood susceptibility: {flash_flood_result.get('aoi_mean_class')} (score={flash_flood_result.get('aoi_mean_score')}, status={flash_flood_result.get('status')})")
    print(f"Waterlogging susceptibility: {waterlogging_result.get('aoi_mean_class')} (score={waterlogging_result.get('aoi_mean_score')}, status={waterlogging_result.get('status')})")
    print(f"Terrain slope: mean={slope_context.get('mean_slope_deg')}deg (status={slope_context.get('status')})")
    print(f"FABDEM bare-earth elevation: mean={fabdem_elevation.get('mean_elevation_m')}m (status={fabdem_elevation.get('status')})")
    print(f"OSM available: {osm_available}")
    print(f"Road score method: {'distance_transform' if osm_available else 'unavailable'}")
    print(f"LOCO mean mIoU (model provenance): {loco_mean_miou} (+/- {loco_std_miou}, {loco_n_folds} folds)")
    print(f"Population context: status={population_context.get('status')}, "
          f"year={population_context.get('population_year')}")
    print(f"GHSL built-up reference: status={builtup_reference.get('status')} (UNVERIFIED asset ID)")
    print(f"OSM road length: {road_length_context.get('total_length_km')}km "
          f"(status={road_length_context.get('status')})")
    print(f"OSM facilities found: {facilities_context.get('status')} "
          f"({len(facilities_context.get('facilities', []))} facilities)")
    print(f"Vulnerability: {vulnerability_block['status']} "
          f"(country={country_context.get('country_name')}/{country_context.get('iso3')})")
    if vulnerability_block.get("status") == "available":
        print(f"  Vulnerability score: {vulnerability_block['dimensions']['vulnerability']['raw_score']}")
        print(f"  Lack of coping capacity: {vulnerability_block['dimensions']['lack_of_coping_capacity']['raw_score']}")
    print(f"Risk: {risk_block['status']} (fusion methodology not yet defined — see Gate E)")
    print(f"{'='*60}\n")
    

    return result


def run_inundation_analysis(
    west: float, south: float, east: float, north: float,
    pre_event_start: str, pre_event_end: str,
    event_start: str, event_end: str,
    aoi_label: str = "aoi",
    output_dir: str = "data/pipeline_runs",
    optical_standing_water_pct: float = None,
) -> dict:
    """
    Phase 8: standalone observed-inundation analysis -- SEPARATE from
    run_pipeline() (stable land-cover + susceptibility screening).
    Deliberately NOT merged into run_pipeline() or given a single
    overloaded date_range, per the master spec's explicit rule ("Do not
    overload one date range with multiple meanings").

    Does NOT re-run SAM segmentation or the land-cover classifier -- this
    is JRC + Sentinel-1 only. For a cross-check against the optical
    standing_water classification, run run_pipeline() separately over a
    matching period first and pass its
    landcover.category_area_pct.standing_water value in via
    optical_standing_water_pct.

    result schema (NEW, separate from run_pipeline()'s result.json):
        run_id, aoi, pre_event_period, event_period, status,
        jrc_context, sentinel1_context, observed_inundation
    """
    run_id = f"{aoi_label}_inundation_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = os.path.join(output_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"GeoWatch Observed-Inundation Run: {run_id}")
    print(f"AOI: ({west}, {south}) to ({east}, {north})")
    print(f"Pre-event: {pre_event_start} to {pre_event_end}")
    print(f"Event: {event_start} to {event_end}")
    print(f"{'='*60}\n")

    result = {
        "run_id": run_id,
        "aoi": {"west": west, "south": south, "east": east, "north": north},
        "pre_event_period": {"start": pre_event_start, "end": pre_event_end},
        "event_period": {"start": event_start, "end": event_end},
        "status": "running",
        "schema_version": "2.0",
    }

    print("[1/3] Fetching JRC Global Surface Water baseline...")
    jrc_context = get_permanent_water_context(west, south, east, north)

    print("\n[2/3] Fetching Sentinel-1 SAR change context...")
    s1_context = get_sentinel1_change_context(
        west, south, east, north,
        pre_event_start, pre_event_end,
        event_start, event_end,
        jrc_permanent_water_pct=jrc_context.get("permanent_water_pct"),
    )

    print("\n[3/3] Fusing observed-inundation result...")
    observed_inundation = compute_observed_inundation(
        jrc_context, s1_context, optical_standing_water_pct=optical_standing_water_pct
    )

    result.update({
        "status": "complete",
        "jrc_context": jrc_context,
        "sentinel1_context": s1_context,
        "observed_inundation": observed_inundation,
    })

    output_path = os.path.join(run_dir, "inundation_result.json")
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Inundation analysis complete. Result saved: {output_path}")
    print(f"Observed inundation status: {observed_inundation.get('status')}")
    print(f"{'='*60}\n")

    return result

def run_event_hazard_analysis(
    west: float, south: float, east: float, north: float,
    event_start: str, event_end: str,
    aoi_label: str = "aoi",
    output_dir: str = "data/pipeline_runs",
) -> dict:
    """
    Phase 9: event hazard -- conditions susceptibility (from a prior
    run_pipeline() call) on real event forcing. Requires a susceptibility
    result already computed over a matching or reasonably contemporaneous
    period -- pass it in explicitly rather than re-running the full
    land-cover pipeline here, keeping this function's cost proportional
    to what it actually adds (rainfall/discharge-proxy fetch + gating),
    not a full SAM+inference re-run.
    """
    run_id = f"{aoi_label}_eventhazard_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir = os.path.join(output_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"GeoWatch Event-Hazard Run: {run_id}")
    print(f"AOI: ({west}, {south}) to ({east}, {north})")
    print(f"Event: {event_start} to {event_end}")
    print(f"{'='*60}\n")

    initialize_gee()
    aoi = aoi_from_bbox(west, south, east, north)

    print("[1/2] Fetching event forcing data...")
    event_rainfall = get_event_rainfall(west, south, east, north, event_start, event_end)
    discharge_proxy = get_discharge_proxy(west, south, east, north, event_start, event_end)

    print("\n[2/2] Computing susceptibility baseline for gating...")
    relative_elevation = compute_relative_elevation_proxy(west, south, east, north)
    hand_context = get_merit_hand_context(west, south, east, north)
    rainfall_climatology = get_rainfall_climatology(aoi)

    fluvial_susceptibility = compute_fluvial_susceptibility(hand_context)
    coastal_context = get_coastline_context(west, south, east, north)
    fabdem_elevation = get_fabdem_elevation_stats(west, south, east, north)
    coastal_susceptibility = compute_coastal_susceptibility(coastal_context, fabdem_elevation)

    # NOTE: pluvial susceptibility needs a real landcover_map + waterway
    # distance map, which only exist from a full run_pipeline() call.
    # Passed as insufficient_evidence here since this standalone function
    # doesn't re-run segmentation/inference -- callers wanting pluvial
    # event hazard should compute it by calling
    # compute_pluvial_event_hazard() directly with a prior run_pipeline()
    # result's susceptibility.pluvial block.
    pluvial_stub = {"status": "insufficient_evidence",
                     "reason": "Requires a prior run_pipeline() landcover result -- "
                               "call compute_pluvial_event_hazard() directly with it."}

    pluvial_hazard = compute_pluvial_event_hazard(pluvial_stub, event_rainfall)
    fluvial_hazard = compute_fluvial_event_hazard(fluvial_susceptibility, discharge_proxy)
    coastal_hazard = compute_coastal_event_hazard(coastal_susceptibility)

    result = {
        "run_id": run_id,
        "aoi": {"west": west, "south": south, "east": east, "north": north},
        "event_period": {"start": event_start, "end": event_end},
        "status": "complete",
        "schema_version": "2.0",
        "event_forcing": {
            "rainfall": event_rainfall,
            "discharge_proxy": discharge_proxy,
        },
        "event_hazard": {
            "pluvial": pluvial_hazard,
            "fluvial": fluvial_hazard,
            "coastal": coastal_hazard,
        },
    }

    output_path = os.path.join(run_dir, "event_hazard_result.json")
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Event-hazard analysis complete. Result saved: {output_path}")
    print(f"Event rainfall: {event_rainfall.get('event_total_mm')}mm (status={event_rainfall.get('status')})")
    print(f"Discharge proxy (NOT real discharge): {discharge_proxy.get('catchment_rainfall_mm')}mm (status={discharge_proxy.get('status')})")
    print(f"Fluvial event hazard: {fluvial_hazard.get('aoi_mean_class')} (score={fluvial_hazard.get('aoi_mean_score')}, status={fluvial_hazard.get('status')})")
    print(f"Coastal event hazard: {coastal_hazard.get('status')}")
    print(f"{'='*60}\n")

    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GeoWatch Copilot — Phase 1 pipeline")
    parser.add_argument("--west",  type=float, required=True)
    parser.add_argument("--south", type=float, required=True)
    parser.add_argument("--east",  type=float, required=True)
    parser.add_argument("--north", type=float, required=True)
    parser.add_argument("--start", type=str, default=None,
                        help="Start date YYYY-MM-DD (omit for latest auto mode)")
    parser.add_argument("--end",   type=str, default=None,
                        help="End date YYYY-MM-DD (omit for latest auto mode)")
    parser.add_argument("--label", type=str, default="aoi", help="AOI label for run ID")
    parser.add_argument("--output-dir", type=str, default="data/pipeline_runs")
    parser.add_argument("--mode", type=str, default="landcover",
                        choices=["landcover", "inundation"],
                        help="landcover = existing full pipeline; inundation = "
                             "Phase 8 JRC+Sentinel-1 observed-inundation only")
    parser.add_argument("--pre-start", type=str, default=None,
                        help="Pre-event window start (--mode inundation only)")
    parser.add_argument("--pre-end", type=str, default=None,
                        help="Pre-event window end (--mode inundation only)")
    parser.add_argument("--event-start", type=str, default=None,
                        help="Event window start (--mode inundation only)")
    parser.add_argument("--event-end", type=str, default=None,
                        help="Event window end (--mode inundation only)")
    args = parser.parse_args()

    if args.mode == "inundation":
        if not all([args.pre_start, args.pre_end, args.event_start, args.event_end]):
            parser.error("--mode inundation requires --pre-start --pre-end "
                          "--event-start --event-end")
        run_inundation_analysis(
            west=args.west, south=args.south, east=args.east, north=args.north,
            pre_event_start=args.pre_start, pre_event_end=args.pre_end,
            event_start=args.event_start, event_end=args.event_end,
            aoi_label=args.label, output_dir=args.output_dir,
        )
    else:
        run_pipeline(
            west=args.west,
            south=args.south,
            east=args.east,
            north=args.north,
            start_date=args.start,
            end_date=args.end,
            aoi_label=args.label,
            output_dir=args.output_dir,
        )