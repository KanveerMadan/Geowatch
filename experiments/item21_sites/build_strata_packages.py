"""
Item 21 -- QGIS strata-drawing packages, one per site (2026-09-25).

    python experiments/item21_sites/build_strata_packages.py [site ...]

writes data/strata_packages/<site>/:

  preview.tif      the chosen scene over the approved 3 x 3 km box, ~1 m,
                   8-bit RGB with an internal mask, site UTM CRS.
                   PREVIEW ONLY -- never a labelling source (labels are
                   traced on the full-resolution source).
  box.geojson      the approved box                      (site UTM CRS)
  frame.geojson    the real-data labelling frame          (site UTM CRS) --
                   the same valid-pixel mask as frames.py, vectorised
  strata.geojson   empty template layer to draw strata in  (site UTM CRS)
  strata.qml       QGIS style: Value Map on "stratum" + a fill per stratum

Only strata.geojson and strata.qml are tracked by git (see .gitignore).

Sources, per configs/labelling.yaml aois.<site>.frame_sources:
  oam      OpenAerialMap COGs, read through their overviews
  ard      Maxar ARD visual COGs of the acquisition over the box
  service  Rio IPP ImageServer exportImage / Cape Town ERDAS MapServer export
"""

from __future__ import annotations

import io
import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from experiments.item21_sites.frames import (RENDERS, ard_visual_urls, data_mask,  # noqa: E402
                                             oam_cog_url, render_mask, _to)

OUT_ROOT = os.path.join(REPO, "data", "strata_packages")
PREVIEW_RES_M = 1.0
COLOURS = {                                  # distinct, colour-blind-safe-ish
    "dense_informal": "215,48,31",
    "formal": "33,113,181",
    "mixed": "128,125,186",
    "fringe": "65,171,93",
}


def crs_member(crs: str) -> dict:
    code = crs.split(":", 1)[1]
    auth = crs.split(":", 1)[0]
    return {"type": "name", "properties": {"name": f"urn:ogc:def:crs:{auth}::{code}"}}


def write_geojson(path, geoms_props, crs, name):
    from shapely.geometry import mapping
    fc = {"type": "FeatureCollection", "name": name, "crs": crs_member(crs),
          "features": [{"type": "Feature", "properties": props, "geometry": mapping(g)}
                       for g, props in geoms_props]}
    with open(path, "w") as fh:
        json.dump(fc, fh)


def frame_polygon(valid, t):
    """Vectorise a valid-data mask into one (multi)polygon."""
    from rasterio.features import shapes
    from shapely.geometry import shape
    from shapely.ops import unary_union
    return unary_union([shape(g) for g, v in shapes(valid.astype(np.uint8), mask=valid, transform=t)
                        if v == 1])


def preview_from_cogs(urls, crs, b):
    """RGB + mask on the box grid at PREVIEW_RES_M, read via COG overviews."""
    import rasterio
    from rasterio.enums import MaskFlags, Resampling
    from rasterio.transform import from_origin
    from rasterio.warp import reproject, transform_bounds
    from rasterio.windows import Window, from_bounds
    w, s_, e, n = b.bounds
    W, H = int(round((e - w) / PREVIEW_RES_M)), int(round((n - s_) / PREVIEW_RES_M))
    t = from_origin(w, n, PREVIEW_RES_M, PREVIEW_RES_M)
    rgb = np.zeros((3, H, W), np.uint8)
    have = np.zeros((H, W), bool)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
        for u in urls:
            with rasterio.open("/vsicurl/" + u) as src:
                sb = transform_bounds(crs, src.crs, w, s_, e, n, densify_pts=21)
                win = from_bounds(*sb, transform=src.transform).round_offsets().round_lengths()
                try:
                    win = win.intersection(Window(0, 0, src.width, src.height))
                except rasterio.errors.WindowError:
                    continue
                step = max(1, int(PREVIEW_RES_M / abs(src.transform.a) / 2))
                oh, ow = max(1, int(win.height / step)), max(1, int(win.width / step))
                d = src.read([1, 2, 3], window=win, out_shape=(3, oh, ow), resampling=Resampling.average)
                m = src.read_masks(1, window=win, out_shape=(oh, ow), resampling=Resampling.nearest) > 0
                if not any(f != MaskFlags.all_valid for f in src.mask_flag_enums[0]):
                    m &= d.max(axis=0) > 0
                wt = rasterio.windows.transform(win, src.transform) * \
                    rasterio.Affine.scale(win.width / ow, win.height / oh)
                band = np.zeros((H, W), np.uint8)
                mk = np.zeros((H, W), np.uint8)
                reproject(m.astype(np.uint8), mk, src_transform=wt, src_crs=src.crs,
                          dst_transform=t, dst_crs=crs, resampling=Resampling.nearest)
                fill = (mk > 0) & ~have
                for i in range(3):
                    reproject(d[i], band, src_transform=wt, src_crs=src.crs, dst_transform=t,
                              dst_crs=crs, resampling=Resampling.bilinear)
                    rgb[i][fill] = band[fill]
                have |= fill
    return rgb, have, t


