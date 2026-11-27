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


def build(version):
    labelled = labelled_leads()
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
        if not c["leads"]:
            continue
        ty = Counter(f"{x['type']}/{x['submode']}" for x in c["leads"]).most_common(1)[0][0]
        out[side].append({"component": cid, "type": ty.split("/")[0], "submode": ty.split("/")[1],
                          "leads": [{k: x[k] for k in ("lead_id", "date", "crest_utc_min", "crest_utc_max",
                                                       "crest_kind", "optical", "paired_radar")} for x in c["leads"]]})
    counts = {side: dict(Counter(f"{c['type']}/{c['submode']}" for c in out[side])) for side in ("reserve", "dev")}
    seal = {"version": version, "sealed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "inputs_sha256": {f: sha(f) for f in FILES}, "counts_components": counts, **out}
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
