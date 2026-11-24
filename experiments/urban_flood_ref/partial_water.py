"""Count observed wet subcells. A single wet patch establishes some water in a cell."""
import argparse
import json
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import Affine
from .guard import authorize
from .package import sha
from .run import atomic_json


def wet_support(fine, built, occurrence):
    if fine.shape!=built.shape or fine.shape!=occurrence.shape or any(n%3 for n in fine.shape):
        raise ValueError('Expected aligned 10 m children of complete 30 m cells')
    if not np.isin(fine,[0,1,255]).all():
        raise ValueError('Invalid manual reference code')
    h,w=fine.shape
    def blocks(v):return v.reshape(h//3,3,w//3,3)
    in_town=np.isfinite(built)&(built>=.10)&(built<=1)
    domain=(blocks(in_town).sum(axis=(1,3))>=5)&blocks(np.isfinite(occurrence)&(occurrence<80)&(occurrence>=0)).all(axis=(1,3))
    count=blocks((fine==1)&in_town).sum(axis=(1,3)).astype(np.uint8)
    positive=(count>0)&domain
    # Sparse positives only. A zero count can also mean obstructed or unobserved.
    return positive,np.where(positive,count,255).astype(np.uint8)


def build(unit,root):
    site=authorize(unit)
    if not site.get('ufo_item'):raise ValueError('Published manual reference required')
    folder=root/'independent'/unit
    receipt=json.loads((folder/'ufo_reference.json').read_text());grid=receipt['grid']
    if receipt['unit']!=unit or receipt['source_item']!=site['ufo_item']:raise ValueError('Source identity mismatch')
    with rasterio.open(folder/'ufo_surface_10m.tif') as ds:
        if (ds.crs.to_string()!=grid['crs'] or ds.transform!=Affine(*grid['transform'])*Affine.scale(1/3)):
            raise ValueError('Nested manual reference grid mismatch')
        fine=ds.read(1)
    with np.load(root/'cache'/unit/(unit+'_radar_v1.npz'),allow_pickle=False) as z:
        wet,count=wet_support(fine,z['built'],z['occ'])
    mask=folder/'ufo_urban_wet_children.tif'
    with rasterio.open(mask,'w',driver='GTiff',dtype='uint8',count=1,width=wet.shape[1],height=wet.shape[0],
                       crs=grid['crs'],transform=Affine(*grid['transform']),nodata=255,compress='deflate') as ds:
        ds.write(count,1);ds.set_band_description(1,'confirmed newly visible 10 m water patches in built-up parts of this cell')
    meta={'unit':unit,'event':site['date'],'incident':site['incident'],'date':receipt['date'],'reference_date':receipt['date'],'block':1,
          'grid':grid,'bbox':site['bbox'],'role':'dev','source_raster':str(mask.relative_to(root)),
          'source_receipt':str((folder/'ufo_reference.json').relative_to(root)),'source':receipt['source'],'licence':receipt['licence'],
          'attribution':receipt['attribution'],'source_item':receipt['source_item'],'source_raster_sha256':sha(mask),
          'definition':'Some new visible water in a built-up 30 m neighbourhood. One or more homogeneous, previously clear-land 10 m patches in GHSL built-up context, all nine children known nonpermanent. Source cannot identify a particular street. Unknown cells have no negative training label.',
          'training_status':'Optional positive-only partial-cell presence target. Keep separate from whole-cell inundation. Same incident and source as manual_refs.'}
    dst=root/'partial_water_refs';dst.mkdir(exist_ok=True);out=dst/(unit+'.npz')
    np.savez_compressed(out,flooded=wet,valid=wet,meta=json.dumps(meta,allow_nan=False))
    atomic_json(out.with_suffix('.json'),{**meta,'file':str(out.relative_to(root)),'sha256':sha(out),
                'wet':int(wet.sum()),'dry':0,'unknown':int((~wet).sum()),'confirmed_wet_children':int(count[wet].sum())})
    print(unit,'partial urban positive',int(wet.sum()),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(__doc__);p.add_argument('units',nargs='+');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    for unit in a.units:build(unit,a.output)