def preview_from_service(site, crs, b):
    """Server-side export of the box's envelope, reprojected onto the box grid."""
    import requests
    from PIL import Image
    from rasterio.enums import Resampling
    from rasterio.transform import from_bounds, from_origin
    from rasterio.warp import reproject
    from scipy.ndimage import label
    url, params, scrs = RENDERS[site]
    sb = _to(b, crs, scrs).bounds
    side = int(np.ceil(max(sb[2] - sb[0], sb[3] - sb[1]) / PREVIEW_RES_M))
    r = requests.get(url, params={**params, "bbox": ",".join(map(str, sb)), "size": f"{side},{side}"},
                     timeout=600)
    r.raise_for_status()
    im = np.asarray(Image.open(io.BytesIO(r.content)).convert("RGBA"))
    fill = (im[..., 3] == 0) | (im[..., :3].min(-1) == 255) | (im[..., :3].max(-1) == 0)
    lab, _ = label(fill)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    ok = ~np.isin(lab, list(edge))
    st = from_bounds(*sb, im.shape[1], im.shape[0])
    w, s_, e, n = b.bounds
    W, H = int(round((e - w) / PREVIEW_RES_M)), int(round((n - s_) / PREVIEW_RES_M))
    t = from_origin(w, n, PREVIEW_RES_M, PREVIEW_RES_M)
    rgb = np.zeros((3, H, W), np.uint8)
    for i in range(3):
        reproject(np.ascontiguousarray(im[..., i]), rgb[i], src_transform=st, src_crs=scrs,
                  dst_transform=t, dst_crs=crs, resampling=Resampling.bilinear)
    mk = np.zeros((H, W), np.uint8)
    reproject(ok.astype(np.uint8), mk, src_transform=st, src_crs=scrs, dst_transform=t,
              dst_crs=crs, resampling=Resampling.nearest)
    return rgb, mk > 0, t


def write_preview(path, rgb, have, t, crs):
    import rasterio
    rgb = np.where(have, rgb, 0).astype(np.uint8)
    with rasterio.open(path, "w", driver="GTiff", width=rgb.shape[2], height=rgb.shape[1], count=3,
                       dtype="uint8", crs=crs, transform=t, photometric="RGB", compress="deflate",
                       tiled=True, blockxsize=512, blockysize=512) as dst:
        dst.write(rgb)
        dst.write_mask((have * 255).astype(np.uint8))
        dst.descriptions = ("red", "green", "blue")
        dst.update_tags(NOTE="PREVIEW ONLY -- never a labelling source (item 21)")
    with rasterio.open(path, "r+") as dst:
        dst.build_overviews([2, 4, 8], rasterio.enums.Resampling.average)


