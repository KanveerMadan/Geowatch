"""Persistent departures from a same-track, same-season vegetation baseline."""
from collections import defaultdict
from datetime import date
from statistics import median

def forest(rows,start,end,forest_share=None):
    if forest_share is None or forest_share < .5:
        reason="missing_forest_reference" if forest_share is None else "outside_prior_forest"
        return {"confirmed":[],"observed_sources":[],"candidates":[],"domain":reason}

    series=defaultdict(list)
    for r in rows:
        if r["day"]<end: series[(r["source"],r["track"])].append(r)
    hits=[]; candidates=[]; valid=set()
    for (source,track),group in series.items():
        group=sorted(group,key=lambda r:r["day"])
        past=[r for r in group if r["day"]<start]
        recent=[]
        for r in group:
            if r["day"]<start: continue
            d=date.fromisoformat(r["day"])
            def distance(h):
                diff=abs(date.fromisoformat(h["day"]).timetuple().tm_yday-d.timetuple().tm_yday)
                return min(diff,366-diff)
            seasonal=[h for h in past if distance(h)<=45]
            if len(seasonal)<5: continue
            radar=source=="radar"; field="VH" if radar else "ndvi"
            base=median(h[field] for h in seasonal)
            mad=1.4826*median(abs(h[field]-base) for h in seasonal)
            change=base-r[field]
            depart=change>=max(1.5*mad,2 if radar else .08)
            if radar:
                # Require corroboration from co-polar power or patch texture.
                vv=median(h["VV"] for h in seasonal)
                texture=median(h["texture"] for h in seasonal)
                depart=depart and (vv-r["VV"]>=1 or abs(texture-r["texture"])>=1)
            else:
                depart=depart and base>=.4
            recent=[p for p in recent if (d-p[0]).days<=60][-5:]+[(d,depart)]
            if depart: candidates.append({"day":r["day"],"source":source,"track":track})
            if len(recent)>=4: valid.add(source)
            if depart and sum(flag for _,flag in recent)>=4:
                hits.append({"day":r["day"],"source":source,"track":track})
    return {"confirmed":sorted(hits,key=lambda h:h["day"]),"observed_sources":sorted(valid),"candidates":candidates,"domain":"prior_forest"}
