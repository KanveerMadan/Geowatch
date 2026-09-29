"""
Item 21 Stage 1: prepare the 8 selected tiles for tracing (decision 7,
2026-09-29), like the practice tiles.

For each tile in data/stage1/selection.json, writes
data/stage1/tiles/<site>/<tile_id>/:
  hr.tif          the tile from the site's chosen scene (configs/labelling.yaml
                  aois.<site>.frame_sources), on the tile's UTM grid at the
                  finest native ground resolution of the contributing files
                  (n = ceil(200 m / res) pixels, so never coarser than native)
  tile.geojson    the 200 m tile boundary
  cells.geojson   its 400 Sentinel-2 10 m cells
  labels.gpkg     EMPTY label layer, QGIS style as default
  metadata.json   the tile record fields (LABELLING_GUIDE.md §8), filled where
                  known now; labeller / timing / QC fields empty
  sun.gpkg        (only where no usable acquisition time is published) the
                  empty shadow-line layer for labelling/sun_geometry.py

Acquisition times: a published time or window is recorded verbatim, with a
daylight check (sun above the horizon at both ends of the window, NOAA
algorithm). A tile whose contributing scenes have no daylight-plausible
published time gets sun.gpkg and `sun_geometry_required: true`.

    python experiments/item21_sites/prepare_stage1_tiles.py
    python experiments/item21_sites/prepare_stage1_tiles.py --refresh-metadata   # rule fields only
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

SELECTION = os.path.join(REPO, "data", "stage1", "selection.json")
TILES = os.path.join(REPO, "data", "stage1", "tiles")
PILOT_A = os.path.join(HERE, "results", "pilot_a_change_test.json")
DETRENDED = os.path.join(HERE, "results", "pilot_a_detrended.json")
TILE_M = 200

# Per-site imagery facts, from configs/labelling.yaml and the sources' own metadata.
SOURCES = {
    "cape_town": {"source": "City of Cape Town 'Aerial Imagery 2025Jan' (MapServer export)",
                  "licence": "City of Cape Town: no restrictions on the digital file for non-commercial purposes",
                  "date": "2025-01-01", "date_end": "2025-01-31",
                  "date_range_reason": "the service publishes only the period '2025Jan'",
                  "time_window_utc": None},
    "karachi": {"source": "Maxar Open Data 10300100D13F6500 (WorldView, pakistan-flooding22 ARD visual)",
                "licence": "CC BY-NC 4.0", "date": "2022-03-29"},
    "monrovia": {"source": "OpenAerialMap 2020-02-23 flight (Uhuru / HOT)", "licence": "CC BY 4.0",
                 "date": "2020-02-23"},
    "lima": {"source": "OpenAerialMap 2019-12-19 (Candelaria / Santuario de las Vizcachas)",
             "licence": "CC BY 4.0", "date": "2019-12-19"},
}


def tile_geom(t: dict):
    from shapely.geometry import box
    return box(t["x0"], t["y1"] - TILE_M, t["x0"] + TILE_M, t["y1"])


def site_files(site: str, cfg: dict, tile, crs: str) -> list:
    """[{url, id, published window, sun angles if published}] of the scene files touching the tile."""
    import frames as fr
    src = cfg["aois"][site]["frame_sources"]
    out = []
    if "oam" in src:
        for oid in src["oam"]:
            meta = fr._get(f"https://api.openaerialmap.org/meta/{oid}")
            meta = meta.get("results", meta)
            if fr.oam_footprint(oid, crs).intersects(tile):
                out.append({"id": oid, "url": meta["uuid"], "title": meta.get("title"),
                            "window_utc": [meta.get("acquisition_start"), meta.get("acquisition_end")],
                            "gsd_m": meta.get("gsd")})
    if "ard" in src:
        event, acq = src["ard"]
        base = f"{fr.MAXAR}{event}/ard/acquisition_collections/"
        acqj = fr._get(base + f"{acq}_collection.json")
        tw = fr._to(tile, crs, "EPSG:4326")
        from shapely.geometry import box as sbox
        for il in acqj["links"]:
            if il["rel"] != "item":
                continue
            it = fr._get(base + il["href"])
            if sbox(*it["bbox"]).intersects(tw):
                p = it["properties"]
                out.append({"id": it["id"],
                            "url": (base + il["href"]).rsplit("/", 1)[0] + "/" + it["assets"]["visual"]["href"].lstrip("./"),
                            "datetime_utc": p.get("datetime"), "gsd_m": p.get("gsd"),
                            "sun_azimuth_deg": p.get("view:sun_azimuth"), "sun_elevation_deg": p.get("view:sun_elevation"),
                            "off_nadir_deg": p.get("view:off_nadir")})
    return out


def native_ground_res(url: str, lat: float) -> float:
    import rasterio
    with rasterio.open(url) as s:
        r = abs(s.res[0])
        if s.crs and s.crs.to_epsg() == 3857:
            r *= math.cos(math.radians(lat))                   # web-mercator scale at this latitude
        return r


def fetch_cogs(files: list, tile, crs: str, lat: float) -> tuple:
    """Mosaic the files onto the tile grid; first file with valid data wins
    (declared masks). Returns (rgb uint8 3xNxN, transform, res, contributing ids)."""
    import rasterio
    from rasterio.enums import Resampling
    from rasterio.transform import from_origin
    from rasterio.vrt import WarpedVRT
    res_native = min(native_ground_res(f["url"], lat) for f in files)
    n = math.ceil(TILE_M / res_native)
    res = TILE_M / n
    x0, _, _, y1 = tile.bounds
    t = from_origin(x0, y1, res, res)
    rgb = np.zeros((3, n, n), np.uint8)
    filled = np.zeros((n, n), bool)
    used = []
    for f in files:
        with rasterio.open(f["url"]) as s, WarpedVRT(s, crs=crs, transform=t, width=n, height=n,
                                                     resampling=Resampling.bilinear) as v:
            data = v.read([1, 2, 3])
            valid = v.dataset_mask() > 0
        take = valid & ~filled
        if take.any():
            rgb[:, take] = data[:, take]
            filled |= take
            used.append(f["id"])
    return rgb, t, res, used, float(filled.mean())


def write_raster(path: str, rgb: np.ndarray, t, crs: str, note: str):
    import rasterio
    from rasterio.enums import Resampling
    with rasterio.open(path, "w", driver="GTiff", width=rgb.shape[2], height=rgb.shape[1], count=3,
                       dtype="uint8", crs=crs, transform=t, photometric="YCBCR", compress="JPEG",
                       jpeg_quality=92, tiled=True, blockxsize=512, blockysize=512) as dst:
        dst.write(rgb)
        dst.update_tags(NOTE=note)
    with rasterio.open(path, "r+") as dst:
        dst.build_overviews([2, 4, 8, 16], Resampling.average)


def write_grids(out: str, tile_id: str, t: dict, crs: str):
    from shapely.geometry import box, mapping
    epsg = crs.split(":")[1]
    member = {"type": "name", "properties": {"name": f"urn:ogc:def:crs:EPSG::{epsg}"}}
    x0, y1 = t["x0"], t["y1"]
    with open(os.path.join(out, "tile.geojson"), "w") as fh:
        json.dump({"type": "FeatureCollection", "name": "tile", "crs": member,
                   "features": [{"type": "Feature", "properties": {"tile_id": tile_id},
                                 "geometry": mapping(tile_geom(t))}]}, fh)
    cells = [{"type": "Feature", "properties": {"cell": f"{r}_{c}"},
              "geometry": mapping(box(x0 + 10 * c, y1 - 10 * (r + 1), x0 + 10 * (c + 1), y1 - 10 * r))}
             for r in range(20) for c in range(20)]
    with open(os.path.join(out, "cells.geojson"), "w") as fh:
        json.dump({"type": "FeatureCollection", "name": "cells", "crs": member, "features": cells}, fh)


def _parse(ts):
    return None if not ts else datetime.fromisoformat(ts.replace("Z", "+00:00"))


def time_record(site: str, files: list, lat: float, lon: float) -> dict:
    """Published acquisition time(s) verbatim + daylight check."""
    from labelling.sun_geometry import is_daylight
    if site == "cape_town":
        return {"imagery_acquisition_time": None, "published_times": [],
                "sun_geometry_required": True,
                "time_note": "no acquisition time is published (period '2025Jan' only)"}
    rows = []
    for f in files:
        if "datetime_utc" in f:
            t0 = t1 = _parse(f["datetime_utc"])
        else:
            t0, t1 = _parse(f["window_utc"][0]), _parse(f["window_utc"][1])
        ok = bool(t0 and t1 and is_daylight(t0, t1, lat, lon))
        rows.append({"file": f["id"], "published_utc": f.get("datetime_utc") or f.get("window_utc"),
                     "daylight_at_both_ends": ok})
    if site == "karachi":
        return {"published_times": rows, "sun_geometry_required": False,
                "imagery_acquisition_time": files[0]["datetime_utc"][11:19] + " UTC",
                "time_note": "Maxar ARD item datetime (publisher metadata)"}
    # Decided 2026-09-29 (v1.6): uploader-entered OpenAerialMap windows are
    # not publisher metadata -> sun from shadows; the window is kept for the
    # corroboration check (labelling/sun_geometry.py).
    return {"published_times": [], "uploader_windows": rows, "sun_geometry_required": True,
            "imagery_acquisition_time": None,
            "uploader_window_utc": rows[0]["published_utc"] if len(rows) == 1 else None,
            "time_note": ("OpenAerialMap acquisition_start / _end are uploader-entered, not publisher "
                          "metadata: sun geometry is measured from shadows; the window is recorded for "
                          "corroboration")}


def gap_and_window(site: str, pa: dict, cfg: dict) -> dict:
    """Composite window (§9.1/§9.2, v1.6) and the worst-case |scene date -
    imagery date| over the window's clear scenes. A date range (not an
    exception) uses [range_end - 90 d, range_start + 90 d]."""
    from range_window_rule import range_window
    r = pa["sites"][site]
    s = SOURCES[site]
    d0 = date.fromisoformat(s["date"])
    d1 = date.fromisoformat(s.get("date_end") or s["date"])
    win = cfg["open"]["change_test"]["window"]
    lo, hi = date.fromisoformat(r["window"][0]), date.fromisoformat(r["window"][1])
    if d1 > d0 and site not in win["date_range_exceptions"]:
        lo, hi = range_window(s["date"], s["date_end"], win["half_window_days"])
    days = [date.fromisoformat(d) for d in r["dates"] if lo <= date.fromisoformat(d) <= hi]
    rng = [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1)]
    worst = max(max(abs((x - h).days) for x in days) for h in rng)
    return {"s2_composite_window": {"start": lo.isoformat(), "end": hi.isoformat()},
            "s2_clear_scenes": len(days), "date_gap_days": worst,
            "date_gap_definition": "max |clear-scene date - imagery date| over the composite window's scenes; "
                                   "worst case across the imagery date range"}


RANGE_RULE = os.path.join(HERE, "results", "range_window_rule.json")


def change_test_row(site: str, tile_id: str, det: dict) -> dict:
    """The frozen change test's result for the tile; for a date-range site
    under the v1.6 window rule, from range_window_rule.json."""
    if os.path.exists(RANGE_RULE):
        with open(RANGE_RULE) as fh:
            rr = json.load(fh)
        if rr["site"] == site:
            return next(r for r in rr["tiles"] if r["tile_id"] == tile_id)
    return next(r for r in det["sites"][site]["tiles"] if r["tile_id"] == tile_id)


def change_test_text(ct: dict, rule: dict) -> str:
    verdict = "dropped" if ct["dropped"] else "kept"
    return (f"{verdict}: {ct['share']:.1%} of {ct['evaluable']} cells changed (frozen §9.1: de-trended, "
            f"k={rule['change']['k']}, drop above {rule['drop_tile_if_changed_share_above']:.0%})")


def refresh_metadata(site: str, tile_dir: str, cfg: dict, pa: dict, det: dict) -> dict:
    """Rewrite only the rule-derived fields of an existing tile record (no
    imagery refetch; labeller fields untouched)."""
    from pyproj import Transformer
    p = os.path.join(tile_dir, "metadata.json")
    with open(p) as fh:
        meta = json.load(fh)
    meta.update(gap_and_window(site, pa, cfg))
    meta["change_test_result"] = change_test_text(change_test_row(site, meta["tile_id"], det),
                                                  cfg["open"]["change_test"])
    meta["guide_version"] = cfg["guide_version"]
    if site in ("lima", "monrovia"):
        import frames as fr
        crs = meta["tile_utm"]["crs"]
        lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(
            meta["tile_utm"]["x0"] + TILE_M / 2, meta["tile_utm"]["y1"] - TILE_M / 2)
        files = []
        for oid in meta["imagery_files"]:
            m = fr._get(f"https://api.openaerialmap.org/meta/{oid}")
            m = m.get("results", m)
            files.append({"id": oid, "window_utc": [m.get("acquisition_start"), m.get("acquisition_end")]})
        meta.pop("published_times", None)
        meta.update(time_record(site, files, lat, lon))
    with open(p, "w") as fh:
        json.dump(meta, fh, indent=1)
    return {k: meta.get(k) for k in ("tile_id", "s2_composite_window", "s2_clear_scenes", "date_gap_days",
                                     "change_test_result", "sun_geometry_required", "uploader_window_utc")}


def prepare(site: str, entry: dict, cfg: dict, pa: dict, det: dict) -> dict:
    from pyproj import Transformer
    from labelling.gpkg_style import write_gpkg
    from labelling.label_style import LAYER, empty_labels_gdf, labels_qml
    from labelling.sun_geometry import setup as sun_setup
    crs = cfg["aois"][site]["crs"]
    t = entry["chosen"]
    tile_id = t["tile_id"]
    out = os.path.join(TILES, site, tile_id)
    if os.path.exists(os.path.join(out, "metadata.json")):
        return {"tile_id": tile_id, "skipped": "already prepared"}
    os.makedirs(out, exist_ok=True)
    tile = tile_geom(t)
    lon, lat = Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform(*tile.centroid.coords[0])

    if site == "cape_town":
        import prepare_practice_tiles as ppt
        rgb, tr = ppt.fetch_hr(tile)
        res, used, cover, files = ppt.RES_M, ["2025Jan MapServer"], float((rgb.max(0) > 0).mean()), []
    else:
        files = site_files(site, cfg, tile, crs)
        rgb, tr, res, used, cover = fetch_cogs(files, tile, crs, lat)
    write_raster(os.path.join(out, "hr.tif"), rgb, tr, crs, f"item 21 Stage 1 tile {tile_id} ({site})")
    write_grids(out, tile_id, t, crs)
    labels = cfg["labels"]["scored"] + cfg["labels"]["excluded"]
    write_gpkg(os.path.join(out, "labels.gpkg"), empty_labels_gdf(crs), LAYER, labels_qml(labels),
               geometry_type="Polygon")

    s = SOURCES[site]
    tr_ = time_record(site, [f for f in files if f["id"] in used], lat, lon)
    ct = change_test_row(site, tile_id, det)
    rule = cfg["open"]["change_test"]
    meta = {
        "purpose": "item 21 Stage 1 training tile (decision 5, 2026-09-29)",
        "site": site, "tile_id": tile_id, "stratum": t["stratum"], "rank_in_stratum": t["rank_in_stratum"],
        "tile_utm": {"crs": crs, "x0": t["x0"], "y1": t["y1"], "size_m": TILE_M},
        "imagery_source": s["source"], "imagery_files": used, "imagery_licence": s["licence"],
        "imagery_acquisition_date": s["date"],
        "imagery_acquisition_date_end": s.get("date_end"),
        "imagery_acquisition_date_range_reason": s.get("date_range_reason"),
        "imagery_acquisition_time": tr_["imagery_acquisition_time"],
        "published_times": tr_["published_times"], "time_note": tr_["time_note"],
        "uploader_windows": tr_.get("uploader_windows"), "uploader_window_utc": tr_.get("uploader_window_utc"),
        "sun_geometry_required": tr_["sun_geometry_required"],
        "sun_azimuth_deg": None, "sun_elevation_deg": None, "sun_geometry_method": None,
        "sun_geometry_n_buildings": None,
        "imagery_resolution_m": round(res, 4), "hr_valid_share": round(cover, 4),
        "labelling_note": cfg["aois"][site].get("labelling_note"),
        **gap_and_window(site, pa, cfg),
        "change_test_result": change_test_text(ct, rule),
        "guide_version": cfg["guide_version"],
        "labeller": None, "labelling_date": None,
        "timing": {"start_local": None, "end_local": None, "minutes": None},
        "pct_unsure": None, "pct_shadow_full": None, "qc_status": "pending",
        "tracing_method": "manual",
    }
    if site == "karachi" and files:
        f = next(f for f in files if f["id"] == used[0])
        meta["published_sun"] = {"sun_azimuth_deg": f["sun_azimuth_deg"], "sun_elevation_deg": f["sun_elevation_deg"],
                                 "off_nadir_deg": f["off_nadir_deg"], "source": f"Maxar ARD item {f['id']}"}
    with open(os.path.join(out, "metadata.json"), "w") as fh:
        json.dump(meta, fh, indent=1)
    if meta["sun_geometry_required"]:
        sun_setup(out, crs)
    return {"tile_id": tile_id, "site": site, "res_m": round(res, 4), "hr_valid_share": round(cover, 4),
            "files": used, "sun_geometry_required": meta["sun_geometry_required"],
            "time": meta["imagery_acquisition_time"]}


def main():
    from labelling.common import load_config
    cfg = load_config()
    with open(SELECTION) as fh:
        sel = json.load(fh)
    with open(PILOT_A) as fh:
        pa = json.load(fh)
    with open(DETRENDED) as fh:
        det = json.load(fh)
    refresh = "--refresh-metadata" in sys.argv
    for site, s in sel["sites"].items():
        for entry in s["strata"].values():
            d = os.path.join(TILES, site, entry["chosen"]["tile_id"])
            r = refresh_metadata(site, d, cfg, pa, det) if refresh else prepare(site, entry, cfg, pa, det)
            print(json.dumps(r), flush=True)


if __name__ == "__main__":
    main()
