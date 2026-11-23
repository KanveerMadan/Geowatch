"""Bounded public Earth Search COG reference acquisition for one cleared incident.

Call collect() only from the study's leakage-guard entry point. The supplied
authorize(bbox, start_inclusive, end_inclusive) callable must raise if access
is denied. It is called before catalog, caches, imagery or output are touched.
"""
import hashlib
import io
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import rasterio
from affine import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import Resampling, transform_bounds

from .optical_reference import MIN_PRE_LAND_DATES, evidence_windows, metadata_record, unanimous_30m

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1/search"
MAX_CATALOG_ROWS = 100
MIN_DISK_BYTES = 15_000_000_000


def require_space(path):
    if shutil.disk_usage(path).free < MIN_DISK_BYTES:
        raise RuntimeError("Less than 15 GB free at the optical cache")


def _save(path, data):
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def _cache_key(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _read_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/geo+json", "User-Agent": "GeoWatch-urban-flood-reference/1"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=50) as response:
                body = response.read(12_000_001)
            if len(body) > 12_000_000:
                raise ValueError("Catalog response exceeded 12 MB bound")
            return json.loads(body)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 3:
                raise
        except (TimeoutError, urllib.error.URLError):
            if attempt == 3:
                raise
        time.sleep(2 ** (attempt + 1))


def _public_cog_url(href):
    parts = urllib.parse.urlsplit(href)
    if parts.scheme == "s3" and parts.netloc == "sentinel-cogs":
        href = "https://sentinel-cogs.s3.us-west-2.amazonaws.com" + parts.path
        parts = urllib.parse.urlsplit(href)
    allowed_hosts = {"sentinel-cogs.s3.us-west-2.amazonaws.com", "sentinel-cogs.s3.amazonaws.com"}
    if parts.scheme != "https" or parts.netloc not in allowed_hosts or not parts.path.lower().endswith((".tif", ".tiff")):
        raise ValueError("SCL asset is outside the public Sentinel COG collection")
    return href


def search(bbox, window, cache):
    if window is None:
        return []
    key = _cache_key([EARTH_SEARCH, bbox, window, "sentinel-2-l2a", 1])
    path = cache / (key + ".json")
    if path.exists():
        return json.loads(path.read_text())
    require_space(cache)
    start, exclusive_end = window
    inclusive_end = (date.fromisoformat(exclusive_end) - timedelta(days=1)).isoformat()
    query = {"collections": "sentinel-2-l2a", "bbox": ",".join(str(x) for x in bbox),
             "datetime": start+"T00:00:00Z/"+inclusive_end+"T23:59:59.999Z", "limit": MAX_CATALOG_ROWS}
    data = _read_json(EARTH_SEARCH + "?" + urllib.parse.urlencode(query))
    if any(link.get("rel") == "next" for link in data.get("links", [])):
        raise RuntimeError("Exceeded bounded catalog query; no partial search accepted")
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError("Invalid catalog response")
    records = {}
    for feature in data["features"]:
        when = feature["properties"]["datetime"]
        if feature["collection"] != "sentinel-2-l2a" or not start <= when[:10] < exclusive_end:
            raise ValueError("Result outside the authorized collection or period")
        asset = feature["assets"]["scl"]
        # Earth Search uses read-only, unsigned Amazon S3 source COGs.
        records[feature["id"]] = {"id": feature["id"], "datetime": when, "href": _public_cog_url(asset["href"])}
    records = sorted(records.values(), key=lambda r: (r["datetime"], r["id"]))
    _save(path, json.dumps(records, indent=2).encode())
    return records


def grid_extent(grid):
    h, w = grid["shape"]
    t = Affine(*grid["transform"][:6])
    if (t.a, t.b, t.d, t.e) != (30, 0, 0, -30) or h <= 0 or w <= 0:
        raise ValueError("Expected a north-up 30 m model grid")
    if h * w > 1_000_000:
        raise ValueError("Too large for a single bounded optical chip")
    return list(transform_bounds(grid["crs"], "EPSG:4326", *rasterio.transform.array_bounds(h, w, t), densify_pts=21))


def _read_chip(record, grid, cache):
    key = _cache_key([record["href"], grid, "SCL nested nearest 10m v1"])
    path = cache / (key + ".npy")
    h, w = grid["shape"]
    shape = (3*h, 3*w)
    if path.exists():
        chip = np.load(path, allow_pickle=False)
        if chip.shape != shape or chip.dtype != np.uint8:
            raise ValueError("Incompatible cached optical chip")
        return chip
    require_space(cache)
    t = Affine(*grid["transform"][:6]) * Affine.scale(1/3)
    href = _public_cog_url(record["href"])
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_PAM_ENABLED="NO",
                      AWS_NO_SIGN_REQUEST="YES", GDAL_HTTP_CONNECTTIMEOUT="15", GDAL_HTTP_TIMEOUT="60",
                      GDAL_HTTP_MAX_RETRY="3", GDAL_HTTP_RETRY_DELAY="2",
                      GDAL_CACHEMAX=32_000_000, CPL_VSIL_CURL_CACHE_SIZE=8_000_000):
        with rasterio.open(href) as src:
            with WarpedVRT(src, crs=grid["crs"], transform=t, width=shape[1], height=shape[0],
                           src_nodata=0, nodata=0, resampling=Resampling.nearest, warp_mem_limit=16) as vrt:
                chip = vrt.read(1, out_dtype="uint8")
    buf = io.BytesIO()
    np.save(buf, chip, allow_pickle=False)
    _save(path, buf.getvalue())
    return chip


