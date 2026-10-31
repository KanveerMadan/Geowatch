"""
Per-pixel hydrology inputs for fluvial, flash flood and waterlogging (item 26,
Phase 1a). Replaces their AOI-wide scalars. Method fixed in
experiments/flood_validation/PREREGISTRATION_ROUND2.md before any run.

Every layer is a declared surface (susceptibility/inputs.py) holding a
PHYSICAL value, not a 0-1 score -- each module scores its own components:

    hand_m               MERIT Hydro `hnd` (90 m), bilinear
    upa_near_km2         MERIT Hydro `upa`, focal max within
                         FLUVIAL_DRAINAGE_SEARCH_RADIUS_M, nearest: the
                         upstream area of the largest drainage line near the
                         cell (a cell's own `upa` is ~0 on every hillslope)
    slope_deg            ee.Terrain.slope of FABDEM (30 m), bilinear
    relief_slope_deg     the same slope, focal mean within
                         FLASH_FLOOD_RELIEF_RADIUS_M
    rain_annual_mm       CHIRPS daily, mean annual total over the
                         FLASH_FLOOD_INTENSITY_YEARS calendar years before
                         `ref_year`, nearest (0.05 deg)
    rain_intensity_mm_h  IMERG V07 half-hourly `precipitation`, the
                         FLASH_FLOOD_INTENSITY_PERCENTILE over the same
                         years, nearest (0.1 deg)

Flood round 4 (PREREGISTRATION_ROUND4.md) adds:

    upa_flash_km2        MERIT `upa` focal max within
                         FLASH_POWER_DRAINAGE_RADIUS_M (300 m), nearest
    clay_pct             SoilGrids clay, thickness-weighted 0-30 cm, %; gaps
                         take the focal mean within 1 km
    rain_design_day_mm   CHIRPS daily, mean annual maximum 1-day total over the
                         PLUVIAL_DESIGN_STORM_YEARS before `ref_year` (0.05 deg)
    jrc_water_freq       JRC GSW monthly history: water months / observed
                         months, 1984 to min(ref_year - 1, 2021)
    s1_water_freq        Sentinel-1 IW VV: share of acquisitions below
                         WATERLOGGING_S1_WATER_DB over the
                         WATERLOGGING_S1_YEARS calendar years before `ref_year`

The two water-history layers read only years before `ref_year`.

Both rainfall layers are computed on their own native grid and mapped to the
hydrology grid locally (nearest_from_native): asking Earth Engine for a
10-year IMERG percentile on a 30 m grid ran past 600 s twice.

HAND is MERIT's, not derived from FABDEM: MERIT's is routed by its authors,
and a FABDEM HAND needs a stream network this project does not have.

All `experimental`. Every Earth Engine call has a hard client deadline
(ee_timeout.call) on top of ee.data.setDeadline.
"""
from __future__ import annotations

import warnings
from contextlib import contextmanager

import numpy as np

from configs.flash_flood_constants import (
    FLASH_FLOOD_INTENSITY_PERCENTILE, FLASH_FLOOD_INTENSITY_YEARS, FLASH_FLOOD_RELIEF_RADIUS_M,
    FLASH_POWER_DRAINAGE_RADIUS_M,
)
from configs.fluvial_constants import FLUVIAL_DRAINAGE_SEARCH_RADIUS_M
from configs.pluvial_constants import HYDROLOGY_PIXEL_M, PLUVIAL_DESIGN_STORM_YEARS
from configs.waterlogging_constants import (
    WATERLOGGING_CLAY_FILL_RADIUS_M, WATERLOGGING_JRC_MONTHLY_FIRST_YEAR,
    WATERLOGGING_JRC_MONTHLY_LAST_YEAR, WATERLOGGING_S1_WATER_DB, WATERLOGGING_S1_YEARS,
)
from susceptibility.inputs import check_surface, surface

MERIT_ASSET = "MERIT/Hydro/v1_0_1"
FABDEM_ASSET = "projects/sat-io/open-datasets/FABDEM"
CHIRPS_ASSET = "UCSB-CHG/CHIRPS/DAILY"
IMERG_ASSET = "NASA/GPM_L3/IMERG_V07"
SOILGRIDS_CLAY_ASSET = "projects/soilgrids-isric/clay_mean"
CLAY_BANDS = {"clay_0-5cm_mean": 5.0, "clay_5-15cm_mean": 10.0, "clay_15-30cm_mean": 15.0}
JRC_MONTHLY_ASSET = "JRC/GSW1_4/MonthlyHistory"
S1_ASSET = "COPERNICUS/S1_GRD"
NODATA = -9999.0
EE_TIMEOUT_S = 600           # one computePixels must beat this
EE_RETRIES = 2

