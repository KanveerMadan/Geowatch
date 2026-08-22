"""
Phase 5: true fluvial terrain context via MERIT Hydro (precomputed HAND)
and FABDEM (bare-earth elevation). These are TWO SEPARATE data sources
computed with different methods -- see the explicit warning below.
Never report FABDEM elevation and MERIT Hydro HAND as if one were
derived from the other. They are not. MERIT Hydro's `hnd` band was
computed from MERIT's own terrain/drainage-routing structure, not from
FABDEM.
"""

import ee
from ingestion.gee_client import initialize_gee
from configs.fluvial_constants import (
    FLUVIAL_BUFFER_KM, MERIT_HYDRO_SCALE_M,
    RIVER_CONNECTIVITY_UPSTREAM_AREA_KM2_THRESHOLD,
)


def _buffer_aoi(west, south, east, north, buffer_km):
    """Buffer a lon/lat rectangle by buffer_km using a geodesic buffer
    on the AOI's centroid-based EE geometry. Approximate -- EE's
    .buffer() on a geographic geometry operates in meters correctly
    regardless of CRS, so this is accurate, just not pixel-exact at
    extreme latitudes."""
    aoi = ee.Geometry.Rectangle([west, south, east, north])
    return aoi.buffer(buffer_km * 1000.0)


def get_merit_hand_context(west: float, south: float, east: float, north: float,
                            buffer_km: float = FLUVIAL_BUFFER_KM) -> dict:
    """
    Query MERIT Hydro's precomputed `hnd` (Height Above Nearest Drainage)
    and `upa` (upstream drainage area) bands over a buffered catchment
    context around the AOI.

    THIS IS REAL, HYDROLOGICALLY-ROUTED HAND -- unlike
    relative_elevation_proxy (AOI-relative p10/p90 elevation, NOT real
    HAND). MERIT Hydro's hnd was computed via actual flow-direction and
    drainage-network routing by the dataset's authors, not derived here.

    Returns AOI-WIDE STATISTICS (mean/min/max), not a per-pixel spatial
    raster -- same limitation-transparency pattern as
    relative_elevation_proxy and pluvial susceptibility's scalar
    components. A real per-pixel HAND raster aligned to the tile grid is
    a reasonable future improvement, not done here to keep this phase
    contained.

    Returns:
        dict with status, hnd stats (meters), upstream_area stats (km^2),
        river_connectivity (bool), source, resolution_m, buffer_km.
    """
    try:
        initialize_gee()

        aoi = ee.Geometry.Rectangle([west, south, east, north])
        buffered = _buffer_aoi(west, south, east, north, buffer_km)

        merit = ee.Image("MERIT/Hydro/v1_0_1")
        hnd = merit.select("hnd")
        upa = merit.select("upa")  # upstream drainage area, km^2 (MERIT Hydro units)

        # HAND stats computed over the AOI itself (the thing we're
        # actually assessing), while upstream area is checked over the
        # BUFFERED region (connectivity can come from just outside the box).
        hnd_stats = hnd.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True),
            geometry=aoi, scale=MERIT_HYDRO_SCALE_M, maxPixels=1e9,
        ).getInfo()

        upa_stats = upa.reduceRegion(
            reducer=ee.Reducer.max(),
            geometry=buffered, scale=MERIT_HYDRO_SCALE_M, maxPixels=1e9,
        ).getInfo()

        mean_hnd = hnd_stats.get("hnd_mean")
        min_hnd = hnd_stats.get("hnd_min")
        max_hnd = hnd_stats.get("hnd_max")
        max_upstream_area_km2 = upa_stats.get("upa")

        if mean_hnd is None:
            raise ValueError("MERIT Hydro hnd reduction returned no value for this AOI.")

        river_connected = (
            max_upstream_area_km2 is not None
            and max_upstream_area_km2 >= RIVER_CONNECTIVITY_UPSTREAM_AREA_KM2_THRESHOLD
        )

        print(f"MERIT Hydro HAND: mean={mean_hnd:.2f}m, min={min_hnd:.2f}m, "
              f"max={max_hnd:.2f}m. Max upstream area in {buffer_km}km buffer: "
              f"{max_upstream_area_km2} km^2 (river_connected={river_connected})")

        return {
            "status": "available",
            "mean_hnd_m": round(float(mean_hnd), 3),
            "min_hnd_m": round(float(min_hnd), 3) if min_hnd is not None else None,
            "max_hnd_m": round(float(max_hnd), 3) if max_hnd is not None else None,
            "max_upstream_area_km2": (
                round(float(max_upstream_area_km2), 3)
                if max_upstream_area_km2 is not None else None
            ),
            "river_connectivity": river_connected,
            "source": "MERIT/Hydro/v1_0_1",
            "hydrologically_conditioned": True,
            "true_hand": True,
            "resolution_m": MERIT_HYDRO_SCALE_M,
            "buffer_km": buffer_km,
            "spatial": False,
            "error": None,
        }

    except Exception as e:
        print(f"MERIT Hydro HAND context computation failed: {e}")
        return {
            "status": "unavailable",
            "mean_hnd_m": None,
            "min_hnd_m": None,
            "max_hnd_m": None,
            "max_upstream_area_km2": None,
            "river_connectivity": None,
            "source": "MERIT/Hydro/v1_0_1",
            "hydrologically_conditioned": True,
            "true_hand": True,
            "resolution_m": MERIT_HYDRO_SCALE_M,
            "buffer_km": buffer_km,
            "spatial": False,
            "error": str(e),
        }


