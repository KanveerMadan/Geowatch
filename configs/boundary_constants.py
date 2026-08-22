"""
Phase 11: constants for administrative boundary ingestion.

This module is a REGISTRY of boundary sources that have been manually
checked and verified live (geometry validity, CRS, ID/name fields,
overlaps, license), the same discipline as every other data source in
this project (MERIT Hydro, FABDEM, WorldPop, the shoreline dataset).

Do NOT add a source to this registry without actually running it
through boundaries.ingestion.validate_boundary_geometries() first and
recording the real results below -- a source listed here without a
matching validation record is not to be trusted.

Boundary layers are NOT sourced from GEE by default (see Phase 11
architecture note) -- municipal ward/village boundaries are usually
absent from global GEE assets, inconsistent, or the wrong admin level.
The first-class path is a real, checked GeoJSON file, whether
user-uploaded or (as with the source below) a vetted open dataset.
"""

# ── Mumbai BMC wards (DataMeet India community) ──
# Live-verified 2026-08-06:
#   - FeatureCollection, CRS84 (= EPSG:4326)
#   - 24 features, geometry type MultiPolygon throughout
#   - properties: gid (int, unique), name (str, unique -- official BMC
#     ward code, e.g. "A", "G/N", "K/E" -- not a full ward name)
#   - 0 invalid geometries (shapely is_valid)
#   - 0 self-intersections
#   - 0 overlapping ward pairs
#   - license CC BY 4.0, per repo root README
#   - file sha256: f8472efd6bfd6c845a9d8c540c675ea41c173c03de61e8475353cd0dc8242f10
#   - NOTE: this specific ward file's licensing is inherited from the
#     repo root's default CC BY 4.0 notice, not a per-file override --
#     re-check the Mumbai/Readme.md in this repo if a stricter license
#     is ever announced for this specific file.
MUMBAI_BMC_WARDS = {
    "boundary_layer_id": "datameet_mumbai_bmc_wards",
    "name": "Mumbai BMC Ward Boundaries",
    "source": {
        "provider": "DataMeet India community",
        "dataset": "Municipal Spatial Data",
        "source_file": "Mumbai/BMC_Wards.geojson",
        "source_url": "https://raw.githubusercontent.com/datameet/Municipal_Spatial_Data/master/Mumbai/BMC_Wards.geojson",
        "repo_url": "https://github.com/datameet/Municipal_Spatial_Data",
        "license": "CC BY 4.0",
        "attribution": "Mumbai Municipal Spatial Data by DataMeet India community (CC BY 4.0)",
    },
    "unit_type": "municipal_ward",
    "admin_level": "ward",
    "unit_id_field": "gid",
    "unit_name_field": "name",
    "expected_feature_count": 24,
    "expected_geometry_type": "MultiPolygon",
    "expected_crs": "EPSG:4326",
    "file_sha256": "f8472efd6bfd6c845a9d8c540c675ea41c173c03de61e8475353cd0dc8242f10",
}

# Registry of known boundary sources, keyed by boundary_layer_id.
# ingest_boundary_layer() looks up entries here when given a known ID,
# or accepts a fully custom manifest dict for a user-uploaded layer
# that isn't in this registry yet.
KNOWN_BOUNDARY_SOURCES = {
    MUMBAI_BMC_WARDS["boundary_layer_id"]: MUMBAI_BMC_WARDS,
}

BOUNDARY_STORAGE_DIR = "data/boundaries"