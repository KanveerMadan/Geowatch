"""
Phase C: SFINCS for Hurricane Ian at Fort Myers Beach (DEV unit
fort_myers_beach, storm cluster ian_2022). It is a coastal surge case, with
rain on top.

    python -m experiments.flood_round2.sfincs.fortmyers prep          # DEM, sea mask, rain, gauge
    python -m experiments.flood_round2.sfincs.fortmyers run <member>  # base | surge2x | glo30 | lidar_e1
    python -m experiments.flood_round2.sfincs.fortmyers score

Domain:
- EPSG:32617, x 394200–420300, y 2916000–2938020, 30 m (870 x 734 cells, 575 km²).
- It covers Estero Island, Estero Bay, San Carlos Island and the Caloosahatchee mouth.

Terrain:
- USGS 3DEP 10 m (USGS/3DEP/10m_collection; NAVD88, public domain), bilinear to 30 m.
- The glo30 member uses GLO-30 (EGM2008), shifted to NAVD88 by the median (3DEP − GLO-30) over dry land in the domain (datum reconciliation).
- 3DEP has no bathymetry. Water cells (JRC occurrence ≥ 80 %) are lowered to at most SEA_FLOOR_M. That is an assumption (Estero Bay and the nearshore Gulf are mostly 1–3 m deep on NOAA chart 11426). It is logged (R5).

Sea boundary:
- Domain-edge cells that are water (msk = 2), forced by NOAA CO-OPS 8725520 Fort Myers 6-min water levels (NAVD88, metres), hourly means.
- The gauge is in the Caloosahatchee ~10 km from the open coast, so it understates the open-coast peak. Member `surge2x` doubles the non-tidal residual (gauge minus predicted tide) as an upper bracket. It is a sensitivity, not a calibration (R5).
- The Naples gauge (8725110) stopped recording at its peak (2.07 m), so it is not used.

Rain: IMERG V07, half-hourly, 2022-09-27 12:00 to 2022-09-30 00:00 UTC.

Settings, as Valencia (D16): huthresh 0.001, dtmax 4 s (divides the 3600 s output interval), manning 0.04 everywhere.

Reference:
- The DEV unit's Sentinel-1 VV-drop labels (4 km box, flood_learned table: flooded / dry / unobserved).
- S1 is blind among buildings (D20), and Fort Myers Beach is built-up. USGS STN high-water marks would be the better reference, but the STN API answered 301 (moved, no documented replacement) on 2026-11-21 (R4).
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_round2/fortmyers")
CRS = "EPSG:32617"
X0, X1, Y0, Y1 = 394200.0, 420300.0, 2916000.0, 2938020.0
DX = 30.0
T0, T1 = "2022-09-27T12:00:00", "2022-09-30T00:00:00"
GAUGE = "8725520"
SEA_FLOOR_M = -1.5
LIDAR_SIGMA = 0.10              # 3DEP QL2 vertical accuracy RMSEz <= 10 cm (USGS LBS v2)
HUTHRESH, DTMAX, MANNING = 0.001, 4.0, 0.04
WET_M = 0.10
DEV_BOX = "fort_myers_beach"


def shape():
    return int(round((Y1 - Y0) / DX)), int(round((X1 - X0) / DX))


def _t30():
    from affine import Affine
    return Affine(DX, 0, X0, 0, -DX, Y1)


def prep():
    import ee
    import xarray as xr
    from affine import Affine
    from ingestion.gee_client import initialize_gee
    from susceptibility.hydro_rasters import compute_pixels
    initialize_gee()
    os.makedirs(CACHE, exist_ok=True)
    H, W = shape()
    t = _t30()
    dcol = ee.ImageCollection("USGS/3DEP/10m_collection").filterBounds(
        ee.Geometry.Rectangle([-82.1, 26.3, -81.75, 26.6]))
    dep = dcol.mosaic().select("elevation").setDefaultProjection(
        ee.Image(dcol.first()).select("elevation").projection())
    z3 = compute_pixels(dep.resample("bilinear").rename("z"), t, (H, W), CRS, "3dep")["z"]
    col = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").filterBounds(
        ee.Geometry.Rectangle([-82.1, 26.3, -81.75, 26.6]))
    g = col.mosaic().select("DEM").setDefaultProjection(ee.Image(col.first()).select("DEM").projection())
    zg = compute_pixels(g.resample("bilinear").rename("z"), t, (H, W), CRS, "glo30")["z"]
    occ = compute_pixels(ee.Image("JRC/GSW1_4/GlobalSurfaceWater").select("occurrence").unmask(0)
                         .rename("o"), t, (H, W), CRS, "jrc")["o"]
    water = occ >= 80.0
    land = ~water & np.isfinite(z3) & np.isfinite(zg) & (z3 > 0.5)
    off = float(np.median(z3[land] - zg[land]))
    np.save(os.path.join(CACHE, "z3dep.npy"), z3.astype(np.float32))
    np.save(os.path.join(CACHE, "zglo30.npy"), (zg + off).astype(np.float32))
    np.save(os.path.join(CACHE, "water.npy"), water)
    # rain (IMERG, 1 km grid in the domain CRS)
    pc = (ee.ImageCollection("NASA/GPM_L3/IMERG_V07").filterDate(T0, T1)
          .select("precipitation").sort("system:time_start"))
    n = pc.size().getInfo()
    times = pc.aggregate_array("system:time_start").getInfo()
    km = 1000.0
    Wk, Hk = int(np.ceil((X1 - X0) / km)), int(np.ceil((Y1 - Y0) / km))
    t1k = Affine(km, 0, X0, 0, -km, Y0 + Hk * km)
    lst = pc.toList(n)
    P = np.stack([compute_pixels(ee.Image(lst.get(i)).resample("bilinear").rename("p"), t1k, (Hk, Wk), CRS,
                                 f"imerg {i}")["p"] for i in range(n)]).astype(np.float32)
    P = np.nan_to_num(P)[:, ::-1, :]
    tmin = (np.array(times) - np.datetime64(T0, "ms").astype(np.int64)) / 60000.0
    ds = xr.Dataset({"Precipitation": (("time", "y", "x"), P)},
                    coords={"time": tmin, "y": Y0 + km * (np.arange(Hk) + 0.5), "x": X0 + km * (np.arange(Wk) + 0.5)})
    ds["time"].attrs["units"] = f"minutes since {T0.replace('T', ' ')}"
    ds["Precipitation"].attrs["units"] = "mm/hr"
    ds.to_netcdf(os.path.join(CACHE, "precip.nc"), engine="scipy")
    # gauge: observed and predicted (tide), NAVD88 metres, hourly means
    gauge = {}
    for prod in ("water_level", "predictions"):
        p = os.path.join(CACHE, f"coops_{GAUGE}_{prod}.json")
        if not os.path.exists(p):
            import urllib.request
            url = ("https://api.tidesandcurrents.noaa.gov/api/prod/datagetter?"
                   f"product={prod}&application=geowatch_research&begin_date=20220927&end_date=20220930"
                   f"&datum=NAVD&station={GAUGE}&time_zone=gmt&units=metric&format=json&interval=6")
            urllib.request.urlretrieve(url, p)
        d = json.load(open(p))
        rows = d.get("data") or d.get("predictions")
        ts = np.array([np.datetime64(r["t"].replace(" ", "T")) for r in rows if r["v"]])
        vs = np.array([float(r["v"]) for r in rows if r["v"]])
        gauge[prod] = (ts, vs)
    hrs = np.arange(np.datetime64(T0), np.datetime64(T1) + np.timedelta64(1, "h"), np.timedelta64(1, "h"))
    obs = np.array([np.nanmean(gauge["water_level"][1][(gauge["water_level"][0] >= h - np.timedelta64(30, "m"))
                                                      & (gauge["water_level"][0] < h + np.timedelta64(30, "m"))])
                    for h in hrs])
    tide = np.interp(hrs.astype("datetime64[s]").astype(float), gauge["predictions"][0].astype("datetime64[s]").astype(float),
                     gauge["predictions"][1])
    obs = np.where(np.isfinite(obs), obs, tide)
    np.savez(os.path.join(CACHE, "gauge_hourly.npz"), t_s=(hrs - np.datetime64(T0)).astype("timedelta64[s]").astype(float),
             obs=obs, tide=tide)
    meta = {"datum_offset_3dep_minus_glo30_m": off, "water_cells": int(water.sum()),
            "z3dep_finite": float(np.isfinite(z3).mean()), "imerg_frames": n,
            "rain_domain_mean_total_mm": float(P.sum(0).mean() * 0.5), "gauge_peak_m": float(np.nanmax(obs)),
            "residual_peak_m": float(np.nanmax(obs - tide))}
    json.dump(meta, open(os.path.join(CACHE, "prep_meta.json"), "w"), indent=1)
    print(json.dumps(meta), flush=True)


def smooth_noise(shp, sigma, corr_cells, rng):
    from scipy.ndimage import gaussian_filter
    f = gaussian_filter(rng.standard_normal(shp), corr_cells)
    return f / f.std() * sigma


def member_setup(member):
    z = np.load(os.path.join(CACHE, "zglo30.npy" if member == "glo30" else "z3dep.npy")).astype(np.float64)
    zg = np.load(os.path.join(CACHE, "zglo30.npy"))
    z = np.where(np.isfinite(z), z, zg)                 # 3DEP gaps: datum-shifted GLO-30
    water = np.load(os.path.join(CACHE, "water.npy"))
    z = np.where(water, np.minimum(np.nan_to_num(z, nan=SEA_FLOOR_M), SEA_FLOOR_M), z)
    z = np.where(np.isfinite(z), z, SEA_FLOOR_M)
    if member.startswith("lidar_e"):
        rng = np.random.default_rng(20261121 + int(member[len("lidar_e"):]))
        s = LIDAR_SIGMA * np.sqrt(0.5)
        noise = smooth_noise(z.shape, s, 100 / DX, rng) + smooth_noise(z.shape, s, 2000 / DX, rng)
        z = np.where(water, z, z + noise)
    g = np.load(os.path.join(CACHE, "gauge_hourly.npz"))
    level = g["obs"] if member != "surge2x" else g["tide"] + 2.0 * (g["obs"] - g["tide"])
    return z.astype(np.float32), water, g["t_s"], level


def write_member(member):
    import shutil
    from experiments.flood_core.sfincs import sfincs_io as S
    d = os.path.join(CACHE, "runs", member)
    os.makedirs(d, exist_ok=True)
    z_top, water_top, t_s, level = member_setup(member)
    z, water = z_top[::-1, :], water_top[::-1, :]
    msk = np.ones(z.shape, int)
    ring = np.zeros(z.shape, bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    msk[ring & water] = 2
    r, c = np.nonzero(msk == 2)
    step = max(1, len(r) // 30)
    pts = [(X0 + DX * (c[i] + 0.5), Y0 + DX * (r[i] + 0.5)) for i in range(0, len(r), step)]
    tstop = float(t_s[-1])
    bzs = [[float(t)] + [float(v)] * len(pts) for t, v in zip(t_s, level)]
    S.write_model(d, z, msk, DX, tstop, 3600.0, manning=MANNING, bnd=pts, bzs=bzs,
                  zsini=float(level[0]),
                  extra={"huthresh": HUTHRESH, "dtmax": DTMAX, "x0": X0, "y0": Y0,
                         "tref": "20220927 120000", "tstart": "20220927 120000",
                         "tstop": "20220930 000000", "netamprfile": "precip.nc", "storecumprcp": 1})
    shutil.copy(os.path.join(CACHE, "precip.nc"), os.path.join(d, "precip.nc"))
    json.dump({"member": member, "boundary_cells": int((msk == 2).sum()), "boundary_points": len(pts),
               "peak_boundary_m": float(np.max(level))}, open(os.path.join(d, "member.json"), "w"), indent=1)
    return d


def run(member):
    from experiments.flood_core.sfincs import sfincs_io as S
    d = os.path.join(CACHE, "runs", member)
    if os.path.exists(os.path.join(d, "summary.json")):
        return json.load(open(os.path.join(d, "summary.json")))
    if os.path.exists(os.path.join(d, "sfincs_map.nc")) and os.path.exists(os.path.join(d, "sfincs_log.txt")):
        # the run finished but its map was not read (R13: h5py missing in that shell): extract, do not re-run
        import re
        txt = open(os.path.join(d, "sfincs_log.txt")).read()
        m_ = re.search(r"Total time\s*:\s*([0-9.]+)", txt)
        r = {"exit_code": "0", "solver_reported_s": float(m_.group(1)) if m_ else None,
             "wall_s": None, "sfincs_peak_rss_mib": None, "note": "extracted from an existing run (R13)"}
    else:
        d = write_member(member)
        r = S.run(d)
    out = {"member": member, **{k: v for k, v in r.items() if k != "log_tail"}}
    if r["exit_code"] == "0" and os.path.exists(os.path.join(d, "sfincs_map.nc")):
        m = S.read_map(d)
        np.save(os.path.join(d, "hmax.npy"), np.squeeze(np.asarray(m.get("hmax", m.get("zsmax")))).astype(np.float32))
        if m.get("zsmax") is not None:
            np.save(os.path.join(d, "zsmax.npy"), np.squeeze(np.asarray(m["zsmax"])).astype(np.float32))
        out["disk_mb"] = round(sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)) / 1e6, 1)
        os.remove(os.path.join(d, "sfincs_map.nc"))
    else:
        out["log_tail"] = r["log_tail"]
    json.dump(out, open(os.path.join(d, "summary.json"), "w"), indent=1, default=str)
    print(json.dumps(out, default=str)[:800], flush=True)
    return out


def score():
    """AUC of hmax on the DEV box (S1 labels) beside HAND and low elevation;
    extent IoU at WET_M; runtime and disk per km2."""
    import glob
    from affine import Affine
    from rasterio.warp import Resampling, reproject
    from experiments.flood_learned import features as FT
    from experiments.flood_validation.harness import auc
    km2 = (X1 - X0) * (Y1 - Y0) / 1e6
    res = {"settings": {"huthresh": HUTHRESH, "dtmax": DTMAX, "manning": MANNING, "wet_m": WET_M,
                        "sea_floor_m": SEA_FLOOR_M, "domain_km2": km2, "gauge": GAUGE},
           "prep": json.load(open(os.path.join(CACHE, "prep_meta.json"))), "members": {}}
    t = FT.load(DEV_BOX)
    g = t["meta"]["grid"]
    y = t["y"]
    elev = t["X"][:, FT.FEATURES.index("elev_glo30")]
    for d in sorted(glob.glob(os.path.join(CACHE, "runs", "*"))):
        if not os.path.exists(os.path.join(d, "hmax.npy")):
            continue
        summ = json.load(open(os.path.join(d, "summary.json")))
        h = np.load(os.path.join(d, "hmax.npy")).reshape(shape())[::-1, :]
        dst = np.full(tuple(g["shape"]), np.nan, np.float32)
        reproject(h, dst, src_transform=_t30(), src_crs=CRS, dst_transform=Affine(*g["transform"][:6]),
                  dst_crs=g["crs"], resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
        s = np.nan_to_num(dst.ravel(), nan=0.0)          # dry cells have no hmax
        ok = (y >= 0) & np.isfinite(t["C"][:, 0]) & np.isfinite(elev)
        yy = y[ok]
        f = lambda v: auc(v, (yy == 1).astype(int), (yy == 0).astype(int))      # noqa: E731
        wet, obs = s[ok] > WET_M, yy == 1
        res["members"][os.path.basename(d)] = {
            "wall_s": summ.get("wall_s") or summ.get("solver_reported_s"), "disk_mb": summ.get("disk_mb"),
            "peak_rss_mib": summ.get("sfincs_peak_rss_mib"),
            "wall_s_per_km2": None if not (summ.get("wall_s") or summ.get("solver_reported_s")) else round((summ.get("wall_s") or summ["solver_reported_s"]) / km2, 3),
            "disk_mb_per_km2": None if not summ.get("disk_mb") else round(summ["disk_mb"] / km2, 4),
            "auc_hmax": round(f(s[ok]), 4), "auc_hand": round(f(t["C"][ok, 0]), 4),
            "auc_low_elevation": round(f(-elev[ok]), 4),
            "iou_wet": round(float((wet & obs).sum() / max(1, (wet | obs).sum())), 4),
            "wet_share": round(float(wet.mean()), 4), "observed_share": round(float(obs.mean()), 4),
            "cells": [int(obs.sum()), int((~obs).sum())]}
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "fortmyers_sfincs.json"), "w"), indent=1)
    print(json.dumps(res, indent=1)[:2500])
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    if a[0] == "score":
        return score()
    if a[0] == "prep":
        prep()
        return 0
    run(a[1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