LAYERS = ("hand_m", "upa_near_km2", "slope_deg", "relief_slope_deg",
          "rain_annual_mm", "rain_intensity_mm_h",
          "upa_flash_km2", "clay_pct", "rain_design_day_mm", "jrc_water_freq", "s1_water_freq")
SOURCES = {
    "hand_m": (MERIT_ASSET, "hnd, bilinear"),
    "upa_near_km2": (MERIT_ASSET, f"upa focal max r={FLUVIAL_DRAINAGE_SEARCH_RADIUS_M:g} m, nearest"),
    "slope_deg": (FABDEM_ASSET, "ee.Terrain.slope, bilinear"),
    "relief_slope_deg": (FABDEM_ASSET, f"slope focal mean r={FLASH_FLOOD_RELIEF_RADIUS_M:g} m"),
    "rain_annual_mm": (CHIRPS_ASSET, f"mean annual total, {FLASH_FLOOD_INTENSITY_YEARS} years"),
    "rain_intensity_mm_h": (IMERG_ASSET, f"p{FLASH_FLOOD_INTENSITY_PERCENTILE:g} half-hourly "
                                         f"rate, {FLASH_FLOOD_INTENSITY_YEARS} years"),
    "upa_flash_km2": (MERIT_ASSET, f"upa focal max r={FLASH_POWER_DRAINAGE_RADIUS_M:g} m, nearest"),
    "clay_pct": (SOILGRIDS_CLAY_ASSET, "clay 0-30 cm thickness-weighted, %, "
                                       f"gaps focal mean r={WATERLOGGING_CLAY_FILL_RADIUS_M:g} m"),
    "rain_design_day_mm": (CHIRPS_ASSET, f"mean annual max 1-day total, "
                                         f"{PLUVIAL_DESIGN_STORM_YEARS} years"),
    "jrc_water_freq": (JRC_MONTHLY_ASSET, "water months / observed months, years before ref_year"),
    "s1_water_freq": (S1_ASSET, f"IW VV < {WATERLOGGING_S1_WATER_DB:g} dB share, "
                                f"{WATERLOGGING_S1_YEARS} years before ref_year"),
}


# ── pure ────────────────────────────────────────────────────────────────

def clip01(a) -> np.ndarray:
    return np.clip(np.asarray(a, dtype=np.float64), 0.0, 1.0)


def layer(rasters: dict | None, name: str):
    """The raster of a declared layer, or None if absent or all-NaN."""
    if not rasters or name not in rasters.get("layers", {}):
        return None
    r = np.asarray(check_surface(rasters["layers"][name], name)["raster"], dtype=np.float64)
    return r if np.isfinite(r).any() else None


def weighted_map(components: dict, weights: dict) -> np.ndarray | None:
    """Per-pixel weighted mean of the available components. A component
    that is NaN at a pixel drops out there; zero total weight -> NaN."""
    num = den = None
    for name, comp in components.items():
        w = float(weights.get(name, 0.0))
        if comp is None or w == 0.0:
            continue
        c = np.asarray(comp, dtype=np.float64)
        ok = np.isfinite(c)
        n, d = np.where(ok, w * c, 0.0), np.where(ok, w, 0.0)
        num, den = (n, d) if num is None else (num + n, den + d)
    if num is None:
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(den > 0, num / den, np.nan)


def map_summary(m: np.ndarray, classify) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = float(np.nanmean(m)) if np.isfinite(m).any() else None
    return {"aoi_mean_score": None if mean is None else round(mean, 4),
            "aoi_mean_class": classify(mean)}