def strata_qml(strata: list) -> str:
    cats = "\n".join(f'      <category symbol="{i}" value="{s}" label="{s}" render="true"/>'
                     for i, s in enumerate(strata))
    syms = "\n".join(f'''      <symbol type="fill" name="{i}" alpha="0.4" clip_to_extent="1" force_rhr="0">
        <layer class="SimpleFill" enabled="1" locked="0" pass="0">
          <Option type="Map">
            <Option name="color" type="QString" value="{COLOURS[s]},255"/>
            <Option name="outline_color" type="QString" value="{COLOURS[s]},255"/>
            <Option name="outline_style" type="QString" value="solid"/>
            <Option name="outline_width" type="QString" value="0.6"/>
            <Option name="style" type="QString" value="solid"/>
          </Option>
        </layer>
      </symbol>''' for i, s in enumerate(strata))
    vmap = "\n".join(f'''              <Option type="Map"><Option name="{s}" type="QString" value="{s}"/></Option>'''
                     for s in strata)
    return f'''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<!-- Item 21 strata style (LABELLING_GUIDE.md §3). Generated by
     experiments/item21_sites/build_strata_packages.py; do not hand-edit. -->
<qgis version="3.28" styleCategories="Symbology|Fields|Forms">
  <renderer-v2 type="categorizedSymbol" attr="stratum" symbollevels="0" enableorderby="0" forceraster="0">
    <categories>
{cats}
    </categories>
    <symbols>
{syms}
    </symbols>
  </renderer-v2>
  <fieldConfiguration>
    <field name="stratum" configurationFlags="None">
      <editWidget type="ValueMap">
        <config>
          <Option type="Map">
            <Option name="map" type="List">
{vmap}
            </Option>
          </Option>
        </config>
      </editWidget>
    </field>
  </fieldConfiguration>
  <constraints>
    <constraint field="stratum" constraints="1" notnull_strength="1" unique_strength="0" exp_strength="0"/>
  </constraints>
</qgis>
'''


def build(site: str, cfg: dict) -> dict:
    from shapely.geometry import box
    a = cfg["aois"][site]
    if a["status"] != "approved" or not a.get("frame_scene"):
        raise ValueError(f"{site}: needs an approved AOI and a frame scene")
    crs, b = a["crs"], box(*a["box_utm"])
    src = a["frame_sources"]
    out = os.path.join(OUT_ROOT, site)
    os.makedirs(out, exist_ok=True)

    if "oam" in src:
        urls = [oam_cog_url(i) for i in src["oam"]]
    elif "ard" in src:
        urls = ard_visual_urls(src["ard"][0], src["ard"][1], crs, b)
    else:
        urls = None
    if urls is not None:
        valid, vt = data_mask(urls, crs, b)
        rgb, have, pt = preview_from_cogs(urls, crs, b)
    else:
        valid, vt = render_mask(site, crs, b)
        rgb, have, pt = preview_from_service(site, crs, b)

    write_preview(os.path.join(out, "preview.tif"), rgb, have, pt, crs)
    write_geojson(os.path.join(out, "box.geojson"), [(b, {"site": site})], crs, "box")
    frame = frame_polygon(valid, vt)
    write_geojson(os.path.join(out, "frame.geojson"),
                  [(frame, {"site": site, "basis": "data", "area_km2": round(frame.area / 1e6, 3)})],
                  crs, "frame")
    tmpl = {"type": "FeatureCollection", "name": "strata", "crs": crs_member(crs), "features": []}
    with open(os.path.join(out, "strata.geojson"), "w") as fh:
        json.dump(tmpl, fh, indent=1)
    with open(os.path.join(out, "strata.qml"), "w") as fh:
        fh.write(strata_qml(cfg["tiles"]["strata"]))
    return {"site": site, "preview_valid_share": round(float(have.mean()), 4),
            "frame_area_km2": round(frame.area / 1e6, 3),
            "frame_config_km2": a["frame_data"]["area_km2"]}


def main(sites):
    from labelling.common import load_config
    cfg = load_config()
    for s in sites or [k for k, v in cfg["aois"].items() if v.get("frame_scene")]:
        print(json.dumps(build(s, cfg)), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
