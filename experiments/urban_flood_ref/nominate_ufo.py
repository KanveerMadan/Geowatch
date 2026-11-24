"""Metadata-only extension of the pre-2022 non-US manual-label pool.

Two chips per city, ordered by distance to the stated city centre and selected
without overlap. No label bytes are touched. Human review of incident aliases and
the full guard are required before publishing the resulting allowlist.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import zipfile
import ee
import requests
from .guard import excluded,connected,registry,metadata
from .ufo import RangeReader,RECORD,PRODUCT

# Incident and acquisition metadata in Mukherjee et al., table 1. The day used
# to query SAR is explicitly the optical observation day where the onset is broad.
CITIES={'CTO':('Can Tho','VN','can_tho_2019_tidal',105.782,10.034,'20191002'),
        'KTM':('Khartoum','SD','nile_khartoum_2020',32.541,15.610,'20200829'),
        'SPS':('San Pedro Sula','HN','iota_2020',-88.027,15.501,'20201125')}


def plan(output):
    f=next(x for x in requests.get(RECORD,timeout=30).json()['files'] if x['key']==PRODUCT)
    accepted=[]
    with zipfile.ZipFile(RangeReader(f['links']['self'],f['size'])) as archive:
        names=archive.namelist()
        for prefix,(city,country,storm,x,y,stamp) in CITIES.items():
            options=[]
            for n in sorted(names):
                if '/items/'+prefix+'_'+stamp+'_' not in n or not n.endswith('.json'):continue
                item=json.loads(archive.read(n));w,s,e,north=item['bbox']
                d=((w+e)/2-x)**2+((s+north)/2-y)**2
                options.append((d,item['id'],item))
            kept=[]
            for _,_,item in sorted(options,key=lambda a:a[:2]):
                box=item['bbox']
                if any(registry._intersects(box,v) for v in kept):continue
                iso=item['properties']['datetime'][:10];label=item['id']
                probe={'event_id':label,'products':['UFO:'+label],'storm_cluster':storm,'geometry':{'type':'boxes','boxes':[{'bbox':box}]}}
                if any(connected(probe,r) for r in excluded()):continue
                accepted.append({'unit':prefix.lower()+'_ufo_'+label.split('_')[-1],'city':city,'country':country,'incident':storm,
                          'date':iso,'peak_date':None,'bbox':box,'ufo_item':label,'ufo_date':iso,'products':['S1','UFO:'+label],
                          'evidence_url':'https://doi.org/10.5281/zenodo.19698577',
                          'basis':'Optical observation date anchors SAR. Supplemental development chip selected by archive footprint and distance to documented city centre; no label inspected in selection.'})
                kept.append(box)
                if len(kept)==2:break
    with open('/private/tmp/geowatch-change-round2-ee.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);ee.Initialize(project=os.environ['GEE_PROJECT_ID']); col=ee.FeatureCollection('WWF/HydroSHEDS/v1/Basins/hybas_6')
        for r in accepted:
            w,s,e,n=r['bbox'];center=col.filterBounds(ee.Geometry.Point([(w+e)/2,(s+n)/2]))
            tile=col.filterBounds(ee.Geometry.Rectangle([w-.002,s-.002,e+.002,n+.002],geodesic=False))
            data=ee.Dictionary({'centers':center.aggregate_array('HYBAS_ID'),'main':center.aggregate_array('MAIN_BAS'),
                   'hybas_6':tile.aggregate_array('HYBAS_ID'),'main_bas':tile.aggregate_array('MAIN_BAS')}).getInfo()
            if len(data['centers'])==1:
                r['basins']={'main_bas':data['main'][0],'hybas_6':data['centers'][0]};r['basin_intersections']={k:data[k] for k in ('main_bas','hybas_6')}
    good=[r for r in accepted if r.get('basins') and not any(
        old.get('basins',{}).get(k) in r['basin_intersections'][k] for old in excluded() for k in ('main_bas','hybas_6'))]
    Path(output).write_text(json.dumps(good,indent=2)+'\n')
    print([(r['unit'],r['city'],r['date']) for r in good])

if __name__=='__main__':
    ap=argparse.ArgumentParser(__doc__);ap.add_argument('output');plan(ap.parse_args().output)
