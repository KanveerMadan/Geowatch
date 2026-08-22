"""
Phase 9: event hazard -- conditions Phase 4/5/6's SUSCEPTIBILITY
baselines (long-term physical predisposition) on ACTUAL EVENT FORCING
(what happened/is forecast during a specific window). Per the master
schema's own terminology rule: susceptibility != hazard. Hazard requires
forcing; these functions are what supplies it.
"""

from configs.event_hazard_constants import (
    EVENT_RAINFALL_NORMALIZATION_MAX_MM,
    DISCHARGE_PROXY_RAINFALL_NORMALIZATION_MAX_MM,
    EVENT_HAZARD_CLASS_BREAKS,
)


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in EVENT_HAZARD_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


def compute_pluvial_event_hazard(pluvial_susceptibility: dict, event_rainfall: dict) -> dict:
    """
    Conditions Phase 4's pluvial susceptibility score on real GPM IMERG
    event rainfall. Both must be available with a real numeric score.
    """
    susc_available = (
        pluvial_susceptibility is not None
        and pluvial_susceptibility.get("status") == "experimental"
        and pluvial_susceptibility.get("aoi_mean_score") is not None
    )
    rainfall_available = (
        event_rainfall is not None
        and event_rainfall.get("status") == "available"
        and event_rainfall.get("event_total_mm") is not None
    )

    if not susc_available or not rainfall_available:
        reasons = []
        if not susc_available:
            reasons.append("pluvial susceptibility unavailable")
        if not rainfall_available:
            reasons.append("event rainfall (IMERG) unavailable")
        return {"status": "not_calculated", "reason": "; ".join(reasons)}

    susc_score = pluvial_susceptibility["aoi_mean_score"]
    rainfall_mm = event_rainfall["event_total_mm"]
    rainfall_factor = max(0.0, min(1.0, rainfall_mm / EVENT_RAINFALL_NORMALIZATION_MAX_MM))

    # Hazard = susceptibility gated by actual forcing -- if no rain fell,
    # hazard should read low regardless of how susceptible the terrain
    # is. Simple multiplicative gating, not a weighted sum: susceptibility
    # sets the CEILING, forcing determines how much of that ceiling is
    # realized this event.
    hazard_score = round(susc_score * rainfall_factor, 4)

    return {
        "status": "experimental",
        "aoi_mean_score": hazard_score,
        "aoi_mean_class": _classify(hazard_score),
        "underlying_susceptibility_score": susc_score,
        "event_rainfall_mm": rainfall_mm,
        "event_period": event_rainfall.get("event_period"),
        "method": "susceptibility_gated_by_event_rainfall_multiplicative",
        "validated": False,
        "limitations": [
            "Simple multiplicative gating -- NOT a hydraulic/hydrological "
            "model. Real flood hazard depends on rainfall intensity/timing, "
            "antecedent soil saturation, and drainage capacity, none of "
            "which are modeled here.",
            f"EVENT_RAINFALL_NORMALIZATION_MAX_MM ({EVENT_RAINFALL_NORMALIZATION_MAX_MM}mm) "
            "is a provisional ceiling, not locally calibrated.",
            "Inherits every limitation already listed in the underlying "
            "pluvial susceptibility result.",
        ],
    }


def compute_fluvial_event_hazard(fluvial_susceptibility: dict, discharge_proxy: dict) -> dict:
    """
    Conditions Phase 5's fluvial susceptibility on the RAINFALL-PROXY
    discharge signal -- explicitly NOT real river discharge. See
    ingestion/event_hazard.py's module docstring.
    """
    susc_available = (
        fluvial_susceptibility is not None
        and fluvial_susceptibility.get("status") == "experimental"
        and fluvial_susceptibility.get("aoi_mean_score") is not None
    )
    proxy_available = (
        discharge_proxy is not None
        and discharge_proxy.get("status") == "available"
        and discharge_proxy.get("catchment_rainfall_mm") is not None
    )

    if not susc_available or not proxy_available:
        reasons = []
        if not susc_available:
            reasons.append("fluvial susceptibility unavailable")
        if not proxy_available:
            reasons.append("discharge proxy unavailable")
        return {"status": "not_calculated", "reason": "; ".join(reasons)}

    susc_score = fluvial_susceptibility["aoi_mean_score"]
    catchment_mm = discharge_proxy["catchment_rainfall_mm"]
    forcing_factor = max(0.0, min(1.0, catchment_mm / DISCHARGE_PROXY_RAINFALL_NORMALIZATION_MAX_MM))
    hazard_score = round(susc_score * forcing_factor, 4)

    return {
        "status": "experimental",
        "aoi_mean_score": hazard_score,
        "aoi_mean_class": _classify(hazard_score),
        "underlying_susceptibility_score": susc_score,
        "real_discharge_data": False,
        "catchment_rainfall_mm_proxy": catchment_mm,
        "event_period": discharge_proxy.get("event_period"),
        "method": "susceptibility_gated_by_rainfall_proxy_NOT_real_discharge",
        "validated": False,
        "limitations": [
            "THIS DOES NOT USE REAL RIVER DISCHARGE. GloFAS (the standard "
            "real discharge product) is not a GEE asset. This uses "
            "catchment-wide rainfall accumulation as a weak proxy -- do not "
            "present this as a river discharge forecast.",
            "Simple multiplicative gating, not a hydraulic/routing model -- "
            "no travel time, channel storage, or flood-wave attenuation is "
            "modeled.",
            "Inherits every limitation already listed in the underlying "
            "fluvial susceptibility result.",
        ],
    }


def compute_coastal_event_hazard(coastal_susceptibility: dict) -> dict:
    """
    NOT IMPLEMENTED. No verified global tide/surge GEE asset exists.
    Phase 6 already deferred this pending its own dataset ADR -- Phase 9
    does not fabricate one. Returns not_calculated honestly rather than
    guessing.
    """
    return {
        "status": "not_calculated",
        "reason": (
            "No tide/surge/storm-surge dataset is integrated. GloFAS-class "
            "coastal forcing (astronomical tide, storm surge, wave setup) "
            "requires a dedicated dataset selection and ADR, per the master "
            "spec's Phase 6 deferral -- not fabricated here."
        ),
    }