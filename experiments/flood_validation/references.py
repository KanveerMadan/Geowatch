"""
Flood references for validation round 2 (item 26 Phase 1a). Rules fixed in
PREREGISTRATION_ROUND2.md, §References.

Each reference returns 30 m arrays on an event's grid:
    flooded  bool    the reference says this cell flooded
    valid    bool    the reference observed this cell (and it is not
                     JRC permanent water)
plus `meta`: source, resolution, the product or image dates actually used.

    Copernicus EMS rapid mapping  observedEventA polygons ("Flooded area" or
                                  "Flood trace"); a cell is flooded if >= half
                                  its area is covered (rasterised at 3 m),
                                  valid if >= half lies in the product extent
    Sentinel-1                    earliest acquisition date in the event
                                  window; pre-event = median of the 30 days
                                  before, same relative orbit(s); VV drop
                                  <= -3 dB at 10 m; >= half the 10 m pixels
    GFD                           MODIS 250 m `flooded`, sampled nearest;
                                  scored on 240 m blocks (EVAL_BLOCK_GFD)
    JRC GSW recurrent water       5 % <= occurrence < 80 %; dry < 5 %

JRC permanent water (occurrence >= 80 %) is excluded from every reference.
Every Earth Engine request has a hard deadline (ee_timeout.call); EMS
downloads have an HTTP timeout and are cached with their SHA256.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import urllib.request

import numpy as np

from configs.inundation_constants import (
    JRC_ASSET, JRC_PERMANENT_WATER_OCCURRENCE_PCT, JRC_SEASONAL_WATER_OCCURRENCE_PCT,
    S1_COLLECTION, S1_INSTRUMENT_MODE, S1_POLARIZATION, S1_VV_DROP_THRESHOLD_DB,
)

EMS_API = ("https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/"
           "public-activations/?code={code}")
EMS_FLOODED_NOTATIONS = ("Flooded area", "Flood trace")
EMS_SUPERSAMPLE = 10              # 30 m cell -> 3 m sub-cells
COVER_MIN = 0.5                   # >= half a cell's area / sub-pixels
S1_PRE_EVENT_DAYS = 30
GFD_ASSET = "GLOBAL_FLOOD_DB/MODIS_EVENTS/V1"
EVAL_BLOCK_GFD = 8                # 8 x 30 m = 240 m, about GFD's 250 m
HTTP_TIMEOUT_S = 120
EE_TIMEOUT_S = 600
CACHE = os.environ.get("GEOWATCH_FLOOD_REF_CACHE",
                       os.path.expanduser("~/.cache/geowatch/flood_refs"))


# ── pure ────────────────────────────────────────────────────────────────

def square_bbox(lat: float, lon: float, side_m: float = 4000.0) -> tuple:
    """(W, S, E, N) of a side_m square centred on (lat, lon)."""
    half = side_m / 2.0
    dlat = half / 111_320.0
    dlon = half / (111_320.0 * np.cos(np.radians(lat)))
    return (round(lon - dlon, 6), round(lat - dlat, 6), round(lon + dlon, 6), round(lat + dlat, 6))


def pick_event_date(timestamps_ms, event: str, window_days: int):
    """The earliest UTC acquisition date in [event, event + window_days), or
    None. The window counts the event day as day 0."""
    e = datetime.date.fromisoformat(event)
    end = e + datetime.timedelta(days=window_days)
    days = sorted({datetime.datetime.fromtimestamp(t / 1000, datetime.timezone.utc).date()
                   for t in timestamps_ms})
    days = [d for d in days if e <= d < end]
    return days[0] if days else None


def coverage(geoms, transform, shape, k: int = EMS_SUPERSAMPLE) -> np.ndarray:
    """Share of each cell's area covered by `geoms` (already in the grid CRS),
    from a k x k supersampled rasterisation."""
    from rasterio.features import rasterize
    from rasterio.transform import Affine
    H, W = shape
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return np.zeros(shape)
    fine = rasterize(((g, 1) for g in geoms), out_shape=(H * k, W * k),
                     transform=transform * Affine.scale(1.0 / k), fill=0, dtype="uint8")
    return fine.reshape(H, k, W, k).mean(axis=(1, 3))


def blocks(score: np.ndarray, flooded: np.ndarray, valid: np.ndarray, b: int):
    """Aggregate 30 m cells into b x b blocks: valid if >= half the cells are
    valid; score = mean of valid cells; flooded if >= half the valid cells are."""
    H, W = (score.shape[0] // b) * b, (score.shape[1] // b) * b
    ok = (valid & np.isfinite(score))[:H, :W]
    s = np.where(ok, score[:H, :W], 0.0).reshape(H // b, b, W // b, b)
    f = np.where(ok, flooded[:H, :W], False).reshape(H // b, b, W // b, b)
    n = ok.reshape(H // b, b, W // b, b).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        bs = s.sum(axis=(1, 3)) / n
        bf = f.sum(axis=(1, 3)) / n >= COVER_MIN
    bv = n >= COVER_MIN * b * b
    return bs, bf, bv


def cells(score, flooded, valid, block: int = 1):
    """(scores, flooded labels) of the valid evaluation cells."""
    score = np.asarray(score, dtype=np.float64)
    flooded, valid = np.asarray(flooded, bool), np.asarray(valid, bool)
    if block > 1:
        score, flooded, valid = blocks(score, flooded, valid, block)
    ok = valid & np.isfinite(score)
    return score[ok], flooded[ok]


# ── Copernicus EMS ──────────────────────────────────────────────────────

def _fetch(url: str, path: str) -> bytes:
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as r:
            data = r.read()
        with open(path, "wb") as f:
            f.write(data)
    with open(path, "rb") as f:
        return f.read()


def ems_product(code: str, aoi: int, monitoring: int) -> dict:
    """The DEL product (activation, AOI number, monitoring number) with its
    extent, images, and observedEventA layer URL."""
    from shapely import wkt
    act = json.loads(_fetch(EMS_API.format(code=code), os.path.join(CACHE, "ems", f"{code}.json")))
    act = act["results"][0]
    a = next(a for a in act["aois"] if a["number"] == aoi)
    p = next(p for p in a["products"]
             if p["type"] == "DEL" and (p.get("monitoringNumber") or 0) == monitoring)
    layer = next(l for l in p["layers"]
                 if "_observedEventA" in l["name"] and "previous" not in l["name"])
    return {"code": code, "aoi": aoi, "aoi_name": a["name"], "monitoring": monitoring,
            "event_time": act["eventTime"], "extent": wkt.loads(p["extent"]),
            "images": [{"sensor": i["sensorName"], "resolution_class": i["resolutionClass"],
                        "acquired": i["acquisitionTime"]} for i in p["images"]],
            "layer_url": layer["json"]}


def ems_polygons(product: dict):
    """(flooded polygons in EPSG:4326, notation counts, SHA256 of the layer)."""
    from shapely.geometry import shape as to_shape
    name = os.path.basename(product["layer_url"])
    raw = _fetch(product["layer_url"], os.path.join(CACHE, "ems", "layers", name))
    fc = json.loads(raw)
    keep, counts = [], {}
    for f in fc["features"]:
        n = f["properties"].get("notation")
        counts[n] = counts.get(n, 0) + 1
        if n in EMS_FLOODED_NOTATIONS and f.get("geometry"):
            keep.append(to_shape(f["geometry"]))
    return keep, counts, hashlib.sha256(raw).hexdigest()


def _to_crs(geoms, crs: str):
    from pyproj import Transformer
    from shapely.ops import transform as shp_transform
    t = Transformer.from_crs(4326, crs, always_xy=True).transform
    return [shp_transform(t, g) for g in geoms]


def ems_reference(product: dict, bbox, transform, shape, crs: str) -> dict:
    from shapely.geometry import box
    polys, counts, sha = ems_polygons(product)
    region = product["extent"].intersection(box(*bbox))
    cover = coverage(_to_crs(polys, crs), transform, shape)
    inside = coverage(_to_crs([region], crs), transform, shape)
    occ = jrc_occurrence(transform, shape, crs)
    return {"flooded": cover >= COVER_MIN, "valid": (inside >= COVER_MIN) & not_permanent(occ),
            "block": 1,
            "meta": {"source": f"Copernicus EMS {product['code']} AOI{product['aoi']:02d} "
                               f"({product['aoi_name']}) DEL monitoring {product['monitoring']}",
                     "images": product["images"], "resolution": "per sensor, see images",
                     "layer_url": product["layer_url"], "layer_sha256": sha,
                     "notation_counts": counts, "flooded_notations": list(EMS_FLOODED_NOTATIONS)}}


# ── Earth Engine references ─────────────────────────────────────────────

def _pixels(img, transform, shape, crs, label):
    from susceptibility.hydro_rasters import compute_pixels
    return compute_pixels(img, transform, shape, crs, label)


def _info(fn, label):
    import ee
    from ee_timeout import call
    ee.data.setDeadline(EE_TIMEOUT_S * 1000)
    return call(fn, timeout=EE_TIMEOUT_S, retries=2, label=label)


def jrc_occurrence(transform, shape, crs) -> np.ndarray:
    import ee
    occ = ee.Image(JRC_ASSET).select("occurrence").unmask(0)
    return _pixels(occ.rename("occ"), transform, shape, crs, "jrc")["occ"]


def not_permanent(occ: np.ndarray) -> np.ndarray:
    return np.isfinite(occ) & (occ < JRC_PERMANENT_WATER_OCCURRENCE_PCT)


def jrc_reference(transform, shape, crs) -> dict:
    occ = jrc_occurrence(transform, shape, crs)
    return {"flooded": occ >= JRC_SEASONAL_WATER_OCCURRENCE_PCT, "valid": not_permanent(occ),
            "block": 1, "occurrence": occ,
            "meta": {"source": f"{JRC_ASSET} occurrence, recurrent 5-80 %",
                     "resolution": "30 m", "dates": "1984-2021"}}


def s1_reference(bbox, event: str, window_days: int, transform, shape, crs) -> dict:
    import ee
    aoi = ee.Geometry.Rectangle(list(bbox))
    e = datetime.date.fromisoformat(event)
    col = (ee.ImageCollection(S1_COLLECTION).filterBounds(aoi)
           .filter(ee.Filter.eq("instrumentMode", S1_INSTRUMENT_MODE))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", S1_POLARIZATION))
           .select(S1_POLARIZATION))
    win = col.filterDate(e.isoformat(), (e + datetime.timedelta(days=window_days)).isoformat())
    ts = _info(lambda: win.aggregate_array("system:time_start").getInfo(), "s1 dates")
    d = pick_event_date(ts, event, window_days)
    if d is None:
        raise LookupError(f"no Sentinel-1 image in {event} + {window_days} d")
    ev = win.filterDate(d.isoformat(), (d + datetime.timedelta(days=1)).isoformat())
    orbits = _info(lambda: ev.aggregate_array("relativeOrbitNumber_start").distinct().getInfo(),
                   "s1 orbits")
    pre = (col.filterDate((e - datetime.timedelta(days=S1_PRE_EVENT_DAYS)).isoformat(), e.isoformat())
           .filter(ee.Filter.inList("relativeOrbitNumber_start", orbits)))
    n_pre, n_ev = _info(lambda: ee.List([pre.size(), ev.size()]).getInfo(), "s1 counts")
    if n_pre == 0:
        raise LookupError(f"no same-orbit pre-event Sentinel-1 image for orbits {orbits}")
    drop = ev.median().subtract(pre.median()).lte(S1_VV_DROP_THRESHOLD_DB)
    share = (drop.reproject(crs=crs, scale=10)
             .reduceResolution(ee.Reducer.mean(), maxPixels=64).rename("share"))
    share = _pixels(share, transform, shape, crs, "s1 share")["share"]
    occ = jrc_occurrence(transform, shape, crs)
    return {"flooded": share >= COVER_MIN, "valid": np.isfinite(share) & not_permanent(occ),
            "block": 1,
            "meta": {"source": f"{S1_COLLECTION} {S1_INSTRUMENT_MODE} {S1_POLARIZATION}, "
                               f"drop <= {S1_VV_DROP_THRESHOLD_DB} dB",
                     "resolution": "10 m -> 30 m", "event_window_days": window_days,
                     "event_image_date": d.isoformat(),
                     "days_after_event": (d - e).days, "event_images": n_ev,
                     "relative_orbits": orbits, "pre_event_images": n_pre}}


def gfd_reference(event_id: int, transform, shape, crs) -> dict:
    import ee
    img = ee.ImageCollection(GFD_ASSET).filter(ee.Filter.eq("id", event_id)).first()
    t0, t1 = _info(lambda: ee.List([ee.Date(img.get("system:time_start")).format("YYYY-MM-dd"),
                                    ee.Date(img.get("system:time_end")).format("YYYY-MM-dd")])
                   .getInfo(), "gfd dates")
    fl = _pixels(img.select("flooded").rename("flooded"), transform, shape, crs, "gfd")["flooded"]
    occ = jrc_occurrence(transform, shape, crs)
    return {"flooded": fl >= 0.5, "valid": np.isfinite(fl) & not_permanent(occ),
            "block": EVAL_BLOCK_GFD,
            "meta": {"source": f"{GFD_ASSET} id {event_id}", "resolution": "250 m MODIS",
                     "dates": f"{t0} to {t1}", "evaluation_block_m": EVAL_BLOCK_GFD * 30}}
