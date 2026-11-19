"""
Add the flood_final DEV and RESERVED units to the flood-core registry.

    python -m experiments.flood_final.register_final            # dry run
    python -m experiments.flood_final.register_final --write    # events.json + registry_units.json

DEV new units: role dev, exposure 3 (reference built and counted), geometry =
their round-4-rule boxes. A DEV unit linked by ANY rule to ANY reserved unit
(the round-4b three or this run's) is dropped, so no development data shares
a storm, box, product or basin with a held-out event.
RESERVED units: role reserved, exposure 2 (EMS product metadata) or 1 (S1:
a town point and a date from general reporting), geometry point_approx.
A reserved unit with a block-severity link to any DEV unit is dropped; with an
exception-severity link (basin, region) it is dropped too, unless listed in
events_final.ACCEPTED_EXCEPTION_LINKS (DECISIONS.md D6).
"""
from __future__ import annotations

import json
import os
import sys

from experiments.flood_core.registry import registry as REG
from experiments.flood_final import events_final as EF

HERE = os.path.dirname(os.path.abspath(__file__))
UNITS_OUT = os.path.join(HERE, "registry_units.json")
SEL = os.path.join(HERE, "..", "flood_learned", "heldout", "results", "selection.json")
ROUND = "flood_final"


def dev_units() -> list:
    sel = json.load(open(SEL))["activations"]
    out = []
    for code, (tags, region) in EF.DEV_NEW.items():
        a = sel[code]
        q = sorted((x for x in a["aois"] if x["qualifies"]),
                   key=lambda x: (-x["flooded_cells"], x["aoi"]))[:EF.DEV_AOIS_PER_ACTIVATION]
        for x in q:
            out.append({"event_id": x["unit"], "role": "dev", "kind": "event", "date": a["event"],
                        "storm_cluster": code, "region_cluster": None,
                        "products": [f"{code}:AOI{x['aoi']:02d}"],
                        "uses": [{"round": ROUND, "module": t, "role": "dev"} for t in tags],
                        "exposure_level": 3,
                        "exposure_note": "flood_learned/heldout/select.py: EMS reference built, "
                                         "flooded/dry counted; not scored",
                        "geometry": {"type": "boxes", "boxes": [{"round": ROUND, "module": tags[0],
                                                                 "bbox": x["bbox"]}]},
                        "flood_final": {"tags": list(tags), "region": region,
                                        "aoi_name": x["aoi_name"], "monitoring": x["monitoring"],
                                        "product_type": x["product_type"],
                                        "flooded_cells": x["flooded_cells"],
                                        "dry_cells": x["dry_cells"]}})
    return out


def reserved_units() -> list:
    from shapely import wkt
    from experiments.flood_learned.heldout.screen import activation
    out = []
    for code, (tags, region, quote) in EF.RESERVED_EMS.items():
        act = activation(code)
        rows = []
        for a in sorted(act["aois"], key=lambda a: a["number"]):
            ok = [p for p in a["products"] if any("_observedEventA" in l["name"]
                                                  and "previous" not in l["name"]
                                                  for l in p.get("layers", []))]
            for typ in ("DEL", "GRA"):
                ps = sorted((p for p in ok if p["type"] == typ),
                            key=lambda p: p.get("monitoringNumber") or 0)
                if ps:
                    rows.append((a["number"], a["name"], typ, ps[0].get("monitoringNumber") or 0,
                                 wkt.loads(ps[0]["extent"]).centroid))
                    break
        for aoi, name, typ, mon, c in rows[:EF.RESERVED_AOIS_PER_ACTIVATION]:
            out.append({"event_id": f"r_{code.lower()}_aoi{aoi:02d}", "role": "reserved",
                        "kind": "event", "date": act["eventTime"][:10], "storm_cluster": code,
                        "region_cluster": None, "products": [f"{code}:AOI{aoi:02d}"],
                        "uses": [{"round": ROUND, "module": t, "role": "registered_test"}
                                 for t in tags],
                        "exposure_level": 2,
                        "exposure_note": "EMS activation text and product metadata (AOI name, "
                                         "type, monitoring number, extent centroid); no layer read",
                        "geometry": {"type": "point_approx", "point": [c.x, c.y],
                                     "note": "centroid of the EMS product extent (metadata)"},
                        "flood_final": {"tags": list(tags), "region": region, "quote": quote,
                                        "aoi_name": name, "product_type": typ, "monitoring": mon,
                                        "reference": ["ems", code, aoi, mon, typ]}})
    for name, (tags, region, pt, date, basis) in EF.RESERVED_S1.items():
        out.append({"event_id": name, "role": "reserved", "kind": "event", "date": date,
                    "storm_cluster": name, "region_cluster": None, "products": ["S1"],
                    "uses": [{"round": ROUND, "module": t, "role": "registered_test"} for t in tags],
                    "exposure_level": 1,
                    "exposure_note": "town point and date from general reporting; no image read",
                    "geometry": {"type": "point_approx", "point": pt, "note": basis},
                    "flood_final": {"tags": list(tags), "region": region, "basis": basis,
                                    "reference": ["s1", pt[1], pt[0], date]}})
    return out


