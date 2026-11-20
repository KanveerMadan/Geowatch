"""Import a bounded, independently mapped SpaceNet 7 building survey pair.

python -m experiments.change_history.spacenet_survey /path/to/working-directory

The fixed experiment uses the first (lexically sorted) public training site
and its first and last monthly mosaics. Only six named files are fetched.
"""
import argparse
import calendar
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
import urllib.request

import numpy as np
from pyproj import CRS, Transformer
import rasterio
from rasterio.enums import ColorInterp
from rasterio.features import shapes
from shapely.geometry import box, mapping, shape
from shapely.ops import transform, unary_union

from analysis.change_surveys import SurveyPairs

SITE = "L15-0331E-1257N_1327_3160_13"
BASE = f"https://spacenet-dataset.s3.amazonaws.com/spacenet/SN7_buildings/train/{SITE}"
MONTHS = ("2018_01", "2020_01")
LICENSE = "CC BY-SA 4.0, SpaceNet Partners"
SOURCE = "SpaceNet 7 Multi-Temporal Urban Development, SpaceNet Partners, Planet monthly mosaics"
MIB = 1024 ** 2
DIGESTS = {
    "2018_01": {
        "image": "4b88562fc2f5142de42876b0a86c208eca9e41a346ee054a7022e28dd699ea64",
        "buildings": "4a6faccde45deaafefbcca84cdb65898071e215093698dbeb717cf2a7bc6ef0e",
        "unusable": "57637baf82c3fd2638c3f55889f45a17a5a20115cf8644b0c7a3cf03f23a9e11",
    },
    "2020_01": {
        "image": "7b031beda25df02767621cb02447a69a4136a2b5f79a7f21c4a51a8d998dcbfb",
        "buildings": "fd67920a79cc61c78042a36dc9bd51d592f6398fe369a2e4161efecf77e14ebb",
        "unusable": "57637baf82c3fd2638c3f55889f45a17a5a20115cf8644b0c7a3cf03f23a9e11",
    },
}


def month_interval(month):
    y, m = map(int, month.split("_"))
    return [date(y, m, 1).isoformat(), date(y, m, calendar.monthrange(y, m)[1]).isoformat()]


def _assets(month):
    stem = f"global_monthly_{month}_mosaic_{SITE}"
    return {"image": f"images_masked/{stem}.tif",
            "buildings": f"labels/{stem}_Buildings.geojson",
            "unusable": f"labels/{stem}_UDM.geojson"}


def _sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _fetch(key, digest, cache, deadline):
    target = cache / key
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and _sha(target) == digest:
        return target
    # The catalogue lists each RGB-alpha mosaic under 4.1 MiB and each vector
    # file under 1 MiB. Limit bytes actually read even if length is omitted.
    cap = 5 * MIB if key.endswith(".tif") else MIB
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as tmp:
        partial = Path(tmp.name)
    try:
        with urllib.request.urlopen(BASE + "/" + key, timeout=20) as src, partial.open("wb") as dest:
            written = 0
            while data := src.read(128 * 1024):
                written += len(data)
                if written > cap or time.monotonic() > deadline:
                    raise RuntimeError("SpaceNet download exceeds the bounded size or time limit")
                dest.write(data)
        if _sha(partial) != digest:
            raise ValueError(f"unexpected contents for pinned SpaceNet source {key}")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)
    return target


def _reproject(geom, origin, target):
    return transform(Transformer.from_crs(origin, target, always_xy=True).transform, geom)


def _read_polygons(path, target):
    data = json.loads(path.read_text())
    if data["type"] != "FeatureCollection":
        raise ValueError("expected GeoJSON features from SpaceNet")
    crs = CRS.from_user_input(data.get("crs", {}).get("properties", {}).get("name", "EPSG:4326"))
    polygons = []
    for feature in data["features"]:
        geom = shape(feature["geometry"])
        if geom.is_empty or geom.geom_type not in {"Polygon", "MultiPolygon"} or not geom.is_valid:
            raise ValueError("invalid SpaceNet label geometry")
        polygons.append(geom)
    return _reproject(unary_union(polygons), crs, target)


