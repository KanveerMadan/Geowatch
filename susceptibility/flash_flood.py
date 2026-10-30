"""
Flash-flood susceptibility (flood taxonomy M4), flood round 4: short-duration
rainfall intensity, catchment response time and stream power, scored on
channels and valley floors below steep, fast catchments -- not on hillsides.
Method fixed in experiments/flood_validation/PREREGISTRATION_ROUND4.md before
it was built. The round-2 weighted-mean method is retired
(susceptibility/retired_methods/flash_flood_round2.py).

Per cell on the hydrology grid (susceptibility/hydro_rasters.py):

    A    MERIT upa focal max within FLASH_POWER_DRAINAGE_RADIUS_M (km^2): the
         drainage line the cell sits on or beside
    S    tan(FABDEM slope focal mean within 1 km): catchment steepness
    L    Hack's law, 1.273 A^0.6 km
    t_c  Kirpich, 0.0195 L_m^0.77 S^-0.385 min
    i    I30 x (max(t_c, 0.5 h) / 0.5 h)^-0.6: the IMERG p99.9 half-hourly
         rate scaled to the response time
    Q    C i A / 3.6 (rational method, m^3/s)
    w    9810 Q S / (3 Q^0.5): unit stream power, W/m^2

    power  = log10(1 + w) / log10(1 + 10,000)
    valley = 1 - HAND / H_max                         (MERIT hnd)
    score  = valley x power^k

A hillside (HAND >= H_max) scores 0 whatever drains past below it. I30 is one
value per 0.1 deg, so it shifts nothing within a city AOI; without IMERG the
fallback FLASH_POWER_INTENSITY_FALLBACK_MM_H is used and recorded (C73).
"""
from __future__ import annotations

import numpy as np

from configs.flash_flood_constants import (
    FLASH_FLOOD_CLASS_BREAKS, FLASH_POWER_BASE_DURATION_H, FLASH_POWER_HACK_C,
    FLASH_POWER_HACK_EXP, FLASH_POWER_IDF_EXPONENT, FLASH_POWER_INTENSITY_FALLBACK_MM_H,
    FLASH_POWER_KIRPICH_C, FLASH_POWER_MIN_AREA_KM2, FLASH_POWER_MIN_SLOPE,
    FLASH_POWER_OMEGA_MAX_W_M2, FLASH_POWER_PARAMS, FLASH_POWER_RUNOFF_C,
    FLASH_POWER_WIDTH_COEF,
)
from susceptibility.hydro_rasters import clip01, layer, map_summary

# Flood round 4 has not been run on this method yet: a real method, not
# validated (C69's meaning). Rounds 1-3's verdicts were on retired methods.
VALIDATION_STATUS = "experimental"
METHOD = "intensity_response_time_stream_power_on_valley_floors"
INPUT_LAYERS = ("hand_m", "upa_flash_km2", "relief_slope_deg", "rain_intensity_mm_h")
CEILINGS = {"omega_max_w_m2": FLASH_POWER_OMEGA_MAX_W_M2,
            "idf_exponent": FLASH_POWER_IDF_EXPONENT, "runoff_c": FLASH_POWER_RUNOFF_C}


def _classify(score):
    if score is None:
        return "unknown"
    for label, (lo, hi) in FLASH_FLOOD_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


def response_time_h(area_km2, slope):
    """Kirpich time of concentration (h) on a Hack's-law channel length."""
    a = np.maximum(np.asarray(area_km2, dtype=np.float64), FLASH_POWER_MIN_AREA_KM2)
    s = np.maximum(np.asarray(slope, dtype=np.float64), FLASH_POWER_MIN_SLOPE)
    length_m = FLASH_POWER_HACK_C * a ** FLASH_POWER_HACK_EXP * 1000.0
    return FLASH_POWER_KIRPICH_C * length_m ** 0.77 * s ** -0.385 / 60.0


