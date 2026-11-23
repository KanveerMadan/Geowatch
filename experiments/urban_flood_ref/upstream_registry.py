"""
Flood event registry and reuse guard (flood-core prototype; not used by any
production harness).

Why: round 4b's guard (`harness_round4b.earlier_event_names`) compares event
NAMES only. In this repo, paiporta / valencia_2024 are one EMS product,
derna / derna_2023 overlap, jakarta / jakarta_gfd_3280 share a box, and
chennai_velachery / chennai_2023 are one cyclone. A name check passes all of
them.

Rules, applied between a unit under check and every dev unit:

    rule              link                                    severity
    alias_product     a shared product id (not bare S1/JRC)   block
    alias_geometry    boxes intersect                         block
    proximity         reserved point within PROXIMITY_KM      block
                      of a dev box
    storm             same storm cluster                      block
    main_basin        same HydroBASINS MAIN_BAS               needs_signed_exception
    sub_basin         same HydroBASINS hybas_<BASIN_LEVEL>    needs_signed_exception
    region            same curated region cluster             needs_signed_exception

PROXIMITY_KM and BASIN_LEVEL are judgements, not measured thresholds:
PROXIMITY_KM = 20 is the side of round 4's pre-registered Sentinel-1 search
square (the largest search extent any round used); BASIN_LEVEL = 6 is the
finer of the two levels annotated. README.md records both as open choices.
"""
from __future__ import annotations

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "events.json")
GENERIC_PRODUCTS = {"S1", "JRC"}
PROXIMITY_KM = 20.0
BASIN_LEVEL = 6
BLOCK, EXCEPTION = "block", "needs_signed_exception"


def load(path: str = PATH) -> dict:
    reg = json.load(open(path))
    ids = [u["event_id"] for u in reg["units"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate event_id in registry")
    for u in reg["units"]:
        if u["role"] not in ("dev", "reserved", "retired"):
            raise ValueError(f"{u['event_id']}: bad role {u['role']}")
        if not 0 <= u["exposure_level"] <= 6:
            raise ValueError(f"{u['event_id']}: exposure_level out of range")
        if u["role"] == "reserved" and u["geometry"]["type"] == "boxes":
            raise ValueError(f"{u['event_id']}: a reserved unit must not carry a reference-derived box")
    return reg


def units(reg: dict) -> dict:
    return {u["event_id"]: u for u in reg["units"]}


def _boxes(u):
    g = u["geometry"]
    return [b["bbox"] for b in g.get("boxes", [])] if g["type"] == "boxes" else []


def _intersects(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _km_point_to_box(p, b) -> float:
    lon = min(max(p[0], b[0]), b[2])
    lat = min(max(p[1], b[1]), b[3])
    dy = (p[1] - lat) * 111.32
    dx = (p[0] - lon) * 111.32 * math.cos(math.radians((p[1] + lat) / 2))
    return math.hypot(dx, dy)


def links(a: dict, b: dict) -> list:
    """[(rule, severity)] linking units a and b."""
    out = []
    pa = {p for p in a.get("products", []) if p not in GENERIC_PRODUCTS}
    pb = {p for p in b.get("products", []) if p not in GENERIC_PRODUCTS}
    if pa & pb:
        out.append(("alias_product", BLOCK))
    if any(_intersects(x, y) for x in _boxes(a) for y in _boxes(b)):
        out.append(("alias_geometry", BLOCK))
    for u, v in ((a, b), (b, a)):
        if u["geometry"]["type"] == "point_approx" and any(
                _km_point_to_box(u["geometry"]["point"], y) <= PROXIMITY_KM for y in _boxes(v)):
            out.append(("proximity", BLOCK))
            break
    if a.get("storm_cluster") and a.get("storm_cluster") == b.get("storm_cluster"):
        out.append(("storm", BLOCK))
    ba, bb = a.get("basins", {}), b.get("basins", {})
    if ba.get("main_bas") and ba.get("main_bas") == bb.get("main_bas"):
        out.append(("main_basin", EXCEPTION))
    key = f"hybas_{BASIN_LEVEL}"
    if ba.get(key) and ba.get(key) == bb.get(key):
        out.append(("sub_basin", EXCEPTION))
    if a.get("region_cluster") and a.get("region_cluster") == b.get("region_cluster"):
        out.append(("region", EXCEPTION))
    return out


def conflicts(reg: dict, unit, against_role: str = "dev") -> list:
    """Every link from `unit` (an event_id or a unit dict) to units of
    `against_role`: [{"other", "rule", "severity"}]."""
    u = units(reg)[unit] if isinstance(unit, str) else unit
    out = []
    for other in reg["units"]:
        if other["event_id"] == u["event_id"] or other["role"] != against_role:
            continue
        for rule, sev in links(u, other):
            out.append({"other": other["event_id"], "rule": rule, "severity": sev})
    return out


def verdict(reg: dict, unit, exceptions: dict | None = None) -> str:
    """'clear', 'blocked', or 'needs_signed_exception'. `exceptions` maps
    (other, rule) -> a person's signed note; it can clear EXCEPTION links only."""
    exceptions = exceptions or {}
    cs = conflicts(reg, unit)
    if any(c["severity"] == BLOCK for c in cs):
        return "blocked"
    if any((c["other"], c["rule"]) not in exceptions for c in cs):
        return "needs_signed_exception" if cs else "clear"
    return "clear"


def alias_groups(reg: dict) -> list:
    """Connected components of dev units under BLOCK links (sorted)."""
    dev = [u for u in reg["units"] if u["role"] == "dev"]
    parent = {u["event_id"]: u["event_id"] for u in dev}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, a in enumerate(dev):
        for b in dev[i + 1:]:
            if any(s == BLOCK for _, s in links(a, b)):
                parent[find(a["event_id"])] = find(b["event_id"])
    groups = {}
    for u in dev:
        groups.setdefault(find(u["event_id"]), []).append(u["event_id"])
    return sorted(sorted(g) for g in groups.values() if len(g) > 1)


def name_only_guard(candidate: str, earlier: set) -> bool:
    """What round 4b's harness does: True if the name was used before."""
    return candidate in earlier
