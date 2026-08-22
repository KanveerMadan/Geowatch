"""
Phase 11: Administrative Boundary Ingestion.

SCOPE, per the locked project methodology (see docs/risk_methodology.md
if/when written) -- this module does ONLY the following:
    - parse a GeoJSON boundary file
    - validate its geometry, IDs, and CRS
    - store the FULL, UNCLIPPED source geometries exactly as sourced
    - record a real provenance manifest (source, license, version, hash)
    - return a boundary_layer_id

This module deliberately does NOT do any of the following -- they
belong to later, separately-gated phases:
    - zonal statistics (Phase 12)
    - ward/village-level exposure, hazard, or vulnerability
    - percentiles or portfolio ranking (Phase 13)
    - contextual risk scoring (Phase 14)
    - AOI-clipped boundary geometry as the stored source of truth --
      clipping is always a downstream analysis artifact, computed
      later against the full stored boundary, never stored as if it
      were the boundary itself
    - automatic AOI expansion to match a ward/unit's full extent

GeoJSON only for v1 -- no Shapefile/KML/GPKG/WFS support. If a future
session adds another format, do it as a deliberate, separate decision,
not silently inside this module.
"""

import os
import json
import hashlib
from datetime import datetime, timezone

import geopandas as gpd
from shapely.validation import explain_validity


def _sha256_of_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_boundary_geometries(gdf: "gpd.GeoDataFrame", unit_id_field: str,
                                  unit_name_field: str) -> dict:
    """
    Run the real validation checks required before any boundary layer
    can be trusted, per the locked methodology: valid polygons, unique
    IDs, no self-intersections, no inter-unit overlaps, known CRS.

    This does NOT check coverage against any particular AOI -- that is
    an analysis-time question (see module docstring), not a property
    of the boundary layer itself.

    Returns a dict of real, checked results -- never a rubber-stamped
    "passed" without actually running the check.
    """
    result = {
        "feature_count": len(gdf),
        "crs": str(gdf.crs) if gdf.crs else None,
        "geometry_types": sorted(set(gdf.geometry.geom_type)),
        "unit_id_field": unit_id_field,
        "unit_name_field": unit_name_field,
    }

    # Field existence -- fail loudly, not silently, if the caller's
    # claimed ID/name fields don't actually exist in this file.
    missing_fields = [f for f in (unit_id_field, unit_name_field) if f not in gdf.columns]
    if missing_fields:
        result["status"] = "invalid"
        result["error"] = f"Declared field(s) not found in file: {missing_fields}. " \
                           f"Actual columns: {list(gdf.columns)}"
        return result

    # Geometry validity
    invalid_mask = ~gdf.geometry.is_valid
    invalid_rows = gdf[invalid_mask]
    result["invalid_geometry_count"] = int(invalid_mask.sum())
    result["invalid_geometry_details"] = [
        {"unit_id": row[unit_id_field], "reason": explain_validity(row.geometry)}
        for _, row in invalid_rows.iterrows()
    ]

    # Unique IDs / names
    result["duplicate_unit_id_count"] = int(len(gdf) - gdf[unit_id_field].nunique())
    result["duplicate_unit_name_count"] = int(len(gdf) - gdf[unit_name_field].nunique())

    # Null/missing IDs or names
    result["null_unit_id_count"] = int(gdf[unit_id_field].isna().sum())
    result["null_unit_name_count"] = int(gdf[unit_name_field].isna().sum())

    # Self-intersection is captured by is_valid above (a self-intersecting
    # ring is invalid geometry) -- reported here explicitly for clarity
    # rather than as a separate pass, since re-deriving it independently
    # would just duplicate is_valid's own check.
    result["self_intersection_check"] = (
        "passed" if result["invalid_geometry_count"] == 0
        else "failed -- see invalid_geometry_details"
    )

    # Inter-unit overlap check -- wards/units should not overlap each
    # other. Only run if geometry is otherwise valid, since overlap
    # area on invalid geometry is not meaningful.
    overlaps = []
    if result["invalid_geometry_count"] == 0:
        sindex = gdf.sindex
        checked_pairs = set()
        for i, row_a in gdf.iterrows():
            candidate_idxs = list(sindex.intersection(row_a.geometry.bounds))
            for j in candidate_idxs:
                if j <= i:
                    continue
                pair = (i, j)
                if pair in checked_pairs:
                    continue
                checked_pairs.add(pair)
                row_b = gdf.iloc[j]
                if row_a.geometry.intersects(row_b.geometry):
                    inter = row_a.geometry.intersection(row_b.geometry)
                    if inter.area > 1e-12:
                        overlaps.append({
                            "unit_a": row_a[unit_id_field],
                            "unit_b": row_b[unit_id_field],
                            "overlap_area_deg2": inter.area,
                        })
    result["overlapping_unit_pairs"] = overlaps
    result["overlap_check"] = "passed" if len(overlaps) == 0 else f"failed -- {len(overlaps)} overlapping pairs"

    # CRS check -- must be a real, known CRS. We require it be
    # equivalent to EPSG:4326 (matches every other lon/lat geometry
    # used elsewhere in this project) rather than silently reprojecting.
    is_4326 = False
    if gdf.crs is not None:
        try:
            is_4326 = gdf.crs.to_epsg() == 4326
        except Exception:
            is_4326 = False
    result["crs_is_epsg4326"] = is_4326

    result["status"] = "valid" if (
        result["invalid_geometry_count"] == 0
        and result["duplicate_unit_id_count"] == 0
        and result["null_unit_id_count"] == 0
        and len(overlaps) == 0
        and is_4326
    ) else "invalid"

    return result


