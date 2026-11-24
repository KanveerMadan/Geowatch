"""Stream verified Geofabrik extracts to a durable local cache."""
import argparse, hashlib, json, os, shutil
from pathlib import Path
import requests

def fetch(region, directory, config=Path(__file__).with_name('regions.json')):
    key=json.loads(Path(config).read_text())[region]
    url='https://download.geofabrik.de/'+key+'-latest.osm.pbf'
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    dest=directory/(region+'.osm.pbf')
    response=requests.get(url+'.md5',timeout=60);response.raise_for_status()
    checksum=response.text.split()[0].lower()
    if len(checksum)!=32:raise ValueError('Invalid Geofabrik checksum')
    if dest.exists():
        with dest.open('rb') as f:
            if hashlib.file_digest(f,'md5').hexdigest()==checksum:return dest
    part=dest.with_suffix('.partial');digest=hashlib.md5()
    try:
        with requests.get(url,stream=True,timeout=(20,90)) as r:
            r.raise_for_status()
            with part.open('wb') as out:
                for chunk in r.iter_content(4*1024*1024):
                    if shutil.disk_usage(directory).free < 15*1024**3:raise OSError('15 GiB disk reserve reached')
                    out.write(chunk);digest.update(chunk)
        if digest.hexdigest()!=checksum:raise ValueError('PBF checksum mismatch')
        os.replace(part,dest)
    finally:part.unlink(missing_ok=True)
    return dest

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory');p.add_argument('regions',nargs='+');a=p.parse_args()
    for region in a.regions:
        try: print(region,fetch(region,a.directory).stat().st_size,flush=True)
        except (requests.RequestException,OSError,ValueError) as e: print(region,str(e),flush=True)
