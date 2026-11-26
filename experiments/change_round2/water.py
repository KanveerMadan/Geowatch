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
    for (source,track),group in grouped.items():
        group=sorted(group,key=lambda r:r["day"])
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
                evidence[name].append((r["day"],source,track,positive))
    for name,events in evidence.items():
        result["candidates"].extend({"day":d,"source":s,"track":t,"target":name} for d,s,t,p in events if p)
        # Confirm within a single track on distinct days, or by independent
        # optical and radar observations. A normal observation resets its track.
        previous={}
        latest_look={}
        confirmed=set()
        for day,src,track,pos in sorted(events):
            key=(src,track)
            current=date.fromisoformat(day)
            def has_pair(prior):
                return any((oldkey[0]!=src or (oldkey==key and current!=old_day))
                           and (current-old_day).days<=24 for oldkey,old_day in prior.items())
            if name not in result["observed_targets"] and has_pair(latest_look):
                result["observed_targets"].append(name)
            latest_look[key]=current
            if pos:
                if has_pair(previous):
                    confirmed.add(day)
                previous[key]=current
            else:
                previous.pop(key,None)
        result[name]=sorted(confirmed)
    result["observed"]=bool(result["observed_targets"])
    return result
