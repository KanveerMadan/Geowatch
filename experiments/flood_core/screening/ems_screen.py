"""Read-only screening of cached EMS activations EMSR773 (Valencia DANA) and EMSR692 (Daniel): AOIs, products,
image times, and the cached DEL layer's flooded geometry summary. Dev events only; nothing is scored."""
import json, os, sys
from shapely.geometry import shape
from shapely.ops import unary_union
from shapely import wkt
from pyproj import Geod
C = os.path.expanduser("~/.cache/geowatch/flood_refs/ems")
geod = Geod(ellps="WGS84")
def km2(g): return abs(geod.geometry_area_perimeter(g)[0]) / 1e6
for code in ("EMSR773", "EMSR692"):
    act = json.load(open(os.path.join(C, f"{code}.json")))["results"][0]
    print("==", code, act.get("name"), "eventTime", act.get("eventTime"), "activationTime", act.get("activationTime"))
    for a in act["aois"]:
        prods = []
        for p in a["products"]:
            imgs = sorted(i["acquisitionTime"][:16] + " " + i["sensorName"] for i in p.get("images", []))
            prods.append(f'{p["type"]} m{p.get("monitoringNumber") or 0}: {"; ".join(imgs[:3])}')
        ext = wkt.loads(a["products"][0]["extent"]) if a["products"] and a["products"][0].get("extent") else None
        c = ext.centroid if ext else None
        print(f'  AOI{a["number"]:02d} {a["name"]!r} centre={None if c is None else (round(c.y,3), round(c.x,3))} extent_km2={None if ext is None else round(km2(ext))}')
        for p in prods: print("     ", p)
for lay in ("EMSR773_AOI03_DEL_PRODUCT_observedEventA_v1.json", "EMSR692_AOI01_DEL_MONIT03_observedEventA_v3.json"):
    fc = json.load(open(os.path.join(C, "layers", lay)))
    by = {}
    for f in fc["features"]:
        n = f["properties"].get("notation")
        if f.get("geometry"): by.setdefault(n, []).append(shape(f["geometry"]))
    print("==", lay)
    for n, gs in by.items():
        u = unary_union(gs); b = u.bounds
        print(f"   {n}: {len(gs)} polys, {km2(u):.2f} km2, bounds W{b[0]:.3f} S{b[1]:.3f} E{b[2]:.3f} N{b[3]:.3f}, centroid ({u.centroid.y:.3f}, {u.centroid.x:.3f})")
    print("   property keys:", sorted(fc["features"][0]["properties"].keys()))
