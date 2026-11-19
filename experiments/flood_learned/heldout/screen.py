"""
Held-out candidate screen (metadata only: no reference raster, no score).

    python -m experiments.flood_learned.heldout.screen

1. Every public Copernicus EMS rapid-mapping activation of category Flood or
   Storm (public-activations-info).
2. Per activation, every AOI product of type DEL (or GRA where an AOI has no
   DEL, as round 4 did for Derna) with an observedEventA layer.
3. Refused, before anything else is read:
   * an activation code any registry unit already carries (rounds 1-4 and the
     baselines used it);
   * a unit the registry guard links to ANY registry unit, dev or reserved
     (alias product, box intersection, proximity within PROXIMITY_KM of a dev
     box, same storm cluster -> blocked; basin / region links are recorded
     and also refused here, because a held-out set must be independent and no
     signed exception exists for these).
Writes results/heldout_candidates.json (one row per AOI product).
"""
from __future__ import annotations

import json
import os
import sys

from experiments.flood_core.registry import registry as REG
from experiments.flood_validation import references as R

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results", "heldout_candidates.json")
INFO_URL = ("https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/"
            "public-activations-info/?limit=500")
CATEGORIES = ("Flood", "Storm")


def registry_codes(reg) -> set:
    import re
    return {c for u in reg["units"] for c in re.findall(r"EMSR\d+", json.dumps(u))}


def activation(code: str) -> dict:
    raw = R._fetch(R.EMS_API.format(code=code), os.path.join(R.CACHE, "ems", f"{code}.json"))
    return json.loads(raw)["results"][0]


def products(act: dict) -> list:
    from shapely import wkt
    out = []
    for a in act["aois"]:
        prods = [p for p in a["products"] if any("_observedEventA" in l["name"]
                                                 and "previous" not in l["name"]
                                                 for l in p.get("layers", []))]
        dels = [p for p in prods if p["type"] == "DEL"]
        for p in (dels or [p for p in prods if p["type"] == "GRA"]):
            ext = wkt.loads(p["extent"])
            c = ext.centroid
            out.append({"code": act["code"], "aoi": a["number"], "aoi_name": a["name"],
                        "product_type": p["type"], "monitoring": p.get("monitoringNumber") or 0,
                        "event_time": act["eventTime"], "countries": act.get("countries"),
                        "name": act["name"], "reason": (act.get("reason") or "")[:600],
                        "centroid": [c.y, c.x], "extent_bounds": list(ext.bounds),
                        "images": [{"sensor": i["sensorName"], "res": i["resolutionClass"],
                                    "acquired": i["acquisitionTime"]} for i in p["images"]]})
    return out


def unit_for(row: dict) -> dict:
    """An ad-hoc registry unit (point geometry) for the guard; nothing is written."""
    return {"event_id": f"{row['code']}_aoi{row['aoi']:02d}_m{row['monitoring']}",
            "role": "candidate", "products": [row["code"]],
            "geometry": {"type": "point_approx",
                         "point": [row["centroid"][1], row["centroid"][0]]}}   # [lon, lat]


def main():
    reg = REG.load()
    used = registry_codes(reg)
    raw = R._fetch(INFO_URL, os.path.join(R.CACHE, "ems", "public_activations_info.json"))
    acts = [a for a in json.loads(raw)["results"] if a["category"] in CATEGORIES]
    rows, refused = [], []
    for a in acts:
        if a["code"] in used:
            refused.append({"code": a["code"], "why": "activation used by a registry unit"})
            continue
        try:
            prods = products(activation(a["code"]))
        except Exception as e:      # noqa: BLE001 -- recorded
            refused.append({"code": a["code"], "why": f"activation unreadable: {e}"[:200]})
            continue
        for p in prods:
            u = unit_for(p)
            cs = [c for role in ("dev", "reserved") for c in REG.conflicts(reg, u, role)]
            if cs:
                refused.append({"code": p["code"], "aoi": p["aoi"], "why": "registry link",
                                "links": cs})
                continue
            p["category"] = a["category"]
            rows.append(p)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump({"source": INFO_URL, "n_activations": len(acts), "candidates": rows,
                   "refused": refused}, fh, indent=1)
    print(f"{len(acts)} activations; {len(rows)} candidate AOI products; {len(refused)} refused")
    return 0


if __name__ == "__main__":
    sys.exit(main())