def ingest_boundary_layer(source_path: str, manifest: dict,
                           storage_dir: str = "data/boundaries") -> dict:
    """
    Ingest a boundary GeoJSON file: validate it, store the full
    unclipped source geometry, and write a provenance manifest.

    Args:
        source_path: path to a local GeoJSON file (already downloaded
            -- this function does not fetch URLs itself, keeping
            network access and ingestion logic separate).
        manifest: a dict matching (at minimum) the shape of entries in
            configs.boundary_constants.KNOWN_BOUNDARY_SOURCES --
            boundary_layer_id, name, source{}, unit_type, admin_level,
            unit_id_field, unit_name_field. Pass a registry entry
            directly for a known source, or a hand-built dict for a
            new user-uploaded layer.
        storage_dir: where the validated boundary + manifest are saved.

    Returns:
        dict with status, boundary_layer_id, validation results, and
        the path the boundary was stored at. Does NOT proceed to save
        anything if validation fails -- an invalid boundary layer is
        never silently stored as if it were usable.
    """
    boundary_layer_id = manifest["boundary_layer_id"]
    unit_id_field = manifest["unit_id_field"]
    unit_name_field = manifest["unit_name_field"]

    if not os.path.exists(source_path):
        return {
            "status": "failed",
            "boundary_layer_id": boundary_layer_id,
            "error": f"Source file not found: {source_path}",
        }

    try:
        gdf = gpd.read_file(source_path)
    except Exception as e:
        return {
            "status": "failed",
            "boundary_layer_id": boundary_layer_id,
            "error": f"Could not parse as GeoJSON: {e}",
        }

    validation = validate_boundary_geometries(gdf, unit_id_field, unit_name_field)

    if validation["status"] != "valid":
        return {
            "status": "failed",
            "boundary_layer_id": boundary_layer_id,
            "error": "Boundary layer failed validation -- not stored.",
            "validation": validation,
        }

    # Real file hash, computed now -- not trusted blindly from the
    # manifest, so a stale or wrong hash in configs.boundary_constants
    # is caught rather than propagated.
    actual_hash = _sha256_of_file(source_path)
    declared_hash = manifest.get("file_sha256")
    hash_match = (declared_hash is None) or (actual_hash == declared_hash)

    out_dir = os.path.join(storage_dir, boundary_layer_id)
    os.makedirs(out_dir, exist_ok=True)
    boundary_out_path = os.path.join(out_dir, "boundary.geojson")

    # Store the FULL source geometry exactly as validated -- never a
    # clipped or otherwise modified version. Clipping against any
    # particular AOI happens later, at analysis time, against this
    # stored full layer (see module docstring).
    gdf.to_file(boundary_out_path, driver="GeoJSON")

    manifest_out = {
        "boundary_layer_id": boundary_layer_id,
        "name": manifest.get("name"),
        "source": manifest.get("source", {}),
        "unit_type": manifest.get("unit_type"),
        "admin_level": manifest.get("admin_level"),
        "unit_id_field": unit_id_field,
        "unit_name_field": unit_name_field,
        "feature_count": validation["feature_count"],
        "geometry_types": validation["geometry_types"],
        "crs": validation["crs"],
        "file_sha256": actual_hash,
        "file_sha256_matches_registry": hash_match,
        "validation": validation,
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "boundary_file_path": boundary_out_path,
    }

    manifest_out_path = os.path.join(out_dir, "manifest.json")
    with open(manifest_out_path, "w") as f:
        json.dump(manifest_out, f, indent=2, default=str)

    print(f"Boundary layer ingested: {boundary_layer_id} "
          f"({validation['feature_count']} units, status=valid)")
    if not hash_match:
        print(f"WARNING: file hash does not match the registry's recorded "
              f"hash for {boundary_layer_id} -- the source file may have "
              f"changed since it was last verified. Re-verify before trusting "
              f"this ingestion.")

    return {
        "status": "available",
        "boundary_layer_id": boundary_layer_id,
        "manifest_path": manifest_out_path,
        "boundary_file_path": boundary_out_path,
        "validation": validation,
        "file_sha256_matches_registry": hash_match,
    }


