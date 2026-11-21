"""Part B screening statistics (read-only Earth Engine reductions; nothing
downloaded, nothing scored). MERIT Hydro upstream area (upa, km2): the
largest value within a radius of each point -- the radius is part of the
answer, because a point beside a channel reads a small tributary.

    python -m experiments.flood_baselines.screen_partb
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POINTS = {   # name: (lon, lat, radius_m)
    "valencia/poyo_at_paiporta": (-0.4177, 39.428, 600),
    "valencia/poyo_outlet_albufera": (-0.375, 39.385, 1500),
    "valencia/r4_box_centre": (-0.4984, 39.4471, 2000),
    "volos_city/torrent_mouths": (22.942, 39.362, 2000),
    "thessaly/r4_box_palamas_2km": (22.0689, 39.4476, 2000),
    "thessaly/r4_box_palamas_5km": (22.0689, 39.4476, 5000),
    "thessaly/pineios_larissa_4km": (22.42, 39.64, 4000),
    "thessaly/pineios_mouth_4km": (22.70, 39.88, 4000),
}


def main():
    import ee
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    upa = ee.Image("MERIT/Hydro/v1_0_1").select("upa")
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([lo, la]).buffer(r), {"k": k})
                               for k, (lo, la, r) in POINTS.items()])
    got = upa.reduceRegions(fc, ee.Reducer.max(), 90).getInfo()
    out = {f["properties"]["k"]: {"upa_max_km2": round(f["properties"]["max"]),
                                  "radius_m": POINTS[f["properties"]["k"]][2]}
           for f in got["features"]}
    path = os.path.join(HERE, "results", "screen_partb.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
