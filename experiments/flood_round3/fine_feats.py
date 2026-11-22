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
# R29 drainage features (owner directive): NaN where a city publishes no such layer.
FEATS2 = ("drain_hist90", "viaduct_hist150", "cb_count90", "rail_bridge_dist_m", "nlcd_imperv", "nlcd_imperv_250")
ALL = FEATS + FEATS2
OVERPASS = "https://overpass-api.de/api/interpreter"


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


def _cells_xy(grid):
    H, W = grid["shape"]
    t = grid["transform"]
    r, c = np.divmod(np.arange(H * W), W)
    return t[2] + (c + 0.5) * t[0], t[5] + (r + 0.5) * t[4]


def rail_bridges(key, bbox):
    """OpenStreetMap railway bridges (rail over road/water: Chicago's viaducts) in bbox: vertex lon/lat array.
    Overpass, cached per box. OSM data (c) OpenStreetMap contributors, ODbL."""
    import urllib.parse
    import urllib.request
    p = os.path.join(OUTD, f"osm_railbridge_{key}.npy")
    if os.path.exists(p):
        return np.load(p)
    w, s_, e, n = bbox
    q = (f'[out:json][timeout:120];way["railway"~"^(rail|light_rail|subway|narrow_gauge)$"]["bridge"]'
         f'({s_},{w},{n},{e});out geom;')
    req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(),
                                 headers={"User-Agent": "geowatch-research"})
    for k in range(4):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                js = json.load(r)
            break
        except Exception as ex:          # noqa: BLE001
            print("overpass:", type(ex).__name__, str(ex)[:100], flush=True)
            time.sleep(30 * (k + 1))
    else:
        raise RuntimeError("overpass failed")
    pts = [(g["lon"], g["lat"]) for el in js.get("elements", []) for g in el.get("geometry", [])]
    a = np.array(pts, np.float64).reshape(-1, 2)
    os.makedirs(OUTD, exist_ok=True)
    np.save(p, a)
    time.sleep(5)
    return a


def drainage_feats(city, grid, before, key, bbox, ee):
    """R29 drainage features on the 30 m grid -> dict of flat float32 arrays (FEATS2)."""
    from pyproj import Transformer
    from scipy import ndimage as nd
    from scipy.spatial import cKDTree
    from experiments.flood_round3 import rain311 as R3
    from susceptibility.hydro_rasters import compute_pixels
    H, W = grid["shape"]
    nan = np.full(H * W, np.nan, np.float32)
    out = {}
    z = R3.history_kind("drain", city)
    out["drain_hist90"] = nan.copy() if z is None else R3.density_feature(z, grid, before, 90.0)
    z = R3.history_kind("viaduct", city)
    out["viaduct_hist150"] = nan.copy() if z is None else R3.density_feature(z, grid, before, 150.0)
    x, y = _cells_xy(grid)
    tr = Transformer.from_crs(4326, grid["crs"], always_xy=True)
    cbp = os.path.join(R3.CACHE, f"catch_basins_{city}.npz")
    if os.path.exists(cbp):
        cb = np.load(cbp)
        X, Y = tr.transform(cb["lon"], cb["lat"])
        out["cb_count90"] = cKDTree(np.c_[X, Y]).query_ball_point(np.c_[x, y], 90.0, return_length=True).astype(np.float32)
    else:
        out["cb_count90"] = nan.copy()
    rb = rail_bridges(key, bbox)
    if len(rb):
        X, Y = tr.transform(rb[:, 0], rb[:, 1])
        out["rail_bridge_dist_m"] = np.minimum(cKDTree(np.c_[X, Y]).query(np.c_[x, y])[0], 5000.0).astype(np.float32)
    else:
        out["rail_bridge_dist_m"] = np.full(H * W, 5000.0, np.float32)
    img = ee.Image(ee.ImageCollection("USGS/NLCD_RELEASES/2021_REL/NLCD").first()).select("impervious").toFloat()
    arr = compute_pixels(img.rename("imp"), grid["transform"], tuple(grid["shape"]), grid["crs"], "nlcd impervious")
    imp = np.asarray(arr["imp"], np.float64)
    if not np.isfinite(imp).any():
        out["nlcd_imperv"], out["nlcd_imperv_250"] = nan.copy(), nan.copy()
    else:
        out["nlcd_imperv"] = imp.ravel().astype(np.float32)
        f = np.where(np.isfinite(imp), imp, 0.0)
        wgt = nd.uniform_filter(np.isfinite(imp).astype(float), 17)
        with np.errstate(invalid="ignore", divide="ignore"):
            out["nlcd_imperv_250"] = (nd.uniform_filter(f, 17) / wgt).ravel().astype(np.float32)
    return out


def drainage_311(n, ee=None):
    """Cached R29 drainage features for one 311 unit."""
    from experiments.flood_round3 import rain311 as R3
    p = os.path.join(OUTD, f"{n}__drain.npz")
    if os.path.exists(p):
        z = np.load(p)
        return {k: z[k] for k in FEATS2}
    meta = json.loads(str(np.load(os.path.join(R3.REFS, f"{n}.npz"))["meta"]))
    if ee is None:
        from experiments.flood_round3 import diagnose_ee as D
        ee = D._init()
    out = drainage_feats(n.split("_")[1], meta["grid"], meta["window"][0][:10], meta["box"], meta["bbox"], ee)
    os.makedirs(OUTD, exist_ok=True)
    np.savez_compressed(p, **out)
    return out


def main(argv=None):
    from experiments.flood_round3 import rain311 as R3
    from experiments.flood_round3 import diagnose_ee as D
    ee = D._init()
    units = json.load(open(os.path.join(R3.REFS, "units.json")))
    for n in sorted(units):
        e = extras_311(n, ee)
        e.update(drainage_311(n, ee))
        print(n, {k: round(float(np.nanmean(v)), 2) for k, v in e.items() if k in ("hist90", "l10_min120", "drain_hist90", "nlcd_imperv")}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
