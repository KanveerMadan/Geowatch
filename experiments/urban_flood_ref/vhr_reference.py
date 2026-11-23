"""Guarded Maxar Open Data before/after chips for a sparse visual review.

Discover footprints via the *single approved* collection's public GeoJSON index.
Only the original vendor's visual COG supplies imagery. No credentials are used.
"""
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling, transform_bounds

from .optical_catalog import _save, grid_extent, require_space


MIRROR = "https://raw.githubusercontent.com/opengeos/maxar-open-data/master/datasets/"
SOURCE = "https://registry.opendata.aws/maxar-open-data/"
LICENCE = "https://creativecommons.org/licenses/by-nc/4.0/"
TERMS = "https://maxar-marketing.s3.amazonaws.com/files/downloads/119757_opendataprotocol_2020_04.pdf"


def _maxar_url(href):
    parts = urllib.parse.urlsplit(href)
    if parts.scheme == "s3" and parts.netloc == "maxar-opendata":
        href = "https://maxar-opendata.s3.amazonaws.com" + parts.path
        parts = urllib.parse.urlsplit(href)
    if (parts.scheme == "https" and parts.netloc == "s3.amazonaws.com" and re.fullmatch(r"/dg-opendata/[a-z0-9_-]+/(pre|post)-event/\d{4}-\d{2}-\d{2}/[A-Z0-9]+/[0-3]+\.tif", parts.path)):
        return href
    if (parts.scheme != "https" or parts.netloc not in {"maxar-opendata.s3.amazonaws.com", "maxar-opendata.s3.us-west-2.amazonaws.com", "maxar-opendata.s3.us-east-1.amazonaws.com"}
            or not parts.path.lower().endswith((".tif", ".tiff"))):
        raise ValueError("Expected an official public visual COG")
    return href


def _bounds(geometry):
    rings = geometry["coordinates"]
    if geometry["type"] == "MultiPolygon":
        vertices = [p for polygon in rings for p in polygon[0]]
    elif geometry["type"] == "Polygon":
        vertices = rings[0]
    else:
        raise ValueError("Invalid optical footprint")
    xs, ys = zip(*[point[:2] for point in vertices])
    return [min(xs), min(ys), max(xs), max(ys)]


def intersects(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def footprint_candidates(collection, grid, start, end, authorize, target):
    """Read only the allowlisted event-specific index. Return dated, overlapping tiles."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", collection):
        raise ValueError("Invalid Maxar collection identifier")
    bbox = grid_extent(grid)
    authorize(bbox, start, end)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps([collection, grid, start, end], sort_keys=True).encode()).hexdigest()[:20]
    cached = target / ("maxar-index-" + key + ".json")
    if cached.exists():
        return json.loads(cached.read_text())
    require_space(target)
    url = MIRROR + collection + ".geojson"
    request = urllib.request.Request(url, headers={"User-Agent":"GeoWatch urban-flood reference"})
    with urllib.request.urlopen(request, timeout=45) as response:
        body = response.read(90_000_001)
    if len(body) > 90_000_000:
        raise ValueError("Single-event Maxar index exceeds the 90 MB metadata limit")
    catalog = json.loads(body)
    records = []
    for feature in catalog["features"]:
        props = feature["properties"]
        when = props["datetime"]
        bounds = _bounds(feature["geometry"])
        if start <= when[:10] <= end and intersects(bbox, bounds):
            records.append({"datetime":when, "bounds":bounds, "visual":_maxar_url(props["visual"]),
                            "cloud_cover":props.get("eo:cloud_cover"), "platform":props.get("platform"),
                            "id":props.get("id") or props["visual"].split("/")[-1], "collection":collection,
                            "index_url":url, "index_sha256":hashlib.sha256(body).hexdigest()})
    _save(cached, json.dumps(records, indent=2).encode())
    return records


def read_rgb_chip(records, grid, row, col, authorize, target, scale=1):
    """One bounded 150×150 m chip around a fixed 30 m cell. Same-day mosaics only."""
    h, w = grid["shape"]
    if row < 2 or col < 2 or row + 2 >= h or col + 2 >= w or scale not in (0.5, 1):
        raise ValueError("Select a full five-cell-wide chip inside the approved grid")
    when = {r["datetime"][:10] for r in records}
    if len(when) != 1:
        raise ValueError("Exactly one observation date required")
    when = next(iter(when))
    grid_transform = Affine(*grid["transform"][:6])
    t = grid_transform * Affine.translation(col-2, row-2) * Affine.scale(scale/30)
    side = round(150/scale)
    bbox = transform_bounds(grid["crs"], "EPSG:4326", *rasterio.transform.array_bounds(side, side, t), densify_pts=21)
    authorize(bbox, when, when)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    require_space(target)
    compatible = sorted((r for r in records if intersects(bbox, r["bounds"])), key=lambda r:r["visual"])
    identity = ["legacy-pyramid-1m-v1",grid, row, col, when, scale, [r["visual"] for r in compatible]]
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    dest = target / (key + ".npz")
    if dest.exists():
        with np.load(dest) as saved:
            return saved["rgb"], saved["valid"], compatible
    rgb, valid = np.zeros((3, side, side), "uint8"), np.zeros((side, side), bool)
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_PAM_ENABLED="NO",
                      GDAL_HTTP_CONNECTTIMEOUT="15", GDAL_HTTP_TIMEOUT="60", GDAL_HTTP_MAX_RETRY="3",
                      GDAL_HTTP_RETRY_DELAY="2", GDAL_CACHEMAX=32_000_000, CPL_VSIL_CURL_CACHE_SIZE=8_000_000):
        for record in compatible:
            require_space(target)
            href = _maxar_url(record["visual"])
            if href.startswith("https://s3.amazonaws.com/dg-opendata/"):
                from .vhr_pyramid import chip
                if valid.all():
                    continue
                data, visible = chip(record,href,grid["crs"],t,(side,side),target,authorize,level=0)
                new = visible & ~valid
                rgb[:,new] = data[:,new]
                valid |= visible
                continue
            with rasterio.open(href) as src:
                if src.count < 3 or src.dtypes[:3] != ("uint8",)*3:
                    raise ValueError("Unsupported vendor visual asset; no radiometric interpretation assumed")
                with WarpedVRT(src, crs=grid["crs"], transform=t, width=side, height=side,
                               nodata=0, resampling=Resampling.bilinear, warp_mem_limit=16) as vrt:
                    data = vrt.read([1,2,3], masked=True)
                    visible = ~np.ma.getmaskarray(data).any(axis=0)
                    new = visible & ~valid
                    rgb[:, new] = data.data[:,new]
                    valid |= visible
    partial = dest.with_suffix(".partial.npz")
    np.savez_compressed(partial, rgb=rgb, valid=valid)
    os.replace(partial, dest)
    return rgb, valid, compatible


def review_pair(pre, post, path):
    """Produce an unlabelled before/after RGB pair, independent of the detector."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig, axes = plt.subplots(1, 2, figsize=(7.5, 4), constrained_layout=True)
    for ax, (rgb, valid, title) in zip(axes, (pre, post)):
        side = rgb.shape[-1]
        ax.imshow(rgb.transpose(1,2,0), interpolation="nearest")
        ax.add_patch(Rectangle((side*0.4-.5, side*0.4-.5), side*.2, side*.2, fill=False, color="yellow", linewidth=.8))
        ax.set_title(title)
        ax.set_axis_off()
    fig.suptitle("Same 150 m window · yellow outline = one model cell")
    fig.savefig(path, dpi=140)
    plt.close(fig)