def basins(points: dict) -> dict:
    """HydroBASINS ids at each point: the lookup of registry/annotate_basins.py."""
    import ee
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point(p), {"event_id": k})
                               for k, p in points.items()])
    found = {}
    for lev in (4, 6):
        bas = ee.FeatureCollection(f"WWF/HydroSHEDS/v1/Basins/hybas_{lev}")

        def tag(f, bas=bas):
            hit = bas.filterBounds(f.geometry())
            return f.set(ee.Dictionary(ee.Algorithms.If(
                hit.size().gt(0), ee.Dictionary({"HYBAS_ID": hit.first().get("HYBAS_ID"),
                                                 "MAIN_BAS": hit.first().get("MAIN_BAS")}),
                ee.Dictionary({"HYBAS_ID": -1, "MAIN_BAS": -1}))))
        for f in fc.map(tag).getInfo()["features"]:
            p = f["properties"]
            if p.get("HYBAS_ID", -1) == -1:
                continue
            found.setdefault(p["event_id"], {})[f"hybas_{lev}"] = p["HYBAS_ID"]
            found[p["event_id"]]["main_bas"] = p["MAIN_BAS"]
    return found


def centre(u):
    g = u["geometry"]
    if g["type"] == "point_approx":
        return g["point"]
    w, s, e, n = g["boxes"][-1]["bbox"]
    return [(w + e) / 2, (s + n) / 2]


def main(argv=None):
    write = "--write" in (argv or sys.argv[1:])
    reg = REG.load()
    have = set(REG.units(reg))
    dev, res = dev_units(), reserved_units()
    for u in dev + res:
        if u["event_id"] in have:
            raise SystemExit(f"{u['event_id']} already registered")
    b = basins({u["event_id"]: centre(u) for u in dev + res})
    for u in dev + res:
        u["basins"] = b.get(u["event_id"], {"note": "centre outside HydroBASINS"})
    log = {"dropped_dev": [], "dropped_reserved": [], "accepted_exception_links": {}}
    all_res = [u for u in reg["units"] if u["role"] == "reserved"] + res
    kept_dev = []
    for u in dev:
        links = [(r["event_id"], rule) for r in all_res for rule, _ in REG.links(u, r)]
        if links:
            log["dropped_dev"].append({"event_id": u["event_id"], "links": links})
        else:
            kept_dev.append(u)
    all_dev = [u for u in reg["units"] if u["role"] == "dev"] + kept_dev
    kept_res = []
    for u in res:
        links = [(d["event_id"], rule, sev) for d in all_dev for rule, sev in REG.links(u, d)]
        block = [x for x in links if x[2] == REG.BLOCK]
        exc = [x for x in links if x[2] != REG.BLOCK]
        if block or (exc and u["event_id"] not in EF.ACCEPTED_EXCEPTION_LINKS):
            log["dropped_reserved"].append({"event_id": u["event_id"], "links": links})
            continue
        if exc:
            log["accepted_exception_links"][u["event_id"]] = exc
        kept_res.append(u)
    for k in ("dropped_dev", "dropped_reserved"):
        for x in log[k]:
            print(k, x["event_id"], x["links"][:4])
    for k, v in log["accepted_exception_links"].items():
        print("accepted exception", k, v[:4])
    print(f"DEV new kept {len(kept_dev)}/{len(dev)}; RESERVED kept {len(kept_res)}/{len(res)}")
    if write:
        reg["units"].extend(kept_dev + kept_res)
        with open(REG.PATH, "w") as fh:
            json.dump(reg, fh, indent=1)
        with open(UNITS_OUT, "w") as fh:
            json.dump({"units": kept_dev + kept_res, "log": log}, fh, indent=1)
        print("wrote", REG.PATH, "and", UNITS_OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
