"""
Fabric-strata DRAFT rule (item 21, approved 2026-09-25).

One fixed rule for every site, thresholds in configs/labelling.yaml
`strata_rule`. Unit: each 200 m tile lying entirely inside the site's
real-data frame. Per tile, from Open Buildings v3 (confidence >= 0.7) only,
buildings assigned by centroid:

    n             building count
    area_median   median footprint area (m2)
    area_cv       footprint-area coefficient of variation (sd / mean)
    coverage      built coverage (share of the tile under footprints)

Applied in order -- the first match wins:

    n < unassigned_min_buildings                       -> unassigned
    coverage < fringe_coverage_max                     -> fringe
    coverage >= dense_informal_coverage_min
      and area_median < dense_informal_median_area_max -> dense_informal
    area_median >= formal_median_area_min
      or area_cv <= formal_area_cv_max                 -> formal
    otherwise                                          -> mixed

The draft is written to strata_draft.gpkg AND strata.gpkg; strata.gpkg is
reviewed and corrected by hand, then frozen before any tile is sampled.
Stratification for sampling only: not item 23 morphology, never published
as a result.
"""

from __future__ import annotations

UNASSIGNED = "unassigned"
TILE_M = 200
LAYER = "strata"
FIELDS = ["tile_id", "stratum", "draft_stratum", "n", "area_median", "area_cv", "coverage"]


def assign(m: dict, cfg: dict) -> str:
    """The rule, for one tile's metrics."""
    r = cfg["strata_rule"]
    if m["n"] < r["unassigned_min_buildings"]["value"]:
        return UNASSIGNED
    if m["coverage"] < r["fringe_coverage_max"]["value"]:
        return "fringe"
    if (m["coverage"] >= r["dense_informal_coverage_min"]["value"]
            and m["area_median"] < r["dense_informal_median_area_max_m2"]["value"]):
        return "dense_informal"
    cv = m.get("area_cv")
    if (m["area_median"] >= r["formal_median_area_min_m2"]["value"]
            or (cv is not None and cv <= r["formal_area_cv_max"]["value"])):
        return "formal"
    return "mixed"


def frame_tiles(frame) -> list:
    """(x0, y1) of every 200 m tile lying entirely inside `frame`."""
    from shapely.geometry import box
    from labelling.tiles import tile_origins
    return [(x0, y1) for x0, y1 in tile_origins(frame.bounds, TILE_M)
            if frame.contains(box(x0, y1 - TILE_M, x0 + TILE_M, y1))]


def compute_tile_metrics(site: str, cfg: dict, frame) -> list:
    """Earth Engine: metrics for every frame tile. One grouped pass over the
    buildings (tile index from each centroid's UTM coordinates) instead of a
    spatial filter per tile, which timed out; coverage is the tile mean of
    the same 1 m-subcell coverage raster the pipeline uses."""
    import ee
    from shapely.geometry import box
    from surface_fractions.grid import coverage_fraction
    a = cfg["aois"][site]
    crs = a["crs"]
    src = cfg["strata_rule"]["source"]
    tiles = frame_tiles(frame)
    region = ee.Geometry.Rectangle(list(box(*a["box_utm"]).bounds), crs, False)
    ob = (ee.FeatureCollection(src["asset"]).filterBounds(region)
          .filter(ee.Filter.gte("confidence", src["min_confidence"])))

    def tag(f):
        xy = f.geometry().centroid(1).transform(crs, 0.01).coordinates()
        i = ee.Number(xy.get(0)).divide(TILE_M).floor()
        j = ee.Number(xy.get(1)).divide(TILE_M).floor()
        return f.set("tile", i.multiply(1000000).add(j))

    groups = (ob.map(tag).reduceColumns(
        ee.Reducer.count().combine(ee.Reducer.median(), sharedInputs=True)
        .combine(ee.Reducer.mean(), sharedInputs=True).combine(ee.Reducer.stdDev(), sharedInputs=True)
        .group(groupField=1, groupName="tile"), ["area_in_meters", "tile"]).get("groups").getInfo())
    by_tile = {int(g["tile"]): g for g in groups}
    tfc = ee.FeatureCollection([ee.Feature(ee.Geometry.Rectangle([x0, y1 - TILE_M, x0 + TILE_M, y1], crs, False),
                                           {"x0": x0, "y1": y1}) for x0, y1 in tiles])
    proj = ee.Projection(crs).atScale(10)
    cov = coverage_fraction(ob, proj, 1).rename("cov")
    feats = cov.reduceRegions(tfc, ee.Reducer.mean().setOutputs(["coverage"]), crs=proj).getInfo()["features"]
    rows = []
    for f in feats:
        p = f["properties"]
        # Tile (x0, y1) holds centroids with floor(y / 200) == y1 / 200 - 1.
        g = by_tile.get(int(round(p["x0"] / TILE_M)) * 1000000 + int(round(p["y1"] / TILE_M)) - 1, {})
        mean = g.get("mean")
        rows.append({"x0": p["x0"], "y1": p["y1"], "n": int(g.get("count", 0)),
                     "area_median": g.get("median"),
                     "area_cv": (g["stdDev"] / mean) if mean else None,
                     "coverage": p.get("coverage") or 0.0})
    return rows


