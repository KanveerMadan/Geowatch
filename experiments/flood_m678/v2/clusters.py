"""
M6–M8 v2 step 1c: join leads into independent components (SELECTION.md §3 and Amendment 1),
with v1 incidents and round-3 DEV units as extra nodes so their components are marked.

    python -m experiments.flood_m678.v2.clusters      # -> clusters.csv, components.json
"""
from __future__ import annotations

import csv
import json
import os
import re
from datetime import date

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STOP = {"RIVER", "RIV", "R", "AT", "NEAR", "NR", "BELOW", "ABOVE", "BLW", "ABV", "THE", "CREEK", "CR", "LAKE",
        "OUTLET", "INLET", "MOUTH", "FORK", "NORTH", "SOUTH", "EAST", "WEST", "N", "S", "E", "W", "USGS", "WSC",
        "AND", "OF", "DE", "LA", "DU", "AU", "STATION", "ST", "SAINT", "LITTLE", "BIG", "UPPER", "LOWER"}
KM_JOIN, DAYS_JOIN = 20.0, 30


class UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, a):
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def river_token(anchor):
    """The first meaningful word of a station name: the river (e.g. 'RED' for 'RED RIVER AT FARGO')."""
    m = re.sub(r"^(USGS|WSC)\s+\S+\s+", "", anchor or "").upper()
    toks = [t for t in re.split(r"[^A-Z]+", m) if t and t not in STOP and len(t) > 1]
    return toks[0] if toks else None


def nodes():
    from experiments.flood_m678.v2 import registry as R
    reg = R.load()
    out = []
    for r in csv.DictReader(open(os.path.join(HERE, "leads.csv"))):
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
        except ValueError:
            lat = lon = None
        if r["anchor"] == "country only":
            lat = lon = None
        out.append({"id": r["lead_id"], "kind": "lead", "type": r["type"], "submode": r["submode"], "date": r["date"][:10],
                    "lat": lat, "lon": lon, "station": r["anchor"].split(" ")[1] if r["anchor"].startswith(("USGS", "WSC")) else None,
                    "lake": r["anchor"][5:].split(" / ")[0] if r["anchor"].startswith("lake ") else None,
                    "river": river_token(r["anchor"]), "region": r["region"], "country": r["country"],
                    "storm": r.get("storm") or None})
    cat = list(csv.DictReader(R.show(R.PINS["v1_reserve_seal"], "experiments/flood_m678/catalog.csv").decode().splitlines()))
    quar, devonly = set(reg["v1"]["incidents"]), set(reg["v1"]["dev_only_incidents"])
    for r in cat:
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except ValueError:
            continue
        status = "v1_reserve" if r["incident_id"] in quar else "inspected" if r["incident_id"] in devonly else "v1_catalogue"
        out.append({"id": f"v1:{r['incident_id']}", "kind": status, "type": r["type"], "submode": r["subtype"], "date": r["date"],
                    "lat": lat, "lon": lon, "station": None, "lake": None, "river": None, "region": r["country"], "country": r["country"]})
    for n, r in reg["round3_dev_whitelist"].items():
        b = r.get("bbox")
        if not b or not r.get("event"):
            continue
        out.append({"id": f"r3:{n}", "kind": "inspected", "type": "R3", "submode": ",".join(r.get("tags") or []),
                    "date": r["event"][:10], "lat": (b[1] + b[3]) / 2, "lon": (b[0] + b[2]) / 2, "station": None,
                    "lake": None, "river": None, "region": r.get("region"), "country": ""})
    return out


def join(ns):
    from scipy.spatial import cKDTree
    uf = UF(len(ns))
    for key in ("station", "lake", "storm"):
        first = {}
        for i, n in enumerate(ns):
            k = n.get(key)
            if k:
                if k in first:
                    uf.union(first[k], i)
                else:
                    first[k] = i
    idx = [i for i, n in enumerate(ns) if n["lat"] is not None]
    lat = np.radians([ns[i]["lat"] for i in idx])
    lon = np.radians([ns[i]["lon"] for i in idx])
    xyz = np.c_[np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]
    tree = cKDTree(xyz)
    chord = 2 * np.sin(KM_JOIN / 6371.0 / 2)
    days = {}
    for a, b in tree.query_pairs(chord):
        i, j = idx[a], idx[b]
        ni, nj = ns[i], ns[j]
        try:
            dd = abs((date.fromisoformat(ni["date"]) - date.fromisoformat(nj["date"])).days)
        except ValueError:
            dd = 10 ** 6
        same_river = ni["river"] and ni["river"] == nj["river"]
        if dd <= DAYS_JOIN or same_river:
            uf.union(i, j)
    comp = {}
    for i in range(len(ns)):
        comp.setdefault(uf.find(i), []).append(i)
    return comp


def main():
    ns = nodes()
    comp = join(ns)
    rows, summary = [], {}
    for root, mem in comp.items():
        cid = "c" + ns[min(mem, key=lambda i: ns[i]["id"])]["id"].replace(":", "_")[:60]
        kinds = {ns[i]["kind"] for i in mem}
        leads = [ns[i] for i in mem if ns[i]["kind"] == "lead"]
        status = ("excluded_v1_reserve" if "v1_reserve" in kinds else "dev_only_inspected" if "inspected" in kinds
                  else "candidate")
        for i in mem:
            n = ns[i]
            rows.append({"component": cid, "status": status, **{k: n[k] for k in ("id", "kind", "type", "submode", "date",
                                                                                  "lat", "lon", "region", "country")}})
        if leads:
            k = status
            summary[k] = summary.get(k, 0) + 1
    with open(os.path.join(HERE, "clusters.csv"), "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["component"], r["date"], r["id"])))
    print(json.dumps({"nodes": len(ns), "components": len(comp), "lead_components_by_status": summary}))


if __name__ == "__main__":
    main()
