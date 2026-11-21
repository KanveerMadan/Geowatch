"""
Flood-core prototype P0: SFINCS on synthetic cases. No real data.

Cases
  c1  water balance, closed irregular basin (conservation)
  c2  tilted plane, steady rain (kinematic-wave analytic profile), default and
      lowered `huthresh`
  c3  backwater: downstream level raised (monotonicity; hydrostatic bound)
  c4  interacting drivers: rain, river inflow, coastal level, all
      combinations, two surge timings; plus a closed variant where driver
      attribution has a known answer
  c5  grid size 10 / 30 / 90 m on one analytic terrain
  c6  terrain perturbation at 30 m (correlated noise, three amplitudes)

Thresholds: none decides pass/fail. Every check's basis is stated where it
is computed: conservation, an analytic solution, monotonicity, or a known
synthetic answer. Depth cut-offs used only for reporting areas are listed
(0.05 / 0.10 / 0.30 m) so their effect is visible.

Usage: python p0_cases.py <run_dir> <results.json> [case ...]
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfincs_io as io  # noqa: E402

REPORT_CUTS_M = (0.05, 0.10, 0.30)
F32_EPS = float(np.finfo(np.float32).eps)


def series_integral(series, t):
    """Integral of a piecewise-linear (time, value) series from 0 to t."""
    ts = np.array([p[0] for p in series], float)
    vs = np.array([p[1] for p in series], float)
    grid = np.unique(np.concatenate([ts[ts < t], [0.0, t]]))
    return float(np.trapezoid(np.interp(grid, ts, vs), grid))


def volume(h, dx):
    return float(np.nansum(np.where(h > 0, h, 0.0)) * dx * dx)


def runmeta(r, cells, tstop):
    keep = {k: r[k] for k in ("wall_s", "sfincs_peak_rss_mib", "solver_reported_s", "exit_code")}
    keep["cells"] = cells
    keep["sim_hours"] = tstop / 3600
    return keep


def smooth_noise(shape, sigma_m, corr_cells, rng):
    """Correlated Gaussian noise (FFT Gaussian filter), rescaled to std sigma_m."""
    w = rng.standard_normal(shape)
    ky = np.fft.fftfreq(shape[0])[:, None]
    kx = np.fft.fftfreq(shape[1])[None, :]
    g = np.exp(-2 * (np.pi * corr_cells) ** 2 * (kx ** 2 + ky ** 2))
    f = np.real(np.fft.ifft2(np.fft.fft2(w) * g))
    return f / f.std() * sigma_m


# ── c1 ─────────────────────────────────────────────────────────────────
def c1(root):
    dx, n = 10.0, 100
    y, x = (np.mgrid[0:n, 0:n] + 0.5) * dx
    z = 5.0 * (((x - 500) ** 2 + (y - 500) ** 2) / 500 ** 2) + 0.3 * np.sin(x / 37) * np.cos(y / 53)
    rain = [(0, 50.0), (3600, 50.0), (3601, 0.0), (10800, 0.0)]
    area = n * n * dx * dx
    out = {"basis": "conservation: stored volume must equal rain volume in a closed basin; the model starts "
                    "dry (zsini below the lowest bed) so no initial storage enters the balance",
           "variants": {}}
    # 'stop': rain stops at 1 h (tests drift after forcing ends); 'steady': rain throughout
    for name, series in (("stop", rain), ("steady", [(0, 50.0), (10800, 50.0)])):
        d = os.path.join(root, f"c1_{name}")
        io.write_model(d, z, np.ones_like(z, int), dx, 10800, 600, rain=series, zsini=float(z.min()) - 1.0)
        r = io.run(d)
        m = io.read_map(d)
        t = m["time"].astype(float)
        model = np.array([volume(m["h"][i], dx) for i in range(len(t))])
        expect = np.array([series_integral(series, ti) / 1000 / 3600 * area for ti in t])
        resid = model - expect
        # float32 resolution of the written depths, summed over wet cells
        f32 = np.array([F32_EPS * float(np.nansum(np.where(m["h"][i] > 0, m["h"][i], 0))) * dx * dx
                        for i in range(len(t))])
        out["variants"][name] = {
            "output_time_s": t.tolist(), "model_m3": model.round(3).tolist(),
            "expected_m3": expect.round(3).tolist(), "residual_m3": resid.round(4).tolist(),
            "residual_rel_final": float(resid[-1] / expect[-1]),
            "residual_rel_max_abs_after_first_output": float(np.max(np.abs(resid[1:] / expect[1:]))),
            "float32_output_bound_m3_final": float(f32[-1]),
            "run": runmeta(r, n * n, 10800)}
    return out


# ── c2 ─────────────────────────────────────────────────────────────────
def c2(root):
    dx, ny, nx, S, n_man, i_mmh = 10.0, 12, 100, 0.01, 0.04, 100.0
    xc = (np.arange(nx) + 0.5) * dx
    z = np.tile(S * (nx * dx - xc), (ny, 1))
    msk = np.ones((ny, nx), int)
    msk[:, -1] = 3                       # outflow boundary on the east column
    i = i_mmh / 1000 / 3600
    analytic = (n_man * i * xc / np.sqrt(S)) ** 0.6
    t_eq = (nx * dx / (np.sqrt(S) / n_man * i ** (2 / 3))) ** 0.6
    out = {"basis": "kinematic-wave steady state h(x) = (n i x / sqrt(S))^(3/5) on a plane "
                    "(an approximation SFINCS's local-inertial scheme should approach)",
           "t_equilibrium_s": round(t_eq, 1), "variants": {}}
    for name, extra in (("default", {}), ("huthresh_0.001", {"huthresh": 0.001})):
        d = os.path.join(root, f"c2_{name}")
        io.write_model(d, z, msk, dx, 10800, 1800, manning=n_man, rain=[(0, i_mmh), (10800, i_mmh)],
                       extra=extra)
        r = io.run(d)
        m = io.read_map(d)
        h = m["h"][-1][ny // 2]
        cols = np.arange(5, nx - 5)
        rel = (h[cols] - analytic[cols]) / analytic[cols]
        out["variants"][name] = {
            "x_m": xc[cols][::10].tolist(), "h_model_m": h[cols][::10].round(4).tolist(),
            "h_analytic_m": analytic[cols][::10].round(4).tolist(),
            "rel_err_median": float(np.median(rel)), "rel_err_max_abs": float(np.max(np.abs(rel))),
            "rel_err_upstream_quarter": float(np.median(rel[: len(cols) // 4])),
            "rel_err_downstream_quarter": float(np.median(rel[-len(cols) // 4:])),
            "run": runmeta(r, ny * nx, 10800)}
    return out


# ── c3 ─────────────────────────────────────────────────────────────────
def c3(root):
    dx, ny, nx, S = 10.0, 10, 200, 0.0005
    xc = (np.arange(nx) + 0.5) * dx
    z = np.tile(S * (nx * dx - xc), (ny, 1))
    msk = np.ones((ny, nx), int)
    msk[:, -1] = 2
    bnd = [(nx * dx - 5, 5.0), (nx * dx - 5, ny * dx - 5)]
    src = [(5.0, ny * dx / 2)]
    levels = (-1.0, 0.5, 1.0, 1.5)
    runs, profiles = {}, {}
    for L in levels:
        d = os.path.join(root, f"c3_L{L:+.1f}")
        io.write_model(d, z, msk, dx, 6 * 3600, 3600, bnd=bnd, bzs=[(0, L, L), (6 * 3600, L, L)],
                       src=src, dis=[(0, 5.0), (6 * 3600, 5.0)])
        r = io.run(d)
        m = io.read_map(d)
        zs = np.where(m["h"][-1] > 0, m["zs"][-1], np.nan)[ny // 2]
        profiles[L] = zs
        runs[str(L)] = runmeta(r, ny * nx, 6 * 3600)
    viol = []
    for a, b in zip(levels[:-1], levels[1:]):
        lo, hi = np.nan_to_num(profiles[a], nan=-9), np.nan_to_num(profiles[b], nan=-9)
        bad = np.where(hi < lo - 1e-4)[0]
        if bad.size:
            viol.append({"levels": [a, b], "cells": bad.tolist()[:20], "max_drop_m": float((lo - hi)[bad].max())})
    hydro = {}
    for L in levels[1:]:
        pool = z[ny // 2] < L
        below = np.nan_to_num(profiles[L][pool], nan=-9) < L - 1e-3
        hydro[str(L)] = {"cells_below_boundary_level_bed": int(pool.sum()),
                         "cells_with_zs_below_level": int(below.sum())}
    base = np.nan_to_num(profiles[-1.0], nan=0)
    reach = {}
    for L in levels[1:]:
        diff = np.nan_to_num(profiles[L], nan=0) - base
        raised = np.where(diff > 0.01)[0]
        reach[str(L)] = {"backwater_reach_m_from_outlet": float(nx * dx - xc[raised.min()]) if raised.size else 0.0,
                         "level_pool_reach_m_from_outlet": float(min(L / S, nx * dx))}
    return {"basis": "monotonicity (a higher downstream level must not lower any upstream water level) "
                     "and the hydrostatic bound (with inflow, zs >= boundary level wherever the bed is below it)",
            "levels_m": list(levels), "monotonicity_violations": viol, "hydrostatic_bound": hydro,
            "reach": reach, "zs_centreline_every_20_cells": {str(L): np.round(profiles[L][::20], 3).tolist() for L in levels},
            "runs": runs}


# ── c4 ─────────────────────────────────────────────────────────────────
def c4_terrain():
    """Estuary valley: a 2 m incised channel, a floodplain falling to the sea
    boundary, and a low-lying town basin beside the channel near the outlet,
    low enough for rain, river overtopping and surge each to reach it.
    (A first design put the town above every driver's reach; replaced.)"""
    dx, ny, nx = 20.0, 60, 150
    y, x = (np.mgrid[0:ny, 0:nx] + 0.5) * dx
    mid = ny * dx / 2
    z = 0.5 + 0.0005 * (nx * dx - x) + 0.002 * np.abs(y - mid)
    chan = np.abs(y - mid) < 1.5 * dx
    z = np.where(chan, z - 2.0, z)
    r2 = (x - 2600) ** 2 + (y - 420) ** 2
    town = r2 < 140 ** 2
    z = np.where(town, z - 0.8 * (1 - r2 / 140 ** 2), z)
    pts = {"town": (2600.0, 420.0), "upstream_floodplain": (800.0, 400.0), "channel_near_outlet": (2900.0, 600.0)}
    return dx, z, pts


def c4(root):
    dx, z, pts = c4_terrain()
    ny, nx = z.shape
    H = 3600
    R = [(0, 0), (3 * H, 0), (3 * H + 1, 30.0), (6 * H, 30.0), (6 * H + 1, 0), (18 * H, 0)]
    Q = [(0, 2.0), (2 * H, 2.0), (6 * H, 150.0), (10 * H, 2.0), (18 * H, 2.0)]
    Q0 = [(0, 0.0), (18 * H, 0.0)]
    B = lambda pk: [(0, 0.0), ((pk - 3) * H, 0.0), (pk * H, 1.8), ((pk + 3) * H, 0.0), (18 * H, 0.0)]  # noqa: E731
    B0 = [(0, 0.0), (18 * H, 0.0)]
    bnd = [(nx * dx - 10, 10.0), (nx * dx - 10, ny * dx - 10)]
    src = [(10.0, ny * dx / 2)]
    rc = {k: (int(v[1] // dx), int(v[0] // dx)) for k, v in pts.items()}
    combos = {"none": (0, 0, None), "R": (1, 0, None), "Q": (0, 1, None), "B": (0, 0, 6), "RQ": (1, 1, None),
              "RB": (1, 0, 6), "QB": (0, 1, 6), "RQB": (1, 1, 6), "QB_off": (0, 1, 12), "RQB_off": (1, 1, 12)}
    res = {}
    for name, (r_on, q_on, bpk) in combos.items():
        msk = np.ones((ny, nx), int)
        msk[:, -1] = 2
        b = B(bpk) if bpk else B0
        d = os.path.join(root, f"c4_{name}")
        io.write_model(d, z, msk, dx, 18 * H, 1800, rain=R if r_on else None, bnd=bnd,
                       bzs=[(t, v, v) for t, v in b], src=src, dis=Q if q_on else Q0,
                       zsini=float(z.min()) - 1.0)
        r = io.run(d)
        m = io.read_map(d)
        hmax = np.where(m["hmax"][-1] > -1e3, m["hmax"][-1], 0.0)     # dry cells are written as -99999
        land = z > 0.5                                   # floodplain (not channel)
        res[name] = {"hmax_at": {k: round(float(hmax[i, j]), 3) for k, (i, j) in rc.items()},
                     "flooded_land_km2": {str(c): round(float(((hmax > c) & land).sum() * dx * dx / 1e6), 4)
                                          for c in REPORT_CUTS_M},
                     "run": runmeta(r, ny * nx, 18 * H)}
    # checks
    # every decrease is listed with its size; no tolerance is applied
    viol = []
    for joint, parts in (("RQ", ("R", "Q")), ("RB", ("R", "B")), ("QB", ("Q", "B")), ("RQB", ("RQ", "RB", "QB"))):
        for k in rc:
            for p in parts:
                if res[joint]["hmax_at"][k] < res[p]["hmax_at"][k]:
                    viol.append({"joint": joint, "part": p, "point": k,
                                 "joint_m": res[joint]["hmax_at"][k], "part_m": res[p]["hmax_at"][k]})
    inter = {k: round(res["RQB"]["hmax_at"][k] - res["none"]["hmax_at"][k]
                      - sum(res[s]["hmax_at"][k] - res["none"]["hmax_at"][k] for s in ("R", "Q", "B")), 3)
             for k in rc}
    timing = {k: {"aligned": res["RQB"]["hmax_at"][k], "offset": res["RQB_off"]["hmax_at"][k]} for k in rc}
    # closed variant: attribution has a known answer (all inflow is stored)
    closed = {}
    for name, (r_on, q_on) in {"R": (1, 0), "Q": (0, 1), "RQ": (1, 1)}.items():
        d = os.path.join(root, f"c4_closed_{name}")
        io.write_model(d, z, np.ones((ny, nx), int), dx, 18 * H, 18 * H, rain=R if r_on else None,
                       src=src, dis=Q if q_on else Q0, zsini=float(z.min()) - 1.0)
        io.run(d)
        m = io.read_map(d)
        closed[name] = volume(m["h"][-1], dx) - volume(m["h"][0], dx)     # starts dry: h[0] = 0
    area = ny * nx * dx * dx
    known = {"R": series_integral(R, 18 * H) / 1000 / 3600 * area, "Q": series_integral(Q, 18 * H)}
    known["RQ"] = known["R"] + known["Q"]
    return {"basis": "monotonicity (adding a driver must not lower peak depth), driver timing, and in a closed "
                     "domain the known answer: stored volume = input volume per driver",
            "points": pts, "runs": res, "monotonicity_violations": viol,
            "interaction_term_hmax_m": inter, "timing_effect_hmax_m": timing,
            "closed_attribution": {"model_m3": {k: round(v, 2) for k, v in closed.items()},
                                   "known_m3": {k: round(v, 2) for k, v in known.items()},
                                   "removal_attribution_R": round(closed["RQ"] - closed["Q"], 2),
                                   "removal_attribution_Q": round(closed["RQ"] - closed["R"], 2)}}


# ── c5 / c6 ────────────────────────────────────────────────────────────
HOLLOWS = {"small_r60m": (900.0, 1500.0, 60.0), "mid_r120m": (1500.0, 1500.0, 120.0),
           "large_r250m": (2200.0, 1500.0, 250.0)}


def terrain(xx, yy):
    z = 3.0 + 0.001 * (3000 - xx) + 0.5 * np.cos(yy / 3000 * 2 * np.pi)
    for cx, cy, r in HOLLOWS.values():
        z = z - 0.6 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * (r / 2) ** 2))
    return z


def dem_at(dx, extent=3000.0, sub=5):
    n = int(round(extent / dx))
    f = (np.arange(n * sub) + 0.5) * dx / sub
    yy, xx = np.meshgrid(f, f, indexing="ij")
    return terrain(xx, yy).reshape(n, sub, n, sub).mean(axis=(1, 3))    # cell-average, as a DEM aggregates


def hollow_depths(hmax, dx):
    """Max of hmax within each designed hollow's radius (a centre-cell test
    misses a pond that terrain noise shifted sideways)."""
    n = hmax.shape[0]
    c = (np.arange(n) + 0.5) * dx
    yy, xx = np.meshgrid(c, c, indexing="ij")
    out = {}
    for k, (cx, cy, r) in HOLLOWS.items():
        inside = (xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2
        out[k] = round(float(hmax[inside].max()) if inside.any() else float(hmax[int(cy // dx), int(cx // dx)]), 3)
    return out


def hollow_ponded_m3(hmax, dx):
    n = hmax.shape[0]
    c = (np.arange(n) + 0.5) * dx
    yy, xx = np.meshgrid(c, c, indexing="ij")
    return {k: round(float(np.where(((xx - cx) ** 2 + (yy - cy) ** 2 <= r ** 2), np.maximum(hmax, 0), 0).sum()
                           * dx * dx), 1) for k, (cx, cy, r) in HOLLOWS.items()}


def run_terrain(d, z, dx):
    msk = np.ones(z.shape, int)
    msk[:, -1] = 3
    rain = [(0, 60.0), (3600, 60.0), (3601, 0.0), (3 * 3600, 0.0)]
    io.write_model(d, z, msk, dx, 3 * 3600, 3 * 3600, rain=rain)
    r = io.run(d)
    m = io.read_map(d)
    return m["hmax"][-1], r


def c5(root):
    out = {}
    for dx in (10.0, 30.0, 90.0):
        z = dem_at(dx)
        hmax, r = run_terrain(os.path.join(root, f"c5_{int(dx)}m"), z, dx)
        out[f"{int(dx)}m"] = {"hollow_max_depth_m": hollow_depths(hmax, dx),
                              "flooded_km2": {str(c): round(float((hmax > c).sum() * dx * dx / 1e6), 4)
                                              for c in REPORT_CUTS_M},
                              "dem_hollow_depth_relief_m": {k: round(float(z[int(cy // dx), int(cx // dx) - int(3 * r_ // dx)]
                                                                           - z[int(cy // dx), int(cx // dx)]), 3)
                                                            for k, (cx, cy, r_) in HOLLOWS.items()},
                              "run": runmeta(r, z.size, 3 * 3600)}
    return {"basis": "sensitivity only: one analytic terrain, cell-averaged to each grid", "grids": out}


def c6(root, realisations=8, seed=20261031):
    dx = 30.0
    z0 = dem_at(dx)
    h0, _ = run_terrain(os.path.join(root, "c6_ref"), z0, dx)
    ref = h0 > 0.10
    rng = np.random.default_rng(seed)
    corr_cells = 3            # 90 m correlation length: assumed, not measured
    out = {"basis": "sigma values: 0.10 m = pluvial's bluespot depth threshold; 1.24 m = GEDTM30 v1.2 std, "
                    "median over the Hanoi dev box (measured this session); 0.50 m = an intermediate. "
                    "Correlation length 90 m is an assumption (error structure not measured).",
           "reference_hollow_depth_m": hollow_depths(h0, dx),
           "reference_hollow_peak_ponded_m3": hollow_ponded_m3(h0, dx), "sigmas": {}}
    for sigma in (0.10, 0.50, 1.24):
        wet = {k: 0 for k in HOLLOWS}
        jac, area = [], []
        runs, ponded = [], {k: [] for k in HOLLOWS}
        for k in range(realisations):
            z = z0 + smooth_noise(z0.shape, sigma, corr_cells, rng)
            hmax, r = run_terrain(os.path.join(root, f"c6_s{sigma}_{k}"), z, dx)
            hd = hollow_depths(hmax, dx)
            pv = hollow_ponded_m3(hmax, dx)
            for h in HOLLOWS:
                wet[h] += hd[h] > 0.10
                ponded[h].append(pv[h])
            f = hmax > 0.10
            jac.append(float((f & ref).sum() / max((f | ref).sum(), 1)))
            area.append(float(f.sum() * dx * dx / 1e6))
            runs.append(r["wall_s"])
        out["sigmas"][str(sigma)] = {"hollow_wet_fraction": {h: wet[h] / realisations for h in HOLLOWS},
                                     "hollow_peak_ponded_m3": {h: {"median": float(np.median(ponded[h])),
                                                                   "min": float(min(ponded[h])),
                                                                   "max": float(max(ponded[h]))} for h in HOLLOWS},
                                     "jaccard_vs_reference": {"median": float(np.median(jac)), "min": float(min(jac)),
                                                              "max": float(max(jac))},
                                     "flooded_km2_cut0.10": {"median": float(np.median(area)), "min": float(min(area)),
                                                             "max": float(max(area))},
                                     "reference_flooded_km2": float(ref.sum() * dx * dx / 1e6),
                                     "wall_s_each": runs}
    return out


CASES = {"c1": c1, "c2": c2, "c3": c3, "c4": c4, "c5": c5, "c6": c6}

if __name__ == "__main__":
    root, outpath = sys.argv[1], sys.argv[2]
    which = sys.argv[3:] or list(CASES)
    import json
    results = json.load(open(outpath)) if os.path.exists(outpath) else {}
    results["image"] = io.IMAGE
    for c in which:
        t0 = time.time()
        results[c] = CASES[c](root)
        results[c]["case_wall_s"] = round(time.time() - t0, 1)
        io.save_json(outpath, results)
        print(c, "done", results[c]["case_wall_s"], "s")
