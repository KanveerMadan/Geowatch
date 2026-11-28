"""
M6–M8 v2 step 1e: the metadata-only seal (BUILD_PLAN step 1).

    python -m experiments.flood_m678.v2.seal_v2 <version>      # e.g. 2.0; writes seal_<v>.json and SEAL.md

- A reserve component has at least one timed, full-box lead on or after 2022-01-01 and no
  inspected or quarantined unit. Its pre-2022 leads are withheld from DEV.
- A DEV component has at least one timed, full-box lead and is not a reserve component.
- Components are listed whole, by type and submode (majority of the component's timed leads).
- No label exists for any v2 incident at seal time. Later leads enter an addendum seal
  (2.1, 2.2, ...) under the same rules, before any reserve access; earlier assignments never change.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = ("registry.json", "SELECTION.md", "leads.csv", "clusters.csv", "screening.csv")


def sha(p):
    return hashlib.sha256(open(os.path.join(HERE, p), "rb").read()).hexdigest()


KEYED_FROM = (2, 2)                     # Amendment 4: keyed split for components entering from seal 2.2
ENFORCE_FROM = (2, 3)                   # Amendment 5: SELECTION §4 exclusions enforced in code from seal 2.3
EXCLUDED_LEADS = {                      # Amendment 5: named exclusions (component excluded whole)
    "ems_peer:EMSR753": "round-3 public EMS reserve pool (r3_emsr753_aoi01); round 3 keeps it",
    "handlocated:EMSR753": "round-3 public EMS reserve pool (r3_emsr753_aoi01); round 3 keeps it",
}
R3_LIVE = ("~/gw-floodproto", "exp/flood-round3")   # round 3's reserve metadata, rechecked at seal time (§4)


def version_tuple(v):
    return tuple(int(x) for x in v.split("."))


def keyed_side(cid):
    import hmac
    key = open(os.path.join(HERE, "split_key.txt")).read().strip().encode()
    h = hmac.new(key, cid.encode(), hashlib.sha256).hexdigest()
    return "reserve" if int(h[:8], 16) / 2 ** 32 < 0.5 else "dev"


def labelled_leads():
    d = os.path.expanduser("~/.cache/geowatch/m678v2/dev/labels")
    return {f[:-4].replace("__", ":") for f in os.listdir(d)} if os.path.isdir(d) else set()


def exclusion_boxes():
    """Round 3's footprints: the pinned registry.json set plus the candidate pools at round 3's current head."""
    import subprocess
    from experiments.flood_m678.v2 import registry as R
    geo = [g["bbox"] for g in json.load(open(os.path.join(HERE, "registry.json")))["exclusion_geometry"]]
    repo = os.path.expanduser(R3_LIVE[0])
    head = subprocess.check_output(["git", "-C", repo, "rev-parse", R3_LIVE[1]], text=True).strip()
    for name, key in R.R3_CANDIDATES.items():
        try:
            d = json.loads(subprocess.check_output(["git", "-C", repo, "show", f"{head}:experiments/flood_round3/results/{name}.json"]))
        except subprocess.CalledProcessError:
            continue
        geo += [row[key] for row in d["candidates"] if row.get(key)]
    return geo, head


def touches(lead, boxes, km=10.0):
    """SELECTION §4: the lead's 20 km search square (anchor ± 10 km) intersects any footprint box."""
    import math
    try:
        lat, lon = float(lead["lat"]), float(lead["lon"])
    except (TypeError, ValueError):
        return False
    dl, dg = km / 111.0, km / (111.0 * max(math.cos(math.radians(lat)), 1e-3))
    x0, y0, x1, y1 = lon - dg, lat - dl, lon + dg, lat + dl
    return any(not (x1 < b[0] or x0 > b[2] or y1 < b[1] or y0 > b[3]) for b in boxes)


