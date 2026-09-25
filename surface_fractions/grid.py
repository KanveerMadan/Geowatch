"""
The native Sentinel-2 10 m grid, and coverage fractions on it.

Item 21 Phase A (05_BUILD_MANUAL.md, "Phase A — build rulings"): fractions and
hand-label fractions share the NATIVE Sentinel-2 UTM grid. The pre-existing
float32 export snaps to an EPSG:4326 lattice (tiler._compute_export_grid),
i.e. every existing raw.tif is a resample of the real grid. A label fraction
computed on the real grid and a prediction on the resampled one would be
scored against each other one sub-pixel shift apart.

Two halves:
  - Earth Engine: find the grid for an AOI (`native_grid`), paint polygon
    coverage onto it (`coverage_fraction`). `s2_grid_for` and
    `pure_pixel_images` moved here from diagnose_pure_pixels.py unchanged;
    that script re-exports them so the diagnostic scripts keep working.
  - Local: the same coverage computation for polygons already on disk
    (`polygon_coverage`) -- OSM layers here, hand-label polygons in part 7.
    One implementation, so a label fraction and an OSM fraction are computed
    identically.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"

# Sub-cell size for the coverage-fraction test. 1m -> 100 sub-cells per 10m
# pixel. Smaller is more exact but costs quadratically; 1m is enough to make
# the over-count in note (a) small.
SUBPIXEL_M = 1

# A 10m pixel counts as pure at this covered fraction. Not exactly 1.0 to
# absorb floating-point noise in the mean reducer.
PURE_FRACTION_MIN = 0.999

S2_RESOLUTION_M = 10


@dataclass(frozen=True)
class Grid:
    """A north-up raster grid. `transform` is in Earth Engine crsTransform
    order, which is also rasterio Affine order: (xScale, xShear, xTranslate,
    yShear, yScale, yTranslate)."""
    crs: str
    transform: tuple
    width: int
    height: int

    @property
    def res(self) -> float:
        return self.transform[0]

    @property
    def bounds(self) -> tuple:
        """(minx, miny, maxx, maxy) in `crs`."""
        x0, y1 = self.transform[2], self.transform[5]
        return (x0, y1 - self.height * self.res,
                x0 + self.width * self.res, y1)

    def affine(self):
        from rasterio.transform import Affine
        return Affine(*self.transform)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["transform"] = list(self.transform)
        return d


def snap_bounds(minx: float, miny: float, maxx: float, maxy: float,
                res: float, origin_x: float, origin_y: float) -> tuple:
    """Expand a bounding box outward to the lattice {origin + k*res}.

    Returns (x0, y0, x1, y1) with every edge on the lattice and the box
    containing the input. Pure arithmetic, so it is unit-tested directly.
    """
    x0 = origin_x + math.floor(round((minx - origin_x) / res, 9)) * res
    y0 = origin_y + math.floor(round((miny - origin_y) / res, 9)) * res
    x1 = origin_x + math.ceil(round((maxx - origin_x) / res, 9)) * res
    y1 = origin_y + math.ceil(round((maxy - origin_y) / res, 9)) * res
    return x0, y0, x1, y1


def grid_from_bounds(crs: str, bounds: tuple, res: float,
                     origin_x: float, origin_y: float) -> Grid:
    x0, y0, x1, y1 = snap_bounds(*bounds, res, origin_x, origin_y)
    width = int(round((x1 - x0) / res))
    height = int(round((y1 - y0) / res))
    return Grid(crs=crs, transform=(res, 0.0, x0, 0.0, -res, y1),
                width=width, height=height)


# ── Earth Engine ────────────────────────────────────────────────────────────

def s2_grid_for(aoi):
    """The real Sentinel-2 10m grid over this AOI.

    Taken from an actual S2_SR_HARMONIZED scene's B2 band, so the CRS and
    crsTransform are the ones the real composite is built on -- not a 10m
    grid synthesized from the AOI bounds.
    """
    import ee
    scene = (ee.ImageCollection(S2_COLLECTION)
             .filterBounds(aoi)
             .first())
    proj = ee.Image(scene).select("B2").projection()
    info = proj.getInfo()
    return proj, info


def native_grid(aoi, collection: str = S2_COLLECTION) -> Grid:
    """The native Sentinel-2 grid covering `aoi`, snapped outward.

    Unlike `s2_grid_for` (arbitrary first scene), the scene is chosen
    deterministically: the earliest one containing the AOI centroid. That
    fixes the UTM zone when an AOI straddles a zone boundary, and makes the
    grid reproducible across runs.
    """
    import ee
    scene = (ee.ImageCollection(collection)
             .filterBounds(aoi.centroid(1))
             .sort("system:time_start")
             .first())
    info = ee.Image(scene).select("B2").projection().getInfo()
    crs, t = info["crs"], info["transform"]
    if abs(t[0]) != S2_RESOLUTION_M or t[1] != 0 or t[3] != 0:
        raise ValueError(f"Unexpected Sentinel-2 B2 projection: {info}")
    coords = aoi.bounds(1, crs).getInfo()["coordinates"][0]
    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    return grid_from_bounds(crs, (min(xs), min(ys), max(xs), max(ys)),
                            S2_RESOLUTION_M, t[2], t[5])


def grid_region(grid: Grid):
    """The grid's extent as an ee.Geometry in the grid CRS, inset a quarter
    pixel so Earth Engine's own edge snapping cannot add a row or column
    (same device as tiler._export_image_local_chunked)."""
    import ee
    q = grid.res / 4
    minx, miny, maxx, maxy = grid.bounds
    return ee.Geometry.Rectangle([minx + q, miny + q, maxx - q, maxy - q],
                                 proj=grid.crs, geodesic=False)


def ee_projection(grid: Grid):
    import ee
    return ee.Projection(grid.crs, list(grid.transform))


def coverage_fraction(fc, proj, subpixel_m: float = SUBPIXEL_M):
    """Per-pixel covered fraction in [0, 1] of polygon FeatureCollection `fc`
    on `proj`'s grid, by painting at a sub-pixel scale derived from `proj`
    itself (`.atScale`) so sub-cells tile the 10 m cells exactly, then
    averaging back down."""
    import ee
    fine_proj = proj.atScale(subpixel_m)
    mask = ee.Image(0).byte().paint(fc, 1).reproject(fine_proj)
    subcells = int((S2_RESOLUTION_M / subpixel_m) ** 2)
    return (mask
            .reduceResolution(ee.Reducer.mean(), maxPixels=subcells + 16)
            .reproject(proj))


def pure_pixel_images(fc, proj):
    """(overlap, pure) masks on `proj`'s grid for an arbitrary polygon
    FeatureCollection.

    Coverage fraction is measured by painting the polygons at a sub-pixel
    scale derived from `proj` itself (`.atScale`), so sub-cells tile the 10m
    cells exactly, then averaging back down onto the 10m grid.

    Kept source-agnostic: `built` passes building footprints, `paved` passes
    unroofed OSM polygons, and both are measured identically.
    """
    covered_fraction = coverage_fraction(fc, proj, SUBPIXEL_M)
    subcells = int((10 / SUBPIXEL_M) ** 2)
    return (covered_fraction.gt(0).rename("overlap"),
            covered_fraction.gte(PURE_FRACTION_MIN).rename("pure"),
            subcells)


# ── Local ───────────────────────────────────────────────────────────────────

def to_grid_crs(geoms, grid: Grid, src_crs: str = "EPSG:4326") -> list:
    """Reproject shapely geometries into the grid CRS."""
    from pyproj import Transformer
    from shapely.ops import transform
    tr = Transformer.from_crs(src_crs, grid.crs, always_xy=True)
    return [transform(tr.transform, g) for g in geoms]


def polygon_coverage(geoms, grid: Grid, subcell_m: float = SUBPIXEL_M) -> np.ndarray:
    """Per-pixel covered fraction in [0, 1] of (multi)polygons already in the
    grid CRS. Rasterises at `subcell_m` on a lattice that tiles each 10 m cell
    exactly, then block-averages -- the local twin of `coverage_fraction`.

    Overlapping polygons are counted once (a union), so the result never
    exceeds 1.
    """
    from rasterio.features import rasterize
    from rasterio.transform import Affine

    k = grid.res / subcell_m
    if abs(k - round(k)) > 1e-9:
        raise ValueError(f"subcell {subcell_m} m does not tile {grid.res} m")
    k = int(round(k))
    out = np.zeros((grid.height, grid.width), dtype=np.float64)
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return out
    t = grid.transform
    fine = Affine(t[0] / k, 0.0, t[2], 0.0, t[4] / k, t[5])
    burned = rasterize(((g, 1) for g in geoms),
                       out_shape=(grid.height * k, grid.width * k),
                       transform=fine, fill=0, dtype="uint8")
    return burned.reshape(grid.height, k, grid.width, k).mean(axis=(1, 3))


def line_touch(geoms, grid: Grid) -> np.ndarray:
    """Per-pixel 0/1: does any line (already in the grid CRS) touch the
    pixel. Used where OSM carries no width, so no area can be claimed."""
    from rasterio.features import rasterize
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return np.zeros((grid.height, grid.width), dtype=np.uint8)
    return rasterize(((g, 1) for g in geoms),
                     out_shape=(grid.height, grid.width),
                     transform=grid.affine(), fill=0, all_touched=True,
                     dtype="uint8")
