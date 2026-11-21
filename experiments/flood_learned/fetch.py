"""
Fetch the layers the learned model needs that flood_baselines did not cache,
one event at a time, onto each event's cached 30 m box grid.

    python -m experiments.flood_learned.fetch            # every batch-0 event
    python -m experiments.flood_learned.fetch --only hanoi volos

Reused from flood_baselines' cache (not refetched): MERIT HAND and upa
(focal), FABDEM slope/relief, CHIRPS, IMERG, SoilGrids clay, JRC occurrence
and pre-event monthly frequency, S1 water history, distance to water, and the
pluvial inputs.

Fetched here, on the box grid grown by MARGIN_CELLS on every side (the
terrain derivatives and the mapped-water HAND need the surroundings):
  dem_glo30      Copernicus DEM GLO-30 2024_1 (bilinear)
  dem_fabdem     FABDEM v1-2 (bilinear)
  dem_gedtm30    GEDTM30 v1.2 COG, RAW values = metres (flood_core/gedtm30/
                 FINDING.md: the header's 0.1 scale is wrong and is NOT applied)
  upa_cell_km2   MERIT Hydro upa at the cell (nearest)
  hs_acc_cells   HydroSHEDS 15 arc-second flow accumulation (cells; nearest)
  jrc_occ_ext    JRC GSW 1.4 occurrence (for the permanent-water part of the
                 water mask on the margin grid)
  water_ext      OSM water (flood_baselines' cached Overpass answers) OR JRC
                 permanent water, as a bool raster
and on the box grid:
  jrc_recurrence JRC GSW 1.4 recurrence (%; NaN where never water)
  wc_<class>     ESA WorldCover class fractions (10 m -> 30 m mean): tree,
                 shrub, grass, crop, built, bare, wetland, mangrove. The map
                 year is the latest before the event year; events before 2021
                 have none, so they use the 2020 map (recorded per event).
  ndvi_pre       Sentinel-2 L1C (harmonized) median NDVI over the calendar year
                 before the event year (the project's water-history rule:
                 inputs read only years before ref_year), clouds masked
                 with Cloud Score+ (CSPLUS_CLEAR).
plus the event-level setting statistics (settings.py reads them).

Results go to CACHE/<unit>.npz; a cached unit is skipped, so a run resumes.
Disk is checked (15 GB rule) before every unit.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import os
import sys
import time
import traceback

import numpy as np

from experiments.flood_baselines import build as BUILD
from experiments.flood_learned import events as LE

CACHE = os.path.expanduser(os.environ.get("GEOWATCH_LEARNED_CACHE",
                                          "~/.cache/geowatch/flood_learned/inputs"))
# Same margin as flood_baselines' distance-to-water (half the 4 km box side),
# so the mapped-water HAND sees the same water the distance baseline sees.
MARGIN_CELLS = math.ceil(BUILD.DIST_MARGIN_M / BUILD.PIXEL_M)
GLO30_ASSET = "COPERNICUS/DEM/GLO30_2024_1"
FABDEM_ASSET = "projects/sat-io/open-datasets/FABDEM"
MERIT_ASSET = "MERIT/Hydro/v1_0_1"
HYDROSHEDS_ACC_ASSET = "WWF/HydroSHEDS/15ACC"
JRC_ASSET = "JRC/GSW1_4/GlobalSurfaceWater"
WORLDCOVER = {2020: "ESA/WorldCover/v100", 2021: "ESA/WorldCover/v200"}
WC_CLASSES = {"tree": 10, "shrub": 20, "grass": 30, "crop": 40, "built": 50, "bare": 60,
              "wetland": 90, "mangrove": 95}
S2_ASSET = "COPERNICUS/S2_HARMONIZED"
# Clouds: Google Cloud Score+ (Pasquarella et al. 2023, CVPR), linked per
# image. QA60 cannot be used: ESA stopped populating it from processing
# baseline 04.00 (25 Jan 2022), so it masks nothing on later images.
CSPLUS_ASSET = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
# cs_cdf >= 0.60 = clear: the value in the dataset's own example code; the
# catalogue recommends 0.50-0.65.
CSPLUS_CLEAR = 0.60
GHS_SMOD = "JRC/GHSL/P2023A/GHS_SMOD_V2-0/2020"
ERA5_LAND_MONTHLY = "ECMWF/ERA5_LAND/MONTHLY_AGGR"
CLIMATE_YEARS = (1991, 2020)         # the WMO standard normal period
KAPOS_RADIUS_M = 7000.0              # Kapos et al. (2000): local range within 7 km
GEDTM30_URL = ("/vsicurl/https://s3.opengeohub.org/global/dtm/v1.2/"
               "gedtm_rf_m_30m_s_20060101_20151231_go_epsg.4326.3855_v1.2.tif")
GEDTM30_NODATA_ABOVE = 1e30          # header nodata is 3.4028e38 (float32 max)


def path(name: str) -> str:
    return os.path.join(CACHE, f"{name}.npz")


def save(name: str, arrays: dict, meta: dict):
    os.makedirs(CACHE, exist_ok=True)
    tmp = path(name) + f".tmp{os.getpid()}.npz"
    np.savez_compressed(tmp, **arrays, meta=np.array(json.dumps(meta, default=str)))
    os.replace(tmp, path(name))


def load(name: str) -> dict:
    z = np.load(path(name), allow_pickle=False)
    return {"arrays": {k: z[k] for k in z.files if k != "meta"},
            "meta": json.loads(str(z["meta"]))}


def _mosaic(asset, region, band=0):
    import ee
    col = ee.ImageCollection(asset).filterBounds(region)
    # The projection of the selected band only: GLO-30 tiles above 60 degrees
    # N/S carry bands with different projections, and Image.projection() on
    # the whole image raises (EMSR683, Norway; flood_round2 D-B1).
    return col.mosaic().select(band).setDefaultProjection(ee.Image(col.first()).select(band).projection())


def margin_stack(te, she, crs, ll) -> dict:
    import ee
    from susceptibility.hydro_rasters import compute_pixels
    region = ee.Geometry.Rectangle(list(ll))
    merit = ee.Image(MERIT_ASSET)
    jrc = ee.Image(JRC_ASSET)
    img = ee.Image.cat([
        _mosaic(GLO30_ASSET, region, "DEM").resample("bilinear").rename("dem_glo30"),
        _mosaic(FABDEM_ASSET, region).resample("bilinear").rename("dem_fabdem"),
        merit.select("upa").rename("upa_cell_km2"),
        ee.Image(HYDROSHEDS_ACC_ASSET).select(0).rename("hs_acc_cells"),
        jrc.select("occurrence").unmask(0).rename("jrc_occ_ext"),
    ])
    return compute_pixels(img, te, she, crs, "learned margin stack")


def worldcover_year(event_year: int) -> int:
    before = [y for y in WORLDCOVER if y < event_year]
    return max(before) if before else min(WORLDCOVER)


def box_stack(t, shape, crs, ll, event_year: int) -> tuple:
    import ee
    from susceptibility.hydro_rasters import compute_pixels
    region = ee.Geometry.Rectangle(list(ll))
    wy = worldcover_year(event_year)
    wc = ee.ImageCollection(WORLDCOVER[wy]).first().select("Map")
    proj = wc.projection()
    fr = [wc.eq(v).rename(f"wc_{k}").toFloat().setDefaultProjection(proj)
          .reduceResolution(ee.Reducer.mean(), maxPixels=64) for k, v in WC_CLASSES.items()]
    y0 = event_year - 1

    def ndvi(im):
        ok = im.select("cs_cdf").gte(CSPLUS_CLEAR)
        return im.normalizedDifference(["B8", "B4"]).rename("ndvi_pre").updateMask(ok)
    s2 = (ee.ImageCollection(S2_ASSET).filterBounds(region)
          .filterDate(f"{y0}-01-01", f"{y0 + 1}-01-01")
          .linkCollection(ee.ImageCollection(CSPLUS_ASSET), ["cs_cdf"]))
    n_s2 = s2.size()
    img = ee.Image.cat([ee.Image(JRC_ASSET).select("recurrence").rename("jrc_recurrence"),
                        *fr, s2.map(ndvi).median().rename("ndvi_pre")])
    arr = compute_pixels(img, t, shape, crs, "learned box stack")
    return arr, {"worldcover_year": wy, "worldcover_asset": WORLDCOVER[wy],
                 "ndvi_year": y0, "s2_images": n_s2.getInfo()}


def gedtm30(te, she, crs, ll) -> np.ndarray:
    """GEDTM30 raw metres on the margin grid (bilinear). Raw values are used
    as metres by decision (FINDING.md); the header scale is not applied."""
    import rasterio
    from rasterio.warp import Resampling, reproject
    from rasterio.windows import from_bounds
    pad = 0.005
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="120",
                      GDAL_HTTP_MAX_RETRY="3"):
        with rasterio.open(GEDTM30_URL) as ds:
            win = from_bounds(ll[0] - pad, ll[1] - pad, ll[2] + pad, ll[3] + pad, ds.transform)
            win = win.round_offsets().round_lengths()
            src = ds.read(1, window=win, masked=False).astype(np.float64)   # raw, unscaled
            src_t = ds.window_transform(win)
            src_crs = ds.crs
    src[~np.isfinite(src) | (np.abs(src) > GEDTM30_NODATA_ABOVE)] = np.nan
    out = np.full(she, np.nan)
    reproject(src, out, src_transform=src_t, src_crs=src_crs, dst_transform=te,
              dst_crs=crs, resampling=Resampling.bilinear, src_nodata=np.nan, dst_nodata=np.nan)
    return out


def setting_stats(ll, event_year: int) -> dict:
    """Event-level numbers for the setting tags (events.py states the rules)."""
    import ee
    box = ee.Geometry.Rectangle(list(ll))
    centre = box.centroid(1)
    out = {}
    smod = ee.Image(GHS_SMOD).select(0)
    out["smod_hist"] = smod.reduceRegion(ee.Reducer.frequencyHistogram(), box, 1000,
                                         bestEffort=True).getInfo()
    dem = _mosaic(GLO30_ASSET, box.buffer(KAPOS_RADIUS_M + 2000), "DEM")
    slope = ee.Terrain.slope(dem)
    st = ee.Image.cat([dem.rename("z"), slope.rename("s")]).reduceRegion(
        ee.Reducer.median(), box, 90, bestEffort=True).getInfo()
    rng = dem.rename("z").reduceRegion(ee.Reducer.minMax(), centre.buffer(KAPOS_RADIUS_M), 90,
                                       bestEffort=True).getInfo()
    out["kapos"] = {"elev_median_m": st.get("z"), "slope_median_deg": st.get("s"),
                    "range_7km_m": (None if rng.get("z_max") is None
                                    else rng["z_max"] - rng["z_min"])}
    era = (ee.ImageCollection(ERA5_LAND_MONTHLY)
           .filterDate(f"{CLIMATE_YEARS[0]}-01-01", f"{CLIMATE_YEARS[1] + 1}-01-01"))
    def monthly(geom):
        clim = {}
        for m in range(1, 13):
            im = era.filter(ee.Filter.calendarRange(m, m, "month")).select(
                ["temperature_2m", "total_precipitation_sum"]).mean()
            clim[m] = im.reduceRegion(ee.Reducer.mean(), geom, 11132, bestEffort=True)
        return ee.Dictionary({str(k): v for k, v in clim.items()}).getInfo()
    clim = monthly(box)
    out["era5_region"] = "box"
    if any(v.get("temperature_2m") is None for v in clim.values()):
        # ERA5-Land is land-only: a coastal box can fall on masked sea cells.
        # Grow it by one native ERA5-Land cell (0.1 deg ~ 11.1 km).
        clim = monthly(box.buffer(11132))
        out["era5_region"] = "box + 11.1 km"
    out["era5_monthly"] = {m: {"t_c": v["temperature_2m"] - 273.15,
                               "p_mm": v["total_precipitation_sum"] * 1000.0}
                           for m, v in clim.items()}
    from ingestion.coastal import get_coastline_context
    cc = get_coastline_context(*ll)
    out["coast_distance_km"] = cc.get("distance_km")
    out["centre_lat"] = (ll[1] + ll[3]) / 2
    return out


def water_ext(name, te, she, crs, ll, occ_ext) -> tuple:
    """OSM water (flood_baselines' cached Overpass answers, same key) OR JRC
    permanent water, on the margin grid."""
    from experiments.flood_validation import references as R
    from vector.sources import bbox_key
    osm, counts = BUILD.water_mask(ll, te, she, crs, bbox_key(f"bl_{name}", ll))
    return osm | ~R.not_permanent(occ_ext), counts


def fetch_unit(entry: dict) -> tuple:
    from susceptibility.hydro_rasters import grid_lonlat_bounds
    name = entry["unit"]
    base = BUILD.load(name)
    g = base["meta"]["grid"]
    crs, shape, t = g["crs"], tuple(g["shape"]), BUILD._affine(base["meta"])
    te, she = BUILD.expanded(t, shape, MARGIN_CELLS)
    ll_ext = grid_lonlat_bounds(te, she, crs)
    ll_box = grid_lonlat_bounds(t, shape, crs)
    year = datetime.date.fromisoformat(entry["meta"]["event"]).year
    meta = {"unit": name, "event": entry["meta"]["event"], "margin_cells": MARGIN_CELLS,
            "grid": g, "box_lonlat": ll_box, "ext_lonlat": ll_ext, "errors": {},
            "timings_s": {}}
    arrays = {}

    def step(label, fn):
        t0 = time.time()
        try:
            return fn()
        except Exception as e:      # noqa: BLE001 -- recorded; the layer is then missing
            meta["errors"][label] = f"{type(e).__name__}: {e}"[:400]
            return None
        finally:
            meta["timings_s"][label] = round(time.time() - t0, 1)

    ms = step("margin_stack", lambda: BUILD._call(lambda: margin_stack(te, she, crs, ll_ext),
                                                  f"margin {name}"))
    if ms is None:
        raise RuntimeError(f"{name}: margin stack failed: {meta['errors']}")
    arrays.update({k: v.astype(np.float32) for k, v in ms.items()})
    w = step("water_ext", lambda: water_ext(name, te, she, crs, ll_ext, ms["jrc_occ_ext"]))
    if w is not None:
        arrays["water_ext"] = w[0]
        meta["osm_counts"] = w[1]
        meta["osm_complete"] = all(v is not None for v in w[1].values())
    bs = step("box_stack", lambda: BUILD._call(lambda: box_stack(t, shape, crs, ll_box, year),
                                               f"box {name}"))
    if bs is not None:
        arrays.update({k: v.astype(np.float32) for k, v in bs[0].items()})
        meta.update(bs[1])
    gd = step("gedtm30", lambda: gedtm30(te, she, crs, ll_ext))
    if gd is not None:
        arrays["dem_gedtm30"] = gd.astype(np.float32)
    meta["settings"] = step("settings", lambda: BUILD._call(lambda: setting_stats(ll_box, year),
                                                            f"settings {name}"))
    ex = step("extra", lambda: BUILD._call(lambda: extra_stack(t, shape, crs, ll_box), f"extra {name}"))
    if ex is not None:
        arrays.update(ex)
    return arrays, meta


# flood_final additions (coastal features; a second built-up source).
GHSL_BUILT_S = "JRC/GHSL/P2023A/GHS_BUILT_S/2020"     # built-up surface, m2 per 100 m cell
GHSL_CELL_M2 = 100.0 * 100.0
# The coastal module's existing search radius (configs/coastal_constants.py):
# beyond it distance is capped, never extrapolated.
COAST_SEARCH_M = 50_000.0


def extra_stack(t, shape, crs, ll) -> dict:
    """dist_coast_m: distance (m) to the sat-io shoreline polygons' edge,
    capped at COAST_SEARCH_M (ingestion/coastal.py's datasets);
    ghsl_built_frac: GHSL 2020 built-up surface share of each 100 m cell."""
    import ee
    from configs.coastal_constants import COASTAL_SEARCH_RADIUS_KM
    from ingestion.coastal import BIG_ISLANDS_ASSET, MAINLANDS_ASSET, SMALL_ISLANDS_ASSET
    from susceptibility.hydro_rasters import compute_pixels
    assert COASTAL_SEARCH_RADIUS_KM * 1000.0 == COAST_SEARCH_M
    region = ee.Geometry.Rectangle(list(ll)).buffer(COAST_SEARCH_M)
    land = (ee.FeatureCollection(MAINLANDS_ASSET).merge(ee.FeatureCollection(BIG_ISLANDS_ASSET))
            .merge(ee.FeatureCollection(SMALL_ISLANDS_ASSET)).filterBounds(region))
    edge = ee.Image().byte().paint(land, 1, 1)             # polygon outlines = the shoreline
    dist = (edge.fastDistanceTransform(2048, "pixels", "squared_euclidean").sqrt()
            .multiply(ee.Image.pixelArea().sqrt()))
    dist = dist.min(COAST_SEARCH_M).unmask(COAST_SEARCH_M)
    built = ee.Image(GHSL_BUILT_S).select(0).divide(GHSL_CELL_M2)
    img = ee.Image.cat([dist.rename("dist_coast_m"), built.rename("ghsl_built_frac")])
    return {k: v.astype(np.float32) for k, v in compute_pixels(img, t, shape, crs,
                                                               "extra stack").items()}


def add_extra(names) -> int:
    """Add extra_stack to cached units that lack it."""
    for n in names:
        if not os.path.exists(path(n)):
            continue
        u = load(n)
        if "dist_coast_m" in u["arrays"]:
            continue
        g = u["meta"]["grid"]
        t, shape, crs = BUILD._affine(u["meta"]), tuple(g["shape"]), g["crs"]
        try:
            u["arrays"].update(BUILD._call(lambda: extra_stack(t, shape, crs, u["meta"]["box_lonlat"]),
                                           f"extra {n}"))
            u["meta"]["errors"].pop("extra", None)
            print(f"── {n}: extra added", flush=True)
        except Exception as e:      # noqa: BLE001
            u["meta"]["errors"]["extra"] = f"{type(e).__name__}: {e}"[:400]
            print(f"── {n}: extra failed: {u['meta']['errors']['extra'][:200]}", flush=True)
        save(n, u["arrays"], u["meta"])
    return 0


def redo_step(cat, step: str) -> int:
    """Redo one failed step of cached units, keeping everything else."""
    import datetime as _dt
    from susceptibility.hydro_rasters import grid_lonlat_bounds
    for c in cat:
        n = c["unit"]
        if not os.path.exists(path(n)):
            continue
        u = load(n)
        if step not in u["meta"]["errors"]:
            continue
        g = u["meta"]["grid"]
        t, shape, crs = BUILD._affine(u["meta"]), tuple(g["shape"]), g["crs"]
        te, she = BUILD.expanded(t, shape, MARGIN_CELLS)
        try:
            if step == "settings":
                year = _dt.date.fromisoformat(c["meta"]["event"]).year
                u["meta"]["settings"] = BUILD._call(
                    lambda: setting_stats(grid_lonlat_bounds(t, shape, crs), year), f"settings {n}")
            else:
                u["arrays"]["dem_gedtm30"] = gedtm30(te, she, crs, grid_lonlat_bounds(te, she, crs)
                                                     ).astype(np.float32)
            u["meta"]["errors"].pop(step)
            print(f"── {n}: {step} redone", flush=True)
        except Exception as e:      # noqa: BLE001
            u["meta"]["errors"][step] = f"{type(e).__name__}: {e}"[:400]
            print(f"── {n}: {step} failed again: {u['meta']['errors'][step][:200]}", flush=True)
        save(n, u["arrays"], u["meta"])
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--redo-failed", action="store_true",
                    help="refetch cached units that recorded any step error")
    ap.add_argument("--redo-step", choices=("settings", "gedtm30"),
                    help="cached units whose step failed: redo that step only, in place")
    ap.add_argument("--add-extra", action="store_true",
                    help="add the coastal / GHSL layers to cached units that lack them")
    args = ap.parse_args(argv)
    print(f"free disk {BUILD.check_disk():.1f} GB", flush=True)
    import ee
    from experiments.flood_validation import references as R
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    ee.data.setDeadline(R.EE_TIMEOUT_S * 1000)
    cat = LE.batch0()
    if args.only:
        cat = [c for c in cat if c["unit"] in set(args.only)]
    if args.redo_step:
        return redo_step(cat, args.redo_step)
    if args.add_extra:
        return add_extra([c["unit"] for c in cat])
    log = {}
    for c in cat:
        name = c["unit"]
        if os.path.exists(path(name)):
            if not (args.redo_failed and load(name)["meta"].get("errors")):
                print(f"── {name}: cached", flush=True)
                continue
        BUILD.check_disk()
        t0 = time.time()
        print(f"── {name}: fetch", flush=True)
        try:
            arrays, meta = fetch_unit(c)
            save(name, arrays, meta)
            log[name] = {"ok": True, "s": round(time.time() - t0), "errors": meta["errors"]}
        except Exception as e:      # noqa: BLE001 -- named, then the next unit
            traceback.print_exc()
            log[name] = {"ok": False, "s": round(time.time() - t0),
                         "error": f"{type(e).__name__}: {e}"[:400]}
        print(f"   {name}: {json.dumps(log[name], default=str)[:500]}", flush=True)
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, f"fetch_log_{int(time.time())}.json"), "w") as fh:
        json.dump(log, fh, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
