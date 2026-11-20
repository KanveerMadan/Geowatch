"""Dated, spatially matched observations for GeoWatch change history.

Each 100 m reporting cell has a fixed set of 20 m sample centres inside the
AOI. Its mean is admitted only when *every* one of those centres is observed.
A narrow clipped boundary cell can have no samples and remains unknown. The
sampling grid is a support convention, not a claim of sub-Landsat resolution.
The underlying native measurements, QA and effective dates remain distinct.

Public interface: open_history(layer, start, end).tiles(), dates [start, end).
Each tile holds cells and date records with aligned 1D float arrays. No full
AOI-by-time cube is allocated. EE requests and cache writes are sequential.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time
from zipfile import BadZipFile

import numpy as np

from vector.units import GRID_CELL_M

PRODUCT_VERSION = "fixed-support-v1"
CELL_M = int(GRID_CELL_M)
SAMPLE_M = 20            # common sample grid, aligned to 100 m reporting boundaries
TILE_CELLS = 48          # 4.8 km wide; ~35 MiB for 1000 dates, 3 signals + coverage
BATCH_DATES = 16         # < 1 MiB of float32 output for three signals plus coverage
DYNAMIC_WORLD_BANDS = ("water", "trees", "grass", "flooded_vegetation", "crops", "shrub_and_scrub",
                       "built", "bare", "snow_and_ice")
S2_LEVEL1C = "COPERNICUS/S2_HARMONIZED"
SOURCES = {
    "sentinel2": {
        "asset": "COPERNICUS/S2_SR_HARMONIZED", "signals": ("ndvi", "mndwi", "ndbi"),
        "lineage": "sentinel2", "resolution_m": 20,
        "quality": "SCL 4–6 only (vegetation, ground, water); all four bands required",
        "license": "Copernicus Sentinel Data Terms and Conditions",
    },
    "landsat8": {
        "asset": "LANDSAT/LC08/C02/T1_L2", "signals": ("ndvi", "mndwi", "ndbi"),
        "lineage": "landsat8", "resolution_m": 30,
        "quality": "Collection 2 Tier 1; QA_PIXEL fill, cloud, cirrus, shadow and snow excluded; QA_RADSAT clear",
        "license": "USGS public domain",
    },
    "landsat9": {
        "asset": "LANDSAT/LC09/C02/T1_L2", "signals": ("ndvi", "mndwi", "ndbi"),
        "lineage": "landsat9", "resolution_m": 30,
        "quality": "Collection 2 Tier 1; QA_PIXEL fill, cloud, cirrus, shadow and snow excluded; QA_RADSAT clear",
        "license": "USGS public domain",
    },
    "sentinel1": {
        "asset": "COPERNICUS/S1_GRD", "signals": ("vv_db", "vh_db"),
        "lineage": "sentinel1", "resolution_m": 20,
        "quality": "IW GRD dual VV/VH, 10 m posting, approximately 20 m resolution; native valid mask; "
                   "platform, pass and relative orbit held fixed. Terrain shadow/layover may remain",
        "license": "Copernicus Sentinel Data Terms and Conditions",
    },
    "dynamic_world": {
        "asset": "GOOGLE/DYNAMICWORLD/V1", "signals": tuple("dw_" + band for band in DYNAMIC_WORLD_BANDS),
        "lineage": "sentinel2", "resolution_m": 10, "context_only": True,
        "quality": "Dynamic World V1 single-acquisition class scores, with native cloud and shadow masks. "
                   "Every score must be present on the same sampled ground.",
        "license": "CC BY 4.0", "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "attribution": "This dataset is produced for the Dynamic World Project by Google in partnership "
                       "with National Geographic Society and the World Resources Institute. "
                       "Contains modified Copernicus Sentinel data.",
        "parent_asset": S2_LEVEL1C,
    },
    "open_buildings": {
        "asset": "GOOGLE/Research/open-buildings-temporal/v1", "signals": ("building_presence",),
        "lineage": "sentinel2", "resolution_m": 4,
        "quality": "annual uncalibrated confidence sampled at fixed centres; historical context only",
        "license": "CC BY 4.0, Google Research Open Buildings (derived from Copernicus Sentinel-2)",
    },
}
DEFAULT_SOURCES = tuple(key for key in SOURCES if key != "dynamic_world")
for _details in SOURCES.values():
    _details["url"] = "https://developers.google.com/earth-engine/datasets/catalog/" + _details["asset"].replace("/", "_")

_FIELDS = {
    "sentinel2": ["SENSING_ORBIT_NUMBER", "GENERATION_TIME", "PROCESSING_BASELINE", "GEOMETRIC_QUALITY"],
    "landsat8": ["WRS_PATH", "DATE_PRODUCT_GENERATED", "ALGORITHM_SOURCE_SURFACE_REFLECTANCE"],
    "landsat9": ["WRS_PATH", "DATE_PRODUCT_GENERATED", "ALGORITHM_SOURCE_SURFACE_REFLECTANCE"],
    "sentinel1": ["orbitProperties_pass", "relativeOrbitNumber_start", "platform_number"],
    "dynamic_world": ["SENSING_ORBIT_NUMBER", "GEOMETRIC_QUALITY", "PROCESSING_BASELINE",
                      "dynamicworld_algorithm_version", "qa_algorithm_version"],
    "open_buildings": ["inference_time_epoch_s", "imagery_start_time_epoch_s", "imagery_end_time_epoch_s"],
}


def _iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).date().isoformat()


def _groups(source, rows, start, end, *, errors=None):
    """A product split across scene boundaries is one acquisition, not independent evidence."""
    by = defaultdict(list)
    missing_orbits = 0
    for row in rows:
        timestamp = row["system:time_start"] / 1000
        if source == "open_buildings":
            # An inference target can precede imagery used to make it. Only make
            # this context visible after its last possible contributing image.
            timestamp = max(row["inference_time_epoch_s"], row["imagery_end_time_epoch_s"])
            track = "annual"
        elif source == "sentinel1":
            track = "IW:{}:{}:{}:VV/VH".format(row["platform_number"], row["orbitProperties_pass"],
                                                 row["relativeOrbitNumber_start"])
        elif source in ("sentinel2", "dynamic_world"):
            if source == "dynamic_world" and row.get("SENSING_ORBIT_NUMBER") is None:
                # linkCollection preserves unmatched granules with null metadata.
                missing_orbits += 1
                continue
            if str(row.get("GEOMETRIC_QUALITY", "")).upper() == "FAILED":
                continue
            track = f"MSI:{row['SENSING_ORBIT_NUMBER']}"
        else:
            track = f"OLI:{row['WRS_PATH']}"
        day = _iso(timestamp)
        if start <= day < end:
            by[(day, track)].append(row)

    if missing_orbits and errors is not None:
        errors.append(f"{missing_orbits} Dynamic World granules lack a matching Sentinel-2 orbit")
    observations = []
    spec = SOURCES[source]
    for (day, track), group in sorted(by.items()):
        rows_by_id = {r["system:index"]: r for r in group}
        scenes = [rows_by_id[i] for i in sorted(rows_by_id)]
        record = dict(date=day, track=track, source=source, lineage=spec["lineage"],
                      resolution_m=spec["resolution_m"], sample_spacing_m=SAMPLE_M,
                      asset=spec["asset"], quality=spec["quality"], scenes=scenes,
                      id=f"{source}/{track}/{day}")
        if source == "dynamic_world":
            record.update(context_only=True, parent_asset=S2_LEVEL1C,
                          attribution=spec["attribution"], license=spec["license"])
        if source == "open_buildings":
            record["inference_date"] = _iso(min(r["inference_time_epoch_s"] for r in scenes))
            record["imagery_interval"] = [_iso(min(r["imagery_start_time_epoch_s"] for r in scenes)),
                                          _iso(max(r["imagery_end_time_epoch_s"] for r in scenes))]
        observations.append(record)
    return observations


def _catalog(ee, source, bounds, start, end):
    from ee_timeout import call

    col = ee.ImageCollection(SOURCES[source]["asset"]).filterBounds(ee.Geometry.Rectangle(list(bounds)))
    if source == "open_buildings":
        # Its image timestamp is the target year, not when the inference's
        # imagery became observable. Use actual source metadata instead.
        def seconds(value):
            return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()
        # Availability is max(nominal target, last possible source image).
        lo, hi = seconds(start), seconds(end)
        col = (col.filter(ee.Filter.Or(ee.Filter.gte("imagery_end_time_epoch_s", lo),
                                       ee.Filter.gte("inference_time_epoch_s", lo)))
               .filter(ee.Filter.lt("imagery_end_time_epoch_s", hi))
               .filter(ee.Filter.lt("inference_time_epoch_s", hi)))
    else:
        col = col.filterDate(start, end)
    if source == "dynamic_world":
        # Dynamic World granule IDs match Sentinel-2 L1C. Copy metadata only.
        flights = ee.ImageCollection(S2_LEVEL1C).filterDate(start, end).filterBounds(
            ee.Geometry.Rectangle(list(bounds)))
        col = col.linkCollection(flights, linkedProperties=[
            "SENSING_ORBIT_NUMBER", "GEOMETRIC_QUALITY", "PROCESSING_BASELINE"],
            matchPropertyName="system:index")
    if source == "sentinel1":
        col = (col.filter(ee.Filter.eq("instrumentMode", "IW"))
               .filter(ee.Filter.eq("resolution_meters", 10))
               .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
               .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH")))
    fields = ["system:index", "system:time_start", "system:version", *_FIELDS[source]]
    rows = col.map(lambda image: image.set("_gw_row", image.toDictionary(fields))).aggregate_array("_gw_row")
    return call(rows.getInfo, retries=1, label=f"change inventory {source} {start}")


def _cached_catalog(source, bounds, start, end, cache, connect):
    # Keep recent inventories briefly: near-real-time collections backfill.
    # Per-calendar-year partitions and stable scene IDs reuse past pixels when
    # a later monitoring date is added. Expired metadata is labelled if used
    # during an outage, so coverage cannot silently look up to date.
    key = json.dumps([PRODUCT_VERSION, source, list(bounds), start, end])
    digest = hashlib.sha256(key.encode()).hexdigest()
    path = cache / "catalog" / (digest + ".json")
    cached = None
    try:
        cached = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - cached["retrieved_at"] < 24 * 3600:
            return cached["rows"], None
    except (OSError, KeyError, TypeError, ValueError):
        cached = None
    try:
        rows = _catalog(connect(), source, bounds, start, end)
    except Exception as exc:
        if cached is None:
            raise
        return cached["rows"], f"using stale inventory {start}..{end}: {str(exc)[:180]}"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     delete=False) as tmp:
        try:
            json.dump({"retrieved_at": time.time(), "rows": rows}, tmp)
            tmp.close()
            os.replace(tmp.name, path)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    return rows, None


def _optical_indices(reflectance):
    def ratio(a, b, name):
        x, y = reflectance.select(a), reflectance.select(b)
        denom = x.add(y)
        return x.subtract(y).divide(denom).updateMask(x.gte(0).And(y.gte(0)).And(denom.gt(0))).rename(name)
    return (ratio("nir", "red", "ndvi").addBands(ratio("green", "swir", "mndwi"))
            .addBands(ratio("swir", "nir", "ndbi")))


def _scene(ee, source, scene):
    image = ee.Image(f"{SOURCES[source]['asset']}/{scene['system:index']}")
    if source == "dynamic_world":
        # Select only class scores. EE preserves the published per-band QA masks.
        return image.select(list(DYNAMIC_WORLD_BANDS), list(SOURCES[source]["signals"]))
    if source == "sentinel2":
        scl = image.select("SCL")
        bands = image.select(["B3", "B4", "B8", "B11"], ["green", "red", "nir", "swir"])
        return _optical_indices(bands.updateMask(scl.gte(4).And(scl.lte(6))))
    if source.startswith("landsat"):
        qa = image.select("QA_PIXEL")
        clear = qa.bitwiseAnd(63).eq(0).And(image.select("QA_RADSAT").eq(0))
        bands = image.select(["SR_B3", "SR_B4", "SR_B5", "SR_B6"], ["green", "red", "nir", "swir"])
        return _optical_indices(bands.multiply(0.0000275).add(-0.2).updateMask(clear))
    if source == "sentinel1":
        # EE delivers log10 sigma0. Perform the spatial mean in linear
        # power, then convert back to dB at the reporting scale.
        db = image.select(["VV", "VH"], ["vv_db", "vh_db"])
        return ee.Image.constant(10).pow(db.divide(10)).rename(["vv_db", "vh_db"])
    return image.select("building_presence")


def _crs_transform(spacing):
    return [spacing, 0, 0, 0, -spacing, 0]


def _block_pixels(ee, layer, tile, records):
    from ee_timeout import call
    from shapely.geometry import mapping

    source = records[0]["source"]
    signals = SOURCES[source]["signals"]
    crs = layer.crs.to_string()
    fine = {"crs": crs, "crsTransform": _crs_transform(SAMPLE_M)}
    geom = ee.Geometry(mapping(layer.aoi), proj=crs, geodesic=False)
    inside = ee.Image.constant(1).reproject(**fine).clip(geom).unmask(0, False)
    n_samples = (CELL_M // SAMPLE_M) ** 2
    def mean(image):
        return image.reproject(**fine).reduceResolution(ee.Reducer.mean(), maxPixels=n_samples * 4)
    footprint = mean(inside)
    images = []
    for i, record in enumerate(records):
        # Resolve overlapping tiles deterministically on a single acquisition
        # date and geometry. Require the same optical samples in all indices.
        scenes = []
        for part in record["scenes"]:
            sample = _scene(ee, source, part).reproject(**fine)
            scenes.append(sample.updateMask(sample.mask().reduce(ee.Reducer.min())))
        mosaic = ee.ImageCollection.fromImages(scenes).mosaic().reproject(**fine)
        valid = mosaic.mask().reduce(ee.Reducer.min()).unmask(0, False).gt(0).multiply(inside)
        coverage = mean(valid).divide(footprint).updateMask(footprint.gt(0))
        values = mean(mosaic.updateMask(inside))
        if source == "sentinel1":
            values = values.log10().multiply(10)
        bands = values.addBands(coverage.rename("coverage")).rename(
            [f"r{i}_{s}" for s in (*signals, "coverage")])
        images.append(bands)
    # An explicit sentinel is necessary: computePixels returns zeros for
    # masked pixels in ndarray format, and a real water index can be zero.
    result = ee.Image.cat(images).unmask(-9999, False).toFloat()
    x, y, w, h = tile["grid"]
    grid = {"dimensions": {"width": w, "height": h}, "crsCode": crs,
            "affineTransform": {"scaleX": CELL_M, "scaleY": -CELL_M,
                                "translateX": x, "translateY": y, "shearX": 0, "shearY": 0}}
    arr = call(lambda: ee.data.computePixels({"expression": result, "fileFormat": "NUMPY_NDARRAY",
                                              "grid": grid}), retries=1, label=f"change {source} {records[0]['date']}")
    rows = tile["indices"]
    cube = np.empty((len(records), len(signals) + 1, len(rows)), dtype="float32")
    for i in range(len(records)):
        for j, name in enumerate((*signals, "coverage")):
            cube[i, j] = arr[f"r{i}_{name}"].ravel()[rows]
    cube[cube == -9999] = np.nan
    return cube


def _sanitise(cube):
    # For 25 equally weighted samples, one missing centre reduces coverage
    # by at least 1/25. Tolerance here only accommodates float32 arithmetic.
    coverage = np.nan_to_num(cube[:, -1, :], nan=0).clip(0, 1)
    cube[:, -1, :] = coverage
    cube[:, :-1, :] = np.where(coverage[:, None, :] >= 1 - 1e-6, cube[:, :-1, :], np.nan)
    return cube


def _cached_block(ee, layer, tile, records, cache):
    version = [PRODUCT_VERSION, layer.crs.to_string(), layer.aoi.wkb_hex, tile["grid"], records]
    key = hashlib.sha256(json.dumps(version, sort_keys=True).encode()).hexdigest()
    path = cache / key[:2] / (key + ".npz")
    shape = (len(records), 1 + len(SOURCES[records[0]["source"]]["signals"]), len(tile["indices"]))
    try:
        with np.load(path, allow_pickle=False) as archive:
            cube = archive["values"]
        if cube.shape == shape and cube.dtype == np.float32:
            return cube
    except (OSError, ValueError, EOFError, KeyError, BadZipFile):
        pass
    cube = _sanitise(_block_pixels(ee() if callable(ee) else ee, layer, tile, records))
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".npz", delete=False) as tmp:
        try:
            np.savez_compressed(tmp, values=cube)
            tmp.close()
            os.replace(tmp.name, path)
        finally:
            Path(tmp.name).unlink(missing_ok=True)
    return cube


def _spatial_tiles(layer):
    from pyproj import Transformer
    from shapely.geometry import box, mapping
    from shapely.ops import transform

    to_ll = Transformer.from_crs(layer.crs, "EPSG:4326", always_xy=True).transform
    west, south, east, north = layer.aoi.bounds
    x0 = math.floor(west / CELL_M) * CELL_M
    y0 = math.ceil(north / CELL_M) * CELL_M
    rows = math.ceil((y0 - south) / CELL_M)
    cols = math.ceil((east - x0) / CELL_M)
    code = layer.crs.to_string()
    unit_index = 0
    for row in range(0, rows, TILE_CELLS):
        for col in range(0, cols, TILE_CELLS):
            height, width = min(TILE_CELLS, rows - row), min(TILE_CELLS, cols - col)
            left, top = x0 + col * CELL_M, y0 - row * CELL_M
            cells, indices = [], []
            for r in range(height):
                for c in range(width):
                    x, y = left + CELL_M*c, top - CELL_M*r
                    square = box(x, y - CELL_M, x + CELL_M, y)
                    polygon = layer.aoi.intersection(square)
                    if polygon.is_empty or polygon.area <= 0:
                        continue
                    cell_id = f"{code}/{x}/{y}"
                    # Two partly overlapping queries share a cell ID, but can
                    # compare measurements only if their clipped areas match.
                    support = (cell_id if polygon.equals(square) else
                               cell_id + "/" + hashlib.sha256(polygon.normalize().wkb).hexdigest()[:16])
                    cells.append({"unit_index": unit_index, "cell_id": cell_id, "support_id": support,
                                  "geometry": mapping(transform(to_ll, polygon)), "area_m2": float(polygon.area)})
                    indices.append(r * width + c)
                    unit_index += 1
            if cells:
                yield {"cells": cells, "grid": (left, top, width, height), "indices": indices}


def _calendar_years(start, end):
    cursor, finish = date.fromisoformat(start), date.fromisoformat(end)
    while cursor < finish:
        stop = min(finish, date(cursor.year + 1, 1, 1))
        yield cursor.isoformat(), stop.isoformat()
        cursor = stop


@dataclass
class ObservationHistory:
    layer: object
    start: str
    end: str
    cache: Path
    sources: tuple
    cancelled: object

    def _check(self):
        if self.cancelled is not None and self.cancelled():
            raise TimeoutError("change observation history cancelled")

    def tiles(self):
        import ee
        self._check()
        init_error = None
        def connect():
            nonlocal init_error
            if init_error is not None:
                raise init_error
            if not ee.data.is_initialized():
                from ingestion.gee_client import initialize_gee
                try:
                    initialize_gee()
                except Exception as exc:
                    init_error = exc
                    raise
            return ee
        catalogs, failures = {}, {}
        for source in self.sources:
            rows, errors = [], []
            for first, last in _calendar_years(self.start, self.end):
                self._check()
                try:
                    images, stale = _cached_catalog(source, self.layer.bbox, first, last, self.cache, connect)
                    rows.extend(images)
                    if stale:
                        errors.append(stale)
                except Exception as exc:
                    errors.append(f"catalog {first}..{last}: {str(exc)[:240]}")
            try:
                catalogs[source] = _groups(source, rows, self.start, self.end, errors=errors)
            except (KeyError, TypeError, ValueError) as exc:
                catalogs[source] = []
                errors.append(f"incomplete acquisition metadata: {str(exc)[:200]}")
            failures[source] = errors

        for tile in _spatial_tiles(self.layer):
            observations, diagnostics = [], []
            for source, catalog in catalogs.items():
                errors = list(failures[source])
                usable = fetched = 0
                # Calendar boundaries insulate older cached batches from late
                # arrivals and moving start/end windows.
                months = defaultdict(list)
                for record in catalog:
                    months[record["date"][:7]].append(record)
                for month in months.values():
                    for offset in range(0, len(month), BATCH_DATES):
                        self._check()
                        batch = month[offset:offset + BATCH_DATES]
                        try:
                            cube = _cached_block(connect, self.layer, tile, batch, self.cache)
                        except Exception as exc:
                            errors.append(f"pixels {batch[0]['date']}..{batch[-1]['date']}: {str(exc)[:240]}")
                            continue
                        fetched += len(batch)
                        for record, values in zip(batch, cube):
                            if np.isfinite(values[0]).any():
                                usable += 1
                            observations.append({**record, "coverage": values[-1],
                                                 "values": dict(zip(SOURCES[source]["signals"], values[:-1]))})
                if errors:
                    status = "partial" if fetched else "failed"
                else:
                    status = "available" if catalog else "no_acquisitions"
                diagnostics.append({"source": source, "status": status, "acquisitions": len(catalog),
                                    "usable_acquisitions": usable, "fetched_acquisitions": fetched, "errors": errors})
            observations.sort(key=lambda o: (o["date"], o["source"], o["track"]))
            yield {"cells": tile["cells"], "observations": observations, "diagnostics": diagnostics}


def open_history(layer, start: str, end: str, *, cache_dir=None, sources=None, cancelled=None):
    """Prepare a history on a stable UTM grid. End is exclusive; EE is lazy until iteration."""
    if date.fromisoformat(start) >= date.fromisoformat(end):
        raise ValueError("history requires start < end")
    selected = DEFAULT_SOURCES if sources is None else tuple(dict.fromkeys(sources))
    if not selected or set(selected).difference(SOURCES):
        raise ValueError("choose at least one recognized change observation source")
    root = cache_dir or os.getenv("GEOWATCH_CHANGE_CACHE") or "~/.cache/geowatch/change-history"
    return ObservationHistory(layer, start, end, Path(root).expanduser(), selected, cancelled)