def check_aoi_coverage(boundary_layer_id: str, west: float, south: float,
                        east: float, north: float,
                        storage_dir: str = "data/boundaries") -> dict:
    """
    Read-only diagnostic: which units in a stored boundary layer
    intersect a given AOI, and by how much. This is NOT zonal statistics
    and does NOT decide partial-vs-whole handling (that is Phase 12's
    job) -- it only reports the two distinct coverage percentages the
    locked methodology requires, so this information is available
    up front rather than discovered by accident:

        aoi_coverage_pct_of_unit: how much of the unit's total area
            falls inside the AOI (answers "how much of the ward would
            be analyzed if we clipped to this AOI").
        unit_contribution_pct_of_aoi: how much of the AOI's total area
            falls inside this unit (answers "how much of the AOI does
            this ward account for").
    """
    manifest_path = os.path.join(storage_dir, boundary_layer_id, "manifest.json")
    boundary_path = os.path.join(storage_dir, boundary_layer_id, "boundary.geojson")

    if not os.path.exists(boundary_path):
        return {"status": "unavailable", "error": f"No ingested boundary layer found for '{boundary_layer_id}'."}

    with open(manifest_path) as f:
        manifest = json.load(f)
    unit_id_field = manifest["unit_id_field"]
    unit_name_field = manifest["unit_name_field"]

    gdf = gpd.read_file(boundary_path)

    from shapely.geometry import box
    aoi_geom = box(west, south, east, north)
    aoi_area = aoi_geom.area

    intersecting = gdf[gdf.geometry.intersects(aoi_geom)]
    units = []
    for _, row in intersecting.iterrows():
        inter_area = row.geometry.intersection(aoi_geom).area
        unit_area = row.geometry.area
        units.append({
            "unit_id": row[unit_id_field],
            "unit_name": row[unit_name_field],
            "aoi_coverage_pct_of_unit": round(inter_area / unit_area * 100, 2) if unit_area > 0 else None,
            "unit_contribution_pct_of_aoi": round(inter_area / aoi_area * 100, 2) if aoi_area > 0 else None,
            "fully_contained_in_aoi": bool(inter_area >= unit_area * 0.999),
        })

    return {
        "status": "available",
        "boundary_layer_id": boundary_layer_id,
        "aoi": {"west": west, "south": south, "east": east, "north": north},
        "intersecting_unit_count": len(units),
        "units": units,
        "note": "This is a coverage diagnostic only -- no exposure, hazard, "
                "or risk metrics are computed here. See Phase 12 (zonal "
                "statistics) for that, once it exists.",
    }