def _counts(records, grid, cache):
    h, w = grid["shape"]
    shape = (3*h, 3*w)
    land, water = np.zeros(shape, dtype="uint16"), np.zeros(shape, dtype="uint16")
    grouped = defaultdict(list)
    for entry in records:
        grouped[entry["datetime"][:10]].append(entry)
    for entries in grouped.values():
        day_land = np.zeros(shape, dtype=bool)
        day_water = np.zeros(shape, dtype=bool)
        for entry in entries:
            chip = _read_chip(entry, grid, cache)
            day_land |= (chip == 4) | (chip == 5)
            day_water |= chip == 6
        land += day_land
        water += day_water
    return land, water


def collect(event_id, grid, onset, end, radar_date, approved_start, approved_end,
            authorize, output):
    """Write independent/{event_id}/{s2_ref.tif,reference.json} via study caller."""
    bbox = grid_extent(grid)
    windows = evidence_windows(onset, end, radar_date, approved_start, approved_end)
    # Includes spaces between pre/post, and the incident even when the SAR date is late.
    authorize(bbox, approved_start, approved_end)
    path = Path(output)
    path.mkdir(parents=True, exist_ok=True)
    cache = path / ".optical_cache"
    cache.mkdir(exist_ok=True)
    post = search(bbox, windows["post"], cache)
    # Save I/O when there is no contemporaneous observation at all.
    pre = search(bbox, windows["pre"], cache) if post else []
    h, w = grid["shape"]
    fine = np.full((h*3, w*3), 255, dtype="uint8")
    if len({rec["datetime"][:10] for rec in pre}) >= MIN_PRE_LAND_DATES:
        dry_pre, wet_pre = _counts(pre, grid, cache)
        dry_post, wet_post = _counts(post, grid, cache)
        stable = (dry_pre >= MIN_PRE_LAND_DATES) & (wet_pre == 0)
        fine[stable & (dry_post > 0) & (wet_post == 0)] = 0
        fine[stable & (wet_post > 0) & (dry_post == 0)] = 1
    result = unanimous_30m(fine)
    counts = {str(value): int(np.count_nonzero(result == value)) for value in (0, 1, 255)}
    metadata = metadata_record(event_id, radar_date, windows, grid, {"pre": pre, "post": post}, counts)
    metadata.update(catalog=EARTH_SEARCH, pre_query_skipped_for_absent_post=not bool(post),
                    agreement="Report separately from independent human-labelled extents")
    temporary = path / "s2_ref.partial.tif"
    with rasterio.open(temporary, "w", driver="GTiff", height=h, width=w, count=1, dtype="uint8",
                       crs=grid["crs"], transform=Affine(*grid["transform"][:6]), nodata=255,
                       compress="deflate") as ds:
        ds.write(result, 1)
        ds.set_band_description(1, "Optically visible new water vs observed non-water")
    os.replace(temporary, path / "s2_ref.tif")
    _save(path / "reference.json", json.dumps(metadata, indent=2).encode())
    return counts
