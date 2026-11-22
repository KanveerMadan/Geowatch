"""
Held-out selection and reference build (references only: no input layer, no
score, no model output is computed here).

    python -m experiments.flood_learned.heldout.select        # builds references, writes selection

Rules (fixed before any held-out reference was built):
  1. Pool: the screen's candidates (screen.py): public Copernicus EMS Flood/Storm
     activations not carried by any registry unit and not linked by the
     registry guard to any dev or reserved unit.
  2. Flood type from the activation's own text (quoted per activation in
     ACTIVATIONS), by these rules:
       fluvial       the text names a river or a river overflow as the cause
       flash_flood   the text says "flash flood", or floods with landslides
                     in steep terrain
       pluvial       heavy rainfall flooding a city; no river named as the cause
       waterlogging  prolonged flooding of a flat plain or polder
     Excluded types: glacial-lake outburst (M6), dam breach (M7), snowmelt /
     ice (M8), groundwater (M10), cyclone wind damage without flood mapping.
     Excluded: an activation from the same storm as a registry event
     (EXCLUDED_SAME_STORM), and one whose HydroBASINS main basin is a registry
     dev unit's (checked after placement, `independence`).
  3. Product per AOI: the lowest monitoring number of type DEL (round 4's
     product rule), else GRA.
  4. Box: round 4's box rule (harness_round4.place: 4 km square centred on the
     reference's flood).
  5. Qualifies: >= 50 flooded and >= 50 dry valid cells in the box (the
     project's MIN_FLOODED_CELLS / MIN_DRY_CELLS).
  6. One event per activation (each activation is one storm, i.e. one cluster):
     the qualifying AOI with the most flooded cells in its box. Ties: lowest
     AOI number.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.expanduser("~/.cache/geowatch/flood_learned/heldout")
REF_DIR = os.path.join(CACHE, "refs")
OUT = os.path.join(HERE, "results", "selection.json")

# code: (type, region (UN M49 grouping as events.REGION), quote from the activation text)
ACTIVATIONS = {
    # fluvial
    "EMSR662": ("fluvial", "africa", "River Katonga in Western Uganda flooded ... after heavy rain"),
    "EMSR774": ("fluvial", "americas", "heavy rains hit the Veracruz region causing the Papaloapan river overflow"),
    "EMSR865": ("fluvial", "americas", "severe flooding in the department of Córdoba ... Overflow of th[e] ... river"),
    "EMSR853": ("fluvial", "americas", "intense rainfall ... provinces of Andrés Ibáñez and Sara, Bolivia ... caused rivers to overflow"),
    "EMSR844": ("fluvial", "southeast_asia", "flood ... Viet Nam (Cau River, Thuong River, Ca Lo River and Day River areas)"),
    "EMSR757": ("fluvial", "europe_mediterranean", "flooding is forecast to affect the March and Morava Basins"),
    "EMSR868": ("fluvial", "europe_mediterranean", "large areas in the Greek part of the Evros River basin had been flooded"),
    "EMSR711": ("fluvial", "europe_mediterranean", "a flood event is forecast and expected over Charente River"),
    # waterlogging
    "EMSR779": ("waterlogging", "africa", "flood ... affected Departments of Logone et Chari and Mayo Danay, Cameroon (Sahelian floodplain, weeks-long inundation; second wave of EMSR772)"),
    "EMSR708": ("waterlogging", "europe_mediterranean", "a flood event is reported to have affected West Flanders, Belgium (polders)"),
    "EMSR799": ("waterlogging", "americas", "heavy rains ... departments of La Paz, Beni and Oruro, causing flooding (Beni plains)"),
    # flash flood
    "EMSR870": ("flash_flood", "americas", "heavy rainfall ... Ecuador, triggering flash floods, floods and landslides"),
    "EMSR813": ("flash_flood", "americas", "heavy rainfall ... Amazon region in Ecuador which has resulted in floods and landslides (Zamora Chinchipe)"),
    "EMSR770": ("flash_flood", "europe_mediterranean", "flood ... municipalities of Jablanica and Konjic ... (Oct 2024 torrential floods and landslides)"),
    "EMSR680": ("flash_flood", "europe_mediterranean", "red weather alert ... severe weather characterized by heavy rain (Slovenia, Aug 2023 torrential floods)"),
    "EMSR838": ("flash_flood", "south_asia", "a flash flood event during the monsoon season ... Punjab and Khyber Pakhtunkhwa provinces, Pakistan"),
    # pluvial (urban rain)
    "EMSR776": ("pluvial", "americas", "a flood ... affected Panama ... damage reported to affect many cities, towns and villages"),
    "EMSR694": ("pluvial", "europe_mediterranean", "slow-moving storm system (DANA) has affected Spain, causing heavy rains and floods"),
    "EMSR935": ("pluvial", "europe_mediterranean", "adverse weather affecting the south of Valencia province and the north of Alicante ... Up to 500 rescues"),
    "EMSR843": ("pluvial", "europe_mediterranean", "a severe storm ... affected northern Italy, particularly the Lombardy region, including the city of Milan"),
}
# Same storm as a registry unit (registry storm clusters do not carry EMS codes
# of other activations, so this is checked by hand from date and place).
EXCLUDED_SAME_STORM = {
    "EMSR789": "Ecuador 26 Feb 2025 rainfall = milagro's storm (EMSR796, 2025-02-26)",
    "EMSR772": "Cameroon Logone flood: first wave of EMSR779 (selected); one activation per flood",
}


def product_rows(code: str) -> list:
    """(aoi, monitoring, type) per AOI: lowest monitoring DEL, else GRA."""
    from experiments.flood_learned.heldout.screen import activation
    act = activation(code)
    rows = []
    for a in act["aois"]:
        ok = [p for p in a["products"] if any("_observedEventA" in l["name"]
                                              and "previous" not in l["name"]
                                              for l in p.get("layers", []))]
        for typ in ("DEL", "GRA"):
            ps = sorted((p for p in ok if p["type"] == typ),
                        key=lambda p: p.get("monitoringNumber") or 0)
            if ps:
                rows.append((a["number"], ps[0].get("monitoringNumber") or 0, typ, a["name"]))
                break
    return rows, act["eventTime"][:10]


def build_ref(code, aoi, mon, typ, event) -> dict:
    """Round 4's place() + reference() on one AOI; saved like the round caches."""
    from experiments.flood_validation import harness_round4 as H4
    from susceptibility.hydro_rasters import utm_grid
    name = f"{code.lower()}_aoi{aoi:02d}"
    p = os.path.join(REF_DIR, f"{name}.npz")
    if os.path.exists(p):
        z = np.load(p, allow_pickle=False)
        return json.loads(str(z["meta"]))
    ev = H4.place(H4._ems(code, aoi, mon, event, typ))
    if ev.get("bbox") is None:
        meta = {"unit": name, "error": "no flood centre (no flooded polygon in the extent)"}
    else:
        t, shape, crs = utm_grid(ev["bbox"])
        ref = H4._call(lambda: H4.reference(ev, t, shape, crs), f"ref {name}")
        f, v = ref["flooded"], ref["valid"]
        meta = {"unit": name, "event": event, "bbox": ev["bbox"], "centre": ev["centre"],
                "grid": {"crs": crs, "transform": list(t)[:6], "shape": list(shape)},
                "reference": ref["meta"], "block": 1,
                "flooded_cells": int((f & v).sum()), "dry_cells": int((~f & v).sum())}
        os.makedirs(REF_DIR, exist_ok=True)
        np.savez_compressed(p + ".tmp.npz", flooded=f, valid=v,
                            meta=np.array(json.dumps(meta, default=str)))
        os.replace(p + ".tmp.npz", p)
        return meta
    os.makedirs(REF_DIR, exist_ok=True)
    np.savez_compressed(p + ".tmp.npz", flooded=np.zeros((1, 1), bool),
                        valid=np.zeros((1, 1), bool), meta=np.array(json.dumps(meta)))
    os.replace(p + ".tmp.npz", p)
    return meta


