"""
Round 3, rain (R29): SFINCS rain-on-grid with a drainage loss, as a feature for 311 units.

Per unit (one storm on one 8 km box):
- grid: 20 m, from the box's cached 3DEP 10 m DEM (fine_feats.dem10), each 20 m cell = the minimum of its
  2 x 2 10 m pixels so street-level low spots survive; closed edges (msk 1 everywhere);
- rain: the storm's half-hourly IMERG mean over the box, uniform, [peak - 1 d, peak + 2 d) (the label window);
- drainage loss: an initial abstraction. The drainage network removes the first D mm of the storm's rain;
  the rest is rain-on-grid with no further loss, so it runs off and ponds where it collects.
  Members fixed: D = 0.25 and 0.5 of the storm's box-mean total.
- Tried first, recorded here and not tuned on labels:
  - SFINCS `qinf` (a constant loss on every cell) at 10 / 25 mm/h, then at 0.25 / 0.5 of the storm's peak rate,
    left every cell dry;
  - IMERG box-mean rates are low (one Chicago storm peaked at 13 mm/h), and a continuous loss also stops runoff
    on every upslope cell and drains every pond;
  - with no loss at all, 23 % of that box was wet above 5 cm.
- manning 0.04, huthresh 0.01 m (as round 2's Ida and Valencia runs).
Output: hmax on the unit's 30 m grid (max over the 20 m cells whose centres fall in each cell):
features `sf_hmax_q10`, `sf_hmax_q25`. One Docker run at a time, memory capped (sfincs_io.run).

    python -m experiments.flood_round3.sfincs_drain          # every 311 DEV unit (resumable)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import sys

import numpy as np

CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/sfincs_drain")
QINF = (0.25, 0.5)            # initial abstraction, as fractions of the storm total
DX = 20.0
MANNING = 0.04
HUTHRESH = 0.01
FEATS = tuple(f"sf_hmax_f{int(q * 100)}" for q in QINF)


def imerg_halfhourly(ee, bbox, t0, t1):
    """[(t_s from t0, mm/h)] box-mean IMERG half-hourly rate (cached)."""
    from experiments.flood_round3 import diagnose_ee as D
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"imerg_{'_'.join(f'{x:.3f}' for x in bbox)}_{t0}_{t1}.json")
    if not os.path.exists(p):
        col = ee.ImageCollection(D.IMERG).select("precipitation").filterDate(t0, t1)
        g = ee.Geometry.Rectangle(list(bbox))
        fc = col.map(lambda im: ee.Feature(None, {"t": im.get("system:time_start"),
                                                   "v": im.reduceRegion(ee.Reducer.mean(), g, 10000).get("precipitation")}))
        info = fc.aggregate_array("t").getInfo(), fc.aggregate_array("v").getInfo()
        json.dump(list(zip(*info)), open(p, "w"))
    rows = sorted(json.load(open(p)))
    a = dt.datetime.fromisoformat(t0).replace(tzinfo=dt.timezone.utc).timestamp() * 1000
    return [((t - a) / 1000.0, float(v or 0.0)) for t, v in rows]


def dem20(dem_path):
    import rasterio
    with rasterio.open(dem_path) as s:
        z = s.read(1).astype(np.float64)
        tr = s.transform
    bad = ~np.isfinite(z) | (z < -1000)
    z = np.where(bad, np.nan, z)
    H, W = (z.shape[0] // 2) * 2, (z.shape[1] // 2) * 2
    z = z[:H, :W].reshape(H // 2, 2, W // 2, 2)
    z = np.nanmin(np.nanmin(z, axis=3), axis=1)
    z = np.where(np.isfinite(z), z, np.nanmax(z))           # no-data -> high ground (dry, does not pond)
    return z, (tr.a * 2, tr.b, tr.c, tr.d, tr.e * 2, tr.f)


def run_unit(n, ee=None):
    from experiments.flood_core.sfincs import sfincs_io as S
    from experiments.flood_round3 import fine_feats as FF
    from experiments.flood_round3 import rain311 as R3
    outp = os.path.join(CACHE, f"{n}.npz")
    if os.path.exists(outp):
        z = np.load(outp)
        return {k: z[k] for k in FEATS}
    meta = json.loads(str(np.load(os.path.join(R3.REFS, f"{n}.npz"))["meta"]))
    if ee is None:
        from experiments.flood_round3 import diagnose_ee as D
        ee = D._init()
    g = meta["grid"]
    dem_p = FF.dem10(ee, meta["box"], meta["bbox"], g["crs"])
    z_top, tr = dem20(dem_p)
    w0, w1 = meta["window"]
    rain = imerg_halfhourly(ee, meta["bbox"], w0, w1)
    tstop = (dt.datetime.fromisoformat(w1) - dt.datetime.fromisoformat(w0)).total_seconds()
    feats = {}
    t_s = np.array([t for t, _ in rain])
    rate = np.array([v for _, v in rain])
    cum = np.cumsum(rate * 0.5)                         # mm at the end of each half hour
    for fq in QINF:
        D_mm = fq * float(cum[-1]) if len(cum) else 0.0
        eff = np.diff(np.r_[0.0, np.maximum(cum - D_mm, 0.0)]) / 0.5      # mm/h after the abstraction
        rain_eff = [(float(t), float(v)) for t, v in zip(t_s, eff)]
        d = os.path.join(CACHE, "runs", f"{n}_f{int(fq * 100)}")
        z = z_top[::-1, :]
        msk = np.ones(z.shape, int)
        S.write_model(d, z, msk, DX, tstop, 3600.0, manning=MANNING, rain=rain_eff,     # times from TREF, in s
                      extra={"huthresh": HUTHRESH, "x0": tr[2], "y0": tr[5] + tr[4] * z.shape[0]})
        r = S.run(d)
        if r["exit_code"] != "0":
            raise RuntimeError(f"SFINCS failed for {n} q{q}: {r.get('log_tail')}")
        m = S.read_map(d)
        h = np.squeeze(np.asarray(m.get("hmax", m.get("zsmax"))))[::-1, :]        # back to top-row-first
        if m.get("hmax") is None:
            h = h - z_top
        h = np.nan_to_num(np.asarray(h, np.float64), nan=0.0)
        h[h < 0] = 0.0                      # SFINCS fill value where a cell never got wet
        feats[f"sf_hmax_f{int(fq * 100)}"] = to_unit_grid(h, tr, g)
        shutil.rmtree(d, ignore_errors=True)
    np.savez_compressed(outp, **feats)
    print(n, {k: round(float(np.nanpercentile(v, 99)), 3) for k, v in feats.items()}, flush=True)
    return feats


def to_unit_grid(h, tr, grid):
    """Max of the 20 m cells whose centres fall in each 30 m unit cell (flat float32)."""
    H, W = grid["shape"]
    t = grid["transform"]
    rr, cc = np.mgrid[0:h.shape[0], 0:h.shape[1]]
    x = tr[2] + (cc + 0.5) * tr[0]
    y = tr[5] + (rr + 0.5) * tr[4]
    c30 = np.floor((x - t[2]) / t[0]).astype(int)
    r30 = np.floor((y - t[5]) / t[4]).astype(int)
    ok = (r30 >= 0) & (r30 < H) & (c30 >= 0) & (c30 < W)
    out = np.full(H * W, np.nan)
    idx = r30[ok] * W + c30[ok]
    np.fmax.at(out, idx, h[ok])
    return out.astype(np.float32)


def main(argv=None):
    from experiments.flood_round3 import diagnose_ee as D
    from experiments.flood_round3 import rain311 as R3
    ee = D._init()
    units = json.load(open(os.path.join(R3.REFS, "units.json")))
    for n in sorted(units):
        try:
            run_unit(n, ee)
        except Exception as e:          # noqa: BLE001
            print(n, "FAILED", type(e).__name__, str(e)[:200], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
