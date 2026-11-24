"""Render a snapped 30 m cell for independent optical review at native detail."""
import math
import numpy as np
import rasterio
from affine import Affine
from PIL import Image,ImageDraw
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT


def preview(path, xy, *, planet=False):
    with rasterio.open(path) as ds:
        x,y=ds.transform*(xy[0]*ds.width/400,xy[1]*ds.height/400)
        lon,lat=Transformer.from_crs(ds.crs,4326,always_xy=True).transform(x,y)
        zone=(32600 if lat>=0 else 32700)+math.floor((lon+180)/6)+1
        x,y=Transformer.from_crs(4326,zone,always_xy=True).transform(lon,lat)
        col,row=math.floor(x/30),math.floor(y/30)
        t=Affine(.5,0,col*30-30,0,-.5,row*30+60)
        with WarpedVRT(ds,crs=f'EPSG:{zone}',transform=t,width=180,height=180,resampling=Resampling.nearest) as src:
            rgb=np.moveaxis(src.read([3,2,1] if planet else [1,2,3]),0,2)
        valid=rgb.max(2)>0
        if valid.any():
            low,high=np.percentile(rgb[valid],[1,99])
            rgb=np.uint8(np.clip((rgb.astype(float)-low)/max(1,high-low),0,1)*255)
        im=Image.fromarray(rgb)
        draw=ImageDraw.Draw(im)
        draw.rectangle((59,59,120,120),outline='#32f9dc')
        return im,{'epsg':zone,'col':col,'row':row,
                   'center_lonlat':Transformer.from_crs(zone,4326,always_xy=True).transform((col+.5)*30,(row+.5)*30),
                   'all_rgb_present':bool(valid[60:120,60:120].all())}
