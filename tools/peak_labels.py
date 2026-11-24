"""Sparse peak-inundation observations. Unknown outside surveyed mark cells."""
import argparse,csv,fcntl,json,math,os
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import ee,numpy as np,requests
from pyproj import Transformer

# Event-exclusive layers. Hard-filter mixed archives by event ID on the server.
LAYERS={
 'Harvey':('8017e9a1337e45a5bc933c4e8c5ac4bf',2,180),
 'Irma':('d342e77fb9644b948e1d70cee0204a2a',2,182),
 'Florence':('f42f6dad7e664522b9575e6453e3d7af',0,283),
 'Michael':('52a15e7f4e994ef49d91b58ef2b69dbc',0,None),
 'Ida':('9caae56297e04f8ba57db2adadb577bf',3,None)}
DATES={'Harvey':'2017-08-25','Irma':'2017-09-10','Florence':'2018-09-14','Michael':'2018-10-10','Ida':'2021-09-02'}
def number(v):
    try:return float(v) if math.isfinite(float(v)) else None
    except (TypeError,ValueError):return None

def fetch_marks(storm):
    item,layer,code=LAYERS[storm]
    meta=requests.get(f'https://www.arcgis.com/sharing/rest/content/items/{item}',params={'f':'json'},timeout=30).json()
    url=f"{meta['url']}/{layer}/query"
    filt=f'event_id={code}' if code else ("eventName='Michael Oct 2018'" if storm=='Michael' else '1=1')
    ids=requests.get(url,params=dict(where=filt,returnIdsOnly='true',f='json'),timeout=40).json()['objectIds']
    for j in range(0,len(ids),200):
        q=dict(objectIds=','.join(map(str,ids[j:j+200])),where=filt,outFields='*',outSR=4326,f='json')
        r=requests.get(url,params=q,timeout=40);r.raise_for_status()
        for f in r.json()['features']:
            a=f['attributes']
            if storm=='Ida':
                height=number(a.get('hwm__ft_NA')); depth=number(a.get('depth_ft_a'))
                if height is None or depth is None or depth<=0:continue
                quality=None
            else:
                if a.get('verticalDa',a.get('verticalDatumName'))!='NAVD88':continue
                height=number(a.get('elev_ft'));quality=str(a.get('hwmQuality',a.get('hwmQualityName','')))
                if height is None or not quality.startswith(('Excellent','Good','Fair')):continue
            lon=number(a.get('longitude'));lat=number(a.get('latitude'))
            if lon is None or lat is None:lon,lat=f['geometry']['x'],f['geometry']['y']
            unc=[number(a.get(k)) for k in ('uncertainty','uncertaint','hwm_uncert','hwm_uncertainty')]
            yield {'storm':storm,'id':str(a.get('hwm_id',a.get('OBJECTID',a.get('objectid',a.get('FID'))))),
                   'lon':lon,'lat':lat,'wse_m':height*.3048,'quality':quality or 'mapped Manville survey depth',
                   'quality_margin_m':max([.2]+[abs(v) for v in unc if v is not None and v>=0])*.3048,
                   'survey_date_raw':str(a.get('survey_date',a.get('survey_dat',''))),'source_item':item,'layer':layer}

def run(storm,out,project):
    marks=list(fetch_marks(storm))
    if not marks:raise ValueError('No datum-verified marks')
    groups=defaultdict(list)
    for m in marks:
        epsg=32600+int((m['lon']+180)//6)+1
        x,y=Transformer.from_crs(4326,epsg,always_xy=True).transform(m['lon'],m['lat'])
        col,row=int(x//30),int(y//30)
        m.update(epsg=epsg,col=col,row=row,center_offset_m=math.hypot(x-(col+.5)*30,y-(row+.5)*30))
        groups[epsg].append(m)
    with open('/private/tmp/geowatch-change-round2-ee.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);ee.Initialize(project=project)
        for epsg,group in groups.items():
            for ix in range(0,len(group),100):
                chunk=group[ix:ix+100]
                pts=ee.FeatureCollection([ee.Feature(ee.Geometry.Point([m['lon'],m['lat']]),{'idx':i}) for i,m in enumerate(chunk)])
                dem=ee.ImageCollection('USGS/3DEP/10m_collection').filterBounds(pts.geometry().bounds()).mosaic().select('elevation')
                gsw=ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').unmask(0).updateMask(ee.Image('JRC/GSW1_4/Metadata').select('valid_obs').gt(0))
                rows=dem.addBands(gsw).reduceRegions(collection=pts,crs=f'EPSG:{epsg}',crsTransform=[10,0,0,0,-10,0],reducer=ee.Reducer.first()).getInfo()['features']
                for f in rows:
                    a=f['properties'];m=chunk[a['idx']];z=a.get('elevation');oc=a.get('occurrence')
                    m.update(ground_m=z,occurrence=oc,state=0)
                    if z is not None and oc is not None and oc<80:
                        m['state']=2 if m['center_offset_m']<=15 and m['wse_m']-z>1.0+m['quality_margin_m'] else 3
    out=Path(out)/storm;out.mkdir(exist_ok=True,parents=True)
    tiles=defaultdict(list)
    for m in marks:tiles[m['epsg'],m['col']//64,m['row']//64].append(m)
    for (epsg,tx,ty),tile in tiles.items():
        state=np.zeros((64,64),dtype='uint8')
        for m in tile:
            y,x=63-m['row']%64,m['col']%64
            if state[y,x]!=2:state[y,x]=m['state']
        meta={'event':DATES[storm],'incident':storm,'role':'dev','block':1,'grid':{'crs':f'EPSG:{epsg}','shape':[64,64],'transform':[30,0,1920*tx,0,-30,1920*(ty+1)]},
              'definition':'Observed inundation at mark within 15 m of cell center; local peak time unknown. Date is an incident anchor.'}
        np.savez_compressed(out/f'{storm}_{epsg}_{tx}_{ty}.npz',state=state,flooded=state==2,valid=(state==2)|(state==1),meta=json.dumps(meta))
    with (out/'marks.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(marks[0]),lineterminator='\n');w.writeheader();w.writerows(marks)
    print(storm,len(marks),sum(m['state']==2 for m in marks),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('storms',nargs='+',choices=LAYERS);a=p.parse_args()
    for storm in a.storms:run(storm,a.output,os.environ['GEE_PROJECT_ID'])
