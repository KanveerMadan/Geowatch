"""
Item 21 measurement B -- AOI PROPOSALS (2026-09-25). Proposals only: the
user approves AOIs; this script picks none and runs no measurement.

For each site, a 3 km x 3 km box (exact, in the site's UTM zone) centred on
the named settlement -- its OSM boundary centroid where one exists, else the
stated fallback -- and for each box:

  - which measurement-A inventory scenes FULLY cover it, using real
    footprints (OpenAerialMap polygons re-fetched; Maxar = union of the
    acquisition's tile boxes; Rio IPP = the ImageServer extent), and the
    covered share for every scene that overlaps it;
  - descriptive Open Buildings v3 (>= 0.7) indicators, for the user to judge
    whether all four fabric strata (dense informal, formal, mixed, fringe)
    are plausibly present. Descriptive only -- no threshold decides anything.

    python experiments/item21_sites/aoi_proposals.py
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
HERE = os.path.dirname(os.path.abspath(__file__))
from experiments.item21_sites.inventory import MAXAR, _get  # noqa: E402

BOX_M = 3000

# name -> centre (lon, lat) and where it came from. Only Makoko, Kibera and
# Rocinha are named in the site list; training-city settlements are
# PROPOSED, with the project record that names them.
CENTRES = {
    "makoko": ((3.3923367, 6.4958525),
               "OSM node 13176760049 'Makoko' (place=suburb); no OSM boundary"),
    "kibera": ((36.7890001, -1.3113332),
               "OSM node 11007276790 'Kibera' (place=suburb); no OSM boundary"),
    "rocinha": ((-43.2484463, -22.9896502),
                "OSM relation 5520358 'Rocinha' (boundary=administrative, admin_level 10) centroid"),
    "cape_town": ((18.6588537, -34.0122734),
                  "PROPOSED settlement Khayelitsha (the project's Cape Town informal AOI in the "
                  "endmember-stability work); OSM relation 1017405 centroid"),
    "lima_candelaria": ((-76.9305604, -12.1268455),
                        "Candelaria is a site-list scene name; OSM node 9057391328 'Virgen de la "
                        "Candelaria' (place=neighbourhood), inside that scene's footprint"),
    "lima_both_scenes": ((-76.9286130, -12.1335585),
                         "ALTERNATIVE for Lima: midpoint of the two scenes the site list prioritises "
                         "(Candelaria 601c75ae..., Santuario de las Vizcachas 5fa4dedd...)"),
    "karachi": ((67.0019, 24.9433),
                "PROPOSED settlement Orangi (experiments/city_selection/aois.py); no OSM boundary; "
                "mean of 7 OSM 'Orangi Sector' place=neighbourhood nodes"),
    "monrovia": ((-10.8064, 6.3259),
                 "PROPOSED settlement West Point (experiments/city_selection/aois.py); no OSM "
                 "boundary or place; mean of 6 OSM features named 'West Point ...'"),
    "marrakech": ((-7.9978668, 31.6082337),
                  "PROPOSED settlement: the Médina (no settlement is named for Marrakech in any "
                  "project record); OSM relation 8340819 centroid"),
}
INVENTORY_SITE = {"lima_candelaria": "lima", "lima_both_scenes": "lima"}
IPP_EXTENT_31983 = (621720.15, 7444172.25, 695788.5, 7485303.6)   # Mosaico_2024 ImageServer


def utm_box(lon, lat):
    from pyproj import CRS, Transformer
    from shapely.geometry import box
    zone = int((lon + 180) // 6) + 1
    utm = CRS.from_epsg((32600 if lat >= 0 else 32700) + zone)
    tr = Transformer.from_crs("EPSG:4326", utm, always_xy=True)
    x, y = tr.transform(lon, lat)
    h = BOX_M / 2
    return utm, box(x - h, y - h, x + h, y + h)


def to_utm(geom, utm, src="EPSG:4326"):
    from pyproj import Transformer
    from shapely.ops import transform
    tr = Transformer.from_crs(src, utm, always_xy=True)
    return transform(tr.transform, geom)


def box_wgs84(utm, b):
    from pyproj import Transformer
    from shapely.ops import transform
    tr = Transformer.from_crs(utm, "EPSG:4326", always_xy=True)
    return transform(tr.transform, b)


def scene_footprints(site, bw, utm):
    """[(label, footprint in UTM or None, note)] for the site's inventory scenes."""
    from shapely.geometry import box, shape
    from shapely.ops import unary_union
    inv = json.load(open(os.path.join(HERE, "results", "imagery_inventory.json")))
    out = []
    oam = {}
    q = "https://api.openaerialmap.org/meta?bbox=" + ",".join(f"{v:.6f}" for v in bw.bounds) + "&limit=100"
    for r in _get(q)["results"]:
        oam[r["_id"]] = shape(r["geojson"])
    for sc in inv["sites"][site]["scenes"]:
        if sc.get("resolution_m") is not None and sc["resolution_m"] > 2:
            continue
        label = f"{sc['catalogue']}: {sc.get('title')}" + (f" [{sc['id']}]" if sc.get("id") else "")
        date = (sc.get("acquisition_start_utc") or sc.get("acquisition") or "")[:10]
        label += f" {date}"
        if sc["catalogue"] == "OpenAerialMap":
            fp = oam.get(sc["id"])
            out.append((label, None if fp is None else to_utm(fp, utm),
                        None if fp is not None else "does not intersect the box"))
        elif sc["catalogue"] == "Maxar Open Data":
            acq = _get(f"{MAXAR}{sc['event']}/ard/acquisition_collections/{sc['id']}_collection.json")
            fp = unary_union([box(*b) for b in acq["extent"]["spatial"]["bbox"]])
            out.append((label, to_utm(fp, utm), "union of ARD tile boxes (valid-data gaps not seen)"))
        elif sc["catalogue"] == "recorded (Rio IPP)":
            out.append((label, to_utm(box(*IPP_EXTENT_31983), utm, "EPSG:31983"),
                        "ImageServer extent rectangle (mosaic nodata not seen)"))
        else:
            out.append((label, None, "publisher states city-wide coverage; no extent published"))
    return out


