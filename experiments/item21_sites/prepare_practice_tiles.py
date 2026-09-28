"""
Item 21 §9 pilot C (2026-09-28): prepare two PRACTICE tiles for tracing.

PRACTICE tiles are NEVER scored and NEVER used in training. They lie outside
every labelling frame (outside every approved 3 x 3 km box, so they can never
be sampled), and their records use site "practice", which is not in the item
21 site list -- labelling.records.LabelStore refuses to store them.

Chosen 2026-09-28 by eye from the Cape Town 2025Jan city imagery around the
Khayelitsha box (the draft strata rule is inverted at Cape Town, so no
footprint metric was trusted for this):
  PRACTICE_dense_informal  tile (286000, 6235400) EPSG:32734, 691 m from the box
  PRACTICE_formal          tile (285000, 6236000) EPSG:32734, 288 m from the box

Writes data/practice_tiles/<tile>/:
  hr.tif          the tile at 0.05 m (the imagery's native 5 cm), UTM, from the
                  city MapServer export (for tracing)
  tile.geojson    the 200 m tile boundary
  cells.geojson   its 400 Sentinel-2 10 m cells (reference grid)
  labels.gpkg     EMPTY label layer, QGIS style as default (labelling/label_style.py)
  metadata.json   the tile record, marked PRACTICE, with timing fields

    python experiments/item21_sites/prepare_practice_tiles.py
"""

from __future__ import annotations

import io
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
OUT_ROOT = os.path.join(REPO, "data", "practice_tiles")

SITE_SOURCE = "cape_town"
CRS = "EPSG:32734"
TILES = {
    "PRACTICE_dense_informal": {"x0": 286000.0, "y1": 6235400.0, "looks": "dense_informal"},
    "PRACTICE_formal": {"x0": 285000.0, "y1": 6236000.0, "looks": "formal"},
}
RES_M = 0.05
EXPORT = ("https://cityimg.capetown.gov.za/erdas-iws/esri/Geospatial%20Datasets/rest/services/"
          "Aerial%20Imagery_Aerial%20Imagery%202025Jan/MapServer/export")
SERVICE_CRS = "ESRI:102562"   # wkid 20482


def check_outside_every_frame(tile, cfg):
    """A practice tile must not touch any approved box (frames lie inside boxes)."""
    from shapely.geometry import box
    from shapely.ops import transform
    from pyproj import Transformer
    for site, a in cfg["aois"].items():
        if not a.get("box_utm"):
            continue
        b = box(*a["box_utm"])
        t = tile if a["crs"] == CRS else transform(
            Transformer.from_crs(CRS, a["crs"], always_xy=True).transform, tile)
        if t.intersects(b):
            raise ValueError(f"practice tile intersects the {site} box -- it could be sampled")


def fetch_hr(tile):
    """0.05 m RGB on the tile's UTM grid: 2 x 2 service exports (each under the
    4000 px limit), reprojected and mosaicked."""
    import requests
    from PIL import Image
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds, from_origin
    from rasterio.warp import reproject
    from shapely.geometry import box
    from shapely.ops import transform
    from pyproj import Transformer
    fwd = Transformer.from_crs(CRS, SERVICE_CRS, always_xy=True)
    x0, y0, x1, y1 = tile.bounds
    n = int(round((x1 - x0) / RES_M))
    t = from_origin(x0, y1, RES_M, RES_M)
    rgb = np.zeros((3, n, n), np.uint8)
    half = (x1 - x0) / 2
    for qx in (0, 1):
        for qy in (0, 1):
            q = box(x0 + qx * half - 2, y0 + qy * half - 2, x0 + (qx + 1) * half + 2, y0 + (qy + 1) * half + 2)
            sb = transform(fwd.transform, q).bounds
            side = int(np.ceil(max(sb[2] - sb[0], sb[3] - sb[1]) / RES_M))
            r = requests.get(EXPORT, params={"bbox": ",".join(map(str, sb)), "bboxSR": 20482,
                                             "imageSR": 20482, "size": f"{side},{side}",
                                             "format": "jpg", "f": "image"}, timeout=600)
            r.raise_for_status()
            im = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB"))
            st = from_bounds(*sb, im.shape[1], im.shape[0])
            for i in range(3):
                band = np.zeros((n, n), np.uint8)
                reproject(np.ascontiguousarray(im[..., i]), band, src_transform=st, src_crs=SERVICE_CRS,
                          dst_transform=t, dst_crs=CRS, resampling=Resampling.bilinear)
                rgb[i] = np.where(band > 0, band, rgb[i])
    return rgb, t


