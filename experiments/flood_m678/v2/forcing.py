"""
M6–M8 v2 step 3: event water surface per reach from discharge (ARCHITECTURE_V2 item 2).

HAND synthetic rating curve (the NOAA OWP / Zheng et al. 2018 approach): for one reach of length
Lr with catchment cells i (HAND h_i, slope s_i, cell area a):
    V(y) = sum_i max(0, y - h_i) * a                       wetted volume at stage y
    A(y) = V(y) / Lr                                        cross-section area
    P(y) = sum_{h_i < y} a * sqrt(1 + s_i^2) / Lr           wetted perimeter
    Q(y) = A R^(2/3) sqrt(S) / n,  R = A / P                Manning
Stage for a discharge is found by bisection. The surface W = channel elevation + y.

Melt forcing (M8 sustained melt): the measured crest discharge at the gauge (WSC annual peak), scaled
to other reaches on the network by upstream area (Q_r = Q_g (A_r / A_g)^0.8, a regional exponent;
recorded as an assumption). Every output carries its source, issue time and units. A stage taken from
the same gauge that dates the labels is not independent stage validation (design note).
"""
from __future__ import annotations

import numpy as np

N_DEFAULT = 0.05
AREA_EXPONENT = 0.8


def rating(hand, slope_frac, cell_area_m2, reach_len_m, bed_slope, n=N_DEFAULT, ys=None):
    """(stage grid y, discharge Q(y)) for one reach's catchment cells."""
    h = np.asarray(hand, float)
    h = h[np.isfinite(h)]
    s = np.asarray(slope_frac, float)[: len(h)] if np.ndim(slope_frac) else np.full(len(h), float(slope_frac))
    ys = np.linspace(0.05, 15.0, 300) if ys is None else np.asarray(ys, float)
    Q = np.zeros_like(ys)
    for k, y in enumerate(ys):
        wet = h < y
        if not wet.any():
            continue
        A = np.sum(y - h[wet]) * cell_area_m2 / reach_len_m
        P = np.sum(cell_area_m2 * np.sqrt(1 + s[wet] ** 2)) / reach_len_m
        R = A / P if P > 0 else 0.0
        Q[k] = A * R ** (2 / 3) * np.sqrt(max(bed_slope, 1e-5)) / n
    return ys, Q


def stage_for(Q_target, ys, Q):
    """Stage for a discharge (monotone interpolation; clipped to the table)."""
    Qm = np.maximum.accumulate(Q)
    if Q_target <= Qm[0]:
        return float(ys[0])
    if Q_target >= Qm[-1]:
        return float(ys[-1])
    return float(np.interp(Q_target, Qm, ys))


def scale_discharge(Q_gauge, upa_gauge_km2, upa_reach_km2, exponent=AREA_EXPONENT):
    return float(Q_gauge) * (float(upa_reach_km2) / float(upa_gauge_km2)) ** exponent


def forcing_record(source, issue_time, q_m3s, kind, bounds=None):
    return {"source": source, "issue_time": issue_time, "discharge_m3s": q_m3s, "kind": kind,
            "bounds_m3s": bounds, "units": "m3/s"}
