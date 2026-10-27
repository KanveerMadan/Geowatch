"""
Phase 4: rainfall climatology via CHIRPS, queried through Google Earth
Engine. Provides a STATIC climatology signal (long-term mean annual
rainfall) for the pluvial susceptibility baseline -- NOT event-specific
rainfall forcing (that's Phase 9, event hazard). CHIRPS chosen over
GPM IMERG for this use case: CHIRPS has a longer record (1981-present)
suited to multi-year means; GPM IMERG suits event-window rainfall later.
"""

import ee
from ingestion.errors import NoDataError, no_data
from datetime import date


def get_rainfall_climatology(aoi: ee.Geometry, lookback_years: int = 10) -> dict:
    try:
        end = date.today()
        start = date(end.year - lookback_years, end.month, end.day)

        chirps = (
            ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY")
            .filterBounds(aoi)
            .filterDate(start.isoformat(), end.isoformat())
        )

        count = chirps.size().getInfo()
        if count == 0:
            raise NoDataError("No CHIRPS images found for this AOI/period.")

        total_mm_image = chirps.sum()
        result = total_mm_image.reduceRegion(
            reducer=ee.Reducer.mean(), geometry=aoi, scale=5000, maxPixels=1e8,
        ).getInfo()

        total_mm = result.get("precipitation")
        if total_mm is None:
            raise NoDataError("CHIRPS reduction returned no value.")

        mean_annual_mm = float(total_mm) / lookback_years
        print(f"Rainfall climatology: {mean_annual_mm:.1f} mm/year "
              f"(mean of {lookback_years}yr CHIRPS record, {count} daily images)")

        return {
            "status": "available",
            "mean_annual_mm": round(mean_annual_mm, 1),
            "source": "UCSB-CHG/CHIRPS/DAILY",
            "lookback_years": lookback_years,
            "source_image_count": count,
            "error": None,
        }

    # Items 54/55: only a genuine data gap becomes "unavailable". A GEE,
    # network or programming error propagates (see ingestion/errors.py).
    except NoDataError as e:
        print(f"Rainfall climatology: no data for this AOI: {e}")
        return no_data(
            e,
            mean_annual_mm=None,
            source="UCSB-CHG/CHIRPS/DAILY",
            lookback_years=lookback_years,
            source_image_count=0,
        )