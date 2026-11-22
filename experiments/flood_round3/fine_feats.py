"""
Round 3, rain: extra per-cell features for 311 units (DIAGNOSIS §k), on the unit's own 30 m grid.

- `hist90`: rain311.hist_feature at 90 m. Only reports before the label window and before 2022 are counted.
- 10 m USGS 3DEP lidar terrain, where 3DEP covers the box (US only). Each 30 m cell takes the minimum over
  its 3 x 3 10 m pixels, so a street-level low spot inside the cell counts.
  - `l10_elev`: the 10 m elevation itself;
  - `l10_min{30,60,120,250}`: height above the local minimum within that radius;
  - `l10_tpi{30,60,120,250}`: elevation minus the local mean within that radius.

Cells with no 3DEP value are NaN. For units outside the US, every lidar feature is NaN; LightGBM handles
NaN natively, and the baselines never see these features.

    python -m experiments.flood_round3.fine_feats      # build the cache for every 311 DEV unit
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

BIG = os.path.expanduser("~/.cache/geowatch/flood_round3/big")
OUTD = os.path.join(BIG, "extras")
DEMD = os.path.expanduser("~/.cache/geowatch/flood_round3/dem3dep10")
RADII = (30, 60, 120, 250)
FEATS = ("hist90", "l10_elev") + tuple(f"l10_min{r}" for r in RADII) + tuple(f"l10_tpi{r}" for r in RADII)


def _disk(r_m, px=10.0):
    k = int(r_m / px)
    yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
    return (xx ** 2 + yy ** 2) <= k * k


def dem10(ee, key, bbox, crs):
    """3DEP 10 m mosaic over bbox (lon/lat), on the unit's UTM CRS; cached GeoTIFF path."""
    import urllib.request
    os.makedirs(DEMD, exist_ok=True)
    p = os.path.join(DEMD, f"{key}.tif")
    if not os.path.exists(p):
        g = ee.Geometry.Rectangle(list(bbox))
        im = ee.ImageCollection("USGS/3DEP/10m_collection").filterBounds(g).mosaic().select("elevation")
        url = im.getDownloadURL({"region": g, "scale": 10, "crs": crs, "format": "GEO_TIFF"})
        with urllib.request.urlopen(url, timeout=300) as r:
            data = r.read()
        open(p + ".part", "wb").write(data)
        os.replace(p + ".part", p)
        time.sleep(1.0)
    return p


def lidar_feats(dem_path, grid):
    """Lidar features on the 30 m grid ({crs, transform, shape}) -> dict of float32 arrays, flat."""
    import rasterio
    from scipy import ndimage as nd
    with rasterio.open(dem_path) as s:
        z = s.read(1).astype(np.float64)
        tr = s.transform
        nodata = s.nodata
    bad = ~np.isfinite(z) | (z < -1000)
    if nodata is not None:
        bad |= z == nodata
    H, W = grid["shape"]
    if bad.all():
        return {k: np.full(H * W, np.nan, np.float32) for k in FEATS if k.startswith("l10_")}
    zf = np.where(bad, np.nanmean(np.where(bad, np.nan, z)), z)
    F = {"l10_elev": zf}
    for r in RADII:
        F[f"l10_tpi{r}"] = zf - nd.uniform_filter(zf, 2 * (r // 10) + 1)
        F[f"l10_min{r}"] = zf - nd.minimum_filter(zf, footprint=_disk(r))
    t = grid["transform"]
    rr, cc = np.divmod(np.arange(H * W), W)
    x, y = t[2] + (cc + 0.5) * t[0], t[5] + (rr + 0.5) * t[4]
    c10, r10 = ~tr * (x, y)
    r10 = np.clip(r10.astype(int), 0, z.shape[0] - 1)
    c10 = np.clip(c10.astype(int), 0, z.shape[1] - 1)
    badc = nd.maximum_filter(bad, 3)[r10, c10]
    out = {}
    for k, v in F.items():
        a = nd.minimum_filter(v, 3)[r10, c10].astype(np.float32)
        a[badc] = np.nan
        out[k] = a
    return out


def extras_311(n, ee=None):
    """Cached extras for one 311 unit -> dict of flat float32 arrays (FEATS)."""
    from experiments.flood_round3 import rain311 as R3
    p = os.path.join(OUTD, f"{n}.npz")
    if os.path.exists(p):
        z = np.load(p)
        return {k: z[k] for k in FEATS}
    meta = json.loads(str(np.load(os.path.join(R3.REFS, f"{n}.npz"))["meta"]))
    g = meta["grid"]
    city = n.split("_")[1]
    out = {"hist90": R3.hist_feature(city, g, meta["window"][0][:10], 90.0)}
    if ee is None:
        from experiments.flood_round3 import diagnose_ee as D
        ee = D._init()
    out.update(lidar_feats(dem10(ee, meta["box"], meta["bbox"], g["crs"]), g))
    os.makedirs(OUTD, exist_ok=True)
    np.savez_compressed(p, **{k: out[k] for k in FEATS})
    return out


def main(argv=None):
    from experiments.flood_round3 import rain311 as R3
    from experiments.flood_round3 import diagnose_ee as D
    ee = D._init()
    units = json.load(open(os.path.join(R3.REFS, "units.json")))
    for n in sorted(units):
        e = extras_311(n, ee)
        print(n, {k: round(float(np.nanmean(v)), 2) for k, v in e.items() if k in ("hist90", "l10_min120")}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
