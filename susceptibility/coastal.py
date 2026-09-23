"""
Phase 6: coastal susceptibility baseline (STATIC/SCREENING SLICE ONLY --
NOT tide/surge event hazard, which is deliberately deferred pending a
dataset ADR -- candidates include the GEE community catalog's "Global
Storm Surge Reconstruction (GSSR) database" and IBTrACS cyclone tracks,
neither integrated yet). Combines two AOI-WIDE SCALAR signals --
distance to the nearest real coastline polygon
(ingestion.coastal.get_coastline_context) and FABDEM bare-earth
elevation (already computed in Phase 5, reused here rather than fetched
again) -- into a simple two-component average.

Deliberately simpler than pluvial's multi-component quality-weighted
fusion: with only two signals and neither empirically validated, a
transparent unweighted average is more honest than implying more
precision than the inputs support. Same reasoning fluvial.py used for
staying a simple direct threshold classification instead of a weighted
fusion.
"""

from configs.coastal_constants import (
    COASTAL_DISTANCE_NORMALIZATION_MAX_KM,
    COASTAL_ELEVATION_NORMALIZATION_MAX_M,
    COASTAL_CLASS_BREAKS,
)


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in COASTAL_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


from perception.applicability_gate import gated


@gated("coastal")
def compute_coastal_susceptibility(coastal_context: dict, fabdem_elevation: dict = None) -> dict:
    """
    Args:
        coastal_context: output of ingestion.coastal.get_coastline_context()
        fabdem_elevation: output of ingestion.hydrology.get_fabdem_elevation_stats()
            (Phase 5) -- reused rather than fetched again, since bare-earth
            elevation relative to sea level is exactly what coastal
            susceptibility needs and this project already fetches it for
            fluvial/terrain_context.

    Returns:
        dict matching the master schema's susceptibility.coastal shape.
    """
    if coastal_context is None or coastal_context.get("status") != "available":
        return {
            "status": "insufficient_evidence",
            "reason": f"Coastline context unavailable: "
                      f"{coastal_context.get('error') if coastal_context else 'not computed'}",
        }

    distance_km = coastal_context.get("distance_km")
    coastal_connected = coastal_context.get("coastal_connectivity")

    if distance_km is None:
        # No coastline found within the search radius -- AOI is far
        # inland. Do not compute a susceptibility score for a mechanism
        # that plausibly doesn't apply; report not_applicable instead of
        # guessing a near-zero score.
        return {
            "status": "not_applicable",
            "reason": (
                f"No coastline geometry found within "
                f"{coastal_context.get('search_radius_km')}km of this AOI -- "
                f"coastal flooding is not a plausible mechanism here."
            ),
        }

    elevation_available = (
        fabdem_elevation is not None
        and fabdem_elevation.get("status") == "available"
        and fabdem_elevation.get("mean_elevation_m") is not None
    )

    distance_score = max(0.0, min(1.0, 1.0 - (distance_km / COASTAL_DISTANCE_NORMALIZATION_MAX_KM)))

    components_used = ["distance_to_coast"]
    components_excluded = []
    scores = [distance_score]

    if elevation_available:
        mean_elev = fabdem_elevation["mean_elevation_m"]
        elevation_score = max(0.0, min(1.0, 1.0 - (mean_elev / COASTAL_ELEVATION_NORMALIZATION_MAX_M)))
        scores.append(elevation_score)
        components_used.append("bare_earth_elevation")
    else:
        components_excluded.append("bare_earth_elevation (FABDEM unavailable)")

    score = sum(scores) / len(scores)

    limitations = [
        "AOI-WIDE SCALAR only -- not a per-pixel spatial raster. Does not show "
        "WHERE within the AOI susceptibility is higher or lower.",
        "STATIC/SCREENING SLICE ONLY -- does NOT include tide, storm surge, "
        "wave setup, or cyclone forcing. This is proximity + elevation "
        "screening, not event hazard. Do not present this as coastal flood risk.",
        "distance_to_coast is measured to the nearest mapped coastline polygon "
        "boundary in a global dataset -- local coastal defenses, seawalls, or "
        "engineered protection are NOT accounted for.",
        "COASTAL_DISTANCE_NORMALIZATION_MAX_KM / "
        "COASTAL_ELEVATION_NORMALIZATION_MAX_M are provisional ceilings, not "
        "calibrated against real coastal flood outcomes.",
        "Unweighted two-component average -- no quality-confidence weighting "
        "applied yet (unlike pluvial's fusion), since neither component has "
        "been independently validated enough to justify a non-uniform weight.",
    ]
    if not coastal_connected:
        limitations.append(
            f"Distance ({distance_km}km) exceeds the applicability threshold -- "
            f"treat this score with extra caution, coastal relevance is "
            f"marginal at this distance."
        )

    return {
        "status": "experimental",
        "aoi_mean_score": round(score, 4),
        "aoi_mean_class": _classify(score),
        "distance_to_coast_km": distance_km,
        "coastal_connectivity": coastal_connected,
        "components_used": components_used,
        "components_excluded": components_excluded,
        "method": "distance_and_elevation_unweighted_average",
        "validated": False,
        "spatial": False,
        "limitations": limitations,
    }