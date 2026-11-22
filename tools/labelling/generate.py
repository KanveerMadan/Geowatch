"""Generate a separate, exclusively created candidate GeoPackage on an authorized tile."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import rasterio
from rasterio.warp import transform_bounds
import shapely
from shapely.geometry import box

from .candidate_imagery import imagery_candidates
from .candidate_sources import check_disk, vector_sources
from .guard import authorize_tile


LAYERS = ("built_open_buildings", "built_microsoft", "built_osm", "paved_osm", "water_osm",
          "vegetation_rgb", "hint_water_rgb", "hint_vegetation_osm", "hint_shadow_rgb")
COLUMNS = ("candidate_id","class","source","source_id","source_version","confidence","needs_check","hint_only","note")
PRIORITY = {n:i for i,n in enumerate(LAYERS)}
ATTRIBUTION = ("Google Open Buildings v3, CC BY 4.0; Microsoft Global ML Building Footprints via sat-io MSBuildings (mirror cites ODbL; current upstream cites CDLA Permissive 2.0); "
               "© OpenStreetMap contributors, ODbL (https://www.openstreetmap.org/copyright). "
               "Tile RGB candidates inherit the source imagery conditions in tile metadata.")


def _polygon_parts(g):
    if g.is_empty:
        return
    if g.geom_type == "Polygon":
        yield g
    elif g.geom_type in ("GeometryCollection", "MultiPolygon"):
        for piece in g.geoms:
            yield from _polygon_parts(piece)


def _clip_snap(g, footprint, affine):
    """Clip polygon parts and quantize vertices to the original image pixel-edge lattice."""
    def snap(coords):
        grid_origin = np.array([affine.c, affine.f])
        spacing = np.array([affine.a, affine.e])
        return grid_origin + np.rint((coords-grid_origin)/spacing)*spacing
    if not g.is_valid:
        g = shapely.make_valid(g)
    for poly in _polygon_parts(g.intersection(footprint)):
        snapped = shapely.make_valid(shapely.transform(poly, snap))
        for part in _polygon_parts(snapped.intersection(footprint)):
            if part.area >= abs(affine.a * affine.e) - 1e-8:
                yield part


def clean_candidates(rows, bounds, affine, tile_id):
    """A lower-priority footprint is redundant when at least half the smaller outline overlaps."""
    footprint = box(*bounds)
    rows = sorted(rows, key=lambda r:(PRIORITY[r["layer"]], -(r["confidence"] or 0), r["source_id"]))
    chosen, ids, buildings, duplicates = [], set(), [], {}
    for row in rows:
        layer = row["layer"]
        for g in _clip_snap(row["geometry"], footprint, affine):
            if row["class"] == "built":
                if any(b.intersects(g) and b.intersection(g).area >= .5 * min(g.area,b.area) for b in buildings):
                    duplicates[layer] = duplicates.get(layer,0) + 1
                    continue
                buildings.append(g)
            ident = hashlib.sha256(json.dumps([tile_id,layer,row["source_id"],row["source_version"]],
                                              separators=(",",":")).encode()+g.normalize().wkb).hexdigest()[:32]
            if ident in ids:
                continue
            ids.add(ident)
            chosen.append({**row, "geometry":g, "candidate_id":ident})
    return chosen, duplicates


def _write(path, crs, rows, receipt):
    for i,layer in enumerate(LAYERS):
        data = [r for r in rows if r["layer"] == layer]
        frame = pd.DataFrame([{k:r[k] for k in COLUMNS} for r in data], columns=COLUMNS)
        frame["confidence"] = frame["confidence"].astype("float64")
        frame[["needs_check","hint_only"]] = frame[["needs_check","hint_only"]].astype("int32")
        frame = gpd.GeoDataFrame(frame, geometry=[r["geometry"] for r in data], crs=crs)
        meta = {"item21_receipt":json.dumps(receipt, sort_keys=True), "attribution":ATTRIBUTION}
        pyogrio.write_dataframe(frame,path,layer=layer,driver="GPKG",geometry_type="Polygon",
                                dataset_metadata=meta if i == 0 else None)


def generate(tile_dir, *, cache=None, output_dir=None):
    spec = authorize_tile(tile_dir)
    folder = spec.path
    if output_dir is not None and Path(output_dir).resolve(strict=True) != folder:
        raise ValueError("Generate inside the authorized tile. Use a registered private tile copy for staging.")
    target = folder / "prelabels.gpkg"
    if os.path.lexists(target):
        raise FileExistsError(f"{target} already exists; existing review work is preserved")
    cache = Path(cache or Path.home()/".cache"/"geowatch"/"item21-prelabels").expanduser().resolve()
    if any(p == folder or (p/".git").exists() for p in (cache,*cache.parents)):
        raise ValueError("use a private source cache outside the tile and repository")
    cache.mkdir(parents=True, exist_ok=True)
    check_disk(cache)
    check_disk(folder)
    metadata = json.loads((folder/"metadata.json").read_text())
    imagery_version = "{} | {}".format(metadata.get("imagery_source","tile RGB"),metadata.get("imagery_acquisition_date","undated"))
    with rasterio.Env(GDAL_PAM_ENABLED="NO", GDAL_NUM_THREADS="1"), rasterio.open(spec.image) as src:
        bounds = tuple(src.bounds)
        if src.crs.to_string() != spec.crs or not np.allclose(bounds,spec.bounds,rtol=0,atol=1e-4):
            raise ValueError("The image header changed after authorization")
        rgb, rgb_status = imagery_candidates(src, imagery_version)
        affine = src.transform
    ext = transform_bounds(spec.crs,4326,*bounds)
    vector, sources = vector_sources(ext, spec.crs, cache)
    rows, duplicates = clean_candidates(vector + rgb,bounds,affine,spec.tile_id)
    counts = {layer:sum(r["layer"]==layer for r in rows) for layer in LAYERS}
    receipt = {"tile_id":spec.tile_id,"bounds":bounds,"crs":spec.crs,"version":"item21-assist-v1",
               "image":imagery_version,"sources":{**sources,"tile_rgb":rgb_status},"counts":counts,
               "suppressed_building_duplicates":duplicates, "attribution":ATTRIBUTION}
    # Build privately and publish with an exclusive hard link; a concurrent generation cannot overwrite a tile.
    with tempfile.TemporaryDirectory(dir=cache) as temp:
        path = Path(temp)/target.name
        _write(path,spec.crs,rows,receipt)
        # The private cache and tile can be on separate disks. Copy to a sibling staging file only in that case.
        if path.stat().st_dev == folder.stat().st_dev:
            os.link(path,target)
        else:
            import shutil
            with tempfile.NamedTemporaryFile(dir=folder,prefix=".item21-",delete=False) as out, path.open("rb") as src:
                staging = Path(out.name)
                try:
                    shutil.copyfileobj(src,out)
                    out.flush()
                    os.link(staging,target)
                finally:
                    staging.unlink()
    return receipt


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("tile",type=Path)
    cli.add_argument("--cache",type=Path,help="Private persistent source cache outside any checkout")
    cli.add_argument("--output-dir",type=Path,help="Must be the authorized tile directory")
    args = cli.parse_args()
    print(json.dumps(generate(args.tile,cache=args.cache,output_dir=args.output_dir),indent=2))


if __name__ == "__main__":
    main()
