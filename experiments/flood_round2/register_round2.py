"""
Register flood_round2 units in the flood-core registry.

    python -m experiments.flood_round2.register_round2 reserved [--write]
    python -m experiments.flood_round2.register_round2 dev [--write]

`reserved` does two things:
1. The flood_final RESERVED units become role dev, exposure 6 (scored once, results public; R6).
   Geometry becomes their reference box (from the cached reference metadata) where one exists, so box rules can see them.
2. It adds RESERVED_EMS_R2 + RESERVED_S1_R2 (point_approx; exposure 2 or 1).
   A reserved unit with any link to any dev unit (block, or an exception not in ACCEPTED_EXCEPTION_LINKS) is dropped.
   Point-to-point proximity (< PROXIMITY_KM), which registry.links() does not test, is checked here too.

`dev` adds DEV_EMS_R2 (references built by flood_round2.build_dev_refs) and DEV_S1_R2.
A DEV unit with any link to any reserved unit is dropped.
"""
from __future__ import annotations

import json
import math
import os
import sys

from experiments.flood_core.registry import registry as REG
from experiments.flood_final import register_final as RF
from experiments.flood_round2 import events_round2 as E

HERE = os.path.dirname(os.path.abspath(__file__))
UNITS_OUT = os.path.join(HERE, "registry_units_round2.json")
ROUND = "flood_round2"
R1_REFS = os.path.expanduser("~/.cache/geowatch/flood_final/heldout/refs")
DEV_REFS = os.path.expanduser("~/.cache/geowatch/flood_round2/dev_refs")


def _km(p, q):
    lat = math.radians((p[1] + q[1]) / 2)
    return math.hypot((p[0] - q[0]) * 111.32 * math.cos(lat), (p[1] - q[1]) * 110.57)


def _point(u):
    return RF.centre(u)


def flip_round1(reg) -> list:
    import numpy as np
    out = []
    for u in reg["units"]:
        if u["role"] != "reserved" or not any(x.get("round") == "flood_final" for x in u.get("uses", [])):
            continue
        u["role"] = "dev"
        u["exposure_level"] = 6
        u["exposure_note"] = ("flood_final held-out pass 2026-11-20 (scored once, published); "
                              "used as DEV from flood_round2")
        u.setdefault("uses", []).append({"round": ROUND, "module": "all", "role": "dev"})
        p = os.path.join(R1_REFS, f"{u['event_id']}.npz")
        if os.path.exists(p):
            meta = json.loads(str(np.load(p, allow_pickle=True)["meta"]))
            if meta.get("bbox"):
                u["geometry"] = {"type": "boxes", "boxes": [{"round": "flood_final", "module":
                                                             u["flood_final"]["tags"][0], "bbox": meta["bbox"]}],
                                 "note": "reference box of the flood_final held-out pass"}
        out.append(u["event_id"])
    return out


def reserved_units() -> list:
    saved = (RF.EF.RESERVED_EMS, RF.EF.RESERVED_S1, RF.ROUND)
    RF.EF.RESERVED_EMS, RF.EF.RESERVED_S1, RF.ROUND = E.RESERVED_EMS_R2, E.RESERVED_S1_R2, ROUND
    try:
        units = RF.reserved_units()
    finally:
        RF.EF.RESERVED_EMS, RF.EF.RESERVED_S1, RF.ROUND = saved
    for u in units:
        u["flood_round2"] = u.pop("flood_final")
        u["flood_final"] = u["flood_round2"]          # registry tooling reads this key for tags/region
    return units


def dev_units() -> list:
    out = []
    for code, (tags, region, link) in E.DEV_EMS_R2.items():
        p = os.path.join(DEV_REFS, f"{code}.json")
        if not os.path.exists(p):
            print("no references built for", code)
            continue
        a = json.load(open(p))
        q = sorted((x for x in a["aois"] if x["qualifies"]),
                   key=lambda x: (-x["flooded_cells"], x["aoi"]))[:E.DEV_AOIS_PER_ACTIVATION]
        for x in q:
            out.append({"event_id": x["unit"], "role": "dev", "kind": "event", "date": a["event"],
                        "storm_cluster": code, "region_cluster": None, "products": [f"{code}:AOI{x['aoi']:02d}"],
                        "uses": [{"round": ROUND, "module": t, "role": "dev"} for t in tags],
                        "exposure_level": 3, "exposure_note": "flood_round2 DEV: EMS reference built",
                        "geometry": {"type": "boxes", "boxes": [{"round": ROUND, "module": tags[0], "bbox": x["bbox"]}]},
                        "flood_final": {"tags": list(tags), "region": region, "storm_link": link,
                                        "aoi_name": x["aoi_name"], "flooded_cells": x["flooded_cells"],
                                        "dry_cells": x["dry_cells"]}})
    for name, (tags, region, pt, date, basis) in E.DEV_S1_R2.items():
        out.append({"event_id": name, "role": "dev", "kind": "event", "date": date, "storm_cluster": name,
                    "region_cluster": None, "products": ["S1"],
                    "uses": [{"round": ROUND, "module": t, "role": "dev"} for t in tags],
                    "exposure_level": 1, "exposure_note": "flood_round2 DEV: town point and date; reference not yet built",
                    "geometry": {"type": "point_approx", "point": pt, "note": basis},
                    "flood_final": {"tags": list(tags), "region": region, "basis": basis,
                                    "reference": ["s1", pt[1], pt[0], date]}})
    return out


