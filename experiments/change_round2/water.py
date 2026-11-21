"""Evidence for new or lost open water, frozen per query and track."""
from collections import defaultdict
from datetime import date
import statistics as st


def water(rows,start,end,permanent):
    result={"gain":[],"loss":[],"observed":False,"observed_targets":[],"candidates":[]}
    if permanent is None:
        return result
    grouped=defaultdict(list)
    for r in rows:
        if r["day"]<end:
            grouped[(r["source"],r["track"])].append(r)
    evidence=defaultdict(list)
    looks=defaultdict(set)
    for (source,track),group in grouped.items():
        past=[r for r in group if r["day"]<start][-12:]
        if len(past)<3:
            continue
        radar=source=="radar"
        field="VV" if radar else "water"
        values=[r[field] for r in past]
        base=st.median(values)
        spread=1.4826*st.median(abs(v-base) for v in values)
        base_vh=st.median(r["VH"] for r in past) if radar else None
        for r in group:
            if r["day"]<start: continue
            delta=r[field]-base
            if radar:
                wet=r["VV"]<=-15 and r["VH"]<=-21
                prior_wet=base<=-15 and base_vh<=-21
                gain=wet and delta<=-max(3,2*spread) and r["VH"]<=base_vh-1
                loss=prior_wet and not wet and delta>=max(3,2*spread) and r["VH"]>=base_vh+1
            else:
                gain=r[field]>0 and base<=0 and delta>=max(.15,2*spread)
                loss=r[field]<=0 and base>0 and -delta>=max(.15,2*spread)
            for name,positive in (("gain",gain),("loss",loss)):
                if name=="gain" and permanent>=.8:
                    continue
                looks[name].add(r["day"])
                evidence[name].append((r["day"],source,track,positive))
    for name,events in evidence.items():
        result["candidates"].extend({"day":d,"source":s,"track":t,"target":name} for d,s,t,p in events if p)
        # Confirm within a single track on distinct days, or by independent
        # optical and radar observations. A normal observation resets its track.
        previous={}
        confirmed=set()
        for day,src,track,pos in sorted(events):
            key=(src,track)
            if pos:
                if any((oldkey==key and oldday!=day or oldkey[0]!=src) and
                       (date.fromisoformat(day)-date.fromisoformat(oldday)).days<=24
                       for oldkey,oldday in previous.items()):
                    confirmed.add(day)
                previous[key]=day
            else:
                previous.pop(key,None)
        result[name]=sorted(confirmed)
        if len(looks[name])>=2:
            result["observed_targets"].append(name)
    result["observed"]=bool(result["observed_targets"])
    return result
