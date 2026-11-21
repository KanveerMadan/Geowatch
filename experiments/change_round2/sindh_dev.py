"""A second seen monsoon flood: independent S2 reference polygons versus radar only."""
import hashlib
import mmap
import struct
from pathlib import Path

import numpy as np
import pyogrio
import shapely
from pyproj import Transformer
from .data import HERE,connect,history,permanence,save
from .water import water

def sample(folder):
    stem="S2_20220831_{}_Sindh.shp"
    flood=folder/stem.format("FloodExtent")
    extent=pyogrio.read_dataframe(folder/stem.format("AnalysisExtent")).to_crs(32642).geometry.union_all()
    cx,cy=extent.centroid.coords[0]
    # 1 km spatial separation in a fixed 40 km square around the source AOI centre.
    x0,y0=int(cx//100)*100-20000,int(cy//100)*100-20000
    cells=[(x0+1000*i,y0+1000*j) for i in range(40) for j in range(40)]
    pts=np.array([[(x+a,y+b) for a in range(10,100,20) for b in range(10,100,20)] for x,y in cells])
    lon,lat=Transformer.from_crs(32642,4326,always_xy=True).transform(pts[:,:,0],pts[:,:,1])
    inside=np.zeros(lon.shape,bool)
    lon_lo,lon_hi,lat_lo,lat_hi=lon.min(),lon.max(),lat.min(),lat.max()
    attrs=pyogrio.read_dataframe(flood,read_geometry=False)
    with flood.open('rb') as fh,mmap.mmap(fh.fileno(),0,access=mmap.ACCESS_READ) as mm:
        at=100
        for f in attrs.itertuples():
            _,words=struct.unpack_from(">ii",mm,at); content=at+8; at=content+2*words
            if f.Water_Clas!="Flood Water":continue
            assert f.Sensor_ID=="Sentinel-2" and str(f.Sensor_Dat)[:10]=="2022-08-31"
            assert struct.unpack_from("<i",mm,content)[0]==5
            n,k=struct.unpack_from("<ii",mm,content+36)
            offsets=np.frombuffer(mm,"<i4",n,content+44).tolist()+[k]
            xy=np.frombuffer(mm,"<f8",2*k,content+44+4*n).reshape(-1,2)
            mask=np.zeros(lon.shape,bool)
            # A spatial index over sample points keeps the multipart source read bounded.
            points=shapely.points(lon.ravel(),lat.ravel())
            tree=shapely.STRtree(points)
            for a,b in zip(offsets,offsets[1:]):
                ring=xy[a:b]
                lo=ring.min(axis=0); hi=ring.max(axis=0)
                if hi[0]<lon_lo or lo[0]>lon_hi or hi[1]<lat_lo or lo[1]>lat_hi:continue
                polygon=shapely.Polygon(ring)
                idx=tree.query(polygon,predicate="contains")
                mask.flat[idx]^=True
            inside|=mask
            del xy,ring
    inside &= shapely.contains_xy(extent,pts[:,:,0],pts[:,:,1])
    available=[c for c,yes in zip(cells,inside.all(axis=1)) if yes]
    return sorted(available,key=lambda c:hashlib.sha256(str(c).encode()).digest())[:48]

def main():
    folder=Path.home()/".cache/geowatch/flood_refs/unosat/FL20220808PAK_SHP"
    cells=sample(folder)
    if not cells:raise RuntimeError("no mapped flood cells")
    ee=connect(); start="2022-08-01"; end="2022-09-01"
    rows=history(ee,"EPSG:32642",cells,"2022-03-01",end,sensors=("radar",))
    masks=permanence(ee,"EPSG:32642",cells,start)
    results=[]
    for cell,h,p in zip(cells,rows,masks,strict=True):
        r=water(h,start,end,p)
        results.append({"xy":cell,"confirmed":next(iter(r["gain"]),None),"judged":"gain" in r["observed_targets"]})
    save(HERE/"sindh_dev.json",{"source":"UNOSAT FL20220808PAK Sentinel-2 August 31 2022","zero_hits":0,"cells":results})
if __name__=="__main__":main()
