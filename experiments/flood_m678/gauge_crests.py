"""Extract crest brackets from approved public USGS gauge observations, metadata only."""
import argparse
import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from screen_acquisitions import HERE, crest_interval, write_file

ENDPOINT = "https://api.waterdata.usgs.gov/ogcapi/v0/collections/continuous/items"


def bracket(features, lo, hi):
    groups = {}
    for feature in features:
        p=feature["properties"]
        # "REVISED" marks an approved value that was revised before approval; it is not a quality flag.
        if p["approval_status"]!="Approved" or [q for q in (p["qualifier"] or []) if q!="REVISED"] or p["value"] is None:
            continue
        if p["parameter_code"]!="00065" or p["unit_of_measure"]!="ft":
            continue
        t=datetime.fromisoformat(p["time"])
        groups.setdefault(p["time_series_id"],{})[t]=float(p["value"])
    if len(groups)!=1:
        return {"status":"no_unambiguous_approved_series"}
    series=next(iter(groups.values()))
    times=sorted(series)
    if len(times)<3:
        return {"status":"insufficient_gauge_observations"}
    steps=[b-a for a,b in zip(times,times[1:])]
    cadence=Counter(steps).most_common(1)[0][0]
    top=max(series.values())
    indices=[i for i,t in enumerate(times) if series[t]==top]
    first,last=indices[0],indices[-1]
    if times[0]>lo+cadence or times[-1]<hi-cadence or max(steps)>cadence:
        return {"status":"gap_in_gauge_record","observed_max_start":times[first].isoformat(),
                "observed_max_end":times[last].isoformat()}
    if first==0 or last==len(times)-1:
        return {"status":"crest_unbounded"}
    return {"status":"gauge_bracket","start":times[first-1].isoformat(),
            "end":times[last+1].isoformat(),"gauge_max_ft":top,
            "sample_seconds":cadence.total_seconds(),"observations":len(times),
            "series_id":next(iter(groups))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cache",type=Path)
    args=parser.parse_args()
    args.cache.mkdir(exist_ok=True,parents=True)
    data=json.loads((HERE/"event_evidence.json").read_text())
    out={}
    for event in data["events"]:
        gauge=event.get("stage_gauge")
        if not gauge:
            continue
        site=data["sites"][event["site"]]
        begin,end=event["stage_search_local_days"]
        lo=crest_interval(begin,site[4])[0]
        hi=crest_interval(end, site[4])[1]
        params=dict(monitoring_location_id="USGS-"+gauge,parameter_code="00065",
                    datetime=f"{lo.isoformat()}/{hi.isoformat()}",f="json",limit=10000)
        cache=args.cache/f"{gauge}-{begin}-{end}.json"
        if not cache.exists():
            r=requests.get(ENDPOINT,params=params,timeout=(15,90))
            r.raise_for_status()
            page=r.json()
            if any(x["rel"]=="next" for x in page.get("links",[])):
                raise ValueError("Incomplete gauge response")
            if any(x["properties"]["monitoring_location_id"]!="USGS-"+gauge for x in page["features"]):
                raise ValueError("Unexpected gauge in response")
            write_file(cache,json.dumps(page["features"]))
        result=bracket(json.loads(cache.read_text()),lo,hi)
        if result["status"]=="gap_in_gauge_record" and event.get("crest_date"):
            a,b=crest_interval(event["crest_date"],site[4])
            if datetime.fromisoformat(result["observed_max_end"])<a or datetime.fromisoformat(result["observed_max_start"])>=b:
                result["status"]="published_day_and_gauge_disagree"
        if result["status"]=="gauge_bracket" and event.get("crest_date"):
            a,b=crest_interval(event["crest_date"],site[4])
            if datetime.fromisoformat(result["end"]) < a or datetime.fromisoformat(result["start"]) >= b:
                result={"status":"published_day_and_gauge_disagree"}
        eid=event["site"]+"-"+event["date"]
        out[eid]={**result,"station":gauge,"source":requests.Request("GET",ENDPOINT,params=params).prepare().url}
    write_file(HERE/"gauge_metadata.json",json.dumps(out,indent=2,sort_keys=True)+"\n")


if __name__=="__main__":
    main()
