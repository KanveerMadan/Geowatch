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


def build(version):
    scr = list(csv.DictReader(open(os.path.join(HERE, "screening.csv"))))
    prev = {}
    for f in sorted(os.listdir(HERE)):
        if f.startswith("seal_") and f.endswith(".json") and f != f"seal_{version}.json":
            for side in ("reserve", "dev"):
                for c in json.load(open(os.path.join(HERE, f)))[side]:
                    prev[c["component"]] = side
    comps = {}
    for r in scr:
        if r["status"] != "timed_footprint":
            continue
        comps.setdefault(r["component"], {"side": r["side"], "leads": []})["leads"].append(r)
    out = {"reserve": [], "dev": []}
    for cid, c in sorted(comps.items()):
        side = prev.get(cid, c["side"])                   # earlier assignments never change
        if side == "reserve":
            c["leads"] = [x for x in c["leads"] if x["date"] >= "2022-01-01"]
        if not c["leads"]:
            continue
        ty = Counter(f"{x['type']}/{x['submode']}" for x in c["leads"]).most_common(1)[0][0]
        out[side].append({"component": cid, "type": ty.split("/")[0], "submode": ty.split("/")[1],
                          "leads": [{k: x[k] for k in ("lead_id", "date", "crest_utc_min", "crest_utc_max",
                                                       "crest_kind", "optical", "paired_radar")} for x in c["leads"]]})
    counts = {side: dict(Counter(f"{c['type']}/{c['submode']}" for c in out[side])) for side in out}
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
