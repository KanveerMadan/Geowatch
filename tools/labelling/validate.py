"""Read-only Item 21 topology, branch-rule and provenance audit."""
import argparse
from collections import defaultdict
from dataclasses import fields
import json
import math
from pathlib import Path
import sys
import sqlite3
from tempfile import TemporaryDirectory

import pyogrio
from shapely import union_all
from shapely.geometry import box, mapping
from shapely.validation import explain_validity

from labelling.common import load_config
from labelling.fractions import LabelQCError, parse_features, tile_fractions
from labelling.records import RecordError, TileRecord
from labelling.tiles import tile_grid
from .guard import authorize_tile, load

ORIGINS = ("hand_drawn", "prelabel_kept", "prelabel_edited", "unknown")
SOURCE_FIELDS = ("source", "source_id", "source_version", "candidate_id")


def text(value):
    if value is None or isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def load_candidates(tile):
    path = tile.path / "prelabels.gpkg"
    index = {}
    if path.exists():
        for layer, kind in pyogrio.list_layers(path):
            if kind is None:
                continue
            gdf = pyogrio.read_dataframe(path, layer=layer)
            if gdf.crs is None or gdf.crs.to_string() != tile.crs:
                raise ValueError(f"Different suggestion CRS in {layer}")
            if "candidate_id" not in gdf:
                continue
            for row in gdf.to_dict("records"):
                key = text(row["candidate_id"])
                if not key or key in index:
                    raise ValueError(f"Missing or duplicate suggestion ID in {layer}")
                index[key] = row
    return index


def shares(tally):
    total_count = sum(v[0] for v in tally.values())
    total_area = sum(v[1] for v in tally.values())
    summary = {}
    for origin in ORIGINS:
        count, area = tally.get(origin, (0, 0))
        summary[origin] = dict(polygons=count, area_m2=area,
                              polygon_share=count/total_count if total_count else None,
                              area_share=area/total_area if total_area else None)
    return summary


def inspect_labels(table, tile, candidates, cfg):
    errors, warnings, features, geometries = [], [], [], []
    by_class = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    total = defaultdict(lambda: [0, 0.0])
    used_ids = set()
    boundary = box(*tile.bounds)
    for fid, row in zip(table.index, table.to_dict("records")):
        label = text(row.get("label")) or "missing_label"
        origin = text(row.get("provenance"))
        if origin not in ORIGINS[:-1]:
            origin = "unknown"
            errors.append(f"{fid}: missing or invalid provenance; review manually")
        geom = row["geometry"]
        good = geom is not None and not geom.is_empty and geom.is_valid and geom.geom_type in ("Polygon","MultiPolygon")
        area = 0.0
        if good:
            cut = geom.intersection(boundary)
            geometries.append(cut)
            area = cut.area
            if geom.difference(boundary).area > 1e-6:
                errors.append(f"{fid}: label extends outside the registered tile")
            feature = {"type":"Feature", "geometry":mapping(geom), "properties":row}
            try:
                parse_features([feature], cfg)
                features.append(feature)
            except LabelQCError as exc:
                errors.append(f"{fid}: {exc}")
        else:
            reason = explain_validity(geom) if geom is not None else "missing"
            errors.append(f"{fid}: empty, invalid or non-polygon geometry ({reason})")
        for tally in (total[origin], by_class[label][origin]):
            tally[0] += 1
            tally[1] += area
        tags = {k:text(row.get(k)) for k in SOURCE_FIELDS}
        key = tags["candidate_id"]
        if origin == "hand_drawn":
            if key or tags["source_id"]:
                errors.append(f"{fid}: hand-drawn polygon has an upstream suggestion ID")
        elif origin in ("prelabel_kept","prelabel_edited"):
            source = candidates.get(key)
            if not all(tags.values()) or source is None:
                errors.append(f"{fid}: missing source, version or matching suggestion")
                continue
            if key in used_ids and origin == "prelabel_kept":
                errors.append(f"{fid}: duplicate unchanged copy of {key}")
            used_ids.add(key)
            if text(source.get("hint_only")).lower() not in ("0","false"):
                errors.append(f"{fid}: a display-only hint cannot be accepted")
            if any(tags[k] != text(source.get(k)) for k in SOURCE_FIELDS):
                errors.append(f"{fid}: source fields differ from {key}")
            if origin == "prelabel_kept" and good and (label != source["class"] or not geom.equals(source["geometry"])):
                errors.append(f"{fid}: geometry or class differs from {key}; review edited provenance")
    covered = union_all(geometries)
    gap = boundary.difference(covered).area
    overlap = max(0.0, sum(g.area for g in geometries) - covered.area)
    # One square millimetre suppresses floating-point overlay residue on projected coordinates.
    if gap > 1e-6 or overlap > 1e-6:
        errors.append(f"Tile has {gap:.6f} m² uncovered and {overlap:.6f} m² excess overlapping area")
    per_class = {k:shares(by_class[k]) for k in dict.fromkeys([*cfg['labels']['scored'],*cfg['labels']['excluded'],*by_class])}
    kept = per_class["built"]["prelabel_kept"]
    if max(kept["area_share"] or 0, kept["polygon_share"] or 0) > .5:
        warnings.append("A majority of built area or polygons was kept unchanged from suggestions; inspect independently against the imagery.")
    result = None
    if len(features) == len(table):
        grid = tile_grid(tile.crs, tile.bounds[0], tile.bounds[3], tile.bounds[2]-tile.bounds[0])
        try:
            f = tile_fractions(features, grid, cfg, cfg["open"]["max_excluded_share_per_cell"]["value"])
            result = {k:float(f[k]) for k in ("pct_unsure","pct_shadow_full")}
            result.update(scored_cells=int(f["scored"].sum()), total_cells=f["scored"].size)
        except LabelQCError as exc:
            errors.append(str(exc))
    return dict(errors=errors, warnings=warnings, tile=tile.tile_id, polygons=len(table),
                uncovered_m2=gap, overlap_excess_m2=overlap, provenance=shares(total),
                by_class=per_class, fractions=result)


