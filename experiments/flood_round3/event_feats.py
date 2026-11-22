"""
Round 3, Phase 4: event features the terrain cannot know (river).

Per cell, from the reaches of the GEOGloWS v2 network (CC BY 4.0) near the box. Discharge is the retrospective simulation, so nothing comes from the label.
- **Reach:** each cell's nearest reach point among reaches with drainage ≥ MIN_DSAREA_KM2 inside the box + 2 km.
- **`ev_q_ratio`:** log10(event peak Q / median Q) of that reach, i.e. how unusual this event was on this river.
- **`ev_q_rp`:** the empirical annual-maximum return period of the peak (years, log10).
- **`ev_depth_below_stage_m`:** a stage proxy minus the cell's MERIT HAND:
  - stage = d_bf · (Q_peak / Q_2)^0.4;
  - d_bf = 0.27 · Q_2^0.39 m, from global hydraulic geometry for bankfull depth (Andreadis, Schumann & Pavelsky 2013), where Q_2 is the 2-year annual maximum;
  - the exponent 0.4 is the at-a-station depth exponent (Leopold & Maddock 1953: f ≈ 0.4).
  - Positive means the cell lies below the estimated event water surface of its reach.

The peak is the maximum Q in [event − 10 d, event + 7 d], as in DIAGNOSIS §b and RESERVE_CRITERIA §2.
Monotone directions are in model_r3.MONOTONE.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

MIN_DSAREA_KM2 = 10.0
PAD_DEG = 0.02


def _cell_lonlat(transform, shape, crs):
    from pyproj import Transformer
    r, c = np.mgrid[0:shape[0], 0:shape[1]]
    x = transform[2] + (c + 0.5) * transform[0]
    y = transform[5] + (r + 0.5) * transform[4]
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(x.ravel(), y.ravel())
    return np.asarray(lon), np.asarray(lat)


def reach_stats(link, event):
    from experiments.flood_round3 import diagnose_ee as D
    s = D.q_series(link)
    if s is None:
        return None
    t, q = s
    ev = dt.date.fromisoformat(event)
    m = (t >= (ev - dt.timedelta(days=10)).isoformat()) & (t <= (ev + dt.timedelta(days=7)).isoformat())
    if not m.any():
        return None
    qp = float(q[m].max())
    yrs = np.array([int(x[:4]) for x in t])
    amax = np.array([q[yrs == y].max() for y in np.unique(yrs) if (yrs == y).sum() > 300])
    q2 = float(np.median(amax))
    rp = 1.0 / max(1e-3, float(np.mean(amax >= qp)))
    qmed = float(np.median(q))
    return {"q_peak": qp, "q2": q2, "q_med": qmed, "rp": rp}


def river_features(grid: dict, event: str, hand_m: np.ndarray, ix=None) -> dict:
    """{feature: per-cell array} for a table grid {crs, transform, shape}; hand_m per cell (flattened)."""
    from experiments.flood_round3 import diagnose_ee as D
    ix = ix if ix is not None else D._reach_index()
    shape = tuple(grid["shape"])
    lon, lat = _cell_lonlat(grid["transform"], shape, grid["crs"])
    w, s_, e, n = lon.min() - PAD_DEG, lat.min() - PAD_DEG, lon.max() + PAD_DEG, lat.max() + PAD_DEG
    m = ((ix["lon"] >= w) & (ix["lon"] <= e) & (ix["lat"] >= s_) & (ix["lat"] <= n)
         & (ix["dsarea"] / 1e6 >= MIN_DSAREA_KM2))
    nan = np.full(lon.shape, np.nan, np.float32)
    out = {"ev_q_ratio": nan.copy(), "ev_q_rp": nan.copy(), "ev_depth_below_stage_m": nan.copy()}
    idx = np.flatnonzero(m)
    stats, keep = [], []
    for i in idx:
        st = reach_stats(int(ix["link"][i]), event)
        if st is not None and st["q2"] > 0 and st["q_med"] > 0:
            stats.append(st)
            keep.append(i)
    if not keep:
        return out
    from scipy.spatial import cKDTree
    coslat = np.cos(np.radians(np.mean(lat)))
    tree = cKDTree(np.c_[ix["lon"][keep] * coslat, ix["lat"][keep]])
    _, j = tree.query(np.c_[lon * coslat, lat])
    qr = np.array([np.log10(max(s["q_peak"], 1e-6) / s["q_med"]) for s in stats])
    rp = np.array([np.log10(s["rp"]) for s in stats])
    stage = np.array([0.27 * s["q2"] ** 0.39 * (s["q_peak"] / s["q2"]) ** 0.4 for s in stats])
    out["ev_q_ratio"] = qr[j].astype(np.float32)
    out["ev_q_rp"] = rp[j].astype(np.float32)
    out["ev_depth_below_stage_m"] = (stage[j] - np.asarray(hand_m, np.float64)).astype(np.float32)
    out["_reaches"] = len(keep)
    return out
