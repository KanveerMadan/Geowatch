"""Independent, dated visible-surface corroboration on exactly the SAR grid."""
import argparse
from datetime import date,timedelta
import fcntl
import json
import os
from pathlib import Path
import time

import ee
import numpy as np
import rasterio
from rasterio.transform import Affine

from .grid import grid30
from .guard import authorize, authorize_window, CUTOFF
from .optical_reference import metadata_record, unanimous_30m
from .run import atomic_json, disk


def window(unit, begin, end):
    authorize_window(unit,begin,end)
    return [str(begin),str(end+timedelta(days=1))]


def collect(unit, root, control):
    site=authorize(unit)
    key=unit+'_control' if control else unit
    meta=json.loads((root/'events'/key/'manifest.json').read_text())
    if meta['unit']!=key or meta['event']!=site['date'] or meta['grid']!=grid30(unit):
        raise ValueError('Inconsistent SAR product')
    post=date.fromisoformat(meta['post_date'])
    anchor=post if control else date.fromisoformat(site['date'])
    pre=window(unit,anchor-timedelta(days=60),anchor-timedelta(days=10))
    after=window(unit,max(anchor,post-timedelta(days=1)) if not control else post-timedelta(days=1),
                 min(CUTOFF-timedelta(days=1),post+timedelta(days=1)))
    directory=root/'independent'/unit
    directory.mkdir(parents=True,exist_ok=True)
    file=directory/('s2_control.tif' if control else 's2_event.tif')
    if file.exists() and file.with_suffix('.json').exists(): return
    disk(directory)
    area=ee.Geometry.Rectangle(site['bbox'],geodesic=False)
    collection=ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(area)
    def tally(bounds):
        col=collection.filterDate(*bounds)
        ids=sorted(col.aggregate_array('system:index').getInfo())
        land=ee.Image.constant(0); water=ee.Image.constant(0)
        days=sorted(set(i[:8] for i in ids))
        for day in days:
            common=col.filter(ee.Filter.stringStartsWith('system:index',day))
            def flags(im):
                scl=im.select('SCL')
                return scl.eq(4).Or(scl.eq(5)).rename('land').addBands(scl.eq(6).rename('water'))
            observed=common.map(flags).max().unmask(0)
            land=land.add(observed.select('land'))
            water=water.add(observed.select('water'))
        return land,water,ids
    preland,prewater,preids=tally(pre)
    postland,postwater,postids=tally(after)
    grid=meta['grid']; h,w=grid['shape']; x0,y0=grid['transform'][2],grid['transform'][5]
    label=np.full((h,w),255,dtype=np.uint8)
    if preids and postids:
        base=preland.gte(2).And(prewater.eq(0))
        water=ee.Image('JRC/GSW1_4/GlobalSurfaceWater').select('occurrence').unmask(0)
        valid=ee.Image('JRC/GSW1_4/Metadata').select('valid_obs').gt(0).And(water.lt(80))
        out=(ee.Image.constant(255).where(base.And(postland.gt(0)).And(postwater.eq(0)),0)
             .where(base.And(postwater.gt(0)).And(postland.eq(0)),1).updateMask(valid).unmask(255).rename('label').toByte())
        raw=ee.data.computePixels({'expression':out,'fileFormat':'NUMPY_NDARRAY','grid':{
            'crsCode':grid['crs'],'dimensions':{'width':3*w,'height':3*h},
            'affineTransform':{'scaleX':10,'scaleY':-10,'translateX':x0,'translateY':y0,'shearX':0,'shearY':0}}})
        label=unanimous_30m(raw['label'])
    counts={str(k):int((label==k).sum()) for k in [0,1,255]}
    record=metadata_record(unit,str(post),{'pre':pre,'post':after},grid,
                           {'pre':preids,'post':postids},counts)
    record['sensor']='Sentinel-2 Level-2A / Sen2Cor SCL (Earth Engine COPERNICUS/S2_SR_HARMONIZED)'
    record['control']=control
    record['reference_date']=str(date.fromisoformat(postids[0][:8])) if postids and len({i[:8] for i in postids})==1 else None
    record['product_role']='automated visible-surface corroboration; urban dry may be roofs'
    tmp=file.with_suffix('.tmp.tif')
    with rasterio.open(tmp,'w',driver='GTiff',dtype='uint8',count=1,crs=grid['crs'],
                       transform=Affine(*grid['transform']),height=h,width=w,nodata=255,compress='deflate') as dst:
        dst.write(label,1); dst.set_band_description(1,'optical surface 0=dry 1=new water 255=unknown')
    os.replace(tmp,file)
    atomic_json(file.with_suffix('.json'),record)
    print(key,counts,'post scenes',len(postids),flush=True)


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('units',nargs='+');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    for unit in a.units: authorize(unit)
    for unit in a.units:
        for control in (False,True):
            for attempt in range(5):
                try:
                    with open('/private/tmp/geowatch-change-round2-ee.lock','a') as lock:
                        fcntl.flock(lock,fcntl.LOCK_EX)
                        ee.Initialize(project=os.environ['GEE_PROJECT_ID'])
                        collect(unit,a.output,control)
                    break
                except Exception as e:
                    if attempt==4 or not any(w in str(e).lower() for w in ['429','503','quota','timeout','socket','temporarily']):raise
                    time.sleep(2**(attempt+2))

if __name__=='__main__':main()
