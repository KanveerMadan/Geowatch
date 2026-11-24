"""Export the production rain reducers on the exact native cells of historic unit grids."""
import csv,fcntl,hashlib,json,math,os,time
from datetime import date
from pathlib import Path
import ee
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from susceptibility import hydro_rasters as hydro

def cells(units):
    needed={}
    for u in units:
        day=date.fromisoformat(u['date'])
        if day.year>=2022:raise ValueError('Pre-2022 units only')
        transform,shape,crs=hydro.utm_grid(u['bbox'])
        extent=hydro.grid_lonlat_bounds(transform,shape,crs)
        for name,deg in hydro.RAIN_NATIVE_DEG.items():
            x,y,w,h=hydro.native_grid(extent,deg)
            for j in range(h):
                for i in range(w):
                    lon,lat=round(x+(i+.5)*deg,6),round(y-(j+.5)*deg,6)
                    needed.setdefault((day.year,name,lon,lat),set()).add(u['id'])
    return needed

def export(units,cache,project,poll_seconds=20):
    """Return a cached native-cell CSV. Reuse in-flight task IDs across restarts."""
    needed=cells(units)
    if not needed:raise ValueError('Empty unit list')
    cache=Path(cache);cache.mkdir(exist_ok=True,parents=True)
    tag='gw_rain_'+hashlib.sha256(json.dumps(sorted((y,n,x,a,sorted(v)) for (y,n,x,a),v in needed.items())).encode()).hexdigest()[:24]
    dest=cache/(tag+'.csv');state=cache/(tag+'.task')
    with open('/private/tmp/geowatch-change-round2-ee.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if dest.exists():return dest
        ee.Initialize(project=project)
        drive=build('drive','v3',credentials=ee.data.get_persistent_credentials(),cache_discovery=False)
        query=drive.files().list(q=f"name='{tag}.csv' and trashed=false",fields='files(id,name)')
        files=query.execute()['files']
        if not files:
            if state.exists():tid=state.read_text().strip()
            else:
                all_rows=[]
                for year in sorted({k[0] for k in needed}):
                    for name,img in hydro._rain_images(year).items():
                        pts=[ee.Feature(ee.Geometry.Point([x,a]),{'year':y,'layer':n,'lon':x,'lat':a,'units':','.join(sorted(v))})
                             for (y,n,x,a),v in needed.items() if y==year and n==name]
                        if not pts:continue
                        deg=hydro.RAIN_NATIVE_DEG[name]
                        records=img.unmask(hydro.NODATA).toFloat().rename('value').reduceRegions(
                            collection=ee.FeatureCollection(pts),reducer=ee.Reducer.first().setOutputs(['value']),
                            crs='EPSG:4326',crsTransform=[deg,0,-180,0,-deg,90])
                        all_rows.append(records)
                task=ee.batch.Export.table.toDrive(collection=ee.FeatureCollection(all_rows).flatten(),description=tag,
                      fileNamePrefix=tag,fileFormat='CSV',selectors=['year','layer','lon','lat','units','value'])
                task.start();tid=task.id;tmp=state.with_suffix('.tmp');tmp.write_text(tid);tmp.replace(state)
            while True:
                info=ee.data.getTaskStatus(tid)[0];stage=info['state']
                if stage=='COMPLETED':break
                if stage not in ('READY','RUNNING','SUBMITTED'):raise RuntimeError(f'{tid}: {stage}: '+str(info.get('error_message','')))
                time.sleep(poll_seconds)
            for _ in range(12):
                files=query.execute()['files']
                if files:break
                time.sleep(5)
        if len(files)!=1:raise RuntimeError('Expected exactly one uniquely named Drive export')
        part=dest.with_suffix('.partial')
        with part.open('wb') as f:
            downloader=MediaIoBaseDownload(f,drive.files().get_media(fileId=files[0]['id']),chunksize=1024*1024)
            done=False
            while not done:_,done=downloader.next_chunk(num_retries=4)
        with part.open() as f:
            rows=list(csv.DictReader(f))
        if {(int(r['year']),r['layer'],float(r['lon']),float(r['lat'])) for r in rows}!=set(needed) or len(rows)!=len(needed) or any(not math.isfinite(float(r['value'])) for r in rows):
            raise ValueError('Incomplete or malformed native grid export')
        part.replace(dest)
    return dest


def unit_layers(unit, table):
    """Map the three exported native rainfall grids to the exact 30 m unit grid."""
    import numpy as np
    if date.fromisoformat(unit['date']).year>=2022:raise ValueError('Pre-2022 only')
    t,shape,crs=hydro.utm_grid(unit['bbox'])
    extent=hydro.grid_lonlat_bounds(t,shape,crs)
    native={}
    for name,deg in hydro.RAIN_NATIVE_DEG.items():
        x,y,w,h=hydro.native_grid(extent,deg)
        native[name]=(np.full((h,w),np.nan),np.zeros((h,w),bool),x,y,deg)
    with Path(table).open() as f:
        for r in csv.DictReader(f):
            if unit['id'] not in r['units'].split(',') or int(r['year'])!=int(unit['date'][:4]):continue
            arr,seen,x,y,deg=native[r['layer']]
            row,col=round((y-float(r['lat']))/deg-.5),round((float(r['lon'])-x)/deg-.5)
            if not (0<=row<arr.shape[0] and 0<=col<arr.shape[1]) or seen[row,col]:raise ValueError('Inconsistent unit or duplicated cell')
            value=float(r['value']);arr[row,col]=np.nan if value==hydro.NODATA else value;seen[row,col]=True
    if not all(seen.all() for _,seen,*_ in native.values()):raise ValueError('Incomplete unit')
    return {name:hydro.nearest_from_native(arr,x,y,deg,t,shape,crs) for name,(arr,_,x,y,deg) in native.items()}
