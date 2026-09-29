"""
Item 21 inventory (report only, 2026-09-29): existing human-digitised
building footprints at the item 21 sites. Nothing is used for labels, and
no model output is compared with anything.

OSM buildings (ways and multipolygon relations tagged building=*) intersecting
each approved 3 x 3 km box, from the Overpass API: count, footprint area
share of the box, last-edit timestamps (OSM keeps only the current version's
timestamp here -- a last-edit date, not the digitisation date), and the
source=* / source:geometry tag values. Licence: ODbL. Mapper names are not
recorded. For reference, the Open Buildings v3 (confidence >= 0.7) area
share of the same box.

Also: the two city building datasets found (Rio IPP "Edificacoes (2013)",
City of Cape Town "2D Building Footprints"), and the Open Cities AI
Challenge scenes' overlap with the Monrovia box (from its STAC catalog).

    python experiments/item21_sites/inventory_footprints.py
"""

from __future__ import annotations

import collections
import json
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "inventory_footprints.json")
OVERPASS = ["https://overpass-api.de/api/interpreter",          # public instances, same OSM data
            "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
SITES = ["makoko", "kibera", "rocinha", "lima", "monrovia", "karachi", "cape_town"]


def box_ll(a: dict):
    from pyproj import Transformer
    from shapely.geometry import box
    from shapely.ops import transform
    b = box(*a["box_utm"])
    return b, transform(Transformer.from_crs(a["crs"], "EPSG:4326", always_xy=True).transform, b)


def overpass(bbox_ll) -> list:
    import requests
    w, s, e, n = bbox_ll.bounds
    q = f'[out:json][timeout:600];(way["building"]({s},{w},{n},{e});relation["building"]({s},{w},{n},{e}););out geom meta;'
    for attempt in range(2):
        for url in OVERPASS:
            try:
                r = requests.post(url, data={"data": q}, timeout=900, headers={"User-Agent": "geowatch-research"})
            except requests.RequestException as e:
                print(f"  {url}: {type(e).__name__}", flush=True)
                continue
            if r.status_code == 200:
                j = r.json()
                return j["elements"], {"endpoint": url, "osm_data_as_of": j.get("osm3s", {}).get("timestamp_osm_base")}
            print(f"  {url}: HTTP {r.status_code}", flush=True)
        time.sleep(60)
    raise RuntimeError("every Overpass instance failed")


def polygons(el):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    if el["type"] == "way" and len(el.get("geometry", [])) >= 4:
        return Polygon([(p["lon"], p["lat"]) for p in el["geometry"]]).buffer(0)
    if el["type"] == "relation":
        outers = [Polygon([(p["lon"], p["lat"]) for p in m["geometry"]]).buffer(0)
                  for m in el.get("members", []) if m.get("role") == "outer" and len(m.get("geometry", [])) >= 4]
        inners = [Polygon([(p["lon"], p["lat"]) for p in m["geometry"]]).buffer(0)
                  for m in el.get("members", []) if m.get("role") == "inner" and len(m.get("geometry", [])) >= 4]
        if outers:
            return unary_union(outers).difference(unary_union(inners)) if inners else unary_union(outers)
    return None


def open_buildings_share(a: dict) -> float:
    import ee
    from shapely.geometry import box
    region = ee.Geometry.Rectangle(list(box(*a["box_utm"]).bounds), a["crs"], False)
    ob = (ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons").filterBounds(region)
          .filter(ee.Filter.gte("confidence", 0.7)))
    img = ee.Image.constant(0).paint(ob, 1).selfMask().unmask(0)
    return float(img.reduceRegion(ee.Reducer.mean(), region, scale=1, crs=a["crs"], maxPixels=1e10)
                 .getInfo()["constant"])


CITY = {   # found 2026-09-29 via each city's ArcGIS Hub catalogue
    "rocinha": {"name": "IPP Rio 'Edificacoes (2013)'", "licence": "CC BY 4.0 (data.rio)",
                "url": "https://services5.arcgis.com/mgrvZxGU0bSJbVld/arcgis/rest/services/"
                       "Quadras_Lotes_Edificacoes/FeatureServer/0", "summarise": ["Tipo"]},
    "cape_town": {"name": "City of Cape Town '2D Building Footprints'",
                  "licence": "City of Cape Town open data terms of use",
                  "url": "https://esapqa.capetown.gov.za/agsext/rest/services/Theme_Based/"
                         "ODP_SPLIT_6/FeatureServer/2", "summarise": ["ACQS_MTHD", "ACQS_PRD", "DATA_SRC"]},
}
OPEN_CITIES = "https://data.source.coop/open-cities/ai-challenge/"


def arcgis_in_box(url: str, a: dict, summarise: list) -> dict:
    import requests
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    b = box(*a["box_utm"])
    epsg = int(a["crs"].split(":")[1])
    env = json.dumps({"xmin": b.bounds[0], "ymin": b.bounds[1], "xmax": b.bounds[2], "ymax": b.bounds[3],
                      "spatialReference": {"wkid": epsg}})
    base = {"geometry": env, "geometryType": "esriGeometryEnvelope", "inSR": epsg,
            "spatialRel": "esriSpatialRelIntersects", "f": "json"}
    step = requests.get(url, params={"f": "json"}, timeout=120).json().get("maxRecordCount") or 1000
    geoms, counts, off, n = [], {k: collections.Counter() for k in summarise}, 0, 0
    while True:
        r = requests.get(url + "/query", params={**base, "outFields": ",".join(summarise), "outSR": epsg,
                                                 "resultOffset": off, "resultRecordCount": step}, timeout=300).json()
        fs = r.get("features", [])
        for f in fs:
            n += 1
            for k in summarise:
                counts[k][str(f["attributes"].get(k))] += 1
            rings = (f.get("geometry") or {}).get("rings")
            if rings:
                geoms.append(Polygon(rings[0]).buffer(0))
        off += len(fs)
        if not fs or not r.get("exceededTransferLimit"):
            break
    share = unary_union(geoms).intersection(b).area / b.area if geoms else 0.0
    return {"features": n, "with_geometry": len(geoms), "area_share_of_box": round(share, 4),
            "attributes": {k: dict(c.most_common(10)) for k, c in counts.items()}}


def open_cities_overlap(a: dict) -> list:
    import requests
    from pyproj import Transformer
    from shapely.geometry import box, shape
    from shapely.ops import transform
    b = box(*a["box_utm"])
    to = Transformer.from_crs("EPSG:4326", a["crs"], always_xy=True).transform
    rows = []
    for tier in ("train_tier_1", "train_tier_2", "test"):
        r = requests.get(OPEN_CITIES + f"{tier}/mon/collection.json", timeout=60)
        if r.status_code != 200:
            rows.append({"tier": tier, "monrovia": False})
            continue
        for link in r.json()["links"]:
            if link["rel"] != "item" or "-labels" not in link["href"]:
                continue
            it = requests.get(OPEN_CITIES + f"{tier}/mon/" + link["href"][2:], timeout=60).json()
            ov = transform(to, shape(it["geometry"])).intersection(b).area
            p = it.get("properties", {})
            rows.append({"tier": tier, "item": it["id"], "datetime": p.get("datetime"),
                         "labels_licence": p.get("license"), "overlap_km2": round(ov / 1e6, 4),
                         "share_of_box": round(ov / b.area, 4)})
    return rows


def main():
    from pyproj import Transformer
    from shapely.ops import transform, unary_union
    from ingestion.gee_client import initialize_gee
    from labelling.common import load_config
    initialize_gee()
    cfg = load_config()
    out = {"source": "OpenStreetMap via Overpass API", "licence": "ODbL 1.0", "sites": {}}
    if os.path.exists(OUT):                              # resume: keep sites already done
        with open(OUT) as fh:
            out = json.load(fh)
    for site in SITES:
        if site in out["sites"]:
            continue
        a = cfg["aois"][site]
        b_utm, b_ll = box_ll(a)
        els, prov = overpass(b_ll)
        to_utm = Transformer.from_crs("EPSG:4326", a["crs"], always_xy=True).transform
        geoms, ts, src = [], [], collections.Counter()
        for el in els:
            g = polygons(el)
            if g is None or g.is_empty:
                continue
            g = transform(to_utm, g).intersection(b_utm)
            if g.is_empty:
                continue
            geoms.append(g)
            ts.append(el.get("timestamp", "")[:10])
            tags = el.get("tags", {})
            src[tags.get("source") or tags.get("source:geometry") or "(no source tag)"] += 1
        ts = sorted(t for t in ts if t)
        share = unary_union(geoms).area / b_utm.area if geoms else 0.0
        row = {"osm_buildings": len(geoms), "osm_area_share_of_box": round(share, 4),
               "open_buildings_v3_area_share_of_box": round(open_buildings_share(a), 4),
               "last_edit": {"min": ts[0] if ts else None, "median": ts[len(ts) // 2] if ts else None,
                             "max": ts[-1] if ts else None,
                             "by_year": dict(sorted(collections.Counter(t[:4] for t in ts).items()))},
               "source_tags_top": src.most_common(8)}
        row["queried_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        row.update(prov)                                 # mirrors can lag: record which answered
        out["sites"][site] = row
        with open(OUT, "w") as fh:
            json.dump(out, fh, indent=1)
        print(site, json.dumps(row), flush=True)
        time.sleep(10)                                   # be polite to the public Overpass instance
    if "city_datasets" not in out:
        out["city_datasets"] = {}
        for site, c in CITY.items():
            out["city_datasets"][site] = {"name": c["name"], "licence": c["licence"], "service": c["url"],
                                          **arcgis_in_box(c["url"], cfg["aois"][site], c["summarise"])}
            print(site, json.dumps(out["city_datasets"][site])[:600], flush=True)
    if "open_cities_monrovia" not in out:
        oc = open_cities_overlap(cfg["aois"]["monrovia"])
        out["open_cities_monrovia"] = {
            "imagery_licence": "CC BY 4.0", "catalog": OPEN_CITIES, "labels": oc,
            "total_overlap_share_of_box": round(sum(r.get("share_of_box", 0) for r in oc), 4)}
        print("open_cities", json.dumps(out["open_cities_monrovia"])[:600], flush=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1)
    print(OUT)


if __name__ == "__main__":
    main()