def strata_indicators(bw, utm):
    """Descriptive Open Buildings v3 (>= 0.7) statistics inside the box.

    Coverage is built on the box's own UTM grid, 10 m cells aggregated to
    100 m cells that tile them exactly. Percentiles come from Earth Engine's
    histogram-based (approximate) percentile reducer: a repeated tiny value
    such as 4.9e-05 at p10 and p50 is its lowest bin edge and means ~0. The
    empty-cell share is an exact mean and is the reliable figure."""
    import ee
    from surface_fractions.grid import coverage_fraction
    g = ee.Geometry.Rectangle(list(bw.bounds))
    fc = (ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons")
          .filterBounds(g).filter(ee.Filter.gte("confidence", 0.7)))
    n = fc.size().getInfo()
    area = fc.reduceColumns(ee.Reducer.percentile([10, 50, 90]), ["area_in_meters"]).getInfo()
    proj10 = ee.Projection(utm.to_string()).atScale(10)
    cov10 = coverage_fraction(fc, proj10, 1)
    cov100 = (cov10.reduceResolution(ee.Reducer.mean(), maxPixels=128)
              .reproject(proj10.atScale(100)).rename("c"))
    stats = cov100.addBands(cov100.eq(0).rename("empty")).reduceRegion(
        ee.Reducer.percentile([10, 50, 90]).combine(ee.Reducer.mean(), sharedInputs=True),
        g, None, proj10.atScale(100), maxPixels=1e8).getInfo()
    return {"buildings": n,
            "footprint_area_m2_p10_p50_p90": [area.get(f"p{p}") for p in (10, 50, 90)],
            "coverage_100m_cells_p10_p50_p90": [stats.get(f"c_p{p}") for p in (10, 50, 90)],
            "share_100m_cells_without_buildings": stats.get("empty_mean")}


def main():
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    rows = {}
    for key, ((lon, lat), source) in CENTRES.items():
        utm, b = utm_box(lon, lat)
        bw = box_wgs84(utm, b)
        site = INVENTORY_SITE.get(key, key)
        cover = []
        for label, fp, note in scene_footprints(site, bw, utm):
            share = None if fp is None else float(fp.intersection(b).area / b.area)
            if fp is None and note != "does not intersect the box":
                cover.append({"scene": label, "covered_share": None, "note": note})
            elif share:
                cover.append({"scene": label, "covered_share": round(share, 4),
                              "fully_covers": share >= 0.999, "note": note})
        rows[key] = {"centre_lon_lat": [lon, lat], "centre_source": source,
                     "utm": utm.to_string(), "box_utm": [round(v, 1) for v in b.bounds],
                     "box_wgs84": [round(v, 6) for v in bw.bounds],
                     "scenes": sorted(cover, key=lambda c: -(c["covered_share"] or 0)),
                     "open_buildings_indicators": strata_indicators(bw, utm)}
        full = [c["scene"] for c in cover if c.get("fully_covers")]
        print(f"{key:18s} full={len(full)} indicators={rows[key]['open_buildings_indicators']}",
              flush=True)
    path = os.path.join(HERE, "results", "aoi_proposals.json")
    with open(path, "w") as fh:
        json.dump(rows, fh, indent=1)
    print(path)


if __name__ == "__main__":
    main()