def get_fabdem_elevation_stats(west: float, south: float, east: float, north: float) -> dict:
    """
    Bare-earth elevation statistics from FABDEM (building/canopy bias
    reduced), via the GEE community-catalog hosted asset. SEPARATE from
    MERIT Hydro's HAND (different source, different method) and
    SEPARATE from relative_elevation_proxy (which still uses Copernicus
    DSM -- see Phase 0). Do not merge these into one number.

    Source: gee-community-catalog.org/projects/fabdem/
    License: CC BY-NC-SA 4.0 (non-commercial, share-alike). Flag if this
    project ever moves toward commercial use.
    """
    try:
        initialize_gee()
        aoi = ee.Geometry.Rectangle([west, south, east, north])

        fabdem = (
            ee.ImageCollection("projects/sat-io/open-datasets/FABDEM")
            .filterBounds(aoi)
            .mosaic()
            .clip(aoi)
        )

        stats = fabdem.reduceRegion(
            reducer=ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True),
            geometry=aoi, scale=30, maxPixels=1e9,
        ).getInfo()

        mean_elev = stats.get("b1_mean")
        min_elev = stats.get("b1_min")
        max_elev = stats.get("b1_max")

        if mean_elev is None:
            raise ValueError("FABDEM reduction returned no value for this AOI.")

        print(f"FABDEM bare-earth elevation: mean={mean_elev:.2f}m, "
              f"min={min_elev}m, max={max_elev}m")

        return {
            "status": "available",
            "mean_elevation_m": round(float(mean_elev), 3),
            "min_elevation_m": float(min_elev) if min_elev is not None else None,
            "max_elevation_m": float(max_elev) if max_elev is not None else None,
            "source": "projects/sat-io/open-datasets/FABDEM",
            "bare_earth": True,
            "building_bias_reduced": True,
            "canopy_bias_reduced": True,
            "resolution_m": 30,
            "license": "CC BY-NC-SA 4.0 (non-commercial, share-alike)",
            "error": None,
        }

    except Exception as e:
        print(f"FABDEM elevation computation failed: {e}")
        return {
            "status": "unavailable",
            "mean_elevation_m": None,
            "min_elevation_m": None,
            "max_elevation_m": None,
            "source": "projects/sat-io/open-datasets/FABDEM",
            "bare_earth": True,
            "building_bias_reduced": True,
            "canopy_bias_reduced": True,
            "resolution_m": 30,
            "license": "CC BY-NC-SA 4.0 (non-commercial, share-alike)",
            "error": str(e),
        }

def get_slope_stats(west: float, south: float, east: float, north: float) -> dict:
    """
    Phase 7: mean terrain slope over the AOI, via Copernicus DEM GLO-30
    (the same asset already verified working in
    compute_relative_elevation_proxy() -- see ingestion/osm_dem.py).

    NOTE: compute_relative_elevation_proxy() already computes a slope
    band internally via ee.Terrain.products(dem).select("slope") but
    NEVER RETURNS IT -- see that function's own docstring, which flags
    this exact "computed and discarded" pattern for flow_dir too. This
    is a small, separate function rather than modifying
    relative_elevation_proxy's return shape, to avoid touching a
    function every other phase already depends on and has tested against.

    Returns AOI-WIDE MEAN slope in degrees, not a per-pixel raster --
    same limitation-transparency pattern as every other terrain
    statistic in this project.
    """
    try:
        initialize_gee()
        aoi = ee.Geometry.Rectangle([west, south, east, north])

        dem = (
            ee.ImageCollection("COPERNICUS/DEM/GLO30_2024_1")
            .filterBounds(aoi)
            .mosaic()
            .select("DEM")
            .clip(aoi)
        )
        # ee.Terrain.slope() computes a pixel-to-pixel gradient BEFORE any
        # reduceRegion happens, and that gradient step relies on the
        # image's own native/default projection to know real-world
        # distance between pixels. A .mosaic() output doesn't reliably
        # carry a well-defined projection for this -- unlike plain value
        # reduction (used by get_fabdem_elevation_stats/get_merit_hand_context
        # above, which pass an explicit scale to reduceRegion and don't
        # hit this issue). Reproject explicitly before the slope call so
        # the gradient computation has a defined projection/scale to work
        # with -- confirmed as the likely cause of "Slope reduction
        # returned no value" against the real error text, not assumed
        # blind.
        dem = dem.reproject(crs="EPSG:4326", scale=30)
        slope = ee.Terrain.slope(dem)

        stats = slope.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=aoi, scale=30, maxPixels=1e9,
        ).getInfo()

        mean_slope_deg = stats.get("slope")
        if mean_slope_deg is None:
            raise ValueError("Slope reduction returned no value for this AOI.")

        print(f"Mean terrain slope: {mean_slope_deg:.2f} degrees")

        return {
            "status": "available",
            "mean_slope_deg": round(float(mean_slope_deg), 3),
            "source": "COPERNICUS/DEM/GLO30_2024_1",
            "dem_type": "DSM",
            "resolution_m": 30,
            "spatial": False,
            "error": None,
        }

    except Exception as e:
        print(f"Slope computation failed: {e}")
        return {
            "status": "unavailable",
            "mean_slope_deg": None,
            "source": "COPERNICUS/DEM/GLO30_2024_1",
            "dem_type": "DSM",
            "resolution_m": 30,
            "spatial": False,
            "error": str(e),
        }