"""Write an experimental water/forest change map for one small area."""
import argparse
from datetime import date, timedelta
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import box, mapping
from shapely.ops import transform

from .data import connect, forest_cover, grid, history, permanence, save
from .forest import forest
from .monitor_lock import ee_lock
from .water import water


def run(args):
    first, last = map(date.fromisoformat, (args.start, args.end))
    if last <= first or not(-180 <= args.lon < 180 and -80 <= args.lat <= 84):
        raise ValueError("select an ordered monitoring interval and a location within local UTM coverage")
    if args.output.exists():
        raise FileExistsError(args.output)
    crs,cells=grid(args.lon,args.lat,args.side)
    ee=connect()
    lookback = 731 if "forest" in args.targets else 120
    rows=history(ee,crs,cells,str(first-timedelta(days=lookback)),str(last))
    water_prior=permanence(ee,crs,cells,args.start) if "water" in args.targets else [None]*len(cells)
    canopy=forest_cover(ee,crs,cells,args.start) if "forest" in args.targets else [None]*len(cells)
    inverse=Transformer.from_crs(crs,4326,always_xy=True).transform
    features=[]
    for (x,y),h,p,trees in zip(cells,rows,water_prior,canopy,strict=True):
        prop={"cell_id":f"{crs}/{x}/{y+100}"}
        if "water" in args.targets:
            short=[r for r in h if r["day"] >= str(first-timedelta(days=120))]
            prop["water"]=water(short,args.start,args.end,p)
        if "forest" in args.targets:
            prop["forest"]=forest(h,args.start,args.end,trees)
        features.append({"type":"Feature","properties":prop,
                         "geometry":mapping(transform(inverse,box(x,y,x+100,y+100)))})
    save(args.output,{"type":"FeatureCollection","period":[args.start,args.end],
                      "validation":"experimental","features":features})


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lon",required=True,type=float)
    parser.add_argument("--lat",required=True,type=float)
    parser.add_argument("--start",required=True)
    parser.add_argument("--end",required=True,help="exclusive end date")
    parser.add_argument("--side",type=int,choices=range(1,12),default=3,help="100 m cells per side")
    parser.add_argument("--targets",nargs="+",choices=("water","forest"),default=["water","forest"])
    parser.add_argument("--output",required=True,type=Path)
    with ee_lock():
        run(parser.parse_args())
