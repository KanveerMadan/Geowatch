"""Package historical point-supported peak cells and their timing receipts."""
import argparse
import csv
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from rasterio.transform import array_bounds
from rasterio.warp import transform_bounds
from affine import Affine

from .peak_labels import DATES

CODES = {'unobserved': 0, 'confident_dry': 1, 'confident_flooded': 2, 'ambiguous': 3}


def survey_day(text):
    if text.isdigit():
        return datetime.fromtimestamp(int(text) / 1000, timezone.utc).date()
    if '/' in text:
        return datetime.strptime(text.split()[0], '%m/%d/%Y').date()
    return None


def late_flag(day, peak):
    """Day-only source in an unspecified US local zone. Bound midnight in UTC."""
    if day is None or peak is None:
        return 'unknown'
    earliest = datetime.combine(day, datetime.min.time(), timezone.utc)
    latest = earliest + timedelta(hours=30)  # entire calendar day plus US central UTC offset
    cutoff = peak + timedelta(hours=48)
    return 'yes' if earliest > cutoff else 'no' if latest <= cutoff else 'uncertain'


def package(raw, dest, timings, tides):
    dest.mkdir(parents=True, exist_ok=True)
    sources = {(r['storm'],r['mark_id']): r for r in csv.DictReader(timings.open())}
    stations = {r['storm']: r for r in json.loads(tides.read_text())}
    manifest = []
    for name, anchor in DATES.items():
        marks = list(csv.DictReader((raw / name / 'marks.csv').open()))
        tiles = defaultdict(list)
        for r in marks:
            timing = sources.get((name,r['id']), {})
            utc = timing.get('source_peak_utc', '')
            peak = datetime.fromisoformat(utc.replace('Z', '+00:00')) if utc else None
            station = stations[name]
            day = survey_day(r['survey_date_raw'])
            r.update(local_peak_utc=utc, time_estimated=timing.get('estimated_time', ''),
                     survey_day=day.isoformat() if day else '',
                     survey_over_48h_after_local_peak=late_flag(day, peak),
                     label_time_basis='physical trace of local maximum',
                     station_id=station['station'], station_peak_utc=station['time_utc'],
                     survey_over_48h_after_station_peak=late_flag(day, datetime.fromisoformat(station['time_utc']).replace(tzinfo=timezone.utc)) if name!='Ida' else 'different region')
            epsg, col, row = (int(r[k]) for k in ('epsg','col','row'))
            tiles[epsg,col//64,row//64].append(r)
        with zipfile.ZipFile(dest/(name+'.zip'),'w',zipfile.ZIP_DEFLATED) as archive:
            log = io.StringIO()
            writer = csv.DictWriter(log,fieldnames=list(marks[0]),lineterminator='\n')
            writer.writeheader()
            writer.writerows(marks)
            archive.writestr('marks.csv',log.getvalue())
            for (epsg,x,y), points in sorted(tiles.items()):
                unit = f'{name}_{epsg}_{x}_{y}'
                cells = np.zeros((64,64),np.uint8)
                bycell=defaultdict(set)
                wet_times=set()
                for r in points:
                    idx=63-int(r['row'])%64,int(r['col'])%64
                    bycell[idx].add(int(r['state']))
                    if int(r['state'])==2 and r['local_peak_utc']:
                        wet_times.add(r['local_peak_utc'][:10])
                for idx,states in bycell.items():
                    # Inconsistent evidence abstains. Missing data alone is neutral.
                    evidence=states-{0}
                    cells[idx]=next(iter(evidence)) if len(evidence)==1 else 3 if evidence else 0
                transform=Affine(30,0,x*1920,0,-30,(y+1)*1920)
                crs=f'EPSG:{epsg}'
                grid={'crs':crs,'shape':[64,64],'transform':list(transform)[:6]}
                dates=sorted(wet_times)
                meta={'unit':unit,'event':anchor,'incident':name,'role':'dev','block':1,'grid':grid,
                      'bbox':list(transform_bounds(crs,'EPSG:4326',*array_bounds(64,64,transform))),
                      'state_codes':CODES,'local_peak_dates_if_known':dates,
                      'date_basis':'event is an incident anchor. Read marks.csv for location-specific timing.',
                      'support':'point-supported peak in mark-containing 30 m cell; no area fraction or causal attribution'}
                b=io.BytesIO()
                np.savez_compressed(b,state=cells,flooded=cells==2,valid=(cells==1)|(cells==2),meta=json.dumps(meta))
                payload=b.getvalue();archive.writestr(unit+'.npz',payload)
                manifest.append({'event':name,'incident_anchor':anchor,'archive':name+'.zip','file':unit+'.npz','sha256':hashlib.sha256(payload).hexdigest(),
                    'local_wet_dates_if_known':'|'.join(dates),'licence':'USGS federal observations; EC JRC/Google water mask, Copernicus terms',
                    **{k:int(np.count_nonzero(cells==v)) for k,v in CODES.items()}})
    with (dest/'tiles.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(manifest[0]),lineterminator='\n')
        w.writeheader();w.writerows(manifest)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['raw','dest','timings','tides']:
        p.add_argument(name,type=Path)
    a=p.parse_args()
    package(a.raw,a.dest,a.timings,a.tides)
