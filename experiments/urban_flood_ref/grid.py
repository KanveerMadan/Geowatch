"""Reconstruct the upstream flood model's snapped UTM grid exactly."""
import math
from pyproj import Transformer
from .guard import authorize


def grid30(unit):
    w,s,e,n = authorize(unit)['bbox']
    zone = int(((w+e)/2+180)//6)+1
    code = (32600 if s+n >= 0 else 32700)+zone
    xs,ys = Transformer.from_crs(4326,code,always_xy=True).transform([w,e,w,e],[s,s,n,n])
    x0 = math.floor(min(xs)/30)*30
    y0 = math.ceil(max(ys)/30)*30
    return {'crs':f'EPSG:{code}','transform':[30,0,x0,0,-30,y0],
            'shape':[math.ceil((y0-min(ys))/30),math.ceil((max(xs)-x0)/30)]}
