"""Compare every 30 m model pixel to the original per-unit rainfall implementation."""
import csv,fcntl,json,os,time
from pathlib import Path
import ee
import numpy as np
from susceptibility import hydro_rasters as h
from .ee_batch import export

def compare(units, cache, project):
    start=time.monotonic();path=export(units,cache,project)
    retrieval=time.monotonic()-start
    with path.open() as f:rows=list(csv.DictReader(f))
    output=[]
    with open('/private/tmp/geowatch-change-round2-ee.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);ee.Initialize(project=project)
        for u in units:
            b=u['bbox'];t,shape,crs=h.utm_grid(b);year=int(u['date'][:4]);start=time.monotonic()
            for name,img in h._rain_images(year).items():
                deg=h.RAIN_NATIVE_DEG[name];x,y,w,ht=h.native_grid(h.grid_lonlat_bounds(t,shape,crs),deg)
                raster=np.full((ht,w),np.nan)
                rr=[r for r in rows if r['layer']==name and u['id'] in r['units'].split(',')]
                for r in rr:raster[round((y-float(r['lat']))/deg-.5),round((float(r['lon'])-x)/deg-.5)]=float(r['value'])
                raster[raster==h.NODATA]=np.nan
                batch=h.nearest_from_native(raster,x,y,deg,t,shape,crs)
                ref=h._rain_layer(img,name,b,t,shape,crs)
                diff=np.abs(batch-ref)
                output.append(dict(unit=u['id'],layer=name,pixels=int(diff.size),valid=int(np.isfinite(diff).sum()),nodata_mismatches=int(np.count_nonzero(np.isfinite(batch)!=np.isfinite(ref))),max_abs=float(np.nanmax(diff)) if np.isfinite(diff).any() else None))
            output[-1]['unit_elapsed_s']=time.monotonic()-start
    return {'batch_lookup_seconds':retrieval,'comparisons':output}
