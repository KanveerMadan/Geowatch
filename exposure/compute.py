"""
Phase 10A: exposure computation. Combines population (WorldPop),
built-up reference (GHSL cross-check + GeoWatch's own land-cover),
roads (OSM), and facilities (OSM) -- intersected against ONE evidence
layer at a time.

GATE C STATUS: WAIVED, NOT PASSED -- see PROJECT_GATES.md at the project
root for the full gate table and waiver reasoning. No real user
(planner/NGO/researcher) has reviewed this module's output for whether
its shape, granularity, and limitation-labeling are actually adequate
for real decision-support use. This module is technically correct
(Gate A: verified data sources, re-verified population fix) and has
been run against real data including one real event window (Gate B),
but "useful and correctly understood by a real user" remains
UNVERIFIED. Every caller of compute_exposure_for_layer() -- Phase 10B
risk scoring, any frontend display, any generated report -- MUST
propagate the `product_validation_status` field from this module's
output forward into its own output, so the waiver cannot silently
disappear as more phases get built on top of exposure. Update
GATE_C_STATUS below (and PROJECT_GATES.md's Gate C row, in the same
change) only after a real user has actually reviewed this output.
"""

# See module docstring above and PROJECT_GATES.md for full context.
# This constant is the single source of truth for Gate C's status --
# read it here, do not hardcode the string "waived..." anywhere else.
GATE_C_STATUS = "waived_pending_real_user_validation"

""" HARD RULE, per Document 1's correction of the original Phase 10 plan:
exposure is computed SEPARATELY for every EvidenceLayer (e.g. pluvial
susceptibility, fluvial susceptibility, coastal susceptibility, observed
inundation). This module NEVER auto-selects a "highest available hazard
layer" and NEVER merges multiple evidence layers into one exposure
number. "Population near a pluvial-susceptibility zone" and "population
in observed floodwater" are different claims and must never be
collapsed into one field.

This is EXPOSURE, not IMPACT. Population intersecting a hazard/
susceptibility layer does not mean that population was "affected" --
people may be on upper floors, absent, protected by local barriers, or
the population estimate (2020) may not match current residency. Use
"estimated population exposed" language, never "affected" or "at risk"
in any user-facing text derived from this module's output.
"""

import ee


class EvidenceLayer:
    """
    Minimal version of Document 1's EvidenceLayer contract -- prevents
    accidentally mixing event-specific observed evidence with long-term
    static susceptibility screening under one exposure computation.
    """

    def __init__(self, layer_id: str, label: str, evidence_type: str,
                 status: str, mask_source: str, threshold_or_score,
                 temporal_scope: str, limitations: list = None):
        self.layer_id = layer_id
        self.label = label
        # evidence_type: "event_specific_observation" or "long_term_screening"
        self.evidence_type = evidence_type
        self.status = status
        # mask_source: "aoi_wide_scalar" (no per-pixel raster exists yet
        # for most Phase 4-9 susceptibility outputs) or "per_pixel_raster"
        self.mask_source = mask_source
        self.threshold_or_score = threshold_or_score
        self.temporal_scope = temporal_scope
        self.limitations = limitations or []


from perception.applicability_gate import gated


