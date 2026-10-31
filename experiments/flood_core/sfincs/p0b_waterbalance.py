"""
P0b-1: what causes c1's water-balance saw-tooth (up to 0.12 % during rain,
resetting about every 30 min)?

Hypothesis under test: precipitation forcing is refreshed on the meteo
update interval `dtwnd` (documented default 1800 s, "time-interval on which
spatially varying meteo conditions (... precipitation ...) are updated from
file"), and the residual comes from how the rate is applied between updates.

Each variant is one change from the c1 'steady' run (bowl terrain, steady
50 mm/h, 3 h, closed basin, starts dry):
  dtwnd 60 / 600 / 1800 / 3600       -> reset period should follow dtwnd
  dtout 300 (vs 600)                 -> rules output timing in or out
  flat basin                         -> no flow: isolates forcing from routing
  advection 0 (SFINCS-LIE)           -> continuity scheme change
Confirmation variants cap the internal step (dtmax = 2.0 / 1.0 s, both
divisors of 600 s) so that steps land exactly on output times.
Every variant writes SFINCS's own cumulative precipitation (storecumprcp=1,
dtmaxout = dtout), so the stored volume is compared with (a) the rain the
input file implies and (b) the rain SFINCS reports it applied.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfincs_io as io  # noqa: E402
from p0_cases import volume  # noqa: E402

DX, N, RATE, TSTOP = 10.0, 100, 50.0, 10800


def terrain(flat=False):
    y, x = (np.mgrid[0:N, 0:N] + 0.5) * DX
    if flat:
        return np.zeros((N, N))
    return 5.0 * (((x - 500) ** 2 + (y - 500) ** 2) / 500 ** 2) + 0.3 * np.sin(x / 37) * np.cos(y / 53)


def variant(root, name, dtout=600, flat=False, extra=None):
    z = terrain(flat)
    d = os.path.join(root, f"wb_{name}")
    ex = {"storecumprcp": 1}
    ex.update(extra or {})
    io.write_model(d, z, np.ones_like(z, int), DX, TSTOP, dtout, rain=[(0, RATE), (TSTOP, RATE)],
                   zsini=float(z.min()) - 1.0, extra=ex)
    # dtmaxout = dtout so cumprcp is written at the same times as the maps
    p = os.path.join(d, "sfincs.inp")
    txt = open(p).read().replace(f"dtmaxout      = {TSTOP}", f"dtmaxout      = {dtout}")
    open(p, "w").write(txt)
    r = io.run(d)
    m = io.read_map(d)
    t = m["time"].astype(float)
    area = N * N * DX * DX
    stored = np.array([volume(m["h"][i], DX) for i in range(len(t))])
    implied = RATE / 1000 / 3600 * t * area
    out = {"output_time_s": t.tolist(), "resid_vs_input_m3": (stored - implied).round(3).tolist(),
           "resid_vs_input_rel_max_abs": float(np.max(np.abs((stored - implied)[1:] / implied[1:]))),
           "run": {k: r[k] for k in ("wall_s", "sfincs_peak_rss_mib", "solver_reported_s")}}
    if "cumprcp" in m:
        tm = m["timemax"].astype(float)
        cum = np.array([float(np.nansum(np.where(m["cumprcp"][i] > -1e3, m["cumprcp"][i], 0))) / 1000 * DX * DX
                        if np.nanmax(m["cumprcp"][i]) > 1 else float(np.nansum(np.where(m["cumprcp"][i] > -1e3, m["cumprcp"][i], 0))) * DX * DX
                        for i in range(len(tm))])
        out["cumprcp_units_note"] = "cumprcp read as mm if its max > 1, else m"
        out["timemax_s"] = tm.tolist()
        out["cumprcp_m3"] = cum.round(3).tolist()
        # SFINCS-applied rain vs input-implied rain, at the timemax stamps
        out["applied_minus_implied_m3"] = (cum - RATE / 1000 / 3600 * tm * area).round(3).tolist()
        stored_at_tm = np.interp(tm, t, stored)
        out["stored_minus_applied_m3"] = (stored_at_tm - cum).round(3).tolist()
    return out


def main(root, outpath):
    res = {"hypothesis": "residual saw-tooth follows dtwnd (meteo update interval, default 1800 s)"}
    for name, kw in {"dtwnd60": {"extra": {"dtwnd": 60}}, "dtwnd600": {"extra": {"dtwnd": 600}},
                     "dtwnd1800": {"extra": {"dtwnd": 1800}}, "dtwnd3600": {"extra": {"dtwnd": 3600}},
                     "dtout300": {"dtout": 300}, "flat": {"flat": True}, "flat_dtwnd60": {"flat": True, "extra": {"dtwnd": 60}},
                     "lie_advection0": {"extra": {"advection": 0}},
                     # confirmation: a time step that divides dtout makes steps land on output times
                     "flat_dtmax2": {"flat": True, "extra": {"dtmax": 2.0}},
                     "bowl_dtmax2": {"extra": {"dtmax": 2.0}},
                     "bowl_dtmax1": {"extra": {"dtmax": 1.0}}}.items():
        res[name] = variant(root, name, **kw)
        print(name, "max rel", round(res[name]["resid_vs_input_rel_max_abs"], 6),
              "resid", res[name]["resid_vs_input_m3"][:10])
    io.save_json(outpath, res)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
