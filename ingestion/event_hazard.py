"""
Phase 9: event forcing data. THREE MECHANISMS, THREE VERY DIFFERENT
LEVELS OF REAL DATA AVAILABILITY -- read this before using any function
here.

    1. get_event_rainfall() -- REAL DATA. GPM IMERG, queried via GEE,
       same discipline as every other ingestion function in this project
       (explicit status, never fabricates on failure).

    2. get_discharge_proxy() -- NOT REAL RIVER DISCHARGE. GloFAS (the
       standard real discharge product) is NOT a Google Earth Engine
       asset -- it is accessed via ECMWF/Copernicus's separate CDS API,
       which this project has no client for. Rather than fabricate a
       GEE asset ID (which would likely fail exactly like the shoreline
       dataset needed two live-caught fixes), this function returns a
       RAINFALL-ACCUMULATION PROXY over the buffered upstream catchment
       instead -- explicitly labeled real_discharge_data: False. This is
       a genuinely weaker signal than real discharge and must never be
       presented as river discharge in any user-facing output.

    3. Coastal tide/surge has NO function here at all. No verified
       global tide/surge GEE asset exists. Phase 6 already deferred this
       pending its own dataset ADR -- Phase 9 does not fabricate one
       either. susceptibility/coastal_event_hazard.py returns
       not_calculated with this exact reason.
"""

import ee
from ingestion.gee_client import initialize_gee
from configs.event_hazard_constants import IMERG_ASSET, DISCHARGE_PROXY_BUFFER_KM


def get_event_rainfall(west: float, south: float, east: float, north: float,
                        event_start: str, event_end: str) -> dict:
    """
    Real accumulated rainfall (mm) over the AOI during a specific event
    window, via GPM IMERG -- distinct from Phase 4's CHIRPS climatology
    mean, which is a multi-year average, not an event total.
    """
    try:
        initialize_gee()
        aoi = ee.Geometry.Rectangle([west, south, east, north])

        imerg = (
            ee.ImageCollection(IMERG_ASSET)
            .filterBounds(aoi)
            .filterDate(event_start, event_end)
            .select("precipitation")
        )

        count = imerg.size().getInfo()
        if count == 0:
            raise ValueError("No IMERG images found for this AOI/event window.")

        # IMERG's 'precipitation' band is a RATE (mm/hr for the half-hourly
        # product). Summing half-hourly rate images and dividing by 2
        # (30min = 0.5hr) gives accumulated mm -- standard IMERG convention.
        total_image = imerg.sum().multiply(0.5)
        stats = total_image.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=aoi, scale=10000, maxPixels=1e9,
        ).getInfo()

        total_mm = stats.get("precipitation")
        if total_mm is None:
            raise ValueError("IMERG reduction returned no value.")

        print(f"Event rainfall (IMERG): {total_mm:.1f}mm accumulated "
              f"({event_start} to {event_end}, {count} half-hourly images)")

        return {
            "status": "available",
            "event_total_mm": round(float(total_mm), 1),
            "source": IMERG_ASSET,
            "source_image_count": count,
            "event_period": {"start": event_start, "end": event_end},
            "error": None,
        }

    except Exception as e:
        print(f"Event rainfall (IMERG) computation failed: {e}")
        return {
            "status": "unavailable",
            "event_total_mm": None,
            "source": IMERG_ASSET,
            "source_image_count": 0,
            "event_period": {"start": event_start, "end": event_end},
            "error": str(e),
        }


def get_discharge_proxy(west: float, south: float, east: float, north: float,
                         event_start: str, event_end: str,
                         buffer_km: float = DISCHARGE_PROXY_BUFFER_KM) -> dict:
    """
    NOT REAL RIVER DISCHARGE. See module docstring. Returns accumulated
    rainfall (mm) over a buffered catchment during the event window, as
    a weak stand-in for "how much water is being delivered upstream of
    this AOI" -- real discharge requires actual routed streamflow, which
    needs GloFAS or an equivalent hydrological model, not available via
    GEE.
    """
    try:
        initialize_gee()
        aoi = ee.Geometry.Rectangle([west, south, east, north])
        buffered = aoi.buffer(buffer_km * 1000.0)

        imerg = (
            ee.ImageCollection(IMERG_ASSET)
            .filterBounds(buffered)
            .filterDate(event_start, event_end)
            .select("precipitation")
        )

        count = imerg.size().getInfo()
        if count == 0:
            raise ValueError("No IMERG images found for this catchment/event window.")

        total_image = imerg.sum().multiply(0.5)
        stats = total_image.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=buffered, scale=10000, maxPixels=1e9,
        ).getInfo()

        total_mm = stats.get("precipitation")
        if total_mm is None:
            raise ValueError("IMERG catchment reduction returned no value.")

        print(f"Discharge proxy (rainfall-only, NOT real discharge): "
              f"{total_mm:.1f}mm over {buffer_km}km buffer "
              f"({event_start} to {event_end}, {count} images)")

        return {
            "status": "available",
            "real_discharge_data": False,
            "catchment_rainfall_mm": round(float(total_mm), 1),
            "buffer_km": buffer_km,
            "source": IMERG_ASSET,
            "source_image_count": count,
            "event_period": {"start": event_start, "end": event_end},
            "note": (
                "This is a rainfall-accumulation proxy, NOT real river "
                "discharge. GloFAS (the standard real discharge product) is "
                "not a GEE asset and requires a separate CDS API client, not "
                "yet integrated into this project. Do not present this as "
                "river discharge in any user-facing output."
            ),
            "error": None,
        }

    except Exception as e:
        print(f"Discharge proxy computation failed: {e}")
        return {
            "status": "unavailable",
            "real_discharge_data": False,
            "catchment_rainfall_mm": None,
            "buffer_km": buffer_km,
            "source": IMERG_ASSET,
            "source_image_count": 0,
            "event_period": {"start": event_start, "end": event_end},
            "note": "This would be a rainfall proxy, not real discharge, even if available.",
            "error": str(e),
        }