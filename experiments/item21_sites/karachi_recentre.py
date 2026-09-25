"""
Item 21 measurement B -- Karachi AOI re-centre candidates (2026-09-25).
PROPOSALS ONLY: the user approves the box.

The first Orangi box (centre 67.0019, 24.9433) had 1.9% empty 100 m cells:
uniformly dense, no undeveloped fringe. This sweeps the centre 0-2 km west
and 0-2 km north (toward Orangi's hill edge) in 0.5 km steps and reports, per
candidate 3 x 3 km box, the same descriptive Open Buildings indicators as
aoi_proposals.py plus the share of the box covered by the site list's Maxar
scene (2022-03-29, 10300100D13F6500).

    python experiments/item21_sites/karachi_recentre.py
"""

from __future__ import annotations

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
HERE = os.path.dirname(os.path.abspath(__file__))

from experiments.item21_sites.aoi_proposals import box_wgs84, strata_indicators, utm_box  # noqa: E402
from experiments.item21_sites.inventory import MAXAR, _get  # noqa: E402

ORIGINAL = (67.0019, 24.9433)
SCENE = ("pakistan-flooding22", "10300100D13F6500")     # site list: Maxar 2022-03-29 (event id as the inventory recorded it)
STEPS_KM = [0.0, 0.5, 1.0, 1.5, 2.0]


def scene_union(utm):
    from shapely.geometry import box
    from shapely.ops import unary_union
    from experiments.item21_sites.aoi_proposals import to_utm
    acq = _get(f"{MAXAR}{SCENE[0]}/ard/acquisition_collections/{SCENE[1]}_collection.json")
    return to_utm(unary_union([box(*b) for b in acq["extent"]["spatial"]["bbox"]]), utm)


def main():
    from pyproj import Transformer
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    utm0, _ = utm_box(*ORIGINAL)
    to_utm_t = Transformer.from_crs("EPSG:4326", utm0, always_xy=True)
    to_ll = Transformer.from_crs(utm0, "EPSG:4326", always_xy=True)
    x0, y0 = to_utm_t.transform(*ORIGINAL)
    scene = scene_union(utm0)
    rows = []
    for west_km in STEPS_KM:
        for north_km in STEPS_KM:
            lon, lat = to_ll.transform(x0 - west_km * 1000, y0 + north_km * 1000)
            utm, b = utm_box(lon, lat)
            bw = box_wgs84(utm, b)
            ind = strata_indicators(bw, utm)
            row = {"shift_west_km": west_km, "shift_north_km": north_km,
                   "centre_lon_lat": [round(lon, 6), round(lat, 6)],
                   "box_utm": [round(v, 1) for v in b.bounds], "crs": utm.to_string(),
                   "site_list_scene_covered_share": round(float(scene.intersection(b).area / b.area), 4),
                   **ind}
            rows.append(row)
            print(f"W{west_km:.1f} N{north_km:.1f}  empty={ind['share_100m_cells_without_buildings']:.3f} "
                  f"bldgs={ind['buildings']} scene={row['site_list_scene_covered_share']:.3f}", flush=True)
    path = os.path.join(HERE, "results", "karachi_recentre.json")
    with open(path, "w") as fh:
        json.dump({"original_centre": ORIGINAL, "scene": SCENE, "candidates": rows}, fh, indent=1)
    print(path)


if __name__ == "__main__":
    main()
