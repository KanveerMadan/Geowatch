"""
Item 21 -- Cape Town imagery extent, determined by machine-readable means
(2026-09-25). Report only; the Cape Town AOI stays pending until approved.

The city's ERDAS APOLLO service returns nothing on its ImageServer endpoint
but answers on MapServer:
  - MapServer?f=json -> description (licence wording), fullExtent rectangle,
    spatialReference wkid 20482, which behaves as Hartebeesthoek94 / Lo19
    (E-N), i.e. ESRI:102562 (Khayelitsha projects inside the extent);
  - MapServer/export -> the proposed box rendered server-side in that CRS
    (JPEG; png/png32 are refused), checked for fill-colour no-data.

The fullExtent is a bounding rectangle, not a valid-data footprint; the
render test is what shows the box itself is covered. JPEG carries no
transparency, so "no black / white fill" rules out fill-colour no-data only.

    python experiments/item21_sites/capetown_extent.py
"""

from __future__ import annotations

import io
import json
import os

import numpy as np
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = ("https://cityimg.capetown.gov.za/erdas-iws/esri/Geospatial%20Datasets/rest/services/"
        "Aerial%20Imagery_Aerial%20Imagery%20{}/MapServer")
YEARS = ("2026Jan", "2025Jan")
SERVICE_CRS = "ESRI:102562"                       # behaviour of wkid 20482
PROPOSED_BOX_UTM = ("EPSG:32734", (282308.6, 6232511.7, 285308.6, 6235511.7))  # Khayelitsha


def main():
    from PIL import Image
    from pyproj import Transformer
    from shapely.geometry import box
    from shapely.ops import transform

    crs, b = PROPOSED_BOX_UTM
    tr = Transformer.from_crs(crs, SERVICE_CRS, always_xy=True)
    lo = transform(tr.transform, box(*b)).bounds
    out = {"service_crs_interpretation": f"wkid 20482 treated as {SERVICE_CRS} "
                                         "(Hartebeesthoek94 / Lo19, E-N)",
           "proposed_box": {"crs": crs, "box": list(b), "in_service_crs": [round(v, 1) for v in lo]},
           "years": {}}
    for y in YEARS:
        meta = requests.get(BASE.format(y) + "?f=json", timeout=120).json()
        ext = meta["fullExtent"]
        inside = (ext["xmin"] <= lo[0] and lo[2] <= ext["xmax"]
                  and ext["ymin"] <= lo[1] and lo[3] <= ext["ymax"])
        url = (BASE.format(y) + f"/export?bbox={lo[0]},{lo[1]},{lo[2]},{lo[3]}"
               "&bboxSR=20482&imageSR=20482&size=600,600&format=jpg&f=image")
        r = requests.get(url, timeout=180)
        render = {"http": r.status_code, "content_type": r.headers.get("content-type")}
        if r.ok and render["content_type"].startswith("image"):
            rgb = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB")).astype(int)
            render.update({"pixels": int(rgb.shape[0] * rgb.shape[1]),
                           "metres_per_pixel": round((lo[2] - lo[0]) / rgb.shape[1], 2),
                           "pure_black_share": float((rgb.sum(-1) == 0).mean()),
                           "pure_white_share": float((rgb.min(-1) == 255).mean()),
                           "rgb_std": rgb.reshape(-1, 3).std(0).round(1).tolist()})
        out["years"][y] = {"description": meta.get("description"),
                           "full_extent": {k: ext[k] for k in ("xmin", "ymin", "xmax", "ymax")},
                           "box_inside_full_extent": inside, "render": render}
        print(y, "inside extent:", inside, render)
    path = os.path.join(HERE, "results", "capetown_extent.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print(path)


if __name__ == "__main__":
    main()
