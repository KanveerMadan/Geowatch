"""
Event-level setting tags from the statistics fetch.setting_stats stored.
Rules and their sources are in events.py's docstring; the code is the rule.
"""
from __future__ import annotations

from configs.coastal_constants import COASTAL_APPLICABILITY_THRESHOLD_KM
from experiments.flood_learned import events as LE

LECZ_ELEV_M = 10.0      # Low Elevation Coastal Zone (McGranahan et al. 2007)
# GHS-SMOD level-2 codes (GHSL Data Package 2023, table 5)
SMOD_URBAN = {30, 23}           # urban centre, dense urban cluster
SMOD_PERI = {22, 21}            # semi-dense urban cluster, suburban / peri-urban
SMOD_RURAL = {13, 12, 11}       # rural cluster, low and very low density rural


def kapos_mountain(elev_m, slope_deg, range_7km_m) -> bool | None:
    """Kapos et al. (2000) classes 1-6 (UNEP-WCMC mountain definition)."""
    if elev_m is None:
        return None
    s = slope_deg or 0.0
    r = range_7km_m or 0.0
    return bool(elev_m >= 2500
                or (1500 <= elev_m < 2500 and s >= 2)
                or (1000 <= elev_m < 1500 and (s >= 5 or r > 300))
                or (300 <= elev_m < 1000 and r > 300))


def koppen_arid(monthly: dict, centre_lat: float) -> dict:
    """Koppen-Geiger group B test (Peel et al. 2007, Table 1)."""
    t = [monthly[str(m)]["t_c"] for m in range(1, 13)]
    p = [monthly[str(m)]["p_mm"] for m in range(1, 13)]
    mat, map_ = sum(t) / 12, sum(p)
    summer = range(4, 10) if centre_lat >= 0 else (10, 11, 12, 1, 2, 3)
    p_summer = sum(p[m - 1] for m in summer)
    if p_summer >= 0.7 * map_:
        pth = 2 * mat + 28
    elif map_ - p_summer >= 0.7 * map_:
        pth = 2 * mat
    else:
        pth = 2 * mat + 14
    arid = map_ < 10 * pth
    return {"mat_c": round(mat, 2), "map_mm": round(map_, 1), "p_threshold": round(pth, 2),
            "arid": bool(arid), "class": ("BW" if map_ < 5 * pth else "BS") if arid else "not B"}


def settlement(smod_hist: dict) -> str | None:
    h = (smod_hist or {}).get("smod_code") or {}
    h = {int(float(k)): v for k, v in h.items() if int(float(k)) != 10}     # 10 = water
    if not h:
        return None
    top = max(h, key=h.get)
    return ("urban" if top in SMOD_URBAN else "peri_urban" if top in SMOD_PERI
            else "rural" if top in SMOD_RURAL else None)


def tags(name: str, s: dict) -> dict:
    k = s["kapos"]
    ar = koppen_arid(s["era5_monthly"], s["centre_lat"])
    coast = s.get("coast_distance_km")
    coastal = (coast is not None and coast <= COASTAL_APPLICABILITY_THRESHOLD_KM
               and k["elev_median_m"] is not None and k["elev_median_m"] <= LECZ_ELEV_M)
    st = settlement(s.get("smod_hist"))
    return {"settlement": st, "urban": st == "urban", "peri_urban": st == "peri_urban",
            "rural": st == "rural",
            "mountain": kapos_mountain(k["elev_median_m"], k["slope_median_deg"],
                                       k["range_7km_m"]),
            "arid": ar["arid"], "koppen": ar, "coastal": bool(coastal),
            "coast_distance_km": coast, "elev_median_m": k["elev_median_m"],
            "delta": name in LE.DELTA_UNITS}
