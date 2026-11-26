"""Screen public scene metadata. No pixel, thumbnail or reference-map requests."""
import argparse
import csv
import hashlib
import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from pyproj import CRS, Transformer
from requests.adapters import HTTPAdapter
from shapely.geometry import Polygon, shape
from urllib3.util.retry import Retry

HERE = Path(__file__).resolve().parent
STAC = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
OPTICAL = ("landsat-c2-l2", "sentinel-2-l2a")
IDENTITY_FIELDS = ("type", "subtype", "country", "reach", "zone", "latitude", "longitude", "location_source")


def write_file(path, data):
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(data)
    Path(tmp.name).replace(path)


def study_box(lon, lat):
    local = CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m")
    trans = Transformer.from_crs(local, "EPSG:4326", always_xy=True)
    return Polygon([trans.transform(x,y) for x,y in
                    [(-4000,-4000), (4000,-4000), (4000,4000), (-4000,4000)]])


def crest_interval(day, zone):
    zone = ZoneInfo(zone)
    day = date.fromisoformat(day)
    return tuple(datetime.combine(d, time.min, zone).astimezone(timezone.utc)
                 for d in (day, day + timedelta(days=1)))


def query(session, cache, coll, box, start, end):
    # Download inventory fields only. The cache contains neither images nor asset URLs.
    fields = "id,collection,geometry,properties.datetime,properties.sar:instrument_mode,properties.sar:polarizations,properties.sat:relative_orbit,properties.sat:orbit_state"
    params = dict(collections=coll, bbox=",".join(map(str,box.bounds)),
                  datetime=f"{start.isoformat()}/{end.isoformat()}", fields=fields, limit=500)
    key = hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()
    receipt = cache / (key + ".json")
    if receipt.exists():
        return json.loads(receipt.read_text())["scenes"]
    url, scenes = STAC, {}
    seen = set()
    while url:
        r = session.get(url, params=params, timeout=(10,60))
        r.raise_for_status()
        if r.url in seen:
            raise ValueError("Repeated STAC page")
        seen.add(r.url)
        page = r.json()
        for item in page["features"]:
            if not shape(item["geometry"]).covers(box):
                continue
            props = item["properties"]
            scenes[item["id"]] = dict(id=item["id"], collection=coll, utc=props["datetime"],
                orbit=props.get("sat:relative_orbit"), direction=props.get("sat:orbit_state"),
                mode=props.get("sar:instrument_mode"), pol=props.get("sar:polarizations",[]))
        nxt = next((x for x in page["links"] if x["rel"]=="next"),None)
        url = nxt["href"] if nxt else None
        if url and (urlparse(url).netloc != "planetarycomputer.microsoft.com" or
                    urlparse(url).path != "/api/stac/v1/search" or nxt.get("method","GET")!="GET"):
            raise ValueError("Unexpected STAC pagination endpoint")
        params = None
    result = sorted(scenes.values(),key=lambda item:(item["utc"],item["id"]))
    write_file(receipt,json.dumps({"scenes":result},sort_keys=True))
    return result


def radar_pair(a, b):
    return (a["mode"]==b["mode"]=="IW" and a["orbit"] is not None and
            a["orbit"]==b["orbit"] and a["direction"] and a["direction"]==b["direction"] and
            "VV" in a["pol"] and "VV" in b["pol"])


def late_hours(site):
    """Latest image after the crest (DECISIONS 2026-11-27): 72 h for sustained M8 melt,
    48 h (same or next day) for M6, M7 and ice-jam releases."""
    return 72 if site["type"]=="M8" and "ice jam" not in site["subtype"] else 48


def crest_bounds(event, site, gauge):
    """(lo, hi, kind): the UTC interval that contains the crest, in order of preference."""
    if gauge.get("status") == "gauge_bracket":
        return (*(datetime.fromisoformat(gauge[key]) for key in ("start","end")), "gauge_bracket")
    if event.get("crest_utc_bracket"):
        lo,hi = (datetime.fromisoformat(x) for x in event["crest_utc_bracket"])
        return lo,hi,"published_reading"
    if event.get("crest_date"):
        return (*crest_interval(event["crest_date"],site["zone"]), event.get("crest_kind","published_day"))
    if gauge.get("status") == "geoglows_day":
        return (*(datetime.fromisoformat(gauge[key]) for key in ("start","end")), "geoglows_day")
    raise ValueError("no crest evidence")


