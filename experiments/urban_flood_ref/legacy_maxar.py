"""Locate a bounded historical Maxar tile without downloading a full GeoTIFF."""
import argparse
import json
import re
import struct
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from xml.etree import ElementTree

from rasterio.warp import transform_bounds

from .guard import authorize, authorize_window
from .grid import grid30
from .optical_catalog import grid_extent, require_space, _save
from .vhr_reference import intersects

BASE = "https://s3.amazonaws.com/dg-opendata/"
# Add a prefix only after verifying that it represents the approved incident.
COLLECTIONS = {"idai_2019": "cyclone_idai", "dorian_2019": "hurricane-dorian"}


def validate_subset(unit, bbox, first, last):
    s = authorize_window(unit, first, last)
    w,z,e,n = s["bbox"]
    if not (w-.002 <= bbox[0] < bbox[2] <= e+.002 and z-.002 <= bbox[1] < bbox[3] <= n+.002):
        raise ValueError("Requested chip extends outside the guarded site")


def _request(unit, when, key, *, ranged=None):
    site = authorize_window(unit, when, when)
    slug = COLLECTIONS[site["incident"]]
    if not re.fullmatch(rf'{re.escape(slug)}/(?:pre|post)-event/{re.escape(when)}/[A-Z0-9]+/[0-3]+\.tif',key):
        raise ValueError("Unexpected Maxar scene key")
    request = urllib.request.Request(BASE+urllib.parse.quote(key, safe="/"),
                                     headers={"Range":f"bytes={ranged[0]}-{ranged[1]}","User-Agent":"GeoWatch archive reference"})
    with urllib.request.urlopen(request, timeout=30) as resp:
        if resp.status != 206:
            raise ValueError("Server does not support a bounded range request")
        return resp.read(ranged[1] - ranged[0] + 1)


def _keys(unit, when, phase, cache):
    site = authorize_window(unit, when, when)
    prefix = f"{COLLECTIONS[site['incident']]}/{phase}-event/{when}/"
    cache_file = cache / ("keys-"+when+"-"+phase+".json")
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    require_space(cache)
    query=urllib.parse.urlencode({"list-type":"2","prefix":prefix,"max-keys":1000})
    with urllib.request.urlopen(BASE+"?"+query,timeout=25) as response:
        xml=ElementTree.fromstring(response.read(2_000_000))
    if xml.findtext("{*}IsTruncated") != "false":
        raise ValueError("Date index too large for a bounded read")
    keys=[item.findtext("{*}Key") for item in xml.findall("{*}Contents")]
    keys=[k for k in keys if re.fullmatch(re.escape(prefix)+r"[A-Z0-9]+/[0-3]+\.tif",k)]
    _save(cache_file,json.dumps(keys).encode())
    return keys


def _geotags(unit, when, key, cache):
    authorize_window(unit, when, when)
    cache_file = cache / ("geom-"+key.split("/")[-2]+"-"+Path(key).stem+".json")
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    require_space(cache)
    # These legacy TIFFs have the IFD at their end. Read only the TIFF header
    # and the IFD/georeferencing tags. No image or external overview is opened.
    first = _request(unit,when,key,ranged=(0,7))
    endian = "<" if first[:2]==b"II" else ">"
    if struct.unpack_from(endian+"H",first,2)[0] != 42:
        raise ValueError("Unsupported legacy TIFF header")
    off = struct.unpack_from(endian+"I",first,4)[0]
    raw = _request(unit,when,key,ranged=(off,off+4095))
    n = struct.unpack_from(endian+"H",raw)[0]
    entries = {t:(typ,c,v,2+12*i+8) for i in range(n)
               for t,typ,c,v in [struct.unpack_from(endian+"HHII",raw,2+12*i)]}
    def values(t):
        typ,c,ptr,valueoff = entries[t]
        fmt,size = {3:("H",2),4:("I",4),12:("d",8)}[typ]
        if c*size<=4: src,pos=raw,valueoff
        elif off<=ptr and ptr+c*size <= off+len(raw): src,pos=raw,ptr-off
        else: src,pos=_request(unit,when,key,ranged=(ptr,ptr+c*size-1)),0
        return struct.unpack_from(endian+str(c)+fmt,src,pos)
    sx,sy,_=values(33550)
    i,j,_,x,y,_=values(33922)
    x0,y0=x-sx*i,y+sy*j
    nx,ny=values(256)[0],values(257)[0]
    keys=values(34735)
    epsg=next((keys[k+3] for k in range(4,len(keys),4) if keys[k]==3072 and keys[k+1]==0),None)
    if not epsg:
        epsg=next(keys[k+3] for k in range(4,len(keys),4) if keys[k]==2048 and keys[k+1]==0)
    crs="EPSG:"+str(epsg)
    local=[x0,y0-ny*sy,x0+nx*sx,y0]
    record={"bounds":list(transform_bounds(crs,"EPSG:4326",*local,densify_pts=21)),"local_bounds":local,"crs":crs,"width":nx,"height":ny,
            "datetime":when,"visual":BASE+key,"gsd":[sx,sy],"id":key,"collection":COLLECTIONS[authorize(unit)["incident"]]}
    _save(cache_file,json.dumps(record).encode())
    return record


def quad_xy(key):
    positions=[int(c) for c in Path(key).stem]
    x=y=0
    for digit in positions:
        x=2*x+(digit%2)
        y=2*y+(digit//2)
    return x,y


def footprints(unit,when,cache):
    site=authorize_window(unit,when,when)
    phase="pre" if when<site["date"] else "post"
    grid=grid30(unit)
    bbox=grid_extent(grid)
    validate_subset(unit,bbox,when,when)
    cache=Path(cache)
    cache.mkdir(parents=True,exist_ok=True)
    keys=_keys(unit,when,phase,cache)
    groups={}
    for key in keys: groups.setdefault(key.split("/")[-2],[]).append(key)
    found=[]
    for group in groups.values():
        first=group[0]
        first_rec=_geotags(unit,when,first,cache)
        x,y=quad_xy(first); w,s,e,n=first_rec["local_bounds"]
        sx,sy=e-w,n-s
        aoi=transform_bounds("EPSG:4326",first_rec["crs"],*bbox,densify_pts=21)
        def expected(key):
            i,j=quad_xy(key)
            return [w+(i-x)*sx,s+(j-y)*sy,e+(i-x)*sx,n+(j-y)*sy]
        # Check extrapolation on a second distant tile before using it.
        last=group[-1];last_rec=_geotags(unit,when,last,cache); pred=expected(last)
        conforms=max(abs(v-u) for v,u in zip(pred,last_rec["local_bounds"])) < .01
        possible=[k for k in group if intersects(expected(k),aoi)] if conforms else group
        for k in possible:
            measured=_geotags(unit,when,k,cache)
            if intersects(measured["bounds"],bbox): found.append(measured)
    return found


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("unit");p.add_argument("dates",nargs="+");p.add_argument("--cache",type=Path,required=True)
    args=p.parse_args()
    for dt in args.dates:
        rows=footprints(args.unit,dt,args.cache)
        _save(args.cache/("hits-"+dt+".json"),json.dumps(rows,indent=2).encode())
        print(dt,len(rows),[(x["id"],x["gsd"]) for x in rows],flush=True)
