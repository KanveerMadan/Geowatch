"""Obtain only the two nominated Beira chip metadata records from the public UFO ZIP.

The central directory contains filenames only. Read an annotation member only for
the approved storm, the specified date window and a positive metadata intersection.
Never extract the archive; unused members (including other events) are not read.
"""
import io
import json
import re
from pathlib import Path
from zipfile import ZipFile

import requests

from .guard import authorize, authorize_window
from .run import disk

RECORD='https://zenodo.org/api/records/19698577'
PRODUCT='ufo-dataset.zip'


class RangeReader(io.RawIOBase):
    def __init__(self,url,size):
        self.url=url; self.size=size; self.pos=0
    def seekable(self):return True
    def seek(self,n,whence=0):
        self.pos=(0,self.pos,self.size)[whence]+n
        if self.pos<0:raise OSError('negative seek')
        return self.pos
    def tell(self):return self.pos
    def read(self,n=-1):
        if n<0:n=self.size-self.pos
        end=min(self.size,self.pos+n)
        if end<=self.pos:return b''
        if end-self.pos>6_000_000:raise ValueError('Unbounded range')
        span=f'{self.pos}-{end-1}'
        with requests.get(self.url,headers={'Range':'bytes='+span,'Accept-Encoding':'identity'},
                          params={'span':span},stream=True,timeout=45) as r:
            if r.status_code!=206 or r.headers.get('Content-Range','').split('/')[0]!='bytes '+span:
                raise OSError('Archive server did not honor range: '+str(r.status_code))
            data=r.content
        if len(data)!=end-self.pos:raise OSError('Incomplete range response')
        self.pos=end
        return data


def inspect(unit,root):
    if unit!='beira': raise ValueError('Only the explicitly investigated Beira archive is enabled')
    site=authorize(unit);authorize_window(unit,'2019-03-25','2019-03-26')
    root=Path(root);dst=root/'independent'/unit
    dst.mkdir(parents=True,exist_ok=True);disk(dst)
    response=requests.get(RECORD,timeout=20);response.raise_for_status()
    f=next(x for x in response.json()['files'] if x['key']==PRODUCT)
    source=RangeReader(f['links']['self'],f['size'])
    with ZipFile(source) as archive:
        matches=[i for i in archive.namelist() if re.search(r'/items/BEI_2019032[56]_[^/]+\.json$',i,re.I)]
        results=[]
        for key in matches:
            item=json.loads(archive.read(key))
            box=item['bbox'];w,s,e,n=site['bbox']
            overlap=box[0]<e and box[2]>w and box[1]<n and box[3]>s
            results.append({'item':item['id'],'bbox':box,'datetime':item['properties']['datetime'],'overlap':overlap,
                            'assets':item['assets']})
        if not matches:print([i for i in archive.namelist() if ('BEI_' in i and '201903' in i)][:10])
    (dst/'ufo_catalog.json').write_text(json.dumps({'unit':unit,'source':RECORD,'tiles':results},indent=2)+'\n')
    print([(i['item'],i['overlap'],i['bbox']) for i in results])
    return results


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(__doc__);p.add_argument('unit');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();inspect(a.unit,a.output)
