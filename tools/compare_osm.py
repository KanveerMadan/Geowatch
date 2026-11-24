"""Compare water feature identities with successful archived Chicago queries."""
import json,time
from pathlib import Path
import numpy as np
from affine import Affine
from susceptibility.hydro_rasters import grid_lonlat_bounds
from vector.sources import bbox_key
from .osm_local import query

CASES={'r311_chicago_2019-04-29_b03_07':'6a620cab5c','r311_chicago_2019-05-27_b02_06':'1428e7179b','r311_chicago_2021-06-24_b02_07':'99f44da7fd'}

def compare(root):
    results=[]
    for unit,token in CASES.items():
        key='chicago_'+unit.split('_')[-2]+'_'+unit.split('_')[-1]
        with np.load(root/'flood_round3/big/r311_refs'/(unit+'.npz'),allow_pickle=False) as z:
            meta=json.loads(str(z['meta']))
        grid=meta['grid']; t=Affine(*grid['transform']);h,w=grid['shape']
        k=67  # ceil(the original 2000 m margin / 30 m pixels)
        bbox=grid_lonlat_bounds(t*Affine.translation(-k,-k),(h+2*k,w+2*k),grid['crs'])
        if not bbox_key('bl_'+key,bbox).endswith(token):raise ValueError('Archived request bounds mismatch')
        start=time.monotonic()
        data=query(bbox,root/'floodspeed/pbf/IL.osm.pbf',root/'floodspeed/index')
        ids=set()
        for f in data['features']:
            t=f['properties']['tags']; kind=f['id'].split('/')[0]
            if kind in ('way','relation') and (t.get('natural')=='water' or (kind=='way' and t.get('waterway') in ('river','stream','canal','drain','ditch','tidal_channel','riverbank'))):ids.add(f['id'])
        old=set()
        for cat in ['water_riverbank','water_water_ways','water_water_relations','water_waterway_lines']:
            rows=json.loads((root/'vector/osm'/f'bl_{key}_{token}__{cat}.json').read_text())
            old.update(f"{x['type']}/{x['id']}" for x in rows)
        results.append(dict(unit=unit,bbox=bbox,archived=len(old),local=len(ids),matched=len(old&ids),
                          recall=len(old&ids)/len(old),jaccard=len(old&ids)/len(old|ids),seconds=time.monotonic()-start))
    return results
if __name__=='__main__':print(json.dumps(compare(Path.home()/'.cache/geowatch'),indent=2))
