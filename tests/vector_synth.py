"""Synthetic OSM/footprint builders shared by the vector-track tests
(items 19-25). Not a test module."""
import math

import pytest
from shapely.geometry import box

from vector import roads


BBOX = (72.840, 19.040, 72.850, 19.050)   # ~1.05 km x 1.11 km near Dharavi
LAT = 19.045
M_PER_DEG_LON = 111_320 * math.cos(math.radians(LAT))


def _way(wid, highway, lon0, lon1, lat, nodes, surface=None):
    n = len(nodes)
    lons = [lon0 + (lon1 - lon0) * i / (n - 1) for i in range(n)]
    tags = {"highway": highway}
    if surface:
        tags["surface"] = surface
    return {"type": "way", "id": wid, "tags": tags, "nodes": nodes,
            "geometry": [{"lon": x, "lat": lat} for x in lons]}


def _highways(ways, unavailable=()):
    return {"ways": ways, "clauses": {}, "unavailable": list(unavailable)}


def _layer(ways, footprints=(), source="open_buildings_v3"):
    return roads.build_road_layer("t", BBOX, highways=_highways(ways),
                                  footprints_4326=list(footprints), footprint_source=source)


# Two east-west ways crossing the whole box, sharing node 2 with a north-south one.
def _grid_ways():
    return [
        _way(1, "primary", 72.840, 72.850, 19.045, [1, 2, 3], surface="asphalt"),
        _way(2, "footway", 72.845, 72.845, 19.040, [4, 2, 5]),   # degenerate x, fixed below
        _way(3, "residential", 72.840, 72.850, 19.048, [6, 7]),
    ]


def _fix_ns(w):
    w["geometry"] = [{"lon": 72.845, "lat": 19.040}, {"lon": 72.845, "lat": 19.045},
                     {"lon": 72.845, "lat": 19.050}]
    return w


@pytest.fixture
def grid_layer():
    ws = _grid_ways()
    ws[1] = _fix_ns(ws[1])
    return _layer(ws)



def _rows_of_huts():
    """Two rows of 8 m x 8 m huts with a 4 m alley between rows and 3 m
    gaps within rows, the shape informal fabric takes where OSM is thin."""
    dlon = 8 / M_PER_DEG_LON
    dlat = 8 / 111_320
    gap_lon = 3 / M_PER_DEG_LON
    alley_lat = 4 / 111_320
    huts = []
    for row in range(2):
        lat0 = 19.044 + row * (dlat + alley_lat)
        for i in range(20):
            lon0 = 72.842 + i * (dlon + gap_lon)
            huts.append(box(lon0, lat0, lon0 + dlon, lat0 + dlat))
    return huts




def service_missing_layer():
    """HCMC's live shape on 2026-10-27: every clause but `service` retrieved.
    Nine footways, two arterials, one service road, and the hut rows."""
    ways = [_fix_ns(_way(100 + k, "footway", 0, 0, 0, [1000 + 3 * k, 1001 + 3 * k, 1002 + 3 * k]))
            for k in range(9)]
    ways += [_way(200 + k, "primary", 72.840, 72.850, 19.0405 + 0.0003 * k, [2000 + 2 * k, 2001 + 2 * k])
             for k in range(2)]
    ways.append(_way(400, "service", 72.840, 72.850, 19.0475, [4000, 4001]))
    layer = _layer(ways, footprints=_rows_of_huts())
    layer.fetch["unavailable"] = ["service"]
    return layer