def write_tile(name, spec, cfg):
    import rasterio
    from shapely.geometry import box, mapping
    from labelling.gpkg_style import write_gpkg
    from labelling.label_style import LAYER, empty_labels_gdf, labels_qml
    x0, y1 = spec["x0"], spec["y1"]
    tile = box(x0, y1 - 200, x0 + 200, y1)
    check_outside_every_frame(tile, cfg)
    out = os.path.join(OUT_ROOT, name)
    os.makedirs(out, exist_ok=True)

    rgb, t = fetch_hr(tile)
    with rasterio.open(os.path.join(out, "hr.tif"), "w", driver="GTiff", width=rgb.shape[2],
                       height=rgb.shape[1], count=3, dtype="uint8", crs=CRS, transform=t,
                       photometric="YCBCR", compress="JPEG", jpeg_quality=92, tiled=True,
                       blockxsize=512, blockysize=512) as dst:
        dst.write(rgb)
        dst.update_tags(NOTE="PRACTICE TILE -- never scored, never used in training (item 21)")
    with rasterio.open(os.path.join(out, "hr.tif"), "r+") as dst:
        dst.build_overviews([2, 4, 8, 16], rasterio.enums.Resampling.average)

    crs_member = {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::32734"}}
    with open(os.path.join(out, "tile.geojson"), "w") as fh:
        json.dump({"type": "FeatureCollection", "name": "tile", "crs": crs_member,
                   "features": [{"type": "Feature", "properties": {"tile_id": name},
                                 "geometry": mapping(tile)}]}, fh)
    cells = [{"type": "Feature", "properties": {"cell": f"{r}_{c}"},
              "geometry": mapping(box(x0 + 10 * c, y1 - 10 * (r + 1), x0 + 10 * (c + 1), y1 - 10 * r))}
             for r in range(20) for c in range(20)]
    with open(os.path.join(out, "cells.geojson"), "w") as fh:
        json.dump({"type": "FeatureCollection", "name": "cells", "crs": crs_member, "features": cells}, fh)

    labels = cfg["labels"]["scored"] + cfg["labels"]["excluded"]
    write_gpkg(os.path.join(out, "labels.gpkg"), empty_labels_gdf(CRS), LAYER, labels_qml(labels),
               geometry_type="Polygon")

    meta = {
        "purpose": "PRACTICE -- never scored, never used in training (LABELLING_GUIDE §9 pilot C, 2026-09-28)",
        "site": "practice",                      # not in the item 21 site list: LabelStore refuses it
        "tile_id": name,
        "looks": spec["looks"],
        "source_site": SITE_SOURCE,
        "tile_utm": {"crs": CRS, "x0": x0, "y1": y1, "size_m": 200},
        "imagery_source": "City of Cape Town 'Aerial Imagery 2025Jan' (MapServer export)",
        "imagery_acquisition_date": "2025-01 (month only)",
        "imagery_acquisition_time": None,
        "imagery_resolution_m": RES_M,
        "imagery_licence": "City of Cape Town: no restrictions on the digital file for non-commercial purposes",
        "sun_geometry": {"azimuth_deg": None, "elevation_deg": None, "method": None, "n_buildings": None,
                         "note": "no acquisition time is published: measure from >= 3 building shadows (guide v1.2)"},
        "guide_version": cfg["guide_version"],
        "labeller": None, "labelling_date": None,
        "timing": {"start_local": None, "end_local": None, "minutes": None,
                   "note": "trace the whole tile; record wall-clock start/end"},
        "pct_unsure": None, "pct_shadow_full": None,
        "qc_status": "PRACTICE",
    }
    with open(os.path.join(out, "metadata.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    return {"tile": name, "hr_px": rgb.shape[1], "hr_valid_share": round(float((rgb.max(0) > 0).mean()), 4)}


def main():
    from labelling.common import load_config
    cfg = load_config()
    for name, spec in TILES.items():
        print(json.dumps(write_tile(name, spec, cfg)), flush=True)


if __name__ == "__main__":
    main()