def build(version):
    labelled = labelled_leads()
    enforce = version_tuple(version) >= ENFORCE_FROM
    if enforce:
        boxes, r3_head = exclusion_boxes()
        anchors = {r["lead_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "leads.csv")))}
    scr = list(csv.DictReader(open(os.path.join(HERE, "screening.csv"))))
    prev, lead_side = {}, {}
    for f in sorted(os.listdir(HERE)):
        if f.startswith("seal_") and f.endswith(".json") and f != f"seal_{version}.json":
            for side in ("reserve", "dev"):
                for c in json.load(open(os.path.join(HERE, f)))[side]:
                    prev[c["component"]] = side
                    for x in c["leads"]:
                        lead_side[x["lead_id"]] = (side, c["component"])
    crow = list(csv.DictReader(open(os.path.join(HERE, "clusters.csv"))))
    cluster_of = {r["id"]: r["component"] for r in crow}
    status_of = {r["component"]: r["status"] for r in crow}
    comps = {}
    for r in scr:
        if r["status"] != "timed_footprint":
            continue
        cid = cluster_of.get(r["lead_id"], r["component"])          # the current join decides grouping
        st = status_of.get(cid)
        comps.setdefault(cid, {"side": "dev_only" if st == "dev_only_inspected" else r["side"], "leads": []})["leads"].append(r)
    out = {"reserve": [], "dev": [], "excluded_addendum": []}
    for cid, c in sorted(comps.items()):
        # Earlier assignments never change: a component sharing any lead with a sealed component keeps
        # that side; one that merges components from both sides is excluded (conservative).
        sides = {lead_side[x["lead_id"]][0] for x in c["leads"] if x["lead_id"] in lead_side}
        if len(sides) > 1:
            out["excluded_addendum"].append({"component": cid, "reason": "joins sealed DEV and reserve components"})
            continue
        named = sorted({EXCLUDED_LEADS[x["lead_id"]] for x in c["leads"] if x["lead_id"] in EXCLUDED_LEADS})
        if enforce and named:
            out["excluded_addendum"].append({"component": cid, "reason": "; ".join(named)})
            continue
        keyed = False
        if sides:
            side = sides.pop()
        elif cid in prev:
            side = prev[cid]
        elif KEYED_FROM and version_tuple(version) >= KEYED_FROM:
            inspected = c["side"] == "dev_only" or any(x["lead_id"] in labelled for x in c["leads"])
            has_pre = any(x["date"] < "2022-01-01" for x in c["leads"])
            if inspected:
                side = "dev"
            elif has_pre:                                  # Amendment 4a: keyed only with a pre-2022 incident
                side, keyed = keyed_side(cid), True
            else:
                side = "reserve"
        else:
            side = "dev" if c["side"] == "dev_only" else c["side"]
        if side == "reserve" and not keyed:
            c["leads"] = [x for x in c["leads"] if x["date"] >= "2022-01-01"]
        if enforce and side == "reserve" and any(touches(anchors.get(x["lead_id"], {}), boxes) for x in c["leads"]):
            if cid in prev or sides:
                raise SystemExit(f"sealed reserve component {cid} touches a round-3 footprint: stop and report")
            out["excluded_addendum"].append({"component": cid, "reason": "20 km search square touches a round-3 footprint (§4)"})
            continue
        if not c["leads"]:
            continue
        ty = Counter(f"{x['type']}/{x['submode']}" for x in c["leads"]).most_common(1)[0][0]
        out[side].append({"component": cid, "type": ty.split("/")[0], "submode": ty.split("/")[1],
                          "leads": [{k: x[k] for k in ("lead_id", "date", "crest_utc_min", "crest_utc_max",
                                                       "crest_kind", "optical", "paired_radar")} for x in c["leads"]]})
    counts = {side: dict(Counter(f"{c['type']}/{c['submode']}" for c in out[side])) for side in ("reserve", "dev")}
    seal = {"version": version, "sealed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "inputs_sha256": {f: sha(f) for f in FILES}, "counts_components": counts, **out}
    if enforce:
        seal["round3_head_checked"] = r3_head
    p = os.path.join(HERE, f"seal_{version}.json")
    blob = json.dumps(seal, indent=1, sort_keys=True) + "\n"
    open(p, "w").write(blob)
    h = hashlib.sha256(blob.encode()).hexdigest()
    with open(os.path.join(HERE, "SEAL.md"), "a") as fh:
        fh.write(f"\n## Seal {version} ({seal['sealed_utc']})\n\n- `seal_{version}.json` sha256 `{h}`\n")
        for f, v in seal["inputs_sha256"].items():
            fh.write(f"- `{f}` sha256 `{v}`\n")
        fh.write("- components, reserve: " + json.dumps(counts["reserve"], sort_keys=True) + "\n")
        fh.write("- components, DEV: " + json.dumps(counts["dev"], sort_keys=True) + "\n")
        fh.write("- metadata only: no v2 label, feature or score existed when this was written.\n")
    print(h, json.dumps(counts))
    return h


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "2.0")
