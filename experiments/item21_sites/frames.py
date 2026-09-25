"""
Item 21 -- labelling frames from the chosen imagery (2026-09-25).

frame = approved 3 x 3 km box ∩ chosen scene footprint(s), in the site's UTM
CRS. Reported per site: footprint coverage of the box, frame area (km²), and
the number of 200 m tiles lying ENTIRELY inside the frame -- the tiles the
sampler can draw (labelling.tiles; strata not applied here).

Footprints:
  OpenAerialMap   the record's own footprint polygon (/meta/<id>)
  Maxar ARD       union of the acquisition's ARD tile boxes
  Rio IPP         Mosaico_2024 ImageServer extent rectangle
  Cape Town       2025Jan MapServer fullExtent rectangle (Lo19 E-N = ESRI:102562)
None of these sees INTERNAL no-data (drone mosaics have gaps; site list
caveat 3), so a footprint frame is an upper bound on labellable ground. For
OpenAerialMap scenes the script ALSO measures the data frame: every file is
resampled onto the box's UTM grid at DATA_RES_M, a cell is valid where the
dataset mask is set and a band is non-zero, files are unioned, and a 200 m
tile counts only if every cell in it is valid. Found 2026-09-25: the Kibera
OAM footprint polygon (615.7 km2) is the image OUTLINE -- its data stops
exactly at the edge of the Maxar ARD tiles it repackages.

Karachi is a COMPARISON of three Maxar candidates only; nothing is chosen.

    python experiments/item21_sites/frames.py
"""

from __future__ import annotations

import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
HERE = os.path.dirname(os.path.abspath(__file__))

from experiments.item21_sites.inventory import MAXAR, _get  # noqa: E402

TILE_M = 200
DATA_RES_M = 5.0

CHOICES = {
    "makoko": {"oam": ["5dd0f6dda7dadc0006433b5b"]},  # pragma: allowlist secret -- public OAM record ids
    "monrovia": {"oam": ["5e53faa7906c590005ecc5bb", "5e557ce2642d040007b7c56f",  # pragma: allowlist secret -- public OAM record ids
                         "5e55b345642d040007b7c573", "5e71be79ccc61e00059aedcc",  # pragma: allowlist secret -- public OAM record ids
                         "5e6941c0ce171e0005d341f3", "5e679949e82eb700055028ca",  # pragma: allowlist secret -- public OAM record ids
                         "5e6a8cdb5abd57000732847c"]},  # pragma: allowlist secret -- public OAM record ids
    "lima": {"oam": ["601c75ae5ed94000077fc5ed", "5fa4dedd73fd1d000512b0d9"]},  # pragma: allowlist secret -- public OAM record ids
    "kibera": {"oam": ["663d16016049ef00013b84b8"]},  # pragma: allowlist secret -- public OAM record ids
    "rocinha": {"extent": ("EPSG:31983", (621720.15, 7444172.25, 695788.5, 7485303.6))},
    "cape_town": {"extent": ("ESRI:102562", (-64131.3824, -3803650.65, 7000.0176, -3705000.0))},
    # Chosen 2026-09-25 by the user after the coverage comparison below.
    "karachi": {"ard": ("pakistan-flooding22", "10300100D13F6500")},
}
KARACHI_CANDIDATES = {
    "10300100D13F6500": "2022-03-29",
    "10300100CFA70700": "2022-03-29",
    "1040010073509D00": "2022-03-26",
}
KARACHI_EVENT = "pakistan-flooding22"
KIBERA_ARD = ("Kenya-Flooding-May24", "104001008E063C00")


def _to(geom, src, dst):
    from pyproj import Transformer
    from shapely.ops import transform
    return transform(Transformer.from_crs(src, dst, always_xy=True).transform, geom)


def oam_footprint(oam_id, crs):
    from shapely.geometry import shape
    r = _get(f"https://api.openaerialmap.org/meta/{oam_id}")
    r = r.get("results", r)
    return _to(shape(r["geojson"]), "EPSG:4326", crs)


def ard_union(event, acq_id, crs):
    from shapely.geometry import box
    from shapely.ops import unary_union
    acq = _get(f"{MAXAR}{event}/ard/acquisition_collections/{acq_id}_collection.json")
    return _to(unary_union([box(*b) for b in acq["extent"]["spatial"]["bbox"]]), "EPSG:4326", crs)


def oam_cog_url(oam_id) -> str:
    r = _get(f"https://api.openaerialmap.org/meta/{oam_id}")
    return r.get("results", r)["uuid"]


