"""
M6–M8 v2, Amendment 6 (owner 2026-11-28): M7 strata from metadata only, written before any reserve access.

    python -m experiments.flood_m678.v2.m7_strata 2.3      # -> m7_strata_<seal>.json

- primary   : levee/embankment breaches, and reservoir breaches whose reservoir holds >= 3 million m3 (ICOLD's
              storage criterion for a large dam). The water persists, so a satellite can still see it.
- small_dam : every other reservoir breach (storage below 3 million m3, or unknown). Scenario-only in the
              product. Scored only where its label passes the floor, and reported as its own stratum.
Storage per lead: the largest of ASDSO "Max Storage" (acre-ft), NID "Max Storage" / "NID Storage" (acre-ft, via
the NID number) and NPDP "Normal Reservoir Storage" (m3). A component is primary if any of its timed leads is.
"""
from __future__ import annotations

import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.expanduser("~/.cache/geowatch/m678v2/sources")
LARGE_M3 = 3.0e6
ACFT_M3 = 1233.48


def _f(x):
    try:
        v = float(str(x).replace(",", ""))
        return v if v > 0 else None
    except ValueError:
        return None


def storages():
    csv.field_size_limit(1 << 26)
    fh = open(os.path.join(SRC, "nid", "nation.csv"), encoding="utf-8-sig", errors="replace")
    next(fh)
    nid = {}
    for r in csv.DictReader(fh):
        v = [_f(r.get("Max Storage (Acre-Ft)")), _f(r.get("NID Storage (Acre-Ft)"))]
        v = [x * ACFT_M3 for x in v if x]
        if v:
            nid[r["NID ID"].strip()] = max(v)
    out = {}
    for r in csv.DictReader(open(os.path.join(SRC, "asdso", "asdso_incidents.csv"), encoding="utf-8-sig", errors="replace")):
        v = [x for x in (_f(r.get("Max Storage")) and _f(r.get("Max Storage")) * ACFT_M3,
                         nid.get((r.get("NID Number") or "").strip())) if x]
        if v:
            out[f"asdso:{(r.get('Incident ID') or '').strip()}"] = max(v)
    for r in csv.DictReader(open(os.path.join(SRC, "npdp", "npdp_failures_1984.csv"))):
        v = _f(r.get("storage_m3"))
        if v:
            out[f"npdp:{r['event_id']}"] = v
    return out


def build(version):
    seal = json.load(open(os.path.join(HERE, f"seal_{version}.json")))
    st = storages()
    sub = {r["lead_id"]: r["submode"] for r in csv.DictReader(open(os.path.join(HERE, "leads.csv")))}
    res = {"seal": version, "large_m3": LARGE_M3, "components": {}}
    for side in ("reserve", "dev"):
        for c in seal[side]:
            if c["type"] != "M7":
                continue
            leads = []
            for x in c["leads"]:
                lid = x["lead_id"]
                s = st.get(lid)
                leads.append({"lead_id": lid, "submode": sub.get(lid), "storage_m3": s,
                              "primary": bool(sub.get(lid) == "levee_breach" or (s is not None and s >= LARGE_M3))})
            res["components"][c["component"]] = {"side": side, "submode": c["submode"],
                                                 "stratum": "primary" if any(l["primary"] for l in leads) else "small_dam",
                                                 "leads": leads}
    cnt = {}
    for c in res["components"].values():
        k = f"{c['side']}/{c['stratum']}"
        cnt[k] = cnt.get(k, 0) + 1
    res["counts"] = cnt
    json.dump(res, open(os.path.join(HERE, f"m7_strata_{version}.json"), "w"), indent=1, sort_keys=True)
    print(json.dumps(cnt, sort_keys=True))


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "2.3")
