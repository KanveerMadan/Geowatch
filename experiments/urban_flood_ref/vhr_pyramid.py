"""Read individual uncompressed vendor overview tiles for a bounded optical window."""
import hashlib
import math
import os
import struct
from pathlib import Path

import numpy as np
from affine import Affine
from rasterio.enums import Resampling
from rasterio.transform import array_bounds, from_bounds
from rasterio.warp import reproject, transform_bounds

from .optical_catalog import require_space
from .vhr_scanline import _get


def _layout(url,level,cache):
    file=cache/("pyramid-"+hashlib.sha256(url.encode()).hexdigest()[:14]+"-"+str(level)+".npz")
    if file.exists():
        with np.load(file) as s: return {k:s[k] for k in s.files}
    require_space(cache)
    h=_get(url,0,7)
    order="<" if h[:2]==b"II" else ">"
    if struct.unpack_from(order+"H",h,2)[0]!=42: raise ValueError("Classic TIFF required")
    ifd=struct.unpack_from(order+"I",h,4)[0]
    for _ in range(level+1):
        if ifd==0: raise ValueError("Missing pyramid level")
        raw=_get(url,ifd,ifd+350)
        n=struct.unpack_from(order+"H",raw)[0]
        if n>27: raise ValueError("Unexpected overview IFD size")
        fields={t:(typ,count,p,2+12*i+8) for i in range(n) for t,typ,count,p in [struct.unpack_from(order+"HHII",raw,2+i*12)]}
        ifd=struct.unpack_from(order+"I",raw,2+12*n)[0]
    def tag(num):
        typ,count,pos,v=fields[num];fmt,width={3:("H",2),4:("I",4)}[typ]
        if count*width<=4: return struct.unpack_from(order+str(count)+fmt,raw,v)
        return struct.unpack(order+str(count)+fmt,_get(url,pos,pos+count*width-1))
    w,h=tag(256)[0],tag(257)[0]
    bw,bh=tag(322)[0],tag(323)[0]
    if (tag(258),tag(259),tag(262),tag(277),tag(284))!=((8,8,8),(1,),(2,),(3,),(2,)):
        raise ValueError("Expected RGB, uncompressed planar-separate overview")
    nx,ny=math.ceil(w/bw),math.ceil(h/bh)
    offsets,counts=np.array(tag(324)).reshape(3,ny,nx),np.array(tag(325)).reshape(3,ny,nx)
    if not (counts==bw*bh).all(): raise ValueError("Inconsistent RGB block storage")
    item=dict(offsets=offsets,counts=counts,dims=np.array([h,w,bh,bw]))
    part=file.with_suffix(".part.npz");np.savez_compressed(part,**item);os.replace(part,file)
    return item


def chip(record,href,crs,t,shape,cache,authorize,level=0):
    bbox=array_bounds(*shape,t)
    geo=transform_bounds(crs,"EPSG:4326",*bbox,densify_pts=21)
    dt=record["datetime"][:10];authorize(geo,dt,dt)
    url=href+".ovr"
    key=hashlib.sha256(url.encode()).hexdigest()[:14]
    lay=_layout(url,level,cache)
    h,w,bh,bw=map(int,lay["dims"]);tr=from_bounds(*record["local_bounds"],w,h)
    r=transform_bounds(crs,record["crs"],*bbox,densify_pts=21)
    ax,ay=(~tr)*(r[0],r[3]);bx,by=(~tr)*(r[2],r[1])
    i0,j0=max(0,int(ax)//bw),max(0,int(ay)//bh)
    i1,j1=min(math.ceil(w/bw),math.ceil(bx/bw)),min(math.ceil(h/bh),math.ceil(by/bh))
    if not (0<i1-i0<=24 and 0<j1-j0<=24): raise ValueError("Requested tile exceeds optical window budget")
    region=np.zeros((3,(j1-j0)*bh,(i1-i0)*bw),"uint8")
    tasks=[]
    for j in range(j0,j1):
        for i in range(i0,i1):
            file=cache/f"pyr-{key}-{level}-{j}-{i}.npy"
            if file.exists():
                region[:,(j-j0)*bh:(j-j0+1)*bh,(i-i0)*bw:(i-i0+1)*bw]=np.load(file,allow_pickle=False)
                continue
            for band in range(3):
                pos=int(lay["offsets"][band,j,i])
                tasks.append((pos,pos+bw*bh-1,band,j,i))
    # S3 supports a single byte range. Coalesce tile-adjacent buffers; never
    # download a full image or retain pixels from outside the requested region.
    groups=[]
    for item in sorted(tasks):
        if groups and item[0]-groups[-1][-1][1] <= 16385 and item[1]-groups[-1][0][0] < 384000:
            groups[-1].append(item)
        else:
            groups.append([item])
    from concurrent.futures import ThreadPoolExecutor
    def fetch(group):
        start,end=group[0][0],group[-1][1]
        return start,_get(url,start,end)
    with ThreadPoolExecutor(max_workers=3) as executor:
        for group,(base,data) in zip(groups,executor.map(fetch,groups)):
            for start,end,band,j,i in group:
                dest=region[band,(j-j0)*bh:(j-j0+1)*bh,(i-i0)*bw:(i-i0+1)*bw]
                dest[:]=np.frombuffer(data,dtype="uint8",count=bw*bh,offset=start-base).reshape(bh,bw)
    # Keep only the bounded output chip on disk, not the containing source blocks.
    dst=np.zeros((3,*shape),"uint8")
    reproject(region,dst,src_transform=tr*Affine.translation(i0*bw,j0*bh),src_crs=record["crs"],
              dst_transform=t,dst_crs=crs,src_nodata=0,dst_nodata=0,resampling=Resampling.nearest,
              num_threads=1,warp_mem_limit=16)
    return dst,(dst!=0).any(axis=0)