def data_mask(urls, crs, b):
    """Valid-data mask of the union of `urls` on the box grid at DATA_RES_M.

    Reads each file's window over the box DECIMATED to ~DATA_RES_M, so GDAL
    serves it from the COG overviews (a full-resolution warp of a 5 cm drone
    mosaic reads ~60 000^2 pixels per box), then reprojects that small array
    onto the box grid with nearest neighbour.

    Valid = the file's DECLARED mask (per-dataset mask, alpha or nodata
    value) when it has one; only a file declaring none falls back to "not
    all bands zero". Found 2026-09-25: at overview resolution a genuinely
    dark pixel (deep shadow) can read as 0,0,0 -- the old "mask AND
    non-zero" rule flagged 2 such Karachi cells as no-data, while the
    declared mask alone gives identical shares at Kibera and Makoko."""
    import numpy as np
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.warp import reproject, transform_bounds
    from rasterio.windows import from_bounds
    w, s_, e, n = b.bounds
    W, H = int(round((e - w) / DATA_RES_M)), int(round((n - s_) / DATA_RES_M))
    t = from_origin(w, n, DATA_RES_M, DATA_RES_M)
    valid = np.zeros((H, W), bool)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        for u in urls:
            with rasterio.open("/vsicurl/" + u) as src:
                sb = transform_bounds(crs, src.crs, w, s_, e, n, densify_pts=21)
                win = from_bounds(*sb, transform=src.transform).round_offsets().round_lengths()
                try:                                   # file does not reach the box
                    win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
                except rasterio.errors.WindowError:
                    continue
                res = abs(src.transform.a)
                step = max(1, int(DATA_RES_M / res / 2))          # ~2x finer than the target grid
                oh, ow = max(1, int(win.height / step)), max(1, int(win.width / step))
                data = src.read(window=win, out_shape=(src.count, oh, ow),
                                resampling=Resampling.nearest, boundless=True, fill_value=0)
                m = src.read_masks(1, window=win, out_shape=(oh, ow),
                                   resampling=Resampling.nearest, boundless=True) > 0
                declared = any(f != rasterio.enums.MaskFlags.all_valid
                               for f in src.mask_flag_enums[0])
                ok = (m if declared else m & (data.max(axis=0) > 0)).astype(np.uint8)
                wt = rasterio.windows.transform(win, src.transform) * \
                    rasterio.Affine.scale(win.width / ow, win.height / oh)
                dst = np.zeros((H, W), np.uint8)
                reproject(ok, dst, src_transform=wt, src_crs=src.crs, dst_transform=t,
                          dst_crs=crs, resampling=Resampling.nearest)
                valid |= dst > 0
    return valid, t


RENDERS = {
    # site -> (service export URL, request params, service CRS). The server
    # renders the box; fill it adds outside its data (transparent, or pure
    # white / black CONNECTED TO THE BORDER) is no-data. Interior pure-white
    # pixels (roofs) are kept as data.
    "rocinha": ("https://pgeo3.rio.rj.gov.br/arcgis/rest/services/Imagens/Mosaico_2024/ImageServer/exportImage",
                {"bboxSR": 31983, "imageSR": 31983, "format": "png", "f": "image"}, "EPSG:31983"),
    "cape_town": ("https://cityimg.capetown.gov.za/erdas-iws/esri/Geospatial%20Datasets/rest/services/"
                  "Aerial%20Imagery_Aerial%20Imagery%202025Jan/MapServer/export",
                  {"bboxSR": 20482, "imageSR": 20482, "format": "jpg", "f": "image"}, "ESRI:102562"),
}


def render_mask(site, crs, b):
    """Valid-data mask from a server-side render of the box (~DATA_RES_M/px)."""
    import io
    import numpy as np
    import requests
    from PIL import Image
    from rasterio.transform import from_origin
    from scipy.ndimage import label
    url, params, scrs = RENDERS[site]
    sb = _to(b, crs, scrs).bounds
    n = int(round((b.bounds[2] - b.bounds[0]) / DATA_RES_M))
    r = requests.get(url, params={**params, "bbox": ",".join(map(str, sb)), "size": f"{n},{n}"},
                     timeout=180)
    r.raise_for_status()
    im = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGBA")).astype(int)
    rgb, a = im[..., :3], im[..., 3]
    fill = (a == 0) | (rgb.min(-1) == 255) | (rgb.max(-1) == 0)
    lab, _ = label(fill)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    return ~np.isin(lab, list(edge)), from_origin(b.bounds[0], b.bounds[3], DATA_RES_M, DATA_RES_M)


def data_frame_row(b, valid, t) -> dict:
    import numpy as np
    from labelling.tiles import tile_origins
    k = int(round(TILE_M / DATA_RES_M))
    x0g, y1g = t.c, t.f
    n_tiles = 0
    for x0, y1 in tile_origins(b.bounds, TILE_M):
        c, r = int(round((x0 - x0g) / DATA_RES_M)), int(round((y1g - y1) / DATA_RES_M))
        if valid[r:r + k, c:c + k].shape == (k, k) and valid[r:r + k, c:c + k].all():
            n_tiles += 1
    area = float(valid.sum()) * DATA_RES_M ** 2
    return {"box_data_share": round(area / b.area, 4), "data_frame_area_km2": round(area / 1e6, 3),
            "eligible_200m_tiles_data": n_tiles, "data_res_m": DATA_RES_M}


