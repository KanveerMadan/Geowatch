"""Mechanical M6–M8 split from metadata only (RESERVE_CRITERIA_M678.md and its addendum).

Reads catalog.csv, scene_metadata.json, overlap_metadata.json and event_evidence.json. Reads no
image pixel, label, feature or score. Writes reserve_m678.json (the sealed reserve) and
dev_m678.json (the development pool). Rules, in order:

1. An incident qualifies when its screening is `timed_footprint` (crest evidence plus a full-box
   scene inside the type's window) and it is not excluded.
2. A reserve incident (2022 onwards) is refused when the round-3 overlap check finds any
   geographic match for its 20 km search square.
3. A cluster with at least one qualifying reserve incident is a reserve cluster. Its pre-2022
   incidents are withheld from DEV (DECISIONS 2026-11-27).
4. At most two incidents per reserve cluster, earliest date first (round 3's two units per
   activation), so a recurring lake cannot dominate the mean.
5. Every other qualifying pre-2022 incident is DEV.

    python select_m678.py
"""
import csv
import hashlib
import json
from datetime import datetime, timezone

from screen_acquisitions import HERE, write_file

PER_CLUSTER = 2


def load():
    rows = list(csv.DictReader((HERE / "catalog.csv").open()))
    scenes = json.loads((HERE / "scene_metadata.json").read_text())
    overlap = json.loads((HERE / "overlap_metadata.json").read_text())["records"]
    ev = json.loads((HERE / "event_evidence.json").read_text())
    by_id = {e["site"] + "-" + e["date"]: e for e in ev["events"]}
    return rows, scenes, overlap, by_id


def record(row, scenes, by_id):
    s = scenes[row["incident_id"]]
    e = by_id[row["incident_id"]]
    return {"incident": row["incident_id"], "type": row["type"], "subtype": row["subtype"], "cluster": row["cluster"],
            "date": row["date"], "reach": row["reach"], "reach_point": [float(row["latitude"]), float(row["longitude"])],
            "crest_utc": [s["crest_utc_min"], s["crest_utc_max"]], "crest_kind": s["crest_kind"],
            "window_utc": s["window_utc"], "not_before_utc": e.get("not_before_utc"),
            "scenes": s["scenes"], "source": row["source"], "peak_source": row["peak_source"]}


def select():
    rows, scenes, overlap, by_id = load()
    ok = [r for r in rows if r["screening"] == "timed_footprint"]
    refused = {}
    res = []
    for r in ok:
        if r["split"] == "DEV":
            continue
        o = overlap.get(r["incident_id"], {})
        if o.get("status") != "no_match_in_available_geometry":
            refused[r["incident_id"]] = o.get("status", "no_overlap_record")
            continue
        res.append(r)
    res_clusters = {(r["type"], r["cluster"]) for r in res}
    reserve, withheld, dev = {}, [], {}
    for r in sorted(res, key=lambda r: (r["type"], r["cluster"], r["date"], r["incident_id"])):
        c = reserve.setdefault(r["type"], {}).setdefault(r["cluster"], [])
        if len(c) < PER_CLUSTER:
            c.append(record(r, scenes, by_id))
        else:
            refused[r["incident_id"]] = f"cluster already has {PER_CLUSTER} incidents"
    for r in ok:
        if r["split"] != "DEV":
            continue
        if (r["type"], r["cluster"]) in res_clusters:
            withheld.append(r["incident_id"])
            continue
        dev.setdefault(r["type"], {}).setdefault(r["cluster"], []).append(record(r, scenes, by_id))
    return reserve, dev, sorted(withheld), refused


def main():
    reserve, dev, withheld, refused = select()
    crit = (HERE / "RESERVE_CRITERIA_M678.md").read_bytes()
    out = {"criteria_sha256": hashlib.sha256(crit).hexdigest(), "per_cluster": PER_CLUSTER,
           "counts": {t: {"clusters": len(c), "incidents": sum(map(len, c.values()))} for t, c in sorted(reserve.items())},
           "reserve": reserve, "refused": refused, "withheld_dev_incidents": withheld}
    write_file(HERE / "reserve_m678.json", json.dumps(out, indent=1, sort_keys=True) + "\n")
    write_file(HERE / "dev_m678.json", json.dumps({
        "counts": {t: {"clusters": len(c), "incidents": sum(map(len, c.values()))} for t, c in sorted(dev.items())},
        "dev": dev}, indent=1, sort_keys=True) + "\n")
    print(json.dumps(out["counts"]), "| DEV", json.dumps({t: len(c) for t, c in dev.items()}))


if __name__ == "__main__":
    main()