def main():
    from experiments.flood_baselines.build import check_disk
    from experiments.flood_validation.harness import MIN_DRY_CELLS, MIN_FLOODED_CELLS
    from ingestion.gee_client import initialize_gee
    print(f"free disk {check_disk():.1f} GB", flush=True)
    initialize_gee()
    out = {"rules": __doc__, "activations": {}, "excluded_same_storm": EXCLUDED_SAME_STORM}
    for code, (ftype, region, quote) in ACTIVATIONS.items():
        rows, event = product_rows(code)
        aois = []
        for aoi, mon, typ, aname in rows:
            check_disk()
            t0 = time.time()
            try:
                m = build_ref(code, aoi, mon, typ, event)
            except Exception as e:      # noqa: BLE001 -- recorded
                traceback.print_exc()
                m = {"unit": f"{code.lower()}_aoi{aoi:02d}", "error": f"{type(e).__name__}: {e}"[:300]}
            m.update(aoi=aoi, monitoring=mon, product_type=typ, aoi_name=aname)
            m["qualifies"] = (m.get("flooded_cells", 0) >= MIN_FLOODED_CELLS
                              and m.get("dry_cells", 0) >= MIN_DRY_CELLS)
            aois.append({k: m.get(k) for k in ("unit", "aoi", "aoi_name", "monitoring",
                                               "product_type", "bbox", "centre", "flooded_cells",
                                               "dry_cells", "qualifies", "error")})
            print(f"   {code} AOI{aoi:02d} {aname[:30]}: {m.get('flooded_cells')} / "
                  f"{m.get('dry_cells')} {'Q' if m['qualifies'] else '-'} "
                  f"{m.get('error', '')[:80]} ({time.time() - t0:.0f} s)", flush=True)
        q = sorted((a for a in aois if a["qualifies"]), key=lambda a: (-a["flooded_cells"], a["aoi"]))
        out["activations"][code] = {"type": ftype, "region": region, "quote": quote,
                                    "event": event, "aois": aois,
                                    "chosen": q[0]["unit"] if q else None}
        with open(OUT, "w") as fh:
            json.dump(out, fh, indent=1, default=str)
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
