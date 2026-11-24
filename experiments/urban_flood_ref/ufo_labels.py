"""Conservative 10 and 30 m change labels from human-drawn 3 m PlanetScope annotations."""
import argparse
from datetime import date,timedelta
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

import ee
import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.warp import Resampling,reproject,transform,transform_bounds
from rasterio.transform import Affine
import requests

from .guard import authorize,authorize_window
from .grid import grid30
from .optical_reference import unanimous_30m
from .package import sha
from .run import atomic_json,disk
from .ufo import RangeReader,RECORD,PRODUCT

ATTRIBUTION='Mukherjee et al., Urban Flood Observations, doi:10.5281/zenodo.19698577. Derived from hand-annotated PlanetScope optical surface water. Contains modified Copernicus Sentinel data and EC JRC/Google water history.'


def baseline(unit, site, grid, root):
    anchor=date.fromisoformat(site['date']); begin=anchor-timedelta(days=60);end=anchor-timedelta(days=10)
    authorize_window(unit,begin,end)
    with open('/private/tmp/geowatch-change-round2-ee.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);ee.Initialize(project=os.environ['GEE_PROJECT_ID'])
        col=(ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED').filterBounds(ee.Geometry.Rectangle(site['bbox'],geodesic=False))
             .filterDate(str(begin),str(end+timedelta(days=1))))
        ids=sorted(col.aggregate_array('system:index').getInfo())
        land=ee.Image.constant(0);water=ee.Image.constant(0)
        for day in sorted(set(x[:8] for x in ids)):
            scl=col.filter(ee.Filter.stringStartsWith('system:index',day)).select('SCL')
            land=land.add(scl.map(lambda i:i.eq(4).Or(i.eq(5))).max().unmask(0))
            water=water.add(scl.map(lambda i:i.eq(6)).max().unmask(0))
        eligible=land.gte(2).And(water.eq(0))
        req={'expression':eligible.toByte().rename('eligible'),'fileFormat':'NUMPY_NDARRAY','grid':{
             'crsCode':grid['crs'],'dimensions':{'height':grid['shape'][0]*3,'width':grid['shape'][1]*3},
             'affineTransform':{'scaleX':10,'scaleY':-10,'shearX':0,'shearY':0,'translateX':grid['transform'][2],'translateY':grid['transform'][5]}}}
        answer=ee.data.computePixels(req)['eligible'].astype(bool)
    return answer,ids


def write_tif(path,layer,grid,t):
    with rasterio.open(path,'w',driver='GTiff',count=1,dtype='uint8',width=layer.shape[1],height=layer.shape[0],
                       crs=grid['crs'],transform=t,nodata=255,compress='deflate') as out:
        out.write(layer,1);out.set_band_description(1,'0 observed non-water, 1 new visible inundation, 255 ambiguous/unobserved')


def build(unit,root):
    site=authorize(unit)
    chip=site.get('ufo_item')
    if not chip or 'UFO:'+chip not in site['products'] or site.get('evidence_url')!='https://doi.org/10.5281/zenodo.19698577':
        raise ValueError('No vetted interpretation for this site')
    acquired=date.fromisoformat(chip.split('_')[1]).isoformat()
    authorize_window(unit,acquired,acquired)
    folder=root/'independent'/unit;folder.mkdir(parents=True,exist_ok=True);disk(folder)
    grid=grid30(unit);t=Affine(*grid['transform'])*Affine.scale(1/3)
    src=requests.get(RECORD,timeout=30);src.raise_for_status()
    f=next(x for x in src.json()['files'] if x['key']==PRODUCT)
    with zipfile.ZipFile(RangeReader(f['links']['self'],f['size'])) as archive:
        records=[k for k in archive.namelist() if k.endswith('/items/'+chip+'.json')]; assert len(records)==1
        item=json.loads(archive.read(records[0]))
        if not np.allclose(item['bbox'],site['bbox'],atol=1e-8,rtol=0) or item['properties']['datetime'][:10]!=acquired:
            raise ValueError('Archive metadata disagrees with frozen guard')
        label_members=[k for k in archive.namelist() if k.endswith('/labels/'+chip+'.tif')]
        if len(label_members)!=1: raise ValueError('Missing or duplicate label')
        data=archive.read(label_members[0])
    with MemoryFile(data) as mem, mem.open() as ds:
        native=ds.read(1)
        if ds.crs is None or not set(np.unique(native)).issubset({0,1}) or min(ds.shape)<512 or max(ds.shape)>2048:
            raise ValueError(f'Unexpected source geometry or label encoding: {ds.crs} {ds.shape} {np.unique(native)}')
        bounds=transform_bounds(ds.crs,'EPSG:4326',*ds.bounds,densify_pts=21)
        # Original labels may retain a projected CRS while discovery bounds are
        # in WGS84. A one-native-pixel tolerance covers serialization rounding.
        pixel=max((bounds[2]-bounds[0])/ds.width,(bounds[3]-bounds[1])/ds.height)
        if not np.allclose(bounds,item['bbox'],rtol=0,atol=pixel):
            raise ValueError(f'Native label footprint differs from authorized STAC item: {bounds} vs {item["bbox"]}')
        h,w=[n*3 for n in grid['shape']]
        frac=np.full((h,w),-1,dtype=np.float32)
        reproject(native.astype('float32'),frac,src_transform=ds.transform,src_crs=ds.crs,dst_transform=t,dst_crs=grid['crs'],
                  dst_nodata=-1,resampling=Resampling.average)
        yy,xx=np.indices((h,w)); inside=np.ones((h,w),bool)
        for dy,dx in [(0,0),(1,0),(0,1),(1,1)]:
            xs,ys=t*(xx+dx,yy+dy)
            lon,lat=transform(grid['crs'],ds.crs,xs.flatten(),ys.flatten())
            lon=np.asarray(lon).reshape(h,w); lat=np.asarray(lat).reshape(h,w)
            inside &= (lon>=ds.bounds.left)&(lon<=ds.bounds.right)&(lat>=ds.bounds.bottom)&(lat<=ds.bounds.top)
    prior,scenes=baseline(unit,site,grid,root)
    with np.load(root/'cache'/unit/(unit+'_radar_v1.npz'),allow_pickle=False) as z:
        mask=inside & prior & np.isfinite(z['occ']) & (z['occ']<80)
        urban=(z['built']>=.1); open_ground=np.isfinite(z['built']) & ~urban & (z['open']==1)
    # Negative labels on roofs would reintroduce the exact city bias this study targets.
    fine=np.full((h,w),255,np.uint8);fine[mask & (frac==1)]=1
    fine[mask & (frac==0) & open_ground]=0
    coarse=unanimous_30m(fine)
    write_tif(folder/'ufo_surface_10m.tif',fine,grid,t)
    write_tif(folder/'ufo_surface.tif',coarse,grid,Affine(*grid['transform']))
    valid=coarse!=255;wet=coarse==1
    meta={'unit':unit,'incident':site['incident'],'event':site['date'],'date':acquired,'post_date':acquired,
          'role':'dev','block':1,'grid':grid,'bbox':site['bbox'],'licence':'CC BY 4.0',
          'source':'https://doi.org/10.5281/zenodo.19698577','source_item':chip,'label_member':label_members[0],
          'source_sha256':hashlib.sha256(data).hexdigest(),'attribution':ATTRIBUTION,
          'method':'Published hand-annotated visible water, with two pre-event clear land dates and JRC nonpermanent mask. All contributing source pixels and fine cells must agree. Dry only over mapped grassland/barren outside the urban stratum.',
          'pre_sentinel2_assets':scenes,'reference_date':acquired,'kind':'published manual optical with automated screening',
          'wet':int(wet.sum()),'dry':int((valid & ~wet).sum()),'unknown':int((~valid).sum()),
          'urban_wet':int((wet & (urban.reshape(grid['shape'][0],3,grid['shape'][1],3).sum((1,3))>=5)).sum()),
          'training_status':'development labels; group all tiles from the same incident; fresh testing elsewhere'}
    atomic_json(folder/'ufo_reference.json',meta)
    dest=root/'manual_refs';dest.mkdir(exist_ok=True);out=dest/(unit+'.npz')
    np.savez_compressed(out,flooded=wet,valid=valid,meta=json.dumps(meta,allow_nan=False))
    atomic_json(out.with_suffix('.json'),{**meta,'file':str(out.relative_to(root)),'sha256':sha(out),
                'source_raster':str((folder/'ufo_surface.tif').relative_to(root)),
                'source_receipt':str((folder/'ufo_reference.json').relative_to(root))})
    print(unit,'wet',meta['wet'],'urban wet',meta['urban_wet'],'dry',meta['dry'],'unknown',meta['unknown'],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('units',nargs='+');p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    for unit in args.units:authorize(unit)
    for unit in args.units:build(unit,args.output)
