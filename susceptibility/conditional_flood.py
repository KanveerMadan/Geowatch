"""
M6–M8 (flood round 5): where water goes IF the event happens. Per pixel, on the hydrology grid.

    debris_flow_glof        M6  glacial lake outburst / debris flood
    embankment_dam_breach   M7  dam, levee or embankment breach
    snowmelt_ice_jam        M8  spring snowmelt or ice-jam flood

None of these says how likely the event is. A glacial lake, a dam or a snowpack can be absent, and
then the type is NOT computed (absent, with the reason) -- never a zero score.

The ranking method per type is the one pre-registered and tested in
experiments/flood_m678/PREREGISTRATION_M678.md, read from configs/m678_constants.py:
  elev        minus FABDEM elevation, as a within-area percentile;
  hand        minus MERIT HAND;
  phys_main   minus the height above the nearest trunk-channel cell (MERIT upa >= 25 % of the
              area maximum): the flood arrives down the trunk river, not the side streams.
  phys_laharz LAHARZ-style routed inundation from the nearest inventoried lake's typical released
              volume (M6, pre-registered physics-only method).
The trust label comes only from the one-shot reserve test (experiments/flood_m678/results/test_m678.json).

Scenario mode (scenario_depth): for a user-named lake or dam, an illustrative depth map from a
published empirical peak-flow formula and hydraulic geometry. Always labelled `scenario`; never
validated.
"""
from __future__ import annotations


import numpy as np

from configs import m678_constants as K
from susceptibility.hydro_rasters import layer

KINDS = ("debris_flow_glof", "embankment_dam_breach", "snowmelt_ice_jam")


def _pct(v):
    """Within-area percentile in [0, 1], NaN kept."""
    out = np.full(v.shape, np.nan)
    ok = np.isfinite(v)
    n = int(ok.sum())
    if n > 1:
        r = np.argsort(np.argsort(v[ok], kind="stable"), kind="stable")
        out[ok] = r / (n - 1)
    return out


def trunk_height(elev, upa):
    """(height above nearest trunk cell m, distance m in cells) or (None, None)."""
    from scipy.ndimage import distance_transform_edt
    if elev is None or upa is None or not np.isfinite(upa).any():
        return None, None
    u = np.nan_to_num(upa, nan=0.0)
    if u.max() < K.MIN_TRUNK_UPA_KM2:
        return None, None
    trunk = u >= K.TRUNK_SHARE * u.max()
    d, (ri, ci) = distance_transform_edt(~trunk, return_indices=True)
    h = elev - elev[ri, ci]
    return h, d


def laharz_score(elev, upa, volume_m3, c=0.05, cell=30.0):
    """LAHARZ-style routed inundation (Iverson et al. 1998), as pre-registered for M6
    (experiments/flood_m678/m6_physics.py): each trunk cross-section fills to the level that
    floods A = c * V^(2/3); score = that level minus the cell's height above the trunk."""
    h, _ = trunk_height(elev, upa)
    if h is None:
        return None
    from scipy.ndimage import distance_transform_edt
    u = np.nan_to_num(upa, nan=0.0)
    _, (ri, ci) = distance_transform_edt(~(u >= K.TRUNK_SHARE * u.max()), return_indices=True)
    sec = (ri * elev.shape[1] + ci).ravel()
    hv = h.ravel()
    target = c * volume_m3 ** (2.0 / 3.0)
    out = np.full(hv.shape, np.nan)
    ok = np.flatnonzero(np.isfinite(hv))
    order = ok[np.argsort(sec[ok], kind="stable")]
    s_sorted = sec[order]
    cuts = np.flatnonzero(np.diff(s_sorted)) + 1
    for a, b in zip(np.r_[0, cuts], np.r_[cuts, len(order)]):
        idx = order[a:b]
        hs = hv[idx]
        lo, hi = float(hs.min()), float(hs.min()) + 1.0
        while np.clip(hi - hs, 0, None).sum() * cell < target and hi - lo < 1e4:
            hi = lo + 2 * (hi - lo)
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if np.clip(mid - hs, 0, None).sum() * cell < target else (lo, mid)
        out[idx] = hi - hs
    return out.reshape(elev.shape)


def score_map(method: str, rasters: dict, ctx: dict | None = None):
    """Higher = more flood-prone, within-area percentile; None when the inputs are missing."""
    elev, hand, upa = layer(rasters, "elev_m"), layer(rasters, "hand_m"), layer(rasters, "upa_km2")
    if method == "elev":
        return None if elev is None else _pct(-elev)
    if method == "hand":
        return None if hand is None else _pct(-hand)
    if method == "phys_main":
        h, _ = trunk_height(elev, upa)
        return None if h is None else _pct(-h)
    if method == "phys_laharz":
        v = ((ctx or {}).get("glacial_lakes") or {}).get("volume_m3") or K.DEFAULT_LAKE_VOLUME_M3
        sc = laharz_score(elev, upa, v) if elev is not None and upa is not None else None
        return None if sc is None else _pct(sc)
    raise ValueError(f"unknown method {method!r}")


