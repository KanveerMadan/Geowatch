"""
Item 21 measurement A (2026-09-25): high-resolution imagery inventory for
every item 21 site. Inventory only -- this script CHOOSES NO SOURCE.

For each site it lists every candidate scene from:
  - OpenAerialMap (api.openaerialmap.org/meta, bbox query)
  - Maxar Open Data (STAC, maxar-opendata.s3.amazonaws.com/events)
  - the source recorded for the site in 05_BUILD_MANUAL.md item 21 "Site
    list", where it is in neither catalogue (Cape Town, Rocinha)

and, per scene, Sentinel-2 L2A availability near its acquisition date:
S2_SR_HARMONIZED scenes over the scene/site overlap centroid with
CLOUDY_PIXEL_PERCENTAGE < 20 (the convention used by the site list), within
+-30 / 60 / 90 days, and the nearest such scene.

SEARCH_BBOXES bound the catalogue query only: the named settlement for the
validation sites, the metro area for the city-level training sites.

    python experiments/item21_sites/inventory.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta

import requests

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# (west, south, east, north) -- query windows, not AOIs.
SEARCH_BBOXES = {
    "cape_town": (18.30, -34.20, 18.95, -33.70),
    "lima":      (-77.20, -12.30, -76.70, -11.75),
    "karachi":   (66.85, 24.75, 67.35, 25.10),
    "monrovia":  (-10.85, 6.23, -10.70, 6.37),
    "marrakech": (-8.10, 31.55, -7.90, 31.70),
    "makoko":    (3.37, 6.47, 3.42, 6.52),
    "kibera":    (36.76, -1.33, 36.81, -1.29),
    "rocinha":   (-43.262, -22.995, -43.238, -22.978),
}
ROLE = {"makoko": "validation", "kibera": "validation", "rocinha": "validation"}

# Recorded in 05_BUILD_MANUAL.md item 21 "Site list" and not in either
# catalogue. Times are what the publisher states; None = not published there.
RECORDED_ONLY = {
    # Both listed as ImageServer services at cityimg.capetown.gov.za
    # (checked 2026-09-25); the services return no machine-readable date,
    # time or description. The portal terms page carries only an "as is"
    # disclaimer; licence detail is in the 2020 Open Data Policy PDF.
    "cape_town": [{
        "catalogue": "recorded (City of Cape Town)",
        "title": "City of Cape Town aerial imagery, 'Aerial Imagery 2026Jan'",
        "acquisition": "2026-01 (month only, as recorded)", "time_utc": None,
        "resolution_m": 0.05,
        "licence": "City of Cape Town: 'no restrictions on the digital file for "
                   "non-commercial purposes' (as recorded 2026-09-24; not "
                   "re-verified 2026-09-25)",
        "footprint_bbox": None, "date_for_s2": "2026-01-15"}, {
        "catalogue": "City of Cape Town image service",
        "title": "City of Cape Town aerial imagery, 'Aerial Imagery 2025Jan'",
        "acquisition": "2025-01 (month only, from the service name)", "time_utc": None,
        "resolution_m": None,
        "licence": "same portal and terms as 2026Jan (not separately verified)",
        "footprint_bbox": None, "date_for_s2": "2025-01-15"}],
    # IPP ImageServer description (2026-09-25): "Aquisição 1º semestre de
    # 2024", 15 cm, RGB, LiDAR flight; no per-raster date or time; catalogue
    # query unsupported.
    "rocinha": [{
        "catalogue": "recorded (Rio IPP)",
        "title": "IPP city true-orthophoto mosaic, Imagens/Mosaico_2024",
        "acquisition": "first half of 2024 (as recorded)", "time_utc": None,
        "resolution_m": 0.15,
        "licence": "IPP: non-commercial; commercial use needs IPP's prior written "
                   "authorisation (as recorded 2026-09-24)",
        "footprint_bbox": None, "date_for_s2": "2024-04-01"}],
}

UA = {"User-Agent": "GeoWatch/1.0 (research; https://github.com/KanveerMadan/Geowatch)"}
MAXAR = "https://maxar-opendata.s3.amazonaws.com/events/"


def _get(url):
    for i in range(4):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if i == 3:
                raise
            time.sleep(2 * (i + 1))


def overlaps(a, b):
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def overlap_centroid(a, b):
    w, s, e, n = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return ((w + e) / 2, (s + n) / 2)


def oam(site, bbox):
    out, page = [], 1
    while True:
        q = f"https://api.openaerialmap.org/meta?bbox={','.join(map(str, bbox))}&limit=100&page={page}"
        d = _get(q)
        for r in d["results"]:
            p = r.get("properties", {})
            fb = r["geojson"]["bbox"] if r.get("geojson") else r.get("bbox")
            out.append({
                "catalogue": "OpenAerialMap", "id": r["_id"], "title": r.get("title"),
                "provider": r.get("provider"), "platform": r.get("platform"),
                "sensor": p.get("sensor"),
                "acquisition_start_utc": r.get("acquisition_start"),
                "acquisition_end_utc": r.get("acquisition_end"),
                "resolution_m": p.get("resolution_in_meters") or r.get("gsd"),
                "licence": p.get("license") or d["meta"].get("license"),
                "footprint_bbox": fb,
                "date_for_s2": (r.get("acquisition_start") or "")[:10] or None,
            })
        if page * 100 >= d["meta"]["found"]:
            return out
        page += 1


def maxar(site, bbox, events):
    out = []
    for ev in events:
        coll = _get(MAXAR + ev)
        if not overlaps(coll["extent"]["spatial"]["bbox"][0], bbox):
            continue
        base = MAXAR + ev.rsplit("/", 1)[0] + "/"
        for link in coll["links"]:
            if link["rel"] != "child":
                continue
            acq = _get(base + link["href"][2:])
            boxes = acq["extent"]["spatial"]["bbox"]
            if not any(overlaps(b, bbox) for b in boxes):
                continue
            acq_base = (base + link["href"][2:]).rsplit("/", 1)[0] + "/"
            item = None
            for il in acq["links"]:
                if il["rel"] != "item":
                    continue
                it = _get(acq_base + il["href"])
                if overlaps(it["bbox"], bbox):
                    item = it
                    break
            if item is None:
                continue
            pr = item["properties"]
            u = [min(b[0] for b in boxes), min(b[1] for b in boxes),
                 max(b[2] for b in boxes), max(b[3] for b in boxes)]
            out.append({
                "catalogue": "Maxar Open Data", "event": coll["id"], "id": acq["id"],
                "title": coll.get("title"), "platform": pr.get("platform"),
                "acquisition_start_utc": acq["extent"]["temporal"]["interval"][0][0],
                "acquisition_end_utc": acq["extent"]["temporal"]["interval"][0][1],
                "resolution_m": pr.get("gsd"),
                "sun_elevation_deg": pr.get("view:sun_elevation"),
                "sun_azimuth_deg": pr.get("view:sun_azimuth"),
                "off_nadir_deg": pr.get("view:off_nadir"),
                "clouds_percent_first_overlapping_tile": pr.get("tile:clouds_percent"),
                "licence": coll.get("license"),
                "licence_acquisition_collection": acq.get("license"),
                "footprint_bbox": u,
                "date_for_s2": acq["extent"]["temporal"]["interval"][0][0][:10],
            })
    return out


def s2_availability(point, date_str):
    import ee
    d = datetime.fromisoformat(date_str)
    pt = ee.Geometry.Point(point)
    col = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(pt)
           .filterDate((d - timedelta(days=90)).strftime("%Y-%m-%d"),
                       (d + timedelta(days=91)).strftime("%Y-%m-%d"))
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20)))
    dates = sorted({datetime.utcfromtimestamp(t / 1000).date()
                    for t in col.aggregate_array("system:time_start").getInfo()})
    gaps = [abs((x - d.date()).days) for x in dates]
    return {"clear_scenes_pm30": sum(g <= 30 for g in gaps),
            "clear_scenes_pm60": sum(g <= 60 for g in gaps),
            "clear_scenes_pm90": sum(g <= 90 for g in gaps),
            "nearest_clear_gap_days": min(gaps) if gaps else None,
            "rule": "scenes with CLOUDY_PIXEL_PERCENTAGE < 20 (scene-level, not per pixel)"}


def main(sites=None):
    """sites: re-run only these and merge into an existing results file."""
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    cat = _get(MAXAR + "catalog.json")
    events = [l["href"][2:] for l in cat["links"] if l["rel"] == "child"]
    path = os.path.join(OUT, "imagery_inventory.json")
    if sites and os.path.exists(path):
        with open(path) as fh:
            result = json.load(fh)
    else:
        result = {"sites": {}}
    result.update({"generated_utc": datetime.utcnow().isoformat() + "Z",
                   "search_bboxes": SEARCH_BBOXES, "maxar_events_scanned": len(events)})
    for site, bbox in SEARCH_BBOXES.items():
        if sites and site not in sites:
            continue
        print(f"== {site}", flush=True)
        scenes = oam(site, bbox) + maxar(site, bbox, events) + RECORDED_ONLY.get(site, [])
        for sc in scenes:
            fb = sc.get("footprint_bbox")
            pt = overlap_centroid(fb, bbox) if fb else ((bbox[0] + bbox[2]) / 2,
                                                        (bbox[1] + bbox[3]) / 2)
            sc["s2"] = (s2_availability(pt, sc["date_for_s2"]) if sc.get("date_for_s2")
                        else {"status": "no acquisition date"})
            print(f"   {sc['catalogue']:18s} {sc.get('acquisition_start_utc') or sc.get('acquisition')} "
                  f"{sc.get('resolution_m')} {sc.get('title')}", flush=True)
        result["sites"][site] = {"role": ROLE.get(site, "training"), "scenes": scenes}
    os.makedirs(OUT, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(result, fh, indent=1)
    print(path)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
