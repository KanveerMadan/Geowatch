"""
P0b-2: shallow-flow threshold (`huthresh`, documented default 0.05 m,
"minimum flow depth limiter") convergence.

A. Kinematic plane (c2 geometry: 1 km, slope 0.01, n = 0.04), analytic steady
   state h(x) = (n i x / sqrt(S))^(3/5), at two rain rates (100 and 20 mm/h)
   and huthresh 0.05 ... 0.0001 m, dx = 10 m.
B. Grid refinement at a fixed small huthresh (dx 5 / 10 / 20 m), to measure
   the discretisation error that a threshold reduction cannot remove.
C. The c5 analytic terrain at 30 m (hollows, outflow boundary, 60 mm/h for
   1 h) at huthresh 0.05 / 0.01 / 0.001 m: effect on ponding and area.

No threshold decides convergence. The basis reported is the comparison of
the threshold-induced error with the grid-refinement error (B): reducing
huthresh further cannot help once its effect is below that.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfincs_io as io  # noqa: E402
from p0_cases import HOLLOWS, REPORT_CUTS_M, dem_at, hollow_depths  # noqa: E402

S, N_MAN, L = 0.01, 0.04, 1000.0
HUT = (0.05, 0.02, 0.01, 0.005, 0.002, 0.001, 0.0005, 0.0002, 0.0001)


def plane(root, name, dx, i_mmh, hut):
    nx, ny = int(L / dx), max(6, int(120 / dx))
    xc = (np.arange(nx) + 0.5) * dx
    z = np.tile(S * (L - xc), (ny, 1))
    msk = np.ones((ny, nx), int)
    msk[:, -1] = 3
    d = os.path.join(root, f"hut_{name}")
    io.write_model(d, z, msk, dx, 3 * 3600, 3 * 3600, manning=N_MAN, rain=[(0, i_mmh), (3 * 3600, i_mmh)],
                   extra={"huthresh": hut})
    r = io.run(d)
    m = io.read_map(d)
    h = m["h"][-1][ny // 2]
    analytic = (N_MAN * i_mmh / 1000 / 3600 * xc / np.sqrt(S)) ** 0.6
    keep = (xc > 50) & (xc < L - 50)
    rel = (h[keep] - analytic[keep]) / analytic[keep]
    log = open(os.path.join(d, "sfincs_log.txt")).read()
    import re
    adt = float(re.findall(r"Average time step \(s\)\s*:\s*([\d.]+)", log)[-1])
    return {"dx": dx, "rain_mmh": i_mmh, "huthresh": hut,
            "rel_err_median": float(np.median(rel)), "rel_err_max_abs": float(np.max(np.abs(rel))),
            "rel_err_first_10pct_of_slope": float(np.median(rel[: max(1, len(rel) // 10)])),
            "analytic_range_m": [float(analytic[keep].min()), float(analytic[keep].max())],
            "avg_dt_s": adt, "solver_s": r["solver_reported_s"], "rss_mib": r["sfincs_peak_rss_mib"]}


def terrain_case(root, hut):
    dx = 30.0
    z = dem_at(dx)
    msk = np.ones(z.shape, int)
    msk[:, -1] = 3
    d = os.path.join(root, f"hut_terrain_{hut}")
    io.write_model(d, z, msk, dx, 3 * 3600, 3 * 3600,
                   rain=[(0, 60.0), (3600, 60.0), (3601, 0.0), (3 * 3600, 0.0)], extra={"huthresh": hut})
    r = io.run(d)
    hmax = np.where(io.read_map(d)["hmax"][-1] > -1e3, io.read_map(d)["hmax"][-1], 0.0)
    return {"huthresh": hut, "hollow_max_depth_m": hollow_depths(hmax, dx),
            "flooded_km2": {str(c): round(float((hmax > c).sum() * dx * dx / 1e6), 4) for c in REPORT_CUTS_M},
            "solver_s": r["solver_reported_s"]}


def main(root, outpath):
    res = {"A_threshold_sweep": [], "B_grid_refinement": [], "C_terrain": []}
    for i_mmh in (100.0, 20.0):
        for hut in HUT:
            res["A_threshold_sweep"].append(plane(root, f"A_{int(i_mmh)}_{hut}", 10.0, i_mmh, hut))
    for i_mmh in (100.0, 20.0):
        for dx in (5.0, 10.0, 20.0):
            res["B_grid_refinement"].append(plane(root, f"B_{int(i_mmh)}_{int(dx)}", dx, i_mmh, 0.0001))
    for hut in (0.05, 0.01, 0.001):
        res["C_terrain"].append(terrain_case(root, hut))
    io.save_json(outpath, res)
    for k, rows in res.items():
        print(k)
        for r in rows:
            print("  ", {kk: (round(v, 4) if isinstance(v, float) else v) for kk, v in r.items()})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