def applicability(kind: str, ctx: dict) -> tuple[bool, str]:
    """(applies, reason). Missing context is 'unknown', reported as not applicable with that reason."""
    if kind == "debris_flow_glof":
        n = (ctx.get("glacial_lakes") or {}).get("count_within_km")
        if n is None:
            return False, "glacial-lake inventory not checked for this area"
        if n == 0:
            return False, (f"no glacial lake in the GLOF v4.2 inventory within {K.LAKE_SEARCH_KM:g} km; "
                           "not computed (this is not a zero risk: lakes form and inventories are incomplete)")
        return True, f"{n} inventoried glacial lake(s) within {K.LAKE_SEARCH_KM:g} km"
    if kind == "snowmelt_ice_jam":
        days = (ctx.get("snow") or {}).get("snow_days_per_year")
        if days is None:
            return False, "seasonal snow cover not checked for this area"
        if days < K.MIN_SNOW_DAYS:
            return False, (f"seasonal snow is rare here ({days:.0f} snow-covered days a year, MODIS); "
                           "not computed")
        return True, f"{days:.0f} snow-covered days a year (MODIS 2015-2024)"
    return True, "computed wherever a river crosses the area; conditional on a breach upstream"


def compute(kind: str, rasters: dict | None, ctx: dict | None = None) -> dict:
    ctx = ctx or {}
    method = K.METHODS[kind]
    base = {"method": method, "flood_type": K.FLOOD_TYPE_ID[kind],
            "validation_status": K.validation_status(kind),
            "limitations": list(K.LIMITATIONS[kind]) + [K.trust_note(kind)]}
    ok, why = applicability(kind, ctx)
    base["applicability"] = {"applies": ok, "reason": why}
    if not ok:
        return {**base, "status": "not_applicable", "reason": why, "aoi_mean_score": None,
                "susceptibility_map": None}
    m = score_map(method, rasters, ctx) if rasters else None
    if m is None or not np.isfinite(m).any():
        return {**base, "status": "insufficient_evidence", "aoi_mean_score": None, "susceptibility_map": None,
                "reason": "terrain layers unavailable for this method"
                          + (f": {rasters.get('error')}" if rasters and rasters.get("error") else "")}
    score = float(np.nanmean(m))
    return {**base, "status": "computed", "aoi_mean_score": round(score, 4),
            "aoi_mean_class": K.classify(score), "susceptibility_map": m,
            "components_used": [method], "components_excluded": []}


# ------------------------------------------------------------------ scenario
def peak_flow_m3s(kind: str, volume_m3: float, height_m: float | None = None) -> float:
    """Empirical peak outflow. Dam: Froehlich (1995), Qp = 0.607 V^0.295 H^1.24 (V m3, H m).
    Ice- or moraine-dammed lake: Walder & Costa (1996) for non-tunnel drainage, Qp = 1100 V^0.44
    (V in 10^6 m3)."""
    if volume_m3 <= 0:
        raise ValueError("volume must be positive")
    if kind == "embankment_dam_breach":
        if not height_m or height_m <= 0:
            raise ValueError("a dam scenario needs the dam height")
        return 0.607 * volume_m3 ** 0.295 * height_m ** 1.24
    if kind == "debris_flow_glof":
        return 1100.0 * (volume_m3 / 1e6) ** 0.44
    raise ValueError(f"no scenario for {kind}")


def scenario_depth(kind: str, rasters: dict, volume_m3: float, height_m: float | None = None) -> dict:
    """Illustrative water depth (m) if the named lake or dam released `volume_m3`: the breach peak
    turned into a stage by hydraulic geometry (depth 0.27 Q^0.39, Andreadis et al. 2013), minus
    the height above the trunk channel, without attenuation. Labelled `scenario`, never validated."""
    q = peak_flow_m3s(kind, volume_m3, height_m)
    stage = 0.27 * q ** 0.39
    h, _ = trunk_height(layer(rasters, "elev_m"), layer(rasters, "upa_km2"))
    if h is None:
        return {"status": "insufficient_evidence", "validation_status": "scenario",
                "reason": "no trunk channel in the area", "peak_flow_m3s": round(q, 1)}
    depth = np.where(np.isfinite(h), np.clip(stage - h, 0.0, None), np.nan)
    return {"status": "computed", "validation_status": "scenario", "peak_flow_m3s": round(q, 1),
            "stage_m": round(stage, 2), "depth_map_m": depth,
            "wet_share": float(np.nanmean(depth > 0)) if np.isfinite(depth).any() else None,
            "limitations": ["Scenario, not a forecast or a validated map: one empirical peak flow, no "
                            "routing, no attenuation, no breach timing.",
                            "Shows where water could stand if this lake or dam released the stated volume."]}


def peak_reference():
    return {"froehlich_1995": "Froehlich, D.C. (1995) Peak outflow from breached embankment dam. J. Water Resour. Plann. Manage. 121(1).",
            "walder_costa_1996": "Walder, J.S. & Costa, J.E. (1996) Outburst floods from glacier-dammed lakes. Earth Surf. Process. Landforms 21.",
            "andreadis_2013": "Andreadis, K.M., Schumann, G.J.-P. & Pavelsky, T. (2013) A simple global river bankfull width and depth database. WRR 49."}


