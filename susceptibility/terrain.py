"""
DEM hydrology for pluvial susceptibility (build item 26, task 4).

Four per-cell terrain inputs on the hydrology grid, each a declared surface
(susceptibility/inputs.py), scored so 1 = more pluvial-prone:

    low_slope               1 - slope / PLUVIAL_SLOPE_NORMALIZATION_MAX_DEG
    flow_accumulation       log(1 + upstream cells) / log(cells in grid), D8
    topographic_hollow      -TPI / PLUVIAL_TPI_NORMALIZATION_M; TPI = elevation
                            minus the mean within PLUVIAL_TPI_RADIUS_CELLS
    drainage_disconnection  1 where the D8 path ends in an interior pit
                            instead of leaving the grid edge, else 0

D8 runs on the UNFILLED DEM on purpose: a closed depression is where rain
ponds, so it is signal here, not noise to fill away. The grid edge stands in
for an outlet -- it is where water leaves the AOI, not a real drain. Flat
cells (no lower neighbour) count as pits.

All constants are provisional (configs/pluvial_constants.py). All four are
`experimental`: real methods, not validated.
"""
from __future__ import annotations

import numpy as np

from configs.pluvial_constants import (
    PLUVIAL_SLOPE_NORMALIZATION_MAX_DEG, PLUVIAL_TPI_NORMALIZATION_M, PLUVIAL_TPI_RADIUS_CELLS,
)
from susceptibility.inputs import surface

FABDEM_ASSET = "projects/sat-io/open-datasets/FABDEM"
TERRAIN_COMPONENTS = ("low_slope", "flow_accumulation", "topographic_hollow",
                      "drainage_disconnection")
_OFFSETS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def slope_deg(dem: np.ndarray, pixel_m: float) -> np.ndarray:
    dy, dx = np.gradient(dem.astype(np.float64), pixel_m)
    return np.degrees(np.arctan(np.hypot(dx, dy)))


def d8_receivers(dem: np.ndarray, pixel_m: float) -> np.ndarray:
    """Flat index of each cell's steepest-descent neighbour; -1 for a pit
    (no strictly lower neighbour) or a no-data cell."""
    H, W = dem.shape
    pad = np.pad(dem.astype(np.float64), 1, constant_values=np.nan)
    best = np.zeros((H, W))
    recv = np.full((H, W), -1, dtype=np.int64)
    rows, cols = np.mgrid[0:H, 0:W]
    for dr, dc in _OFFSETS:
        nb = pad[1 + dr:1 + dr + H, 1 + dc:1 + dc + W]
        with np.errstate(invalid="ignore"):
            drop = (dem - nb) / (pixel_m * np.hypot(dr, dc))
            better = drop > best          # NaN compares False: no-data never receives
        best = np.where(better, drop, best)
        recv = np.where(better, (rows + dr) * W + (cols + dc), recv)
    return recv.ravel()


def flow_accumulation(dem: np.ndarray, recv: np.ndarray) -> np.ndarray:
    """Upstream cells draining through each cell, itself excluded."""
    acc = np.zeros(dem.size)
    order = np.argsort(np.nan_to_num(dem.ravel(), nan=-np.inf))[::-1]   # high to low
    for i in order:
        if recv[i] >= 0:
            acc[recv[i]] += acc[i] + 1
    return acc.reshape(dem.shape)


def drains_to_edge(dem: np.ndarray, recv: np.ndarray) -> np.ndarray:
    """True where the D8 path reaches a grid-edge cell."""
    H, W = dem.shape
    edge = np.zeros((H, W), dtype=bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    edge = edge.ravel()
    out = edge.copy()
    for i in np.argsort(np.nan_to_num(dem.ravel(), nan=np.inf)):   # low to high
        if not out[i] and recv[i] >= 0:
            out[i] = out[recv[i]]      # receiver is strictly lower, already resolved
    return out.reshape(H, W)


def tpi(dem: np.ndarray, radius: int) -> np.ndarray:
    from scipy.ndimage import uniform_filter
    ok = np.isfinite(dem)
    size = 2 * radius + 1
    s = uniform_filter(np.where(ok, dem, 0.0).astype(np.float64), size, mode="constant")
    n = uniform_filter(ok.astype(np.float64), size, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        return dem - s / n


def terrain_surfaces(dem: np.ndarray, pixel_m: float, source: str = FABDEM_ASSET) -> dict:
    """The four scored terrain inputs, NaN where the DEM has no data."""
    dem = np.asarray(dem, dtype=np.float64)
    nodata = ~np.isfinite(dem)
    recv = d8_receivers(dem, pixel_m)
    acc = flow_accumulation(dem, recv)
    scores = {
        "low_slope": 1.0 - slope_deg(dem, pixel_m) / PLUVIAL_SLOPE_NORMALIZATION_MAX_DEG,
        "flow_accumulation": np.log1p(acc) / np.log(max(dem.size, 2)),
        "topographic_hollow": -tpi(dem, PLUVIAL_TPI_RADIUS_CELLS) / PLUVIAL_TPI_NORMALIZATION_M,
        "drainage_disconnection": (~drains_to_edge(dem, recv)).astype(np.float64),
    }
    methods = {
        "low_slope": f"1 - slope/{PLUVIAL_SLOPE_NORMALIZATION_MAX_DEG}deg",
        "flow_accumulation": "D8 on the unfilled DEM, log-scaled upstream cell count",
        "topographic_hollow": f"-TPI(r={PLUVIAL_TPI_RADIUS_CELLS} cells)/{PLUVIAL_TPI_NORMALIZATION_M}m",
        "drainage_disconnection": "D8 path ends in an interior pit, not the grid edge",
    }
    return {k: surface(np.where(nodata, np.nan, np.clip(v, 0.0, 1.0)), source, methods[k],
                       "experimental")
            for k, v in scores.items()}


def fetch_dem(layer, transform, shape) -> np.ndarray:
    """FABDEM bare-earth elevation on the hydrology grid, bilinear, from Earth
    Engine. NaN where FABDEM has no data. Raises on Earth Engine errors."""
    import ee
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    H, W = shape
    col = ee.ImageCollection(FABDEM_ASSET).filterBounds(ee.Geometry.Rectangle(list(layer.bbox)))
    # mosaic() drops the native 1" projection; without it bilinear resampling
    # interpolates from a 1-degree default grid and returns a constant.
    img = (col.mosaic().setDefaultProjection(col.first().projection()).select(0)
           .resample("bilinear").rename("dem").unmask(-9999).toFloat())
    grid = {"dimensions": {"width": W, "height": H},
            "affineTransform": {"scaleX": transform.a, "shearX": 0, "translateX": transform.c,
                                "shearY": 0, "scaleY": transform.e, "translateY": transform.f},
            "crsCode": layer.crs.to_string()}
    arr = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY", "grid": grid})
    return np.where(arr["dem"] == -9999, np.nan, arr["dem"]).astype(np.float64)
