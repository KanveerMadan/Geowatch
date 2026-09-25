"""
Item 21 Phase A, part 1 — input assembly per AOI.

One float32 GeoTIFF on the native Sentinel-2 grid (surface_fractions.grid),
holding every raster input the later parts read:

  s2_*          the existing 6-band median composite (sentinel2.py), float32
                reflectance -- never the 8-bit PNG preview (C41)
  s2_observed   1 where the composite has any valid observation, else 0
  tv_*          item 18 temporal variance: {band}_stddev and {band}_cv
  ob_cov        Open Buildings v3 (confidence >= 0.7) covered fraction
  ms_cov        Microsoft building footprints covered fraction
  dem_elevation Copernicus GLO-30 elevation, metres
  dem_slope_deg slope, degrees, computed at 30 m in the grid CRS

plus the OSM layers (osm_layers.py), rasterised locally onto the same grid.

Absent is never zero (C33). A source that cannot be obtained keeps its bands
in the stack as NaN and carries status "unavailable" with the reason.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from ingestion.overpass import run_query
from ingestion.sentinel2 import S2_BAND_NAMES
from surface_fractions.config import REPO_ROOT, aoi_config, load_config
from surface_fractions.grid import Grid
from surface_fractions.osm_layers import assemble_osm_layers

NODATA = -9999.0

S2_STACK_BANDS = [f"s2_{b}" for b in S2_BAND_NAMES] + ["s2_observed"]
TV_SOURCE_BANDS = ([f"{b}_stddev" for b in list(S2_BAND_NAMES) + ["NDVI", "NDBI"]]
                   + [f"{b}_cv" for b in S2_BAND_NAMES])
TV_STACK_BANDS = [f"tv_{b}" for b in TV_SOURCE_BANDS]
FOOTPRINT_BANDS = ["ob_cov", "ms_cov"]
DEM_BANDS = ["dem_elevation", "dem_slope_deg"]
STACK_BANDS = S2_STACK_BANDS + TV_STACK_BANDS + FOOTPRINT_BANDS + DEM_BANDS

DEFAULT_OUT_DIR = os.path.join(REPO_ROOT, "data", "surface_fractions")


class GridMismatchError(RuntimeError):
    """The exported file is not on the grid that was requested."""


@dataclass
class InputBundle:
    aoi: dict
    grid: Grid
    bands: dict                      # name -> float32 array, NaN = no data
    osm: dict                        # layer name -> osm_layers.rasterise_layer()
    status: dict                     # source -> "available" | "unavailable" | ...
    provenance: dict
    stack_path: str | None = None
    errors: dict = field(default_factory=dict)


# ── Earth Engine side ───────────────────────────────────────────────────────

def microsoft_asset_for(aoi_geom, cfg: dict) -> tuple:
    """(asset id or None, country name, error or None). The sat-io catalogue
    has one table per country, named with underscores for spaces."""
    import ee
    ms = cfg["footprints"]["microsoft"]
    feat = (ee.FeatureCollection(ms["country_lookup"])
            .filterBounds(aoi_geom.centroid(1)).first())
    country = ee.Feature(feat).get(ms["country_field"]).getInfo()
    if not country:
        return None, None, "no LSIB country at AOI centroid"
    asset = f"{ms['folder']}/{country.replace(' ', '_')}"
    try:
        ee.data.getAsset(asset)
    except Exception as e:  # noqa: BLE001 -- EE raises a generic exception
        return None, country, f"no Microsoft table {asset}: {e}"
    return asset, country, None


def _nodata_bands(names):
    import ee
    return ee.Image.constant([NODATA] * len(names)).rename(names).toFloat()


def build_ee_stack(aoi_cfg: dict, cfg: dict, grid: Grid, region) -> tuple:
    """-> (ee.Image with STACK_BANDS, status, provenance, errors)."""
    import ee
    from ingestion.sentinel2 import get_sentinel2_median_composite
    from ingestion.temporal_variance import compute_temporal_variance
    from surface_fractions.grid import coverage_fraction, ee_projection

    status, prov, errors = {}, {}, {}
    proj = ee_projection(grid)
    win = aoi_cfg["composite_window"]

    # Sentinel-2 composite -- the existing recipe, unchanged.
    s2 = get_sentinel2_median_composite(
        region, win["start"], win["end"], cfg["sentinel2"]["cloud_cover_threshold"])
    composite = s2["image"].select(list(S2_BAND_NAMES))
    observed = composite.select(S2_BAND_NAMES[0]).mask().gt(0).rename("s2_observed")
    s2_img = composite.rename([f"s2_{b}" for b in S2_BAND_NAMES]).addBands(observed)
    status["sentinel2"] = "available"
    prov["sentinel2"] = {**s2["provenance"], "observation_quality": s2["observation_quality"],
                         "bands": list(S2_BAND_NAMES), "dtype": "float32",
                         "reflectance_scale": "surface reflectance, 0-1"}

    # Item 18 temporal variance.
    year = int(win["end"][:4])
    tv = compute_temporal_variance(region, year, cfg["sentinel2"]["cloud_cover_threshold"])
    prov["temporal_variance"] = {k: tv.get(k) for k in
                                 ("composite_count", "date_range", "reduction_scale_m", "error")}
    prov["temporal_variance"]["item_18_status"] = "open (not accepted)"
    if tv["status"] == "available":
        tv_img = tv["variance_image"].select(TV_SOURCE_BANDS, TV_STACK_BANDS)
        status["temporal_variance"] = "available"
    else:
        tv_img = _nodata_bands(TV_STACK_BANDS)
        status["temporal_variance"] = "unavailable"
        errors["temporal_variance"] = tv.get("error")

    # Footprints. Open Buildings is `built`; Microsoft is only the second
    # source for the disagreement signal (part 4).
    ob = cfg["footprints"]["open_buildings"]
    ob_fc = (ee.FeatureCollection(ob["asset"]).filterBounds(region)
             .filter(ee.Filter.gte("confidence", ob["min_confidence"])))
    sub = cfg["footprints"]["subcell_m"]
    ob_img = coverage_fraction(ob_fc, proj, sub).rename("ob_cov")
    status["open_buildings"] = "available"
    prov["open_buildings"] = {"asset": ob["asset"], "min_confidence": ob["min_confidence"],
                              "subcell_m": sub}

    ms_asset, country, ms_err = microsoft_asset_for(region, cfg)
    prov["microsoft_buildings"] = {"asset": ms_asset, "country": country, "subcell_m": sub}
    if ms_asset:
        ms_fc = ee.FeatureCollection(ms_asset).filterBounds(region)
        ms_img = coverage_fraction(ms_fc, proj, sub).rename("ms_cov")
        status["microsoft_buildings"] = "available"
    else:
        ms_img = _nodata_bands(["ms_cov"])
        status["microsoft_buildings"] = "unavailable"
        errors["microsoft_buildings"] = ms_err

    # Copernicus DEM. Slope needs a defined projection (see
    # ingestion/hydrology.get_slope_stats); here it is the grid's own CRS at
    # the DEM's native 30 m, so the gradient is in metres, not degrees.
    dem_cfg = cfg["dem"]
    dem = (ee.ImageCollection(dem_cfg["collection"]).filterBounds(region)
           .select(dem_cfg["band"]).mosaic()
           .reproject(crs=grid.crs, scale=30))
    slope = ee.Terrain.slope(dem)
    dem_img = dem.rename("dem_elevation").addBands(slope.rename("dem_slope_deg"))
    status["dem"] = "available"
    prov["dem"] = {"collection": dem_cfg["collection"], "native_resolution_m": 30,
                   "slope_computed_at_m": 30, "slope_crs": grid.crs}

    stack = (ee.Image.cat([s2_img, tv_img, ob_img, ms_img, dem_img])
             .select(STACK_BANDS).toFloat().unmask(NODATA))
    return stack, status, prov, errors


# ── Local side ──────────────────────────────────────────────────────────────

def read_stack(path: str, grid: Grid, names: list = STACK_BANDS) -> dict:
    """Read the exported stack, refusing any file that is not exactly on
    `grid` or whose bands are not `names` in order (C4). NODATA -> NaN."""
    import rasterio
    from rasterio.crs import CRS
    from ingestion.tiler import assert_band_order

    with rasterio.open(path) as src:
        assert_band_order(src, path, strict=True, expected=names)
        if CRS.from_user_input(src.crs) != CRS.from_user_input(grid.crs):
            raise GridMismatchError(f"{path}: CRS {src.crs} != grid {grid.crs}")
        if (src.width, src.height) != (grid.width, grid.height):
            raise GridMismatchError(
                f"{path}: shape {src.width}x{src.height} != grid "
                f"{grid.width}x{grid.height}")
        # Absolute tolerance only: np.allclose's default rtol=1e-5 would pass
        # a 5 m (half-pixel) shift at UTM eastings of ~600 000 m.
        if not np.allclose(tuple(src.transform)[:6], grid.transform, rtol=0, atol=1e-6):
            raise GridMismatchError(
                f"{path}: transform {tuple(src.transform)[:6]} != grid {grid.transform}")
        data = src.read().astype(np.float32)
    data[data == NODATA] = np.nan
    return {name: data[i] for i, name in enumerate(names)}


def assemble_inputs(aoi_name: str, cfg: dict | None = None,
                    out_dir: str = DEFAULT_OUT_DIR, osm_query_fn=run_query) -> InputBundle:
    import ee
    from ingestion.gee_client import initialize_gee
    from ingestion.tiler import export_image_local
    from surface_fractions.grid import grid_region, native_grid

    cfg = cfg or load_config()
    aoi = aoi_config(cfg, aoi_name)
    b = aoi["bbox"]

    initialize_gee()
    aoi_geom = ee.Geometry.Rectangle([b["west"], b["south"], b["east"], b["north"]])
    grid = native_grid(aoi_geom, cfg["sentinel2"]["collection"])
    region = grid_region(grid)

    stack, status, prov, errors = build_ee_stack(aoi, cfg, grid, region)

    run_dir = os.path.join(out_dir, f"{aoi_name}_{datetime.now():%Y%m%d_%H%M%S}")
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, "inputs.tif")
    export_image_local(stack, region, path, crs=grid.crs,
                       crs_transform=list(grid.transform), band_names=STACK_BANDS)
    bands = read_stack(path, grid)

    osm = assemble_osm_layers(cfg, b, grid, query_fn=osm_query_fn)
    for name, layer in osm.items():
        status[f"osm:{name}"] = layer["status"]
        if layer.get("error"):
            errors[f"osm:{name}"] = layer["error"]
    prov["osm"] = {"client": "ingestion/overpass.py",
                   "layers": {n: {"filters": cfg["osm_layers"][n].get("filters", []),
                                  "geometry": l["geometry"],
                                  "n_features": l["n_features"]} for n, l in osm.items()}}
    prov["grid"] = grid.to_dict()

    return InputBundle(aoi=aoi, grid=grid, bands=bands, osm=osm, status=status,
                       provenance=prov, stack_path=path, errors=errors)
