"""
Item 21 measurement B (2026-09-25): part 4 (`built` + two-source
disagreement) on every item 21 site. No labels, no training.

Reuses the pipeline path exactly -- native Sentinel-2 grid
(surface_fractions.grid), Open Buildings v3 >= 0.7 and Microsoft coverage at
1 m sub-cells (the same bands as surface_fractions.inputs), exported on the
explicit grid and scored by surface_fractions.built.disagreement -- so the
numbers are the ones the pipeline would emit.

AOIs: --site NAME uses the APPROVED 3 x 3 km box from configs/labelling.yaml
(exact, in the site's UTM zone; approved 2026-09-25); --aoi name=W,S,E,N takes
a lon/lat box. Validated on Dharavi, where it reproduces the part 4 numbers
exactly (results/built_disagreement_dharavi_check.json).

Also reports R5's per-site coverage bias BETWEEN THE TWO SOURCES
(Open Buildings mean - Microsoft mean). Descriptive only: these are two
footprint datasets, not labels, so no pass/fail applies.

    python experiments/item21_sites/built_disagreement.py --site makoko --site kibera --label sites
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

BANDS = ["ob_cov", "ms_cov"]


def run_aoi(name: str, bbox: tuple, cfg: dict, work_dir: str, crs: str | None = None) -> dict:
    import ee
    from ingestion.tiler import export_image_local
    from surface_fractions.built import compute_built
    from surface_fractions.grid import coverage_fraction, ee_projection, grid_region, native_grid
    from surface_fractions.inputs import NODATA, microsoft_asset_for, microsoft_fc, read_stack

    geom = (ee.Geometry.Rectangle(list(bbox), proj=crs, geodesic=False) if crs
            else ee.Geometry.Rectangle(list(bbox)))
    grid = native_grid(geom, cfg["sentinel2"]["collection"])
    region = grid_region(grid)
    proj = ee_projection(grid)
    ob = cfg["footprints"]["open_buildings"]
    sub = cfg["footprints"]["subcell_m"]
    ob_fc = (ee.FeatureCollection(ob["asset"]).filterBounds(region)
             .filter(ee.Filter.gte("confidence", ob["min_confidence"])))
    ms_asset, country, ms_err = microsoft_asset_for(region, cfg)
    ms_img = (coverage_fraction(microsoft_fc(ms_asset).filterBounds(region), proj, sub)
              if ms_asset else ee.Image.constant(NODATA)).rename("ms_cov")
    img = ee.Image.cat([coverage_fraction(ob_fc, proj, sub).rename("ob_cov"), ms_img])
    path = os.path.join(work_dir, f"{name}_footprints.tif")
    export_image_local(img.toFloat().unmask(NODATA), region, path, crs=grid.crs,
                       crs_transform=list(grid.transform), band_names=BANDS)
    bands = read_stack(path, grid, BANDS)
    status = {"microsoft_buildings": "available" if ms_asset else "unavailable"}
    b = compute_built(bands, status, {"asset": ob["asset"],
                                      "min_confidence": ob["min_confidence"], "subcell_m": sub})
    d = b["disagreement"]
    if d.get("status") == "computed":
        d["coverage_bias_primary_minus_secondary"] = (
            d["coverage_total_primary"] - d["coverage_total_secondary"])
        d["coverage_bias_note"] = "R5 per-site bias metric, descriptive only (not labels)"
    return {"bbox": list(bbox), "bbox_crs": crs or "EPSG:4326", "grid": grid.to_dict(),
            "area_km2": grid.width * grid.height * grid.res ** 2 / 1e6,
            "microsoft": {"asset": ms_asset, "country": country, "error": ms_err},
            "disagreement": b["disagreement"]}


def main(aois: dict, label: str, crs_by_aoi: dict | None = None):
    from ingestion.gee_client import initialize_gee
    from surface_fractions.config import load_config
    initialize_gee()
    cfg = load_config()
    work = os.path.join(REPO, "data", "surface_fractions", "measurement_b")
    os.makedirs(work, exist_ok=True)
    rows = {}
    for name, bbox in aois.items():
        print(f"== {name} {bbox}", flush=True)
        try:
            rows[name] = run_aoi(name, bbox, cfg, work, (crs_by_aoi or {}).get(name))
        except Exception as e:  # noqa: BLE001 -- recorded per AOI, never silent
            rows[name] = {"bbox": list(bbox), "error": f"{type(e).__name__}: {e}"}
        print(json.dumps(rows[name].get("disagreement") or rows[name]), flush=True)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"built_disagreement_{label}.json")
    with open(path, "w") as fh:
        json.dump({"generated_utc": datetime.now(timezone.utc).isoformat(),
                   "aois": rows}, fh, indent=1)
    print(path)


def _parse(argv):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aoi", action="append", default=[],
                    help="name=west,south,east,north in lon/lat (repeatable)")
    ap.add_argument("--site", action="append", default=[],
                    help="approved item 21 site from configs/labelling.yaml (repeatable)")
    ap.add_argument("--label", required=True, help="results file suffix")
    a = ap.parse_args(argv)
    aois, crs = {}, {}
    for spec in a.aoi:
        name, box = spec.split("=", 1)
        aois[name] = tuple(float(v) for v in box.split(","))
    if a.site:
        from labelling.common import load_config as load_labelling
        lcfg = load_labelling()
        for site in a.site:
            s = lcfg["aois"][site]
            if s["status"] != "approved":
                ap.error(f"{site}: AOI is {s['status']}, not approved")
            aois[site], crs[site] = tuple(s["box_utm"]), s["crs"]
    if not aois:
        ap.error("give --site and/or --aoi")
    return aois, a.label, crs


if __name__ == "__main__":
    main(*_parse(sys.argv[1:]))