def _polygon_parts(geometry):
    if geometry.geom_type == "Polygon" and not geometry.is_empty:
        yield geometry
    elif geometry.geom_type in ("MultiPolygon", "GeometryCollection"):
        for part in geometry.geoms:
            yield from _polygon_parts(part)


def epoch_features(files):
    with rasterio.open(files["image"]) as image:
        if image.crs is None or ColorInterp.alpha not in image.colorinterp:
            raise ValueError("a georeferenced masked alpha band is required to identify surveyed coverage")
        alpha = image.read(image.colorinterp.index(ColorInterp.alpha) + 1)
        full_bounds = box(*image.bounds)
        valid = alpha > 0
        polys = [shape(g) for g, _ in shapes(valid.astype("uint8"), mask=valid, transform=image.transform)]
        crs = image.crs
    coverage = unary_union(polys).difference(_read_polygons(files["unusable"], crs))
    if coverage.is_empty:
        return None, _reproject(full_bounds, crs, "EPSG:4326")
    buildings = _read_polygons(files["buildings"], crs).intersection(coverage)
    features = []
    for role, geom in (("coverage", coverage), ("surface", buildings)):
        ll = _reproject(geom, crs, "EPSG:4326")
        for poly in _polygon_parts(ll):
            features.append({"type": "Feature", "properties": {"role": role}, "geometry": mapping(poly)})
    return {"type": "FeatureCollection", "features": features}, _reproject(full_bounds, crs, "EPSG:4326")


def _save(path, obj):
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as tmp:
        partial = Path(tmp.name)
        try:
            json.dump(obj, tmp, allow_nan=False, separators=(",", ":"))
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
    partial.replace(path)


def run(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(root).free < 15 * 1024**3:
        raise RuntimeError("less than 15 GiB free; skipping SpaceNet downloads")
    deadline = time.monotonic() + 120
    row = dict(name="surveyed_buildings", source=SOURCE, license=LICENSE)
    areas, sources = [], []
    for key, month in zip(("before", "after"), MONTHS):
        keys = _assets(month)
        files = {name: _fetch(remote, DIGESTS[month][name], root / "raw", deadline)
                 for name, remote in keys.items()}
        sources.extend({"url": f"{BASE}/{keys[name]}", "bytes": p.stat().st_size, "sha256": _sha(p)}
                       for name, p in files.items())
        features, area = epoch_features(files)
        if features is None:
            return {"state": "insufficient_observation", "month": month}
        out = root / f"survey_{month}.geojson"
        _save(out, features)
        row[key] = {"interval": month_interval(month), "file": out.name}
        areas.append(area)
    manifest = root / "survey_manifest.json"
    _save(manifest, [row])
    pair = SurveyPairs(manifest)
    full = unary_union(areas)
    centroid = full.centroid
    utm = (32600 if centroid.y >= 0 else 32700) + int((centroid.x + 180) // 6) + 1
    crs = f"EPSG:{utm}"
    start, stop = month_interval(MONTHS[0])[0], month_interval(MONTHS[1])[1]
    end = (date.fromisoformat(stop) + timedelta(days=1)).isoformat()
    stats = pair.measure(mapping(full), crs, start, end)
    w, s, e, n = full.bounds
    outside = box(e + (e-w), s, e + 2*(e-w), n)
    result = {"state": "measured" if stats else "insufficient_observation", "site": SITE,
              "selection": "first training site, first and last available months",
              "license": LICENSE, "sources": sources, "bounds_wgs84": list(full.bounds),
              "projected_crs": crs, "image_footprint_union_m2": _reproject(full, "EPSG:4326", crs).area,
              "measurements": stats, "outside_coverage": pair.measure(mapping(outside), crs, start, end),
              "manifest": manifest.name}
    _save(root / "result.json", result)
    return result


if __name__ == "__main__":
    arg = argparse.ArgumentParser(description=__doc__)
    arg.add_argument("destination", type=Path)
    print(json.dumps(run(arg.parse_args().destination), indent=2))
