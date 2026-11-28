"""
Round 3, waterlogging (R33): pre-event ponding history, antecedent soil moisture and canals, per DEV unit,
on the unit's 30 m grid. Clay is already a table feature (clay_pct).

- wl_jrc_month_prior   JRC Monthly History: share of valid observations that were water, in the event's month
                       +/- 1, over the 5 years before the event year (clipped to the archive's end, 2021);
- wl_s1_season_prior   Sentinel-1: share of VV passes below -15 dB, same months, the 3 years before the event;
- wl_sm_antecedent     ERA5-Land layer-1 volumetric soil water, mean of the 7 days before the peak (coarse);
- wl_canal_dist_m      distance to the nearest OSM drain / canal (tools.osm_local, local Geofabrik extracts);
- wl_canal_len_250     OSM drain / canal cells within 250 m (all-touched rasterised lines).
All are dated strictly before the event. Units without a local extract get NaN canal features.

    python -m experiments.flood_round3.wl_feats
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

import numpy as np

BIG = os.path.expanduser("~/.cache/geowatch/flood_round3/big")
OUTD = os.path.join(BIG, "ev_wl")
PBF = os.path.expanduser("~/.cache/geowatch/floodspeed/pbf")
IDX = os.path.expanduser("~/.cache/geowatch/floodspeed/index")
FEATS = ("wl_jrc_month_prior", "wl_s1_season_prior", "wl_sm_antecedent", "wl_canal_dist_m", "wl_canal_len_250")
PLAIN_PBF = {"sindh": ("PK", "IN"), "punjab": ("PK", "IN"), "bangladesh": ("BD", "IN"), "south_sudan": ("SS",),
             "nigeria": ("NG",)}


def _months(m):
    return sorted({((m - 2) % 12) + 1, m, (m % 12) + 1})


def ee_layers(ee, grid, event, peak):
    from affine import Affine
    from susceptibility.hydro_rasters import compute_pixels
    t = Affine(*grid["transform"][:6])
    shape, crs = tuple(grid["shape"]), grid["crs"]
    d = dt.date.fromisoformat(event)
    pk = dt.date.fromisoformat(peak or event)
    ms = _months(d.month)
    yrs = [y for y in range(d.year - 5, d.year) if y <= 2021]
    jm = ee.ImageCollection("JRC/GSW1_4/MonthlyHistory").filter(ee.Filter.inList("year", yrs)) \
        .filter(ee.Filter.inList("month", ms)).select("water")
    wat = jm.map(lambda i: i.eq(2)).sum()
    val = jm.map(lambda i: i.gt(0)).sum()
    jrc = wat.divide(val.max(1)).updateMask(val.gt(0)).rename("jrc")
    s1 = ee.ImageCollection("COPERNICUS/S1_GRD").filter(ee.Filter.eq("instrumentMode", "IW")) \
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")).select("VV") \
        .filterDate(f"{d.year - 3}-01-01", f"{d.year}-01-01") \
        .filter(ee.Filter.calendarRange(ms[0], ms[-1], "month") if ms[0] <= ms[-1] else ee.Filter.Or(
            ee.Filter.calendarRange(ms[0], 12, "month"), ee.Filter.calendarRange(1, ms[-1], "month")))
    s1f = s1.map(lambda i: i.lt(-15)).mean().rename("s1")
    sm = ee.ImageCollection("ECMWF/ERA5_LAND/DAILY_AGGR").select("volumetric_soil_water_layer_1") \
        .filterDate((pk - dt.timedelta(days=7)).isoformat(), pk.isoformat()).mean().rename("sm")
    img = ee.Image.cat([jrc, s1f.reproject(crs=crs, scale=10).reduceResolution(ee.Reducer.mean(), maxPixels=64), sm])
    a = compute_pixels(img.toFloat(), t, shape, crs, "wl layers")
    return {"wl_jrc_month_prior": np.asarray(a["jrc"], np.float32).ravel(),
            "wl_s1_season_prior": np.asarray(a["s1"], np.float32).ravel(),
            "wl_sm_antecedent": np.asarray(a["sm"], np.float32).ravel()}


def canal_layers(grid, pbfs):
    from affine import Affine
    from pyproj import Transformer
    from rasterio.features import rasterize
    from scipy import ndimage as nd
    from shapely.geometry import shape as shp
    from shapely.ops import transform as stransform
    from susceptibility.hydro_rasters import grid_lonlat_bounds
    t = Affine(*grid["transform"][:6])
    H, W = grid["shape"]
    nan = np.full(H * W, np.nan, np.float32)
    files = [os.path.join(PBF, f"{k}.osm.pbf") for k in pbfs if os.path.exists(os.path.join(PBF, f"{k}.osm.pbf"))]
    if not files:
        return {"wl_canal_dist_m": nan.copy(), "wl_canal_len_250": nan.copy()}
    sys.path.insert(0, os.path.expanduser("~/gw-floodproto"))
    from tools.osm_local import query
    w, s, e, n = grid_lonlat_bounds(t, (H, W), grid["crs"])
    pad = 0.02
    seen, geoms = set(), []
    for f in files:
        try:
            fc = query((w - pad, s - pad, e + pad, n + pad), f, IDX)
        except Exception:          # noqa: BLE001  (box outside this extract)
            continue
        for ft in fc.get("features", []):
            if "drains_canals" not in (ft["properties"].get("classes") or []):
                continue
            oid = ft["properties"].get("id") or ft.get("id")
            if oid in seen:
                continue
            seen.add(oid)
            geoms.append(shp(ft["geometry"]))
    tr = Transformer.from_crs(4326, grid["crs"], always_xy=True).transform
    lines = [stransform(tr, g) for g in geoms]
    if not lines:
        return {"wl_canal_dist_m": np.full(H * W, 5000.0, np.float32), "wl_canal_len_250": np.zeros(H * W, np.float32)}
    m = rasterize([(g, 1) for g in lines], out_shape=(H, W), transform=t, all_touched=True, fill=0).astype(bool)
    dist = nd.distance_transform_edt(~m) * abs(t.a)
    k = int(250 / abs(t.a))
    yy, xx = np.mgrid[-k:k + 1, -k:k + 1]
    cnt = nd.convolve(m.astype(np.float32), ((xx ** 2 + yy ** 2) <= k * k).astype(np.float32), mode="constant")
    return {"wl_canal_dist_m": np.minimum(dist, 5000.0).astype(np.float32).ravel(), "wl_canal_len_250": cnt.ravel()}


def units():
    """Waterlogging DEV units with tables: burned catalog + R29 plains."""
    from experiments.flood_round3 import build_r3 as B
    cat = json.load(open(os.path.join(os.path.dirname(__file__), "results", "burned_catalog.json")))
    have = {f[:-4] for f in os.listdir(B.TABLES)}
    out = [n for n in cat if "waterlogging" in cat[n]["tags"] and n in have]
    out += sorted(n for n in have if n.startswith("r3pl_"))
    return out


def one(n, ee, refs=None, tables=None):
    """Waterlogging features for one unit (cached in OUTD)."""
    from experiments.flood_round3 import build_r3 as B
    p = os.path.join(OUTD, f"{n}.npz")
    if os.path.exists(p):
        z = np.load(p)
        return {k: z[k] for k in FEATS}
    tb = np.load(os.path.join(tables or B.TABLES, f"{n}.npz"), allow_pickle=False)
    m = json.loads(str(tb["meta"]))
    peak = None
    rp = os.path.join(refs or B.REFS, f"{n}.npz")
    if os.path.exists(rp):
        rm = json.loads(str(np.load(rp)["meta"]))
        peak = rm.get("peak") or (rm.get("label_v3") or {}).get("peak")
    out = ee_layers(ee, m["grid"], m["event"], peak)
    plain = n.split("_")[1] if n.startswith("r3pl_") else None
    if plain == "south":
        plain = "south_sudan"
    out.update(canal_layers(m["grid"], PLAIN_PBF.get(plain, ())))
    os.makedirs(OUTD, exist_ok=True)
    np.savez_compressed(p, **out)
    print(n, {k: round(float(np.nanmean(v)), 3) for k, v in out.items()}, flush=True)
    return out


def main(argv=None):
    from experiments.flood_round3.diagnose_ee import _init
    ee = _init()
    os.makedirs(OUTD, exist_ok=True)
    for n in units():
        try:
            one(n, ee)
        except Exception as e:          # noqa: BLE001
            print(n, "FAILED", type(e).__name__, str(e)[:200], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
