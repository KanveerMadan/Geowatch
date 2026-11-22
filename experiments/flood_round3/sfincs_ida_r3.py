"""
Round 3: Ida compound SFINCS again, now with infiltration (R26's stated prerequisite).

R26 found rain-on-grid with no infiltration wets ~100 % of the box, so peak depth ranked below HAND.
This rerun keeps round 2's Ida case exactly (DEM, sea mask, IMERG rain, Grand Isle surge, settings; imported
from experiments.flood_round2.sfincs.ida, which is not changed) and adds SFINCS constant infiltration `qinf`.
Members fixed now: qinf = 5 and 10 mm/h on the base member. Coastal Louisiana soils are clays and marsh with
low saturated conductivity, so these are generous upper values; a member is usable as a feature only if its wet
share on the DEV box is < 1 (R26).

    python -m experiments.flood_round3.sfincs_ida_r3 run 5|10
    python -m experiments.flood_round3.sfincs_ida_r3 score        -> results/ida_sfincs_infil_r3.json
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
RUNS = os.path.expanduser("~/.cache/geowatch/flood_round3/ida_infil")
QINF = (5.0, 10.0)


def write_member(q):
    from experiments.flood_core.sfincs import sfincs_io as S
    from experiments.flood_round2.sfincs import ida as I
    d = os.path.join(RUNS, f"base_qinf{int(q)}")
    os.makedirs(d, exist_ok=True)
    z_top, water_top, t_s, level = I.member_setup("base")
    z, water = z_top[::-1, :], water_top[::-1, :]
    msk = np.ones(z.shape, int)
    ring = np.zeros(z.shape, bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    msk[ring & water] = 2
    r, c = np.nonzero(msk == 2)
    step = max(1, len(r) // 30)
    pts = [(I.X0 + I.DX * (c[i] + 0.5), I.Y0 + I.DX * (r[i] + 0.5)) for i in range(0, len(r), step)]
    bzs = [[float(t)] + [float(v)] * len(pts) for t, v in zip(t_s, level)]
    S.write_model(d, z, msk, I.DX, float(t_s[-1]), 3600.0, manning=I.MANNING, bnd=pts, bzs=bzs,
                  zsini=float(level[0]),
                  extra={"huthresh": I.HUTHRESH, "dtmax": I.DTMAX, "x0": I.X0, "y0": I.Y0, "qinf": q,
                         "tref": "20210829 000000", "tstart": "20210829 000000",
                         "tstop": "20210831 120000", "netamprfile": "precip.nc", "storecumprcp": 1})
    shutil.copy(os.path.join(I.CACHE, "precip.nc"), os.path.join(d, "precip.nc"))
    return d


def run(q):
    from experiments.flood_core.sfincs import sfincs_io as S
    from experiments.flood_round2.sfincs import ida as I
    d = os.path.join(RUNS, f"base_qinf{int(q)}")
    if os.path.exists(os.path.join(d, "summary.json")):
        return json.load(open(os.path.join(d, "summary.json")))
    d = write_member(q)
    r = S.run(d)
    out = {"member": f"base_qinf{int(q)}", "qinf_mm_h": q, **{k: v for k, v in r.items() if k != "log_tail"}}
    if r["exit_code"] == "0" and os.path.exists(os.path.join(d, "sfincs_map.nc")):
        m = S.read_map(d)
        np.save(os.path.join(d, "hmax.npy"), np.squeeze(np.asarray(m["hmax"])).astype(np.float32))
        os.remove(os.path.join(d, "sfincs_map.nc"))
        for f in ("precip.nc",):
            if os.path.exists(os.path.join(d, f)):
                os.remove(os.path.join(d, f))
    else:
        out["log_tail"] = r["log_tail"]
    json.dump(out, open(os.path.join(d, "summary.json"), "w"), indent=1, default=str)
    print(json.dumps(out, default=str)[:600], flush=True)
    return out


def score():
    """round 2's Ida score() applied to these runs (same reference, same metrics)."""
    from experiments.flood_round2.sfincs import ida as I
    saved = I.CACHE, I.OUT
    tmp = os.path.join(RUNS, "_score")
    os.makedirs(os.path.join(tmp, "runs"), exist_ok=True)
    for f in ("prep_meta.json",):
        shutil.copy(os.path.join(I.CACHE, f), os.path.join(tmp, f))
    for q in QINF:
        src = os.path.join(RUNS, f"base_qinf{int(q)}")
        dst = os.path.join(tmp, "runs", f"base_qinf{int(q)}")
        if os.path.exists(os.path.join(src, "hmax.npy")):
            os.makedirs(dst, exist_ok=True)
            for f in ("hmax.npy", "summary.json"):
                shutil.copy(os.path.join(src, f), os.path.join(dst, f))
    I.CACHE, I.OUT = tmp, tmp
    try:
        I.score()
    finally:
        I.CACHE, I.OUT = saved
    res = json.load(open(os.path.join(tmp, "ida_sfincs.json")))
    res["note"] = "R26 rerun with infiltration (qinf); round-2 Ida case unchanged"
    json.dump(res, open(os.path.join(OUT, "ida_sfincs_infil_r3.json"), "w"), indent=1)
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    if a[0] == "run":
        run(float(a[1]))
        return 0
    return score()


if __name__ == "__main__":
    raise SystemExit(main())
