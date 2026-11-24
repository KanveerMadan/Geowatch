"""Export only the historical STN mark IDs and their linked, possibly estimated peak times."""
import csv
from datetime import datetime
from pathlib import Path
import requests
ROOT='https://services7.arcgis.com/M1GdIfrBNFtdTD7r/arcgis/rest/services/'
SERVICES={'Harvey':('USGS_Harvey_HWM_Peaks',180),'Irma':('USGS_Irma_HWM_Group',182)}


def rows(url,fields,where):
    args={'where':where,'f':'json'}
    r=requests.get(url,params={**args,'returnIdsOnly':'true'},timeout=45)
    r.raise_for_status()
    ids=r.json()['objectIds']
    for start in range(0,len(ids),200):
        r=requests.get(url,params={**args,'outFields':fields,'objectIds':','.join(map(str,ids[start:start+200])),
                                   'returnGeometry':'false'},timeout=45)
        r.raise_for_status()
        yield from (item['attributes'] for item in r.json()['features'])


def export(path):
    with Path(path).open('w') as out:
        w=csv.writer(out,lineterminator='\n')
        w.writerow(['storm','mark_id','source_peak_utc','estimated_time'])
        for name,(service,code) in SERVICES.items():
            base=ROOT+service+'/FeatureServer/'
            # Both layer 1 tables are dedicated to the named 2017 storm.
            key,flag=('peak_summa','is_peak_ti') if name=='Harvey' else ('peak_summary_id','is_peak_time_estimated')
            dates={r[key]:r for r in rows(base+'1/query',f'{key},peak_date,time_zone,{flag}','1=1')}
            for mark in rows(base+'2/query',f'hwm_id,{key}',f'event_id={code}'):
                r=dates.get(mark[key])
                if not r or r['time_zone']!='UTC' or not r['peak_date']:continue
                value=r['peak_date']
                when=datetime.utcfromtimestamp(value/1000) if isinstance(value,(int,float)) else datetime.strptime(value,'%m/%d/%Y %I:%M:%S %p')
                if when.year!=2017:raise ValueError('Unexpected storm year')
                w.writerow([name,mark['hwm_id'],when.isoformat()+'Z',bool(r[flag])])


if __name__=='__main__':
    import sys
    export(sys.argv[1])
