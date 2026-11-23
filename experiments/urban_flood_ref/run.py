"""One guarded historical AOI at a time. Invoke with python -m ...run UNIT."""
import argparse
import fcntl
import json
import os
import shutil
import time
from datetime import date, timedelta
from pathlib import Path

import ee
import numpy as np

from .detector import detect_summary
from .grid import grid30
from .guard import authorize, authorize_window, CUTOFF
from .package import package_event, recover_reference


def disk(directory):
    if shutil.disk_usage(directory).free < 15*1024**3:
        raise RuntimeError('Less than 15 GiB available; stop downloads')


def atomic_json(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')
    os.replace(tmp,path)


def acquisitions(unit):
    r=authorize(unit)
    anchor=date.fromisoformat(r['date'])
    first=anchor-timedelta(days=170)
    last=min(anchor+timedelta(days=12), CUTOFF-timedelta(days=1))
    authorize_window(unit,first,last)
    area=ee.Geometry.Rectangle(r['bbox'],geodesic=False)
    col=(ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(area.centroid(1))
         .filterDate(str(first),str(last+timedelta(days=1)))
         .filter(ee.Filter.eq('instrumentMode','IW')).filter(ee.Filter.eq('resolution_meters',10))
         .filter(ee.Filter.listContains('transmitterReceiverPolarisation','VV'))
         .filter(ee.Filter.listContains('transmitterReceiverPolarisation','VH')))
    # Scene IDs include acquisition date/time, satellite and slice identity.
    keys=['system:index','orbitProperties_pass','relativeOrbitNumber_start','platform_number']
    rows=col.map(lambda im:im.set('scene',im.toDictionary(keys))).aggregate_array('scene').getInfo()
    return [{'id':x[keys[0]],'pass':x[keys[1]],'track':int(x[keys[2]]),'platform':x[keys[3]],
             'date':date.fromisoformat(x[keys[0]].split('_')[4][:8]).isoformat()} for x in rows]


def select_pair(rows, anchor, control=False):
    start=date.fromisoformat(anchor)
    low,high=(-45,-21) if control else (0,12)
    def dt(x): return (date.fromisoformat(x['date'])-start).days
    choices=[]
    for post in rows:
        lag=dt(post)
        if not low <= lag <= high:
            continue
        support={}
        for pre in sorted(rows,key=lambda x:x['id']):
            if not 7 <= lag-dt(pre) <= 120:
                continue
            if all(pre[k]==post[k] for k in ['pass','track','platform']):
                support.setdefault(pre['date'],pre)
        if len(support)>=3:
            choices.append((abs(lag+30) if control else lag,-len(support),post['id'],post,
                            sorted(support.values(),key=lambda x:x['date'])))
    if not choices:
        return None
    _,_,_,post,pre=min(choices,key=lambda x:x[:3])
    return {'post':post,'pre':pre}


def graph(pair,year):
    def scene(row):
        im=ee.Image('COPERNICUS/S1_GRD/'+row['id'])
        vv=im.select(['VV','VH'])
        # Require paired valid polarizations and reject the noisy swath edges.
        valid=vv.mask().reduce(ee.Reducer.min()).And(im.select('angle').gt(30)).And(im.select('angle').lt(46))
        return vv.updateMask(valid)
    post=scene(pair['post'])
    pre=ee.ImageCollection.fromImages([scene(r) for r in pair['pre']])
    median=pre.median()
    mad=pre.map(lambda img:img.subtract(median).abs()).median()
    days=ee.ImageCollection.fromImages([
        scene(r).select('VV').multiply(0).add((date.fromisoformat(r['date'])-date(1970,1,1)).days)
        for r in pair['pre']])
    terrain=ee.Algorithms.Terrain(ee.Image('USGS/SRTMGL1_003').select('elevation'))
    gradient=terrain.select('slope')
    look=77 if pair['post']['pass']=='ASCENDING' else 283
    direction=terrain.select('aspect').subtract(look).multiply(np.pi/180).cos()
    projected=gradient.multiply(np.pi/180).tan().multiply(direction).atan().multiply(180/np.pi)
    incidence=ee.Image('COPERNICUS/S1_GRD/'+pair['post']['id']).select('angle')
    # Approximate side-facing terrain shadow and layover only; no building DSM.
    visible=projected.gt(incidence.multiply(-1)).And(projected.lt(ee.Image.constant(90).subtract(incidence)))
    epoch=((year-1)//5)*5
    built=ee.Image(f'JRC/GHSL/P2023A/GHS_BUILT_S/{epoch}').select('built_surface').divide(10000)
    occ=ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').unmask(0).updateMask(
        ee.Image('JRC/GSW1_4/Metadata').select('valid_obs').gt(0))
    lc=ee.ImageCollection('MODIS/061/MCD12Q1').filterDate(f'{year-1}-01-01',f'{year}-01-01').first().select('LC_Type1')
    # IGBP grassland and barren only. Crops and seasonally inundated wetlands abstain.
    open_land=lc.eq(10).Or(lc.eq(16))
    return ee.Image.cat([median.rename(['mv','mh']),mad.rename(['dv','dh']),pre.select('VV').count().rename('cnt'),
                         post.rename(['pv','ph']),built.rename('built'),occ.rename('occ'),gradient.rename('slope'),
                         visible.rename('visible'),open_land.rename('open'),days.min().rename('first'),days.max().rename('last')])


def read_grid(img,grid,cache):
    if cache.exists():
        with np.load(cache,allow_pickle=False) as z: return dict(z)
    rows,cols=grid['shape']; x0,y0=grid['transform'][2],grid['transform'][5]
    h,w=rows*3,cols*3
    if h*w>2_000_000: raise ValueError('AOI exceeds the bounded compute budget')
    bands={}
    for top in range(0,h,512):
        for left in range(0,w,512):
            disk(cache.parent)
            request={'expression':img.toFloat().unmask(-9999,False),'fileFormat':'NUMPY_NDARRAY','grid':{
                'crsCode':grid['crs'],'dimensions':{'width':min(512,w-left),'height':min(512,h-top)},
                'affineTransform':{'scaleX':10,'scaleY':-10,'translateX':x0+10*left,'translateY':y0-10*top,
                                   'shearX':0,'shearY':0}}}
            tile=ee.data.computePixels(request)
            for name in tile.dtype.names:
                if name not in bands: bands[name]=np.empty((h,w),dtype=np.float32)
                v=tile[name]
                bands[name][top:top+v.shape[0],left:left+v.shape[1]]=np.where(v==-9999,np.nan,v)
    tmp=cache.with_suffix('.part.npz')
    np.savez_compressed(tmp,**bands); os.replace(tmp,cache)
    return bands


def run_unit(unit,root,control=False):
    site=authorize(unit); grid=grid30(unit)
    dest=unit+'_control' if control else unit
    if (root/'events'/dest/'manifest.json').exists():
        recover_reference(root,dest)
        return
    cache=root/'cache'/unit
    cache.mkdir(exist_ok=True,parents=True)
    disk(cache)
    manifest=cache/'acquisitions.json'
    if not manifest.exists(): atomic_json(manifest,acquisitions(unit))
    pair=select_pair(json.loads(manifest.read_text()),site['date'],control)
    if not pair:
        print(unit,dest,'NO QUALIFYING ACQUISITION',flush=True)
        atomic_json(cache/(dest+'_unavailable.json'),{'unit':unit,'control':control,'reason':'No qualifying same-track dual-pol series'})
        return
    anchor=date.fromisoformat(site['date'])
    first,post=pair['pre'][0]['date'],pair['post']['date']
    authorize_window(unit,first,post)
    path=cache/(dest+'_radar_v1.npz')
    arr=read_grid(graph(pair,date.fromisoformat(post).year),grid,path)
    result=detect_summary(arr['mv'],arr['mh'],arr['dv'],arr['dh'],arr['cnt'],arr['pv'],arr['ph'],
                          built_fraction=arr['built'],slope_deg=arr['slope'],occurrence_pct=arr['occ'],
                          terrain_visible=arr['visible'],open_land=arr['open'])
    dates=[r['date'] for r in pair['pre']]
    meta={**site,'event':site['date'],'role':'dev','pre_dates':dates,'post_date':post,
          'days_from_anchor':(date.fromisoformat(post)-anchor).days,
          'kind':'pre_event_control' if control else 'event',
          'acquisitions':pair,'method_name':'same-track GRD dual-pol change; no interferometric input',
          'lineage':'Copernicus Sentinel-1, GHSL JRC, EC JRC/Google Global Surface Water, SRTM, MODIS MCD12Q1',
          'rights':'See SOURCES.md; satellite-derived development candidates','training_status':'requires independent review'}
    out=package_event(root,dest,grid,result,meta,reference_dates=(arr['first'],arr['last']))
    print(dest,post,out['counts30'],flush=True)


def main():
    parser=argparse.ArgumentParser(__doc__); parser.add_argument('units',nargs='+')
    parser.add_argument('--output',type=Path,required=True); parser.add_argument('--controls',action='store_true')
    args=parser.parse_args()
    # Authenticate only after validating every requested identity.
    for unit in args.units: authorize(unit)
    args.output.mkdir(exist_ok=True,parents=True)
    for unit in args.units:
        for control in ([False,True] if args.controls else [False]):
            for attempt in range(5):
                try:
                    with open('/private/tmp/geowatch-change-round2-ee.lock','a') as lock:
                        fcntl.flock(lock,fcntl.LOCK_EX)
                        ee.Initialize(project=os.environ['GEE_PROJECT_ID'])
                        run_unit(unit,args.output,control)
                    break
                except Exception as exc:
                    if attempt==4 or not any(w in str(exc).lower() for w in ('429','quota','503','timeout','socket','temporarily')):
                        raise
                    time.sleep(2**(attempt+2))


if __name__=='__main__': main()
