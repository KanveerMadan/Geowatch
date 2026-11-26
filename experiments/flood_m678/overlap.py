"""Geographic conflicts against metadata in the pinned Round 3 branch (no label inputs)."""
import argparse
import csv
import json
import subprocess
from pathlib import Path

from pyproj import Geod
from shapely.geometry import Point, box

from screen_acquisitions import HERE, write_file
from pyproj import CRS, Transformer
from shapely.geometry import Polygon

SEARCH_HALF_M = 10_000   # the 20 km search square that place() may use (criteria addendum)


def search_square(lon, lat):
    local = CRS.from_proj4(f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m")
    t = Transformer.from_crs(local, "EPSG:4326", always_xy=True)
    h = SEARCH_HALF_M
    return Polygon([t.transform(x, y) for x, y in [(-h, -h), (h, -h), (h, h), (-h, h)]])

PIN = "f28d71446f0c3f9d180b4415b7e6f8a4fe204f5f"  # round-3 head on 2026-11-27 (was 5287883)
REGISTRIES = ("flood_core/registry/events.json", "flood_final/registry_units.json",
              "flood_round2/registry_units_round2.json")
CANDIDATES = {"r3_ems_candidates":"bounds","r3_mmflood_candidates":"bbox_at_search_point",
              "se_flash_candidates":"bbox_at_search_point","plains_candidates":"square"}
GEOD = Geod(ellps="WGS84")


def read(repo, path):
    output=subprocess.check_output(["git","-C",str(repo),"show",f"{PIN}:experiments/{path}"])
    return json.loads(output)


def entries(repo):
    for path in REGISTRIES:
        for row in read(repo,path)["units"]:
            g=row["geometry"]
            if g["type"]=="boxes":
                for area in g["boxes"]:
                    yield path,row["event_id"],box(*area["bbox"])
            elif g["type"]=="point_approx":
                yield path,row["event_id"],Point(*g["point"])
    burned=read(repo,"flood_round3/results/burned_catalog.json")
    for name,row in burned.items():
        if row.get("bbox"):
            yield "burned_catalog",name,box(*row["bbox"])
        elif row.get("centre"):
            lat,lon=row["centre"]
            yield "burned_catalog",name,Point(lon,lat)
    for name,key in CANDIDATES.items():
        for row in read(repo,"flood_round3/results/"+name+".json")["candidates"]:
            yield name,row["unit"],box(*row[key])


def conflicts(study,previous):
    p,q=study.centroid,previous.centroid
    metres=GEOD.inv(p.x,p.y,q.x,q.y)[2]
    return study.intersects(previous) or metres<=20_000


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo",type=Path)
    args=parser.parse_args()
    pool=list(entries(args.repo))
    scenes=json.loads((HERE/"scene_metadata.json").read_text())
    with (HERE/"catalog.csv").open() as f:
        rows=list(csv.DictReader(f))
    out={}
    for row in rows:
        eid=row["incident_id"]
        if row["split"]!="reserve_candidate":
            continue
        if eid not in scenes:
            out[eid]={"status":"needs_study_footprint"}
            continue
        study=search_square(float(row["longitude"]),float(row["latitude"]))
        matches=sorted({(name,key) for name,key,other in pool if conflicts(study,other)})
        out[eid]={"status":"known_geographic_conflict" if matches else "no_match_in_available_geometry",
                  "matches":matches}
    write_file(HERE/"overlap_metadata.json",json.dumps({"round3_commit":PIN,
        "sealed_manifest_available_at_commit":False,"records":out},indent=2,sort_keys=True)+"\n")


if __name__=="__main__":
    main()
