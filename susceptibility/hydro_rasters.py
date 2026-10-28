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

HAND is MERIT's, not derived from FABDEM: MERIT's is routed by its authors,
and a FABDEM HAND needs a stream network this project does not have.

All `experimental`. Every Earth Engine call has a hard client deadline
(ee_timeout.call) on top of ee.data.setDeadline.
"""
from __future__ import annotations

import warnings

import numpy as np

from configs.flash_flood_constants import (
    FLASH_FLOOD_INTENSITY_PERCENTILE, FLASH_FLOOD_INTENSITY_YEARS, FLASH_FLOOD_RELIEF_RADIUS_M,
)
from configs.fluvial_constants import FLUVIAL_DRAINAGE_SEARCH_RADIUS_M
from configs.pluvial_constants import HYDROLOGY_PIXEL_M
from susceptibility.inputs import check_surface, surface

MERIT_ASSET = "MERIT/Hydro/v1_0_1"
FABDEM_ASSET = "projects/sat-io/open-datasets/FABDEM"
CHIRPS_ASSET = "UCSB-CHG/CHIRPS/DAILY"
IMERG_ASSET = "NASA/GPM_L3/IMERG_V07"
NODATA = -9999.0
EE_TIMEOUT_S = 600           # one computePixels must beat this
EE_RETRIES = 2

LAYERS = ("hand_m", "upa_near_km2", "slope_deg", "relief_slope_deg",
          "rain_annual_mm", "rain_intensity_mm_h")
SOURCES = {
    "hand_m": (MERIT_ASSET, "hnd, bilinear"),
    "upa_near_km2": (MERIT_ASSET, f"upa focal max r={FLUVIAL_DRAINAGE_SEARCH_RADIUS_M:g} m, nearest"),
    "slope_deg": (FABDEM_ASSET, "ee.Terrain.slope, bilinear"),
    "relief_slope_deg": (FABDEM_ASSET, f"slope focal mean r={FLASH_FLOOD_RELIEF_RADIUS_M:g} m"),
    "rain_annual_mm": (CHIRPS_ASSET, f"mean annual total, {FLASH_FLOOD_INTENSITY_YEARS} years"),
    "rain_intensity_mm_h": (IMERG_ASSET, f"p{FLASH_FLOOD_INTENSITY_PERCENTILE:g} half-hourly "
                                         f"rate, {FLASH_FLOOD_INTENSITY_YEARS} years"),
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

def compute_pixels(img, transform, shape, crs: str, label: str) -> dict:
    """{band: float64 array, NaN where no data}, with a hard deadline."""
    import ee
    from ee_timeout import call
    ee.data.setDeadline(EE_TIMEOUT_S * 1000)
    arr = call(lambda: ee.data.computePixels({
        "expression": img.unmask(NODATA).toFloat(), "fileFormat": "NUMPY_NDARRAY",
        "grid": ee_grid(transform, shape, crs)}), timeout=EE_TIMEOUT_S, retries=EE_RETRIES,
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
    return ee.Image.cat([
        merit.select("hnd").resample("bilinear").rename("hand_m"),
        upa_near.rename("upa_near_km2"),
        slope.resample("bilinear").rename("slope_deg"),
        relief.rename("relief_slope_deg"),
    ])


def _rain_images(ref_year: int):
    import ee
    y0, y1 = f"{ref_year - FLASH_FLOOD_INTENSITY_YEARS}-01-01", f"{ref_year}-01-01"
    annual = (ee.ImageCollection(CHIRPS_ASSET).filterDate(y0, y1).select("precipitation")
              .sum().divide(FLASH_FLOOD_INTENSITY_YEARS)
              .setDefaultProjection(ee.ImageCollection(CHIRPS_ASSET).first().projection())
              .rename("rain_annual_mm"))
    imerg = ee.ImageCollection(IMERG_ASSET).filterDate(y0, y1).select("precipitation")
    intensity = (imerg.reduce(ee.Reducer.percentile([FLASH_FLOOD_INTENSITY_PERCENTILE]))
                 .setDefaultProjection(imerg.first().projection())
                 .rename("rain_intensity_mm_h"))
    return annual, intensity


def fetch_hydro_rasters(bbox, transform, shape, crs: str, ref_year: int,
                        rainfall: bool = True) -> dict:
    """Every LAYERS input on the given grid. Terrain and each rainfall layer
    are separate calls, so a rainfall timeout loses only that layer (it is
    recorded under `errors` and the component is excluded downstream).
    rainfall=False skips both rainfall layers (recorded the same way)."""
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    bands, errors = {}, {}
    bands.update(compute_pixels(_terrain_image(bbox), transform, shape, crs, "terrain"))
    annual, intensity = _rain_images(ref_year)
    for name, img in (("rain_annual_mm", annual), ("rain_intensity_mm_h", intensity)):
        if not rainfall:
            errors[name] = "not requested"
            continue
        try:
            bands.update(compute_pixels(img, transform, shape, crs, name))
        except Exception as e:   # noqa: BLE001 -- recorded, component excluded
            errors[name] = f"{type(e).__name__}: {e}"
    layers = {k: surface(bands[k], source=SOURCES[k][0], method=SOURCES[k][1],
                         validation_status="experimental")
              for k in LAYERS if k in bands}
    return {"status": "available", "transform": transform, "shape": tuple(shape), "crs": crs,
            "ref_year": ref_year, "layers": layers, "errors": errors}