@gated("exposure")
def compute_exposure_for_layer(
    evidence_layer: EvidenceLayer,
    aoi_geometry: "ee.Geometry",
    population_context: dict,
    builtup_reference: dict = None,
    road_length_context: dict = None,
    facilities_context: dict = None,
    landcover_builtup_pct: float = None,
) -> dict:
    """
    Compute exposure for ONE evidence layer.

    IMPORTANT CURRENT LIMITATION, stated explicitly rather than hidden:
    most of this project's evidence layers (pluvial/fluvial/coastal/
    flash_flood/waterlogging susceptibility) are AOI-WIDE SCALARS, not
    per-pixel spatial rasters (see each susceptibility module's own
    `spatial: false` field). This means "population intersecting the
    hazard mask" cannot yet be computed as a true spatial intersection
    for those layers -- there is no per-pixel mask to intersect against.
    For AOI-wide-scalar evidence layers, this function instead reports:
    "total population/built-up/roads/facilities WITHIN THE AOI, given
    that this evidence layer's status is {applicable/experimental}" --
    an AOI-total exposure context, NOT a within-hazard-footprint
    exposure. This distinction is preserved explicitly in the output via
    `intersection_type`. True per-pixel intersection becomes possible
    once a per-pixel hazard raster exists (e.g. Phase 8's observed
    inundation, if a spatial mask is exported in a future revision).

    Args:
        evidence_layer: which evidence this exposure is FOR (never merged
            across layers)
        aoi_geometry: ee.Geometry.Rectangle for the AOI (or a real
            per-pixel hazard mask geometry, once one exists)
        population_context: output of
            ingestion.exposure_sources.get_population_context()
        builtup_reference: optional, output of get_builtup_reference()
        road_length_context: optional, output of get_osm_road_length()
        facilities_context: optional, output of get_osm_facilities()
        landcover_builtup_pct: optional, GeoWatch's own built-up-like
            category_area_pct sum (dense_informal_roofing +
            sparse_informal_roofing + paved_road, etc.) for cross-check
            against GHSL -- caller computes this, not this function.

    Returns:
        dict matching the exposure-per-layer schema.
    """
    if evidence_layer.status not in ("applicable", "experimental", "available"):
        return {
            "layer_id": evidence_layer.layer_id,
            "label": evidence_layer.label,
            "status": "not_calculated",
            "reason": f"Evidence layer status is '{evidence_layer.status}', "
                      f"not usable for exposure computation.",
        }

    result = {
        "layer_id": evidence_layer.layer_id,
        "label": evidence_layer.label,
        "evidence_type": evidence_layer.evidence_type,
        "temporal_scope": evidence_layer.temporal_scope,
        "intersection_type": (
            "aoi_total_given_layer_applicability"
            if evidence_layer.mask_source == "aoi_wide_scalar"
            else "spatial_mask_intersection"
        ),
        "status": "available",
        # Gate C (product-value validation) is WAIVED, not passed -- see
        # PROJECT_GATES.md. This field must be carried forward by any
        # future consumer of this output (Phase 10B risk, frontend,
        # reports) rather than dropped, so the waiver stays visible no
        # matter how many layers get built on top of exposure.
        "product_validation_status": GATE_C_STATUS,
        "components": {},
        "limitations": list(evidence_layer.limitations),
    }

    # ── Population (WorldPop, zonal SUM -- never mean x area) ──
    if population_context is not None and population_context.get("status") == "available":
        try:
            pop_image = population_context["image"]
            pop_proj = pop_image.projection().getInfo()
            pop_sum_stats = pop_image.reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=aoi_geometry,
                crs=pop_proj["crs"],
                crsTransform=pop_proj["transform"],
                maxPixels=1e9,
                bestEffort=False,
            ).getInfo()
            pop_estimate = pop_sum_stats.get(population_context["band"])

            result["components"]["population"] = {
                "status": "available",
                "estimated_population": (
                    round(float(pop_estimate)) if pop_estimate is not None else None
                ),
                "population_source": {
                    "dataset": "WorldPop",
                    "asset_id": population_context["source"],
                    "population_year": population_context["population_year"],
                    "native_resolution_m": population_context["native_resolution_m"],
                    "method": "raster_zonal_sum",
                    "estimate_type": "modelled_population_estimate",
                },
            }
            result["limitations"].extend(population_context.get("limitations", []))
        except Exception as e:
            result["components"]["population"] = {
                "status": "unavailable", "estimated_population": None, "error": str(e),
            }
    else:
        result["components"]["population"] = {
            "status": "unavailable",
            "estimated_population": None,
            "error": (population_context or {}).get("error", "Population context not provided."),
        }

    # ── Built-up (GeoWatch model + GHSL cross-check, per Document 1) ──
    builtup_component = {"status": "not_calculated"}
    if landcover_builtup_pct is not None:
        builtup_component = {
            "status": "available",
            "geowatch_model_builtup_pct": landcover_builtup_pct,
            "geowatch_applicability": "see urban_landcover_model in applicability block",
        }
        if builtup_reference is not None and builtup_reference.get("status") == "available":
            builtup_component["global_reference_source"] = builtup_reference["source"]
            builtup_component["agreement_status"] = "not_yet_compared"  # placeholder --
            # real pixel-level agreement comparison is a follow-up, not built
            # in this pass; do not fabricate an agreement score.
            builtup_component["limitations"] = builtup_reference.get("limitations", [])
        else:
            builtup_component["global_reference_source"] = None
            builtup_component["note"] = (
                "GHSL reference unavailable or unverified -- built-up figure "
                "reflects GeoWatch's own model only, which has known "
                "geographic and classification limitations (see "
                "applicability.urban_landcover_model and the project's "
                "documented paved_road/roofing confusion)."
            )
    result["components"]["built_up"] = builtup_component

    # ── Roads (real OSM geometry, never model paved_road) ──
    if road_length_context is not None and road_length_context.get("status") == "available":
        result["components"]["roads"] = {
            "status": "available",
            "source": "OpenStreetMap",
            "total_length_km": road_length_context["total_length_km"],
            "by_highway_type": road_length_context["by_highway_type"],
            "osm_completeness": "unknown",
            "limitation": "Unmapped roads are not included; OSM completeness varies by region.",
        }
    else:
        result["components"]["roads"] = {
            "status": "unavailable",
            "total_length_km": None,
            "error": (road_length_context or {}).get("error", "Road context not provided."),
        }

    # ── Facilities (OSM points, hospitals/clinics/schools only for v1) ──
    if facilities_context is not None and facilities_context.get("status") == "available":
        result["components"]["facilities"] = {
            "status": "available",
            "source": "OpenStreetMap",
            "count": len(facilities_context["facilities"]),
            "facilities": facilities_context["facilities"],
            "osm_completeness": "unknown",
            "note": "Mapped facilities intersecting the AOI -- this does NOT imply "
                    "these facilities are non-functional or disrupted.",
        }
    else:
        result["components"]["facilities"] = {
            "status": "unavailable",
            "count": 0,
            "error": (facilities_context or {}).get("error", "Facilities context not provided."),
        }

    return result