def sun_record(tile, meta, cfg):
    """Run the branch's shadow-line resolver against a consistent private copy."""
    from labelling.sun_geometry import run
    with TemporaryDirectory(prefix="item21-qc-") as directory:
        scratch = Path(directory)
        (scratch/"metadata.json").write_text(json.dumps(meta))
        with sqlite3.connect((tile.path/"sun.gpkg").as_uri()+"?mode=ro", uri=True) as source:
            with sqlite3.connect(scratch/"sun.gpkg") as dest:
                source.backup(dest)
        run(str(scratch), cfg)
        return load(scratch/"metadata.json")


def audit(tile_dir):
    tile = authorize_tile(tile_dir)
    table = pyogrio.read_dataframe(tile.path/"labels.gpkg", layer="labels", fid_as_index=True)
    if table.crs is None or table.crs.to_string() != tile.crs:
        raise ValueError("Label CRS differs from the registered image")
    cfg = load_config()
    report = inspect_labels(table, tile, load_candidates(tile), cfg)
    if tile.city != "practice":
        meta = load(tile.path/"metadata.json")
        if meta.get("sun_geometry_required") and (tile.path/"sun.gpkg").is_file():
            try:
                meta = sun_record(tile, meta, cfg)
                report["measured_sun"] = {k:meta[k] for k in TileRecord.SUN_FIELDS}
            except (ValueError, RuntimeError) as exc:
                report["errors"].append(f"Sun measurements: {exc}")
        args = {f.name:meta.get(f.name) for f in fields(TileRecord)}
        if report["fractions"]:
            args.update({k:report["fractions"][k] for k in ("pct_unsure","pct_shadow_full")})
        try:
            TileRecord(**args).validate(cfg)
        except (RecordError, ValueError) as exc:
            report["errors"].append(str(exc))
        if str(meta.get("change_test_result","")).lower().startswith("dropped"):
            report["errors"].append("Tile was dropped by the frozen change test")
    report["ok"] = not report["errors"]
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tile_dir",type=Path)
    args=parser.parse_args(argv)
    try:
        report=audit(args.tile_dir)
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as exc:
        print(json.dumps({"ok":False, "errors":[str(exc)]}))
        return 2
    print(json.dumps(report,indent=2,allow_nan=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