def stream_power(area_km2, slope, i30_mm_h):
    """(unit stream power W/m^2, t_c h, intensity mm/h, Q m^3/s)."""
    a = np.maximum(np.asarray(area_km2, dtype=np.float64), FLASH_POWER_MIN_AREA_KM2)
    s = np.maximum(np.asarray(slope, dtype=np.float64), FLASH_POWER_MIN_SLOPE)
    tc = response_time_h(a, s)
    d = np.maximum(tc, FLASH_POWER_BASE_DURATION_H) / FLASH_POWER_BASE_DURATION_H
    i = np.asarray(i30_mm_h, dtype=np.float64) * d ** -FLASH_POWER_IDF_EXPONENT
    q = FLASH_POWER_RUNOFF_C * i * a / 3.6
    omega = 9810.0 * q * s / (FLASH_POWER_WIDTH_COEF * np.sqrt(np.maximum(q, 1e-12)))
    return omega, tc, i, q


def components(rasters: dict) -> dict:
    """{name: 0-1 array or None, "hand_m": array or None, "_rain": source}.
    `valley` is left as HAND here: H_max is a tuned parameter (combine)."""
    hand, upa = layer(rasters, "hand_m"), layer(rasters, "upa_flash_km2")
    relief, rain = layer(rasters, "relief_slope_deg"), layer(rasters, "rain_intensity_mm_h")
    i30, rain_src = (FLASH_POWER_INTENSITY_FALLBACK_MM_H, "fallback") if rain is None \
        else (rain, "imerg")
    power = None
    if upa is not None and relief is not None:
        omega, _, _, _ = stream_power(upa, np.tan(np.radians(relief)), i30)
        power = clip01(np.log10(1.0 + omega) / np.log10(1.0 + FLASH_POWER_OMEGA_MAX_W_M2))
    return {"hand_m": hand, "power": power, "_rain": rain_src}


def combine(comps: dict, params: dict = None):
    """score = (1 - HAND / hand_max_m) x power ** power_exponent, NaN where
    either is missing."""
    p = FLASH_POWER_PARAMS if params is None else params
    if comps.get("hand_m") is None or comps.get("power") is None:
        return None
    valley = clip01(1.0 - comps["hand_m"] / p["hand_max_m"])
    with np.errstate(invalid="ignore"):
        s = valley * comps["power"] ** p["power_exponent"]
    return np.where(np.isfinite(comps["hand_m"]) & np.isfinite(comps["power"]), s, np.nan)


from perception.applicability_gate import gated


@gated("flash_flood")
def compute_flash_flood_susceptibility(rasters: dict = None, params: dict = None) -> dict:
    """
    Args:
        rasters: susceptibility.hydro_rasters.fetch_hydro_rasters() output.
        params: override FLASH_POWER_PARAMS (the validation harness only).
    """
    p = dict(FLASH_POWER_PARAMS if params is None else params)
    comps = components(rasters) if rasters else {}
    m = combine(comps, p) if comps else None
    if m is None or not np.isfinite(m).any():
        return {"status": "insufficient_evidence", "validation_status": VALIDATION_STATUS,
                "reason": "No per-pixel HAND, upstream area or relief slope is available."}
    errors = (rasters or {}).get("errors", {})
    excluded = []
    if comps["_rain"] == "fallback":
        excluded.append(f"rain_intensity_mm_h (IMERG unavailable: "
                        f"{errors.get('rain_intensity_mm_h', 'absent')}; "
                        f"I30 = {FLASH_POWER_INTENSITY_FALLBACK_MM_H} mm/h used)")
    return {
        "status": "experimental",
        "validation_status": VALIDATION_STATUS,
        **map_summary(m, _classify),
        "susceptibility_map": m,
        "components_used": ["valley", "power"],
        "components_excluded": excluded,
        "weights": p,
        "ceilings": dict(CEILINGS),
        "inputs": {k: {kk: v[kk] for kk in ("source", "method", "validation_status")}
                   for k, v in rasters["layers"].items() if k in INPUT_LAYERS},
        "method": METHOD,
        "validated": VALIDATION_STATUS == "validated",
        "spatial": True,
        "limitations": [
            "Hack's law and Kirpich's formula are regional empiricisms applied "
            "everywhere; S is hillslope relief within 1 km, not channel gradient.",
            "Upstream area is MERIT Hydro (~90 m): gullies and urban micro-catchments "
            "are missed.",
            "Rainfall intensity is a climatological percentile (IMERG, 0.1 deg), not an "
            "event forecast, and is one value across a city AOI.",
            "No channel confinement, culverts, debris or sediment are modelled.",
        ],
    }
