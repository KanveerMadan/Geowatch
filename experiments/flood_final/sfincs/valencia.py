"""
Phase 6, DEV case 1: SFINCS on the Poyo / Horta Sud flood (DANA, 29 Oct 2024).
A diagnostic on DEV boxes (valencia_2024, paiporta); not a held-out candidate
(PREREGISTRATION §4).

    python -m experiments.flood_final.sfincs.valencia dem        # MDT05 LiDAR tiles (IGN WCS) -> 30 m
    python -m experiments.flood_final.sfincs.valencia rain       # IMERG V07 half-hourly -> 1 km netCDF
    python -m experiments.flood_final.sfincs.valencia run <member>
    python -m experiments.flood_final.sfincs.valencia score

Settings and their basis:
  domain      EPSG:25830 x 691000-733000, y 4352000-4378000 (42 x 26 km): the Poyo
              catchment (413-421 km2 at Paiporta / the Albufera, flood_baselines B1)
              plus the Horta Sud plain and the coast; headwaters inside, so no
              river inflow boundary.
  grid        30 m (the labels' grid; P0 c5: 30 m keeps a 120 m hollow's depth).
  terrain     IGN MDT05 (PNOA LiDAR, CC BY 4.0) averaged 5 m -> 30 m. Comparison
              member: Copernicus GLO-30.
  rain        IMERG V07 'precipitation' (mm/h, 30 min), 2024-10-29 00:00 to
              2024-10-31 12:00 UTC, on a 1 km grid (bilinear from 0.1 deg).
              Member 'gauge': the same field scaled so its largest 24 h total in the
              domain equals AEMET's Turis 771.8 mm / 24 h (flood_baselines B1 notes that
              IMERG misses the convective core; this brackets it).
  coast       msk = 2 water-level boundary on outer-ring cells with z <= 1 m (sea and
              lagoon edge); level 0.3 m (microtidal Mediterranean, ~0.2 m range, plus
              set-up; flood_baselines B1). Member 'lagoon1m': 1.0 m (the lagoon rose
              ~1.0 m on 29 Oct, B1).
  solver      huthresh 0.001 m (the brief; P0 c2 shows the 0.05 m default holds
              shallow sheet flow), dtmax 4 s (divides the 3600 s output interval,
              P0b-1), manning 0.04 (P0's value), no infiltration (a stated simplification:
              soils were saturated by the first DANA day; it biases depth high).
  terrain ensemble  members 'lidar_e1'..'lidar_e5': LiDAR + correlated error with
              sigma 0.20 m (PNOA LiDAR's specified vertical RMSE <= 0.20 m) split
              50 % short (100 m) / 50 % long (2 km) (P0b-3's error model).
Outputs per member: hmax, h at 2024-10-31 09:00 UTC (the AOI03 VHR image is 10:22
local = 09:22 UTC; nearest hourly map), runtime, peak memory, disk.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_final/sfincs/valencia")
CRS = "EPSG:25830"
X0, X1, Y0, Y1 = 691000, 733000, 4352000, 4378000
DX = 30.0
TILE_M = 4000
WCS = ("https://servicios.idee.es/wcs-inspire/mdt?SERVICE=WCS&REQUEST=GetCoverage&VERSION=2.0.1"
       "&COVERAGEID=Elevacion25830_5&SUBSET=x({x0},{x1})&SUBSET=y({y0},{y1})&FORMAT=image/tiff")
T0 = "2024-10-29T00:00:00"
T1 = "2024-10-31T12:00:00"
TURIS_24H_MM = 771.8
COAST_LEVEL = {"base": 0.3, "lagoon1m": 1.0}
SNAPSHOT_H = 57          # 2024-10-31 09:00 UTC
HUTHRESH, DTMAX, MANNING = 0.001, 4.0, 0.04
LIDAR_SIGMA = 0.20


def grid_shape():
    return int((Y1 - Y0) / DX), int((X1 - X0) / DX)


def dem():
    import subprocess
    import rasterio
    from rasterio.merge import merge
    from rasterio.warp import Resampling, reproject
    from affine import Affine
    tdir = os.path.join(CACHE, "mdt05_tiles")
    os.makedirs(tdir, exist_ok=True)
    paths = []
    for x in range(X0, X1, TILE_M):
        for y in range(Y0, Y1, TILE_M):
            p = os.path.join(tdir, f"mdt05_{x}_{y}.tif")
            if not os.path.exists(p):
                url = WCS.format(x0=x, x1=min(x + TILE_M, X1), y0=y, y1=min(y + TILE_M, Y1))
                for attempt in range(3):          # the brief: 3 tries with backoff
                    r = subprocess.run(["curl", "-s", "--max-time", "300", "-o", p + ".part", url])
                    if r.returncode == 0 and os.path.getsize(p + ".part") > 1000:
                        os.replace(p + ".part", p)
                        break
                    time.sleep(10 * (attempt + 1))
                else:
                    raise RuntimeError(f"MDT05 tile {x},{y} failed 3 times")
            paths.append(p)
    srcs = [rasterio.open(p) for p in paths]
    mosaic, mt = merge(srcs)
    nod = srcs[0].nodata
    z = mosaic[0].astype(np.float32)
    if nod is not None:
        z[z == nod] = np.nan
    H, W = grid_shape()
    dst = np.full((H, W), np.nan, np.float32)
    t30 = Affine(DX, 0, X0, 0, -DX, Y1)
    reproject(z, dst, src_transform=mt, src_crs=CRS, dst_transform=t30, dst_crs=CRS,
              resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
    np.save(os.path.join(CACHE, "dem_lidar30.npy"), dst)
    print("lidar 30 m", dst.shape, np.nanmin(dst), np.nanmax(dst), np.isnan(dst).mean(), flush=True)
    # GLO-30 on the same grid (comparison member)
    import ee
    from ingestion.gee_client import initialize_gee
    from susceptibility.hydro_rasters import compute_pixels
    initialize_gee()
    region = ee.Geometry.Rectangle([-0.80, 39.28, -0.28, 39.54])
    col = ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1").filterBounds(region)
    img = col.mosaic().setDefaultProjection(col.first().projection()).select("DEM").resample("bilinear")
    g = compute_pixels(img.rename("z"), t30, (H, W), CRS, "glo30 valencia")["z"]
    np.save(os.path.join(CACHE, "dem_glo30.npy"), g.astype(np.float32))
    print("glo30 30 m", np.nanmin(g), np.nanmax(g), flush=True)


def rain():
    import ee
    import xarray as xr
    from affine import Affine
    from ingestion.gee_client import initialize_gee
    from susceptibility.hydro_rasters import compute_pixels
    initialize_gee()
    col = (ee.ImageCollection("NASA/GPM_L3/IMERG_V07").filterDate(T0, T1)
           .select("precipitation").sort("system:time_start"))
    n = col.size().getInfo()
    times = col.aggregate_array("system:time_start").getInfo()
    km = 1000.0
    W, H = int((X1 - X0) / km), int((Y1 - Y0) / km)
    t1k = Affine(km, 0, X0, 0, -km, Y1)
    lst = col.toList(n)
    frames = []
    for i in range(n):
        im = ee.Image(lst.get(i)).resample("bilinear").rename("p")
        frames.append(compute_pixels(im, t1k, (H, W), CRS, f"imerg {i}")["p"].astype(np.float32))
    P = np.stack(frames)                      # (t, y_top_down, x), mm/h
    P = np.nan_to_num(P)[:, ::-1, :]          # south first (y ascending)
    xs = X0 + km * (np.arange(W) + 0.5)
    ys = Y0 + km * (np.arange(H) + 0.5)
    tmin = (np.array(times) - np.datetime64(T0, "ms").astype(np.int64)) / 60000.0
    os.makedirs(CACHE, exist_ok=True)
    acc24 = max(P[k:k + 48].sum(0).max() * 0.5 for k in range(0, len(P) - 47))
    scale = TURIS_24H_MM / acc24
    for name, f in (("imerg", 1.0), ("gauge", scale)):
        ds = xr.Dataset({"Precipitation": (("time", "y", "x"), P * f)},
                        coords={"time": tmin, "y": ys, "x": xs})
        ds["time"].attrs["units"] = f"minutes since {T0.replace('T', ' ')}"
        ds["Precipitation"].attrs["units"] = "mm/hr"
        ds.to_netcdf(os.path.join(CACHE, f"precip_{name}.nc"), engine="scipy")
    meta = {"frames": n, "imerg_max_24h_mm": float(acc24), "gauge_scale": float(scale),
            "domain_mean_total_mm": float(P.sum(0).mean() * 0.5)}
    json.dump(meta, open(os.path.join(CACHE, "rain_meta.json"), "w"), indent=1)
    print(meta, flush=True)


def smooth_noise(shape, sigma, corr_cells, rng):
    from scipy.ndimage import gaussian_filter
    f = gaussian_filter(rng.standard_normal(shape), corr_cells)
    return f / f.std() * sigma


def member_setup(member: str):
    """(dem, precip file, coast level) for a member name."""
    z = np.load(os.path.join(CACHE, "dem_glo30.npy" if member == "glo30" else "dem_lidar30.npy"))
    if member.startswith("lidar_e"):
        k = int(member[len("lidar_e"):])
        rng = np.random.default_rng(20261119 + k)
        s = LIDAR_SIGMA * np.sqrt(0.5)
        z = z + smooth_noise(z.shape, s, 100 / DX, rng) + smooth_noise(z.shape, s, 2000 / DX, rng)
    rainf = "precip_gauge.nc" if member == "gauge" else "precip_imerg.nc"
    level = COAST_LEVEL["lagoon1m" if member == "lagoon1m" else "base"]
    return z.astype(np.float32), rainf, level


def write_member(member: str) -> str:
    import shutil
    from experiments.flood_core.sfincs import sfincs_io as S
    d = os.path.join(CACHE, "runs", member)
    os.makedirs(d, exist_ok=True)
    z_top, rainf, level = member_setup(member)
    z = z_top[::-1, :]                        # SFINCS rows: south first
    z = np.where(np.isfinite(z), z, 0.0)
    msk = np.ones(z.shape, int)
    ring = np.zeros(z.shape, bool)
    ring[0, :] = ring[-1, :] = ring[:, 0] = ring[:, -1] = True
    msk[ring & (z <= 1.0)] = 2
    nb = int((msk == 2).sum())
    # boundary points at the centres of msk = 2 cells (one series; SFINCS interpolates)
    r, c = np.nonzero(msk == 2)
    pts = [(X0 + DX * (c[i] + 0.5), Y0 + DX * (r[i] + 0.5)) for i in range(0, len(r), max(1, len(r) // 20))]
    tstop = (np.datetime64(T1) - np.datetime64(T0)).astype("timedelta64[s]").astype(float)
    S.write_model(d, z, msk, DX, tstop, 3600.0, manning=MANNING,
                  bnd=pts, bzs=[[0.0] + [level] * len(pts), [tstop] + [level] * len(pts)],
                  extra={"huthresh": HUTHRESH, "dtmax": DTMAX, "x0": float(X0), "y0": float(Y0),
                         "tref": "20241029 000000", "tstart": "20241029 000000",
                         "tstop": "20241031 120000", "netamprfile": "precip.nc",
                         "storecumprcp": 1})
    shutil.copy(os.path.join(CACHE, rainf), os.path.join(d, "precip.nc"))
    json.dump({"member": member, "boundary_cells": nb, "coast_level_m": level, "rain": rainf},
              open(os.path.join(d, "member.json"), "w"), indent=1)
    return d


def run(member: str):
    from experiments.flood_core.sfincs import sfincs_io as S
    d = write_member(member)
    if os.path.exists(os.path.join(d, "summary.json")):
        return json.load(open(os.path.join(d, "summary.json")))
    r = S.run(d)
    out = {"member": member, **{k: v for k, v in r.items() if k != "log_tail"}}
    if r["exit_code"] == "0" and os.path.exists(os.path.join(d, "sfincs_map.nc")):
        m = S.read_map(d)
        hmax = np.asarray(m.get("hmax", m.get("zsmax")))
        np.save(os.path.join(d, "hmax.npy"), np.squeeze(hmax).astype(np.float32))
        zs, zb = m.get("zs"), m.get("zb")
        if zs is not None:
            h = np.asarray(zs)[SNAPSHOT_H] - np.asarray(zb)
            np.save(os.path.join(d, "h_snapshot.npy"), h.astype(np.float32))
        out["disk_mb"] = round(sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)) / 1e6, 1)
        os.remove(os.path.join(d, "sfincs_map.nc"))          # regenerable; keep the npy extracts
    else:
        out["log_tail"] = r["log_tail"]
    json.dump(out, open(os.path.join(d, "summary.json"), "w"), indent=1, default=str)
    print(json.dumps(out, default=str)[:800], flush=True)
    return out


WET_M = 0.10            # "flooded" depth for extent IoU: the flood-core P0 convention (> 0.10 m)
DEV_BOXES = ("valencia_2024", "paiporta")


def score():
    """Each finished member on the DEV boxes: AUC of hmax and of the snapshot
    depth vs the cached EMS reference (same labels as every DEV score), beside
    HAND; extent IoU at WET_M; runtime / memory / disk per km2."""
    import glob
    from affine import Affine
    from rasterio.warp import Resampling, reproject
    from experiments.flood_learned import features as FT
    from experiments.flood_validation.harness import auc
    t30 = Affine(DX, 0, X0, 0, -DX, Y1)
    res = {"settings": {"huthresh": HUTHRESH, "dtmax": DTMAX, "manning": MANNING, "wet_m": WET_M,
                        "domain_km2": (X1 - X0) * (Y1 - Y0) / 1e6}, "members": {}}
    for d in sorted(glob.glob(os.path.join(CACHE, "runs", "*"))):
        sp = os.path.join(d, "summary.json")
        if not os.path.exists(os.path.join(d, "hmax.npy")):
            continue
        summ = json.load(open(sp))
        mem = os.path.basename(d)
        rec = {k: summ.get(k) for k in ("wall_s", "solver_reported_s", "sfincs_peak_rss_mib", "disk_mb")}
        km2 = res["settings"]["domain_km2"]
        rec["wall_s_per_km2"] = None if not rec["wall_s"] else round(rec["wall_s"] / km2, 3)
        rec["disk_mb_per_km2"] = None if not rec["disk_mb"] else round(rec["disk_mb"] / km2, 4)
        for field in ("hmax", "h_snapshot"):
            p = os.path.join(d, f"{field}.npy")
            if not os.path.exists(p):
                continue
            h = np.load(p).astype(np.float32)
            h = h.reshape(grid_shape()) if h.size == np.prod(grid_shape()) else h
            h_top = h[::-1, :]                     # back to north-up
            for box in DEV_BOXES:
                t = FT.load(box)
                g = t["meta"]["grid"]
                dst = np.full(tuple(g["shape"]), np.nan, np.float32)
                reproject(h_top, dst, src_transform=t30, src_crs=CRS,
                          dst_transform=Affine(*g["transform"][:6]), dst_crs=g["crs"],
                          resampling=Resampling.average, src_nodata=np.nan, dst_nodata=np.nan)
                y = t["y"]
                s = dst.ravel()
                ok = (y >= 0) & np.isfinite(s) & np.isfinite(t["C"][:, 0])
                yy = y[ok]
                f = lambda v: auc(v, (yy == 1).astype(int), (yy == 0).astype(int))   # noqa: E731
                wet = s[ok] > WET_M
                obs = yy == 1
                rec[f"{box}__{field}"] = {
                    "auc": round(f(s[ok]), 4), "hand_auc": round(f(t["C"][ok, 0]), 4),
                    "iou_wet": round(float((wet & obs).sum() / max(1, (wet | obs).sum())), 4),
                    "wet_share": round(float(wet.mean()), 4), "observed_share": round(float(obs.mean()), 4)}
        res["members"][mem] = rec
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, "valencia_sfincs.json"), "w"), indent=1)
    print(json.dumps(res, indent=1)[:3000])
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    if a[0] == "score":
        return score()
    {"dem": dem, "rain": rain}.get(a[0], lambda: run(a[1]))()
    return 0


if __name__ == "__main__":
    sys.exit(main())