def ard_visual_urls(event, acq_id, crs, b):
    """Visual COG URLs of the acquisition's ARD tiles that touch box `b`."""
    from shapely.geometry import box as sbox
    base = f"{MAXAR}{event}/ard/acquisition_collections/"
    acq = _get(base + f"{acq_id}_collection.json")
    bw = _to(b, crs, "EPSG:4326")
    urls = []
    for il in acq["links"]:
        if il["rel"] != "item":
            continue
        item_url = base + il["href"]
        it = _get(item_url)
        if sbox(*it["bbox"]).intersects(bw):
            href = it["assets"]["visual"]["href"]
            urls.append(item_url.rsplit("/", 1)[0] + "/" + href.lstrip("./"))
    return urls


def tiles_inside(frame) -> int:
    from shapely.geometry import box
    from labelling.tiles import tile_origins
    return sum(1 for x0, y1 in tile_origins(frame.bounds, TILE_M)
               if frame.contains(box(x0, y1 - TILE_M, x0 + TILE_M, y1)))


def frame_row(b, footprint) -> dict:
    frame = b.intersection(footprint)
    return {"box_covered_share": round(frame.area / b.area, 4),
            "frame_area_km2": round(frame.area / 1e6, 3),
            "eligible_200m_tiles": tiles_inside(frame) if not frame.is_empty else 0,
            "frame_wkt_utm": frame.wkt}


def main():
    from shapely.geometry import box
    from shapely.ops import unary_union
    from labelling.common import load_config
    cfg = load_config()
    out = {"sites": {}, "karachi_candidates": {}}
    for site, choice in CHOICES.items():
        a = cfg["aois"][site]
        crs, b = a["crs"], box(*a["box_utm"])
        if "oam" in choice:
            fp = unary_union([oam_footprint(i, crs) for i in choice["oam"]])
        elif "ard" in choice:
            fp = ard_union(*choice["ard"], crs)
        else:
            src, ext = choice["extent"]
            fp = _to(box(*ext), src, crs)
        out["sites"][site] = {"sources": choice, **frame_row(b, fp)}
        if "oam" in choice:
            valid, t = data_mask([oam_cog_url(i) for i in choice["oam"]], crs, b)
            out["sites"][site].update(data_frame_row(b, valid, t))
        elif "ard" in choice:
            valid, t = data_mask(ard_visual_urls(*choice["ard"], crs, b), crs, b)
            out["sites"][site].update(data_frame_row(b, valid, t))
        elif site in RENDERS:
            valid, t = render_mask(site, crs, b)
            out["sites"][site].update(data_frame_row(b, valid, t))
            out["sites"][site]["data_method"] = "server render, border-connected fill = no-data"
        r = out["sites"][site]
        print(f"{site:10s} footprint: covered={r['box_covered_share']:.4f} frame={r['frame_area_km2']:.3f} km2 "
              f"tiles={r['eligible_200m_tiles']}"
              + (f" | DATA: covered={r['box_data_share']:.4f} frame={r['data_frame_area_km2']:.3f} km2 "
                 f"tiles={r['eligible_200m_tiles_data']}" if "box_data_share" in r else ""), flush=True)

    # Kibera: the Maxar ARD acquisition the OAM file repackages. Verified
    # 2026-09-25: pixel-identical where both exist (r = 1.0000 at two
    # patches; the 2024-05-11 acquisition correlates 0.50 / 0.12), and the
    # OAM file holds NO data outside these ARD tiles.
    a = cfg["aois"]["kibera"]
    ard = ard_union(*KIBERA_ARD, a["crs"])
    out["kibera_ard_104001008E063C00"] = frame_row(box(*a["box_utm"]), ard)
    out["kibera_oam_vs_ard"] = {
        "oam_footprint_km2": round(oam_footprint("663d16016049ef00013b84b8", a["crs"]).area / 1e6, 1),
        "ard_union_km2": round(ard.area / 1e6, 1)}

    # Karachi: comparison only.
    a = cfg["aois"]["karachi"]
    kb = box(*a["box_utm"])
    inv = json.load(open(os.path.join(HERE, "results", "imagery_inventory.json")))
    meta = {s["id"]: s for s in inv["sites"]["karachi"]["scenes"]}
    for acq_id, day in KARACHI_CANDIDATES.items():
        fp = ard_union(KARACHI_EVENT, acq_id, a["crs"])
        m = meta[acq_id]
        row = {"date": day, **{k: v for k, v in frame_row(kb, fp).items() if k != "frame_wkt_utm"},
               "gsd_m": m["resolution_m"], "off_nadir_deg": m["off_nadir_deg"],
               "sun_elevation_deg": m["sun_elevation_deg"],
               "acquisition_utc": m["acquisition_start_utc"],
               "s2_clear_pm30_60_90": [m["s2"][f"clear_scenes_pm{d}"] for d in (30, 60, 90)]}
        out["karachi_candidates"][acq_id] = row
        print(f"karachi {acq_id} {day} covered={row['box_covered_share']:.4f} "
              f"off_nadir={row['off_nadir_deg']} gsd={row['gsd_m']} tiles={row['eligible_200m_tiles']}",
              flush=True)
    path = os.path.join(HERE, "results", "frames.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print(path)


if __name__ == "__main__":
    main()