def draft_frame(site: str, cfg: dict, metrics: list):
    """Metrics -> GeoDataFrame of tiles with the drafted stratum."""
    import geopandas as gpd
    from shapely.geometry import box
    from labelling.tiles import tile_id
    crs = cfg["aois"][site]["crs"]
    recs = []
    for m in sorted(metrics, key=lambda m: (-m["y1"], m["x0"])):
        s = assign(m, cfg)
        recs.append({"tile_id": tile_id(crs, m["x0"], m["y1"]), "stratum": s, "draft_stratum": s,
                     "n": m["n"], "area_median": m["area_median"], "area_cv": m["area_cv"],
                     "coverage": m["coverage"],
                     "geometry": box(m["x0"], m["y1"] - TILE_M, m["x0"] + TILE_M, m["y1"])})
    return gpd.GeoDataFrame(recs, columns=FIELDS + ["geometry"], crs=crs)


def write_strata_gpkg(path: str, gdf, qml: str) -> str:
    """Write layer "strata" and store `qml` as its QGIS DEFAULT style (the
    layer_styles table QGIS reads on open), so the stratum dropdown and
    colours appear without loading a style by hand."""
    import os
    import sqlite3
    if os.path.exists(path):
        os.remove(path)
    gdf.to_file(path, layer=LAYER, driver="GPKG", engine="pyogrio")
    con = sqlite3.connect(path)
    try:
        con.execute("""CREATE TABLE layer_styles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT(256), f_table_schema TEXT(256),
            f_table_name TEXT(256), f_geometry_column TEXT(256), styleName TEXT(30), styleQML TEXT,
            styleSLD TEXT, useAsDefault BOOLEAN, description TEXT, owner TEXT(30), ui TEXT(30),
            update_time DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        geom_col = con.execute("SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ?",
                               (LAYER,)).fetchone()[0]
        con.execute("""INSERT INTO layer_styles (f_table_catalog, f_table_schema, f_table_name,
            f_geometry_column, styleName, styleQML, styleSLD, useAsDefault, description, owner)
            VALUES ('', '', ?, ?, 'strata', ?, '', 1, 'item 21 strata style (default)', '')""",
                    (LAYER, geom_col, qml))
        con.execute("""INSERT INTO gpkg_contents (table_name, data_type, identifier, description)
            VALUES ('layer_styles', 'attributes', 'layer_styles', '')""")
        con.commit()
    finally:
        con.close()
    return path


# ── command line: draft every approved site ─────────────────────────────────

def _package(site: str) -> str:
    import os
    from surface_fractions.config import REPO_ROOT
    return os.path.join(REPO_ROOT, "data", "strata_packages", site)


def write_site(site: str, cfg: dict, force: bool = False) -> dict:
    """Compute metrics, draft, and write strata_draft.gpkg + strata.gpkg.

    Refuses to overwrite a strata.gpkg that has been edited (it differs from
    the existing draft) unless force=True: the hand-corrected final must never
    be clobbered by a re-draft."""
    import json
    import os
    from collections import Counter
    from shapely.geometry import shape
    from labelling.strata_style import strata_qml
    pkg = _package(site)
    draft_path, final_path = os.path.join(pkg, "strata_draft.gpkg"), os.path.join(pkg, "strata.gpkg")
    if os.path.exists(final_path) and os.path.exists(draft_path) and not force:
        from labelling.strata_io import compare_draft_final
        if compare_draft_final(draft_path, final_path, site, cfg)["changed"]:
            raise RuntimeError(f"{final_path} has hand edits; refusing to overwrite (force=True to discard)")
    with open(os.path.join(pkg, "frame.geojson")) as fh:
        frame = shape(json.load(fh)["features"][0]["geometry"])
    metrics = compute_tile_metrics(site, cfg, frame)
    with open(os.path.join(pkg, "tile_metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=1)
    gdf = draft_frame(site, cfg, metrics)
    qml = strata_qml(cfg["tiles"]["strata"])
    write_strata_gpkg(draft_path, gdf, qml)
    write_strata_gpkg(final_path, gdf, qml)
    return {"site": site, "tiles": len(gdf), **Counter(gdf["stratum"])}


if __name__ == "__main__":
    import json
    import sys
    from surface_fractions.config import REPO_ROOT
    sys.path.insert(0, REPO_ROOT)
    from ingestion.gee_client import initialize_gee
    from labelling.common import load_config
    initialize_gee()
    _cfg = load_config()
    for _site in sys.argv[1:] or [k for k, v in _cfg["aois"].items() if v.get("frame_scene")]:
        print(json.dumps(write_site(_site, _cfg)), flush=True)
