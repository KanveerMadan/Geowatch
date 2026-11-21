"""
Add HydroBASINS ids to events.json (flood-core prototype). Read-only Earth
Engine lookup of WWF/HydroSHEDS/v1/Basins polygons at each unit's centre
point (box centre for dev units; the approximate town point for reserved
units). No raster, reference or score is read.

MAIN_BAS is the basin draining to the sea (the whole river system); the
level-4/6 ids are nested sub-basins. Which level counts as "same basin" for
the guard is a judgement recorded in README.md, not decided here.
Run with an Earth Engine-enabled interpreter (geowatch-env).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEVELS = (4, 6)


def centre(u):
    g = u["geometry"]
    if g["type"] == "point_approx":
        return g["point"]
    w, s, e, n = g["boxes"][-1]["bbox"]
    return [(w + e) / 2, (s + n) / 2]


def main(env_file):
    from dotenv import dotenv_values
    import ee
    ee.Initialize(project=dotenv_values(env_file).get("GEE_PROJECT_ID"))
    path = os.path.join(HERE, "events.json")
    reg = json.load(open(path))
    pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point(centre(u)), {"event_id": u["event_id"]})
                                for u in reg["units"] if u["geometry"]["type"] != "none"])
    found = {}
    for lev in LEVELS:
        basins = ee.FeatureCollection(f"WWF/HydroSHEDS/v1/Basins/hybas_{lev}")
        def tag(f, basins=basins):
            hit = basins.filterBounds(f.geometry())
            ids = ee.Algorithms.If(hit.size().gt(0),
                                   ee.Dictionary({"HYBAS_ID": hit.first().get("HYBAS_ID"),
                                                  "MAIN_BAS": hit.first().get("MAIN_BAS")}),
                                   ee.Dictionary({"HYBAS_ID": -1, "MAIN_BAS": -1}))
            return f.set(ee.Dictionary(ids))
        rows = pts.map(tag).select(["event_id", "HYBAS_ID", "MAIN_BAS"]).getInfo()
        for f in rows["features"]:
            p = f["properties"]
            if p.get("HYBAS_ID", -1) == -1:
                continue            # centre point in the sea: no basin
            found.setdefault(p["event_id"], {})[f"hybas_{lev}"] = p.get("HYBAS_ID")
            found[p["event_id"]]["main_bas"] = p.get("MAIN_BAS")
    for u in reg["units"]:
        u["basins"] = found.get(u["event_id"], {"note": "no geometry, or centre point outside HydroBASINS"})
    reg["basins_source"] = "WWF/HydroSHEDS/v1/Basins hybas_4, hybas_6 (centre point)"
    json.dump(reg, open(path, "w"), indent=1)
    print(json.dumps({k: v for k, v in found.items()}, indent=0)[:4000])


if __name__ == "__main__":
    main(sys.argv[1])
