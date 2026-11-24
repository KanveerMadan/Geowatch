"""Find the verified maximum at one contextual tide gauge per named historical event."""
import json
from pathlib import Path
import requests
EVENTS=json.loads(Path(__file__).with_name('hurricane_events.json').read_text())

def tide_peak(storm):
    start,end,station,_=EVENTS[storm]
    if end>='2022':raise ValueError('Historical events only')
    args=dict(station=station,begin_date=start.replace('-',''),end_date=end.replace('-',''),product='water_level',datum='MLLW',units='metric',time_zone='gmt',format='json',application='GeoWatch')
    r=requests.get('https://api.tidesandcurrents.noaa.gov/api/prod/datagetter',params=args,timeout=40)
    r.raise_for_status();data=r.json()
    rows=[x for x in data.get('data',[]) if x.get('q')=='v' and x.get('v','').strip()]
    if not rows:raise ValueError('No verified data: '+str(data.get('error')))
    best=max(rows,key=lambda x:float(x['v']))
    return dict(storm=storm,station=station,metadata=data['metadata'],time_utc=best['t'],metres_above_MLLW=float(best['v']),
        samples=len(rows),first=rows[0]['t'],last=rows[-1]['t'],requested=[start,end],url=r.url,licence='US NOAA federal government data',
        use='Station maximum within event window only; MLLW is not NAVD88 terrain elevation.')
