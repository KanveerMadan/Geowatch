"""Run and inspect GeoWatch change histories without starting an analysis job."""

import argparse
import ctypes
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from types import SimpleNamespace


def _area(bounds):
    from pyproj import Geod, Transformer
    from shapely.geometry import box
    from shapely.ops import transform
    from vector.roads import utm_crs_for

    west, south, east, north = bounds
    if not (-180 <= west < east <= 180 and east - west < 180 and -80 <= south < north <= 84):
        raise ValueError("select an ordered WGS84 box inside the local UTM domain (80°S to 84°N)")
    polygon = box(*bounds)
    area, _ = Geod(ellps="WGS84").geometry_area_perimeter(polygon)
    # Match the GeoWatch API's 100 km² AOI limit without importing the web service.
    if abs(area) > 100 * 1_000_000:
        raise ValueError("select an area of at most 100 km²")
    crs = utm_crs_for(bounds)
    project = Transformer.from_crs("EPSG:4326", crs, always_xy=True).transform
    return SimpleNamespace(bbox=tuple(bounds), crs=crs, aoi=transform(project, polygon))


def _publish_directory(staging, destination):
    """Atomic no-replace on the Mac and Linux filesystems used by GeoWatch."""
    if os.name == "nt":
        os.rename(staging, destination)  # Windows refuses existing destinations
        return
    libc = ctypes.CDLL(None, use_errno=True)
    paths = os.fsencode(staging), os.fsencode(destination)
    if sys.platform == "darwin":
        rc = libc.renamex_np(*paths, 4)  # RENAME_EXCL (Darwin stdio.h)
    elif sys.platform.startswith("linux"):
        rc = libc.renameat2(-100, paths[0], -100, paths[1], 1)  # AT_FDCWD, RENAME_NOREPLACE
    else:
        raise RuntimeError("this platform lacks a supported exclusive directory rename")
    if rc:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), str(destination))


def _dump(value, file):
    json.dump(value, file, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    file.write("\n")


def run(args):
    from threadpoolctl import threadpool_limits
    from analysis.change_history import run_history
    from analysis.run import _years_back, change_epochs, resolve_window
    from analysis.wards import change_features
    from vector.change_detection import DetectionConfig
    from vector.change_observations import DEFAULT_SOURCES, PRODUCT_VERSION, SOURCES

    destination = args.out.expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"destination already exists: {destination}")
    layer = _area(args.bbox)
    policy = DetectionConfig() if args.history_years is None else DetectionConfig(history_years=args.history_years)
    window = resolve_window(args.start, args.end)
    epochs = change_epochs(window)
    monitor = epochs["s2"][1]
    baseline = tuple(_years_back(date.fromisoformat(s), policy.history_years).isoformat() for s in monitor)
    epochs["s2"] = (baseline, monitor)
    sources = tuple(dict.fromkeys(args.sources)) if args.sources else DEFAULT_SOURCES
    destination.parent.mkdir(parents=True, exist_ok=True)
    with threadpool_limits(limits=1):
        result = run_history(layer, epochs, sources=sources, policy=policy, cache_dir=args.cache,
                             archive_root=destination.parent)
    with result["archive"] as staging:
        summary = result["summary"]
        errors = [f"{s['source']}: {' | '.join(s['errors']) or s['status']}" for s in summary["source_status"]
                  if s["status"] in ("partial", "failed")]
        if errors:
            raise RuntimeError("source retrieval incomplete; retry with the same cache: " + "; ".join(errors))
        metadata = {**summary, "bbox": layer.bbox, "crs": layer.crs.to_string(),
                    "validation_status": "experimental", "observation_version": PRODUCT_VERSION,
                    "sources": {key: SOURCES[key] for key in sources},
                    "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        for filename, data in (("summary.json", metadata), ("cells.geojson", change_features(result["block"]))):
            with (Path(staging) / filename).open("w", encoding="utf-8") as f:
                _dump(data, f)
        _publish_directory(staging, destination)
    print(destination)


def inspect_cell(args):
    from analysis.change_history import cell_detail, replay_options

    directory = args.directory.expanduser()
    with (directory / "summary.json").open(encoding="utf-8") as f:
        summary = json.load(f)
    replay = replay_options(summary, args.start, args.end, args.mode, args.as_of)
    data = cell_detail(directory / "history.sqlite", args.index, replay=replay)
    if data is None:
        raise ValueError(f"unknown unit index {args.index}; see cells.geojson")
    data["period"] = [replay["start"], replay["end"]] if replay else summary["period"]
    if args.out is None:
        _dump(data, sys.stdout)
        return
    dest = args.out.expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", dir=dest.parent, encoding="utf-8") as f:
        _dump(data, f)
        f.flush()
        os.link(f.name, dest)  # file becomes visible complete; EEXIST for any existing path
    print(dest)


def main(argv=None):
    from vector.change_observations import SOURCES

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Run from the repository root with its Python environment and Earth Engine credentials.

  python -m analysis.change_cli run --bbox 72.901 19.013 72.911 19.023 --start 2023-07-01 --end 2023-10-01 --sources sentinel2 sentinel1 --out ./change-example
  python -m analysis.change_cli cell ./change-example 0 --out ./cell-0.json

The run processes tiles sequentially and saves history.sqlite, summary.json and cells.geojson.
All date intervals use an exclusive end. A failed run can be repeated with the same cache.
The cell export matches the detail format in experiments.change_history.validate manifests.
Use run --help or cell --help for options.""")
    sub = parser.add_subparsers(required=True, dest="command")
    p = sub.add_parser("run", help="fetch archived observations and assess one interval")
    p.add_argument("--bbox", type=float, nargs=4, metavar=("WEST", "SOUTH", "EAST", "NORTH"), required=True)
    p.add_argument("--start", required=True, help="first monitoring date, inclusive (YYYY-MM-DD)")
    p.add_argument("--end", required=True, help="last boundary, exclusive (YYYY-MM-DD)")
    p.add_argument("--out", type=Path, required=True, help="new result directory; existing paths are preserved")
    p.add_argument("--sources", nargs="+", choices=sorted(SOURCES), help="default: Sentinel-1/2, Landsat 8/9 and historical buildings; add dynamic_world for class context")
    p.add_argument("--cache", type=Path, help="source cache (default: provider cache or GEOWATCH_CHANGE_CACHE)")
    p.add_argument("--history-years", type=int, help="full years before monitoring (detector default: five)")
    p.set_defaults(execute=run)
    p = sub.add_parser("cell", help="read a saved cell and its dated observations offline")
    p.add_argument("directory", type=Path)
    p.add_argument("index", type=int, help="unit_index from cells.geojson")
    p.add_argument("--out", type=Path, help="new JSON file; default: standard output")
    p.add_argument("--start", help="replay monitoring start (inclusive)")
    p.add_argument("--end", help="replay monitoring end (exclusive)")
    p.add_argument("--as-of", help="last evidence date included in replay")
    p.add_argument("--mode", choices=("prospective", "retrospective"))
    p.set_defaults(execute=inspect_cell)
    args = parser.parse_args(argv)
    try:
        args.execute(args)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")


if __name__ == "__main__":
    main()
