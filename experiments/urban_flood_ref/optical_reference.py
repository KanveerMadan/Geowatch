"""Retrospective optical corroboration of open-surface wet/dry states.

This module implements the offline reference definitions. The acquisition module
must authorize each incident and its full grid before fetching data. Only use as independent corroboration of a radar-only method.
"""
from datetime import date, timedelta
from itertools import groupby


SENSOR = "Sentinel-2 Level-2A / Sen2Cor SCL (Earth Search sentinel-2-l2a)"
SOURCE_URL = "https://sentiwiki.copernicus.eu/web/s2-processing"
LICENCE_URL = "https://dataspace.copernicus.eu/terms-and-conditions"
LABELS = {0: "optically visible non-water", 1: "new optically visible water", 255: "unobserved or ambiguous"}
BASELINE_LOOKBACK_DAYS = 60
PRE_EVENT_GAP_DAYS = 10
MAX_OPTICAL_OFFSET_DAYS = 1
MIN_PRE_LAND_DATES = 2


def evidence_windows(onset, end, radar_date, approved_start, approved_end):
    """All arguments are inclusive UTC dates. No search beyond approved dates."""
    onset, end, radar_date, approved_start, approved_end = map(
        date.fromisoformat, (onset, end, radar_date, approved_start, approved_end)
    )
    if not approved_start <= onset <= radar_date <= end <= approved_end:
        raise ValueError("Radar date and entire incident must be inside the approved interval")
    pre = (max(approved_start, onset - timedelta(days=BASELINE_LOOKBACK_DAYS)), onset - timedelta(days=PRE_EVENT_GAP_DAYS))
    post = (max(onset, radar_date - timedelta(days=MAX_OPTICAL_OFFSET_DAYS)), min(end, radar_date + timedelta(days=MAX_OPTICAL_OFFSET_DAYS)))
    def half_open(bounds):
        return None if bounds[0] > bounds[1] else (bounds[0].isoformat(), (bounds[1] + timedelta(days=1)).isoformat())
    return {"pre": half_open(pre), "post": half_open(post)}


def _day_counts(scl_entries):
    """Count distinct days after coalescing duplicate and overlapping granules."""
    import numpy as np
    records = sorted(scl_entries, key=lambda item: item[0][:10])
    if not records:
        return None, None
    shape = np.asarray(records[0][1]).shape
    land_dates = np.zeros(shape, dtype=np.uint16)
    water_dates = np.zeros(shape, dtype=np.uint16)
    for _, grouped in groupby(records, key=lambda item: item[0][:10]):
        day_land = np.zeros(shape, dtype=bool)
        day_water = np.zeros(shape, dtype=bool)
        for _, image in grouped:
            image = np.asarray(image)
            if image.shape != shape:
                raise ValueError("Inconsistent optical grids")
            day_land |= (image == 4) | (image == 5)
            day_water |= image == 6
        # Count both observations on a disagreement. This makes the pixel abstain.
        land_dates += day_land
        water_dates += day_water
    return land_dates, water_dates


def optical_states(pre, post, shape):
    """Subpixel reference requiring repeated clear, non-water pre-event evidence."""
    import numpy as np
    label = np.full(shape, 255, dtype=np.uint8)
    pre_land, pre_water = _day_counts(pre)
    post_land, post_water = _day_counts(post)
    if pre_land is None or post_land is None:
        return label
    if pre_land.shape != shape or post_land.shape != shape:
        raise ValueError("Optical grids must be co-registered")
    stable_land = (pre_land >= MIN_PRE_LAND_DATES) & (pre_water == 0)
    label[stable_land & (post_land > 0) & (post_water == 0)] = 0
    label[stable_land & (post_water > 0) & (post_land == 0)] = 1
    return label


def unanimous_30m(reference10):
    """All nine 10 m sample centres must agree; SCL has native 20 m support."""
    import numpy as np
    h, w = reference10.shape
    if h % 3 or w % 3:
        raise ValueError("Expected a nested 3:1 grid")
    blocks = reference10.reshape(h // 3, 3, w // 3, 3)
    label = np.full((h // 3, w // 3), 255, dtype=np.uint8)
    for value in (0, 1):
        label[(blocks == value).all(axis=(1, 3))] = value
    return label


def metadata_record(event_id, radar_date, windows, grid30, acquisitions, counts):
    if sum(counts.values()) != grid30["shape"][0] * grid30["shape"][1]:
        raise ValueError("Reference pixel accounting does not match grid")
    return {
        "event_id": event_id, "sensor": SENSOR, "source_documentation": SOURCE_URL,
        "source_terms": LICENCE_URL, "attribution": "Contains modified Copernicus Sentinel data",
        "effective_resolution_metres": 20, "grid": grid30, "label_codes": LABELS,
        "method": "new clear-surface water vs repeatedly clear pre-event land, homogeneous 30 m support",
        "radar_utc_date": radar_date, "search_intervals_utc_end_exclusive": windows,
        "acquisitions": acquisitions, "pixel_counts": counts,
        "limitations": [
            "Automated optical corroboration. Streets beneath roofs, vegetation and shadow can be invisible.",
            "A clear non-water return applies to the visible surface. It cannot rule out water on a street beneath a roof.",
            "Up to one UTC calendar date of offset permits inundation to change between sensors.",
            "Cloud and mixed boundaries reduce eligible coverage. Clear-only samples can favour open places.",
            "The baseline excludes previously visible water. Seasonal water appearing for the first time can still qualify.",
        ],
    }
