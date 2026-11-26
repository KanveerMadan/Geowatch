"""
Round 3, flash (R33): NOAA MRMS 1 km radar/gauge rain as event features for US flash units.

MRMS hourly QPE from the Iowa Environmental Mesonet archive (NOAA data, public domain; IEM archive, attribution):
- before 2020-10-14: GaugeCorr_QPE_01H;
- from 2020-10-14: MultiSensor_QPE_01H_Pass2.
Values in mm; negative = no coverage (NaN).

Per unit, over the label window [peak - 1 d, peak + 2 d) UTC, hourly:
- mrms_total_mm      event total at the cell;
- mrms_max1h_mm      the wettest hour at the cell;
- mrms_up_mean_mm    event total averaged over the cell's upstream catchment (D8 on GLO-30 at 90 m over the box
                     + 10 km, priority-flood filled);
- mrms_up_logvol     log1p(upstream event rain volume, m^3).
The event selection is unchanged (Storm Events + IMERG driver check); only features are added, for every method.

    python -m experiments.flood_round3.flash_mrms [workers]
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import gzip
import heapq
import io
import json
import os
import sys
import time
import urllib.request

import numpy as np

BIG = os.path.expanduser("~/.cache/geowatch/flood_round3/big")
OUTD = os.path.join(BIG, "ev_mrms")
RAW = os.path.expanduser("~/.cache/geowatch/flood_round3/mrms_crops")
IEM = "https://mtarchive.geol.iastate.edu/{y}/{m:02d}/{d:02d}/mrms/ncep/{p}/{p}_00.00_{y}{m:02d}{d:02d}-{h:02d}0000.grib2.gz"
SWITCH = dt.datetime(2020, 10, 14, tzinfo=dt.timezone.utc)
MARGIN_DEG = 0.1
DEM_M = 90.0
FEATS = ("mrms_total_mm", "mrms_max1h_mm", "mrms_up_mean_mm", "mrms_up_logvol")


def _product(t):
    return "GaugeCorr_QPE_01H" if t < SWITCH else "MultiSensor_QPE_01H_Pass2"


def hour_crop(t, box):
    """MRMS 1 h QPE at hour t cropped to box (lon/lat) -> (array mm, transform tuple) or None (cached)."""
    import rasterio
    from rasterio.windows import from_bounds
    key = f"{t:%Y%m%d%H}_{'_'.join(f'{x:.3f}' for x in box)}"
    p = os.path.join(RAW, key + ".npz")
    if os.path.exists(p):
        z = np.load(p)
        return (None, None) if z["a"].size == 0 else (z["a"], tuple(z["t"]))
    url = IEM.format(y=t.year, m=t.month, d=t.day, h=t.hour, p=_product(t))
    data = None
    for k in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "geowatch-research"}), timeout=120) as r:
                data = gzip.decompress(r.read())
            break
        except urllib.error.HTTPError as e:
            if e.code == 404:
                break
            time.sleep(5 * (k + 1))
        except Exception:          # noqa: BLE001
            time.sleep(5 * (k + 1))
    os.makedirs(RAW, exist_ok=True)
    if data is None:
        np.savez_compressed(p, a=np.zeros(0), t=np.zeros(6))
        return None, None
    with rasterio.MemoryFile(io.BytesIO(data)) as mf, mf.open() as s:
        w = from_bounds(*box, transform=s.transform).round_offsets().round_lengths()
        a = s.read(1, window=w).astype(np.float32)
        tr = s.window_transform(w)
    if a.size == 0 or min(a.shape) < 2:            # box fell outside this product's grid
        np.savez_compressed(p, a=np.zeros(0), t=np.zeros(6))
        return None, None
    a[a < 0] = np.nan
    np.savez_compressed(p, a=a, t=np.array(tuple(tr)[:6]))
    return a, tuple(tr)[:6]


def _fill_d8(z):
    """Priority-flood fill (+ tiny epsilon) and D8 receiver index per cell (-1 = edge outlet)."""
    H, W = z.shape
    filled = z.copy()
    seen = np.zeros(z.shape, bool)
    pq = []
    for r in range(H):
        for c in (0, W - 1):
            heapq.heappush(pq, (filled[r, c], r, c)); seen[r, c] = True
    for c in range(1, W - 1):
        for r in (0, H - 1):
            heapq.heappush(pq, (filled[r, c], r, c)); seen[r, c] = True
    nb = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    while pq:
        h, r, c = heapq.heappop(pq)
        for dr, dc in nb:
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W and not seen[rr, cc]:
                seen[rr, cc] = True
                if filled[rr, cc] <= h:
                    filled[rr, cc] = h + 1e-4
                heapq.heappush(pq, (filled[rr, cc], rr, cc))
    rec = np.full(H * W, -1, np.int64)
    best = np.zeros((H, W))
    for dr, dc in nb:
        dist = np.hypot(dr, dc)
        sh = np.full((H, W), np.inf)
        rs, re_ = max(0, -dr), H - max(0, dr)
        cs, ce = max(0, -dc), W - max(0, dc)
        sh[rs:re_, cs:ce] = filled[rs + dr:re_ + dr, cs + dc:ce + dc]
        slope = (filled - sh) / dist
        better = slope > best
        best = np.where(better, slope, best)
        idx = (np.arange(H)[:, None] + dr) * W + (np.arange(W)[None, :] + dc)
        rec = np.where(better.ravel(), idx.ravel(), rec)
    return filled, rec


def accumulate(rec, weight):
    """Upstream sums of `weight` (flat) following receivers (each cell includes itself)."""
    n = len(rec)
    indeg = np.zeros(n, np.int64)
    np.add.at(indeg, rec[rec >= 0], 1)
    acc = weight.astype(np.float64).copy()
    stack = list(np.flatnonzero(indeg == 0))
    while stack:
        i = stack.pop()
        j = rec[i]
        if j >= 0:
            acc[j] += acc[i]
            indeg[j] -= 1
            if indeg[j] == 0:
                stack.append(j)
    return acc


def unit_features(n, meta, ee):
    from affine import Affine
    from pyproj import Transformer
    from susceptibility.hydro_rasters import compute_pixels, grid_lonlat_bounds, utm_grid
    p = os.path.join(OUTD, f"{n}.npz")
    if os.path.exists(p):
        return "cached"
    g = meta["grid"]
    t30 = Affine(*g["transform"][:6])
    H30, W30 = g["shape"]
    w, s, e, nn = grid_lonlat_bounds(t30, (H30, W30), g["crs"])
    box = (w - MARGIN_DEG, s - MARGIN_DEG, e + MARGIN_DEG, nn + MARGIN_DEG)
    pk = dt.datetime.fromisoformat(meta.get("peak") or meta["label_v3"]["peak"]).replace(tzinfo=dt.timezone.utc)
    hours = [pk - dt.timedelta(days=1) + dt.timedelta(hours=k) for k in range(72)]
    stack, tr = [], None
    for t in hours:
        a, tt = hour_crop(t, box)
        if a is not None:
            if tr is None:
                tr = tt
            if stack and a.shape != stack[0].shape:
                continue
            stack.append(a)
    if stack:                                       # keep the most common crop shape only
        from collections import Counter
        shp = Counter(x.shape for x in stack).most_common(1)[0][0]
        stack = [x for x in stack if x.shape == shp]
    if not stack:
        np.savez_compressed(p, **{k: np.full(H30 * W30, np.nan, np.float32) for k in FEATS}, hours=0)
        return "no MRMS"
    S = np.stack(stack)
    total = np.nansum(S, 0)
    total[np.all(np.isnan(S), 0)] = np.nan
    mx = np.nanmax(np.where(np.isnan(S), -1, S), 0)
    mx[mx < 0] = np.nan
    tr_m = Affine(*tr)
    # DEM for routing: GLO-30 on a 90 m UTM grid over the margin box
    t90, shp90, crs90 = utm_grid(box, pixel_m=DEM_M)
    dem = ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").mosaic().rename("z")
    z = np.asarray(compute_pixels(dem, t90, shp90, crs90, "glo30 90m")["z"], np.float64)
    z = np.where(np.isfinite(z), z, np.nanmin(z) if np.isfinite(z).any() else 0.0)
    filled, rec = _fill_d8(z)
    H9, W9 = shp90
    rr, cc = np.mgrid[0:H9, 0:W9]
    x9, y9 = t90 * (cc + 0.5, rr + 0.5)
    lon9, lat9 = Transformer.from_crs(crs90, 4326, always_xy=True).transform(x9, y9)
    ci, ri = ~tr_m * (lon9, lat9)
    ri, ci = np.floor(ri).astype(int), np.floor(ci).astype(int)
    ok = (ri >= 0) & (ri < total.shape[0]) & (ci >= 0) & (ci < total.shape[1])
    rain9 = np.full((H9, W9), np.nan)
    rain9[ok] = total[ri[ok], ci[ok]]
    has = np.isfinite(rain9).ravel()
    vol = accumulate(rec, np.where(has, np.nan_to_num(rain9.ravel()) / 1000.0 * DEM_M ** 2, 0.0))
    area = accumulate(rec, has.astype(float) * DEM_M ** 2)
    with np.errstate(invalid="ignore", divide="ignore"):
        up_mean = np.where(area > 0, vol / area * 1000.0, np.nan)
    # sample everything at the unit's 30 m cell centres
    r3, c3 = np.divmod(np.arange(H30 * W30), W30)
    x3, y3 = t30 * (c3 + 0.5, r3 + 0.5)
    lon3, lat3 = Transformer.from_crs(g["crs"], 4326, always_xy=True).transform(x3, y3)
    cm, rm = ~tr_m * (lon3, lat3)
    rm, cm = np.clip(np.floor(rm).astype(int), 0, total.shape[0] - 1), np.clip(np.floor(cm).astype(int), 0, total.shape[1] - 1)
    xu, yu = Transformer.from_crs(g["crs"], crs90, always_xy=True).transform(x3, y3)
    c9, r9 = ~t90 * (xu, yu)
    r9, c9 = np.clip(np.floor(r9).astype(int), 0, H9 - 1), np.clip(np.floor(c9).astype(int), 0, W9 - 1)
    i9 = r9 * W9 + c9
    out = {"mrms_total_mm": total[rm, cm].astype(np.float32), "mrms_max1h_mm": mx[rm, cm].astype(np.float32),
           "mrms_up_mean_mm": up_mean[i9].astype(np.float32), "mrms_up_logvol": np.log1p(vol[i9]).astype(np.float32)}
    os.makedirs(OUTD, exist_ok=True)
    np.savez_compressed(p, **out, hours=len(stack))
    return f"{len(stack)} h"


def _utm90(box):
    """A 90 m UTM grid over a lon/lat box (utm_grid builds 30 m grids)."""
    from affine import Affine
    from pyproj import CRS, Transformer
    lon0 = (box[0] + box[2]) / 2
    lat0 = (box[1] + box[3]) / 2
    epsg = (32600 if lat0 >= 0 else 32700) + int((lon0 + 180) // 6) + 1
    crs = f"EPSG:{epsg}"
    tr = Transformer.from_crs(4326, CRS.from_user_input(crs), always_xy=True)
    xs, ys = tr.transform([box[0], box[2], box[0], box[2]], [box[1], box[1], box[3], box[3]])
    x0, x1 = np.floor(min(xs) / DEM_M) * DEM_M, np.ceil(max(xs) / DEM_M) * DEM_M
    y0, y1 = np.floor(min(ys) / DEM_M) * DEM_M, np.ceil(max(ys) / DEM_M) * DEM_M
    return Affine(DEM_M, 0, x0, 0, -DEM_M, y1), (int((y1 - y0) / DEM_M), int((x1 - x0) / DEM_M)), crs


def flash_units():
    """US flash DEV units with a feature table (Storm Events route)."""
    from experiments.flood_round3 import build_r3 as B
    return sorted(f[:-4] for f in os.listdir(B.TABLES) if f.startswith("r3se_"))


def main(argv=None):
    from experiments.flood_round3 import build_r3 as B
    from experiments.flood_round3.diagnose_ee import _init
    ee = _init()
    a = argv or sys.argv[1:]
    workers = int(a[0]) if a else 4
    units = flash_units()
    print(len(units), "US flash DEV units", flush=True)
    metas = {n: json.loads(str(np.load(os.path.join(B.REFS, f"{n}.npz"))["meta"])) for n in units}
    with cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(unit_features, n, metas[n], ee): n for n in units}
        for f in cf.as_completed(futs):
            n = futs[f]
            try:
                print(n, f.result(), flush=True)
            except Exception as e:          # noqa: BLE001
                print(n, "FAILED", type(e).__name__, str(e)[:200], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
