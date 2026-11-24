"""Bounded byte-range reader for uncompressed, one-row RGB strips in legacy TIFFs."""
import hashlib
import json
import math
import struct
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
from affine import Affine
from rasterio.transform import array_bounds, from_bounds
from rasterio.warp import Resampling, reproject, transform_bounds

from .optical_catalog import _save, require_space


def _get(url,begin,end):
    for index in range(4):
        req=urllib.request.Request(url,headers={"Range":f"bytes={begin}-{end}","User-Agent":"GeoWatch guarded optical window"})
        try:
            with urllib.request.urlopen(req,timeout=20) as response:
                if response.status!=206 or not response.headers.get("Content-Range","").startswith(f"bytes {begin}-{end}/"):
                    raise ValueError("Incorrect HTTP range response")
                b=response.read(end-begin+1)
            if len(b)!=end-begin+1:
                raise OSError("Truncated requested byte range")
            return b
        except (OSError, TimeoutError, urllib.error.URLError):
            if index==3: raise
            time.sleep(2**index)


def _layout(record, url, cache):
    receipt=cache / ("layout-"+hashlib.sha256(url.encode()).hexdigest()[:16]+".json")
    if receipt.exists():
        return json.loads(receipt.read_text())
    require_space(cache)
    header=_get(url,0,7)
    order="<" if header[:2]==b"II" else ">"
    if struct.unpack_from(order+"H",header,2)[0]!=42:
        raise ValueError("Unsupported TIFF layout")
    ifd=struct.unpack_from(order+"I",header,4)[0]
    table=_get(url,ifd,ifd+399)
    n=struct.unpack_from(order+"H",table)[0]
    if n>32: raise ValueError("Unrecognized TIFF directory")
    fields={tag:(typ,count,ptr,2+i*12+8) for i in range(n)
            for tag,typ,count,ptr in [struct.unpack_from(order+"HHII",table,2+i*12)]}
    def tag(num):
        typ,count,ptr,v=fields[num];codec,width={3:("H",2),4:("I",4)}[typ]
        if count*width<=4: return struct.unpack_from(order+str(count)+codec,table,v)
        return struct.unpack(order+str(count)+codec,_get(url,ptr,ptr+count*width-1))
    w,h=tag(256)[0],tag(257)[0]
    if (w,h)!=(record["width"],record["height"]) or (tag(258),tag(259),tag(262),tag(277),tag(278),tag(284))!=((8,8,8),(1,),(2,),(3,),(1,),(1,)):
        raise ValueError("Expected contiguous uncompressed one-row RGB strips")
    offs,counts=np.asarray(tag(273)),np.asarray(tag(279))
    if len(offs)!=h or len(counts)!=h or not (np.diff(offs)==3*w).all() or not (counts==3*w).all():
        raise ValueError("Non-contiguous strip offsets")
    result={"first":int(offs[0]),"width":w,"height":h,"row_bytes":3*w}
    _save(receipt,json.dumps(result).encode())
    return result


def chip(record, href, target_crs, target_transform, side, cache, authorize):
    """Decode only the chip. Incidental exterior bytes within physical rows are discarded."""
    geo=transform_bounds(target_crs,"EPSG:4326",*array_bounds(side,side,target_transform),densify_pts=21)
    authorize(geo,record["datetime"][:10],record["datetime"][:10])
    layout=_layout(record,href,cache)
    h,w=layout["height"],layout["width"];row_bytes=layout["row_bytes"]
    t=from_bounds(*record["local_bounds"],w,h)
    source_bbox=transform_bounds(target_crs,record["crs"],*array_bounds(side,side,target_transform),densify_pts=21)
    ax,ay=(~t)*(source_bbox[0],source_bbox[3]);bx,by=(~t)*(source_bbox[2],source_bbox[1])
    x0,y0=max(0,math.floor(ax)),max(0,math.floor(ay));x1,y1=min(w,math.ceil(bx)),min(h,math.ceil(by))
    if not (0<x1-x0<=900 and 0<y1-y0<=900):
        raise ValueError("Legacy review chip outside bounded source window")
    src=np.empty((y1-y0,x1-x0,3),"uint8")
    for row in range(y0,y1,12):
        stop=min(y1,row+12)
        begin=layout["first"]+row*row_bytes+x0*3
        end=layout["first"]+(stop-1)*row_bytes+x1*3-1
        b=_get(href,begin,end)
        for k in range(stop-row):
            src[row+k-y0]=np.frombuffer(b,dtype="uint8",count=(x1-x0)*3,offset=row_bytes*k).reshape(x1-x0,3)
    dst=np.zeros((3,side,side),"uint8")
    reproject(src.transpose(2,0,1),dst,src_transform=t*Affine.translation(x0,y0),src_crs=record["crs"],
              dst_transform=target_transform,dst_crs=target_crs,resampling=Resampling.nearest,
              src_nodata=0,dst_nodata=0,num_threads=1,warp_mem_limit=16)
    return dst,(dst!=0).any(axis=0)
