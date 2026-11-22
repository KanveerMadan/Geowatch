"""Only registered training and practice tile footprints can receive suggestions."""
from dataclasses import dataclass
from fnmatch import fnmatchcase
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TRAINING = frozenset({"cape_town", "karachi", "lima", "monrovia"})
PRACTICE = ("PRACTICE_dense_informal", "PRACTICE_formal")
PROTECTED_NAMES = ("labels.gpkg", "sun.gpkg", "labels_valid.gpkg", "labels_resolved.gpkg",
                   "metadata.json", "hr.tif", "prelabels.gpkg", "label_project.qgz",
                   "tile.geojson", "cells.geojson")


class TileRefused(ValueError):
    """No suggestions may be retrieved, generated or shown for this location."""


@dataclass(frozen=True)
class TileSpec:
    path: Path
    city: str
    tile_id: str
    image: Path
    crs: str
    bounds: tuple


def load(path):
    with Path(path).open() as stream:
        return json.load(stream)


def forbidden(parts, policy):
    parts = [str(s).casefold() for s in parts]
    sites = policy["sites"]
    excluded = {s.casefold() for s in sites} | {v["city"].casefold() for v in sites.values()}
    excluded |= {"makoko", "kibera", "rocinha", "lagos", "nairobi", "rio", "rio de janeiro",
                 "validation", "heldout", "held_out", "held-out", "blind_relabel"}
    if any(s in excluded for s in parts):
        return True
    for p in policy["tile_id_patterns"]:
        if any(fnmatchcase(s, p.casefold()) for s in parts):
            return True
    for pattern in policy["path_patterns"]:
        pat = pattern.casefold().split("/")
        for i in range(len(parts) - len(pat) + 1):
            if all(fnmatchcase(value, rule) for value, rule in zip(parts[i:], pat)):
                return True
    return False


def inspect_raster_header(path):
    try:
        from osgeo import gdal
    except ImportError:
        import rasterio
        with rasterio.Env(GDAL_PAM_ENABLED="NO"), rasterio.open(path) as src:
            if src.driver != "GTiff" or src.crs is None or src.transform.b or src.transform.d:
                raise TileRefused("Expected a projected north-up GeoTIFF")
            return src.crs.to_string(), tuple(src.bounds)
    ds = gdal.OpenEx(str(path), gdal.OF_RASTER | gdal.OF_READONLY, allowed_drivers=["GTiff"])
    if ds is None:
        raise TileRefused("Expected a local GeoTIFF")
    x, dx, rx, y, ry, dy = ds.GetGeoTransform()
    crs = ds.GetSpatialRef()
    if crs is None or rx or ry or dx <= 0 or dy >= 0:
        raise TileRefused("Invalid tile CRS or affine transform")
    return "EPSG:" + str(crs.GetAuthorityCode(None)), (x, y+dy*ds.RasterYSize, x+dx*ds.RasterXSize, y)


def registered():
    selection = load(ROOT / "data/stage1/selection.json")
    tiles = {}
    for city, site in selection["sites"].items():
        if city not in TRAINING:
            continue
        for info in site["strata"].values():
            tile = info["chosen"]
            if not tile or tile["change_test"]["dropped"]:
                continue
            tile_id = tile["tile_id"]
            crs = "EPSG:" + tile_id.split("_")[0][4:]
            tiles[tile_id] = city, crs, tile["x0"], tile["y1"], 200
    for tile_id in PRACTICE:
        m = load(ROOT / "data/practice_tiles" / tile_id / "metadata.json")
        t = m["tile_utm"]
        tiles[tile_id] = "practice", t["crs"], t["x0"], t["y1"], t["size_m"]
    return tiles


def authorize_tile(tile_dir):
    raw = Path(tile_dir).expanduser().absolute()
    tile = raw.resolve(strict=True)
    policies = [load(HERE / "heldout_split.json")]
    # Honor union with newer Item 27 rules when the calling checkout has them.
    for base in dict.fromkeys((ROOT, *tile.parents)):
        candidate = base / "configs/heldout_split.json"
        if candidate.is_file():
            policies.append(load(candidate))
    def deny_if_excluded(parts):
        if any(forbidden(parts, policy) for policy in policies):
            raise TileRefused("A held-out site, city, tile ID, or sealed path matched the Item 27 firewall")
    deny_if_excluded(raw.parts)
    deny_if_excluded(tile.parts)
    if raw.name != tile.name or raw.is_symlink() or not tile.is_dir():
        raise TileRefused("Expected the registered tile directory")
    known = registered()
    if tile.name not in known:
        raise TileRefused("Unregistered tile; update the frozen training list before use")
    for name in PROTECTED_NAMES:
        if (tile / name).is_symlink():
            raise TileRefused(f"Refusing linked tile asset: {name}")
    m = load(tile / "metadata.json")
    deny_if_excluded([m.get(k, "") for k in ("site","city","source_site","tile_id","split","role","batch","qc_status")])
    if any(word in str(m.get(k,"")).lower() for k in ("purpose","qc_status","split","role")
           for word in ("heldout","held-out","validation","sealed","blind","relabel","re-label")):
        raise TileRefused("Validation and blind repeat labels must be drawn from scratch")
    city, crs, x, top, size = known[tile.name]
    t = m["tile_utm"]
    if (m["tile_id"],m["site"],t["crs"],t["x0"],t["y1"],t["size_m"]) != (tile.name,city,crs,x,top,size):
        raise TileRefused("Tile identity or footprint differs from the registered selection")
    if city == "practice" and m.get("source_site") != "cape_town":
        raise TileRefused("Unregistered practice source")
    bounds = (x, top-size, x+size, top)
    header_crs, header_bounds = inspect_raster_header(tile/"hr.tif")
    if crs != header_crs or not all(math.isclose(a,b,abs_tol=0.001,rel_tol=0) for a,b in zip(bounds,header_bounds)):
        raise TileRefused("Image footprint differs from the registered tile")
    return TileSpec(tile, city, tile.name, tile/"hr.tif", crs, bounds)