def screen(event, site, gauge, session, cache):
    lo,hi,kind = crest_bounds(event,site,gauge)
    box = study_box(site["longitude"],site["latitude"])
    late = late_hours(site)
    # Intersection over *all* possible peak timestamps. The reported local day is
    # [lo, hi); retaining the limiting endpoint is conservative at its boundary.
    start, end = hi-timedelta(hours=24), lo+timedelta(hours=late)
    if event.get("not_before_utc"):
        # Levee breach: before the breach the protected land is dry by construction.
        start = max(start, datetime.fromisoformat(event["not_before_utc"]))
    scenes = []
    for collection in OPTICAL+("sentinel-1-grd",):
        for item in query(session,cache,collection,box,start,end):
            observed = datetime.fromisoformat(item["utc"].replace("Z","+00:00"))
            if not start <= observed <= end:
                continue
            record = {"collection":collection,"scene":item["id"],"utc":item["utc"],
                      "lag_hours_min":(observed-hi).total_seconds()/3600,
                      "lag_hours_max":(observed-lo).total_seconds()/3600}
            if collection=="sentinel-1-grd":
                t0 = crest_interval(event["date"],site["zone"])[0]
                record["baseline"] = []
                for yr in (0,1):
                    # The historical fallback is the same calendar window a year earlier.
                    anchor = t0.replace(year=t0.year-yr,day=min(t0.day,28)) if t0.month==2 and t0.day==29 and yr else t0.replace(year=t0.year-yr)
                    pool = query(session,cache,collection,box,anchor-timedelta(days=60),anchor-timedelta(days=6))
                    matching = [b for b in pool if radar_pair(item,b)]
                    if len({b["utc"][:10] for b in matching})>=2:
                        record["baseline"] = [b["id"] for b in matching]
                        break
            scenes.append(record)
    scenes.sort(key=lambda x:(x["utc"],x["scene"]))
    return {"crest_utc_min":lo.isoformat(),"crest_utc_max":hi.isoformat(),"crest_kind":kind,
            "window_utc":[start.isoformat(),end.isoformat()],"bbox_wgs84":box.bounds,"scenes":scenes}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cache",type=Path)
    ap.add_argument("--output",type=Path,default=HERE)
    args=ap.parse_args()
    args.cache.mkdir(exist_ok=True,parents=True)
    data=json.loads((HERE/"event_evidence.json").read_text())
    gauges=json.loads((HERE/"gauge_metadata.json").read_text())
    gp=HERE/"geoglows_crests.json"
    geoglows=json.loads(gp.read_text()) if gp.exists() else {}
    if tuple(data["site_fields"])!=IDENTITY_FIELDS:
        raise ValueError("Unknown site schema")
    session=requests.Session()
    session.mount("https://",HTTPAdapter(max_retries=Retry(total=3,backoff_factor=1,
        status_forcelist=(429,500,502,503,504),allowed_methods={"GET"})))
    records,receipts=[],{}
    for event in data["events"]:
        site=dict(zip(IDENTITY_FIELDS,data["sites"][event["site"]],strict=True))
        eid=event["site"]+"-"+event["date"]
        if eid in receipts or any(row["incident_id"]==eid for row in records):
            raise ValueError("Duplicate incident ID")
        split="DEV" if date.fromisoformat(event["date"]).year<2022 else "reserve_candidate"
        row=dict(incident_id=eid,split=split,type=site["type"],subtype=site["subtype"],
                 date=event["date"],country=site["country"],reach=site["reach"],
                 latitude=site["latitude"],longitude=site["longitude"],crest_utc_min="",
                 crest_utc_max="",optical_scenes="",paired_radar_scenes="",
                 screening="excluded" if event.get("excluded") else "needs_reach_or_crest",
                 source=event["source"],peak_source=event.get("peak_source",""),
                 location_source=site["location_source"],note=event["note"],cluster="",crest_kind="")
        gauge=gauges.get(eid,{})
        if gauge.get("status")!="gauge_bracket" and geoglows.get(eid,{}).get("status")=="geoglows_day":
            gauge=geoglows[eid]
        row["cluster"]=data.get("clusters",{}).get(event["site"],event["site"])
        if gauge.get("status")=="published_day_and_gauge_disagree":
            row["screening"]="crest_sources_disagree"
        elif (event.get("crest_date") or event.get("crest_utc_bracket") or gauge.get("status") in ("gauge_bracket","geoglows_day")) \
                and site["latitude"] is not None and not event.get("excluded"):
            evidence=screen(event,site,gauge,session,args.cache)
            receipts[eid]=evidence
            usable=evidence["scenes"]
            optical=sum(s["collection"] in OPTICAL for s in usable)
            radar=sum(bool(s.get("baseline")) for s in usable)
            row.update(crest_utc_min=evidence["crest_utc_min"],
                       crest_utc_max=evidence["crest_utc_max"],
                       optical_scenes=optical,paired_radar_scenes=radar,
                       crest_kind=evidence["crest_kind"],
                       peak_source=gauge["source"] if gauge.get("status") in ("gauge_bracket","geoglows_day") else event.get("peak_source",event["source"]),
                       screening="timed_footprint" if optical+radar else "no_match_in_queried_catalogue")
        records.append(row)
    records.sort(key=lambda x:(x["type"],x["date"],x["incident_id"]))
    with NamedTemporaryFile("w",encoding="utf-8",newline="",dir=args.output,delete=False) as f:
        writer=csv.DictWriter(f,fieldnames=records[0],lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    write_file(args.output/"scene_metadata.json",json.dumps(receipts,indent=2,sort_keys=True)+"\n")
    Path(f.name).replace(args.output/"catalog.csv")


if __name__=="__main__":
    main()
