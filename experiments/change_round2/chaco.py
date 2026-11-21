"""Trace every Chaco miss using the frozen detector and original development inputs."""
from collections import defaultdict
from datetime import date
from pathlib import Path
import numpy as np
from vector import change_detection as old
from experiments.change_history import known_change
from .data import HERE, read, save

def main():
    root=Path("/private/tmp/gw-known-lock-2021")
    folders=list(root.glob("*/*/chaco_paraguay"))
    if len(folders)!=1: raise ValueError("supply original known-change checkpoint in /private/tmp/gw-known-lock-2021")
    values=defaultdict(list)
    for path in folders[0].glob("block-*.json"):
        for key,rows in read(path).items(): values[key]+=rows
    start=date(2021,1,1); end=date(2022,1,1); cfg=old.DetectionConfig()
    misses=[]
    for key,raw in sorted(values.items()):
        obs=[dict(date=r[0],source="sentinel2",track=r[1],support_id=key,values=dict(zip(known_change.SIGNALS,r[2:]))) for r in raw]
        d=old.detect_cell(key,obs,start=start,end=end)
        if any(e["transition"]=="greenness_loss" and e["confirmed_on"] for e in d["events"]): continue
        groups=old._groups(obs,date(2016,1,1),date(2021,12,31))
        prepared=[(k,*old._prepare(k,v,start.toordinal(),end.toordinal(),cfg)) for k,v in sorted(groups.items())]
        scale,*_=old._family_envelope(prepared,start.toordinal(),end.toordinal(),cfg)
        traces=[]
        for k,info,inputs in prepared:
            if info["signal"]!="ndvi" or inputs is None:continue
            days,v,model=inputs
            ix=days>=start.toordinal()
            if not ix.any():continue
            origin,beta,inv,envelope,*_=model
            X=old._design(days[ix],origin,cfg.harmonics)
            threshold=envelope*scale*np.sqrt(1+np.einsum("ij,jk,ik->i",X,inv,X))
            deficit=(X@beta-v[ix])/threshold
            traces.append({"track":info["track"],"looks":int(ix.sum()),"crossings":int((deficit>1+1e-12).sum()),
                           "peak_fraction_of_threshold":float(deficit.max()),"peak_day":date.fromordinal(int(days[ix][deficit.argmax()])).isoformat()})
        candidates=sum(e["transition"]=="greenness_loss" for e in d["events"])
        reason=("no fitted NDVI track" if not traces else "never crossed local envelope" if not any(t["crossings"] for t in traces)
                else "departures did not form a confirmed episode")
        misses.append(dict(cell=key,reason=reason,unconfirmed_episodes=candidates,tracks=traces))
    assert len(misses)==13
    save(HERE/"chaco_misses.json",misses)
if __name__=="__main__":main()
