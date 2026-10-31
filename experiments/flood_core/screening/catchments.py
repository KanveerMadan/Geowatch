"""Read-only: MERIT upa (largest drainage line near points) and HydroBASINS lev-12 upstream area, for screening
the Valencia (Poyo) and Volos/Thessaly domains. Inputs only, dev events only."""
import json
from dotenv import dotenv_values
import ee
ee.Initialize(project=dotenv_values("/Users/kanveermadan/geowatch/.env").get("GEE_PROJECT_ID"))
upa = ee.Image("MERIT/Hydro/v1_0_1").select("upa")
pts = {  # (lon, lat), radius m
 "poyo_at_paiporta": (-0.4177, 39.428, 600), "poyo_at_picanya": (-0.435, 39.434, 600),
 "poyo_outlet_albufera(approx)": (-0.375, 39.385, 1500), "horta_sud_r4_box_centre": (-0.4984, 39.4471, 2000),
 "turia_new_channel_near_valencia": (-0.39, 39.44, 800), "albufera_lagoon_centre": (-0.34, 39.33, 3000),
 "volos_city": (22.942, 39.362, 2000), "volos_r3_r4_box_palamas": (22.0689, 39.4476, 2000),
 "pineios_at_larissa": (22.42, 39.64, 1500)}
fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([v[0], v[1]]).buffer(v[2]), {"k": k}) for k, v in pts.items()])
r = upa.reduceRegions(fc, ee.Reducer.max(), 90).getInfo()
print("MERIT upa max km2:", {f["properties"]["k"]: round(f["properties"]["max"]) for f in r["features"]})
# HydroBASINS level 12 at the Paiporta point: its own and upstream area (UP_AREA)
b = ee.FeatureCollection("WWF/HydroSHEDS/v1/Basins/hybas_12")
for k in ("poyo_at_paiporta", "poyo_outlet_albufera(approx)", "volos_city"):
    lon, lat, _ = pts[k]
    f = b.filterBounds(ee.Geometry.Point([lon, lat])).first()
    print(k, "hybas12", f.toDictionary(["HYBAS_ID", "SUB_AREA", "UP_AREA", "NEXT_DOWN"]).getInfo())
