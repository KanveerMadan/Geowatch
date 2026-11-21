"""Prepare INPE references; seal and run the Amazon clearing study in AMAZON_PROTOCOL.md."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
from functools import lru_cache
import hashlib
import json
from pathlib import Path
from statistics import median
from types import SimpleNamespace

from pyproj import CRS, Transformer
from shapely.geometry import box, shape
from shapely.ops import transform, unary_union

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REGISTRY = HERE / "amazon_clearing_registry.csv"
LOCK = HERE / "amazon_clearing_lock.json"
RESULT = HERE / "amazon_clearing_result.json"
URL = "https://terrabrasilis.dpi.inpe.br/geoserver/deter-amz/wfs"
PARAMS = {"service": "WFS", "version": "2.0.0", "request": "GetFeature",
          "typeNames": "deter-amz:deter_amz", "outputFormat": "application/json",
          "srsName": "EPSG:4326", "CQL_FILTER": "classname='DESMATAMENTO_CR' AND "
          "view_date >= '2024-07-01' AND view_date < '2024-08-01'"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache(maxsize=64)
def projector(epsg):
    return Transformer.from_crs(4326, epsg, always_xy=True).transform


def register(feature):
    p = feature["properties"]
    if (p["classname"] != "DESMATAMENTO_CR" or not p["view_date"].startswith("2024-07-")
            or p["satellite"] not in {"AMAZONIA-1", "CBERS-4", "CBERS-4A"}
            or p["sensor"] not in {"WFI", "AWFI"}):
        return None
    geom = shape(feature["geometry"])
    lon, lat = geom.centroid.coords[0]
    epsg = (32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1
    geom = transform(projector(epsg), geom)
    if not geom.is_valid:
        return None
    interior = geom.buffer(-100)
    if interior.is_empty:
        return None
    px, py = interior.representative_point().coords[0]
    x, y = int(px // 100) * 100, int(py // 100) * 100
    if not geom.covers(box(x, y, x + 100, y + 100).buffer(32)):
        return None
    return dict(notice=feature["id"], state=p["uf"], municipality=p["municipality"],
                satellite=p["satellite"], sensor=p["sensor"], date=p["view_date"],
                epsg=epsg, x=x, y=y, area_m2=round(geom.area),
                block=f"{epsg}/{x // 4800}/{y // 4800}")


def prepare(raw):
    if LOCK.exists() or REGISTRY.exists():
        raise FileExistsError("the registered cohort already exists")
    data = json.loads(raw.read_text())
    features = data["features"]
    if len(features) != int(data["numberMatched"]):
        raise ValueError("incomplete WFS download")
    eligible = [row for f in features if (row := register(f)) is not None]
    counts = Counter((r["epsg"], r["x"], r["y"]) for r in eligible)
    rows = [r for r in eligible if counts[r["epsg"], r["x"], r["y"]] == 1]
    frequencies = Counter((r["state"], r["block"]) for r in rows)
    best = {}
    for (state, block), count in sorted(frequencies.items(), key=lambda it: (-it[1], it[0])):
        best.setdefault(state, (state, block, count))
    selected = sorted(best.values(), key=lambda tup: (-tup[2], tup[:2]))[:3]
    blocks = {(s, b) for s, b, n in selected}
    with REGISTRY.open("x", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=[*rows[0], "split"], lineterminator="\n")
        writer.writeheader()
        for r in sorted(rows, key=lambda r: r["notice"]):
            split = "test" if (r["state"], r["block"]) in blocks else "reference_only"
            writer.writerow({**r, "split": split})
    files = [REGISTRY, HERE / "AMAZON_PROTOCOL.md", Path(__file__).resolve(),
             ROOT / "vector/change_detection.py", ROOT / "vector/change_observations.py"]
    lock = {"source": URL, "parameters": PARAMS, "response_timestamp": data["timeStamp"],
            "source_sha256": digest(raw), "raw_notices": len(features), "eligible": len(rows),
            "selected": selected, "sha256": {str(p.relative_to(ROOT)): digest(p) for p in files}}
    with LOCK.open("x") as f:
        json.dump(lock, f, indent=2)
    print(selected, flush=True)


def load_locked():
    manifest = json.loads(LOCK.read_text())
    for name, expected in manifest["sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"locked file changed: {name}")
    with REGISTRY.open() as f:
        return [r for r in csv.DictReader(f) if r["split"] == "test"]


def run_state(cache, state):
    from vector.change_observations import open_history
    from vector.change_detection import detect_cell
    from analysis.change_history import _tile_arrays, _observations
    group = [r for r in load_locked() if r["state"] == state]
    if not group:
        raise ValueError("state is outside the sealed test")
    crs = CRS.from_epsg(int(group[0]["epsg"]))
    lookup, squares = {}, []
    for r in group:
        x, y = int(r["x"]), int(r["y"])
        lookup[f"{crs.to_string()}/{x}/{y + 100}"] = r
        squares.append(box(x, y, x+100, y+100))
    area = unary_union(squares)
    inverse = Transformer.from_crs(crs, 4326, always_xy=True).transform
    layer = SimpleNamespace(aoi=area, crs=crs, bbox=transform(inverse, area).bounds)
    reports = []
    for tile in open_history(layer, "2019-06-01", "2024-09-01", cache_dir=cache / "source",
                             sources=["sentinel2"]).tiles():
        if any(d["errors"] for d in tile["diagnostics"]):
            raise RuntimeError(str(tile["diagnostics"]))
        obs = tile["observations"]
        arrays = _tile_arrays(obs, 0, len(tile["cells"]))
        meta = [{k:v for k,v in r.items() if k not in ("coverage", "values")} for r in obs]
        for i, cell in enumerate(tile["cells"]):
            r = lookup[cell["cell_id"]]
            rows = _observations(meta, arrays, i, cell["support_id"])
            d = detect_cell(cell["cell_id"], rows, start="2024-06-01", end="2024-09-01")
            hits = sorted({e["confirmed_on"] for e in d["events"] if
                           e["transition"] == "greenness_loss" and e.get("confirmed_on")})
            dates = sorted({o["date"] for o in rows if o["date"] >= r["date"] and "ndvi" in o["values"]})
            observed = any(s["signal"] == "ndvi" and s["status"] == "observed" for s in d["series"])
            reports.append({"notice": r["notice"], "state": state, "date": r["date"],
                            "cell_id": cell["cell_id"], "confirmed": hits[0] if hits else None,
                            "full_ndvi_window": observed, "next_usable": dates[0] if dates else None})
    if len(reports) != len(group):
        raise RuntimeError("missing registered cells")
    payload = {"lock": digest(LOCK), "cells": reports}
    target = cache / f"{state}.json"
    with target.open("x") as f:
        json.dump(payload, f)
    print(state, len(reports), flush=True)


def combine(cache):
    rows = load_locked()
    cells = []
    for state in sorted({r["state"] for r in rows}):
        part = json.loads((cache / f"{state}.json").read_text())
        if part["lock"] != digest(LOCK):
            raise ValueError("mismatched run")
        cells.extend(part["cells"])
    if Counter(c["notice"] for c in cells) != Counter(r["notice"] for r in rows):
        raise ValueError("expected exactly the registered notices")
    hit = [c for c in cells if c["confirmed"]]
    misses = sum(not c["confirmed"] and c["full_ndvi_window"] for c in cells)
    def lag(c, field):
        return (date.fromisoformat(c[field]) - date.fromisoformat(c["date"])).days
    summary = dict(registered=len(rows), positive=len(hit), fully_observed_negative=misses,
                   unresolved=len(rows)-len(hit)-misses,
                   signed_median_days_from_notice_to_confirmation=median(lag(c,"confirmed") for c in hit) if hit else None)
    with RESULT.open("x") as f:
        json.dump(dict(lock=digest(LOCK), summary=summary, cells=cells), f, indent=1)
    print(summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run", "combine"])
    parser.add_argument("path", type=Path, help="raw WFS response for prepare, cache directory otherwise")
    parser.add_argument("--state")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.path)
    elif args.command == "run":
        run_state(args.path, args.state)
    else:
        combine(args.path)