def utm_grid(bbox, pixel_m: float = HYDROLOGY_PIXEL_M):
    """(transform, (rows, cols), crs string): a pixel_m grid in the UTM zone
    of the bbox centre, snapped to multiples of pixel_m, covering the bbox."""
    from pyproj import Transformer
    from rasterio.transform import from_origin
    w, s, e, n = bbox
    lon, lat = (w + e) / 2, (s + n) / 2
    epsg = (32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1
    t = Transformer.from_crs(4326, epsg, always_xy=True)
    xs, ys = t.transform([w, e, w, e], [s, s, n, n])
    x0 = np.floor(min(xs) / pixel_m) * pixel_m
    y1 = np.ceil(max(ys) / pixel_m) * pixel_m
    cols = int(np.ceil((max(xs) - x0) / pixel_m))
    rows = int(np.ceil((y1 - min(ys)) / pixel_m))
    return from_origin(x0, y1, pixel_m, pixel_m), (rows, cols), f"EPSG:{epsg}"


def ee_grid(transform, shape, crs: str) -> dict:
    H, W = shape
    return {"dimensions": {"width": W, "height": H},
            "affineTransform": {"scaleX": transform.a, "shearX": 0, "translateX": transform.c,
                                "shearY": 0, "scaleY": transform.e, "translateY": transform.f},
            "crsCode": crs}


# ── Earth Engine ────────────────────────────────────────────────────────

def ensure_deadline(ms: int) -> None:
    """Set Earth Engine's per-request deadline only if none is set: the
    analysis pipeline keeps one deadline per process (analysis/stages.py), and
    setDeadline rebuilds the client. The hard client-side limit is
    ee_timeout.call either way."""
    import ee
    try:
        current = ee.data._get_state().deadline_ms
    except Exception:            # noqa: BLE001 -- older client: set it
        current = None
    if not current:
        ee.data.setDeadline(ms)


def compute_pixels(img, transform, shape, crs: str, label: str,
                   timeout: int = EE_TIMEOUT_S) -> dict:
    """{band: float64 array, NaN where no data}, with a hard deadline."""
    import ee
    from ee_timeout import call
    ensure_deadline(EE_TIMEOUT_S * 1000)
    arr = call(lambda: ee.data.computePixels({
        "expression": img.unmask(NODATA).toFloat(), "fileFormat": "NUMPY_NDARRAY",
        "grid": ee_grid(transform, shape, crs)}), timeout=timeout, retries=EE_RETRIES,
        label=label)
    return {b: np.where(arr[b] == NODATA, np.nan, arr[b]).astype(np.float64)
            for b in arr.dtype.names}


def _terrain_image(bbox):
    import ee
    region = ee.Geometry.Rectangle(list(bbox)).buffer(5000)
    merit = ee.Image(MERIT_ASSET)
    upa_near = (merit.select("upa")
                .focalMax(FLUVIAL_DRAINAGE_SEARCH_RADIUS_M, "circle", "meters")
                .reproject(merit.projection()))
    col = ee.ImageCollection(FABDEM_ASSET).filterBounds(region)
    # mosaic() drops the native projection (terrain.fetch_dem's fix).
    dem = col.mosaic().setDefaultProjection(col.first().projection()).select(0)
    slope = ee.Terrain.slope(dem)
    relief = slope.focalMean(FLASH_FLOOD_RELIEF_RADIUS_M, "circle", "meters").reproject(
        col.first().projection())
    upa_flash = (merit.select("upa")
                 .focalMax(FLASH_POWER_DRAINAGE_RADIUS_M, "circle", "meters")
                 .reproject(merit.projection()))
    soil = ee.Image(SOILGRIDS_CLAY_ASSET)
    clay = (ee.Image.cat([soil.select(b).multiply(t) for b, t in CLAY_BANDS.items()])
            .reduce(ee.Reducer.sum()).divide(sum(CLAY_BANDS.values()) * 10.0))
    clay = clay.unmask(clay.focalMean(WATERLOGGING_CLAY_FILL_RADIUS_M, "circle", "meters")
                       .reproject(soil.projection()))
    return ee.Image.cat([
        merit.select("hnd").resample("bilinear").rename("hand_m"),
        upa_near.rename("upa_near_km2"),
        slope.resample("bilinear").rename("slope_deg"),
        relief.rename("relief_slope_deg"),
        upa_flash.rename("upa_flash_km2"),
        clay.rename("clay_pct"),
    ])


RAIN_NATIVE_DEG = {"rain_annual_mm": 0.05, "rain_intensity_mm_h": 0.1,     # CHIRPS, IMERG
                   "rain_design_day_mm": 0.05}
RAIN_TIMEOUT_S = 1200        # a 10-year IMERG percentile took 314 s at one point
RAIN_LAYERS = ("rain_annual_mm", "rain_intensity_mm_h", "rain_design_day_mm")
WATER_HISTORY_LAYERS = ("jrc_water_freq", "s1_water_freq")
# C71: the IMERG percentile gets its own request deadline, set explicitly even
# inside the analysis pipeline (whose 240 s per-request deadline it cannot
# beat) and restored afterwards, so every other request keeps the caller's.
# One attempt: a retry after a full deadline would outrun the stage's limit.
IMERG_LAYER = "rain_intensity_mm_h"
# Flood round 4: a multi-year S1 / JRC monthly reduction is one request each,
# with its own deadline (restored afterwards), like IMERG.
WATER_HISTORY_DEADLINE_S = RAIN_TIMEOUT_S
IMERG_DEADLINE_S = RAIN_TIMEOUT_S
IMERG_RETRIES = 1


@contextmanager
def request_deadline(ms: int):
    """Earth Engine's per-request deadline set to `ms` for the block, then
    put back to what it was (0 = none, EE's default)."""
    import ee
    prev = ee.data._get_state().deadline_ms
    ee.data.setDeadline(ms)
    try:
        yield
    finally:
        ee.data.setDeadline(prev or 0)


def _rain_images(ref_year: int):
    import ee
    y0, y1 = f"{ref_year - FLASH_FLOOD_INTENSITY_YEARS}-01-01", f"{ref_year}-01-01"
    annual = (ee.ImageCollection(CHIRPS_ASSET).filterDate(y0, y1).select("precipitation")
              .sum().divide(FLASH_FLOOD_INTENSITY_YEARS).rename("rain_annual_mm"))
    imerg = ee.ImageCollection(IMERG_ASSET).filterDate(y0, y1).select("precipitation")
    intensity = (imerg.reduce(ee.Reducer.percentile([FLASH_FLOOD_INTENSITY_PERCENTILE]))
                 .rename("rain_intensity_mm_h"))
    years = ee.List.sequence(ref_year - PLUVIAL_DESIGN_STORM_YEARS, ref_year - 1)
    chirps = ee.ImageCollection(CHIRPS_ASSET).select("precipitation")
    design = (ee.ImageCollection(years.map(lambda y: chirps.filter(
        ee.Filter.calendarRange(y, y, "year")).max()))
        .mean().rename("rain_design_day_mm"))
    return {"rain_annual_mm": annual, "rain_intensity_mm_h": intensity,
            "rain_design_day_mm": design}


def water_history_years(ref_year: int) -> dict:
    """{layer: (first year, last year)} read for ref_year: only years before it."""
    jrc_last = min(ref_year - 1, WATERLOGGING_JRC_MONTHLY_LAST_YEAR)
    return {"jrc_water_freq": (WATERLOGGING_JRC_MONTHLY_FIRST_YEAR, jrc_last),
            "s1_water_freq": (ref_year - WATERLOGGING_S1_YEARS, ref_year - 1)}


def _water_history_images(bbox, ref_year: int):
    import ee
    yrs = water_history_years(ref_year)
    region = ee.Geometry.Rectangle(list(bbox)).buffer(1000)
    j0, j1 = yrs["jrc_water_freq"]
    m = ee.ImageCollection(JRC_MONTHLY_ASSET).filterDate(f"{j0}-01-01", f"{j1 + 1}-01-01")
    water = m.map(lambda i: i.select("water").eq(2)).sum()
    seen = m.map(lambda i: i.select("water").gte(1)).sum()
    jrc = water.divide(seen.max(1)).updateMask(seen.gt(0)).rename("jrc_water_freq")
    s0, s1 = yrs["s1_water_freq"]
    col = (ee.ImageCollection(S1_ASSET).filterBounds(region)
           .filterDate(f"{s0}-01-01", f"{s1 + 1}-01-01")
           .filter(ee.Filter.eq("instrumentMode", "IW"))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
           .select("VV"))
    s1img = col.map(lambda i: i.lt(WATERLOGGING_S1_WATER_DB)).mean().rename("s1_water_freq")
    return {"jrc_water_freq": jrc, "s1_water_freq": s1img}


def native_grid(bbox, deg: float):
    """(x0, y1, cols, rows) of the deg-aligned lon/lat grid covering bbox --
    CHIRPS and IMERG cell edges sit on multiples of their resolution."""
    w, s, e, n = bbox
    x0, y1 = np.floor(w / deg) * deg, np.ceil(n / deg) * deg
    return x0, y1, int(np.ceil((e - x0) / deg - 1e-9)), int(np.ceil((y1 - s) / deg - 1e-9))


def grid_lonlat_bounds(transform, shape, crs: str) -> tuple:
    """(W, S, E, N) in lon/lat of the hydrology grid's full footprint -- a
    snapped UTM grid reaches past the lon/lat bbox it was built from."""
    from pyproj import Transformer
    H, W = shape
    cols, rows = np.meshgrid([0, W / 2, W], [0, H / 2, H])
    xs, ys = transform * (cols, rows)
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(xs, ys)
    return (float(np.min(lon)), float(np.min(lat)), float(np.max(lon)), float(np.max(lat)))


def nearest_from_native(values, x0: float, y1: float, deg: float, transform, shape, crs: str):
    """Each hydrology cell takes the value of the native cell its centre
    falls in (nearest). NaN outside the native array."""
    from pyproj import Transformer
    H, W = shape
    cols, rows = np.meshgrid(np.arange(W) + 0.5, np.arange(H) + 0.5)
    xs, ys = transform * (cols, rows)
    lon, lat = Transformer.from_crs(crs, 4326, always_xy=True).transform(xs, ys)
    c = np.floor((np.asarray(lon) - x0) / deg).astype(int)
    r = np.floor((y1 - np.asarray(lat)) / deg).astype(int)
    v = np.asarray(values, dtype=np.float64)
    ok = (r >= 0) & (r < v.shape[0]) & (c >= 0) & (c < v.shape[1])
    out = np.full(shape, np.nan)
    out[ok] = v[r[ok], c[ok]]
    return out


def _rain_layer(img, name, bbox, transform, shape, crs):
    """A rainfall layer computed on its own native grid (a handful of cells)
    and mapped nearest onto the hydrology grid. Same statistic as sampling
    it at 30 m, without asking Earth Engine to evaluate the 10-year
    reduction once per 30 m output pixel."""
    import ee
    from ee_timeout import call
    from rasterio.transform import from_origin
    deg = RAIN_NATIVE_DEG[name]
    x0, y1, cols, rows = native_grid(grid_lonlat_bounds(transform, shape, crs), deg)

    def fetch(timeout, retries):
        return call(lambda: ee.data.computePixels({
            "expression": img.unmask(NODATA).toFloat(), "fileFormat": "NUMPY_NDARRAY",
            "grid": ee_grid(from_origin(x0, y1, deg, deg), (rows, cols), "EPSG:4326")}),
            timeout=timeout, retries=retries, label=name)

    if name == IMERG_LAYER:
        with request_deadline(IMERG_DEADLINE_S * 1000):
            arr = fetch(IMERG_DEADLINE_S, IMERG_RETRIES)
    else:
        ensure_deadline(RAIN_TIMEOUT_S * 1000)
        arr = fetch(RAIN_TIMEOUT_S, EE_RETRIES)
    v = np.where(arr[name] == NODATA, np.nan, arr[name]).astype(np.float64)
    return nearest_from_native(v, x0, y1, deg, transform, shape, crs)


def fetch_hydro_rasters(bbox, transform, shape, crs: str, ref_year: int,
                        rainfall=True, water_history=True) -> dict:
    """The LAYERS inputs on the given grid. Terrain, each rainfall layer and
    each water-history layer are separate calls, so a timeout loses only that
    layer (it is recorded under `errors` and the component is excluded
    downstream). `rainfall` / `water_history`: True (all), False (none), or
    the names wanted -- a layer not requested is recorded as such."""
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    wanted = (RAIN_LAYERS if rainfall is True else () if rainfall is False else tuple(rainfall))
    bands, errors = {}, {}
    bands.update(compute_pixels(_terrain_image(bbox), transform, shape, crs, "terrain"))
    images = _rain_images(ref_year)
    for name in RAIN_LAYERS:
        if name not in wanted:
            errors[name] = "not requested"
            continue
        try:
            bands[name] = _rain_layer(images[name], name, bbox, transform, shape, crs)
        except Exception as e:   # noqa: BLE001 -- recorded, component excluded
            errors[name] = f"{type(e).__name__}: {e}"
    wanted_w = (WATER_HISTORY_LAYERS if water_history is True else ()
                if water_history is False else tuple(water_history))
    hist = _water_history_images(bbox, ref_year) if wanted_w else {}
    for name in WATER_HISTORY_LAYERS:
        if name not in wanted_w:
            errors[name] = "not requested"
            continue
        try:
            with request_deadline(WATER_HISTORY_DEADLINE_S * 1000):
                bands[name] = compute_pixels(hist[name], transform, shape, crs, name,
                                             timeout=WATER_HISTORY_DEADLINE_S)[name]
        except Exception as e:   # noqa: BLE001 -- recorded, component excluded
            errors[name] = f"{type(e).__name__}: {e}"
    layers = {k: surface(bands[k], source=SOURCES[k][0], method=SOURCES[k][1],
                         validation_status="experimental")
              for k in LAYERS if k in bands}
    return {"status": "available", "transform": transform, "shape": tuple(shape), "crs": crs,
            "ref_year": ref_year, "layers": layers, "errors": errors}
