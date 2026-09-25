"""R2 amended (2026-09-25): per-GLWD-cell blocked_pixel_share for the controls
and every item 21 site box. python experiments/item21_sites/r2_per_cell_controls.py"""
import ee, os, json, sys, numpy as np
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from ingestion.gee_client import initialize_gee
from surface_fractions.config import load_config
from surface_fractions.grid import native_grid
from surface_fractions import detectors
initialize_gee(); cfg = load_config()
def box(lon, lat, km=3):
    d = km / 2 / 111.0; e = d / np.cos(np.radians(lat)); return [lon - e, lat - d, lon + e, lat + d]
props = json.load(open(os.path.join(REPO, "experiments/item21_sites/results/aoi_proposals.json")))
aois = {"CONTROL dharavi": [72.836, 19.037, 72.862, 19.060],
        "CONTROL east_kolkata_wetlands": box(88.435, 22.535),
        "CONTROL sahara_libya": box(13.0, 25.0),
        "CONTROL orangi_original": box(67.000, 24.940),
        "CONTROL riyadh_olaya": box(46.683, 24.700)}
for k in ("makoko", "kibera", "rocinha", "lima_both_scenes", "monrovia", "karachi", "cape_town"):
    aois[f"SITE {k}"] = props[k]["box_wgs84"]
work = os.path.join(REPO, "data/surface_fractions/r2_cells"); os.makedirs(work, exist_ok=True)
out = {}
for name, b in aois.items():
    g = native_grid(ee.Geometry.Rectangle(b))
    bands, _ = detectors.export_datasets(cfg, g, work)
    known = np.ones((g.height, g.width), bool)
    m = detectors.mixed_water_vegetation(cfg, bands, known)
    ev = m["glwd_evidence"]
    out[name] = {"box": [round(v, 6) for v in b], "status": m["status"],
                 "blocked_pixel_share": round(ev["blocked_pixel_share"], 4),
                 "mangrove_mean": round(float(np.nanmean(m["mangrove_fraction"])), 4),
                 "glwd_classes": sorted(ev["classes_present"])}
    print(f"{name:32s} {m['status']:13s} blocked={ev['blocked_pixel_share']:.4f} "
          f"mangrove={out[name]['mangrove_mean']:.4f} GLWD={out[name]['glwd_classes']}", flush=True)
json.dump(out, open(os.path.join(REPO, "experiments/item21_sites/results/r2_per_cell_controls.json"), "w"), indent=1)