def _main_basin_only_far(u, exc, dev) -> bool:
    """R7: every exception link is main_basin, to another storm, > MAIN_BASIN_MIN_KM away."""
    by = {d["event_id"]: d for d in dev}
    for oid, rule, _ in exc:
        d = by[oid]
        if rule != "main_basin" or d.get("storm_cluster") == u.get("storm_cluster") \
                or _km(_point(u), _point(d)) <= E.MAIN_BASIN_MIN_KM:
            return False
    return True


def _links(u, others):
    out = [(o["event_id"], rule, sev) for o in others for rule, sev in REG.links(u, o)]
    if u["geometry"]["type"] == "point_approx":
        for o in others:
            if o["geometry"]["type"] == "point_approx" and _km(_point(u), _point(o)) <= REG.PROXIMITY_KM:
                out.append((o["event_id"], "proximity_point", REG.BLOCK))
    return out


def main(argv=None):
    a = argv or sys.argv[1:]
    step, write = a[0], "--write" in a
    reg = REG.load()
    have = set(REG.units(reg))
    log = {"step": step, "dropped": [], "accepted_exception_links": {}}
    if step == "reserved_add":
        saved = E.RESERVED_EMS_R2, E.RESERVED_S1_R2
        E.RESERVED_EMS_R2, E.RESERVED_S1_R2 = {}, E.RESERVED_S1_R2_ADD
        try:
            new = reserved_units()
        finally:
            E.RESERVED_EMS_R2, E.RESERVED_S1_R2 = saved
        b = RF.basins({u["event_id"]: _point(u) for u in new})
        for u in new:
            if u["event_id"] in have:
                raise SystemExit(f"{u['event_id']} already registered")
            u["basins"] = b.get(u["event_id"], {"note": "centre outside HydroBASINS"})
        dev = [u for u in reg["units"] if u["role"] == "dev"]
        kept = []
        for u in new:
            links = _links(u, dev)
            block = [x for x in links if x[2] == REG.BLOCK]
            exc = [x for x in links if x[2] != REG.BLOCK]
            if exc and not block and _main_basin_only_far(u, exc, dev):
                log["accepted_exception_links"][u["event_id"]] = exc[:6]
                exc = []
            if block or exc:
                log["dropped"].append({"event_id": u["event_id"], "links": links[:6]})
                continue
            kept.append(u)
    elif step == "reserved":
        flipped = flip_round1(reg)
        log["flipped_to_dev"] = flipped
        new = reserved_units()
        b = RF.basins({u["event_id"]: _point(u) for u in new})
        for u in new:
            if u["event_id"] in have:
                raise SystemExit(f"{u['event_id']} already registered")
            u["basins"] = b.get(u["event_id"], {"note": "centre outside HydroBASINS"})
        dev = [u for u in reg["units"] if u["role"] == "dev"]
        kept = []
        for u in new:
            links = _links(u, dev)
            block = [x for x in links if x[2] == REG.BLOCK]
            exc = [x for x in links if x[2] != REG.BLOCK]
            if exc and not block and _main_basin_only_far(u, exc, dev):
                log["accepted_exception_links"][u["event_id"]] = exc[:6]
                exc = []
            if block or (exc and u["event_id"] not in E.ACCEPTED_EXCEPTION_LINKS):
                log["dropped"].append({"event_id": u["event_id"], "links": links[:6]})
                continue
            kept.append(u)
        print(f"flipped {len(flipped)} flood_final reserved units to dev")
    else:
        new = dev_units()
        b = RF.basins({u["event_id"]: _point(u) for u in new})
        for u in new:
            if u["event_id"] in have:
                raise SystemExit(f"{u['event_id']} already registered")
            u["basins"] = b.get(u["event_id"], {"note": "centre outside HydroBASINS"})
        res = [u for u in reg["units"] if u["role"] == "reserved"]
        kept = []
        for u in new:
            links = _links(u, res) + [x for r in res for x in _links(r, [u])]
            if links:
                log["dropped"].append({"event_id": u["event_id"], "links": links[:6]})
                continue
            kept.append(u)
    for x in log["dropped"]:
        print("dropped", x["event_id"], x["links"][:3])
    for k, v in log["accepted_exception_links"].items():
        print("accepted (R7)", k, v[:3])
    import collections
    print("kept by tag", dict(collections.Counter(t for u in kept for t in u["flood_final"]["tags"])))
    print(f"{step}: kept {len(kept)}/{len(new)}")
    if write:
        reg["units"].extend(kept)
        with open(REG.PATH, "w") as fh:
            json.dump(reg, fh, indent=1)
        prev = json.load(open(UNITS_OUT)) if os.path.exists(UNITS_OUT) else {"units": [], "logs": []}
        prev["units"] += kept
        prev["logs"].append(log)
        with open(UNITS_OUT, "w") as fh:
            json.dump(prev, fh, indent=1)
        print("wrote", REG.PATH, "and", UNITS_OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
